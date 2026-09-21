from __future__ import annotations

import asyncio
import json

import click

from aidar.cli._dates import parse_iso_date
from aidar.cli.main import aidar
from aidar.core.ingestion import ScanSummary, scan_urls
from aidar.core.wayback import WaybackError, discover_wayback_snapshots


@aidar.command("backfill")
@click.argument("domain")
@click.option("--db", "db_path", default="aidar.db", show_default=True)
@click.option("--limit", type=click.IntRange(min=1), default=None)
@click.option("--concurrency", type=click.IntRange(min=1), default=5, show_default=True)
@click.option("--min-words", type=click.IntRange(min=1), default=50, show_default=True)
@click.option(
    "--skip-existing/--rescan-existing",
    default=False,
    show_default=True,
    help="Skip persisted URLs (default rescans every historical URL).",
)
@click.option("--dry-run", is_flag=True, help="Report candidates without fetching or writing.")
@click.option("--wayback", is_flag=True, help="Opt in to bounded Wayback snapshot discovery.")
@click.option("--wayback-limit", type=click.IntRange(min=1, max=1000), default=100, show_default=True)
@click.option("--wayback-from", default=None, metavar="YYYY-MM-DD")
@click.option("--wayback-to", default=None, metavar="YYYY-MM-DD")
@click.pass_context
def backfill_command(
    ctx: click.Context,
    domain: str,
    db_path: str,
    limit: int | None,
    concurrency: int,
    min_words: int,
    skip_existing: bool,
    dry_run: bool,
    wayback: bool,
    wayback_limit: int,
    wayback_from: str | None,
    wayback_to: str | None,
) -> None:
    """Re-scan a domain's persisted URL history with resumable summaries."""
    from aidar.db.database import get_connection

    conn = get_connection(db_path)
    rows = conn.execute(
        """
        SELECT url FROM scans
        WHERE domain = ? AND url IS NOT NULL
        ORDER BY COALESCE(published_date, substr(scanned_at, 1, 10)), url
        """,
        (domain,),
    ).fetchall()
    persisted_urls = [str(row["url"]) for row in rows]
    snapshot_to_original: dict[str, str] = {}
    summary = ScanSummary(discovered=len(persisted_urls))
    wayback_from_date = parse_iso_date(wayback_from, "--wayback-from") if wayback_from else None
    wayback_to_date = parse_iso_date(wayback_to, "--wayback-to") if wayback_to else None
    if wayback_from_date and wayback_to_date and wayback_from_date > wayback_to_date:
        raise click.BadParameter("must not be after --wayback-to", param_hint="--wayback-from")
    urls = list(persisted_urls)
    if wayback:
        try:
            snapshots = discover_wayback_snapshots(
                domain,
                from_date=wayback_from_date,
                to_date=wayback_to_date,
                limit=wayback_limit,
            )
        except WaybackError as exc:
            summary.reasons[exc.reason] += 1
            payload = summary.as_dict()
            payload["queued"] = 0
            if ctx.obj["output"] == "json":
                click.echo(json.dumps(payload, indent=2, sort_keys=True))
            else:
                click.echo(f"{domain}: Wayback discovery failed ({exc.reason})")
            return
        for snapshot in snapshots:
            if snapshot.snapshot_url not in snapshot_to_original:
                snapshot_to_original[snapshot.snapshot_url] = snapshot.original_url
                urls.append(snapshot.snapshot_url)
        summary.discovered += len(snapshot_to_original)
    if skip_existing:
        # This switch is mainly useful when a caller supplies a future query
        # source; for the persisted-history source it intentionally records all
        # rows as already present and leaves no network side effects.
        persisted_count = len(persisted_urls)
        summary.filtered += persisted_count
        summary.reasons["already_scanned"] = persisted_count
        urls = [url for url in urls if url not in set(persisted_urls)]
    if limit is not None and len(urls) > limit:
        deferred = len(urls) - limit
        summary.filtered += deferred
        summary.reasons["limit"] += deferred
        urls = urls[:limit]

    if dry_run or not urls:
        payload = summary.as_dict()
        payload["queued"] = len(urls)
        if ctx.obj["output"] == "json":
            click.echo(json.dumps(payload, indent=2, sort_keys=True))
        else:
            click.echo(
                f"{domain}: discovered={payload['discovered']} queued={payload['queued']} "
                f"filtered={payload['filtered']} (dry-run={dry_run})"
            )
        return

    outcomes = asyncio.run(
        scan_urls(
            urls,
            ctx.obj["analyzer"],
            ctx.obj["config"],
            concurrency=concurrency,
            min_words=min_words,
        )
    )
    summary.record_outcomes(outcomes)
    from aidar.db.queries import store_result

    for outcome in outcomes:
        if outcome.result is not None:
            original_url = snapshot_to_original.get(outcome.url)
            if original_url:
                outcome.result.source_url = outcome.url
                outcome.result.url = original_url
            store_result(conn, outcome.result)
    payload = summary.as_dict()
    payload["queued"] = len(urls)
    if ctx.obj["output"] == "json":
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        click.echo(
            f"{domain}: discovered={payload['discovered']} queued={payload['queued']} "
            f"saved={payload['saved']} failed={payload['failed']}"
        )
