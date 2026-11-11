from __future__ import annotations

import os
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.table import Table
from rich.text import Text

from aidar.cli.main import aidar
from aidar.models.config import WeightConfig

console = Console()

_BEGIN = "<!-- BEGIN GENERATED: pattern catalog — regenerate with: aidar patterns catalog --write -->"
_END = "<!-- END GENERATED: pattern catalog -->"


@aidar.group()
def patterns() -> None:
    """Manage and inspect loaded patterns."""
    pass


@patterns.command("list")
@click.option("--category", default=None, help="Filter by category")
@click.pass_context
def list_patterns(ctx: click.Context, category: str | None) -> None:
    """List all loaded patterns."""
    registry = ctx.obj["registry"]
    by_cat = registry.patterns_by_category()

    table = Table(show_header=True, header_style="bold dim", padding=(0, 1))
    table.add_column("ID", style="cyan", width=28)
    table.add_column("Category", width=14)
    table.add_column("Type", width=12)
    table.add_column("Weight", justify="right", width=7)
    table.add_column("Name")

    categories = [category] if category else sorted(by_cat.keys())
    for cat in categories:
        for p in by_cat.get(cat, []):
            table.add_row(p.id, p.category, p.detection_type, f"{p.weight:.2f}", p.name)

    console.print(table)
    total = sum(len(v) for v in by_cat.values())
    console.print(f"\n[dim]{total} patterns loaded[/dim]")


@patterns.command("versions")
@click.option("--db", "db_path", default="aidar.db", show_default=True)
@click.pass_context
def versions_command(ctx: click.Context, db_path: str) -> None:
    """Show pattern versions stored in DB vs currently loaded — find what needs re-scanning."""
    import os
    from aidar.db.database import get_connection
    from aidar.db.queries import get_pattern_version_summary

    registry = ctx.obj["registry"]
    loaded = {p.id: p.version for p in registry.all_patterns()}

    if not os.path.exists(db_path):
        console.print(f"[yellow]No database found at {db_path}. Run some scans first.[/yellow]")
        return

    conn = get_connection(db_path)
    stored = {row["pattern_id"]: row for row in get_pattern_version_summary(conn)}

    table = Table(show_header=True, header_style="bold dim", padding=(0, 1))
    table.add_column("Pattern ID", style="cyan", width=28)
    table.add_column("Loaded v", justify="right", width=9)
    table.add_column("Stored v", justify="right", width=9)
    table.add_column("Scans", justify="right", width=7)
    table.add_column("Status", width=10)

    any_stale = False
    for pattern_id, loaded_version in sorted(loaded.items()):
        row = stored.get(pattern_id)
        if row is None:
            status = Text("new", style="yellow")
            stored_v = "—"
            scans = "0"
        elif row["max_stored_version"] < loaded_version:
            status = Text("STALE", style="bold red")
            stored_v = str(row["max_stored_version"])
            scans = str(row["scan_count"])
            any_stale = True
        else:
            status = Text("ok", style="green")
            stored_v = str(row["max_stored_version"])
            scans = str(row["scan_count"])
        table.add_row(pattern_id, str(loaded_version), stored_v, scans, status)

    console.print(table)
    if any_stale:
        console.print(
            "\n[yellow]Some patterns are stale.[/yellow] "
            "[dim]track/worker rescan stale URLs automatically by default.[/dim]"
        )


@patterns.command("show")
@click.argument("pattern_id")
@click.pass_context
def show_pattern(ctx: click.Context, pattern_id: str) -> None:
    """Show full configuration for a specific pattern."""
    registry = ctx.obj["registry"]
    pattern = registry.get_pattern(pattern_id)

    if not pattern:
        console.print(f"[red]Pattern not found: {pattern_id}[/red]")
        available = [p.id for p in registry.all_patterns()]
        console.print(f"[dim]Available: {', '.join(sorted(available))}[/dim]")
        raise SystemExit(1)

    console.print(f"\n[bold cyan]{pattern.id}[/bold cyan]")
    console.print(f"[bold]Name:[/bold]     {pattern.name}")
    console.print(f"[bold]Category:[/bold] {pattern.category}")
    console.print(f"[bold]Type:[/bold]     {pattern.detection_type}")
    console.print(f"[bold]Weight:[/bold]   {pattern.weight}")
    console.print(f"[bold]Severity:[/bold] {pattern.severity}")
    console.print()
    console.print(f"[bold]Description:[/bold]\n{pattern.description.strip()}")

    if pattern.params:
        console.print(f"\n[bold]Params:[/bold]")
        for k, v in pattern.params.items():
            if isinstance(v, list) and len(v) > 5:
                console.print(f"  {k}: [{len(v)} items]")
            else:
                console.print(f"  {k}: {v}")

    if pattern.references:
        console.print(f"\n[bold]References:[/bold]")
        for ref in pattern.references:
            console.print(f"  {ref}")


# --------------------------------------------------------------------------
# Generated pattern catalog (docs/PATTERN_CATALOG.md)
#


def _fmt_num(value: object) -> str:
    """Compact deterministic number rendering ('%g'); em dash for missing."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "—"
    return f"{value:g}"


def _pattern_files(patterns_dir: Path) -> dict[str, Path]:
    """pattern id -> YAML path (mirrors load_patterns' discovery rules)."""
    files: dict[str, Path] = {}
    models_dir = patterns_dir / "models"
    for yaml_file in sorted(patterns_dir.rglob("*.yaml")):
        if yaml_file.name.startswith("_") or yaml_file.is_relative_to(models_dir):
            continue
        try:
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if isinstance(data, dict) and "id" in data:
            files[str(data["id"])] = yaml_file
    return files


def _source_map(patterns_dir: Path) -> dict[str, list[str]]:
    """pattern id -> sorted source ids from sources.yaml derived_patterns."""
    manifest = patterns_dir.parent / "sources.yaml"
    if not manifest.exists():
        return {}
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}
    mapping: dict[str, list[str]] = {}
    for src in data.get("sources") or []:
        for pid in src.get("derived_patterns") or []:
            mapping.setdefault(str(pid), []).append(str(src["id"]))
    return {pid: sorted(ids) for pid, ids in mapping.items()}


def _render_catalog_block(
    patterns: list,
    weights: WeightConfig,
    likely_human: int,
    likely_ai: int,
    patterns_dir: Path,
    doc_dir: Path,
) -> str:
    """Render the generated markdown section, including the marker comments."""
    lines: list[str] = [_BEGIN, ""]

    lines += [
        "## Category Weights",
        "",
        "| Category | Weight |",
        "|---|---:|",
    ]
    for cat, w in sorted(weights.as_dict().items()):
        lines.append(f"| {cat} | {w:g} |")
    lines += ["", "Source: [`patterns/_weights.yaml`](../patterns/_weights.yaml)", ""]

    lines += [
        "## Aggregate Labels",
        "",
        "| Label | Aggregate score |",
        "|---|---|",
        f"| LIKELY HUMAN | 0 – {likely_human} |",
        f"| UNCERTAIN | {likely_human + 1} – {likely_ai - 1} |",
        f"| LIKELY AI | {likely_ai} – 100 |",
        "",
    ]

    lines += [
        "## Pattern Inventory",
        "",
        (
            "| Category | Pattern ID | Type | Match Mode | Weight | Version | Severity "
            "| `threshold_low` | `threshold_high` | Sources | References | File |"
        ),
        "|---|---|---|---|---:|---:|---|---:|---:|---|---|---|",
    ]
    file_by_id = _pattern_files(patterns_dir)
    sources_by_id = _source_map(patterns_dir)
    for p in sorted(patterns, key=lambda p: (p.category, p.id)):
        match_mode = (
            str(p.params.get("match_mode", "contains")) if p.detection_type == "frequency" else "—"
        )
        sources = ", ".join(sources_by_id.get(p.id, [])) or "—"
        refs = ", ".join(f"<{ref}>" for ref in p.references) or "—"
        if p.id in file_by_id:
            rel = file_by_id[p.id].relative_to(patterns_dir)
            target = Path(os.path.relpath(file_by_id[p.id], doc_dir)).as_posix()
            file_cell = f"[`patterns/{rel.as_posix()}`]({target})"
        else:
            file_cell = "—"
        lines.append(
            f"| {p.category} | `{p.id}` | {p.detection_type} | {match_mode} | {p.weight:g} "
            f"| {p.version} | {p.severity} | {_fmt_num(p.params.get('threshold_low'))} "
            f"| {_fmt_num(p.params.get('threshold_high'))} | {sources} | {refs} | {file_cell} |"
        )
    lines += [
        "",
        (
            "Thresholds are per-1000-words rates for `frequency`/`regex` patterns and raw metric "
            "values for `structural`/`linguistic` patterns. `match_mode` applies to `frequency` "
            "patterns only (`contains` unless the YAML says otherwise)."
        ),
        "",
        _END,
    ]
    return "\n".join(lines)


_LEGACY_SECTIONS = ("## Category Weights", "## Pattern Inventory", "## Aggregate Labels")


def _splice_catalog(doc: str, block: str) -> str:
    """Replace only the generated region, preserving hand-written parts.

    With markers present: swap the text between them. Without markers
    (legacy hand-maintained doc): insert the marked block where the legacy
    generated sections started and keep everything from '## Tuning Log' on.
    """
    if _BEGIN in doc and _END in doc:
        pre = doc[: doc.index(_BEGIN)]
        post = doc[doc.index(_END) + len(_END):]
        return pre + block + post

    tail_at = doc.find("## Tuning Log")
    if tail_at == -1:
        tail_at = len(doc)
    tail = doc[tail_at:]
    head = doc[:tail_at]
    cut = len(head)
    for marker in _LEGACY_SECTIONS:
        idx = head.find(marker)
        if idx != -1:
            cut = min(cut, idx)
    return head[:cut] + block + ("\n\n" + tail if tail else "")


def _load_weights_file(patterns_dir: Path) -> dict:
    weights_file = patterns_dir / "_weights.yaml"
    if not weights_file.exists():
        return {}
    try:
        return yaml.safe_load(weights_file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}


@patterns.command("catalog")
@click.option("--write", is_flag=True, help="Update the doc in place.")
@click.option(
    "--check",
    "check_mode",
    is_flag=True,
    help="Exit 1 if the doc differs from what would be generated (for CI).",
)
@click.option(
    "--file",
    "doc_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Target doc (default: docs/PATTERN_CATALOG.md next to the patterns dir).",
)
@click.pass_context
def catalog(
    ctx: click.Context, write: bool, check_mode: bool, doc_path: Path | None
) -> None:
    """Render the generated parts of docs/PATTERN_CATALOG.md from the YAMLs.

    Without flags the generated block is printed to stdout. Hand-written
    sections (intro, Tuning Workflow, Tuning Log) are never touched: the
    generated block lives between BEGIN/END marker comments and only that
    region is replaced. Output is deterministic (sorted by category, then id).
    """
    if write and check_mode:
        raise click.UsageError("Use --write or --check, not both.")

    registry = ctx.obj["registry"]
    config = ctx.obj["config"]
    patterns_dir: Path = ctx.obj["patterns_dir"]

    doc_path = doc_path or (patterns_dir.parent / "docs" / "PATTERN_CATALOG.md")
    block = _render_catalog_block(
        patterns=registry.all_patterns(),
        weights=config.weights,
        likely_human=config.likely_human_threshold,
        likely_ai=config.likely_ai_threshold,
        patterns_dir=patterns_dir,
        doc_dir=doc_path.parent,
    )

    if check_mode:
        if not doc_path.exists():
            console.print(f"[red]Catalog doc not found: {doc_path}[/red]")
            raise SystemExit(1)
        current = doc_path.read_text(encoding="utf-8")
        if current == _splice_catalog(current, block):
            console.print(f"[green]Catalog is up to date:[/green] {doc_path}")
            return
        console.print(
            f"[red]Catalog is stale:[/red] {doc_path} does not match the YAMLs. "
            "Run 'aidar patterns catalog --write' and commit the result."
        )
        raise SystemExit(1)

    if write:
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        if doc_path.exists():
            current = doc_path.read_text(encoding="utf-8")
            updated = _splice_catalog(current, block)
        else:
            updated = block
        doc_path.write_text(updated, encoding="utf-8")
        console.print(f"[green]Wrote[/green] {doc_path}")
        return

    click.echo(block)
