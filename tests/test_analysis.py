from __future__ import annotations

from pathlib import Path

import pytest

from aidar.core.analyzer import Analyzer
from aidar.core.scorer import compute_aggregate
from aidar.models.config import AppConfig, WeightConfig
from aidar.models.result import PatternResult
from aidar.patterns.loader import load_patterns, load_weight_config
from aidar.patterns.registry import PatternRegistry


def test_analyzer_aggregate_preserves_pattern_weights() -> None:
    analyzer = Analyzer.__new__(Analyzer)
    results = [
        PatternResult("light", "phrases", 1.0, 0.2, 0.2, "hit"),
        PatternResult("strong", "phrases", 1.0, 1.0, 0.8, "hit"),
        PatternResult("disabled", "phrases", 1.0, 1.0, 0.0, "hit"),
    ]

    assert analyzer._aggregate(results).phrases == pytest.approx(0.84)


def test_repository_patterns_load_and_score() -> None:
    patterns_dir = Path("patterns")
    patterns = load_patterns(patterns_dir)
    registry = PatternRegistry(patterns)
    config = AppConfig(
        patterns_dir=str(patterns_dir),
        weights=load_weight_config(patterns_dir),
    )
    text = (
        "It is not merely a tool, but a platform. Not because it is easy, but because it is useful."
    )

    vector = Analyzer(registry).run(text, len(text.split()))
    result = compute_aggregate(vector, config, word_count=len(text.split()))

    assert patterns
    assert result.aggregate_score >= 0
    assert any(item.pattern_id == "negative_parallelism" for item in vector.pattern_results)


def test_default_weights_are_valid() -> None:
    WeightConfig().validate()
