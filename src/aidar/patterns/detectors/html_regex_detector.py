from __future__ import annotations

import re

from aidar.models.pattern import PatternDef
from aidar.models.result import PatternResult
from aidar.patterns.detectors.base import BaseDetector


class HTMLRegexDetector(BaseDetector):
    """
    Regex detector that runs against raw HTML source when available, falling
    back to plain text otherwise (e.g. for --text input or .md files).
    Patterns should be written for HTML; they will simply produce no matches
    against plain text if raw_html is not available.
    """

    def __init__(self, pattern: PatternDef) -> None:
        super().__init__(pattern)
        raw_patterns = pattern.params.get("patterns", [])
        # DOTALL so . matches newlines (needed for multi-line HTML tags like SVG)
        self._compiled = [
            re.compile(p, re.IGNORECASE | re.UNICODE | re.DOTALL)
            for p in raw_patterns
        ]
        # Optional plain-text fallback patterns (e.g. markdown ** syntax)
        fallback_patterns = pattern.params.get("text_patterns", [])
        self._text_compiled = [
            re.compile(p, re.IGNORECASE | re.UNICODE | re.MULTILINE)
            for p in fallback_patterns
        ]

    def detect(self, text: str, word_count: int, raw_html: str | None = None) -> PatternResult:
        per_n = int(self.pattern.params.get("per_n_words", 1000))

        if raw_html is not None:
            total = sum(len(r.findall(raw_html)) for r in self._compiled)
        else:
            # Fallback: run text_patterns against plain text (covers markdown files)
            total = sum(len(r.findall(text)) for r in self._text_compiled)

        raw = (total / max(word_count, 1)) * per_n
        return self._make_result(raw, f"{raw:.1f} per {per_n} words")
