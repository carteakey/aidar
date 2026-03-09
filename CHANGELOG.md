# Changelog

All notable changes to the aidar pattern repository and tooling.

Format: `[version] — date — description`
Pattern version bumps are noted separately from tool version bumps.

---

## Tool Changes

### [0.4.0] — 2026-03-09
- **`html_regex` detection type**: new `HTMLRegexDetector` runs patterns against raw HTML source, with a `text_patterns` fallback for plain-text/markdown input. Enables detection of structural HTML signals (bold-first list items) that trafilatura strips from extracted text.
- **`FetchResult.raw_html`**: fetcher now stores original HTML response; threaded through `Analyzer.run()` to all detectors.
- **`aidar analyze --text TEXT`**: new option to analyze raw text directly without a URL or file path.
- **`aidar discover` — relative sitemap fix**: added `_sitemap_direct()` fallback that fetches and parses `sitemap.xml` directly when trafilatura's `sitemap_search` returns empty (trafilatura silently drops relative `<loc>` entries). Discovery now works on sites like carteakey.dev that use root-relative sitemap paths.
- **`PatternDef`**: `html_regex` added to valid detection types.

### [0.3.0] — 2026-03-09
- **Tropes Category**: Added `tropes` as the primary detection category with a leading weight of 0.40.
- **Regex Detectors**: Support for Regex-based pattern matching in `PatternRegistry`.
- **Scoring Engine**: Redistributed category weights to prioritize human-discernible writing tropes.

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

### [bold_first_bullets v2] — 2026-03-09
Migrated to `html_regex` detection type. Now runs against raw HTML source, detecting `<li>...<strong>` patterns (including icon-prefixed bullets common in AI-generated docs). Falls back to markdown `**` syntax detection for plain-text input.

### [short_punchy_fragments v1] — 2026-03-09
New pattern. Regex detector for standalone single-word emphasis sentences ("Openly." "Devastating."), short prepositional fragments used as sentences, and 3+ consecutive very short sentences — the manufactured staccato rhythm of RLHF-optimized "readability".

### [tricolon_abuse v1] — 2026-03-09
New pattern. Regex detector for overuse of rule-of-three structures: three semicolon-joined parallel clauses, comma-separated noun-phrase triplets ending with "and", and the "not just X, not just Y, not just Z" negation tricolon.

### [ai_writing_tropes v3] — 2026-03-09
Major expansion: 209 terms across 17 structural/tonal/compositional tropes. New sections added: Negative Parallelism, Em-Dash Addiction (`—`), Unicode Decoration (`→`), Gerund Fragment Litany. Existing sections significantly expanded. Word-choice tropes (Delve, Tapestry, Quietly, Serves As) kept exclusively in `vocabulary/`. Reference updated to `https://tropes.fyi/directory`.

### [ai_word_choice_tropes v2] — 2026-03-09
Major expansion: 123 terms across four word-choice trope families. New sections added: *"Delve" and Friends* (delve, certainly, utilize, leverage, robust, streamline, harness, cutting-edge, seamlessly, actionable insights, holistic approach, etc.) and *"Tapestry" and "Landscape"* (tapestry, landscape, paradigm shift, synergy, ecosystem, cornerstone, bedrock, at the forefront of, at the intersection of, etc.).

### [negative_parallelism v1] — 2026-03-09
New pattern. Regex-based detector capturing "It's not X — it's Y" and "not because X, but because Y" sentence reframes.

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
