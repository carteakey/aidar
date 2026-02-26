from __future__ import annotations

from aidar.models.pattern import PatternDef
from aidar.patterns.detectors.base import BaseDetector
from aidar.patterns.detectors.frequency_detector import FrequencyDetector
from aidar.patterns.detectors.regex_detector import RegexDetector
from aidar.patterns.detectors.structural_detector import StructuralDetector

_DETECTOR_MAP: dict[str, type[BaseDetector]] = {
    "regex": RegexDetector,
    "frequency": FrequencyDetector,
    "structural": StructuralDetector,
}


class PatternRegistry:
    def __init__(self, patterns: list[PatternDef]) -> None:
        self._patterns: dict[str, PatternDef] = {p.id: p for p in patterns}
        self._detectors: dict[str, BaseDetector] = {}

    def get_detector(self, pattern_id: str) -> BaseDetector:
        if pattern_id not in self._detectors:
            pattern = self._patterns[pattern_id]
            detector_cls = _DETECTOR_MAP.get(pattern.detection_type)
            if detector_cls is None:
                raise ValueError(
                    f"No detector implemented for detection_type '{pattern.detection_type}'"
                )
            self._detectors[pattern_id] = detector_cls(pattern)
        return self._detectors[pattern_id]

    def patterns_by_category(self) -> dict[str, list[PatternDef]]:
        result: dict[str, list[PatternDef]] = {}
        for pattern in self._patterns.values():
            result.setdefault(pattern.category, []).append(pattern)
        for cat in result:
            result[cat].sort(key=lambda p: p.weight, reverse=True)
        return result

    def all_patterns(self) -> list[PatternDef]:
        return list(self._patterns.values())

    def get_pattern(self, pattern_id: str) -> PatternDef | None:
        return self._patterns.get(pattern_id)
