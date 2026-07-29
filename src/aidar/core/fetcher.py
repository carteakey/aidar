from __future__ import annotations

from pathlib import Path

import httpx
import trafilatura

from aidar import __version__

_HEADERS = {
    "User-Agent": (
        f"Mozilla/5.0 (compatible; aidar/{__version__}; +https://github.com/carteakey/aidar)"
    )
}


class FetchError(Exception):
    pass


class FetchResult:
    """Holds extracted text plus any metadata trafilatura could extract."""

    __slots__ = ("text", "word_count", "title", "published_date", "raw_html")

    def __init__(
        self,
        text: str,
        word_count: int,
        title: str | None = None,
        published_date: str | None = None,
        raw_html: str | None = None,
    ):
        self.text = text
        self.word_count = word_count
        self.title = title
        self.published_date = published_date  # ISO date string e.g. "2024-03-15" or None
        self.raw_html = raw_html  # Original HTML source for HTML-level pattern detectors


def _extract(html: str) -> FetchResult | None:
    doc = trafilatura.bare_extraction(
        html,
        with_metadata=True,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
    )

    if isinstance(doc, dict):
        extracted_text = str(doc.get("text") or "")
        title = str(doc.get("title") or "") or None
        published_date = str(doc.get("date") or "") or None
    else:
        extracted_text = doc.text or "" if doc else ""
        title = doc.title or None if doc else None
        published_date = doc.date or None if doc else None

    if len(extracted_text.split()) < 20:
        # Fallback: plain extract without metadata
        text = trafilatura.extract(html, include_tables=True, no_fallback=False)
        if not text or len(text.split()) < 20:
            return None
        return FetchResult(text=text, word_count=count_words(text), raw_html=html)

    return FetchResult(
        text=extracted_text,
        word_count=count_words(extracted_text),
        title=title,
        published_date=published_date,
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
    """Read a local .txt or .html file."""
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
    return FetchResult(text=raw, word_count=count_words(raw))


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
