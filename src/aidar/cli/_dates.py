from __future__ import annotations

from datetime import date

import click


def parse_iso_date(value: str, option: str = "date") -> date:
    """Parse a zero-padded ISO calendar date for CLI options."""
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise click.BadParameter("must be a valid ISO date (YYYY-MM-DD)", param_hint=option) from exc
    if parsed.isoformat() != value:
        raise click.BadParameter("must use YYYY-MM-DD with zero padding", param_hint=option)
    return parsed
