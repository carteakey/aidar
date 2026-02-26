from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WeightConfig:
    punctuation: float = 0.25
    phrases: float = 0.35
    structure: float = 0.20
    vocabulary: float = 0.10
    emoji: float = 0.10

    def validate(self) -> None:
        total = sum([self.punctuation, self.phrases, self.structure, self.vocabulary, self.emoji])
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Category weights must sum to 1.0, got {total:.3f}")

    def as_dict(self) -> dict[str, float]:
        return {
            "punctuation": self.punctuation,
            "phrases": self.phrases,
            "structure": self.structure,
            "vocabulary": self.vocabulary,
            "emoji": self.emoji,
        }


@dataclass
class AppConfig:
    patterns_dir: str
    weights: WeightConfig
    likely_ai_threshold: int = 65
    likely_human_threshold: int = 30
