from __future__ import annotations

import hashlib
import json
import random
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable
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
    result = {"topic": sample.topic, "publisher": sample.publisher}
    result.update(sample.segments)
    model_family = sample.provenance.get("model_family")
    if model_family:
        result["model_family"] = str(model_family)
    return result


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
        "calibration_bands": _calibration_bands(rows, config),
        "per_pattern_distributions": per_pattern,
        "samples": [{key: value for key, value in row.items() if key != "patterns"} for row in rows],
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
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path
