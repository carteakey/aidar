# Contributing to aidar

The pattern repository is the heart of the project. Anyone can contribute new signals, improve existing thresholds, or document known false positives — no Python required.

## How patterns work

Each pattern is a YAML file in `patterns/<category>/`. When you run `aidar scan`, every pattern runs against the extracted text and produces a normalized 0–1 score. Scores are aggregated per category, then into a final **Stylistic Index**.

## Adding a new pattern

1. **Pick the right category:**

   | Category      | What it captures |
   |---------------|-----------------|
   | `phrases/`    | Specific word/phrase clusters (hedging, AI idioms, transitions) |
   | `punctuation/`| Character-level overuse (em dashes, ellipses) |
   | `structure/`  | Document shape (bullet density, headers, sentence uniformity) |
   | `vocabulary/` | Word-level signals (formal register, lexical diversity) |
   | `emoji/`      | Emoji frequency and placement |

2. **Create the YAML file** (see template below)

3. **Calibrate thresholds** using real samples:
   - `threshold_low`: value at or below which the score is 0 (normal human usage)
   - `threshold_high`: value at or above which the score saturates to 1 (clearly AI-patterned)
   - The scoring is linear between the two. Aim for thresholds you can justify with examples.

4. **Test it:**
   ```bash
   aidar patterns show your_pattern_id
   aidar analyze /path/to/known_ai_text.txt --verbose
   aidar analyze /path/to/known_human_text.txt --verbose
   ```

5. **Open a PR.** Include in the PR description:
   - What triggered you to add this pattern (link to source, example text, etc.)
   - What threshold values you tested and why you chose them
   - Any known false-positive cases

---

## Pattern template

```yaml
id: your_pattern_id            # snake_case, unique across all patterns
name: Human-Readable Name
version: 1                     # start at 1; bump when thresholds or logic changes
description: >
  1–3 sentences explaining what this pattern detects and why it's
  associated with AI-era writing. Cite sources if you have them.
category: phrases              # phrases | punctuation | structure | vocabulary | emoji
weight: 0.70                   # 0.0–1.0, relative importance within the category
detection_type: frequency      # regex | frequency | structural | linguistic
severity: medium               # low | medium | high
references:
  - https://source-that-inspired-this.example.com
added_by: your-github-handle

params:
  # For frequency detection:
  terms:
    - "phrase one"
    - "phrase two"
  match_mode: contains         # exact | contains
  per_n_words: 1000
  threshold_low: 2.0
  threshold_high: 12.0

  # For regex detection:
  # patterns: ["regex1", "regex2"]
  # per_n_words: 1000
  # threshold_low: 1.0
  # threshold_high: 8.0

  # For structural detection:
  # metric: bullet_density | header_ratio | paragraph_cv_inverted | emoji_density
  # threshold_low: 0.10
  # threshold_high: 0.45

  # For linguistic detection:
  # metric: sentence_burstiness | type_token_ratio | question_rate | avg_sentence_length
  # threshold_low: 0.2
  # threshold_high: 0.7
```

---

## Bumping a pattern version

When you change **thresholds or detection logic** on an existing pattern, increment `version`:

```yaml
# Before
version: 1
params:
  threshold_low: 2.0
  threshold_high: 10.0

# After (thresholds recalibrated based on new data)
version: 2
params:
  threshold_low: 1.5
  threshold_high: 8.0
```

This flags old scans as stale. Users can then re-scan with:
```bash
aidar track <domain> --rescan-stale
aidar patterns versions  # see what's stale in your DB
```

**Don't bump the version** for:
- Fixing a typo in `description` or `name`
- Adding a `reference` URL
- Changing `weight` (this affects scoring but not detection)

---

## Improving thresholds

If you're seeing too many false positives or the pattern isn't firing on text you know is AI-generated, open an issue with:
- The text sample (or a representative excerpt)
- The raw value the pattern reported (`aidar analyze --verbose`)
- Your proposed threshold adjustment

Label: `threshold-calibration`

---

## Submitting known AI samples

The more calibration data, the better. If you have samples of known AI-generated content (from a specific model, context, or publication) that reveal new patterns:

1. Open an issue labeled `pattern-signal` with the sample and your observations
2. Or just open a PR adding a new pattern — the description should explain what you found

---

## GitHub issue labels

| Label | Use for |
|-------|---------|
| `new-pattern` | Proposing a new signal |
| `threshold-calibration` | Existing pattern firing too much or too little |
| `false-positive-report` | Pattern scoring high on text you believe is human |
| `pattern-signal` | Sharing sample text that reveals a new signal |
| `model-profile` | Updates to `patterns/models/*.yaml` baselines |

---

## What makes a good pattern

**Good:**
- Observable in the text without a language model (counts, ratios, structural)
- Has a clear human baseline you can cite or measure
- Fires differently on text you know is AI-generated vs human-written
- Has a plausible mechanism (why would a model do this?)

**Avoid:**
- Patterns that are too topic-specific (a tech blog will naturally use "leverage" more than a recipe site)
- Patterns requiring semantic understanding (those need NLP models — out of scope for now)
- Single-word lists that are too common to be meaningful
- Patterns that rely on recency ("AI writes like X right now" — models change)

---

## Perplexity and burstiness (advanced)

Real perplexity scoring requires a language model and is tracked in [#TODO issue]. If you want to experiment with this, the optional `nlp` dependency group is reserved for it:

```bash
pip install "aidar[nlp]"  # future
```

Current lightweight proxies already in the repo:
- `sentence_burstiness` — CV of sentence lengths
- `type_token_ratio` — standardized lexical diversity
- `question_avoidance` — fraction of interrogative sentences
