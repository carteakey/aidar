from __future__ import annotations

import re

from aidar.models.pattern import PatternDef
from aidar.models.result import PatternResult
from aidar.patterns.detectors.base import BaseDetector


class RegexDetector(BaseDetector):
    """Counts regex pattern matches, normalized per N words."""

    def __init__(self, pattern: PatternDef) -> None:
        super().__init__(pattern)
        raw_patterns = pattern.params.get("patterns", [])
        self._compiled = [
            re.compile(re.escape(p) if len(p) <= 3 else p, re.IGNORECASE | re.UNICODE)
            for p in raw_patterns
        ]

    def detect(self, text: str, word_count: int) -> PatternResult:
        per_n = int(self.pattern.params.get("per_n_words", 1000))
        total_matches = sum(len(r.findall(text)) for r in self._compiled)
        raw = (total_matches / max(word_count, 1)) * per_n
        return self._make_result(raw, f"{raw:.1f} per {per_n} words")
