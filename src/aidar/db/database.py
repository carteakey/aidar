from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT,
    domain          TEXT,
    file_path       TEXT,
    word_count      INTEGER,
    score           INTEGER,
    label           TEXT,
    score_json      TEXT,
    scanned_at      TEXT,
    published_date  TEXT,    -- ISO date extracted from article metadata e.g. "2024-03-15"
    title           TEXT,
    UNIQUE(url)
);

CREATE TABLE IF NOT EXISTS pattern_scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id         INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    pattern_id      TEXT NOT NULL,
    category        TEXT NOT NULL,
    raw_value       REAL,
    norm_score      REAL,
    pattern_version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_scans_domain ON scans(domain);
CREATE INDEX IF NOT EXISTS idx_scans_score ON scans(score DESC);
CREATE INDEX IF NOT EXISTS idx_pattern_scores_scan ON pattern_scores(scan_id);
"""


def get_connection(db_path: str | Path = "aidar.db") -> sqlite3.Connection:
    """Open (or create) the SQLite database and ensure schema exists."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply additive schema migrations for existing databases."""
    ps_cols = {row[1] for row in conn.execute("PRAGMA table_info(pattern_scores)").fetchall()}
    if "pattern_version" not in ps_cols:
        conn.execute(
            "ALTER TABLE pattern_scores ADD COLUMN pattern_version INTEGER NOT NULL DEFAULT 1"
        )

    scan_cols = {row[1] for row in conn.execute("PRAGMA table_info(scans)").fetchall()}
    if "published_date" not in scan_cols:
        conn.execute("ALTER TABLE scans ADD COLUMN published_date TEXT")
    if "title" not in scan_cols:
        conn.execute("ALTER TABLE scans ADD COLUMN title TEXT")
