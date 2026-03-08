from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import click

from aidar.cli.main import aidar
from aidar.cli.track import run_track_domain
from aidar.core.hn import get_hn_trending_domains
from aidar.output.renderer import console


def _load_domains(domains: tuple[str, ...], domains_file: str | None) -> list[str]:
    loaded = list(domains)
    if domains_file:
        lines = Path(domains_file).read_text(encoding="utf-8").splitlines()
        loaded.extend(line.strip() for line in lines if line.strip() and not line.strip().startswith("#"))

    # Deduplicate while preserving order.
    deduped: list[str] = []
    seen: set[str] = set()
    for domain in loaded:
        if domain not in seen:
            seen.add(domain)
            deduped.append(domain)
    return deduped


def _dedupe_keep_order(domains: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for domain in domains:
        if domain not in seen:
            seen.add(domain)
            result.append(domain)
    return result


@aidar.command("worker")
@click.option(
    "--domain",
    "domains",
    multiple=True,
    help="Domain to track (repeatable).",
)
@click.option(
    "--domains-file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="File with one domain per line.",
)
@click.option(
    "--interval-minutes",
    default=60,
    show_default=True,
    help="Sleep duration between full scan cycles.",
)
@click.option(
    "--max-cycles",
    default=0,
    show_default=True,
    help="0 = run forever. Otherwise stop after this many cycles.",
)
@click.option(
    "--limit",
    default=200,
    show_default=True,
    help="Max pages to scan per domain per cycle.",
)
@click.option(
    "--concurrency",
    default=10,
    show_default=True,
    help="Concurrent HTTP requests per domain.",
)
@click.option(
    "--db",
    "db_path",
    default="aidar.db",
    show_default=True,
    help="SQLite database path.",
)
@click.option(
    "--source",
    type=click.Choice(["auto", "sitemap", "rss"]),
    default="auto",
    show_default=True,
)
@click.option(
    "--skip-existing/--no-skip-existing",
    default=True,
    show_default=True,
    help="Skip URLs already in DB unless stale.",
)
@click.option(
    "--rescan-stale/--no-rescan-stale",
    default=True,
    show_default=True,
    help="Re-scan URLs when pattern revision/fingerprint changed.",
)
@click.option(
    "--skip-pattern",
    "skip_patterns",
    multiple=True,
    default=(),
    help="Skip URLs containing this substring. Repeatable.",
)
@click.option(
    "--sleep-between-domains",
    default=3.0,
    show_default=True,
    help="Seconds to sleep between domain jobs.",
)
@click.option(
    "--hn-domains",
    default=0,
    show_default=True,
    help="Add top N trending domains from Hacker News each cycle (0 disables).",
)
@click.option(
    "--hn-story-limit",
    default=200,
    show_default=True,
    help="How many HN top stories to sample when discovering trending domains.",
)
@click.option(
    "--hn-min-story-count",
    default=2,
    show_default=True,
    help="Minimum HN story count per domain before it is included.",
)
@click.pass_context
def worker(
    ctx: click.Context,
    domains: tuple[str, ...],
    domains_file: str | None,
    interval_minutes: int,
    max_cycles: int,
    limit: int,
    concurrency: int,
    db_path: str,
    source: str,
    skip_existing: bool,
    rescan_stale: bool,
    skip_patterns: tuple[str, ...],
    sleep_between_domains: float,
    hn_domains: int,
    hn_story_limit: int,
    hn_min_story_count: int,
) -> None:
    """
    Continuous scanner: discovers + scans domains in a loop.

    Designed for unattended overnight runs. Automatically rescans stale URLs
    when pattern definitions change.
    """
    domain_list = _load_domains(domains, domains_file)
    if not domain_list and hn_domains <= 0:
        raise click.BadParameter(
            "Provide --domain/--domains-file, or set --hn-domains > 0 for HN-only mode."
        )

    analyzer = ctx.obj["analyzer"]
    config = ctx.obj["config"]
    registry = ctx.obj["registry"]

    cycle = 0
    console.print(
        f"[bold]Worker started[/bold] domains={len(domain_list)} "
        f"hn_domains={hn_domains} interval={interval_minutes}m max_cycles={max_cycles or '∞'}"
    )

    try:
        while max_cycles == 0 or cycle < max_cycles:
            cycle += 1
            started = datetime.now(timezone.utc).isoformat()
            console.print(f"\n[bold cyan]Cycle {cycle}[/bold cyan] started={started}")

            cycle_domains = list(domain_list)
            if hn_domains > 0:
                trending = get_hn_trending_domains(
                    story_limit=hn_story_limit,
                    top_domains=hn_domains,
                    min_story_count=hn_min_story_count,
                )
                if trending:
                    hn_list = [domain for domain, _count in trending]
                    cycle_domains = _dedupe_keep_order(cycle_domains + hn_list)
                    preview = ", ".join(f"{d}({c})" for d, c in trending[:8])
                    console.print(
                        f"[dim]HN trending domains added: {len(hn_list)}[/dim] {preview}"
                    )
                else:
                    console.print("[yellow]HN trending lookup returned no domains this cycle.[/yellow]")

            total_saved = 0
            for domain in cycle_domains:
                summary = run_track_domain(
                    analyzer=analyzer,
                    config=config,
                    registry=registry,
                    domain=domain,
                    limit=limit,
                    concurrency=concurrency,
                    db_path=db_path,
                    skip_existing=skip_existing,
                    source=source,
                    rescan_stale=rescan_stale,
                    skip_patterns=skip_patterns,
                )
                total_saved += summary.get("saved", 0)
                if sleep_between_domains > 0:
                    time.sleep(sleep_between_domains)

            finished = datetime.now(timezone.utc).isoformat()
            console.print(
                f"[green]Cycle {cycle} complete[/green] saved={total_saved} finished={finished}"
            )

            if max_cycles and cycle >= max_cycles:
                break

            sleep_s = max(interval_minutes, 1) * 60
            console.print(f"[dim]Sleeping {sleep_s}s before next cycle...[/dim]")
            time.sleep(sleep_s)
    except KeyboardInterrupt:
        console.print("\n[yellow]Worker stopped by user.[/yellow]")
