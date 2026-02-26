from __future__ import annotations

import asyncio
import time
from pathlib import Path

import click
import httpx
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from aidar.cli.main import aidar
from aidar.core.fetcher import FetchError, fetch_url_async, count_words
from aidar.core.scorer import compute_aggregate
from aidar.output.formatters import to_json_list
from aidar.output.renderer import render_comparison_table

import trafilatura

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
@click.pass_context
def scan(
    ctx: click.Context,
    batch_file: str,
    concurrency: int,
    save: bool,
    db_path: str,
    skip_existing: bool,
    delay: float,
) -> None:
    """Async bulk scan of URLs from a batch file."""
    urls = _load_urls(batch_file)
    if not urls:
        console.print("[yellow]No URLs found in batch file.[/yellow]")
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

    if not urls:
        console.print("[green]All URLs already scanned.[/green]")
        return

    console.print(f"[bold]Scanning {len(urls)} URLs (concurrency={concurrency})...[/bold]")
    results = asyncio.run(
        _bulk_scan(urls, analyzer, config, concurrency, delay)
    )

    if save and conn:
        from aidar.db.queries import store_result
        for result in results:
            store_result(conn, result)
        console.print(f"[green]Saved {len(results)} results to {db_path}[/green]")

    if output_format == "json":
        import click as _click
        _click.echo(to_json_list(results))
    else:
        from aidar.core.comparator import rank_results
        render_comparison_table(rank_results(results))
        console.print(f"\n[bold]Total scanned:[/bold] {len(results)}")


def _load_urls(path: str) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


async def _bulk_scan(urls, analyzer, config, concurrency, delay):
    semaphore = asyncio.Semaphore(concurrency)
    results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning...", total=len(urls))

        async with httpx.AsyncClient(timeout=30) as client:
            tasks = [
                _scan_one(url, analyzer, config, client, semaphore, delay, progress, task)
                for url in urls
            ]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in raw_results:
        if isinstance(r, Exception):
            continue
        if r is not None:
            results.append(r)

    return results


async def _scan_one(url, analyzer, config, client, semaphore, delay, progress, task_id):
    async with semaphore:
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            text, word_count = await fetch_url_async(url, client)
            score_vector = analyzer.run(text, word_count)
            result = compute_aggregate(score_vector, config, url=url, word_count=word_count)
            return result
        except FetchError:
            return None
        except Exception:
            return None
        finally:
            progress.advance(task_id)
