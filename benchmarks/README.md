# Aidar benchmarks

Benchmark manifests are committed; fetched and licensed text is not. Materialization copies or
extracts each sample into `.benchmark-data/<benchmark-id>/<version>/` and records a checksum lock
there. Both `.benchmark-data/` and generated `benchmark-reports/` are ignored by Git.

## Core benchmark

`aidar-core-v1/manifest.yaml` fixes the first validation and holdout membership. It includes
human-authored web material from gwern.net and simonwillison.net, generated samples selected from
RAID, and materially edited samples kept as a separate provenance class. Dataset-derived text must
be placed in `.benchmark-inputs/aidar-core-v1/` using the filenames in the manifest. Do not infer a
label from writing style: each file must be exported from the named dataset record or produced by
the recorded editing protocol.

The RAID selectors in the manifest are the selection contract. Download RAID's non-adversarial
training CSV, then stream the selected `generation` fields into the ignored input directory. RAID
is not vendored because its complete corpus is large and has its own distribution terms.

```bash
uv run aidar benchmark import-raid benchmarks/aidar-core-v1/manifest.yaml /path/to/train_none.csv
```

Then run:

```bash
uv run aidar benchmark validate benchmarks/aidar-core-v1/manifest.yaml
uv run aidar benchmark run benchmarks/aidar-core-v1/manifest.yaml --split holdout
```

Use the validation split to generate non-mutating calibration recommendations:

```bash
uv run aidar --output json benchmark calibrate benchmarks/aidar-core-v1/manifest.yaml \
  --output calibration.json
```

The command records its false-positive budget, category separation, and current
configuration. It never edits `_weights.yaml`; review recommendations before
applying a versioned scorer change, and keep holdout results for final reporting.

Use `--refresh` when intentionally refetching web pages. A refreshed URL may produce a new checksum
because publishers can edit pages; retain the local lock with the report so an evaluation can be
audited. Use `--no-materialize` to require the existing checksummed corpus.

## Reports

The JSON report records scorer thresholds, category weights, a pattern-set fingerprint, sample
counts, provenance-class score distributions, per-pattern distributions, fixed-seed percentile
bootstrap intervals, segment metrics, calibration bands, and sample-level results. Precision,
recall, and false-positive rate use only `human` and `ai_generated`; `mixed` is reported separately.
Segment metrics include topic and language. Publication-year cohorts require at least two samples,
list smaller groups as excluded, and explicitly avoid causal claims about temporal drift.

`tests/fixtures/benchmark/manifest.yaml` is a deliberately artificial smoke corpus for CI. Its
labels test the harness only and are not evidence about real model behavior.
