from __future__ import annotations

import json

import click

from aidar.cli._dates import parse_iso_date
from aidar.cli.main import aidar
from aidar.db.queries import get_domain_diff


@aidar.command("diff")
@click.argument("domain")
@click.argument("first_date")
@click.argument("second_date")
@click.option("--db", "db_path", default="aidar.db", show_default=True)
@click.pass_context
def diff_command(
    ctx: click.Context,
    domain: str,
    first_date: str,
    second_date: str,
    db_path: str,
) -> None:
    """Compare a domain's persisted score between two scan dates."""
    from aidar.db.database import get_connection

    before = parse_iso_date(first_date, "FIRST_DATE")
    after = parse_iso_date(second_date, "SECOND_DATE")
    result = get_domain_diff(get_connection(db_path), domain, before, after)
    if result["delta"] is None:
        raise click.ClickException(
            f"no persisted scans for {domain} on both {before.isoformat()} and {after.isoformat()}"
        )
    if ctx.obj["output"] == "json":
        click.echo(json.dumps(result, indent=2, sort_keys=True))
        return
    click.echo(
        f"{domain}: {before.isoformat()} → {after.isoformat()} "
        f"score {result['before']['score']:.2f} → {result['after']['score']:.2f} "
        f"(Δ {result['delta']['score']:+.2f})"
    )
    click.echo(f"pages: {result['before']['pages']} → {result['after']['pages']}")
    for category, delta in result["delta"]["categories"].items():
        click.echo(f"{category}: {delta:+.4f}")

