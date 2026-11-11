"""Property tests for the category aggregation modes (docs/AGGREGATION.md).

The key property the sources demand: adding a never-firing pattern must not
change any category score, so growing the pattern set cannot dilute signal.
"""

from __future__ import annotations

import pytest

from aidar.core.analyzer import Analyzer
from aidar.models.config import ClusterParams
from aidar.models.result import PatternResult, ScoreVector


def result(pid: str, cat: str, score: float, weight: float = 0.90) -> PatternResult:
    return PatternResult(
        pattern_id=pid, category=cat, raw_value=score, normalized_score=score,
        weight=weight, label="x",
    )


def build(results: list[PatternResult], mode: str, cluster: ClusterParams | None = None) -> ScoreVector:
    class _FakeRegistry:
        pass

    return Analyzer(_FakeRegistry(), aggregation=mode, cluster=cluster)._aggregate(results)


# ------------------------------------------------------------- zero-addition --

ZERO = result("never_fires", "tropes", 0.0, weight=0.85)
ACTIVE = [
    result("tricolon_abuse", "tropes", 0.70),
    result("bold_first_bullets", "tropes", 0.45),
    result("ai_writing_tropes", "tropes", 0.30),
    result("em_dash_overuse", "punctuation", 0.55),
    result("hedging_phrases", "phrases", 0.20),
    result("emoji_density", "emoji", 0.0, weight=0.05),
]


@pytest.mark.parametrize("mode", ["noisy_or", "mean_plus_cluster"])
def test_adding_a_never_firing_pattern_changes_nothing(mode):
    base = build(ACTIVE, mode)
    diluted = build([*ACTIVE, ZERO], mode)
    assert base.as_dict() == diluted.as_dict()


def test_plain_mean_does_dilute_documented_bug():
    """The current default does NOT have the property — that is the bug T6 tracks."""
    base = build(ACTIVE, "mean")
    diluted = build([*ACTIVE, ZERO], "mean")
    assert base.as_dict() != diluted.as_dict()
    assert diluted.tropes < base.tropes


# ------------------------------------------------------- cluster semantics --

def test_noisy_or_co_occurring_weak_hits_outweigh_single_hits():
    """One weak tell means little; several co-occurring weak tells mean a lot."""
    weak = {"w1": 0.20, "w2": 0.22, "w3": 0.25}
    singles = [build([result(k, "tropes", v, weight=0.9)], "noisy_or").tropes for k, v in weak.items()]
    cluster = build([result(k, "tropes", v, weight=0.9) for k, v in weak.items()], "noisy_or").tropes

    assert all(s < 0.25 for s in singles)          # each tell alone: small
    assert cluster > max(singles) * 2              # together: far more than any one
    assert cluster == pytest.approx(1 - (1 - 0.20 * 0.9) * (1 - 0.22 * 0.9) * (1 - 0.25 * 0.9))


def test_noisy_or_saturates():
    many = [result(f"p{i}", "tropes", 0.5) for i in range(20)]
    assert build(many, "noisy_or").tropes == pytest.approx(1 - 0.55 ** 20)
    assert build(many, "noisy_or").tropes > 0.999


def test_mean_plus_cluster_single_strong_hit_scores_near_its_own_score():
    single = build([result("tricolon_abuse", "tropes", 0.60)], "mean_plus_cluster")
    # firing mean over one pattern = its own score; cluster bonus 1/3 of scale
    assert single.tropes == pytest.approx(0.60 + ClusterParams().scale / ClusterParams().k)


def test_mean_plus_cluster_bonus_saturates():
    cluster = ClusterParams(firing_threshold=0.30, scale=0.15, k=3)
    below = [result("p1", "tropes", 0.29), result("p2", "tropes", 0.28)]          # 0 firing
    at_k = [result(f"p{i}", "tropes", 0.5) for i in range(3)]                     # k firing
    beyond = [result(f"p{i}", "tropes", 0.5) for i in range(6)]                   # > k firing

    b = build(below, "mean_plus_cluster", cluster).tropes
    a = build(at_k, "mean_plus_cluster", cluster).tropes
    x = build(beyond, "mean_plus_cluster", cluster).tropes

    assert b == pytest.approx((0.29 + 0.28) / 2)  # firing mean only: neither pattern reaches the threshold
    assert a == pytest.approx(0.5 + 0.15)         # saturated exactly at k
    assert x == pytest.approx(0.5 + 0.15)         # capped: more fires do not add more


def test_empty_results_are_all_zero_in_every_mode():
    for mode in ("mean", "noisy_or", "mean_plus_cluster"):
        sv = build([], mode)
        assert sv.as_dict() == {c: 0.0 for c in sv.as_dict()}


# ------------------------------------------------------------------ config --

def test_unknown_mode_rejected():
    with pytest.raises(ValueError, match="aggregation must be one of"):
        Analyzer(registry=None, aggregation="median")


def test_weights_config_roundtrip(tmp_path):
    from aidar.models.config import ClusterParams
    from aidar.patterns.loader import load_weight_config

    weights = (
        "weights:\n"
        "  tropes: 0.40\n  phrases: 0.20\n  punctuation: 0.15\n"
        "  structure: 0.10\n  vocabulary: 0.10\n  emoji: 0.05\n"
    )
    (tmp_path / "_weights.yaml").write_text(weights)
    cfg = load_weight_config(tmp_path)  # no aggregation key -> default mean
    cfg.validate()
    assert cfg.aggregation == "mean"
    assert cfg.cluster == ClusterParams()

    (tmp_path / "_weights.yaml").write_text(
        weights + "aggregation: noisy_or\ncluster:\n  firing_threshold: 0.5\n  scale: 0.2\n  k: 4\n"
    )
    cfg2 = load_weight_config(tmp_path)
    cfg2.validate()
    assert cfg2.aggregation == "noisy_or"
    assert cfg2.cluster == ClusterParams(firing_threshold=0.5, scale=0.2, k=4)

    (tmp_path / "_weights.yaml").write_text(weights + "aggregation: median\n")
    with pytest.raises(ValueError, match="aggregation must be one of"):
        load_weight_config(tmp_path)
