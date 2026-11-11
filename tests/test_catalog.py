"""Generated pattern catalog: deterministic render, --write/--check round trip,
hand-written sections preserved."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from aidar.cli.main import aidar

FIXTURE_WEIGHTS = """\
weights:
  tropes: 0.40
  phrases: 0.20
  punctuation: 0.15
  structure: 0.10
  vocabulary: 0.10
  emoji: 0.05
thresholds:
  likely_human_max: 15
  likely_ai_min: 30
"""

FIXTURE_TROPE = """\
id: fixture_arrow_tell
version: 1
name: Fixture Arrow Tell
description: Regex pattern fixture for the catalog test.
category: tropes
weight: 0.60
detection_type: regex
severity: medium
references:
  - https://tropes.fyi/directory
params:
  patterns:
    - '→'
  per_n_words: 1000
  threshold_low: 0.2
  threshold_high: 1.5
"""

FIXTURE_FILLER = """\
id: fixture_filler
version: 3
name: Fixture Filler
description: Frequency pattern fixture for the catalog test.
category: phrases
weight: 0.75
detection_type: frequency
severity: high
params:
  terms:
    - "overall"
  match_mode: exact
  per_n_words: 1000
  threshold_low: 1.0
  threshold_high: 8.0
"""

FIXTURE_STRUCTURE = """\
id: fixture_structure
version: 1
name: Fixture Structure
description: Structural pattern fixture for the catalog test.
category: structure
weight: 0.50
detection_type: structural
params:
  metric: bullet_density
  threshold_low: 0.10
  threshold_high: 0.45
"""

FIXTURE_SOURCES = """\
sources:
  - id: tropes-fyi
    name: tropes.fyi (fixture)
    kind: gist
    locator: f3baa9d25154c33095e22272c631f5a1
    url: https://tropes.fyi
    pinned: 2026-11-09T20:14:42Z
    license: CC BY 4.0
    derived_patterns:
      - fixture_arrow_tell
  - id: fixture-untracked
    name: untracked source (fixture)
    kind: web
    locator: https://example.com
    pinned: null
    license: All rights reserved (citation only)
    derived_patterns: []
"""

HANDWRITTEN_DOC = """\
# Pattern Catalog and Tuning Log

Canonical inventory intro paragraph.

## Tuning Workflow

1. Pick one pattern to adjust.

## Category Weights

| Category | Weight |
|---|---:|
| phrases | 0.40 |

## Pattern Inventory

| Category | Pattern ID | Type | Weight | Version | File |
|---|---|---|---:|---:|---|
| phrases | `stale_row` | frequency | 0.75 | 1 | none |

## Tuning Log

Add one row per pattern change.

| Date | Pattern ID | Change | Why | Evidence Sample(s) | Expected Impact | Done By |
|---|---|---|---|---|---|---|
| 2026-03-08 | `fixture_filler` | Threshold retune | fixture entry | n/a | none | fixture |
"""


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A tiny repo layout: patterns/ + sources.yaml + docs/PATTERN_CATALOG.md."""
    pdir = tmp_path / "patterns"
    (pdir / "tropes").mkdir(parents=True)
    (pdir / "phrases").mkdir()
    (pdir / "structure").mkdir()
    (pdir / "_weights.yaml").write_text(FIXTURE_WEIGHTS, encoding="utf-8")
    (pdir / "tropes" / "fixture_arrow_tell.yaml").write_text(FIXTURE_TROPE, encoding="utf-8")
    (pdir / "phrases" / "fixture_filler.yaml").write_text(FIXTURE_FILLER, encoding="utf-8")
    (pdir / "structure" / "fixture_structure.yaml").write_text(FIXTURE_STRUCTURE, encoding="utf-8")
    (tmp_path / "sources.yaml").write_text(FIXTURE_SOURCES, encoding="utf-8")
    doc = tmp_path / "docs" / "PATTERN_CATALOG.md"
    doc.parent.mkdir()
    doc.write_text(HANDWRITTEN_DOC, encoding="utf-8")
    return tmp_path, doc


def _invoke(args: list[str], tmp_path: Path) -> object:
    return CliRunner().invoke(aidar, ["--patterns-dir", str(tmp_path / "patterns"), *args])


def test_bootstrap_write_replaces_legacy_sections_preserves_handwritten(
    fixture_repo: tuple[Path, Path],
) -> None:
    tmp_path, doc = fixture_repo
    result = _invoke(["patterns", "catalog", "--write", "--file", str(doc)], tmp_path)
    assert result.exit_code == 0, result.output
    text = doc.read_text(encoding="utf-8")
    # markers inserted, legacy tables replaced
    assert "<!-- BEGIN GENERATED" in text and "<!-- END GENERATED" in text
    assert "`stale_row`" not in text
    # hand-written parts survive verbatim
    assert "Canonical inventory intro paragraph." in text
    assert "1. Pick one pattern to adjust." in text
    assert (
        "| 2026-03-08 | `fixture_filler` | Threshold retune | fixture entry | n/a | none | fixture |"
        in text
    )
    # inventory renders each fixture pattern with the brief's columns
    assert "`fixture_arrow_tell`" in text and "regex" in text
    assert "`fixture_filler`" in text and "exact" in text  # match_mode shown for frequency
    assert "`fixture_structure`" in text and "structural" in text
    assert "tropes-fyi" in text  # source id from sources.yaml
    assert "0.2" in text and "1.5" in text  # thresholds rendered


def test_inventory_is_sorted_by_category_then_id(fixture_repo: tuple[Path, Path]) -> None:
    tmp_path, doc = fixture_repo
    assert _invoke(["patterns", "catalog", "--write", "--file", str(doc)], tmp_path).exit_code == 0
    text = doc.read_text(encoding="utf-8")
    inventory = text.split("## Tuning Log")[0]
    ids = [
        line.split("`")[1]
        for line in inventory.splitlines()
        if line.startswith("| ") and "`fixture_" in line
    ]
    assert ids == ["fixture_filler", "fixture_structure", "fixture_arrow_tell"]


def test_check_passes_after_write_and_fails_after_yaml_edit(
    fixture_repo: tuple[Path, Path],
) -> None:
    tmp_path, doc = fixture_repo
    ok = _invoke(["patterns", "catalog", "--check", "--file", str(doc)], tmp_path)
    assert ok.exit_code == 1  # stale: doc still in legacy form, never written
    assert _invoke(["patterns", "catalog", "--write", "--file", str(doc)], tmp_path).exit_code == 0
    ok = _invoke(["patterns", "catalog", "--check", "--file", str(doc)], tmp_path)
    assert ok.exit_code == 0, ok.output
    # a YAML edit makes the doc stale again
    p = tmp_path / "patterns" / "tropes" / "fixture_arrow_tell.yaml"
    p.write_text(FIXTURE_TROPE.replace("threshold_high: 1.5", "threshold_high: 2.0"), encoding="utf-8")
    stale = _invoke(["patterns", "catalog", "--check", "--file", str(doc)], tmp_path)
    assert stale.exit_code == 1
    # and --write picks it up deterministically
    assert _invoke(["patterns", "catalog", "--write", "--file", str(doc)], tmp_path).exit_code == 0
    assert _invoke(["patterns", "catalog", "--check", "--file", str(doc)], tmp_path).exit_code == 0
    # %g number rendering: 2.0 renders as "2"
    assert "| 0.2 | 2 |" in doc.read_text(encoding="utf-8")


def test_write_is_idempotent_and_preserves_handwritten_across_runs(
    fixture_repo: tuple[Path, Path],
) -> None:
    tmp_path, doc = fixture_repo
    _invoke(["patterns", "catalog", "--write", "--file", str(doc)], tmp_path)
    first = doc.read_text(encoding="utf-8")
    _invoke(["patterns", "catalog", "--write", "--file", str(doc)], tmp_path)
    assert doc.read_text(encoding="utf-8") == first


def test_missing_doc_fails_check(tmp_path: Path) -> None:
    (tmp_path / "patterns").mkdir()
    (tmp_path / "patterns" / "_weights.yaml").write_text(FIXTURE_WEIGHTS, encoding="utf-8")
    result = _invoke(
        ["patterns", "catalog", "--check", "--file", str(tmp_path / "docs" / "nope.md")], tmp_path
    )
    assert result.exit_code == 1
