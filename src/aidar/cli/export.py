from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import click

from aidar.cli._dates import parse_iso_date
from aidar.cli.main import aidar
from aidar.db.queries import export_scans


def _write_output(content: str, output: Path | None) -> None:
    if output is None:
        click.echo(content, nl=False)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    click.echo(f"Exported data to {output}")


@aidar.command("export")
@click.option("--db", "db_path", default="aidar.db", show_default=True, help="SQLite database path.")
@click.option("--format", "output_format", type=click.Choice(["json", "csv"]), default="json", show_default=True)
@click.option("--output", "output_path", type=click.Path(path_type=Path, dir_okay=False), default=None)
@click.option("--domain", default=None, help="Limit export to one domain.")
@click.option(
    "--label",
    type=click.Choice(["LIKELY AI", "UNCERTAIN", "LIKELY HUMAN"]),
    default=None,
    help="Limit export to one persisted label.",
)
@click.option("--published-from", default=None, metavar="YYYY-MM-DD")
@click.option("--published-to", default=None, metavar="YYYY-MM-DD")
@click.pass_context
def export_command(
    ctx: click.Context,
    db_path: str,
    output_format: str,
    output_path: Path | None,
    domain: str | None,
    label: str | None,
    published_from: str | None,
    published_to: str | None,
) -> None:
    """Export persisted scans and pattern evidence as JSON or CSV."""
    from aidar.db.database import get_connection

    first = parse_iso_date(published_from, "--published-from") if published_from else None
    last = parse_iso_date(published_to, "--published-to") if published_to else None
    if first and last and first > last:
        raise click.BadParameter("must not be after --published-to", param_hint="--published-from")

    rows = export_scans(
        get_connection(db_path),
        domain=domain,
        label=label,
        published_from=first,
        published_to=last,
    )
    filters = {
        key: value
        for key, value in {
            "domain": domain,
            "label": label,
            "published_from": first.isoformat() if first else None,
            "published_to": last.isoformat() if last else None,
        }.items()
        if value is not None
    }
    if output_format == "json":
        payload = {"schema_version": 1, "filters": filters, "rows": rows}
        _write_output(json.dumps(payload, indent=2, sort_keys=True) + "\n", output_path)
        return

    stream = io.StringIO()
    fields = [
        "id",
        "url",
        "domain",
        "file_path",
        "word_count",
        "score",
        "label",
        "scanned_at",
        "published_date",
        "title",
        "score_vector_json",
        "patterns_json",
    ]
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        flat = {key: row.get(key) for key in fields if key in row}
        flat["score_vector_json"] = json.dumps(row.get("score_vector", {}), sort_keys=True)
        flat["patterns_json"] = json.dumps(row.get("patterns", []), sort_keys=True)
        writer.writerow(flat)
    _write_output(stream.getvalue(), output_path)

