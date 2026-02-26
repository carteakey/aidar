from __future__ import annotations

from aidar.models.config import AppConfig, WeightConfig
from aidar.models.result import AggregateResult, ScoreVector


def compute_aggregate(
    score_vector: ScoreVector,
    config: AppConfig,
    url: str | None = None,
    file_path: str | None = None,
    word_count: int = 0,
    published_date: str | None = None,
    title: str | None = None,
) -> AggregateResult:
    """Weighted sum of category scores → 0-100 aggregate with label."""
    weights = config.weights
    raw = (
        score_vector.punctuation * weights.punctuation
        + score_vector.phrases * weights.phrases
        + score_vector.structure * weights.structure
        + score_vector.emoji * weights.emoji
        + score_vector.vocabulary * weights.vocabulary
    )
    aggregate = round(raw * 100)
    aggregate = max(0, min(100, aggregate))

    if aggregate <= config.likely_human_threshold:
        label = "LIKELY HUMAN"
    elif aggregate >= config.likely_ai_threshold:
        label = "LIKELY AI"
    else:
        label = "UNCERTAIN"

    return AggregateResult(
        url=url,
        file_path=file_path,
        word_count=word_count,
        score_vector=score_vector,
        aggregate_score=aggregate,
        label=label,
        published_date=published_date,
        title=title,
    )


def compare_model_profile(
    score_vector: ScoreVector,
    model_profile: dict[str, float],
) -> dict[str, float]:
    """
    Compare actual pattern scores against a model's known profile.
    Returns per-pattern deviation + overall similarity score.
    """
    deviations: dict[str, float] = {}
    for pattern_id, expected in model_profile.items():
        actual_results = [
            r for r in score_vector.pattern_results if r.pattern_id == pattern_id
        ]
        if actual_results:
            actual = actual_results[0].normalized_score
            deviations[pattern_id] = abs(actual - expected)

    if deviations:
        similarity = 1.0 - (sum(deviations.values()) / len(deviations))
    else:
        similarity = 0.0

    return {"similarity": round(similarity, 3), **{k: round(v, 3) for k, v in deviations.items()}}
