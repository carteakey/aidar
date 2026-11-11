from __future__ import annotations

import pytest

from aidar.models.pattern import PatternDef
from aidar.patterns.detectors.frequency_detector import FrequencyDetector
from aidar.patterns.detectors.linguistic_detector import _split_sentences


def _frequency_pattern(params: dict) -> PatternDef:
    full = {"threshold_low": 0.0, "threshold_high": 1.0, **params}
    return PatternDef(
        id="test_frequency",
        name="Test Frequency",
        description="test",
        category="phrases",
        weight=0.5,
        detection_type="frequency",
        params=full,
        version=1,
    )


def _raw_for(detector: FrequencyDetector, text: str) -> float:
    return detector.detect(text, word_count=len(text.split())).raw_value


def test_word_boundary_is_default() -> None:
    # no match_mode param -> whole-word matching; 'utilize' must not fire in 'utilized'
    detector = FrequencyDetector(_frequency_pattern({"terms": ["utilize"]}))
    assert _raw_for(detector, "google utilized its basic algorithm to rank results") == 0.0
    assert _raw_for(detector, "google used its algorithm to utilize ranking signals") > 0.0


def test_word_boundary_stops_intra_word_false_matches() -> None:
    # 'thus' inside 'enthusiasts' (real false match from the human corpus)
    detector = FrequencyDetector(_frequency_pattern({"terms": ["thus"]}))
    assert _raw_for(detector, "veteran tech enthusiasts or professionals often write this") == 0.0


def test_contains_mode_still_substring_matches() -> None:
    detector = FrequencyDetector(_frequency_pattern({"terms": ["utilize"], "match_mode": "contains"}))
    assert _raw_for(detector, "google utilized its basic algorithm") > 0.0


def test_exact_is_legacy_alias_for_word_boundary() -> None:
    # the old 'exact' only matched a term surrounded by spaces; word_boundary
    # also matches punctuation- and line-adjacent occurrences
    detector = FrequencyDetector(_frequency_pattern({"terms": ["delve"], "match_mode": "exact"}))
    text = "Delve. Then (delve) again.\ndelve deeper"
    assert _raw_for(detector, text) == pytest.approx(3.0 * 1000 / len(text.split()))


def test_word_boundary_case_insensitive_and_multiword() -> None:
    detector = FrequencyDetector(_frequency_pattern({"terms": ["Deep Dive"]}))
    assert _raw_for(detector, "a Deep Dive into archives, not another DEEP DIVE") == pytest.approx(
        2.0 * 1000 / 9
    )


def test_unknown_match_mode_rejected() -> None:
    with pytest.raises(ValueError, match="match_mode"):
        FrequencyDetector(_frequency_pattern({"terms": ["x"], "match_mode": "regexy"}))


def test_split_sentences_excludes_bullets_headings_tables() -> None:
    text = (
        "# Setup\n"
        "\n"
        "Run the installer and wait for it to finish.\n"
        "- install deps\n"
        "- enable the service\n"
        "- reboot\n"
        "\n"
        "| Navigation | | |\n"
        "| `H` | Home |\n"
        "\n"
        "Then verify the checksum before rebooting the machine today."
    )
    units = _split_sentences(text)
    # every unit is prose: no unit holds a bullet line, table row or heading
    assert all("\n" not in u for u in units)
    assert all("|" not in u and not u.lstrip().startswith(("-", "#")) for u in units)
    assert any(u.startswith("Run the installer") for u in units)
    assert any(u.startswith("Then verify") for u in units)


def test_split_sentences_keeps_plain_prose() -> None:
    text = "The first sentence is short. The second sentence rambles on and on, adding clause after clause, until it becomes notably longer than the first one did."
    units = _split_sentences(text)
    assert len(units) == 2


def test_negative_parallelism_split_loads_and_classifies() -> None:
    from pathlib import Path

    from aidar.patterns.loader import load_patterns

    patterns_path = Path(__file__).resolve().parents[1] / "patterns"
    patterns = {p.id: p for p in load_patterns(patterns_path)}
    assert "negative_parallelism" in patterns and "negative_parallelism_plain" in patterns
    assert patterns["negative_parallelism"].weight == 0.90
    assert patterns["negative_parallelism_plain"].weight == 0.30


def _regex_detector(pattern_id: str) -> object:
    from pathlib import Path

    from aidar.patterns.loader import load_patterns
    from aidar.patterns.registry import PatternRegistry

    patterns_path = Path(__file__).resolve().parents[1] / "patterns"
    registry = PatternRegistry(load_patterns(patterns_path))
    return registry.get_detector(pattern_id)


def test_strong_parallelism_matches_cross_sentence_reprise() -> None:
    detector = _regex_detector("negative_parallelism")
    # brief's example: subject reprise across a sentence break
    result = detector.detect("The question isn't scale. The question is focus.", 10)
    assert result.raw_value > 0
    # pronoun follow-through still lands here, not in the plain pattern
    result = detector.detect("The problem isn't the code. It's the architecture.", 9)
    assert result.raw_value > 0


def test_plain_parallelism_only_matches_plain_contrast() -> None:
    strong = _regex_detector("negative_parallelism")
    plain = _regex_detector("negative_parallelism_plain")
    text = "That is not merely a tool, but a platform for building."
    assert plain.detect(text, 10).raw_value > 0
    assert strong.detect(text, 10).raw_value == 0.0
