from __future__ import annotations

from aidar.models.result import AggregateResult


def rank_results(results: list[AggregateResult]) -> list[AggregateResult]:
    """Sort results by aggregate_score descending (most AI-like first)."""
    return sorted(results, key=lambda r: r.aggregate_score, reverse=True)


def delta_vector(a: AggregateResult, b: AggregateResult) -> dict[str, float]:
    """Per-category score differences (a - b). Positive = a is more AI-like."""
    a_vec = a.score_vector.as_dict()
    b_vec = b.score_vector.as_dict()
    return {cat: round(a_vec[cat] - b_vec[cat], 3) for cat in a_vec}
