# aidar

Track stylistic patterns across the web to surface AI-era writing trends.

aidar measures known stylistic signals — em dash frequency, hedging phrases, bullet density, AI vocabulary idioms, emoji usage — and aggregates them into a per-site index. The goal isn't to classify individual pages as "AI or not", it's to build a comparable, queryable dataset of how writing style is shifting across the web at scale.

Inspired by: [New accounts on Hacker News ten times more likely to use em-dashes](https://www.marginalia.nu/weird-ai-crap/hn/)

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

# Compare multiple pages side by side
aidar compare https://site1.com https://site2.com https://site3.com

# Bulk scan from a URL list, save to DB
aidar scan --batch urls.txt --concurrency 20 --save

# Inspect loaded signal patterns
aidar patterns list
aidar patterns show em_dash_overuse

# JSON output for downstream use
aidar --output json analyze https://example.com
```

## Signal categories

| Category    | Examples                                              |
|-------------|-------------------------------------------------------|
| phrases     | "delve into", "it's worth noting", "key takeaway"    |
| punctuation | em dash frequency, ellipsis overuse                   |
| structure   | bullet point density, header frequency               |
| vocabulary  | formal register words, rare/sophisticated vocabulary |
| emoji       | emoji density and placement                           |

## Pattern repository

Patterns live in `patterns/` as YAML files — no Python needed to add new signals. Model profiles in `patterns/models/` store known stylistic baselines for Claude, GPT-4, and Gemini for use with `--compare-model`.

## Leaderboard

Results stored with `--save` are queryable via `aidar.db`. The `db/queries.py` module exposes `get_leaderboard()`, `get_domain_stats()`, and `get_pattern_stats()` for building a web dashboard once you've accumulated enough scan data.
