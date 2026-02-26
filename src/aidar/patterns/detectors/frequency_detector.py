from __future__ import annotations

from aidar.models.pattern import PatternDef
from aidar.models.result import PatternResult
from aidar.patterns.detectors.base import BaseDetector


class FrequencyDetector(BaseDetector):
    """Counts exact/substring phrase matches, normalized per N words."""

    def __init__(self, pattern: PatternDef) -> None:
        super().__init__(pattern)
        self._terms: list[str] = [t.lower() for t in pattern.params.get("terms", [])]
        self._match_mode: str = pattern.params.get("match_mode", "contains")

    def detect(self, text: str, word_count: int) -> PatternResult:
        per_n = int(self.pattern.params.get("per_n_words", 1000))
        text_lower = text.lower()
        total = 0

        for term in self._terms:
            if self._match_mode == "exact":
                # Match whole words only
                count = text_lower.count(f" {term} ") + (
                    1 if text_lower.startswith(term + " ") else 0
                )
            else:
                # contains — substring match
                count = text_lower.count(term)
            total += count

        raw = (total / max(word_count, 1)) * per_n
        return self._make_result(raw, f"{raw:.2f} per {per_n} words ({total} matches)")
