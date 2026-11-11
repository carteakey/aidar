from __future__ import annotations

import csv
import json
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from aidar.cli import eval as eval_cli
from aidar.cli.main import aidar

PATTERNS_DIR = Path(__file__).resolve().parents[1] / "patterns"


def _doc(path: str, label: str, score: int, raw: float, fired: bool) -> eval_cli.DocScore:
    """Fabricated DocScore: one pattern, controlled separation."""
    return eval_cli.DocScore(
        path=path,
        label=label,
        word_count=100,
        score=score,
        aidar_label="LIKELY HUMAN" if score <= 15 else "LIKELY AI",
        categories={"tropes": score / 100, "punctuation": 0.0, "phrases": 0.0,
                    "structure": 0.0, "emoji": 0.0, "vocabulary": 0.0},
        normalized={"p_trope": 1.0 if fired else 0.0},
        raw={"p_trope": raw},
        pattern_category={"p_trope": "tropes"},
    )


def test_auc_known_values() -> None:
    assert eval_cli.auc([1.0, 2.0], [0.0, 0.0]) == 1.0
    assert eval_cli.auc([0.0], [1.0]) == 0.0
    assert eval_cli.auc([1.0], [1.0]) == 0.5
    # (1,2) loses, (2,2) ties, (3,2) wins -> (0 + 0.5 + 1) / 3
    assert eval_cli.auc([1.0, 2.0, 3.0], [2.0]) == pytest.approx(0.5)
    assert eval_cli.auc([], [1.0]) is None
    assert eval_cli.auc([1.0], []) is None


def test_parse_manifest_csv(tmp_path: Path) -> None:
    manifest = tmp_path / "m.csv"
    manifest.write_text("path,label\na.html,human\nb.html,ai-assisted\n", encoding="utf-8")
    rows = eval_cli.parse_manifest(manifest)
    assert rows == [
        {"path": "a.html", "label": "human"},
        {"path": "b.html", "label": "ai-assisted"},
    ]


def test_parse_manifest_jsonl(tmp_path: Path) -> None:
    manifest = tmp_path / "m.jsonl"
    manifest.write_text(
        '{"path": "a.html", "label": "human"}\n\n{"path": "b.html", "label": "ai"}\n',
        encoding="utf-8",
    )
    rows = eval_cli.parse_manifest(manifest)
    assert rows == [
        {"path": "a.html", "label": "human"},
        {"path": "b.html", "label": "ai"},
    ]


def test_parse_manifest_missing_column(tmp_path: Path) -> None:
    manifest = tmp_path / "m.csv"
    manifest.write_text("path,kind\na.html,human\n", encoding="utf-8")
    with pytest.raises(click.BadParameter):
        eval_cli.parse_manifest(manifest)


def test_parse_manifest_blank_row(tmp_path: Path) -> None:
    manifest = tmp_path / "m.csv"
    manifest.write_text("path,label\n, \na.html,human\n", encoding="utf-8")
    assert eval_cli.parse_manifest(manifest) == [{"path": "a.html", "label": "human"}]


def test_frontmatter_value_yaml_block() -> None:
    text = "---\ntitle: Alpha\nauthored_by: ai-assisted\n---\n\nBody text.\n"
    assert eval_cli.frontmatter_value(text, "authored_by") == "ai-assisted"
    assert eval_cli.frontmatter_value(text, "authored_by") != "Alpha"


def test_frontmatter_value_regex_fallback() -> None:
    text = "# Heading\n\nauthored_by: human\n\nBody.\n"
    assert eval_cli.frontmatter_value(text, "authored_by") == "human"
    assert eval_cli.frontmatter_value(text, "missing") is None


def _make_corpus(tmp_path: Path) -> tuple[Path, Path]:
    content = tmp_path / "content"
    html_root = tmp_path / "_site"
    for rel, body in [
        ("posts/2024-01-01-alpha.md", "---\nauthored_by: human\n---\nBody\n"),
        ("posts/2024-02-02-beta.md", "---\nauthored_by: ai-assisted\n---\nBody\n"),
        ("notes/2024-03-03-nikki.md", "---\nauthored_by: human\n---\nBody\n"),
        ("posts/2024-04-04-nopage.md", "---\nauthored_by: human\n---\nBody\n"),
        ("posts/2024-05-05-nofield.md", "Just body, no frontmatter.\n"),
        ("templates/2024-06-06-tpl.md", "---\nauthored_by: human\n---\nBody\n"),
    ]:
        p = content / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    for kind, slug in [("blog", "alpha"), ("blog", "beta"), ("notes", "nikki")]:
        page = html_root / kind / slug / "index.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("<html><body><p>word " * 30 + "</p></body></html>", encoding="utf-8")
    return content, html_root


def test_build_manifest_from_frontmatter(tmp_path: Path) -> None:
    content, html_root = _make_corpus(tmp_path)
    rows, skipped = eval_cli.build_manifest_from_frontmatter(content, html_root, "authored_by")

    # rows follow sorted rglob order: notes/ < posts/
    assert rows == [
        {"path": str(html_root / "notes" / "nikki" / "index.html"), "label": "human"},
        {"path": str(html_root / "blog" / "alpha" / "index.html"), "label": "human"},
        {"path": str(html_root / "blog" / "beta" / "index.html"), "label": "ai-assisted"},
    ]
    reasons = {Path(s["path"]).name: s["reason"] for s in skipped}
    assert set(reasons) == {"2024-04-04-nopage.md", "2024-05-05-nofield.md", "2024-06-06-tpl.md"}
    assert "no built page" in reasons["2024-04-04-nopage.md"]
    assert "no authored_by frontmatter" in reasons["2024-05-05-nofield.md"]
    assert "template" in reasons["2024-06-06-tpl.md"]


def test_write_manifest_csv_roundtrip(tmp_path: Path) -> None:
    content, html_root = _make_corpus(tmp_path)
    rows, _ = eval_cli.build_manifest_from_frontmatter(content, html_root, "authored_by")
    out = tmp_path / "out.csv"
    eval_cli.write_manifest_csv(rows, out)
    with out.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert {"path", "label"} <= set(reader.fieldnames)
        assert len(list(reader)) == 3


def test_evaluate_synthetic() -> None:
    docs = [
        _doc("h1", "human", 3, 0.0, False),
        _doc("h2", "human", 5, 0.1, False),
        _doc("a1", "ai-assisted", 30, 0.9, True),
        _doc("a2", "ai-generated", 40, 1.0, True),
    ]
    report = eval_cli.evaluate(docs, {"ai-assisted", "ai-generated"}, {"human"})

    assert report["corpus"]["label_counts"] == {"ai-assisted": 1, "ai-generated": 1, "human": 2}
    assert report["aggregate_auc"] == 1.0  # perfect separation
    assert report["labels"]["human"]["median_score"] == 4.0
    assert report["labels"]["human"]["aidar_labels"] == {"LIKELY HUMAN": 2}
    assert report["category_auc"]["tropes"] == 1.0

    (row,) = report["patterns"]
    assert row["pattern_id"] == "p_trope"
    assert row["auc"] == 1.0
    assert row["fire_rate"] == {"ai-assisted": 1.0, "ai-generated": 1.0, "human": 0.0}
    # normalized scores are 1.0 (fired) for both positive docs, 0.0 for both human docs
    assert row["mean_normalized_group"] == {"positive": 1.0, "negative": 0.0}


def test_evaluate_unlabelled_excluded_from_auc() -> None:
    docs = [
        _doc("h1", "human", 3, 0.0, False),
        _doc("a1", "ai-assisted", 30, 0.9, True),
        _doc("d1", "draft", 99, 5.0, True),  # in neither group
    ]
    report = eval_cli.evaluate(docs, {"ai-assisted"}, {"human"})
    assert report["corpus"]["label_counts"]["draft"] == 1
    assert report["aggregate_auc"] == 1.0
    assert "draft" not in json.dumps(report["corpus"]["groups"])


HUMAN_TEXT = (
    "Saturday we drove out to the coast and ate sandwiches in the car because the "
    "wind was awful. The tide was out far enough to walk the sandbar. I found a "
    "crab shell, half intact, and put it in my coat pocket where it still is. On "
    "the way home the light went gold over the hills and I thought about my "
    "grandmother's kitchen and how she never wrote anything down."
)

AI_TEXT = (
    "It's important to note that effective time management isn't just about "
    "productivity — it's about creating space for what matters. Let's dive in. "
    "Here's the thing: whether you're a student or a seasoned professional, these "
    "strategies will change the way you work. In today's fast-paced world, "
    "mastering this skill is more crucial than ever. First, prioritize ruthlessly. "
    "Second, batch similar tasks. Finally, remember: consistency beats intensity."
)


def _manifest_file(tmp_path: Path) -> Path:
    docs = {
        "h1.txt": HUMAN_TEXT,
        "h2.txt": HUMAN_TEXT.replace("coast", "lake"),
        "h3.txt": HUMAN_TEXT.replace("sandwiches", "soup"),
        "a1.txt": AI_TEXT,
        "a2.txt": AI_TEXT.replace("time management", "email hygiene"),
    }
    for name, text in docs.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    manifest = tmp_path / "m.csv"
    manifest.write_text(
        "path,label\n"
        + "".join(f"{tmp_path}/{name},human\n" for name in ("h1.txt", "h2.txt", "h3.txt"))
        + "".join(f"{tmp_path}/{name},ai-assisted\n" for name in ("a1.txt", "a2.txt")),
        encoding="utf-8",
    )
    return manifest


def _invoke(argv: list[str]):
    return CliRunner().invoke(aidar, ["--patterns-dir", str(PATTERNS_DIR), *argv])


def test_eval_cli_json(tmp_path: Path) -> None:
    manifest = _manifest_file(tmp_path)
    result = _invoke(["eval", "--manifest", str(manifest), "--output", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)

    assert data["corpus"]["scored"] == 5
    assert data["corpus"]["label_counts"] == {"ai-assisted": 2, "human": 3}
    assert data["corpus"]["skipped"] == 0
    assert data["aggregate_auc"] is not None
    assert set(data["category_auc"]) == {
        "tropes", "punctuation", "phrases", "structure", "emoji", "vocabulary",
    }
    assert data["patterns"]
    assert all(
        set(p) == {"pattern_id", "category", "auc", "mean_normalized", "fire_rate",
                   "mean_normalized_group", "fire_rate_group"}
        for p in data["patterns"]
    )


def test_eval_cli_terminal(tmp_path: Path) -> None:
    manifest = _manifest_file(tmp_path)
    result = _invoke(["eval", "--manifest", str(manifest)])
    assert result.exit_code == 0, result.output
    assert "aggregate AUC" in result.output
    assert "per-label aggregate score distribution" in result.output
    assert "human" in result.output and "ai-assisted" in result.output


def test_eval_cli_manifest_exclusive(tmp_path: Path) -> None:
    manifest = _manifest_file(tmp_path)
    result = _invoke(["eval", "--manifest", str(manifest), "--from-frontmatter", str(tmp_path)])
    assert result.exit_code != 0
    assert "exactly one" in result.output


def test_eval_cli_group_output_flag(tmp_path: Path) -> None:
    manifest = _manifest_file(tmp_path)
    result = _invoke(["--output", "json", "eval", "--manifest", str(manifest)])
    assert result.exit_code == 0, result.output
    json.loads(result.output)


def test_eval_cli_assert_max_score_passes(tmp_path: Path) -> None:
    manifest = _manifest_file(tmp_path)
    result = _invoke(["eval", "--manifest", str(manifest), "--assert-max-score", "100",
                      "--output", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)  # stderr carries the PASSED line; stdout is pure JSON
    assert data["regression"] == {
        "assert_max_score": 100,
        "negative_labels": ["human"],
        "passed": True,
        "violations": [],
    }


def test_eval_cli_assert_max_score_violation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest_file(tmp_path)
    fake_docs = [
        _doc("h1", "human", 45, 0.0, False),  # 45 > threshold 20 -> violation
        _doc("a1", "ai-assisted", 42, 0.9, True),
    ]
    monkeypatch.setattr(eval_cli, "score_rows", lambda rows, analyzer, config: (fake_docs, []))
    result = _invoke(["eval", "--manifest", str(manifest), "--assert-max-score", "20"])
    assert result.exit_code == 1
    assert "regression FAILED" in result.output
    assert "h1" in result.output


def test_eval_cli_assert_max_score_violation_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest_file(tmp_path)
    fake_docs = [
        _doc("h1", "human", 45, 0.0, False),  # 45 > threshold 20 -> violation
        _doc("a1", "ai-assisted", 42, 0.9, True),
    ]
    monkeypatch.setattr(eval_cli, "score_rows", lambda rows, analyzer, config: (fake_docs, []))
    result = _invoke(["eval", "--manifest", str(manifest), "--assert-max-score", "20",
                      "--output", "json"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)  # stderr carries the FAILED line; stdout is pure JSON
    assert data["regression"]["passed"] is False
    assert data["regression"]["violations"] == [
        {"path": "h1", "label": "human", "score": 45}
    ]


def test_eval_cli_skip_bad_file(tmp_path: Path) -> None:
    good = tmp_path / "good.txt"
    good.write_text(HUMAN_TEXT, encoding="utf-8")
    manifest = tmp_path / "m.csv"
    manifest.write_text(f"path,label\n{tmp_path}/gone.txt,human\n{good},human\n", encoding="utf-8")
    result = _invoke(["eval", "--manifest", str(manifest), "--output", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["corpus"]["scored"] == 1
    assert data["corpus"]["skipped"] == 1
    assert data["corpus"]["skipped_details"][0]["path"].endswith("gone.txt")
