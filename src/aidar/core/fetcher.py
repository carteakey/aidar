from __future__ import annotations

import re
from pathlib import Path

import httpx
import trafilatura

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; aidar/0.1; +https://github.com/carteakey/aidar)"
    )
}

# Characters that make up pure-punctuation markdown lines: table separators
# (|---|---|) and horizontal rules (---, ***, ___). Such lines carry no words
# but would register as bullet lines, paragraphs, and sentence fragments
# downstream. Blank lines are kept — they are the paragraph separators.
_MD_PUNCT_CHARS = frozenset("|-:*_=: \t")

# Markdown structural syntax stripped before counting words, so "# Header" and
# "- item" markers don't inflate the per-1000-words denominators.
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_BULLET_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_MD_ENUM_RE = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
_MD_EMPHASIS_RE = re.compile(r"`+|\*+")
_MD_TABLE_PIPE_RE = re.compile(r"\|")

# Trafilatura marks list items with "- " only, so a line-initial "*" is always
# emphasis ("**Note:** ..."), never a bullet — but it would count as one in
# bullet_density. Strip the leading markers, keep inline ones.
_MD_LEADING_ASTERISK_RE = re.compile(r"(?m)^(\s*)\*+(?=\S)")


def _clean_markdown(text: str) -> str:
    """Drop markdown lines that are pure punctuation (hrules, table separators)
    and de-emphasize paragraph-initial bold/italic that mimics bullet markers."""
    lines = [
        line
        for line in text.splitlines()
        if not (line.strip() and set(line.strip()) <= _MD_PUNCT_CHARS)
    ]
    return _MD_LEADING_ASTERISK_RE.sub(r"\1", "\n".join(lines))


def count_markdown_words(text: str) -> int:
    """Word count excluding markdown syntax markers (headings, bullets, emphasis)."""
    stripped = _MD_HEADING_RE.sub("", text)
    stripped = _MD_BULLET_RE.sub("", stripped)
    stripped = _MD_ENUM_RE.sub("", stripped)
    stripped = _MD_EMPHASIS_RE.sub("", stripped)
    stripped = _MD_TABLE_PIPE_RE.sub(" ", stripped)
    return len(stripped.split())


class FetchError(Exception):
    pass


class FetchResult:
    """Holds extracted text plus any metadata trafilatura could extract."""
    __slots__ = ("text", "word_count", "title", "published_date", "raw_html")

    def __init__(self, text: str, word_count: int, title: str | None = None, published_date: str | None = None, raw_html: str | None = None):
        self.text = text
        self.word_count = word_count
        self.title = title
        self.published_date = published_date  # ISO date string e.g. "2024-03-15" or None
        self.raw_html = raw_html  # Original HTML source for HTML-level pattern detectors


def _extract(html: str) -> FetchResult:
    doc = trafilatura.bare_extraction(
        html,
        with_metadata=True,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
    )

    if not doc or not doc.text or len(doc.text.split()) < 20:
        # Fallback: extract without metadata
        text = trafilatura.extract(
            html,
            output_format="markdown",
            include_formatting=True,
            include_tables=True,
            no_fallback=False,
        )
        if not text or count_markdown_words(text) < 20:
            return None
        return FetchResult(text=_clean_markdown(text), word_count=count_markdown_words(text), raw_html=html)

    # Markdown output keeps the document shape (# headers, - bullets, **bold**)
    # that structural and text-fallback detectors read; plain text drops it.
    text = trafilatura.extract(
        html,
        output_format="markdown",
        include_formatting=True,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
    )
    if not text:
        text = doc.text
        word_count = count_words(text)
    else:
        text = _clean_markdown(text)
        word_count = count_markdown_words(text)

    return FetchResult(
        text=text,
        word_count=word_count,
        title=doc.title or None,
        published_date=doc.date or None,
        raw_html=html,
    )


def fetch_url(url: str, timeout: int = 30) -> FetchResult:
    """Download URL and extract clean article text + metadata."""
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True, headers=_HEADERS)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise FetchError(f"HTTP {e.response.status_code} fetching {url}") from e
    except httpx.RequestError as e:
        raise FetchError(f"Request failed for {url}: {e}") from e

    result = _extract(response.text)
    if result is None:
        raise FetchError(
            f"Could not extract readable text from {url}. "
            "The page may be JavaScript-rendered, paywalled, or have no article body."
        )
    return result


def read_file(path: Path) -> FetchResult:
    """Read a local .txt, .md or .html file."""
    if not path.exists():
        raise FetchError(f"File not found: {path}")

    raw = path.read_text(encoding="utf-8", errors="replace")

    if path.suffix.lower() in (".html", ".htm"):
        result = _extract(raw)
        if result:
            return result
        return FetchResult(text=raw, word_count=count_words(raw), raw_html=raw)

    if not raw.strip():
        raise FetchError(f"File is empty: {path}")
    word_count = count_markdown_words(raw) if path.suffix.lower() == ".md" else count_words(raw)
    return FetchResult(text=raw, word_count=word_count)


def count_words(text: str) -> int:
    return len(text.split())


async def fetch_url_async(url: str, client: httpx.AsyncClient) -> FetchResult:
    """Async version for bulk scanning."""
    try:
        response = await client.get(url, timeout=30, follow_redirects=True, headers=_HEADERS)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise FetchError(f"HTTP {e.response.status_code} fetching {url}") from e
    except httpx.RequestError as e:
        raise FetchError(f"Request failed for {url}: {e}") from e

    result = _extract(response.text)
    if result is None:
        raise FetchError(f"No extractable text from {url}")
    return result
