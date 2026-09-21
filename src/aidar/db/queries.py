from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import date
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

    conn.execute(
        """
        INSERT INTO scans
            (url, domain, file_path, word_count, score, label, score_json,
             scanned_at, published_date, title, source_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            word_count=excluded.word_count,
            score=excluded.score,
            label=excluded.label,
            score_json=excluded.score_json,
            scanned_at=excluded.scanned_at,
            published_date=COALESCE(excluded.published_date, scans.published_date),
            title=COALESCE(excluded.title, scans.title),
            source_url=COALESCE(excluded.source_url, scans.source_url)
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
            result.published_date,
            result.title,
            result.source_url,
        ),
    )
    # Always fetch the real ID — lastrowid is unreliable for ON CONFLICT DO UPDATE
    scan_id = int(
        conn.execute(
            "SELECT id FROM scans WHERE url = ? OR (url IS NULL AND file_path = ?)",
            (result.url, result.file_path),
        ).fetchone()[0]
    )

    # Delete old pattern scores for this scan (in case of update)
    conn.execute("DELETE FROM pattern_scores WHERE scan_id = ?", (scan_id,))

    # Insert fresh pattern scores with version
    conn.executemany(
        "INSERT INTO pattern_scores "
        "(scan_id, pattern_id, category, raw_value, norm_score, pattern_version, pattern_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                scan_id,
                r.pattern_id,
                r.category,
                r.raw_value,
                r.normalized_score,
                r.pattern_version,
                r.pattern_hash,
            )
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


def get_pattern_detail(conn: sqlite3.Connection, pattern_id: str, limit: int = 20) -> dict:
    """Return aggregate stats plus representative evidence for one pattern."""
    summary = conn.execute(
        """
        SELECT pattern_id, category, AVG(norm_score) AS avg_score,
               COUNT(*) AS occurrences, MAX(pattern_version) AS version,
               MAX(pattern_hash) AS pattern_hash
        FROM pattern_scores
        WHERE pattern_id = ?
        GROUP BY pattern_id, category
        """,
        (pattern_id,),
    ).fetchone()
    rows = conn.execute(
        """
        SELECT s.url, s.domain, s.scanned_at, s.word_count,
               ps.raw_value, ps.norm_score, ps.pattern_version, ps.pattern_hash
        FROM pattern_scores ps
        JOIN scans s ON s.id = ps.scan_id
        WHERE ps.pattern_id = ?
        ORDER BY ps.norm_score DESC, s.scanned_at DESC, s.url ASC
        LIMIT ?
        """,
        (pattern_id, max(1, min(limit, 100))),
    ).fetchall()
    return {
        "pattern_id": pattern_id,
        "summary": dict(summary) if summary else None,
        "evidence": [dict(row) for row in rows],
    }


def url_already_scanned(conn: sqlite3.Connection, url: str) -> bool:
    row = conn.execute("SELECT id FROM scans WHERE url = ?", (url,)).fetchone()
    return row is not None


def get_stale_urls(
    conn: sqlite3.Connection,
    current_versions: Mapping[str, int | tuple[int, str]],
    domain: str | None = None,
) -> list[str]:
    """
    Return URLs whose pattern scores were computed with an older pattern version.
    current_versions: dict of {pattern_id: current_version} from the loaded registry.
    If domain is set, only checks that domain.
    """
    normalized: list[tuple[str, int, str]] = []
    for pattern_id, value in current_versions.items():
        if isinstance(value, tuple):
            version, pattern_hash = value
        else:
            version, pattern_hash = value, ""
        normalized.append((pattern_id, int(version), str(pattern_hash)))

    if not normalized:
        return []

    values_sql = ",".join("(?, ?, ?)" for _ in normalized)
    params: list = []
    for row in normalized:
        params.extend(row)

    query = f"""
        WITH current(pattern_id, pattern_version, pattern_hash) AS (
            VALUES {values_sql}
        )
        SELECT DISTINCT s.url
        FROM scans s
        CROSS JOIN current c
        LEFT JOIN pattern_scores ps
          ON ps.scan_id = s.id
         AND ps.pattern_id = c.pattern_id
        WHERE s.url IS NOT NULL
          AND (
                ps.scan_id IS NULL
                OR ps.pattern_version < c.pattern_version
                OR (
                    c.pattern_hash != ''
                    AND COALESCE(ps.pattern_hash, '') != c.pattern_hash
                )
              )
    """
    if domain:
        query += " AND s.domain = ?"
        params.append(domain)

    rows = conn.execute(query, params).fetchall()
    return sorted(r["url"] for r in rows)


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


def get_domain_trend(conn: sqlite3.Connection, domain: str) -> list[dict]:
    """Return scans ordered by published_date for trend charting."""
    rows = conn.execute(
        """
        SELECT url, title, score, label, word_count,
               published_date, scanned_at
        FROM scans
        WHERE domain = ?
          AND published_date IS NOT NULL
        ORDER BY published_date ASC
        """,
        (domain,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_corpus_percentile(conn: sqlite3.Connection, score: int) -> float:
    """Return what percentile this score is in (0.0–1.0) across all scans."""
    total = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
    if not total:
        return 0.0
    below = conn.execute("SELECT COUNT(*) FROM scans WHERE score <= ?", (score,)).fetchone()[0]
    return float(round(below / total, 3))


def get_domain_scans(
    conn: sqlite3.Connection,
    domain: str,
    limit: int = 100,
    sort: str = "recent",  # "recent" | "highest" | "lowest"
) -> list[dict]:
    """Return individual page scans for a domain."""
    order = {
        "highest": "score DESC",
        "lowest": "score ASC",
    }.get(sort, "scanned_at DESC")
    rows = conn.execute(
        f"""
        SELECT id AS scan_id, url, word_count, score, label, score_json, scanned_at,
               published_date, title, source_url
        FROM scans
        WHERE domain = ?
        ORDER BY {order}
        LIMIT ?
        """,
        (domain, limit),
    ).fetchall()
    result: list[dict] = []
    for row in rows:
        item = dict(row)
        scan_id = item.pop("scan_id")
        pattern_rows = conn.execute(
            """
            SELECT pattern_id, category, raw_value, norm_score,
                   pattern_version, pattern_hash
            FROM pattern_scores
            WHERE scan_id = ?
            ORDER BY norm_score DESC, pattern_id ASC
            """,
            (scan_id,),
        ).fetchall()
        item["patterns"] = [dict(pattern) for pattern in pattern_rows]
        result.append(item)
    return result


def export_scans(
    conn: sqlite3.Connection,
    *,
    domain: str | None = None,
    label: str | None = None,
    published_from: date | None = None,
    published_to: date | None = None,
) -> list[dict]:
    """Return deterministic, lossless scan rows for export workflows."""
    clauses: list[str] = []
    params: list[str] = []
    if domain:
        clauses.append("s.domain = ?")
        params.append(domain)
    if label:
        clauses.append("s.label = ?")
        params.append(label)
    if published_from:
        clauses.append("s.published_date >= ?")
        params.append(published_from.isoformat())
    if published_to:
        clauses.append("s.published_date <= ?")
        params.append(published_to.isoformat())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT s.id, s.url, s.domain, s.file_path, s.word_count, s.score, s.label,
               s.score_json, s.scanned_at, s.published_date, s.title, s.source_url
        FROM scans s
        {where}
        ORDER BY COALESCE(s.url, s.file_path, ''), s.id
        """,
        params,
    ).fetchall()
    exported: list[dict] = []
    for row in rows:
        item = dict(row)
        try:
            item["score_vector"] = json.loads(item.pop("score_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["score_vector"] = {}
        pattern_rows = conn.execute(
            """
            SELECT pattern_id, category, raw_value, norm_score,
                   pattern_version, pattern_hash
            FROM pattern_scores
            WHERE scan_id = ?
            ORDER BY pattern_id
            """,
            (row["id"],),
        ).fetchall()
        item["patterns"] = [dict(pattern) for pattern in pattern_rows]
        exported.append(item)
    return exported


def get_domain_diff(
    conn: sqlite3.Connection,
    domain: str,
    first_date: date,
    second_date: date,
) -> dict:
    """Compare deterministic per-day aggregates for a domain."""
    if first_date > second_date:
        raise ValueError("first date must not be after second date")

    def snapshot(day: date) -> dict | None:
        rows = conn.execute(
            """
            SELECT score, score_json, url
            FROM scans
            WHERE domain = ? AND substr(scanned_at, 1, 10) = ?
            ORDER BY COALESCE(url, ''), id
            """,
            (domain, day.isoformat()),
        ).fetchall()
        if not rows:
            return None
        scores = [int(row["score"]) for row in rows]
        categories: dict[str, list[float]] = {}
        for row in rows:
            try:
                vector = json.loads(row["score_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                vector = {}
            for key, value in vector.items():
                if isinstance(value, (int, float)):
                    categories.setdefault(key, []).append(float(value))
        return {
            "date": day.isoformat(),
            "pages": len(rows),
            "score": round(sum(scores) / len(scores), 2),
            "categories": {
                key: round(sum(values) / len(values), 4)
                for key, values in sorted(categories.items())
            },
        }

    before = snapshot(first_date)
    after = snapshot(second_date)
    if before is None or after is None:
        return {"domain": domain, "before": before, "after": after, "delta": None}
    category_keys = sorted(set(before["categories"]) | set(after["categories"]))
    return {
        "domain": domain,
        "before": before,
        "after": after,
        "delta": {
            "pages": after["pages"] - before["pages"],
            "score": round(after["score"] - before["score"], 2),
            "categories": {
                key: round(after["categories"].get(key, 0.0) - before["categories"].get(key, 0.0), 4)
                for key in category_keys
            },
        },
    }


def get_recent_scans(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    """Return recent persisted scans for RSS/Atom feeds."""
    rows = conn.execute(
        """
        SELECT url, domain, title, score, label, scanned_at, published_date
        FROM scans
        WHERE url IS NOT NULL
        ORDER BY scanned_at DESC, id DESC
        LIMIT ?
        """,
        (max(1, min(limit, 200)),),
    ).fetchall()
    return [dict(row) for row in rows]


def get_domain_extremes(
    conn: sqlite3.Connection,
    domain: str,
    n: int = 5,
) -> tuple[list[dict], list[dict]]:
    """Return (top_n highest scoring, top_n lowest scoring) pages for a domain."""
    base = "SELECT url, word_count, score, label, scanned_at FROM scans WHERE domain = ? AND word_count > 100"
    highest = [
        dict(r) for r in conn.execute(f"{base} ORDER BY score DESC LIMIT ?", (domain, n)).fetchall()
    ]
    lowest = [
        dict(r) for r in conn.execute(f"{base} ORDER BY score ASC LIMIT ?", (domain, n)).fetchall()
    ]
    return highest, lowest


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


def delete_domain(conn: sqlite3.Connection, domain: str) -> int:
    """Delete all scans (and cascaded pattern_scores) for a domain. Returns row count."""
    cur = conn.execute("DELETE FROM scans WHERE domain = ?", (domain,))
    conn.commit()
    return cur.rowcount


def get_domain_leaderboard(
    conn: sqlite3.Connection,
    limit: int = 50,
    offset: int = 0,
    label_filter: str | None = None,
) -> list[dict]:
    """Return per-domain aggregated stats for the leaderboard."""
    params: list[object] = []
    where = "WHERE domain != ''"
    having = ""
    if label_filter:
        having = "HAVING SUM(CASE WHEN label = ? THEN 1 ELSE 0 END) > 0"
    rows = conn.execute(
        f"""
        SELECT domain,
               COUNT(*) as pages,
               ROUND(AVG(score), 1) as avg_score,
               MAX(score) as max_score,
               MAX(scanned_at) as last_scanned,
               (SELECT s2.label FROM scans s2
                WHERE s2.domain = scans.domain
                ORDER BY s2.scanned_at DESC, s2.id DESC LIMIT 1) as last_label
        FROM scans
        {where}
        GROUP BY domain
        {having}
        ORDER BY avg_score DESC, domain ASC
        LIMIT ? OFFSET ?
        """,
        ((*params, label_filter) if label_filter else tuple())
        + (max(1, min(limit, 200)), max(0, offset)),
    ).fetchall()
    return [dict(row) for row in rows]


def count_domain_leaderboard(conn: sqlite3.Connection, label_filter: str | None = None) -> int:
    """Count leaderboard domains using the same optional label semantics."""
    if label_filter:
        return int(
            conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT domain FROM scans
                    WHERE domain != ''
                    GROUP BY domain
                    HAVING SUM(CASE WHEN label = ? THEN 1 ELSE 0 END) > 0
                )
                """,
                (label_filter,),
            ).fetchone()[0]
        )
    return int(
        conn.execute("SELECT COUNT(DISTINCT domain) FROM scans WHERE domain != ''").fetchone()[0]
    )
