# Category aggregation: why the mean dilutes, and what to switch to

Status: proposal (T6). Nothing about scoring changed: `patterns/_weights.yaml`
still says `aggregation: mean`, and the thresholds below are untouched. The
other modes exist behind that switch so they can be measured and flipped
deliberately.

## The problem

`Analyzer._aggregate` (`src/aidar/core/analyzer.py`) scores each category as a
weighted mean over **all** patterns, zeros included:

    category = sum(score_i * w_i) / sum(w_i)

A pattern that never fires contributes `0` to the numerator and its full
weight to the denominator. Concretely: `tropes` currently has 7 patterns
(summed weight ≈ 5.3). A document where `tricolon_abuse` fires at 0.7 and
nothing else does scores `0.7 * 0.85 / 5.3 ≈ 0.11`. Add one more
rarely-firing pattern at weight 0.35 and the same document drops to
`0.7 * 0.85 / 5.65 ≈ 0.105` — **every** document in the corpus gets lower,
fired-on or not. T5 measured exactly this: 6 ported declauding patterns at
weight 0.35 cost -0.02 aggregate AUC until their weights were cut to 0.20.
The pattern set can only grow, so the mean guarantees the signal decays with
every addition.

## What the sources say

All three upstreams agree tells are evidence in combination, not alone
(`sources.yaml` ids in parentheses):

- humanizer: patterns that are "weak alone" need the company of other tells
  (`humanizer`).
- declauding: "look for clusters" of tells rather than single hits
  (`declauding`).
- tropes.fyi: "the problem is when multiple tropes appear together"
  (`tropes-fyi`).

The current mean implements the opposite of "together": co-occurring weak
hits average out against silent siblings, and more patterns make it worse.

## Requirements for a replacement

- **R1 zero-invariance** — adding a never-firing pattern changes no score.
  (The brief's non-negotiable; this is what lets the pattern set grow.)
- **R2 cluster semantics** — one tell means little; several co-occurring
  tells mean a lot (the sources' guidance).
- **R3** bounded 0..1, deterministic, cheap; default mode byte-identical to
  today's scores until switched on purpose.

## The three options

### 1. Weighted mean (current default)

    category = Σ score_i·w_i / Σ w_i        over all patterns

- **R1: FAILS** — the dilution above. This is the bug being tracked.
- **R2: weak** — a single strong hit is diluted by every silent sibling
  (0.7 → 0.11 above); a cluster of weak hits lands at the average of the
  hits, not above them.

### 2. Weighted noisy-OR (`aggregation: noisy_or`)

Treat each pattern as an independent cause firing the category's signal with
probability `p_i = score_i · w_i`:

    category = 1 − Π_i (1 − p_i)

- **R1: HOLDS.** A never-firing pattern has `p = 0`, its factor is 1, the
  product is unchanged. Proven by
  `test_adding_a_never_firing_pattern_changes_nothing`.
- **R2: HOLDS.** One strong hit scores exactly `p_i` (not divided by
  siblings). Each additional co-occurring hit multiplies the survivor term
  again, so the category saturates toward 1 — `test_noisy_or_co_occurring_weak_hits_outweigh_single_hits`
  shows three weak hits (0.20/0.22/0.25 at weight 0.9) score 0.61 together
  but < 0.23 each alone.
- **Caveat (honest):** patterns that fire *weakly but non-zero* on ordinary
  human prose (continuous detectors) also accumulate. This lifts the low end
  of the scale — human median on the fixture went 7 → 25. That is breadth
  semantics, aligned with the sources ("multiple tells together"), but it
  means thresholds must be recalibrated (below). AUC is threshold-free and
  still improved.

### 3. Firing mean + saturating cluster bonus (`aggregation: mean_plus_cluster`)

    category = weighted_mean(firing patterns) + scale · min(1, fires / k)

where `fires` counts distinct patterns with `score ≥ cluster.firing_threshold`
and the mean runs over **firing patterns only** (a mean over all patterns
would still dilute and fail R1; the firing restriction is what makes the
mode zero-invariant — that choice is visible in the implementation and
tested).

- **R1: HOLDS.** A never-firing pattern enters neither the firing mean nor
  the fire count. Proven by the same property test.
- **R2: HALF.** The cluster bonus rewards co-occurrence, but the firing mean
  alone is *very* generous to a single hit: one pattern at 0.6 in a
  7-pattern category scores ≈ 0.6 + scale/k instead of ≈ 0.11. Measured, that
  generosity drowned the two categories where human prose fires one or two
  patterns routinely (structure AUC 0.501 → 0.409, vocabulary 0.597 → 0.506).

## Property tests

`tests/test_aggregation.py` (10 tests):

- `test_adding_a_never_firing_pattern_changes_nothing` — R1 for both new
  modes, identical `ScoreVector` with and without a zero pattern.
- `test_plain_mean_does_dilute_documented_bug` — pins the fact that the
  current default lacks R1 (so the test suite can't silently pass if someone
  "simplifies" the new modes back to a plain mean).
- `test_noisy_or_co_occurring_weak_hits_outweigh_single_hits`,
  `test_noisy_or_saturates` — R2 for noisy-OR, with exact values.
- `test_mean_plus_cluster_single_strong_hit_scores_near_its_own_score`,
  `test_mean_plus_cluster_bonus_saturates` — firing-mean semantics and the
  exact saturation point of the bonus.
- `test_empty_results_are_all_zero_in_every_mode`,
  `test_unknown_mode_rejected`, `test_weights_config_roundtrip` — plumbing,
  including that `_weights.yaml` without the key loads `mean` and that an
  unknown mode is refused.

Full suite at time of writing: 55 passed.

## Measurements (single-author fixture — sanity check only)

Wave-2 caveat applies: this corpus is one author, humanizer-cleaned on the
ai-assisted side. It can veto, it cannot bless. Measured with
`aidar eval --from-frontmatter …` on `feat/aggregation` @ 7788975; the base
already includes the T1 extraction fix (merged in f92c11a), so structural
detectors see markdown here.

Integration pattern set (as merged through f92c11a):

| mode              | aggregate AUC | tropes | punct | phrases | structure | vocab | human gate (LH/34, median, max) | ai-assisted LH/18 |
|-------------------|---------------|--------|-------|---------|-----------|-------|---------------------------------|-------------------|
| mean              | 0.7507        | 0.784  | 0.618 | 0.430   | 0.501     | 0.597 | 30/34, 7, 20                    | 11                |
| noisy_or          | **0.7838**    | 0.796  | 0.618 | 0.426   | 0.475     | 0.593 | 12/34, 25, 52                   | 1                 |
| mean_plus_cluster | 0.7419        | 0.760  | 0.604 | 0.414   | 0.409     | 0.506 | 8/34, 25.5, 57                  | 2                 |

Same corpus after trial-merging T5's 11 new patterns
(`feat/new-patterns` @ f3ff01f, merged in a scratch clone under /tmp):

| mode              | aggregate AUC | tropes | phrases | structure | human gate (LH/34, median, max) | ai-assisted LH/18 |
|-------------------|---------------|--------|---------|-----------|---------------------------------|-------------------|
| mean              | 0.7471        | 0.806  | 0.400   | 0.501     | 33/34, 6, 16                    | 13                |
| noisy_or          | **0.7919**    | 0.807  | 0.396   | 0.475     | 12/34, 25, 52                   | 1                 |
| mean_plus_cluster | 0.7390        | 0.753  | 0.384   | 0.409     | 8/34, 25.5, 57                  | 2                 |

Readings:

1. **noisy_or wins on the threshold-free metric in both corpora** (+0.033,
   +0.045 aggregate AUC). tropes — the category the sources' guidance is
   about — also ticks up (0.784 → 0.796, 0.806 → 0.807).
2. **The dilution effect is visible with T5's patterns**: under mean, adding
   11 patterns *lowered* aggregate AUC (0.7507 → 0.7471) even though tropes
   AUC rose (0.784 → 0.806) — the new patterns' silent zeros taxed every
   other category. Under noisy_or the same merge *raised* aggregate AUC
   (0.7838 → 0.7919). Adding patterns can only add evidence once the mean is
   gone.
3. **mean_plus_cluster measured worst** (0.7419 / 0.7390). The firing mean's
   generosity to single hits hurt exactly where human prose fires a pattern
   or two routinely (structure, vocabulary). The cluster bonus it adds is
   the part worth keeping if this direction is revisited — as a bonus on
   top of noisy-OR rather than on top of a firing mean.
4. The LIKELY HUMAN counts collapse under the new modes **because of scale,
   not discrimination**: human median moves 7 → 25 while the ai-assisted
   median moves 12.5 → 43. The 15/30 cutoffs simply sit in the wrong place
   for the new scale.

## Threshold recalibration (required before any switch)

The `thresholds` in `_weights.yaml` (`likely_human_max: 15`,
`likely_ai_min: 30`) were calibrated against the mean's scale ("pure-human
blogs score 0-7, AI-assisted 10-22, heavy AI 25+", per the file's own
comment). Both new modes rescale category scores upward, so:

- **noisy_or**: human on the fixture spans 1–52 (median 25); ai-assisted
  median 43. An arithmetic midpoint would put LIKELY HUMAN around ~40, but
  that is illustrative only — the cutoff must come from the p90–p95 of a
  *multi-author* human corpus. This one-author fixture can only veto a
  cutoff that flags its human posts.
- **mean_plus_cluster**: human max 57 — same procedure, worse starting point.
- The CI regression gate (`eval --assert-max-score N`) needs the same move:
  worst human score is 20 (mean, integration set), 16 (mean, +T5), 52
  (noisy_or), 57 (mean_plus_cluster).
- Category weights (0.40/0.20/…) were tuned when every category spanned the
  same effective range. Under noisy_or, categories with many patterns
  saturate faster than sparse ones (emoji never saturates); the weights
  should be re-examined after the mode switch, against the sources' stated
  importance, not against this fixture.

## Recommendation

Resting on the property tests and the sources' reasoning (corpus numbers are
a sanity check, per the wave-2 rules):

1. **Adopt `noisy_or` as the target default.** It is the only option that
   satisfies R1 and R2 simultaneously, it matches all three sources' cluster
   guidance, and the fixture agrees (+0.033/+0.045 AUC, and it turns T5's
   pattern additions from a net negative into a net positive).
2. **Do not adopt `mean_plus_cluster`.** R1 holds but the firing mean is too
   generous to single hits (measured: structure/vocabulary AUC collapse).
3. **Sequence**: keep `mean` as default until thresholds and the CI gate are
   recalibrated on a multi-author human corpus; then flip the one-line
   `aggregation:` switch. No code change is needed to flip it.
