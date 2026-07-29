from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click
from rich.console import Console

from aidar.cli.main import aidar
from aidar.core.analyzer import Analyzer
from aidar.core.ingestion import ScanOutcome, ScanSummary, filter_prose_urls, scan_urls
from aidar.models.config import AppConfig
from aidar.output.renderer import render_comparison_table

console = Console()


@aidar.command()
@click.option(
    "--batch",
    "batch_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Text file with one URL per line",
)
@click.option(
    "--concurrency",
    default=10,
    show_default=True,
    help="Number of concurrent HTTP requests",
)
@click.option(
    "--save",
    is_flag=True,
    default=False,
    help="Persist results to SQLite database (aidar.db)",
)
@click.option(
    "--db",
    "db_path",
    default="aidar.db",
    show_default=True,
    help="Path to SQLite database file (used with --save)",
)
@click.option(
    "--skip-existing",
    is_flag=True,
    default=True,
    show_default=True,
    help="Skip URLs already in the database",
)
@click.option(
    "--delay",
    default=0.0,
    show_default=True,
    help="Delay in seconds between requests per domain (rate limiting)",
)
@click.option(
    "--min-words",
    default=50,
    show_default=True,
    help="Skip pages with fewer than this many extracted words (nav pages, stubs, etc.)",
)
@click.pass_context
def scan(
    ctx: click.Context,
    batch_file: str,
    concurrency: int,
    save: bool,
    db_path: str,
    skip_existing: bool,
    delay: float,
    min_words: int,
) -> None:
    """Async bulk scan of URLs from a batch file."""
    loaded_urls = _load_urls(batch_file)
    filtered = filter_prose_urls(loaded_urls)
    urls = filtered.kept
    summary = ScanSummary(discovered=len(loaded_urls))
    summary.record_rejections(filtered.rejected)
    if not urls:
        console.print("[yellow]No scannable URLs found in batch file.[/yellow]")
        _render_scan_summary(summary)
        return

    analyzer = ctx.obj["analyzer"]
    config = ctx.obj["config"]
    output_format = ctx.obj["output"]

    # Set up DB if saving
    conn = None
    if save:
        from aidar.db.database import get_connection
        from aidar.db.queries import url_already_scanned

        conn = get_connection(db_path)
        if skip_existing:
            before = len(urls)
            urls = [u for u in urls if not url_already_scanned(conn, u)]
            skipped = before - len(urls)
            if skipped:
                console.print(f"[dim]Skipping {skipped} already-scanned URLs.[/dim]")
                summary.filtered += skipped
                summary.reasons["already_scanned"] += skipped

    if not urls:
        console.print("[green]All URLs already scanned.[/green]")
        _render_scan_summary(summary)
        return

    console.print(
        f"[bold]Scanning {len(urls)} URLs (concurrency={concurrency}, min-words={min_words})...[/bold]"
    )
    outcomes = asyncio.run(_bulk_scan(urls, analyzer, config, concurrency, delay, min_words))
    summary.record_outcomes(outcomes)
    results = [outcome.result for outcome in outcomes if outcome.result is not None]

    if save and conn:
        from aidar.db.queries import store_result

        for result in results:
            store_result(conn, result)
        console.print(f"[green]Saved {len(results)} results to {db_path}[/green]")

    if output_format == "json":
        click.echo(
            json.dumps(
                {
                    "summary": summary.as_dict(),
                    "results": [result.as_dict() for result in results],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        from aidar.core.comparator import rank_results

        render_comparison_table(rank_results(results))
        _render_scan_summary(summary)


def _load_urls(path: str) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


async def _bulk_scan(
    urls: list[str],
    analyzer: Analyzer,
    config: AppConfig,
    concurrency: int,
    delay: float,
    min_words: int = 50,
) -> list[ScanOutcome]:
    return await scan_urls(
        urls,
        analyzer,
        config,
        concurrency=concurrency,
        delay=delay,
        min_words=min_words,
    )


def _render_scan_summary(summary: ScanSummary) -> None:
    data = summary.as_dict()
    console.print(
        "\n[bold]Run summary:[/bold] "
        f"discovered={data['discovered']} filtered={data['filtered']} "
        f"attempted={data['attempted']} saved={data['saved']} failed={data['failed']}"
    )
    if data["reasons"]:
        reasons = ", ".join(f"{key}={value}" for key, value in data["reasons"].items())
        console.print(f"[dim]Reasons: {reasons}[/dim]")
