"""Offline tests for scripts/check_upstreams.py (no network calls)."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "check_upstreams.py"

spec = importlib.util.spec_from_file_location("check_upstreams", SCRIPT)
cu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cu)


def test_load_manifest_parses_the_real_sources_yaml():
    sources = cu.load_manifest(REPO / "sources.yaml")
    by_id = {s["id"]: s for s in sources}
    assert len(sources) == 16
    assert by_id["tropes-fyi"]["pinned"] == "2026-11-09T20:14:42Z"
    assert by_id["tropes-fyi"]["derived_patterns"] == [
        "ai_writing_tropes",
        "short_punchy_fragments",
        "tricolon_abuse",
        "ai_section_headers",
        "bold_first_bullets",
        "negative_parallelism",
        "ai_word_choice_tropes",
    ]
    assert by_id["declauding"]["tag_prefix"] == "declauding-v"
    assert by_id["wikipedia-signs-of-ai-writing"]["pinned"] == "1384930421"  # stays a string
    assert by_id["marginalia-hn-em-dash"]["pinned"] is None


def test_load_manifest_rejects_malformed_lines(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("sources:\n  - id: x\n    bad line without colon\n")
    with pytest.raises(SystemExit):
        cu.load_manifest(bad)


def test_load_manifest_handles_empty_and_block_lists(tmp_path):
    m = tmp_path / "m.yaml"
    m.write_text(
        "# comment\n"
        "sources:\n"
        "  - id: a\n"
        "    kind: web\n"
        "    locator: https://example.com\n"
        "    pinned: null\n"
        "    derived_patterns: []\n"
        "  - id: b\n"
        "    kind: web\n"
        "    locator: https://example.org\n"
        "    pinned: null\n"
        "    derived_patterns:\n"
        "      - p_one\n"
        "      - p_two\n"
    )
    sources = cu.load_manifest(m)
    assert sources[0]["derived_patterns"] == []
    assert sources[1]["derived_patterns"] == ["p_one", "p_two"]
    assert sources[0]["pinned"] is None


def test_compare_tags():
    assert cu.compare_tags("v4.0.0", "v3.1.0", "") > 0
    assert cu.compare_tags("declauding-v0.14.0", "declauding-v0.9.3", "declauding-v") > 0
    assert cu.compare_tags("v2.11.1", "v2.2.0", "") > 0
    assert cu.compare_tags("v4.0.0", "v4.0.0", "") == 0
    assert cu.compare_tags("v3.1.0", "v4.0.0", "") < 0


def test_reference_mapping():
    tropes = {"id": "tropes-fyi", "url": "https://tropes.fyi", "locator": "abc"}
    gist = {"id": "writing-whip", "url": "https://gist.github.com/x/y", "locator": "abc"}
    locator_only = {"id": "web-src", "locator": "https://news.ycombinator.com/item?id=1"}
    assert cu.reference_maps_to("https://tropes.fyi", tropes)
    assert cu.reference_maps_to("https://tropes.fyi/directory", tropes)  # prefix rule
    assert not cu.reference_maps_to("https://tropes.fyi/directory", gist)
    assert cu.reference_maps_to("https://news.ycombinator.com/item?id=1", locator_only)
    assert not cu.reference_maps_to("https://tropes.fyi", {"id": "x", "locator": "not-a-url"})


def test_pattern_references_scan(tmp_path):
    pdir = tmp_path / "patterns" / "tropes"
    pdir.mkdir(parents=True)
    (pdir / "p.yaml").write_text(
        "id: my_pattern\n"
        "name: X\n"
        "references:\n"
        "  - https://a.example/one\n"
        "  - https://a.example/two\n"
        "params:\n"
        "  terms:\n"
        "    - https://not-a-reference.example\n"
    )
    (pdir / "no_refs.yaml").write_text("id: bare\nname: Y\n")
    refs = cu.pattern_references(tmp_path / "patterns")
    assert refs == {"my_pattern": {"https://a.example/one", "https://a.example/two"}}


def test_manifest_and_patterns_agree_on_the_real_repo():
    """The real sources.yaml must cover every pattern references: URL."""
    sources = cu.load_manifest(REPO / "sources.yaml")
    refs = cu.pattern_references(REPO / "patterns")
    assert refs, "no pattern references found"
    for pid, urls in refs.items():
        mapped = {s["id"] for s in sources for u in urls if cu.reference_maps_to(u, s)}
        assert mapped, f"pattern {pid} cites URLs no source tracks: {sorted(urls)}"
    derived = {pid for s in sources for pid in s.get("derived_patterns") or []}
    assert derived == set(refs)


def test_cli_offline_smoke(tmp_path):
    """All-null pins + empty patterns dir: full CLI run without network."""
    m = tmp_path / "sources.yaml"
    m.write_text(
        "sources:\n"
        "  - id: a\n"
        "    kind: web\n"
        "    locator: https://example.com\n"
        "    pinned: null\n"
        "    derived_patterns: []\n"
    )
    empty = tmp_path / "patterns"
    empty.mkdir()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--manifest", str(m), "--patterns-dir", str(empty), "--strict"],
        check=False, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "1 sources, 0 pinned, 0 drifted, 0 manifest errors, 0 unchecked" in proc.stdout
