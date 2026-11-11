# Pattern Catalog and Tuning Log

This is the canonical inventory of all scoring patterns in `aidar`.
Use it to tune thresholds/weights and track why changes were made.

The sections between the GENERATED markers are refreshed by
`aidar patterns catalog --write` — edit the pattern YAMLs, not that block.

## Tuning Workflow

1. Pick one pattern to adjust.
2. Run it against at least one known-human and one known-AI sample.
3. Update `threshold_low` / `threshold_high` (and `version` if detection logic or thresholds changed).
4. Record the change in the tuning log below.
5. Re-run batch scans and compare score drift before/after.

<!-- BEGIN GENERATED: pattern catalog — regenerate with: aidar patterns catalog --write -->

## Category Weights

| Category | Weight |
|---|---:|
| emoji | 0.05 |
| phrases | 0.2 |
| punctuation | 0.15 |
| structure | 0.1 |
| tropes | 0.4 |
| vocabulary | 0.1 |

Source: [`patterns/_weights.yaml`](../patterns/_weights.yaml)

## Aggregate Labels

| Label | Aggregate score |
|---|---|
| LIKELY HUMAN | 0 – 15 |
| UNCERTAIN | 16 – 29 |
| LIKELY AI | 30 – 100 |

## Pattern Inventory

| Category | Pattern ID | Type | Match Mode | Weight | Version | Severity | `threshold_low` | `threshold_high` | Sources | References | File |
|---|---|---|---|---:|---:|---|---:|---:|---|---|---|
| emoji | `emoji_density` | structural | — | 0.7 | 1 | medium | 0.001 | 0.015 | — | — | [`patterns/emoji/emoji_density.yaml`](../patterns/emoji/emoji_density.yaml) |
| phrases | `ai_idioms` | frequency | word_boundary | 0.85 | 2 | high | 2 | 15 | arxiv-delve-lexical-overrepresentation, declauding, humanizer, wikipedia-signs-of-ai-writing | <https://arxiv.org/abs/2412.11385>, <https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing>, <https://github.com/blader/humanizer>, <https://github.com/oaustegard/claude-skills/tree/main/declauding> | [`patterns/phrases/ai_idioms.yaml`](../patterns/phrases/ai_idioms.yaml) |
| phrases | `challenges_future_template` | frequency | word_boundary | 0.68 | 2 | medium | 0.8 | 7 | wikipedia-signs-of-ai-writing | <https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing> | [`patterns/phrases/challenges_future_template.yaml`](../patterns/phrases/challenges_future_template.yaml) |
| phrases | `filler_openers` | frequency | word_boundary | 0.75 | 3 | high | 1 | 8 | — | — | [`patterns/phrases/filler_openers.yaml`](../patterns/phrases/filler_openers.yaml) |
| phrases | `hedging_phrases` | frequency | word_boundary | 0.9 | 3 | high | 1.5 | 12 | declauding, humanizer | <https://github.com/blader/humanizer>, <https://github.com/oaustegard/claude-skills/tree/main/declauding> | [`patterns/phrases/hedging.yaml`](../patterns/phrases/hedging.yaml) |
| phrases | `llm_markup_artifacts` | regex | — | 0.92 | 1 | high | 0.01 | 0.2 | wikipedia-signs-of-ai-writing | <https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing> | [`patterns/phrases/llm_markup_artifacts.yaml`](../patterns/phrases/llm_markup_artifacts.yaml) |
| phrases | `llm_placeholder_tokens` | regex | — | 0.88 | 1 | high | 0.01 | 0.25 | wikipedia-signs-of-ai-writing | <https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing> | [`patterns/phrases/llm_placeholder_tokens.yaml`](../patterns/phrases/llm_placeholder_tokens.yaml) |
| phrases | `llm_reference_artifacts` | regex | — | 0.95 | 1 | high | 0.01 | 0.2 | wikipedia-signs-of-ai-writing | <https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing> | [`patterns/phrases/llm_reference_artifacts.yaml`](../patterns/phrases/llm_reference_artifacts.yaml) |
| phrases | `llm_tracking_parameters` | regex | — | 0.9 | 1 | high | 0.01 | 0.15 | wikipedia-signs-of-ai-writing | <https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing> | [`patterns/phrases/llm_tracking_parameters.yaml`](../patterns/phrases/llm_tracking_parameters.yaml) |
| phrases | `notability_media_overattribution` | frequency | word_boundary | 0.76 | 2 | medium | 1.5 | 11 | wikipedia-signs-of-ai-writing | <https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing> | [`patterns/phrases/notability_media_overattribution.yaml`](../patterns/phrases/notability_media_overattribution.yaml) |
| phrases | `second_person_address` | frequency | word_boundary | 0.7 | 3 | medium | 1 | 8 | — | — | [`patterns/phrases/second_person_address.yaml`](../patterns/phrases/second_person_address.yaml) |
| phrases | `transition_overload` | frequency | word_boundary | 0.35 | 2 | low | 1 | 6 | humanizer, wikipedia-signs-of-ai-writing | <https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing>, <https://github.com/blader/humanizer> | [`patterns/phrases/transition_overload.yaml`](../patterns/phrases/transition_overload.yaml) |
| punctuation | `ellipsis_overuse` | regex | — | 0.4 | 1 | low | 1 | 6 | — | — | [`patterns/punctuation/ellipsis.yaml`](../patterns/punctuation/ellipsis.yaml) |
| punctuation | `em_dash_overuse` | regex | — | 0.85 | 1 | high | 2 | 10 | marginalia-hn-em-dash | <https://www.marginalia.nu/weird-ai-crap/hn/> | [`patterns/punctuation/em_dash.yaml`](../patterns/punctuation/em_dash.yaml) |
| punctuation | `semicolon_overuse` | regex | — | 0.3 | 1 | low | 2 | 8 | — | — | [`patterns/punctuation/semicolons.yaml`](../patterns/punctuation/semicolons.yaml) |
| structure | `bullet_point_density` | structural | — | 0.75 | 1 | medium | 0.1 | 0.45 | — | — | [`patterns/structure/bullet_density.yaml`](../patterns/structure/bullet_density.yaml) |
| structure | `header_frequency` | structural | — | 0.6 | 1 | medium | 0.003 | 0.015 | — | — | [`patterns/structure/header_frequency.yaml`](../patterns/structure/header_frequency.yaml) |
| structure | `paragraph_uniformity` | structural | — | 0.5 | 1 | low | 0.2 | 0.8 | — | — | [`patterns/structure/paragraph_uniformity.yaml`](../patterns/structure/paragraph_uniformity.yaml) |
| structure | `question_avoidance` | linguistic | — | 0.2 | 2 | low | 0 | 0.08 | — | — | [`patterns/structure/question_avoidance.yaml`](../patterns/structure/question_avoidance.yaml) |
| structure | `sentence_burstiness` | linguistic | — | 0.65 | 2 | medium | 0.2 | 0.7 | gptzero-burstiness | <https://gptzero.me/faq> | [`patterns/structure/sentence_burstiness.yaml`](../patterns/structure/sentence_burstiness.yaml) |
| tropes | `ai_section_headers` | html_regex | — | 0.85 | 1 | high | 0.5 | 4 | tropes-fyi, wikipedia-signs-of-ai-writing | <https://tropes.fyi/directory>, <https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing> | [`patterns/tropes/ai_section_headers.yaml`](../patterns/tropes/ai_section_headers.yaml) |
| tropes | `ai_writing_tropes` | frequency | contains | 0.95 | 4 | high | 1 | 12 | tropes-fyi | <https://tropes.fyi/directory> | [`patterns/tropes/ai_writing_tropes.yaml`](../patterns/tropes/ai_writing_tropes.yaml) |
| tropes | `aphoristic_closer` | regex | — | 0.2 | 1 | low | 0.3 | 1.5 | declauding | <https://github.com/oaustegard/claude-skills/tree/main/declauding> | [`patterns/tropes/aphoristic_closer.yaml`](../patterns/tropes/aphoristic_closer.yaml) |
| tropes | `bold_first_bullets` | html_regex | — | 0.85 | 2 | high | 1 | 8 | tropes-fyi | <https://tropes.fyi/directory> | [`patterns/tropes/bold_first_bullets.yaml`](../patterns/tropes/bold_first_bullets.yaml) |
| tropes | `compulsive_counting` | regex | — | 0.4 | 1 | medium | 0.3 | 2 | tropes-fyi | <https://tropes.fyi/directory> | [`patterns/tropes/compulsive_counting.yaml`](../patterns/tropes/compulsive_counting.yaml) |
| tropes | `juridical_register` | regex | — | 0.2 | 1 | low | 0.3 | 1.5 | declauding | <https://github.com/oaustegard/claude-skills/tree/main/declauding> | [`patterns/tropes/juridical_register.yaml`](../patterns/tropes/juridical_register.yaml) |
| tropes | `listicle_trenchcoat` | regex | — | 0.4 | 1 | medium | 0.3 | 2 | tropes-fyi | <https://tropes.fyi/directory> | [`patterns/tropes/listicle_trenchcoat.yaml`](../patterns/tropes/listicle_trenchcoat.yaml) |
| tropes | `negative_parallelism` | regex | — | 0.9 | 2 | high | 0.5 | 5 | declauding, humanizer, tropes-fyi | <https://tropes.fyi>, <https://github.com/blader/humanizer>, <https://github.com/oaustegard/claude-skills/tree/main/declauding> | [`patterns/tropes/negative_parallelism.yaml`](../patterns/tropes/negative_parallelism.yaml) |
| tropes | `negative_parallelism_plain` | regex | — | 0.3 | 1 | low | 2 | 8 | humanizer, tropes-fyi | <https://tropes.fyi>, <https://github.com/blader/humanizer> | [`patterns/tropes/negative_parallelism_plain.yaml`](../patterns/tropes/negative_parallelism_plain.yaml) |
| tropes | `retroactive_significance` | regex | — | 0.2 | 1 | low | 0.3 | 1.5 | declauding | <https://github.com/oaustegard/claude-skills/tree/main/declauding> | [`patterns/tropes/retroactive_significance.yaml`](../patterns/tropes/retroactive_significance.yaml) |
| tropes | `rhetorical_qa` | regex | — | 0.4 | 1 | medium | 0.3 | 1.5 | tropes-fyi | <https://tropes.fyi/directory> | [`patterns/tropes/rhetorical_qa.yaml`](../patterns/tropes/rhetorical_qa.yaml) |
| tropes | `self_grading` | regex | — | 0.2 | 1 | low | 0.3 | 1.5 | declauding | <https://github.com/oaustegard/claude-skills/tree/main/declauding> | [`patterns/tropes/self_grading.yaml`](../patterns/tropes/self_grading.yaml) |
| tropes | `short_punchy_fragments` | regex | — | 0.8 | 2 | medium | 1.5 | 8 | tropes-fyi | <https://tropes.fyi/directory> | [`patterns/tropes/short_punchy_fragments.yaml`](../patterns/tropes/short_punchy_fragments.yaml) |
| tropes | `signposted_conclusion` | regex | — | 0.35 | 1 | low | 0.3 | 1.5 | tropes-fyi | <https://tropes.fyi/directory> | [`patterns/tropes/signposted_conclusion.yaml`](../patterns/tropes/signposted_conclusion.yaml) |
| tropes | `spec_ese` | regex | — | 0.2 | 1 | low | 0.3 | 1.5 | declauding | <https://github.com/oaustegard/claude-skills/tree/main/declauding> | [`patterns/tropes/spec_ese.yaml`](../patterns/tropes/spec_ese.yaml) |
| tropes | `tricolon_abuse` | regex | — | 0.8 | 1 | medium | 0.5 | 4 | tropes-fyi | <https://tropes.fyi/directory> | [`patterns/tropes/tricolon_abuse.yaml`](../patterns/tropes/tricolon_abuse.yaml) |
| tropes | `unicode_arrows` | regex | — | 0.6 | 1 | medium | 0.2 | 1.5 | tropes-fyi | <https://tropes.fyi/directory> | [`patterns/tropes/unicode_arrows.yaml`](../patterns/tropes/unicode_arrows.yaml) |
| tropes | `verification_provenance` | regex | — | 0.2 | 1 | low | 0.3 | 1.5 | declauding | <https://github.com/oaustegard/claude-skills/tree/main/declauding> | [`patterns/tropes/verification_provenance.yaml`](../patterns/tropes/verification_provenance.yaml) |
| vocabulary | `ai_word_choice_tropes` | frequency | word_boundary | 0.8 | 3 | high | 1 | 10 | tropes-fyi | <https://tropes.fyi/directory> | [`patterns/vocabulary/ai_word_choice_tropes.yaml`](../patterns/vocabulary/ai_word_choice_tropes.yaml) |
| vocabulary | `formal_register` | frequency | word_boundary | 0.65 | 2 | medium | 2 | 10 | — | — | [`patterns/vocabulary/formal_register.yaml`](../patterns/vocabulary/formal_register.yaml) |
| vocabulary | `rare_word_density` | frequency | word_boundary | 0.55 | 2 | medium | 1.5 | 8 | — | — | [`patterns/vocabulary/rare_word_density.yaml`](../patterns/vocabulary/rare_word_density.yaml) |
| vocabulary | `type_token_ratio` | linguistic | — | 0.7 | 1 | medium | 0.15 | 0.55 | mattr-lexical-diversity | <https://doi.org/10.1016/j.rmal.2024.100168> | [`patterns/vocabulary/type_token_ratio.yaml`](../patterns/vocabulary/type_token_ratio.yaml) |
| vocabulary | `word_freq_variance` | linguistic | — | 0.8 | 1 | medium | 0.7 | 1.25 | arxiv-detectgpt, wordfreq | <https://arxiv.org/abs/2301.11305>, <https://github.com/rspeer/wordfreq> | [`patterns/vocabulary/word_freq_variance.yaml`](../patterns/vocabulary/word_freq_variance.yaml) |

Thresholds are per-1000-words rates for `frequency`/`regex` patterns and raw metric values for `structural`/`linguistic` patterns. `match_mode` applies to `frequency` patterns only (`contains` unless the YAML says otherwise).

<!-- END GENERATED: pattern catalog -->

## Tuning Log

Add one row per pattern change.

| Date | Pattern ID | Change | Why | Evidence Sample(s) | Expected Impact | Done By |
|---|---|---|---|---|---|---|
| 2026-03-08 | `llm_reference_artifacts` | Added pattern (v1) | Capture high-precision LLM artifact tokens | Wikipedia AI-sign indicators | Increase precision on copy/paste AI output | codex |

