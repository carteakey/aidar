# TODO

Speculative ideas and research notes only. Committed work is tracked in the
[Aidar Linear project](https://linear.app/carteakey/project/aidar-8a949b456d2b).

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
- [ ] **Per-topic baseline** — tech blogs naturally score higher on formal vocab; normalization

## Data & Backfill

- [ ] **Historical backfill** — for sites with archives, scan old posts by published_date to build time series
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
- [ ] **RSS feed** — `/feed.xml` of recently scanned sites
- [ ] **Pagination** on leaderboard (currently top 100)
- [ ] **Filter by label** — show only LIKELY AI / UNCERTAIN / LIKELY HUMAN
- [ ] **Mobile layout** — currently readable but not optimized

## Tooling

- [ ] **`aidar export`** — dump DB to JSON/CSV for external analysis
- [ ] **`aidar backfill`** — re-scan a domain's full history without skip-existing
- [ ] **`aidar diff <domain> <date1> <date2>`** — compare a domain's score between two scan dates
- [ ] **Docker image** — `docker run carteakey/aidar track medium.com --save`

## Deployment

- [ ] **Fly.io persistent volume** — recommended over Heroku for SQLite persistence
- [ ] **Read-only web replica** — separate the scan worker from the web server

## Research

- [ ] **Temporal drift** — do the same sites score higher over time? Track it.
