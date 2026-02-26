from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from aidar.models.result import AggregateResult

console = Console()

_CATEGORY_ORDER = ["phrases", "punctuation", "structure", "vocabulary", "emoji"]

_LABEL_COLORS = {
    "LIKELY AI": "bold red",
    "UNCERTAIN": "bold yellow",
    "LIKELY HUMAN": "bold green",
}


def _bar(score: float, width: int = 10) -> str:
    filled = round(score * width)
    return "█" * filled + "░" * (width - filled)


def render_result(result: AggregateResult, show_patterns: bool = False) -> None:
    """Print the full scored breakdown to terminal using Rich."""
    source = result.url or result.file_path or "unknown"
    label_style = _LABEL_COLORS.get(result.label, "white")

    console.print()
    console.print(f"[bold]Source:[/bold] {source}")
    console.print(f"[bold]Words:[/bold]  {result.word_count:,}")
    console.print()

    # Category scores table
    table = Table(show_header=True, header_style="bold dim", box=None, padding=(0, 1))
    table.add_column("Category", style="dim", width=14)
    table.add_column("Score Bar", width=12)
    table.add_column("Score", justify="right", width=6)

    vec = result.score_vector
    cat_scores = {
        "phrases": vec.phrases,
        "punctuation": vec.punctuation,
        "structure": vec.structure,
        "vocabulary": vec.vocabulary,
        "emoji": vec.emoji,
    }

    for cat in _CATEGORY_ORDER:
        score = cat_scores[cat]
        color = "red" if score >= 0.65 else "yellow" if score >= 0.35 else "green"
        bar_text = Text(_bar(score), style=color)
        table.add_row(cat, bar_text, f"{score:.2f}")

    console.print(table)
    console.print()

    # Aggregate score
    agg_text = Text(f"  Aggregate Score: {result.aggregate_score}/100  [{result.label}]  ")
    agg_text.stylize(label_style)
    console.print(Panel(agg_text, expand=False))

    # Model match if present
    if result.model_match:
        sim = result.model_match.get("similarity", 0)
        console.print(f"\n[dim]Model similarity: {sim:.1%}[/dim]")

    # Verbose pattern breakdown
    if show_patterns and result.score_vector.pattern_results:
        console.print()
        console.print("[bold dim]Pattern Breakdown:[/bold dim]")
        ptable = Table(show_header=True, header_style="bold dim", box=None, padding=(0, 1))
        ptable.add_column("Pattern", width=28)
        ptable.add_column("Category", width=14)
        ptable.add_column("Score", justify="right", width=6)
        ptable.add_column("Raw", width=28)

        sorted_results = sorted(
            result.score_vector.pattern_results,
            key=lambda r: r.normalized_score,
            reverse=True,
        )
        for r in sorted_results:
            color = "red" if r.normalized_score >= 0.65 else "yellow" if r.normalized_score >= 0.35 else "dim"
            ptable.add_row(
                r.pattern_id,
                r.category,
                Text(f"{r.normalized_score:.2f}", style=color),
                Text(r.label, style="dim"),
            )
        console.print(ptable)


def render_comparison_table(results: list[AggregateResult]) -> None:
    """Render a ranked comparison table for multiple URLs."""
    console.print()
    table = Table(show_header=True, header_style="bold dim", padding=(0, 1))
    table.add_column("#", width=3, justify="right")
    table.add_column("Score", width=7, justify="right")
    table.add_column("Label", width=14)
    table.add_column("Words", width=8, justify="right")
    table.add_column("Source")

    for i, result in enumerate(results, 1):
        label_style = _LABEL_COLORS.get(result.label, "white")
        source = result.url or result.file_path or "unknown"
        # Truncate long URLs
        if len(source) > 60:
            source = source[:57] + "..."
        table.add_row(
            str(i),
            Text(str(result.aggregate_score), style=label_style),
            Text(result.label, style=label_style),
            f"{result.word_count:,}",
            source,
        )

    console.print(table)


def render_error(message: str) -> None:
    console.print(f"[bold red]Error:[/bold red] {message}")
