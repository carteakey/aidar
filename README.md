# aidar

Track stylistic patterns across the web to surface AI-era writing trends.

aidar measures known stylistic signals — em dash frequency, hedging phrases, bullet density, AI vocabulary idioms, emoji usage — and aggregates them into a per-site index. The goal isn't to classify individual pages as "AI or not", it's to build a comparable, queryable dataset of how writing style is shifting across the web at scale.

Inspired by: [New accounts on Hacker News ten times more likely to use em-dashes](https://www.marginalia.nu/weird-ai-crap/hn/)

## References

- ["Wikipedia: Signs of AI writing"](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) — 2023–present
- ["Tropes - AI Writing Pattern Directory"](https://tropes.fyi/), Ossama Chaib — 2026

## What it does

- Scans URLs or local files and scores them across stylistic signal categories
- Outputs a per-category breakdown + a 0–100 **Stylistic Index** for cross-site comparison
- Stores results in SQLite for trend analysis and leaderboard queries
- Async bulk scanning — built to run across thousands of sites

## Quick start

```bash
pip install -e .
cp .env.example .env  # fill Litestream/R2 credentials

# Analyze a single page
aidar analyze https://example.com

# Analyze raw text directly
aidar analyze --text "paste your article here"

# Compare multiple pages side by side
aidar compare https://site1.com https://site2.com https://site3.com

# Discover all pages on a site, then bulk scan
aidar discover example.com -o urls.txt
aidar scan --batch urls.txt --concurrency 20 --min-words 50 --save

# Inspect loaded signal patterns
aidar patterns list
aidar patterns show em_dash_overuse
aidar patterns versions

# JSON output for downstream use
aidar --output json analyze https://example.com

# Keep scanning domains in a loop (overnight worker)
aidar worker --domains-file domains.txt --interval-minutes 60 --limit 200 --db aidar.db

# HN trending domains only (refresh every 24h)
aidar worker --hn-domains 25 --hn-story-limit 250 --interval-minutes 1440 --max-cycles 0 --db aidar.db

# Existing domains from file with pull/push sync
bash scripts/domains-daily-sync.sh
```

Saved operational runbook: [`docs/HN_RUNBOOK.md`](docs/HN_RUNBOOK.md).

## Signal categories

| Category    | Weight | Examples                                                                                  |
|-------------|--------|-------------------------------------------------------------------------------------------|
| tropes      | 0.40   | negative parallelism, em-dash addiction, bold-first bullets, "here's the kicker", tricolon abuse, signposted conclusions, grandiose stakes inflation |
| phrases     | 0.20   | "delve into", "it's worth noting", "let's explore", "key takeaway"                       |
| punctuation | 0.15   | em dash frequency, ellipsis overuse, semicolon density                                   |
| structure   | 0.10   | bullet point density, header frequency, sentence burstiness, question avoidance          |
| vocabulary  | 0.10   | magic adverbs (quietly, fundamentally), "serves as" dodge, tapestry/landscape, formal register |
| emoji       | 0.05   | emoji density and placement                                                              |

## Pattern repository

Patterns live in `patterns/` as YAML files — no Python needed to add new signals. Model profiles in `patterns/models/` store known stylistic baselines for Claude, GPT-4, and Gemini for use with `--compare-model`.

For a full inventory of active patterns and current thresholds, see [`docs/PATTERN_CATALOG.md`](docs/PATTERN_CATALOG.md).

Pattern staleness is automatic:
- Each stored pattern score now includes both `pattern_version` and a fingerprint hash.
- If a pattern YAML changes (even without a version bump), stale URLs are auto-detected and re-scanned during `aidar track` / `aidar worker` (unless `--no-rescan-stale` is set).
- Existing rows from older DBs (without stored hashes) are treated as stale once and get refreshed on the next run.

## Leaderboard

Results stored with `--save` are queryable via `aidar.db`. The `db/queries.py` module exposes `get_leaderboard()`, `get_domain_stats()`, and `get_pattern_stats()` for building a web dashboard once you've accumulated enough scan data.
