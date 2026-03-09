# TODO

Roughly prioritized. Open an issue to claim something.

## Next Up

Quick single-session items:

- [ ] **Filter by label** on leaderboard — show only LIKELY AI / UNCERTAIN / LIKELY HUMAN
- [ ] **Pagination** on leaderboard — currently capped at top 100 domains
- [ ] **Public API docs page** — document `/api/leaderboard`, `/api/domain/<domain>` endpoints
- [ ] **`aidar export`** — dump DB to JSON/CSV for external analysis
- [ ] **List intro phrases** pattern — "Here are X ways to...", "The following Y things..." (frequency type, easy add)
- [ ] **Passive voice density** pattern — AI overuses passive constructions (regex, frequency type)
- [ ] **First-person pronoun rate** pattern — AI rarely uses "I" unless system-prompted (frequency type)

Medium effort (2–3 sessions):

- [ ] **Pattern explainer pages** — `/patterns/<pattern_id>` with description, example matches, threshold calibration, historical avg score trend
- [ ] **GitHub Actions template** — weekly cron workflow to track a list of domains; reusable for forks
- [ ] **Historical backfill** — for sites with archives, scan old posts by `published_date` to build time series
- [ ] **Exclamation point rate** pattern — AI avoids them in formal contexts; overuses in "friendly" mode
- [ ] **Repetition detector** pattern — same sentence rephrased within 3 paragraphs
- [ ] **Named entity sparsity** pattern — AI avoids specific names, dates, places unless prompted

Larger efforts:

- [ ] **Perplexity scoring** — real LLM perplexity via GPT-2 (`pip install aidar[nlp]`)
- [ ] **Dead Metaphor detector** — one metaphor repeated 5–10× across a piece; requires NLP/embedding similarity
- [ ] **One-Point Dilution detector** — single argument restated many ways; requires semantic repetition across paragraphs
- [ ] **Establish human baseline corpus** — scan 1000+ known-human pages to calibrate thresholds properly
- [ ] **Wayback Machine integration** — retrieve historical snapshots for pre-AI-era baseline comparison

---

## Patterns

- [ ] **List intro phrases** — "Here are X ways to...", "The following Y things..."
- [ ] **Passive voice density** — AI overuses passive constructions
- [ ] **First-person pronoun rate** — AI rarely uses "I" unless system-prompted to
- [ ] **Exclamation point rate** — AI avoids them in formal contexts; overuses in "friendly" mode
- [ ] **Repetition detector** — same sentence rephrased within 3 paragraphs
- [ ] **Named entity sparsity** — AI avoids specific names, dates, places unless prompted
- [ ] **Vocabulary mismatch** — sudden register shift mid-document (partial AI edit signal)
- [ ] **Content Duplication detector** — verbatim repeated paragraphs within the same piece; requires paragraph-level fingerprinting/hashing
- [ ] **Dead Metaphor detector** — latching onto one metaphor and repeating it 5–10× across a piece; requires tracking metaphor reuse semantically (NLP/embedding similarity)
- [ ] **One-Point Dilution detector** — single argument restated in 10 different ways across thousands of words; requires semantic repetition detection across paragraphs
- [ ] **Perplexity scoring** — real LLM perplexity via GPT-2 (`pip install aidar[nlp]`)
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
- [x] Embed badge — `/badge/<domain>` SVG badge for embedding in READMEs
- [x] Domain delete (admin key protected, `AIDAR_ADMIN_KEY`)
- [ ] **Pattern explainer pages** — `/patterns/<pattern_id>` with description, example matches, threshold calibration, and historical avg score trend
- [ ] **Public API docs page** — `/api/leaderboard`, `/api/domain/<domain>`
- [ ] **RSS feed** — `/feed.xml` of recently scanned sites
- [ ] **Pagination** on leaderboard (currently top 100)
- [ ] **Filter by label** — show only LIKELY AI / UNCERTAIN / LIKELY HUMAN
- [ ] **Mobile layout** — currently readable but not optimized

## Tooling

- [ ] **`aidar export`** — dump DB to JSON/CSV for external analysis
- [ ] **`aidar backfill`** — re-scan a domain's full history without skip-existing
- [ ] **`aidar diff <domain> <date1> <date2>`** — compare a domain's score between two scan dates
- [ ] **GitHub Actions template** — weekly cron to track a list of domains
- [ ] **Docker image** — `docker run carteakey/aidar track medium.com --save`

## Deployment

- [ ] **Fly.io persistent volume** — recommended over Heroku for SQLite persistence
- [ ] **DB backup strategy** — periodic SQLite dump to S3/R2
- [ ] **Read-only web replica** — separate the scan worker from the web server

## Research

- [ ] **Establish human baseline corpus** — scan 1000+ known-human pages to calibrate thresholds properly
- [ ] **False positive audit** — ESL writers, technical docs, legal text all score high; document known FP categories
- [ ] **Temporal drift** — do the same sites score higher over time? Track it.
- [ ] **Per-model fingerprinting** — publish calibrated model profiles with methodology
