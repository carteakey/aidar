from __future__ import annotations

from pathlib import Path

import click

from aidar.cli.main import aidar
from aidar.core.fetcher import FetchError, fetch_url, read_file
from aidar.core.scorer import compare_model_profile, compute_aggregate
from aidar.output.formatters import to_json
from aidar.output.renderer import render_error, render_result
from aidar.patterns.loader import load_model_profile, PatternLoadError


@aidar.command()
@click.argument("target")
@click.option(
    "--compare-model",
    default=None,
    help="Compare against a model profile (e.g. claude, gpt4, gemini)",
)
@click.option(
    "--min-words",
    default=100,
    show_default=True,
    help="Minimum word count; warn if below this",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    default=False,
    help="Show per-pattern breakdown",
)
@click.pass_context
def analyze(
    ctx: click.Context,
    target: str,
    compare_model: str | None,
    min_words: int,
    verbose: bool,
) -> None:
    """Analyze a URL or local file for AI-generated stylistic signals."""
    analyzer = ctx.obj["analyzer"]
    config = ctx.obj["config"]
    output_format = ctx.obj["output"]
    patterns_dir = ctx.obj["patterns_dir"]

    # Fetch text
    try:
        if target.startswith(("http://", "https://")):
            text, word_count = fetch_url(target)
            url, file_path = target, None
        else:
            text, word_count = read_file(Path(target))
            url, file_path = None, target
    except FetchError as e:
        render_error(str(e))
        raise SystemExit(1)

    if word_count < min_words:
        click.echo(
            f"Warning: only {word_count} words extracted "
            f"(--min-words={min_words}). Results may be unreliable.",
            err=True,
        )

    # Run analysis
    score_vector = analyzer.run(text, word_count)
    result = compute_aggregate(score_vector, config, url=url, file_path=file_path, word_count=word_count)

    # Model comparison
    if compare_model:
        try:
            profile = load_model_profile(patterns_dir, compare_model)
            result.model_match = compare_model_profile(score_vector, profile)
        except PatternLoadError as e:
            click.echo(f"Warning: {e}", err=True)

    # Output
    if output_format == "json":
        click.echo(to_json(result))
    else:
        render_result(result, show_patterns=verbose)
