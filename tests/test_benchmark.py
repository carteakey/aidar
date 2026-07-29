from __future__ import annotations

import json
from pathlib import Path

import pytest

from aidar.benchmark.evaluate import evaluate, write_report
from aidar.benchmark.manifest import ManifestError, load_manifest
from aidar.benchmark.materialize import materialize, verify_materialized
from aidar.benchmark.raid import import_raid
from aidar.core.analyzer import Analyzer
from aidar.models.config import AppConfig
from aidar.patterns.loader import load_patterns, load_weight_config
from aidar.patterns.registry import PatternRegistry

FIXTURE_MANIFEST = Path("tests/fixtures/benchmark/manifest.yaml")


def _runtime() -> tuple[Analyzer, AppConfig]:
    patterns_dir = Path("patterns")
    analyzer = Analyzer(PatternRegistry(load_patterns(patterns_dir)))
    config = AppConfig(
        patterns_dir=str(patterns_dir),
        weights=load_weight_config(patterns_dir),
    )
    return analyzer, config


def test_manifest_requires_model_provenance_for_generated_text(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        """
schema_version: 1
benchmark: {id: broken, version: '1', description: Test manifest}
samples:
  - id: generated
    label: ai_generated
    split: holdout
    topic: test
    language: en
    publisher: fixture
    source: {kind: file, path: sample.txt}
    provenance: {evidence: claimed by fixture}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="model_family"):
        load_manifest(manifest)


def test_materialization_lock_detects_changed_text(tmp_path: Path) -> None:
    manifest = load_manifest(FIXTURE_MANIFEST)
    materialize(manifest, tmp_path)
    paths = verify_materialized(manifest, tmp_path)
    paths["human-holdout"].write_text("changed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_materialized(manifest, tmp_path)


def test_evaluation_is_deterministic_and_keeps_mixed_separate(tmp_path: Path) -> None:
    manifest = load_manifest(FIXTURE_MANIFEST)
    analyzer, config = _runtime()
    materialize(manifest, tmp_path)

    first = evaluate(
        manifest,
        tmp_path,
        analyzer,
        config,
        bootstrap_iterations=50,
    )
    second = evaluate(
        manifest,
        tmp_path,
        analyzer,
        config,
        bootstrap_iterations=50,
    )

    assert first == second
    assert first["sample_counts"] == {"ai_generated": 1, "human": 1, "mixed": 1}
    assert first["binary_metrics"]["n"] == 2
    assert "mixed" in first["score_distributions"]

    json_path, markdown_path = write_report(first, tmp_path / "report")
    assert json.loads(json_path.read_text(encoding="utf-8")) == first
    assert "Mixed samples are excluded" in markdown_path.read_text(encoding="utf-8")


def test_raid_import_uses_fixed_selector_ordinal(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
schema_version: 1
benchmark: {id: raid-test, version: '1', description: RAID import test}
samples:
  - id: chosen
    label: ai_generated
    split: holdout
    topic: test
    language: en
    publisher: RAID
    source: {kind: file, path: inputs/chosen.txt}
    provenance:
      evidence: RAID test row
      dataset: RAID
      model_family: GPT
      model: ChatGPT
      selector: {model: chatgpt, domain: news, attack: none, decoding: greedy, repetition_penalty: "no", ordinal: 2}
""".strip(),
        encoding="utf-8",
    )
    raid_csv = tmp_path / "raid.csv"
    raid_csv.write_text(
        "model,domain,attack,decoding,repetition_penalty,generation\n"
        "chatgpt,news,none,greedy,no,first match\n"
        "gpt4,news,none,greedy,no,not selected\n"
        "chatgpt,news,none,greedy,no,second match\n",
        encoding="utf-8",
    )

    written = import_raid(load_manifest(manifest_path), raid_csv)

    assert len(written) == 1
    assert written[0].read_text(encoding="utf-8") == "second match\n"
