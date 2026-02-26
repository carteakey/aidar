from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DetectionType = Literal["regex", "frequency", "structural", "linguistic"]
Category = Literal["punctuation", "phrases", "structure", "emoji", "vocabulary"]
Severity = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class PatternDef:
    id: str
    name: str
    description: str
    category: str
    weight: float
    detection_type: str
    params: dict[str, Any]
    severity: str = "medium"
    references: list[str] = field(default_factory=list)
    added_by: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError(f"Pattern '{self.id}': weight must be 0.0-1.0, got {self.weight}")
        valid_categories = {"punctuation", "phrases", "structure", "emoji", "vocabulary"}
        if self.category not in valid_categories:
            raise ValueError(
                f"Pattern '{self.id}': invalid category '{self.category}'. "
                f"Must be one of {valid_categories}"
            )
        valid_detection_types = {"regex", "frequency", "structural", "linguistic"}
        if self.detection_type not in valid_detection_types:
            raise ValueError(
                f"Pattern '{self.id}': invalid detection_type '{self.detection_type}'. "
                f"Must be one of {valid_detection_types}"
            )
