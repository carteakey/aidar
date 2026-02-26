from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import click
import httpx

from aidar.cli.discover import _from_rss, _from_sitemap, _normalize_domain
from aidar.cli.main import aidar
from aidar.cli.scan import _scan_one
from aidar.core.comparator import rank_results
from aidar.output.renderer import console


@aidar.command()
@click.argument("domain")
@click.option(
    "--limit",
    default=50,
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
    "--rescan-stale",
    is_flag=True,
    default=False,
    help="Re-scan URLs where any pattern version has been bumped since last scan",
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
    base_url = _normalize_domain(domain)
    domain_name = urlparse(base_url).netloc

    console.print(f"\n[bold]Tracking:[/bold] {domain_name}")
    console.print(f"[dim]Discovering URLs...[/dim]")

    # Discover URLs
    urls: list[str] = []
    if source in ("auto", "sitemap"):
        urls = _from_sitemap(base_url)
    if not urls and source in ("auto", "rss"):
        urls = _from_rss(base_url)

    if not urls:
        console.print(f"[red]Could not discover any URLs for {domain_name}.[/red]")
        console.print("[dim]Try: aidar discover <domain> to debug discovery manually.[/dim]")
        raise SystemExit(1)

    console.print(f"[dim]Discovered {len(urls)} URLs.[/dim]")

    # Filter out non-article URLs (tag pages, pagination, author pages, etc.)
    if skip_patterns:
        before = len(urls)
        urls = [u for u in urls if not any(p in u for p in skip_patterns)]
        filtered = before - len(urls)
        if filtered:
            console.print(f"[dim]Filtered {filtered} URLs matching skip patterns.[/dim]")

    # Set up DB
    from aidar.db.database import get_connection
    from aidar.db.queries import store_result, url_already_scanned, get_domain_stats

    conn = get_connection(db_path)

    if rescan_stale:
        from aidar.db.queries import get_stale_urls
        registry = ctx.obj["registry"]
        current_versions = {p.id: p.version for p in registry.all_patterns()}
        stale = set(get_stale_urls(conn, current_versions, domain=domain_name))
        if stale:
            console.print(f"[yellow]{len(stale)} URLs stale (pattern versions updated) — forcing rescan.[/yellow]")
            urls = list(stale | set(u for u in urls if not url_already_scanned(conn, u)))
        else:
            console.print("[dim]No stale URLs found.[/dim]")
            if skip_existing:
                urls = [u for u in urls if not url_already_scanned(conn, u)]
    elif skip_existing:
        before = len(urls)
        urls = [u for u in urls if not url_already_scanned(conn, u)]
        skipped = before - len(urls)
        if skipped:
            console.print(f"[dim]Skipping {skipped} already-scanned URLs.[/dim]")

    if not urls:
        console.print(f"[green]All URLs already up to date.[/green]")
        _print_domain_summary(conn, domain_name)
        return

    urls = urls[:limit]
    console.print(f"[bold]Scanning {len(urls)} URLs (concurrency={concurrency})...[/bold]\n")

    analyzer = ctx.obj["analyzer"]
    config = ctx.obj["config"]

    # Async bulk scan (reuse scan's logic)
    from rich.progress import Progress, SpinnerColumn, BarColumn, TaskProgressColumn, TextColumn

    async def run():
        semaphore = asyncio.Semaphore(concurrency)
        results = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"Scanning {domain_name}...", total=len(urls))
            async with httpx.AsyncClient(timeout=30) as client:
                tasks = [
                    _scan_one(url, analyzer, config, client, semaphore, 0.0, progress, task)
                    for url in urls
                ]
                raw = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in raw if r is not None and not isinstance(r, Exception)]

    results = asyncio.run(run())

    # Save
    for result in results:
        store_result(conn, result)

    console.print(f"\n[green]Saved {len(results)} results to {db_path}[/green]")
    _print_domain_summary(conn, domain_name)


def _print_domain_summary(conn, domain: str) -> None:
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
