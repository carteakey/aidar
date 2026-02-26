from __future__ import annotations

from pathlib import Path

import click

from aidar.cli.main import aidar
from aidar.core.comparator import rank_results
from aidar.core.fetcher import FetchError, fetch_url, read_file
from aidar.core.scorer import compute_aggregate
from aidar.output.formatters import to_json_list
from aidar.output.renderer import console, render_comparison_table, render_result


@aidar.command()
@click.argument("targets", nargs=-1, required=True)
@click.option(
    "--sort",
    type=click.Choice(["score", "url"]),
    default="score",
    show_default=True,
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    default=False,
    help="Show per-URL category breakdowns",
)
@click.pass_context
def compare(
    ctx: click.Context,
    targets: tuple[str, ...],
    sort: str,
    verbose: bool,
) -> None:
    """Analyze multiple URLs/files and rank by AI score."""
    if len(targets) < 2:
        raise click.UsageError("Provide at least 2 targets to compare.")

    analyzer = ctx.obj["analyzer"]
    config = ctx.obj["config"]
    output_format = ctx.obj["output"]

    results = []
    for target in targets:
        try:
            if target.startswith(("http://", "https://")):
                fetch = fetch_url(target)
                url, file_path = target, None
            else:
                fetch = read_file(Path(target))
                url, file_path = None, target

            score_vector = analyzer.run(fetch.text, fetch.word_count)
            result = compute_aggregate(
                score_vector, config,
                url=url, file_path=file_path,
                word_count=fetch.word_count,
                published_date=fetch.published_date,
                title=fetch.title,
            )
            results.append(result)
        except FetchError as e:
            console.print(f"[yellow]Skipping {target}: {e}[/yellow]")

    if not results:
        console.print("[red]No results to compare.[/red]")
        raise SystemExit(1)

    if sort == "score":
        results = rank_results(results)
    else:
        results = sorted(results, key=lambda r: r.url or r.file_path or "")

    if output_format == "json":
        click.echo(to_json_list(results))
    else:
        render_comparison_table(results)
        if verbose:
            for result in results:
                render_result(result)
