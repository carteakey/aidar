from __future__ import annotations

import re
import statistics

from aidar.models.pattern import PatternDef
from aidar.models.result import PatternResult
from aidar.patterns.detectors.base import BaseDetector

try:
    from wordfreq import zipf_frequency
    _WORDFREQ_AVAILABLE = True
except ImportError:
    _WORDFREQ_AVAILABLE = False

_CONTENT_WORD_RE = re.compile(r'\b[a-z]{4,}\b')

# Simple sentence splitter — handles ., !, ? followed by whitespace + capital
_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z"])')
# Question detection
_QUESTION_RE = re.compile(r'\?')
# Sentence-ending question
_QUESTION_SENTENCE_RE = re.compile(r'[^.!?]*\?')


def _split_sentences(text: str) -> list[str]:
    """Naive sentence splitter sufficient for pattern analysis."""
    sentences = _SENTENCE_RE.split(text.strip())
    return [s.strip() for s in sentences if s.strip() and len(s.split()) >= 2]


class LinguisticDetector(BaseDetector):
    """Analyzes linguistic properties: sentence burstiness, TTR, question rate, etc."""

    def detect(self, text: str, word_count: int) -> PatternResult:
        metric = self.pattern.params["metric"]

        if metric == "sentence_burstiness":
            return self._sentence_burstiness(text)
        elif metric == "type_token_ratio":
            return self._type_token_ratio(text, word_count)
        elif metric == "question_rate":
            return self._question_rate(text)
        elif metric == "avg_sentence_length":
            return self._avg_sentence_length(text)
        elif metric == "word_freq_variance":
            return self._word_freq_variance(text)
        else:
            raise ValueError(f"Unknown linguistic metric: {metric}")

    def _sentence_burstiness(self, text: str) -> PatternResult:
        """
        Coefficient of variation of sentence word counts.
        Low CV = uniform sentence lengths = AI-like.
        Score is INVERTED: low burstiness → high score.
        """
        sentences = _split_sentences(text)
        if len(sentences) < 4:
            return self._make_result(0.0, "too few sentences")

        lengths = [len(s.split()) for s in sentences]
        mean = statistics.mean(lengths)
        if mean == 0:
            return self._make_result(0.0, "empty sentences")

        stdev = statistics.stdev(lengths)
        cv = stdev / mean  # coefficient of variation

        # Invert: low CV (uniform) → high AI score
        inverted = max(0.0, 1.0 - cv)
        return self._make_result(inverted, f"CV={cv:.2f} (burstiness={1-inverted:.2f})")

    def _type_token_ratio(self, text: str, word_count: int) -> PatternResult:
        """
        Unique words / total words. Low TTR = repetitive = AI-like.
        Uses a sliding window (STTR) to control for text length.
        Score is INVERTED: low TTR → high score.
        """
        words = [w.lower().strip(".,!?;:\"'()[]") for w in text.split() if w.strip()]
        if len(words) < 50:
            return self._make_result(0.0, "too few words for TTR")

        # Standardized TTR: average TTR over 50-word windows
        window = 50
        ttrs = []
        for i in range(0, len(words) - window + 1, window // 2):
            chunk = words[i:i + window]
            ttrs.append(len(set(chunk)) / len(chunk))

        avg_ttr = statistics.mean(ttrs) if ttrs else len(set(words)) / len(words)

        # Invert: low TTR (repetitive) → high score
        inverted = max(0.0, 1.0 - avg_ttr)
        return self._make_result(inverted, f"STTR={avg_ttr:.3f}")

    def _question_rate(self, text: str) -> PatternResult:
        """
        Fraction of sentences ending with '?'. Near-zero in AI text.
        Score is INVERTED: low question rate → high AI score.

        Capped at `score_cap` (default 0.70) because 0% questions is common in
        human technical/tutorial writing — reserve the full 1.0 for when other
        signals also fire. Weight is intentionally low (0.20).
        """
        sentences = _split_sentences(text)
        if not sentences:
            return self._make_result(0.0, "no sentences")

        questions = sum(1 for s in sentences if s.rstrip().endswith("?"))
        rate = questions / len(sentences)

        # Invert: low question rate → high score
        inverted = max(0.0, 1.0 - (rate / max(self.pattern.params.get("threshold_high", 0.08), 0.001)))
        inverted = min(1.0, inverted)

        # Apply score cap — 0% questions is ambiguous for technical content
        cap = float(self.pattern.params.get("score_cap", 0.70))
        inverted = min(inverted, cap)

        return self._make_result(inverted, f"{questions}/{len(sentences)} sentences are questions ({rate:.1%})")

    def _avg_sentence_length(self, text: str) -> PatternResult:
        """
        Average sentence length in words. AI tends toward 18-25 word sentences.
        Very short or very long averages suggest human writing.
        """
        sentences = _split_sentences(text)
        if not sentences:
            return self._make_result(0.0, "no sentences")
        avg = statistics.mean(len(s.split()) for s in sentences)
        return self._make_result(avg, f"{avg:.1f} words/sentence avg")

    def _word_freq_variance(self, text: str) -> PatternResult:
        """
        Vocabulary predictability via word frequency standard deviation.
        Uses Zipf frequency scores (wordfreq library) for each content word.

        AI models produce text with a NARROW frequency distribution — they cluster
        in the mid-Zipf range (3–5), avoiding both very common stopwords and truly
        rare domain-specific terms. Human technical writing has higher variance: it
        mixes highly specialized rare words with everyday language.

        Score is INVERTED: low std_dev (narrow, predictable) → high AI score.
        Falls back gracefully if wordfreq is not installed.
        """
        if not _WORDFREQ_AVAILABLE:
            return PatternResult(
                pattern_id=self.pattern.id,
                category=self.pattern.category,
                raw_value=0.0,
                normalized_score=0.0,
                weight=self.pattern.weight,
                label="wordfreq not installed",
                pattern_version=self.pattern.version,
            )

        words = _CONTENT_WORD_RE.findall(text.lower())
        if len(words) < 30:
            return PatternResult(
                pattern_id=self.pattern.id,
                category=self.pattern.category,
                raw_value=0.0,
                normalized_score=0.0,
                weight=self.pattern.weight,
                label="too few content words",
                pattern_version=self.pattern.version,
            )

        freqs = [zipf_frequency(w, "en") for w in words]
        # Only include words known to the frequency list (zipf > 0)
        freqs = [f for f in freqs if f > 0]
        if len(freqs) < 20:
            return PatternResult(
                pattern_id=self.pattern.id,
                category=self.pattern.category,
                raw_value=0.0,
                normalized_score=0.0,
                weight=self.pattern.weight,
                label="too few known words",
                pattern_version=self.pattern.version,
            )

        std = statistics.stdev(freqs)

        # Invert: low std (narrow vocabulary) → high score (AI-like)
        # threshold_low = std below which score saturates at 1.0 (very predictable)
        # threshold_high = std above which score drops to 0.0 (very diverse = human)
        t_low = float(self.pattern.params.get("threshold_low", 0.70))
        t_high = float(self.pattern.params.get("threshold_high", 1.25))
        normalized = max(0.0, min(1.0, (t_high - std) / (t_high - t_low)))

        return PatternResult(
            pattern_id=self.pattern.id,
            category=self.pattern.category,
            raw_value=round(std, 4),
            normalized_score=normalized,
            weight=self.pattern.weight,
            label=f"Zipf std={std:.3f} over {len(freqs)} content words",
            pattern_version=self.pattern.version,
        )
