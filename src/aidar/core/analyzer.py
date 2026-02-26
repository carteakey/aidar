from __future__ import annotations

from aidar.models.result import PatternResult, ScoreVector
from aidar.patterns.registry import PatternRegistry


class Analyzer:
    def __init__(self, registry: PatternRegistry) -> None:
        self.registry = registry

    def run(self, text: str, word_count: int) -> ScoreVector:
        """Run all patterns against text, aggregate into ScoreVector."""
        results: list[PatternResult] = []

        for pattern in self.registry.all_patterns():
            try:
                detector = self.registry.get_detector(pattern.id)
                result = detector.detect(text, word_count)
                results.append(result)
            except Exception:
                # Skip failed patterns rather than crashing the whole analysis
                pass

        return self._aggregate(results)

    def _aggregate(self, results: list[PatternResult]) -> ScoreVector:
        """Compute weighted mean per category from pattern results."""
        category_sums: dict[str, float] = {}
        category_weight_totals: dict[str, float] = {}

        for r in results:
            cat = r.category
            category_sums[cat] = category_sums.get(cat, 0.0) + r.normalized_score * r.weight
            category_weight_totals[cat] = category_weight_totals.get(cat, 0.0) + r.weight

        def weighted_mean(cat: str) -> float:
            total_weight = category_weight_totals.get(cat, 0.0)
            if total_weight == 0:
                return 0.0
            return category_sums.get(cat, 0.0) / total_weight

        return ScoreVector(
            punctuation=weighted_mean("punctuation"),
            phrases=weighted_mean("phrases"),
            structure=weighted_mean("structure"),
            emoji=weighted_mean("emoji"),
            vocabulary=weighted_mean("vocabulary"),
            pattern_results=results,
        )
