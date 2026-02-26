from __future__ import annotations

from pathlib import Path

import yaml

from aidar.models.config import WeightConfig
from aidar.models.pattern import PatternDef


class PatternLoadError(Exception):
    pass


def load_patterns(patterns_dir: Path) -> list[PatternDef]:
    """
    Recursively discover all *.yaml files under patterns_dir, excluding
    _weights.yaml and models/*.yaml. Returns validated PatternDef instances.
    """
    patterns: list[PatternDef] = []
    models_dir = patterns_dir / "models"

    for yaml_file in sorted(patterns_dir.rglob("*.yaml")):
        # Skip the weights config and model profiles
        if yaml_file.name.startswith("_"):
            continue
        if yaml_file.is_relative_to(models_dir):
            continue

        try:
            data = _load_yaml(yaml_file)
            pattern = _parse_pattern(data, yaml_file)
            patterns.append(pattern)
        except PatternLoadError as e:
            raise PatternLoadError(f"{yaml_file}: {e}") from e

    return patterns


def load_weight_config(patterns_dir: Path) -> WeightConfig:
    """Load patterns/_weights.yaml and return WeightConfig."""
    weights_file = patterns_dir / "_weights.yaml"
    if not weights_file.exists():
        return WeightConfig()

    data = _load_yaml(weights_file)
    weights_data = data.get("weights", {})
    config = WeightConfig(
        phrases=float(weights_data.get("phrases", 0.35)),
        punctuation=float(weights_data.get("punctuation", 0.25)),
        structure=float(weights_data.get("structure", 0.20)),
        vocabulary=float(weights_data.get("vocabulary", 0.10)),
        emoji=float(weights_data.get("emoji", 0.10)),
    )
    config.validate()
    return config


def load_model_profile(patterns_dir: Path, model_name: str) -> dict[str, float]:
    """Load patterns/models/<model_name>.yaml and return pattern_id → score dict."""
    model_file = patterns_dir / "models" / f"{model_name}.yaml"
    if not model_file.exists():
        available = [f.stem for f in (patterns_dir / "models").glob("*.yaml")]
        raise PatternLoadError(
            f"Model profile '{model_name}' not found. "
            f"Available: {', '.join(available) or 'none'}"
        )
    data = _load_yaml(model_file)
    return {k: float(v) for k, v in data.get("profile", {}).items()}


def _load_yaml(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise PatternLoadError("YAML file must contain a mapping at the top level")
        return data
    except yaml.YAMLError as e:
        raise PatternLoadError(f"YAML parse error: {e}") from e


def _parse_pattern(data: dict, source: Path) -> PatternDef:
    required = ["id", "name", "description", "category", "weight", "detection_type", "params"]
    for field in required:
        if field not in data:
            raise PatternLoadError(f"Missing required field '{field}'")

    try:
        return PatternDef(
            id=str(data["id"]),
            name=str(data["name"]),
            description=str(data["description"]).strip(),
            category=str(data["category"]),
            weight=float(data["weight"]),
            detection_type=str(data["detection_type"]),
            params=dict(data["params"]),
            version=int(data.get("version", 1)),
            severity=str(data.get("severity", "medium")),
            references=list(data.get("references", [])),
            added_by=str(data.get("added_by", "")),
        )
    except (TypeError, ValueError) as e:
        raise PatternLoadError(f"Invalid field value: {e}") from e
