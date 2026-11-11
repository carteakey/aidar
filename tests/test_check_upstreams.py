"""Offline tests for scripts/check_upstreams.py (no network calls)."""

import importlib.util
import re
import subprocess
import sys
import urllib.error
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
    assert len(sources) == 14
    assert by_id["tropes-fyi"]["pinned"] == "2026-11-09T20:14:42Z"
    assert by_id["tropes-fyi"]["derived_patterns"] == [
        "ai_writing_tropes",
        "short_punchy_fragments",
        "tricolon_abuse",
        "ai_section_headers",
        "bold_first_bullets",
        "negative_parallelism",
        "negative_parallelism_plain",  # T4b: split out of negative_parallelism
        "ai_word_choice_tropes",
        "unicode_arrows",
        "compulsive_counting",
        "listicle_trenchcoat",
        "rhetorical_qa",
        "signposted_conclusion",
    ]
    assert by_id["declauding"]["derived_patterns"] == [
        "juridical_register",
        "verification_provenance",
        "self_grading",
        "spec_ese",
        "aphoristic_closer",
        "retroactive_significance",
        # T4b: hedging/ai_idioms/negative_parallelism cite declauding's linter
        "hedging_phrases",
        "ai_idioms",
        "negative_parallelism",
    ]
    assert by_id["declauding"]["tag_prefix"] == "declauding-v"
    assert by_id["wikipedia-signs-of-ai-writing"]["pinned"] == "1384930421"  # stays a string
    assert by_id["marginalia-hn-em-dash"]["pinned"] is None
    assert "arxiv-burstiness-citation" not in by_id
    assert "hn-second-person-comment" not in by_id
    assert by_id["arxiv-delve-lexical-overrepresentation"]["derived_patterns"] == ["ai_idioms"]
    assert by_id["mattr-lexical-diversity"]["locator"] == "doi:10.1016/j.rmal.2024.100168"


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


# ------------------------------------------------- citation verification --

ATOM_OK = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>ArXiv Query</title>
  <entry>
    <id>http://arxiv.org/abs/2412.11385v1</id>
    <title>Why Does ChatGPT &quot;Delve&quot; So Much?</title>
    <summary>words like delve, intricate, underscore</summary>
  </entry>
</feed>
"""

ATOM_ERROR = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>ArXiv Query</title>
  <entry>
    <id>http://arxiv.org/abs/error</id>
    <title>Error</title>
    <summary>incorrect id</summary>
  </entry>
</feed>
"""


def test_resolve_paper_arxiv(monkeypatch):
    seen = {}

    def fake_http_text(url, token):
        seen["url"] = url
        return ATOM_OK

    monkeypatch.setattr(cu, "http_text", fake_http_text)
    ok, title = cu.resolve_paper({"locator": "arXiv:2412.11385"}, None)
    assert ok and title == 'Why Does ChatGPT "Delve" So Much?'
    assert seen["url"] == "https://export.arxiv.org/api/query?id_list=2412.11385"


def test_resolve_paper_arxiv_missing_record(monkeypatch):
    monkeypatch.setattr(cu, "http_text", lambda url, token: ATOM_ERROR)
    ok, err = cu.resolve_paper({"locator": "arXiv:9999.99999"}, None)
    assert not ok and "no record" in err


def test_resolve_paper_arxiv_empty_feed(monkeypatch):
    monkeypatch.setattr(
        cu, "http_text",
        lambda url, token: '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>',
    )
    ok, err = cu.resolve_paper({"locator": "arXiv:2412.11385"}, None)
    assert not ok and "no entry" in err


def test_resolve_paper_doi(monkeypatch):
    monkeypatch.setattr(cu, "http_json", lambda url, token: {"message": {"title": ["MATTR paper"]}})
    ok, title = cu.resolve_paper({"locator": "doi:10.1016/j.rmal.2024.100168"}, None)
    assert ok and title == "MATTR paper"


def test_resolve_paper_doi_404(monkeypatch):
    def boom(url, token):
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(cu, "http_json", boom)
    ok, err = cu.resolve_paper({"locator": "doi:10.1080/09296174.1990.10820076"}, None)
    assert not ok and "404" in err


def test_resolve_paper_unknown_locator():
    ok, err = cu.resolve_paper({"locator": "isbn:1234"}, None)
    assert not ok and "unsupported" in err


def test_real_paper_locators_are_supported_schemes():
    sources = cu.load_manifest(REPO / "sources.yaml")
    papers = [s for s in sources if s["kind"] == "paper"]
    assert papers
    for s in papers:
        assert re.match(r"^(arXiv|doi):", s["locator"]), s["id"]


def test_cli_verify_citations_offline(tmp_path):
    """--verify-citations with no papers: wiring works, exits 0."""
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
        [sys.executable, str(SCRIPT), "--manifest", str(m), "--patterns-dir", str(empty),
         "--verify-citations"],
        check=False, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "0 papers checked, 0 unresolved" in proc.stdout
