from __future__ import annotations

import json
import sqlite3
from urllib.parse import urlparse

from aidar.models.result import AggregateResult


def store_result(conn: sqlite3.Connection, result: AggregateResult) -> int:
    """
    Persist an AggregateResult to the database.
    If the URL already exists, updates the existing row.
    Returns the scan row id.
    """
    domain = ""
    if result.url:
        parsed = urlparse(result.url)
        domain = parsed.netloc

    score_json = json.dumps(result.score_vector.as_dict())

    cursor = conn.execute(
        """
        INSERT INTO scans (url, domain, file_path, word_count, score, label, score_json, scanned_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            word_count=excluded.word_count,
            score=excluded.score,
            label=excluded.label,
            score_json=excluded.score_json,
            scanned_at=excluded.scanned_at
        """,
        (
            result.url,
            domain,
            result.file_path,
            result.word_count,
            result.aggregate_score,
            result.label,
            score_json,
            result.scanned_at.isoformat(),
        ),
    )
    scan_id = cursor.lastrowid

    # Delete old pattern scores for this scan (in case of update)
    conn.execute("DELETE FROM pattern_scores WHERE scan_id = ?", (scan_id,))

    # Insert fresh pattern scores with version
    conn.executemany(
        "INSERT INTO pattern_scores "
        "(scan_id, pattern_id, category, raw_value, norm_score, pattern_version) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (scan_id, r.pattern_id, r.category, r.raw_value, r.normalized_score, r.pattern_version)
            for r in result.score_vector.pattern_results
        ],
    )
    conn.commit()
    return scan_id


def get_leaderboard(
    conn: sqlite3.Connection,
    limit: int = 100,
    offset: int = 0,
    label_filter: str | None = None,
) -> list[dict]:
    """Return top-scored sites for the leaderboard."""
    query = "SELECT id, url, domain, word_count, score, label, scanned_at FROM scans"
    params: list = []
    if label_filter:
        query += " WHERE label = ?"
        params.append(label_filter)
    query += " ORDER BY score DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_domain_stats(conn: sqlite3.Connection, domain: str) -> dict:
    """Return aggregate stats for all scans of a domain."""
    rows = conn.execute(
        "SELECT score, label, scanned_at FROM scans WHERE domain = ? ORDER BY scanned_at DESC",
        (domain,),
    ).fetchall()
    if not rows:
        return {"domain": domain, "scans": 0}
    scores = [r["score"] for r in rows]
    return {
        "domain": domain,
        "scans": len(rows),
        "avg_score": round(sum(scores) / len(scores), 1),
        "max_score": max(scores),
        "min_score": min(scores),
        "latest": rows[0]["scanned_at"],
        "label_counts": {
            "LIKELY AI": sum(1 for r in rows if r["label"] == "LIKELY AI"),
            "UNCERTAIN": sum(1 for r in rows if r["label"] == "UNCERTAIN"),
            "LIKELY HUMAN": sum(1 for r in rows if r["label"] == "LIKELY HUMAN"),
        },
    }


def get_pattern_stats(conn: sqlite3.Connection) -> list[dict]:
    """Return average normalized score per pattern across all scans."""
    rows = conn.execute(
        """
        SELECT pattern_id, category,
               AVG(norm_score) as avg_score,
               COUNT(*) as occurrences
        FROM pattern_scores
        GROUP BY pattern_id
        ORDER BY avg_score DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def url_already_scanned(conn: sqlite3.Connection, url: str) -> bool:
    row = conn.execute("SELECT id FROM scans WHERE url = ?", (url,)).fetchone()
    return row is not None


def get_stale_urls(
    conn: sqlite3.Connection,
    current_versions: dict[str, int],
    domain: str | None = None,
) -> list[str]:
    """
    Return URLs whose pattern scores were computed with an older pattern version.
    current_versions: dict of {pattern_id: current_version} from the loaded registry.
    If domain is set, only checks that domain.
    """
    stale: set[str] = set()
    for pattern_id, current_version in current_versions.items():
        query = """
            SELECT DISTINCT s.url
            FROM scans s
            JOIN pattern_scores ps ON ps.scan_id = s.id
            WHERE ps.pattern_id = ?
              AND ps.pattern_version < ?
              AND s.url IS NOT NULL
        """
        params: list = [pattern_id, current_version]
        if domain:
            query += " AND s.domain = ?"
            params.append(domain)
        rows = conn.execute(query, params).fetchall()
        stale.update(r["url"] for r in rows)
    return sorted(stale)


def get_pattern_version_summary(conn: sqlite3.Connection) -> list[dict]:
    """Show which pattern versions are stored in the DB vs what's loaded."""
    rows = conn.execute(
        """
        SELECT pattern_id,
               MAX(pattern_version) as max_stored_version,
               COUNT(DISTINCT scan_id) as scan_count
        FROM pattern_scores
        GROUP BY pattern_id
        ORDER BY pattern_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_domain_scans(
    conn: sqlite3.Connection,
    domain: str,
    limit: int = 100,
) -> list[dict]:
    """Return individual page scans for a domain, newest first."""
    rows = conn.execute(
        """
        SELECT url, word_count, score, label, score_json, scanned_at
        FROM scans
        WHERE domain = ?
        ORDER BY scanned_at DESC
        LIMIT ?
        """,
        (domain, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def get_global_stats(conn: sqlite3.Connection) -> dict:
    """Return high-level corpus stats for the homepage."""
    row = conn.execute(
        """
        SELECT
            COUNT(*) as total_scans,
            COUNT(DISTINCT domain) as total_domains,
            ROUND(AVG(score), 1) as avg_score,
            SUM(CASE WHEN label = 'LIKELY AI' THEN 1 ELSE 0 END) as likely_ai,
            SUM(CASE WHEN label = 'UNCERTAIN' THEN 1 ELSE 0 END) as uncertain,
            SUM(CASE WHEN label = 'LIKELY HUMAN' THEN 1 ELSE 0 END) as likely_human
        FROM scans
        """
    ).fetchone()
    return dict(row) if row else {}


def get_domain_leaderboard(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    """Return per-domain aggregated stats for the leaderboard."""
    rows = conn.execute(
        """
        SELECT
            domain,
            COUNT(*) as pages,
            ROUND(AVG(score), 1) as avg_score,
            MAX(score) as max_score,
            MAX(scanned_at) as last_scanned
        FROM scans
        WHERE domain != ''
        GROUP BY domain
        ORDER BY avg_score DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]
