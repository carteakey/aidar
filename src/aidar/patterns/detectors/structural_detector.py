from __future__ import annotations

import re
import statistics

from aidar.models.result import PatternResult
from aidar.patterns.detectors.base import BaseDetector

# Bullet markers: -, *, •, ·, ◦, ▪, ▸, ►, ✓, ✗, numbered list (1. 2. etc)
_BULLET_RE = re.compile(r"^\s*(?:[-*•·◦▪▸►✓✗]|\d+[.)]\s)\s*\S", re.MULTILINE)
_HEADER_RE = re.compile(r"^#{1,6}\s+\S", re.MULTILINE)

# Unicode emoji ranges (simplified but covers common blocks)
_EMOJI_RE = re.compile(
    "["
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f300-\U0001f5ff"  # symbols & pictographs
    "\U0001f680-\U0001f6ff"  # transport & map
    "\U0001f1e0-\U0001f1ff"  # flags
    "\U00002702-\U000027b0"
    "\U000024c2-\U0001f251"
    "]+",
    flags=re.UNICODE,
)


class StructuralDetector(BaseDetector):
    """Analyzes document-level structural shape metrics."""

    def detect(self, text: str, word_count: int, raw_html: str | None = None) -> PatternResult:
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
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            return self._make_result(0.0, "0.0% bullet lines")
        bullet_lines = len(_BULLET_RE.findall(text))
        ratio = bullet_lines / len(lines)
        return self._make_result(ratio, f"{ratio:.1%} bullet lines")

    def _header_ratio(self, text: str, word_count: int) -> PatternResult:
        headers = len(_HEADER_RE.findall(text))
        ratio = headers / max(word_count, 1)
        return self._make_result(ratio, f"{headers} headers ({ratio * 1000:.1f} per 1000 words)")

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
        return self._make_result(ratio, f"{emoji_count} emojis ({ratio * 1000:.2f} per 1000 chars)")
