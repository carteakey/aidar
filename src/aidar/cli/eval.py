from __future__ import annotations

import csv
import json
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import click
import yaml

from aidar.cli.main import aidar
from aidar.core.fetcher import read_file
from aidar.core.scorer import compute_aggregate

_SLUG_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-")


@dataclass
class DocScore:
    """One scored document with the per-pattern detail the eval report needs."""

    path: str
    label: str  # corpus label from the manifest / frontmatter
    word_count: int
    score: int  # aggregate 0-100
    aidar_label: str  # LIKELY HUMAN / UNCERTAIN / LIKELY AI
    categories: dict[str, float]  # category -> score
    normalized: dict[str, float]  # pattern id -> normalized score
    raw: dict[str, float]  # pattern id -> raw value
    pattern_category: dict[str, str]  # pattern id -> category


def auc(pos: list[float], neg: list[float]) -> float | None:
    """Mann-Whitney AUC = P[a positive score beats a negative score]; ties count half."""
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def _r(value: float | None, ndigits: int = 4) -> float | None:
    return None if value is None else round(float(value), ndigits)


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _fire_rate(values: list[float]) -> float | None:
    """Share of docs where a pattern fired (normalized score > 0)."""
    if not values:
        return None
    return sum(v > 0 for v in values) / len(values)


def _fmt(value: float | None, spec: str = ".2f") -> str:
    return "n/a" if value is None else format(value, spec)


def parse_manifest(path: Path) -> list[dict[str, str]]:
    """Read a CSV or JSONL manifest with 'path' and 'label' columns."""
    raw = path.read_text(encoding="utf-8-sig")
    rows: list[dict[str, str]] = []

    suffix = path.suffix.lower()
    if suffix == ".jsonl" or (suffix != ".csv" and raw.lstrip().startswith("{")):
        for lineno, line in enumerate(raw.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise click.BadParameter(f"{path}:{lineno}: invalid JSONL ({e})") from e
            if not isinstance(obj, dict) or "path" not in obj or "label" not in obj:
                raise click.BadParameter(f"{path}:{lineno}: JSONL rows need 'path' and 'label'")
            rows.append({"path": str(obj["path"]).strip(), "label": str(obj["label"]).strip()})
    else:
        reader = csv.DictReader(raw.splitlines())
        if not reader.fieldnames or not {"path", "label"} <= set(reader.fieldnames):
            raise click.BadParameter(f"{path}: manifest needs 'path' and 'label' columns")
        rows = [
            {"path": (row.get("path") or "").strip(), "label": (row.get("label") or "").strip()}
            for row in reader
            if (row.get("path") or "").strip() or (row.get("label") or "").strip()
        ]

    bad = [row for row in rows if not row["path"] or not row["label"]]
    if bad:
        raise click.BadParameter(f"{path}: {len(bad)} row(s) missing path or label")
    return rows


def write_manifest_csv(rows: list[dict[str, str]], out: Path) -> None:
    """Persist a resolved manifest as path,label CSV (sorted, for stable diffs)."""
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["path", "label"])
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (r["path"], r["label"])):
            writer.writerow(row)


def frontmatter_value(text: str, field_name: str) -> str | None:
    """Read one field from a markdown file's frontmatter (YAML block, then regex)."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            try:
                data = yaml.safe_load(text[3:end])
            except yaml.YAMLError:
                data = None
            if isinstance(data, dict):
                value = data.get(field_name)
                if value is not None and str(value).strip():
                    return str(value).strip()
    m = re.search(rf"^{re.escape(field_name)}:\s*(\S+)", text, re.MULTILINE)
    return m.group(1) if m else None


def build_manifest_from_frontmatter(
    content_dir: Path,
    html_root: Path,
    label_field: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Map a markdown tree to built pages: slug = filename minus its date prefix,
    page = <html_root>/blog|notes/<slug>/index.html ('notes' if the md path has a
    notes/ part). Returns (manifest rows, skipped-with-reason)."""
    rows: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    for md in sorted(content_dir.rglob("*.md")):
        if any("template" in part.lower() for part in md.parts):
            skipped.append({"path": str(md), "reason": "template path"})
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        value = frontmatter_value(text, label_field)
        if not value:
            skipped.append({"path": str(md), "reason": f"no {label_field} frontmatter"})
            continue
        slug = _SLUG_DATE_PREFIX.sub("", md.stem)
        kind = "notes" if "notes" in md.parts else "blog"
        html = html_root / kind / slug / "index.html"
        if not html.exists():
            skipped.append({"path": str(md), "reason": f"no built page at {html}"})
            continue
        rows.append({"path": str(html.resolve()), "label": value})

    return rows, skipped


def score_rows(
    rows: list[dict[str, str]],
    analyzer,
    config,
) -> tuple[list[DocScore], list[dict[str, str]]]:
    """Score every manifest row; one bad file becomes a skip, not a crash."""
    docs: list[DocScore] = []
    skipped: list[dict[str, str]] = []

    for row in rows:
        try:
            fetch = read_file(Path(row["path"]))
            score_vector = analyzer.run(fetch.text, fetch.word_count, raw_html=fetch.raw_html)
            aggregate = compute_aggregate(
                score_vector, config, file_path=row["path"], word_count=fetch.word_count
            )
        except Exception as e:  # noqa: BLE001 - a bad corpus entry must not kill the eval
            skipped.append({"path": row["path"], "reason": str(e)})
            continue

        docs.append(
            DocScore(
                path=row["path"],
                label=row["label"],
                word_count=fetch.word_count,
                score=aggregate.aggregate_score,
                aidar_label=aggregate.label,
                categories=score_vector.as_dict(),
                normalized={r.pattern_id: r.normalized_score for r in score_vector.pattern_results},
                raw={r.pattern_id: r.raw_value for r in score_vector.pattern_results},
                pattern_category={r.pattern_id: r.category for r in score_vector.pattern_results},
            )
        )

    return docs, skipped


def evaluate(docs: list[DocScore], positive: set[str], negative: set[str]) -> dict:
    """Build the eval report: label distributions, aggregate/category/per-pattern AUC.

    Positive/negative are sets of corpus labels pooled into the two comparison
    groups; corpus labels outside both groups are reported but excluded from AUC."""
    labels = sorted({d.label for d in docs})
    pos = [d for d in docs if d.label in positive]
    neg = [d for d in docs if d.label in negative]
    categories = sorted({c for d in docs for c in d.categories})

    label_stats: dict[str, dict] = {}
    for label in labels:
        group = [d for d in docs if d.label == label]
        scores = [d.score for d in group]
        label_stats[label] = {
            "count": len(group),
            "median_score": statistics.median(scores),
            "min_score": min(scores),
            "max_score": max(scores),
            "aidar_labels": dict(sorted(Counter(d.aidar_label for d in group).items())),
        }

    pattern_rows = []
    for pid in sorted({pid for d in docs for pid in d.normalized}):
        have = [d for d in docs if pid in d.normalized]
        have_pos = [d for d in have if d.label in positive]
        have_neg = [d for d in have if d.label in negative]
        norm_pos = [d.normalized[pid] for d in have_pos]
        norm_neg = [d.normalized[pid] for d in have_neg]

        pattern_rows.append({
            "pattern_id": pid,
            "category": next(
                (d.pattern_category[pid] for d in have if pid in d.pattern_category), None
            ),
            "auc": _r(auc([d.raw[pid] for d in have_pos], [d.raw[pid] for d in have_neg])),
            "mean_normalized": {
                label: _r(_mean([d.normalized[pid] for d in have if d.label == label]))
                for label in labels
            },
            "fire_rate": {
                label: _r(_fire_rate([d.normalized[pid] for d in have if d.label == label]))
                for label in labels
            },
            "mean_normalized_group": {
                "positive": _r(_mean(norm_pos)),
                "negative": _r(_mean(norm_neg)),
            },
            "fire_rate_group": {
                "positive": _r(_fire_rate(norm_pos)),
                "negative": _r(_fire_rate(norm_neg)),
            },
        })
    pattern_rows.sort(key=lambda row: (row["auc"] is None, -(row["auc"] or 0.0)))

    return {
        "corpus": {
            "groups": {"positive": sorted(positive), "negative": sorted(negative)},
            "label_counts": {label: label_stats[label]["count"] for label in labels},
            "scored": len(docs),
        },
        "labels": label_stats,
        "aggregate_auc": _r(auc([d.score for d in pos], [d.score for d in neg])),
        "category_auc": {
            c: _r(auc([d.categories[c] for d in pos], [d.categories[c] for d in neg]))
            for c in categories
        },
        "patterns": pattern_rows,
    }


def render_terminal(report: dict) -> None:
    corpus = report["corpus"]
    skipped = corpus.get("skipped_details") or []
    click.echo(
        f"aidar eval — scored {corpus['scored']} docs, skipped {len(skipped)}"
        f" ({corpus.get('source', 'manifest')})"
    )
    click.echo(
        "groups: positive=[" + ",".join(corpus["groups"]["positive"])
        + "]  negative=[" + ",".join(corpus["groups"]["negative"]) + "]"
    )
    click.echo("")
    click.echo("per-label aggregate score distribution:")
    for label, stats in report["labels"].items():
        aidar_counts = " ".join(f"{k}={v}" for k, v in stats["aidar_labels"].items())
        click.echo(
            f"  {label:14} n={stats['count']:<3} median {stats['median_score']:>5.1f}"
            f"  range {stats['min_score']}-{stats['max_score']}  {aidar_counts}"
        )
    click.echo("")
    click.echo(f"aggregate AUC (P[positive > negative]): {_fmt(report['aggregate_auc'])}")
    click.echo(
        "category AUC: "
        + " ".join(f"{c}={_fmt(v)}" for c, v in report["category_auc"].items())
    )
    click.echo("")
    click.echo("per-pattern: AUC | fire rate per label")
    for row in report["patterns"]:
        fires = " ".join(
            f"{label}={_fmt(rate, '.0%')}"
            for label, rate in row["fire_rate"].items()
            if rate is not None
        )
        click.echo(f"  {row['pattern_id']:32} {_fmt(row['auc'])} | {fires}")


@aidar.command(name="eval")
@click.option(
    "--manifest", "manifest_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="CSV or JSONL manifest with 'path' and 'label' columns; paths resolve relative to cwd.",
)
@click.option(
    "--from-frontmatter", "frontmatter_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Build the manifest from a markdown tree instead: read --label-field from each *.md "
    "and score its built page under --html-root.",
)
@click.option(
    "--label-field", default="authored_by", show_default=True,
    help="Frontmatter field that carries the corpus label (with --from-frontmatter).",
)
@click.option(
    "--html-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Root of built pages: <root>/blog/<slug>/index.html and <root>/notes/<slug>/index.html. "
    "Required with --from-frontmatter.",
)
@click.option(
    "--positive", default="ai-assisted,ai-generated", show_default=True,
    help="Comma-separated corpus labels pooled as the positive (AI) group.",
)
@click.option(
    "--negative", default="human", show_default=True,
    help="Comma-separated corpus labels pooled as the negative (human) group.",
)
@click.option(
    "--write-manifest", type=click.Path(dir_okay=False, path_type=Path), default=None,
    help="Save the resolved manifest as path,label CSV before scoring.",
)
@click.option(
    "--assert-max-score", type=click.IntRange(0, 100), default=None, metavar="N",
    help="Regression gate: exit 1 if any negative-group doc scores above N "
    "(guard a known-human corpus in CI).",
)
@click.option(
    "--output", "output_override", type=click.Choice(["terminal", "json"]), default=None,
    help="Output format (overrides the global --output).",
)
@click.pass_context
def eval_command(
    ctx: click.Context,
    manifest_path: Path | None,
    frontmatter_dir: Path | None,
    label_field: str,
    html_root: Path | None,
    positive: str,
    negative: str,
    write_manifest: Path | None,
    assert_max_score: int | None,
    output_override: str | None,
) -> None:
    """Score a labelled corpus and report how well each pattern separates labels.

    Documents come from --manifest (CSV/JSONL with path,label) or, via
    --from-frontmatter DIR, from a markdown tree whose built pages live under
    --html-root (slug = filename minus its YYYY-MM-DD- prefix, page =
    <html-root>/blog|notes/<slug>/index.html). Reports per-label score
    distributions, aggregate AUC, per-category AUC, and per-pattern AUC plus fire
    rate per label between the --positive and --negative groups.
    """
    output_format = output_override or ctx.obj["output"]
    analyzer = ctx.obj["analyzer"]
    config = ctx.obj["config"]

    positive_set = {part.strip() for part in positive.split(",") if part.strip()}
    negative_set = {part.strip() for part in negative.split(",") if part.strip()}
    if not positive_set or not negative_set:
        raise click.BadParameter("--positive and --negative each need at least one label")
    overlap = positive_set & negative_set
    if overlap:
        raise click.BadParameter(f"labels cannot be both positive and negative: {sorted(overlap)}")

    if (manifest_path is None) == (frontmatter_dir is None):
        raise click.UsageError("pass exactly one of --manifest FILE or --from-frontmatter DIR")
    if frontmatter_dir is not None and html_root is None:
        raise click.UsageError("--from-frontmatter needs --html-root DIR (root of built pages)")

    build_skipped: list[dict[str, str]] = []
    if manifest_path is not None:
        rows = parse_manifest(manifest_path)
        source = str(manifest_path)
    else:
        rows, build_skipped = build_manifest_from_frontmatter(frontmatter_dir, html_root, label_field)
        source = f"frontmatter:{frontmatter_dir}"

    if write_manifest is not None:
        write_manifest_csv(rows, write_manifest)

    docs, score_skipped = score_rows(rows, analyzer, config)
    skipped = build_skipped + score_skipped

    if not docs:
        click.echo("aidar eval: no documents scored — nothing to report", err=True)
        raise SystemExit(1)

    report = evaluate(docs, positive_set, negative_set)
    report["corpus"]["source"] = source
    report["corpus"]["skipped"] = len(skipped)
    report["corpus"]["skipped_details"] = skipped

    violations: list[DocScore] = []
    if assert_max_score is not None:
        violations = [d for d in docs if d.label in negative_set and d.score > assert_max_score]
        report["regression"] = {
            "assert_max_score": assert_max_score,
            "negative_labels": sorted(negative_set),
            "passed": not violations,
            "violations": [
                {"path": d.path, "label": d.label, "score": d.score} for d in violations
            ],
        }

    if output_format == "json":
        click.echo(json.dumps(report, indent=2))
    else:
        render_terminal(report)

    if assert_max_score is not None:
        if violations:
            click.echo(
                f"regression FAILED: {len(violations)} negative-group doc(s) above {assert_max_score}",
                err=True,
            )
            for v in violations:
                click.echo(f"  {v.path}  label={v.label}  score={v.score}", err=True)
            raise SystemExit(1)
        worst = max(d.score for d in docs if d.label in negative_set)
        click.echo(f"regression PASSED: worst negative-group score {worst} <= {assert_max_score}", err=True)
