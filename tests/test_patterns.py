"""New T5 patterns: each regex pattern fires on its positive example and stays
silent on a negative one, and the term moves out of ai_writing_tropes /
filler_openers are complete."""

from __future__ import annotations

from pathlib import Path

import pytest

from aidar.core.fetcher import count_words
from aidar.patterns.loader import load_patterns
from aidar.patterns.registry import PatternRegistry

PATTERNS_DIR = Path(__file__).resolve().parents[1] / "patterns"

NEW_PATTERN_IDS = [
    "unicode_arrows",
    "compulsive_counting",
    "listicle_trenchcoat",
    "rhetorical_qa",
    "signposted_conclusion",
    "juridical_register",
    "verification_provenance",
    "self_grading",
    "spec_ese",
    "aphoristic_closer",
    "retroactive_significance",
]

# (pattern_id, positive text, negative text). Positives must normalize above 0
# (raw > threshold_low per 1000 words); negatives must return raw == 0.
CASES = [
    (
        "unicode_arrows",
        (
            "Use the CLI first then the API next and the results arrive. "
            "The arrow points onward → through the pipe → out the other end. "
            "More filler prose follows so this fixture looks like a real page."
        ),
        (
            "Use the CLI first then the API next and the results arrive. "
            "The arrow points onward and through the pipe and out the other end. "
            "More filler prose follows so this fixture looks like a real page."
        ),
    ),
    (
        "compulsive_counting",
        (
            "We shipped the flag for two reasons that became clear later. "
            "More filler prose follows so this fixture looks like a real page "
            "with enough words to be representative of actual content."
        ),
        (
            "We shipped the flag for reasons that became clear much later. "
            "More filler prose follows so this fixture looks like a real page "
            "with enough words to be representative of actual content."
        ),
    ),
    (
        "listicle_trenchcoat",
        (
            "The first reason is obvious to anyone who has run it.\n\n"
            "More filler prose follows so this fixture looks like a real page "
            "with enough words to be representative of actual content."
        ),
        (
            "I want to explain the first reason in its own section later.\n\n"
            "More filler prose follows so this fixture looks like a real page "
            "with enough words to be representative of actual content."
        ),
    ),
    (
        "rhetorical_qa",
        (
            "The catch? Nobody knows yet. More filler prose follows here so this "
            "fixture looks like a real page with enough words in it to be "
            "representative of actual content for the detector run."
        ),
        (
            "What is the catch? The answer requires careful analysis of many "
            "interlocking factors across the whole system before any conclusion "
            "can be drawn from the evidence gathered during the investigation."
        ),
    ),
    (
        "signposted_conclusion",
        (
            "In conclusion, the approach holds up under load. More filler prose "
            "follows this sentence so the fixture has enough words to look like "
            "a real document for the detector run and its threshold checks."
        ),
        (
            "The approach holds up under load, which is the conclusion. More "
            "filler prose follows this sentence so the fixture has enough words "
            "to look like a real document for the detector run and its checks."
        ),
    ),
    (
        "juridical_register",
        (
            "The scheduler refuses the request and logs the reason. More filler "
            "prose follows this sentence so the fixture has enough words to look "
            "like a real document for the detector run and its threshold checks."
        ),
        (
            "The scheduler rejects the request and logs the reason. More filler "
            "prose follows this sentence so the fixture has enough words to look "
            "like a real document for the detector run and its threshold checks."
        ),
    ),
    (
        "verification_provenance",
        (
            "The artifact is byte-identical across every rebuild we ran. More "
            "filler prose follows this sentence so the fixture has enough words "
            "to look like a real document for the detector run and its checks."
        ),
        (
            "The artifact is identical across every rebuild we verified. More "
            "filler prose follows this sentence so the fixture has enough words "
            "to look like a real document for the detector run and its checks."
        ),
    ),
    (
        "self_grading",
        (
            "It's worth noting the cache never lies about this. More filler "
            "prose follows this sentence so the fixture has enough words to look "
            "like a real document for the detector run and its threshold checks."
        ),
        (
            "The cache never lies about this, and that is notable. More filler "
            "prose follows this sentence so the fixture has enough words to look "
            "like a real document for the detector run and its threshold checks."
        ),
    ),
    (
        "spec_ese",
        (
            "That worker idles awaiting input from the queue above. More filler "
            "prose follows this sentence so the fixture has enough words to look "
            "like a real document for the detector run and its threshold checks."
        ),
        (
            "The worker waits for input from the queue above it. More filler "
            "prose follows this sentence so the fixture has enough words to look "
            "like a real document for the detector run and its threshold checks."
        ),
    ),
    (
        "aphoristic_closer",
        (
            "It misses by a wide margin in production, and that is the result. "
            "More filler prose follows this sentence so the fixture has enough "
            "words to look like a real document for the detector run and checks."
        ),
        (
            "It misses by a large margin in production this quarter. More filler "
            "prose follows this sentence so the fixture has enough words to look "
            "like a real document for the detector run and its checks."
        ),
    ),
    (
        "retroactive_significance",
        (
            "That is why the ordering matters in practice. More filler prose "
            "follows this sentence so the fixture has enough words to look like "
            "a real document for the detector run and its threshold checks."
        ),
        (
            "That is why the ordering was chosen in practice. More filler prose "
            "follows this sentence so the fixture has enough words to look like "
            "a real document for the detector run and its threshold checks."
        ),
    ),
]


@pytest.fixture(scope="module")
def registry() -> PatternRegistry:
    return PatternRegistry(load_patterns(PATTERNS_DIR))


def test_all_new_patterns_load(registry: PatternRegistry) -> None:
    ids = {p.id for p in registry.all_patterns()}
    for pid in NEW_PATTERN_IDS:
        assert pid in ids, f"{pid} missing from loaded patterns"


def test_moved_terms_are_gone(registry: PatternRegistry) -> None:
    tropes = {p.id: p for p in registry.all_patterns()}["ai_writing_tropes"]
    assert tropes.version == 4
    for gone in ("→", "⟹", "the result?", "the catch?", "in conclusion,",
                 "to sum up,", "the first reason", "the second wall",
                 "it's worth noting"):
        assert gone not in tropes.params["terms"], f"'{gone}' still in ai_writing_tropes"
    fillers = {p.id: p for p in registry.all_patterns()}["filler_openers"]
    assert fillers.version == 3  # T4b: v2 (T5 term move) + word_boundary switch combined per supervisor
    for gone in ("in conclusion", "to sum up", "in summary", "to wrap up",
                 "wrapping up", "in closing", "to conclude"):
        assert gone not in fillers.params["terms"], f"'{gone}' still in filler_openers"
    # the distinctive fillers stay
    for kept in ("in essence", "overall", "ultimately", "final thoughts"):
        assert kept in fillers.params["terms"]


@pytest.mark.parametrize("pid,positive,negative", CASES, ids=[c[0] for c in CASES])
def test_positive_fires_and_negative_does_not(
    registry: PatternRegistry, pid: str, positive: str, negative: str
) -> None:
    detector = registry.get_detector(pid)
    pos = detector.detect(positive, count_words(positive))
    neg = detector.detect(negative, count_words(negative))
    assert pos.raw_value > 0, f"{pid} did not fire on positive example (label: {pos.label})"
    assert pos.normalized_score > 0, f"{pid} fired but scored below threshold_low"
    assert neg.raw_value == 0, f"{pid} fired on negative example (label: {neg.label})"
