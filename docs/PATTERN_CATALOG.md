# Pattern Catalog and Tuning Log

This is the canonical inventory of all scoring patterns in `aidar`.
Use it to tune thresholds/weights and track why changes were made.

Last refreshed: 2026-03-08

## Tuning Workflow

1. Pick one pattern to adjust.
2. Run it against at least one known-human and one known-AI sample.
3. Update `threshold_low` / `threshold_high` (and `version` if detection logic or thresholds changed).
4. Record the change in the tuning log below.
5. Re-run batch scans and compare score drift before/after.

## Category Weights

| Category | Weight |
|---|---:|
| phrases | 0.40 |
| punctuation | 0.20 |
| structure | 0.15 |
| vocabulary | 0.15 |
| emoji | 0.10 |

Source: [`patterns/_weights.yaml`](../patterns/_weights.yaml)

## Pattern Inventory

| Category | Pattern ID | Type | Weight | Version | `threshold_low` | `threshold_high` | Signal Set | File |
|---|---|---|---:|---:|---:|---:|---|---|
| emoji | `emoji_density` | structural | 0.70 | 1 | 0.001 | 0.015 | metric: `emoji_density` | [`patterns/emoji/emoji_density.yaml`](../patterns/emoji/emoji_density.yaml) |
| phrases | `ai_idioms` | frequency | 0.85 | 1 | 2.0 | 15.0 | 40 terms | [`patterns/phrases/ai_idioms.yaml`](../patterns/phrases/ai_idioms.yaml) |
| phrases | `challenges_future_template` | frequency | 0.68 | 1 | 0.8 | 7.0 | 10 terms | [`patterns/phrases/challenges_future_template.yaml`](../patterns/phrases/challenges_future_template.yaml) |
| phrases | `filler_openers` | frequency | 0.75 | 1 | 1.0 | 8.0 | 18 terms | [`patterns/phrases/filler_openers.yaml`](../patterns/phrases/filler_openers.yaml) |
| phrases | `hedging_phrases` | frequency | 0.90 | 2 | 1.5 | 12.0 | 33 terms | [`patterns/phrases/hedging.yaml`](../patterns/phrases/hedging.yaml) |
| phrases | `llm_markup_artifacts` | regex | 0.92 | 1 | 0.01 | 0.20 | 4 regex patterns | [`patterns/phrases/llm_markup_artifacts.yaml`](../patterns/phrases/llm_markup_artifacts.yaml) |
| phrases | `llm_placeholder_tokens` | regex | 0.88 | 1 | 0.01 | 0.25 | 6 regex patterns | [`patterns/phrases/llm_placeholder_tokens.yaml`](../patterns/phrases/llm_placeholder_tokens.yaml) |
| phrases | `llm_reference_artifacts` | regex | 0.95 | 1 | 0.01 | 0.20 | 7 regex patterns | [`patterns/phrases/llm_reference_artifacts.yaml`](../patterns/phrases/llm_reference_artifacts.yaml) |
| phrases | `llm_tracking_parameters` | regex | 0.90 | 1 | 0.01 | 0.15 | 2 regex patterns | [`patterns/phrases/llm_tracking_parameters.yaml`](../patterns/phrases/llm_tracking_parameters.yaml) |
| phrases | `notability_media_overattribution` | frequency | 0.76 | 1 | 1.5 | 11.0 | 18 terms | [`patterns/phrases/notability_media_overattribution.yaml`](../patterns/phrases/notability_media_overattribution.yaml) |
| phrases | `transition_overload` | frequency | 0.70 | 1 | 3.0 | 20.0 | 23 terms | [`patterns/phrases/transition_overload.yaml`](../patterns/phrases/transition_overload.yaml) |
| punctuation | `ellipsis_overuse` | regex | 0.40 | 1 | 1.0 | 6.0 | 2 regex patterns | [`patterns/punctuation/ellipsis.yaml`](../patterns/punctuation/ellipsis.yaml) |
| punctuation | `em_dash_overuse` | regex | 0.85 | 1 | 2.0 | 10.0 | 3 regex patterns | [`patterns/punctuation/em_dash.yaml`](../patterns/punctuation/em_dash.yaml) |
| punctuation | `semicolon_overuse` | regex | 0.30 | 1 | 2.0 | 8.0 | 1 regex pattern | [`patterns/punctuation/semicolons.yaml`](../patterns/punctuation/semicolons.yaml) |
| structure | `bullet_point_density` | structural | 0.75 | 1 | 0.1 | 0.45 | metric: `bullet_density` | [`patterns/structure/bullet_density.yaml`](../patterns/structure/bullet_density.yaml) |
| structure | `header_frequency` | structural | 0.60 | 1 | 0.003 | 0.015 | metric: `header_ratio` | [`patterns/structure/header_frequency.yaml`](../patterns/structure/header_frequency.yaml) |
| structure | `paragraph_uniformity` | structural | 0.50 | 1 | 0.2 | 0.8 | metric: `paragraph_cv_inverted` | [`patterns/structure/paragraph_uniformity.yaml`](../patterns/structure/paragraph_uniformity.yaml) |
| structure | `question_avoidance` | linguistic | 0.20 | 1 | 0.0 | 0.08 | metric: `question_rate` | [`patterns/structure/question_avoidance.yaml`](../patterns/structure/question_avoidance.yaml) |
| structure | `sentence_burstiness` | linguistic | 0.65 | 1 | 0.2 | 0.7 | metric: `sentence_burstiness` | [`patterns/structure/sentence_burstiness.yaml`](../patterns/structure/sentence_burstiness.yaml) |
| vocabulary | `formal_register` | frequency | 0.65 | 1 | 2.0 | 10.0 | 19 terms | [`patterns/vocabulary/formal_register.yaml`](../patterns/vocabulary/formal_register.yaml) |
| vocabulary | `rare_word_density` | frequency | 0.55 | 1 | 1.5 | 8.0 | 28 terms | [`patterns/vocabulary/rare_word_density.yaml`](../patterns/vocabulary/rare_word_density.yaml) |
| vocabulary | `type_token_ratio` | linguistic | 0.70 | 1 | 0.15 | 0.55 | metric: `type_token_ratio` | [`patterns/vocabulary/type_token_ratio.yaml`](../patterns/vocabulary/type_token_ratio.yaml) |
| vocabulary | `word_freq_variance` | linguistic | 0.80 | 1 | 0.7 | 1.25 | metric: `word_freq_variance` | [`patterns/vocabulary/word_freq_variance.yaml`](../patterns/vocabulary/word_freq_variance.yaml) |

## Tuning Log

Add one row per pattern change.

| Date | Pattern ID | Change | Why | Evidence Sample(s) | Expected Impact | Done By |
|---|---|---|---|---|---|---|
| 2026-03-08 | `llm_reference_artifacts` | Added pattern (v1) | Capture high-precision LLM artifact tokens | Wikipedia AI-sign indicators | Increase precision on copy/paste AI output | codex |

