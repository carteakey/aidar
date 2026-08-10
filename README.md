# aidar

Track stylistic patterns across the web to surface AI-era writing trends.

aidar measures known stylistic signals — em dash frequency, hedging phrases, bullet density, AI vocabulary idioms, emoji usage — and aggregates them into a per-site index. The goal isn't to classify individual pages as "AI or not", it's to build a comparable, queryable dataset of how writing style is shifting across the web at scale.

Inspired by: [New accounts on Hacker News ten times more likely to use em-dashes](https://www.marginalia.nu/weird-ai-crap/hn/)

## References

- ["Wikipedia: Signs of AI writing"](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) — 2023–present
- ["Tropes - AI Writing Pattern Directory"](https://tropes.fyi/), Ossama Chaib — 2026
- [LLM writing style: empirical stylometric study](https://arxiv.org/abs/2410.16107) (PNAS 2025) — GPT-4o's second-most-overused word is "tapestry"; present participles alone are a near-sufficient classifier
- [LLM writing style resources](https://www.refsmmat.com/notebooks/llm-style.html), Alex Reinhart — curated research notebook

## What it does

- Scans URLs or local files and scores them across stylistic signal categories
- Outputs a per-category breakdown + a 0–100 **Stylistic Index** for cross-site comparison
- Stores results in SQLite for trend analysis and leaderboard queries
- Async bulk scanning — built to run across thousands of sites

## Quick start

```bash
pip install -e .

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

# HN top + new stories (broader coverage)
aidar worker --hn-domains 25 --hn-new-domains 20 --hn-new-story-limit 100 --interval-minutes 1440 --max-cycles 0 --db aidar.db

# Existing domains from file with pull/push sync
bash scripts/domains-daily-sync.sh

# Reprocess a stored domain history (dry-run first)
aidar backfill example.com --dry-run
aidar backfill example.com --concurrency 5

# Export scored pages and evidence for external analysis
aidar export --format json --output scans.json
aidar export --format csv --domain example.com --output example.csv

# Compare deterministic scan-date snapshots
aidar diff example.com 2026-01-01 2026-02-01
```

Saved operational runbook: [`docs/HN_RUNBOOK.md`](docs/HN_RUNBOOK.md).

## Signal categories

| Category    | Weight | Examples                                                                                  |
|-------------|--------|-------------------------------------------------------------------------------------------|
| tropes      | 0.40   | negative parallelism, em-dash addiction, bold-first bullets, AI section headers ("The Takeaway", "Why This Matters"), "here's the kicker", tricolon abuse, signposted conclusions, grandiose stakes inflation |
| phrases     | 0.20   | second-person address ("Here's how it actually went", "We've all been there"), "delve into", "it's worth noting", "let's explore"                    |
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

## Development

Aidar supports Python 3.11 and 3.12. The committed `uv.lock` is the reproducible
development environment:

```bash
uv sync --frozen --extra web --extra dev
uv run pytest
uv run ruff check .
uv run mypy
```

Copy `.env.example` to `.env` only when running the deployment and Litestream
scripts; local analysis does not require those credentials.

Model profiles in `patterns/models/` are experimental heuristics, not verified
model fingerprints. Empirical calibration is planned for the evidence-backed
v0.5 milestone.

## Benchmarking

Versioned labeled manifests and the evaluation workflow live in [`benchmarks/`](benchmarks/README.md).
Raw corpus text and generated reports remain local and ignored. Run the CI smoke benchmark with:

```bash
uv run aidar benchmark run tests/fixtures/benchmark/manifest.yaml --split holdout
```

The report keeps human, fully generated, and materially edited text distinct and includes
fixed-seed confidence intervals for binary threshold metrics.

Corpus discovery and scan quality rules are documented in
[`docs/INGESTION.md`](docs/INGESTION.md), including structured failure reasons and the
non-destructive `aidar audit-corpus` command.

Historical imports can fill a missing publication date with
`aidar analyze --published-date YYYY-MM-DD`; publisher-provided metadata always
wins and the override is validated strictly. Exports include a schema version,
score vectors, pattern evidence, and publication metadata. The web leaderboard
supports `label`, `page`, and `limit` query parameters, the JSON API returns
pagination metadata, and `/feed.xml` exposes a bounded feed of recent scans.
See [`docs/CORPUS_OPERATIONS.md`](docs/CORPUS_OPERATIONS.md) for resumable
backfill, export, and date-precedence details.
Container and read-only replica setup is documented in
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).
