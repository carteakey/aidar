from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PatternResult:
    pattern_id: str
    category: str
    raw_value: float
    normalized_score: float
    weight: float
    label: str


@dataclass
class ScoreVector:
    punctuation: float = 0.0
    phrases: float = 0.0
    structure: float = 0.0
    emoji: float = 0.0
    vocabulary: float = 0.0
    pattern_results: list[PatternResult] = field(default_factory=list)

    def as_dict(self) -> dict[str, float]:
        return {
            "punctuation": self.punctuation,
            "phrases": self.phrases,
            "structure": self.structure,
            "emoji": self.emoji,
            "vocabulary": self.vocabulary,
        }

    def results_by_category(self, category: str) -> list[PatternResult]:
        return [r for r in self.pattern_results if r.category == category]


@dataclass
class AggregateResult:
    url: str | None
    file_path: str | None
    word_count: int
    score_vector: ScoreVector
    aggregate_score: int
    label: str
    scanned_at: datetime = field(default_factory=datetime.utcnow)
    model_match: dict[str, float] | None = None

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "file_path": self.file_path,
            "word_count": self.word_count,
            "aggregate_score": self.aggregate_score,
            "label": self.label,
            "scanned_at": self.scanned_at.isoformat(),
            "score_vector": self.score_vector.as_dict(),
            "pattern_results": [
                {
                    "pattern_id": r.pattern_id,
                    "category": r.category,
                    "raw_value": r.raw_value,
                    "normalized_score": r.normalized_score,
                    "label": r.label,
                }
                for r in self.score_vector.pattern_results
            ],
            "model_match": self.model_match,
        }
