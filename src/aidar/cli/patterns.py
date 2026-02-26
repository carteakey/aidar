from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from aidar.cli.main import aidar

console = Console()


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
            "\n[yellow]Some patterns are stale. Re-run with:[/yellow] "
            "[bold]aidar track <domain> --rescan-stale[/bold]"
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
