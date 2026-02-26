# TODO

Roughly prioritized. Open an issue to claim something.

## Patterns

- [ ] **Perplexity scoring** — real LLM perplexity via GPT-2 (`pip install aidar[nlp]`)
- [ ] **Passive voice density** — AI overuses passive constructions
- [ ] **Named entity sparsity** — AI avoids specific names, dates, places unless prompted
- [ ] **Exclamation point rate** — AI avoids them in formal contexts; overuses in "friendly" mode
- [ ] **First-person pronoun rate** — AI rarely uses "I" unless system-prompted to
- [ ] **Repetition detector** — same sentence rephrased within 3 paragraphs
- [ ] **Vocabulary mismatch** — sudden register shift mid-document (partial AI edit signal)
- [ ] **List intro phrases** — "Here are X ways to...", "The following Y things..."
- [ ] **Calibrate model profiles** — measure gpt4/gemini baselines empirically, not guessed
- [ ] **Per-topic baseline** — tech blogs naturally score higher on formal vocab; normalization

## Data & Backfill

- [ ] **Historical backfill** — for sites with archives, scan old posts by published_date to build time series
- [ ] **Scheduled tracking** — cron job / GitHub Actions workflow to auto-track domains weekly
- [ ] **Wayback Machine integration** — retrieve historical snapshots for pre-AI-era baseline comparison
- [ ] **Manual date override** — `aidar analyze --published-date 2023-06-01 <url>` for missing metadata

## Website (aidar.lol)

- [x] Leaderboard
- [x] Domain detail page
- [x] Patterns page
- [x] Submit / search site form
- [x] Domain trend chart (published_date time series)
- [ ] **Public API docs page** — `/api/leaderboard`, `/api/domain/<domain>`
- [ ] **RSS feed** — `/feed.xml` of recently scanned sites
- [ ] **Embed badge** — `![aidar score](https://aidar.lol/badge/carteakey.dev)` for sites to display
- [ ] **Pagination** on leaderboard (currently top 100)
- [ ] **Filter by label** — show only LIKELY AI / UNCERTAIN / LIKELY HUMAN
- [ ] **Mobile layout** — currently readable but not optimized

## Tooling

- [ ] **`aidar export`** — dump DB to JSON/CSV for external analysis
- [ ] **`aidar backfill`** — re-scan a domain's full history without skip-existing
- [ ] **`aidar diff <domain> <date1> <date2>`** — compare a domain's score between two scan dates
- [ ] **Docker image** — `docker run carteakey/aidar track medium.com --save`
- [ ] **GitHub Actions template** — weekly cron to track a list of domains

## Deployment

- [ ] **Fly.io persistent volume** — recommended over Heroku for SQLite persistence
- [ ] **DB backup strategy** — periodic SQLite dump to S3/R2
- [ ] **Read-only web replica** — separate the scan worker from the web server

## Research

- [ ] **Establish human baseline corpus** — scan 1000+ known-human pages to calibrate thresholds properly
- [ ] **False positive audit** — ESL writers, technical docs, legal text all score high; document known FP categories
- [ ] **Temporal drift** — do the same sites score higher over time? Track it.
- [ ] **Per-model fingerprinting** — publish calibrated model profiles with methodology
