from __future__ import annotations

from dataclasses import dataclass

AGGREGATION_MODES = ("mean", "noisy_or", "mean_plus_cluster")


@dataclass(frozen=True)
class ClusterParams:
    """Parameters for the mean_plus_cluster aggregation mode."""

    firing_threshold: float = 0.30   # normalized score at/above which a pattern "fires"
    scale: float = 0.15              # max bonus a saturated cluster adds to the category
    k: int = 3                       # distinct firing patterns needed to saturate


@dataclass
class WeightConfig:
    tropes: float = 0.40      # AI writing tropes — heaviest signal
    phrases: float = 0.20
    punctuation: float = 0.15
    structure: float = 0.10
    vocabulary: float = 0.10
    emoji: float = 0.10
    aggregation: str = "mean"  # see AGGREGATION_MODES; default keeps current behaviour
    cluster: ClusterParams = ClusterParams()

    def validate(self) -> None:
        total = sum([self.tropes, self.punctuation, self.phrases, self.structure, self.vocabulary, self.emoji])
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Category weights must sum to 1.0, got {total:.3f}")
        if self.aggregation not in AGGREGATION_MODES:
            raise ValueError(
                f"aggregation must be one of {AGGREGATION_MODES}, got {self.aggregation!r}"
            )
        if not 0.0 < self.cluster.firing_threshold <= 1.0:
            raise ValueError(f"cluster.firing_threshold must be in (0, 1], got {self.cluster.firing_threshold}")
        if not 0.0 < self.cluster.scale <= 1.0:
            raise ValueError(f"cluster.scale must be in (0, 1], got {self.cluster.scale}")
        if self.cluster.k < 1:
            raise ValueError(f"cluster.k must be >= 1, got {self.cluster.k}")

    def as_dict(self) -> dict[str, float]:
        return {
            "tropes": self.tropes,
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
    likely_ai_threshold: int = 30
    likely_human_threshold: int = 15
