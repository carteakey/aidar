from __future__ import annotations

import asyncio
import sqlite3
from typing import TypedDict
from urllib.parse import urlparse

import click

from aidar.cli.main import aidar
from aidar.core.analyzer import Analyzer
from aidar.core.discovery import discover_urls, normalize_domain
from aidar.core.ingestion import ScanSummary, filter_prose_urls, scan_urls
from aidar.models.config import AppConfig
from aidar.output.renderer import console
from aidar.patterns.registry import PatternRegistry


class TrackSummary(TypedDict):
    status: str
    discovered: int
    queued: int
    saved: int
    filtered: int
    attempted: int
    failed: int
    reasons: dict[str, int]


@aidar.command()
@click.argument("domain")
@click.option(
    "--limit",
    default=100,
    show_default=True,
    help="Max pages to scan per run",
)
@click.option(
    "--concurrency",
    default=10,
    show_default=True,
    help="Concurrent HTTP requests",
)
@click.option(
    "--db",
    "db_path",
    default="aidar.db",
    show_default=True,
    help="SQLite database path",
)
@click.option(
    "--skip-existing/--no-skip-existing",
    default=True,
    show_default=True,
    help="Skip URLs already in the database",
)
@click.option(
    "--source",
    type=click.Choice(["auto", "sitemap", "rss"]),
    default="auto",
    show_default=True,
)
@click.option(
    "--rescan-stale/--no-rescan-stale",
    default=True,
    show_default=True,
    help="Automatically re-scan URLs when pattern revisions/fingerprints changed",
)
@click.option(
    "--skip-pattern",
    "skip_patterns",
    multiple=True,
    default=(),
    help="Skip URLs containing this substring (e.g. /tag/, /page/). Repeatable.",
)
@click.pass_context
def track(
    ctx: click.Context,
    domain: str,
    limit: int,
    concurrency: int,
    db_path: str,
    skip_existing: bool,
    source: str,
    rescan_stale: bool,
    skip_patterns: tuple[str, ...],
) -> None:
    """Discover and scan all pages for a domain, save results to DB.

    Designed to be run periodically (e.g. cron) to track stylistic drift.

    \b
    Examples:
      aidar track carteakey.dev
      aidar track medium.com --limit 200 --concurrency 20
      aidar track gwern.net --skip-pattern /doc/ --skip-pattern /doc
      aidar track ainewsinternational.com --skip-pattern /tag/ --skip-pattern /page/
    """
    run_track_domain(
        analyzer=ctx.obj["analyzer"],
        config=ctx.obj["config"],
        registry=ctx.obj["registry"],
        domain=domain,
        limit=limit,
        concurrency=concurrency,
        db_path=db_path,
        skip_existing=skip_existing,
        source=source,
        rescan_stale=rescan_stale,
        skip_patterns=skip_patterns,
    )


def run_track_domain(
    *,
    analyzer: Analyzer,
    config: AppConfig,
    registry: PatternRegistry,
    domain: str,
    limit: int = 100,
    concurrency: int = 10,
    db_path: str = "aidar.db",
    skip_existing: bool = True,
    source: str = "auto",
    rescan_stale: bool = True,
    skip_patterns: tuple[str, ...] = (),
) -> TrackSummary:
    """
    Shared track execution for CLI and background worker.
    Returns summary counters for observability.
    """
    base_url = normalize_domain(domain)
    domain_name = urlparse(base_url).netloc

    console.print(f"\n[bold]Tracking:[/bold] {domain_name}")
    console.print("[dim]Discovering URLs...[/dim]")

    from aidar.db.database import get_connection
    from aidar.db.queries import store_result, url_already_scanned

    conn = get_connection(db_path)

    urls, discovery_method = discover_urls(base_url, source)
    discovered_count = len(urls)
    summary = ScanSummary(discovered=discovered_count)
    if urls:
        console.print(f"[dim]Discovered {len(urls)} URLs via {discovery_method}.[/dim]")
    else:
        console.print(
            f"[yellow]Could not discover any URLs for {domain_name} via {source}.[/yellow]"
        )

    filtered_urls = filter_prose_urls(urls, base_url=base_url, skip_patterns=skip_patterns)
    urls = filtered_urls.kept
    summary.record_rejections(filtered_urls.rejected)

    if rescan_stale:
        from aidar.db.queries import get_stale_urls

        current_signatures = {p.id: (p.version, p.fingerprint()) for p in registry.all_patterns()}
        stale = set(get_stale_urls(conn, current_signatures, domain=domain_name))
        if stale:
            console.print(
                f"[yellow]{len(stale)} URLs stale (pattern changed) — forcing rescan.[/yellow]"
            )
            urls = list(stale | set(u for u in urls if not url_already_scanned(conn, u)))
        else:
            console.print("[dim]No stale URLs found.[/dim]")
            if skip_existing:
                before = len(urls)
                urls = [u for u in urls if not url_already_scanned(conn, u)]
                skipped = before - len(urls)
                summary.filtered += skipped
                summary.reasons["already_scanned"] += skipped
    elif skip_existing:
        before = len(urls)
        urls = [u for u in urls if not url_already_scanned(conn, u)]
        skipped = before - len(urls)
        if skipped:
            console.print(f"[dim]Skipping {skipped} already-scanned URLs.[/dim]")
            summary.filtered += skipped
            summary.reasons["already_scanned"] += skipped

    final_filter = filter_prose_urls(urls, base_url=base_url, skip_patterns=skip_patterns)
    urls = final_filter.kept
    summary.record_rejections(final_filter.rejected)

    if not urls:
        if discovered_count == 0:
            status = "no_discovery"
        else:
            console.print("[green]All URLs already up to date.[/green]")
            status = "all_existing"
        _print_domain_summary(conn, domain_name)
        console.print(
            "[bold]Run summary:[/bold] "
            f"discovered={summary.discovered} filtered={summary.filtered} "
            "attempted=0 saved=0 failed=0"
        )
        return {
            "status": status,
            "discovered": discovered_count,
            "queued": 0,
            "saved": 0,
            "filtered": summary.filtered,
            "attempted": 0,
            "failed": 0,
            "reasons": dict(summary.reasons),
        }

    if len(urls) > limit:
        deferred = len(urls) - limit
        summary.filtered += deferred
        summary.reasons["limit"] += deferred
        urls = urls[:limit]
    console.print(f"[bold]Scanning {len(urls)} URLs (concurrency={concurrency})...[/bold]\n")

    outcomes = asyncio.run(scan_urls(urls, analyzer, config, concurrency=concurrency))
    summary.record_outcomes(outcomes)
    results = [outcome.result for outcome in outcomes if outcome.result is not None]
    for result in results:
        store_result(conn, result)

    console.print(f"\n[green]Saved {len(results)} results to {db_path}[/green]")
    console.print(
        "[bold]Run summary:[/bold] "
        f"discovered={summary.discovered} filtered={summary.filtered} "
        f"attempted={summary.attempted} saved={summary.saved} failed={summary.failed}"
    )
    if summary.reasons:
        reasons = ", ".join(f"{key}={value}" for key, value in sorted(summary.reasons.items()))
        console.print(f"[dim]Ingestion reasons: {reasons}[/dim]")
    _print_domain_summary(conn, domain_name)
    return {
        "status": "scanned",
        "discovered": discovered_count,
        "queued": len(urls),
        "saved": len(results),
        "filtered": summary.filtered,
        "attempted": summary.attempted,
        "failed": summary.failed,
        "reasons": dict(sorted(summary.reasons.items())),
    }


def _print_domain_summary(conn: sqlite3.Connection, domain: str) -> None:
    from aidar.db.queries import get_domain_stats

    stats = get_domain_stats(conn, domain)
    if stats.get("scans", 0) == 0:
        return

    console.print(f"\n[bold]Domain summary:[/bold] {domain}")
    console.print(f"  Pages scanned : {stats['scans']}")
    console.print(f"  Avg index     : {stats['avg_score']}/100")
    console.print(f"  Range         : {stats['min_score']} – {stats['max_score']}")
    labels = stats.get("label_counts", {})
    console.print(
        f"  Labels        : "
        f"[red]{labels.get('LIKELY AI', 0)} AI[/red]  "
        f"[yellow]{labels.get('UNCERTAIN', 0)} uncertain[/yellow]  "
        f"[green]{labels.get('LIKELY HUMAN', 0)} human[/green]"
    )
