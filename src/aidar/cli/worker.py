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


def _load_exclude_set(exclude_file: str | None) -> set[str]:
    """Load domain exclusion list from file. Returns normalized set of hostnames."""
    if not exclude_file:
        return set()
    lines = Path(exclude_file).read_text(encoding="utf-8").splitlines()
    excluded = set()
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            # Strip www. prefix for consistency
            if line.startswith("www."):
                line = line[4:]
            excluded.add(line.lower())
    return excluded


def _append_failed_log(path: str, domains: list[str], cycle: int) -> None:
    """Append no-discovery domains to a log file for review."""
    if not domains:
        return
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n# Cycle {cycle} — {ts} — {len(domains)} domains with no discovery\n")
        for d in sorted(domains):
            f.write(f"{d}\n")


def _print_cycle_summary(
    cycle: int,
    outcomes: dict[str, list[str]],
    total_saved: int,
    excluded_count: int,
    started: str,
) -> None:
    """Print a structured per-cycle outcome table."""
    finished = datetime.now(timezone.utc).isoformat()
    scanned = outcomes.get("scanned", [])
    no_discovery = outcomes.get("no_discovery", [])
    all_existing = outcomes.get("all_existing", [])

    console.print(f"\n[bold green]Cycle {cycle} complete[/bold green] saved={total_saved} finished={finished}")
    console.print(f"  [green]✓ scanned ({len(scanned)}):[/green]      {', '.join(scanned[:10]) or '—'}")
    if len(scanned) > 10:
        console.print(f"                       ...and {len(scanned) - 10} more")
    console.print(f"  [dim]○ up to date ({len(all_existing)}):[/dim]  {', '.join(all_existing[:8]) or '—'}")
    if no_discovery:
        console.print(
            f"  [yellow]⚠ no discovery ({len(no_discovery)}):[/yellow] "
            f"{', '.join(no_discovery[:8])}"
            + (f" ...+{len(no_discovery) - 8}" if len(no_discovery) > 8 else "")
        )
    if excluded_count:
        console.print(f"  [dim]✗ excluded: {excluded_count}[/dim]")


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
    "--exclude-domains-file",
    type=click.Path(dir_okay=False),
    default=None,
    help="File with domains to exclude from HN-discovered lists (one per line, # for comments).",
)
@click.option(
    "--failed-log",
    type=click.Path(dir_okay=False),
    default=None,
    help="Append domains that fail discovery each cycle to this file for review.",
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
    help="Minimum HN story count per domain before it is included (top/best stories).",
)
@click.option(
    "--hn-new-domains",
    default=0,
    show_default=True,
    help="Also add top N domains from HN /new stories each cycle (0 disables). min_story_count is forced to 1 for new stories.",
)
@click.option(
    "--hn-new-story-limit",
    default=100,
    show_default=True,
    help="How many HN new stories to sample when discovering fresh domains.",
)
@click.pass_context
def worker(
    ctx: click.Context,
    domains: tuple[str, ...],
    domains_file: str | None,
    exclude_domains_file: str | None,
    failed_log: str | None,
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
    hn_new_domains: int,
    hn_new_story_limit: int,
) -> None:
    """
    Continuous scanner: discovers + scans domains in a loop.

    Designed for unattended overnight runs. Automatically rescans stale URLs
    when pattern definitions change.

    Domain sources (merged each cycle, deduplicated):
      --domains-file  : permanent curated list — always scanned, never excluded
      --hn-domains    : HN top stories trending domains (excluded by --exclude-domains-file)
      --hn-new-domains: HN new stories fresh domains (also excluded by --exclude-domains-file)

    Use --failed-log to capture domains that consistently fail discovery so you
    can review and add them to --exclude-domains-file.
    """
    domain_list = _load_domains(domains, domains_file)
    if not domain_list and hn_domains <= 0:
        raise click.BadParameter(
            "Provide --domain/--domains-file, or set --hn-domains > 0 for HN-only mode."
        )

    exclude_set = _load_exclude_set(exclude_domains_file)
    if exclude_set:
        console.print(f"[dim]Loaded {len(exclude_set)} excluded domains from {exclude_domains_file}[/dim]")

    analyzer = ctx.obj["analyzer"]
    config = ctx.obj["config"]
    registry = ctx.obj["registry"]

    cycle = 0
    console.print(
        f"[bold]Worker started[/bold] domains={len(domain_list)} "
        f"hn_domains={hn_domains} hn_new_domains={hn_new_domains} "
        f"interval={interval_minutes}m max_cycles={max_cycles or '∞'}"
    )

    try:
        while max_cycles == 0 or cycle < max_cycles:
            cycle += 1
            started = datetime.now(timezone.utc).isoformat()
            console.print(f"\n[bold cyan]Cycle {cycle}[/bold cyan] started={started}")

            # domain_list entries are always included (manual curation, no exclusion).
            cycle_domains = list(domain_list)
            hn_excluded_this_cycle = 0

            if hn_domains > 0:
                trending = get_hn_trending_domains(
                    story_limit=hn_story_limit,
                    top_domains=hn_domains,
                    min_story_count=hn_min_story_count,
                )
                if trending:
                    hn_list = [d for d, _ in trending if d not in exclude_set]
                    hn_excluded_this_cycle += len(trending) - len(hn_list)
                    cycle_domains = _dedupe_keep_order(cycle_domains + hn_list)
                    preview = ", ".join(f"{d}({c})" for d, c in trending[:8])
                    console.print(
                        f"[dim]HN trending: {len(hn_list)} added"
                        + (f" ({hn_excluded_this_cycle} excluded)" if hn_excluded_this_cycle else "")
                        + f"[/dim] {preview}"
                    )
                else:
                    console.print("[yellow]HN trending lookup returned no domains this cycle.[/yellow]")

            if hn_new_domains > 0:
                new_trending = get_hn_trending_domains(
                    story_limit=hn_new_story_limit,
                    top_domains=hn_new_domains,
                    min_story_count=1,
                    story_type="new",
                )
                if new_trending:
                    before = len(cycle_domains)
                    new_list = [d for d, _ in new_trending if d not in exclude_set]
                    excl = len(new_trending) - len(new_list)
                    hn_excluded_this_cycle += excl
                    cycle_domains = _dedupe_keep_order(cycle_domains + new_list)
                    added = len(cycle_domains) - before
                    preview = ", ".join(d for d, _ in new_trending[:8])
                    console.print(
                        f"[dim]HN new: {added} added"
                        + (f" ({excl} excluded)" if excl else "")
                        + f"[/dim] {preview}"
                    )
                else:
                    console.print("[yellow]HN new stories lookup returned no domains this cycle.[/yellow]")

            console.print(f"[dim]Cycle {cycle}: scanning {len(cycle_domains)} domains...[/dim]")

            total_saved = 0
            outcomes: dict[str, list[str]] = {"scanned": [], "no_discovery": [], "all_existing": []}

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
                status = summary.get("status", "scanned")
                saved = summary.get("saved", 0)
                total_saved += saved

                if status == "scanned":
                    outcomes["scanned"].append(f"{domain}({saved})")
                elif status == "no_discovery":
                    outcomes["no_discovery"].append(domain)
                else:
                    outcomes["all_existing"].append(domain)

                if sleep_between_domains > 0:
                    time.sleep(sleep_between_domains)

            _print_cycle_summary(cycle, outcomes, total_saved, hn_excluded_this_cycle, started)

            if failed_log and outcomes["no_discovery"]:
                _append_failed_log(failed_log, outcomes["no_discovery"], cycle)
                console.print(
                    f"[dim]⚠ {len(outcomes['no_discovery'])} no-discovery domains appended to {failed_log}[/dim]"
                )

            if max_cycles and cycle >= max_cycles:
                break

            sleep_s = max(interval_minutes, 1) * 60
            console.print(f"[dim]Sleeping {sleep_s}s before next cycle...[/dim]")
            time.sleep(sleep_s)
    except KeyboardInterrupt:
        console.print("\n[yellow]Worker stopped by user.[/yellow]")
