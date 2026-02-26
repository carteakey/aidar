# Changelog

All notable changes to the aidar pattern repository and tooling.

Format: `[version] — date — description`
Pattern version bumps are noted separately from tool version bumps.

---

## Tool Changes

### [0.2.0] — 2026-02-26
- **Pattern versioning**: `version` field in all YAML files; stored per-row in DB
- **`aidar patterns versions`**: shows loaded vs stored pattern versions, flags stale scans
- **`aidar track --rescan-stale`**: re-scans URLs where pattern versions have changed
- **`aidar discover`**: discover article URLs from sitemap or RSS feed
- **`aidar track`**: one-command domain monitoring (discover + scan + save)
- **Published date extraction**: trafilatura now extracts article publish date; stored in DB
- **Percentile scoring**: `get_corpus_percentile()` for relative ranking across corpus
- **Threshold recalibration**: lowered to 15/30 based on observed scan data (was 30/65)
- **`FetchResult`** object replaces bare tuples from fetcher functions
- Web: submit-site form, domain trend chart, percentile display in leaderboard

### [0.1.0] — 2026-02-25
- Initial release: 12 patterns, `analyze`, `compare`, `scan`, `patterns` CLI commands
- SQLite persistence, FastAPI web dashboard, async bulk scanning

---

## Pattern Changes

### [hedging_phrases v2] — 2026-02-26
Added: `honestly`, `to be honest`, `to be fair`, `to be clear`, `genuinely`,
`truthfully`, `candidly`, `i must say`, `i have to say`

Rationale: "Honestly" is one of the most consistent AI authenticity-performance markers.
Models use it to appear candid while still hedging. Submitted from field observation.

---

### [sentence_burstiness v1] — 2026-02-26
New pattern. CV of sentence lengths, inverted. Low variation = uniform = AI-like.

### [type_token_ratio v1] — 2026-02-26
New pattern. Standardized TTR over sliding 50-word windows. Lightweight perplexity proxy.

### [question_avoidance v1] — 2026-02-26
New pattern. AI almost never asks questions. Inverted question rate.

### [transition_overload v1] — 2026-02-26
New pattern. furthermore/moreover/additionally density cluster.
