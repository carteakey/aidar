# Corpus operations

The SQLite corpus is an append/update store keyed by URL. Commands in this
document are designed to be resumable and non-destructive by default.

## Publication dates

Fetch metadata is authoritative when present. `aidar analyze --published-date
YYYY-MM-DD` fills a missing date only; it validates a real, zero-padded ISO
calendar date and never replaces a publisher date. The value is persisted in
`scans.published_date` and returned by exports and API responses.

## Backfill

`aidar backfill example.com --dry-run` lists the persisted URL history and the
number of candidates. A normal run rescans every stored URL, preserving an
existing publication date when a later extraction omits it. Use
`--skip-existing` to turn the command into a no-op audit, `--limit` to bound a
batch, and `--concurrency` to respect publisher capacity. Failed fetches are
reported by structured ingestion reason and are never written as valid rows.

## Export and diff

`aidar export` emits schema-versioned JSON or CSV. JSON includes the aggregate
score vector and every stored pattern result (version and fingerprint included),
with deterministic URL ordering. `--domain`, `--label`, `--published-from`, and
`--published-to` narrow an export without changing source rows.

`aidar diff DOMAIN YYYY-MM-DD YYYY-MM-DD` compares scans by their persisted
`scanned_at` calendar date. Multiple pages are averaged in deterministic URL
order; missing dates are reported as an error rather than interpreted as zero.

All commands operate offline against SQLite unless a backfill is actually run.
