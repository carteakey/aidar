from __future__ import annotations

import hashlib
import json
import random
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from aidar.benchmark.manifest import BenchmarkManifest, Sample
from aidar.benchmark.materialize import verify_materialized
from aidar.core.analyzer import Analyzer
from aidar.core.scorer import compute_aggregate
from aidar.models.config import AppConfig


def _rate_interval(
    rows: list[dict[str, Any]],
    metric: Callable[[list[dict[str, Any]]], float | None],
    seed: int,
    iterations: int,
) -> dict[str, float] | None:
    point = metric(rows)
    if point is None:
        return None
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(iterations):
        sampled = [rows[rng.randrange(len(rows))] for _ in rows]
        value = metric(sampled)
        if value is not None:
            estimates.append(value)
    estimates.sort()
    if not estimates:
        return {"value": round(point, 4), "low": round(point, 4), "high": round(point, 4)}
    low = estimates[int(0.025 * (len(estimates) - 1))]
    high = estimates[int(0.975 * (len(estimates) - 1))]
    return {"value": round(point, 4), "low": round(low, 4), "high": round(high, 4)}


def _binary_metrics(rows: list[dict[str, Any]], seed: int, iterations: int) -> dict[str, Any]:
    binary = [row for row in rows if row["label"] in {"human", "ai_generated"}]

    def precision(items: list[dict[str, Any]]) -> float | None:
        predicted = [row for row in items if row["predicted_ai"]]
        return None if not predicted else sum(row["label"] == "ai_generated" for row in predicted) / len(predicted)

    def recall(items: list[dict[str, Any]]) -> float | None:
        positive = [row for row in items if row["label"] == "ai_generated"]
        return None if not positive else sum(row["predicted_ai"] for row in positive) / len(positive)

    def false_positive_rate(items: list[dict[str, Any]]) -> float | None:
        negative = [row for row in items if row["label"] == "human"]
        return None if not negative else sum(row["predicted_ai"] for row in negative) / len(negative)

    return {
        "n": len(binary),
        "precision": _rate_interval(binary, precision, seed, iterations),
        "recall": _rate_interval(binary, recall, seed + 1, iterations),
        "false_positive_rate": _rate_interval(binary, false_positive_rate, seed + 2, iterations),
    }


def _distribution(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 4),
        "median": round(statistics.median(values), 4),
        "min": round(ordered[0], 4),
        "max": round(ordered[-1], 4),
    }


def _segments(sample: Sample) -> dict[str, str]:
    result = {"topic": sample.topic, "language": sample.language, "publisher": sample.publisher}
    result.update(sample.segments)
    model_family = sample.provenance.get("model_family")
    if model_family:
        result["model_family"] = str(model_family)
    return result


def _temporal_summary(
    rows: list[dict[str, Any]], config: AppConfig, seed: int, iterations: int
) -> dict[str, Any]:
    """Summarize score cohorts by publication year without causal claims."""
    cohorts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        published_at = row.get("published_at")
        if not published_at:
            continue
        try:
            year = date.fromisoformat(str(published_at)[:10]).year
        except ValueError:
            continue
        cohorts[str(year)].append(row)
    min_samples = 2
    included = {
        year: _group_summary(items, config, seed, iterations)
        for year, items in sorted(cohorts.items())
        if len(items) >= min_samples
    }
    excluded = {
        year: len(items)
        for year, items in sorted(cohorts.items())
        if len(items) < min_samples
    }
    return {
        "group_by": "publication_year",
        "min_samples": min_samples,
        "included": included,
        "excluded_small_groups": excluded,
        "note": "Observational cohorts; differences do not establish causality.",
    }


def _calibration_bands(
    rows: list[dict[str, Any]], config: AppConfig
) -> dict[str, dict[str, int]]:
    bands: dict[str, Counter[str]] = {
        "likely_human": Counter(),
        "uncertain": Counter(),
        "likely_ai": Counter(),
    }
    for row in rows:
        if row["score"] <= config.likely_human_threshold:
            band = "likely_human"
        elif row["score"] >= config.likely_ai_threshold:
            band = "likely_ai"
        else:
            band = "uncertain"
        bands[band][row["label"]] += 1
    return {band: dict(sorted(counts.items())) for band, counts in bands.items()}


def _group_summary(
    rows: list[dict[str, Any]], config: AppConfig, seed: int, iterations: int
) -> dict[str, Any]:
    by_label: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_label[row["label"]].append(row["score"])
    return {
        "sample_counts": dict(sorted(Counter(row["label"] for row in rows).items())),
        "score_distributions": {
            label: _distribution(values) for label, values in sorted(by_label.items())
        },
        "binary_metrics": _binary_metrics(rows, seed, iterations),
        "calibration_bands": _calibration_bands(rows, config),
    }


def evaluate(
    manifest: BenchmarkManifest,
    data_dir: Path,
    analyzer: Analyzer,
    config: AppConfig,
    *,
    split: str = "holdout",
    seed: int = 1729,
    bootstrap_iterations: int = 1000,
) -> dict[str, Any]:
    paths = verify_materialized(manifest, data_dir)
    selected = [sample for sample in manifest.samples if split == "all" or sample.split == split]
    if not selected:
        raise ValueError(f"manifest has no samples for split: {split}")

    rows: list[dict[str, Any]] = []
    for sample in selected:
        text = paths[sample.id].read_text(encoding="utf-8")
        word_count = len(text.split())
        vector = analyzer.run(text, word_count)
        result = compute_aggregate(vector, config, word_count=word_count)
        rows.append(
            {
                "id": sample.id,
                "label": sample.label,
                "split": sample.split,
                "topic": sample.topic,
                "language": sample.language,
                "published_at": sample.published_at,
                "provenance": sample.provenance,
                "score": result.aggregate_score,
                "prediction": result.label,
                "predicted_ai": result.aggregate_score >= config.likely_ai_threshold,
                "segments": _segments(sample),
                "patterns": {item.pattern_id: item.normalized_score for item in vector.pattern_results},
            }
        )

    by_label: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_label[row["label"]].append(row["score"])

    segment_rows: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        for dimension, value in row["segments"].items():
            segment_rows[dimension][value].append(row)
    segment_analysis = {
        dimension: {
            value: _group_summary(items, config, seed, bootstrap_iterations)
            for value, items in sorted(groups.items())
        }
        for dimension, groups in sorted(segment_rows.items())
    }

    pattern_values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        for pattern_id, score in row["patterns"].items():
            pattern_values[pattern_id][row["label"]].append(score)
    per_pattern = {
        pattern_id: {
            label: _distribution(values)
            for label, values in sorted(label_values.items())
        }
        for pattern_id, label_values in sorted(pattern_values.items())
    }

    pattern_fingerprint = hashlib.sha256(
        "\n".join(
            f"{pattern.id}:{pattern.version}:{pattern.fingerprint()}"
            for pattern in sorted(analyzer.registry.all_patterns(), key=lambda item: item.id)
        ).encode()
    ).hexdigest()
    return {
        "schema_version": 1,
        "benchmark": {"id": manifest.id, "version": manifest.version, "split": split},
        "scorer": {
            "likely_human_threshold": config.likely_human_threshold,
            "likely_ai_threshold": config.likely_ai_threshold,
            "weights": config.weights.as_dict(),
            "pattern_fingerprint": pattern_fingerprint,
        },
        "bootstrap": {"method": "percentile", "confidence": 0.95, "iterations": bootstrap_iterations, "seed": seed},
        "sample_counts": dict(sorted(Counter(row["label"] for row in rows).items())),
        "score_distributions": {label: _distribution(values) for label, values in sorted(by_label.items())},
        "binary_metrics": _binary_metrics(rows, seed, bootstrap_iterations),
        "segment_analysis": segment_analysis,
        "temporal_analysis": _temporal_summary(rows, config, seed, bootstrap_iterations),
        "calibration_bands": _calibration_bands(rows, config),
        "per_pattern_distributions": per_pattern,
        "samples": rows,
    }


def recommend_calibration(
    report: dict[str, Any],
    analyzer: Analyzer,
    config: AppConfig,
    *,
    false_positive_budget: float = 0.05,
) -> dict[str, Any]:
    """Recommend thresholds/weights from a validation-only benchmark report.

    This function never mutates the active config and intentionally consumes a
    report generated for one split. Callers should pass ``split=validation``;
    the returned metadata makes that basis explicit.
    """
    if not 0.0 <= false_positive_budget <= 1.0:
        raise ValueError("false_positive_budget must be between 0 and 1")
    if report.get("benchmark", {}).get("split") != "validation":
        raise ValueError("calibration recommendations require the validation split")
    samples = [row for row in report.get("samples", []) if row.get("label") in {"human", "ai_generated"}]
    human = [int(row["score"]) for row in samples if row["label"] == "human"]
    ai = [int(row["score"]) for row in samples if row["label"] == "ai_generated"]
    if not human or not ai:
        raise ValueError("validation split needs both human and ai_generated samples")

    candidates = sorted({0, 100, *[int(row["score"]) for row in samples]})
    best: tuple[float, float, int, int] | None = None
    for threshold in candidates:
        predicted = [score >= threshold for score in (int(row["score"]) for row in samples)]
        positives = [row for row, flag in zip(samples, predicted, strict=True) if flag]
        true_positives = sum(row["label"] == "ai_generated" for row in positives)
        false_positives = sum(row["label"] == "human" for row in positives)
        false_negatives = sum(
            row["label"] == "ai_generated" and not flag
            for row, flag in zip(samples, predicted, strict=True)
        )
        precision = true_positives / max(len(positives), 1)
        recall = true_positives / max(len(ai), 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-9)
        fpr = false_positives / max(len(human), 1)
        if fpr <= false_positive_budget:
            candidate = (f1, -fpr, -threshold, false_negatives)
            if best is None or candidate > best:
                best = candidate
    if best is None:
        # A budget below the empirical resolution still gets a safe threshold.
        threshold = max(human) + 1
        threshold = min(threshold, 100)
    else:
        threshold = -int(best[2])

    category_values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    pattern_categories = {
        pattern.id: pattern.category for pattern in analyzer.registry.all_patterns()
    }
    for row in samples:
        for pattern_id, value in row.get("patterns", {}).items():
            category = pattern_categories.get(pattern_id)
            if category:
                category_values[category][row["label"]].append(float(value))
    separation: dict[str, float] = {}
    for category, values in category_values.items():
        human_values = values.get("human", [])
        ai_values = values.get("ai_generated", [])
        if human_values and ai_values:
            separation[category] = round(abs(statistics.fmean(ai_values) - statistics.fmean(human_values)), 4)
    total = sum(separation.values())
    recommended_weights = (
        {category: round(value / total, 4) for category, value in sorted(separation.items())}
        if total
        else config.weights.as_dict()
    )
    # Keep rounding from making the sum drift; adjust the largest category.
    if recommended_weights:
        drift = round(1.0 - sum(recommended_weights.values()), 4)
        largest = max(recommended_weights, key=lambda category: recommended_weights[category])
        recommended_weights[largest] = max(
            0.0, round(recommended_weights[largest] + drift, 4)
        )
    return {
        "basis": {
            "split": "validation",
            "false_positive_budget": false_positive_budget,
            "sample_counts": report.get("sample_counts", {}),
            "holdout_used": False,
        },
        "current": {
            "likely_human_threshold": config.likely_human_threshold,
            "likely_ai_threshold": config.likely_ai_threshold,
            "weights": config.weights.as_dict(),
        },
        "recommended": {
            "likely_human_threshold": min(max(human), threshold - 1),
            "likely_ai_threshold": threshold,
            "weights": recommended_weights,
        },
        "category_separation": separation,
    }


def write_report(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    metrics = report["binary_metrics"]
    lines = [
        f"# {report['benchmark']['id']} {report['benchmark']['version']}",
        "",
        f"Split: `{report['benchmark']['split']}`",
        "",
        "## Sample counts",
        "",
        *[f"- `{label}`: {count}" for label, count in report["sample_counts"].items()],
        "",
        "## Binary metrics",
        "",
        "Human is the negative class; fully AI-generated is the positive class. Mixed samples are excluded.",
        "",
    ]
    for name in ("precision", "recall", "false_positive_rate"):
        interval = metrics[name]
        value = "n/a" if interval is None else f"{interval['value']:.3f} [{interval['low']:.3f}, {interval['high']:.3f}]"
        lines.append(f"- `{name}`: {value}")
    temporal = report.get("temporal_analysis", {})
    lines.extend(["", "## Temporal cohorts", ""])
    lines.append(
        f"Publication-year cohorts require at least {temporal.get('min_samples', 2)} samples; "
        "observational differences do not establish causality."
    )
    for year, summary in temporal.get("included", {}).items():
        distribution = summary.get("score_distributions", {})
        means = ", ".join(
            f"{label}={values.get('mean', 'n/a')}" for label, values in distribution.items()
        )
        lines.append(f"- `{year}`: {means or 'n/a'}")
    for year, count in temporal.get("excluded_small_groups", {}).items():
        lines.append(f"- `{year}`: excluded ({count} sample; below minimum)")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path
