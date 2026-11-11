"""Extraction must preserve document structure (# headers, - bullets, **bold**)
so the structural and text-fallback detectors can read it."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from aidar.core.fetcher import (
    FetchResult,
    _clean_markdown,
    _extract,
    count_markdown_words,
    read_file,
)

HEADER_RE = re.compile(r"^#{1,6}\s+\S.*$", re.MULTILINE)
BULLET_RE = re.compile(r"^\s*(?:[-*•·◦▪▸►✓✗]|\d+[.)]\s)\s*\S", re.MULTILINE)

FIXTURE_HTML = """<html><body><article>
<h1>Test Page</h1>
<p>Intro paragraph with enough words to pass the minimum length filter. Here is more
filler text to reach the threshold quickly and reliably for testing purposes only.</p>
<h2>Section One</h2>
<p>Body text for section one. It has several words and a sentence. Then another
sentence follows here to pad the length a bit further.</p>
<ul><li><strong>First point</strong>: about testing.</li><li>Plain second point about extraction quality.</li></ul>
<h3>Subsection</h3>
<ol><li>Numbered alpha item with words.</li><li>Numbered beta item with words.</li></ol>
<p>Some <em>emphasis</em> and <strong>bold</strong> inline. Closing paragraph text here
with a few more words to keep the extractor happy.</p>
</article></body></html>"""


@pytest.fixture(scope="module")
def extracted() -> FetchResult:
    result = _extract(FIXTURE_HTML)
    assert result is not None, "fixture HTML too short to extract"
    return result


def test_headers_survive_extraction(extracted) -> None:
    # 20 h1-h3 elements -> "# Test Page", "## Section One", "### Subsection"
    headers = HEADER_RE.findall(extracted.text)
    assert len(headers) == 3
    assert "## Section One" in headers
    assert "### Subsection" in headers


def test_bullets_survive_extraction(extracted) -> None:
    # 2 <ul> items render as "- ", 2 <ol> items render as "1. "/"2. "
    bullets = BULLET_RE.findall(extracted.text)
    assert len(bullets) == 4
    assert "- Plain second point about extraction quality." in extracted.text
    assert "1. Numbered alpha item with words." in extracted.text


def test_bold_survives_for_text_fallback_patterns(extracted) -> None:
    # html_regex text_patterns match markdown "**Keyword**" list leads
    assert "**First point**" in extracted.text


def test_word_count_ignores_markdown_syntax(extracted) -> None:
    # "#", "- ", "1. " and "**" markers must not inflate the denominator
    assert extracted.word_count == count_markdown_words(extracted.text)
    assert extracted.word_count < len(extracted.text.split())


def test_count_markdown_words_strips_markers() -> None:
    assert count_markdown_words("# Title\n\n- **bold** word\n\n1. two words\n") == 5
    assert count_markdown_words("plain words only") == 3


def test_clean_markdown_drops_rules_keeps_paragraphs() -> None:
    text = "First paragraph.\n\n|---|---|\n\n---\n\nSecond paragraph.\n"
    cleaned = _clean_markdown(text)
    assert "First paragraph." in cleaned and "Second paragraph." in cleaned
    assert "|" not in cleaned and not re.search(r"^---\s*$", cleaned, re.MULTILINE)
    # blank lines survive: two paragraphs -> one blank-line separator
    assert re.search(r"\n\s*\n", cleaned)


def test_paragraph_initial_bold_is_not_a_bullet() -> None:
    # trafilatura renders "<p><strong>Note:</strong> ..." as "**Note:** ..." —
    # line-initial "*" is emphasis, never a list marker ("- " is used for lists)
    cleaned = _clean_markdown("**Note:** this is a paragraph, not a list item.\n\n- real bullet\n")
    assert not cleaned.splitlines()[0].startswith("*")  # cannot mimic a bullet line
    assert cleaned.splitlines()[0] == "Note: this is a paragraph, not a list item."
    assert "**" not in cleaned  # no orphan closing marker left behind
    assert "- real bullet" in cleaned  # real list markers untouched


def test_leading_emphasis_span_is_stripped_with_closing_marker() -> None:
    assert _clean_markdown("**Note:** x") == "Note: x"
    assert _clean_markdown("*italic start* here") == "italic start here"
    # real bullets and mid-line emphasis are untouched
    assert _clean_markdown("- **Security**: x") == "- **Security**: x"
    assert _clean_markdown("a **b** c") == "a **b** c"


def test_raw_html_passthrough(extracted) -> None:
    assert extracted.raw_html == FIXTURE_HTML


def test_read_file_md_word_count(tmp_path: Path) -> None:
    md = tmp_path / "post.md"
    md.write_text("# Title\n\n- one\n- two words\n\nBody paragraph here.\n")
    result = read_file(md)
    assert result.text == md.read_text()
    assert result.word_count == 7  # Title one two words Body paragraph here
    assert result.word_count < len(result.text.split())  # markers excluded
