from __future__ import annotations

from pathlib import Path

import click

from aidar.core.analyzer import Analyzer
from aidar.models.config import AppConfig, WeightConfig
from aidar.patterns.loader import load_patterns, load_weight_config
from aidar.patterns.registry import PatternRegistry

# Default patterns directory: repo root's patterns/ folder
_DEFAULT_PATTERNS_DIR = Path(__file__).parent.parent.parent.parent.parent / "patterns"


def _resolve_patterns_dir(override: str | None) -> Path:
    if override:
        p = Path(override)
        if not p.is_dir():
            raise click.BadParameter(f"Patterns directory does not exist: {p}")
        return p

    # Try the default location relative to the package
    if _DEFAULT_PATTERNS_DIR.is_dir():
        return _DEFAULT_PATTERNS_DIR

    raise click.UsageError(
        "Could not find the patterns/ directory. "
        "Use --patterns-dir to specify its location."
    )


@click.group()
@click.option(
    "--patterns-dir",
    default=None,
    envvar="AIDAR_PATTERNS_DIR",
    help="Path to patterns/ directory (default: auto-detected)",
)
@click.option(
    "--output",
    type=click.Choice(["terminal", "json"]),
    default="terminal",
    show_default=True,
    help="Output format",
)
@click.pass_context
def aidar(ctx: click.Context, patterns_dir: str | None, output: str) -> None:
    """aidar — detect AI-generated text via stylistic signal scoring."""
    ctx.ensure_object(dict)

    resolved = _resolve_patterns_dir(patterns_dir)
    patterns = load_patterns(resolved)
    weights = load_weight_config(resolved)

    registry = PatternRegistry(patterns)
    analyzer = Analyzer(registry)

    ctx.obj["analyzer"] = analyzer
    ctx.obj["registry"] = registry
    ctx.obj["patterns_dir"] = resolved
    ctx.obj["output"] = output
    ctx.obj["config"] = AppConfig(
        patterns_dir=str(resolved),
        weights=weights,
    )


# Import subcommands so click can register them
from aidar.cli import analyze, compare, patterns, scan  # noqa: E402, F401
