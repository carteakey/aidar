from __future__ import annotations

import re
import statistics
import unicodedata

from aidar.models.pattern import PatternDef
from aidar.models.result import PatternResult
from aidar.patterns.detectors.base import BaseDetector

# Bullet markers: -, *, •, ·, ◦, ▪, ▸, ►, ✓, ✗, numbered list (1. 2. etc)
_BULLET_RE = re.compile(r"^\s*(?:[-*•·◦▪▸►✓✗]|\d+[.)]\s)\s*\S", re.MULTILINE)
_HEADER_RE = re.compile(r"^#{1,6}\s+\S", re.MULTILINE)

# Unicode emoji ranges (simplified but covers common blocks)
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)


class StructuralDetector(BaseDetector):
    """Analyzes document-level structural shape metrics."""

    def detect(self, text: str, word_count: int) -> PatternResult:
        metric = self.pattern.params["metric"]

        if metric == "bullet_density":
            return self._bullet_density(text)
        elif metric == "header_ratio":
            return self._header_ratio(text, word_count)
        elif metric == "paragraph_cv_inverted":
            return self._paragraph_uniformity(text)
        elif metric == "emoji_density":
            return self._emoji_density(text)
        else:
            raise ValueError(f"Unknown structural metric: {metric}")

    def _bullet_density(self, text: str) -> PatternResult:
        lines = [l for l in text.splitlines() if l.strip()]
        if not lines:
            return self._make_result(0.0, "0.0% bullet lines")
        bullet_lines = len(_BULLET_RE.findall(text))
        ratio = bullet_lines / len(lines)
        return self._make_result(ratio, f"{ratio:.1%} bullet lines")

    def _header_ratio(self, text: str, word_count: int) -> PatternResult:
        headers = len(_HEADER_RE.findall(text))
        ratio = headers / max(word_count, 1)
        return self._make_result(ratio, f"{headers} headers ({ratio*1000:.1f} per 1000 words)")

    def _paragraph_uniformity(self, text: str) -> PatternResult:
        # Split on blank lines to get paragraphs
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if len(paragraphs) < 3:
            return self._make_result(0.0, "too few paragraphs to measure")
        lengths = [len(p.split()) for p in paragraphs]
        mean = statistics.mean(lengths)
        if mean == 0:
            return self._make_result(0.0, "empty paragraphs")
        stdev = statistics.stdev(lengths)
        cv = stdev / mean  # coefficient of variation
        # Invert: low CV (uniform) → high score
        inverted = 1.0 - min(cv, 1.0)
        raw = inverted
        return self._make_result(raw, f"CV={cv:.2f} (uniformity={inverted:.2f})")

    def _emoji_density(self, text: str) -> PatternResult:
        char_count = max(len(text), 1)
        emoji_count = len(_EMOJI_RE.findall(text))
        ratio = emoji_count / char_count
        return self._make_result(ratio, f"{emoji_count} emojis ({ratio*1000:.2f} per 1000 chars)")
