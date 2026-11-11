from __future__ import annotations

from aidar.models.config import AGGREGATION_MODES, ClusterParams
from aidar.models.result import PatternResult, ScoreVector
from aidar.patterns.registry import PatternRegistry

CATEGORIES = ("tropes", "punctuation", "phrases", "structure", "emoji", "vocabulary")


class Analyzer:
    def __init__(
        self,
        registry: PatternRegistry,
        aggregation: str = "mean",
        cluster: ClusterParams | None = None,
    ) -> None:
        if aggregation not in AGGREGATION_MODES:
            raise ValueError(f"aggregation must be one of {AGGREGATION_MODES}, got {aggregation!r}")
        self.registry = registry
        self.aggregation = aggregation
        self.cluster = cluster or ClusterParams()

    def run(self, text: str, word_count: int, raw_html: str | None = None) -> ScoreVector:
        """Run all patterns against text, aggregate into ScoreVector."""
        results: list[PatternResult] = []

        for pattern in self.registry.all_patterns():
            try:
                detector = self.registry.get_detector(pattern.id)
                result = detector.detect(text, word_count, raw_html=raw_html)
                results.append(result)
            except Exception:
                # Skip failed patterns rather than crashing the whole analysis
                pass

        return self._aggregate(results)

    def _aggregate(self, results: list[PatternResult]) -> ScoreVector:
        if self.aggregation == "noisy_or":
            return self._noisy_or(results)
        if self.aggregation == "mean_plus_cluster":
            return self._mean_plus_cluster(results)
        return self._weighted_mean(results)

    def _weighted_mean(self, results: list[PatternResult]) -> ScoreVector:
        """Compute weighted mean per category from pattern results.

        Zero-firing patterns count in the denominator, so adding a
        rarely-firing pattern lowers every document's category score.
        Kept as the default because thresholds were calibrated for it.
        """
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

        return self._score_vector(weighted_mean, results)

    def _noisy_or(self, results: list[PatternResult]) -> ScoreVector:
        """Weighted noisy-OR per category.

        Treats each pattern as an independent cause firing the category's
        signal with probability p_i = normalized_score * pattern_weight:

            category = 1 - product_i (1 - p_i)

        Union semantics: a never-firing pattern contributes a factor of 1
        (no change), a single strong hit scores p, and each additional
        co-occurring hit pushes the category further toward 1, saturating.
        Matches the sources' guidance that tells matter in combination.
        """
        survivor: dict[str, float] = {}

        for r in results:
            p = min(1.0, max(0.0, r.normalized_score)) * r.weight
            survivor[r.category] = survivor.get(r.category, 1.0) * (1.0 - p)

        return self._score_vector(lambda cat: 1.0 - survivor.get(cat, 1.0), results)

    def _mean_plus_cluster(self, results: list[PatternResult]) -> ScoreVector:
        """Weighted mean over FIRING patterns, plus a saturating cluster bonus.

        category = weighted_mean(firing patterns) + scale * min(1, fires / k)

        where fires counts distinct patterns with normalized_score >= the
        firing threshold. The mean runs over firing patterns only so that a
        never-firing pattern changes nothing (the plain weighted mean would
        dilute); the bonus is capped at `scale` once `k` patterns fire.
        One strong hit scores near its own normalized score; several
        co-occurring weaker hits add the cluster bonus on top.
        """
        c = self.cluster
        sums: dict[str, float] = {}
        weights: dict[str, float] = {}
        firing: dict[str, set[str]] = {}

        for r in results:
            if r.normalized_score > 0:
                sums[r.category] = sums.get(r.category, 0.0) + r.normalized_score * r.weight
                weights[r.category] = weights.get(r.category, 0.0) + r.weight
            if r.normalized_score >= c.firing_threshold:
                firing.setdefault(r.category, set()).add(r.pattern_id)

        def mean_plus_cluster(cat: str) -> float:
            total_weight = weights.get(cat, 0.0)
            mean = sums.get(cat, 0.0) / total_weight if total_weight else 0.0
            bonus = c.scale * min(1.0, len(firing.get(cat, ())) / c.k)
            return min(1.0, mean + bonus)

        return self._score_vector(mean_plus_cluster, results)

    @staticmethod
    def _score_vector(fn, results: list[PatternResult]) -> ScoreVector:
        return ScoreVector(
            **{cat: fn(cat) for cat in CATEGORIES},
            pattern_results=results,
        )
