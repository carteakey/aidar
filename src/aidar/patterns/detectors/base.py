from __future__ import annotations

from abc import ABC, abstractmethod

from aidar.models.pattern import PatternDef
from aidar.models.result import PatternResult


class BaseDetector(ABC):
    """All pattern detectors implement this interface."""

    def __init__(self, pattern: PatternDef) -> None:
        self.pattern = pattern

    @abstractmethod
    def detect(self, text: str, word_count: int) -> PatternResult:
        """
        Run detection against `text`.
        `word_count` is pre-computed to avoid re-counting per detector.
        Returns a PatternResult with raw_value and normalized_score filled.
        """
        ...

    def _normalize(self, raw: float) -> float:
        """Linear min-max clamp using threshold_low / threshold_high from params."""
        t_low = float(self.pattern.params["threshold_low"])
        t_high = float(self.pattern.params["threshold_high"])
        if raw <= t_low:
            return 0.0
        if raw >= t_high:
            return 1.0
        return (raw - t_low) / (t_high - t_low)

    def _make_result(self, raw: float, label: str) -> PatternResult:
        return PatternResult(
            pattern_id=self.pattern.id,
            category=self.pattern.category,
            raw_value=raw,
            normalized_score=self._normalize(raw),
            weight=self.pattern.weight,
            label=label,
        )
