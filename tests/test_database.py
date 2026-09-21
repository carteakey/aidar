from __future__ import annotations

from datetime import date

from aidar.core.scorer import compute_aggregate
from aidar.db.database import get_connection
from aidar.db.queries import (
    count_domain_leaderboard,
    export_scans,
    get_domain_diff,
    get_domain_leaderboard,
    get_stale_urls,
    store_result,
)
from aidar.models.config import AppConfig, WeightConfig
from aidar.models.result import ScoreVector


def test_store_result_upserts_same_scan(tmp_path) -> None:
    conn = get_connection(tmp_path / "aidar.db")
    result = compute_aggregate(
        ScoreVector(),
        AppConfig(patterns_dir="patterns", weights=WeightConfig()),
        url="https://example.com/post",
        word_count=100,
    )

    first_id = store_result(conn, result)
    second_id = store_result(conn, result)

    assert second_id == first_id
    assert conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0] == 1


def test_stale_urls_include_missing_patterns(tmp_path) -> None:
    conn = get_connection(tmp_path / "aidar.db")
    conn.execute(
        """
        INSERT INTO scans
            (url, domain, file_path, word_count, score, label, score_json, scanned_at)
        VALUES ('https://example.com/1', 'example.com', NULL, 100, 10, 'LIKELY HUMAN', '{}',
                '2026-01-01T00:00:00')
        """
    )
    scan_id = conn.execute("SELECT id FROM scans").fetchone()["id"]
    conn.execute(
        """
        INSERT INTO pattern_scores
            (scan_id, pattern_id, category, raw_value, norm_score, pattern_version,
             pattern_hash)
        VALUES (?, 'existing', 'phrases', 0, 0, 1, 'hash-a')
        """,
        (scan_id,),
    )
    conn.commit()

    stale = get_stale_urls(
        conn,
        {"existing": (1, "hash-a"), "new-pattern": (1, "hash-b")},
    )

    assert stale == ["https://example.com/1"]


def test_export_and_diff_preserve_dates_and_vectors(tmp_path) -> None:
    conn = get_connection(tmp_path / "aidar.db")
    config = AppConfig(patterns_dir="patterns", weights=WeightConfig())
    first = compute_aggregate(
        ScoreVector(phrases=0.2),
        config,
        url="https://example.com/first",
        word_count=100,
        published_date="2026-01-01",
    )
    second = compute_aggregate(
        ScoreVector(phrases=0.8),
        config,
        url="https://example.com/second",
        word_count=100,
        published_date="2026-01-02",
    )
    store_result(conn, first)
    store_result(conn, second)
    conn.execute("UPDATE scans SET scanned_at = '2026-01-01T10:00:00+00:00' WHERE url LIKE '%first'")
    conn.execute("UPDATE scans SET scanned_at = '2026-01-02T10:00:00+00:00' WHERE url LIKE '%second'")
    conn.commit()

    exported = export_scans(conn, domain="example.com", published_from=date(2026, 1, 1))
    assert [row["url"] for row in exported] == ["https://example.com/first", "https://example.com/second"]
    assert exported[0]["published_date"] == "2026-01-01"
    assert "patterns" in exported[0]

    diff = get_domain_diff(conn, "example.com", date(2026, 1, 1), date(2026, 1, 2))
    assert diff["delta"]["pages"] == 0
    assert diff["delta"]["score"] > 0


def test_domain_leaderboard_paginates_and_filters_labels(tmp_path) -> None:
    conn = get_connection(tmp_path / "aidar.db")
    conn.executemany(
        """
        INSERT INTO scans (url, domain, word_count, score, label, score_json, scanned_at)
        VALUES (?, ?, 100, ?, ?, '{}', '2026-01-01T00:00:00')
        """,
        [
            ("https://a.example/1", "a.example", 80, "LIKELY AI"),
            ("https://b.example/1", "b.example", 20, "LIKELY HUMAN"),
        ],
    )
    conn.commit()

    assert count_domain_leaderboard(conn) == 2
    assert count_domain_leaderboard(conn, "LIKELY AI") == 1
    rows = get_domain_leaderboard(conn, limit=1, offset=1)
    assert rows[0]["domain"] == "b.example"
    assert get_domain_leaderboard(conn, label_filter="LIKELY HUMAN")[0]["domain"] == "b.example"
