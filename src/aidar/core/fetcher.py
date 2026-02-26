from __future__ import annotations

from pathlib import Path

import httpx
import trafilatura


class FetchError(Exception):
    pass


def fetch_url(url: str, timeout: int = 30) -> tuple[str, int]:
    """
    Download URL and extract clean article text using trafilatura.
    Returns (clean_text, word_count).
    Raises FetchError on failure.
    """
    try:
        response = httpx.get(
            url,
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; aidar/0.1; "
                    "+https://github.com/yourusername/aidar)"
                )
            },
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise FetchError(f"HTTP {e.response.status_code} fetching {url}") from e
    except httpx.RequestError as e:
        raise FetchError(f"Request failed for {url}: {e}") from e

    text = trafilatura.extract(
        response.text,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
    )

    if not text or len(text.split()) < 20:
        raise FetchError(
            f"Could not extract readable text from {url}. "
            "The page may be JavaScript-rendered, paywalled, or have no article body."
        )

    wc = count_words(text)
    return text, wc


def read_file(path: Path) -> tuple[str, int]:
    """
    Read a local .txt or .html file.
    Returns (clean_text, word_count).
    """
    if not path.exists():
        raise FetchError(f"File not found: {path}")

    raw = path.read_text(encoding="utf-8", errors="replace")

    if path.suffix.lower() in (".html", ".htm"):
        text = trafilatura.extract(raw, include_tables=True) or raw
    else:
        text = raw

    if not text.strip():
        raise FetchError(f"File is empty or contains no extractable text: {path}")

    return text, count_words(text)


def count_words(text: str) -> int:
    return len(text.split())


async def fetch_url_async(url: str, client: httpx.AsyncClient) -> tuple[str, int]:
    """Async version for bulk scanning."""
    try:
        response = await client.get(
            url,
            timeout=30,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; aidar/0.1; "
                    "+https://github.com/yourusername/aidar)"
                )
            },
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise FetchError(f"HTTP {e.response.status_code} fetching {url}") from e
    except httpx.RequestError as e:
        raise FetchError(f"Request failed for {url}: {e}") from e

    text = trafilatura.extract(
        response.text,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
    )

    if not text or len(text.split()) < 20:
        raise FetchError(f"No extractable text from {url}")

    return text, count_words(text)
