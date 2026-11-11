from __future__ import annotations

import re

from aidar.models.pattern import PatternDef
from aidar.models.result import PatternResult
from aidar.patterns.detectors.base import BaseDetector


class FrequencyDetector(BaseDetector):
    """Counts phrase matches, normalized per N words.

    match_mode:
      - "word_boundary" (default): each term is matched as whole words
        (\\b-anchored regex, case-insensitive), so 'utilize' no longer fires
        inside 'utilized' or 'thus' inside 'enthusiasts'.
      - "contains": legacy substring scan — keep only for term lists that
        intentionally match fragments (emoji, punctuation). No current pattern
        uses it.
      - "exact": legacy alias for word_boundary. The old implementation only
        counted a term surrounded by spaces, so 'delve.' or '(delve)' or a
        term at a line edge never matched.
    """

    def __init__(self, pattern: PatternDef) -> None:
        super().__init__(pattern)
        self._terms: list[str] = [str(t).lower() for t in pattern.params.get("terms", [])]
        mode = str(pattern.params.get("match_mode", "word_boundary")).lower()
        if mode == "exact":
            mode = "word_boundary"
        if mode not in ("word_boundary", "contains"):
            raise ValueError(
                f"Unknown match_mode {mode!r} for pattern {pattern.id}; "
                "expected word_boundary or contains"
            )
        self._match_mode = mode
        self._word_res = [
            re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE | re.UNICODE)
            for t in self._terms
        ]

    def detect(self, text: str, word_count: int, raw_html: str | None = None) -> PatternResult:
        per_n = int(self.pattern.params.get("per_n_words", 1000))
        if self._match_mode == "contains":
            text_lower = text.lower()
            total = sum(text_lower.count(term) for term in self._terms)
        else:
            total = sum(len(r.findall(text)) for r in self._word_res)

        raw = (total / max(word_count, 1)) * per_n
        return self._make_result(raw, f"{raw:.2f} per {per_n} words ({total} matches)")
