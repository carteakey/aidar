from __future__ import annotations

from aidar.core.scorer import compute_aggregate
from aidar.db.database import get_connection
from aidar.db.queries import get_stale_urls, store_result
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
