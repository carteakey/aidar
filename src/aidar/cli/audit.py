from __future__ import annotations

import json
from collections import Counter

import click

from aidar.cli.main import aidar
from aidar.core.ingestion import classify_url
from aidar.db.database import get_connection


@aidar.command("audit-corpus")
@click.option("--db", "db_path", default="aidar.db", show_default=True)
@click.option(
    "--min-words",
    default=50,
    show_default=True,
    help="Flag stored rows below this extracted word count.",
)
@click.pass_context
def audit_corpus(ctx: click.Context, db_path: str, min_words: int) -> None:
    """Report likely non-prose rows without modifying the corpus."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT id, url, domain, word_count, title, scanned_at FROM scans ORDER BY id"
    ).fetchall()
    flagged: list[dict] = []
    reasons: Counter[str] = Counter()
    for row in rows:
        reason = classify_url(row["url"]) if row["url"] else "missing_url"
        if reason is None and (row["word_count"] or 0) < min_words:
            reason = "short_text"
        if reason:
            reasons[reason] += 1
            flagged.append({**dict(row), "reason": reason})

    report = {
        "scanned_rows": len(rows),
        "flagged_rows": len(flagged),
        "reasons": dict(sorted(reasons.items())),
        "rows": flagged,
    }
    if ctx.obj["output"] == "json":
        click.echo(json.dumps(report, indent=2, sort_keys=True))
        return

    click.echo(
        f"Audited {report['scanned_rows']} rows; flagged {report['flagged_rows']} likely non-prose rows."
    )
    for reason, count in sorted(reasons.items()):
        click.echo(f"  {reason}: {count}")
    for row in flagged[:20]:
        click.echo(f"  [{row['reason']}] {row['url'] or '(missing URL)'}")
    if len(flagged) > 20:
        click.echo(f"  ... and {len(flagged) - 20} more")
