from __future__ import annotations

import multiprocessing
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from aidar import __version__
from aidar.output.renderer import console

_COMMON_FEED_PATHS = [
    "/feed.xml",
    "/feed",
    "/rss.xml",
    "/rss",
    "/atom.xml",
    "/feeds/posts/default",
    "/feeds/all.atom.xml",
    "/index.xml",
]


def normalize_domain(domain: str) -> str:
    """Accept a hostname or URL and return its scheme and host."""
    if not domain.startswith(("http://", "https://")):
        domain = "https://" + domain
    parsed = urlparse(domain)
    return f"{parsed.scheme}://{parsed.netloc}"


def _sitemap_worker(base_url: str, queue: Any) -> None:
    try:
        from trafilatura.sitemaps import sitemap_search

        queue.put(list(sitemap_search(base_url) or []))
    except Exception:
        queue.put([])


def _sitemap_direct(base_url: str) -> list[str]:
    candidates = [
        f"{base_url.rstrip('/')}/sitemap.xml",
        f"{base_url.rstrip('/')}/sitemap_index.xml",
    ]
    headers = {"User-Agent": f"Mozilla/5.0 (compatible; aidar/{__version__})"}
    for sitemap_url in candidates:
        try:
            response = httpx.get(
                sitemap_url,
                timeout=15,
                follow_redirects=True,
                headers=headers,
            )
            if response.status_code != 200:
                continue
            raw_locations = re.findall(r"<loc>([^<]+)</loc>", response.text)
            urls = []
            for location in raw_locations:
                location = location.strip()
                if location.startswith(("http://", "https://")):
                    urls.append(location)
                elif location.startswith("/"):
                    urls.append(base_url.rstrip("/") + location)
            if urls:
                return urls
        except Exception:
            continue
    return []


def from_sitemap(base_url: str, timeout: int = 30) -> list[str]:
    """Discover sitemap URLs with a timeout and relative-location fallback."""
    queue: Any = multiprocessing.Queue()
    process = multiprocessing.Process(target=_sitemap_worker, args=(base_url, queue))
    process.start()
    process.join(timeout=timeout)
    if process.is_alive():
        console.print(f"[yellow]Sitemap discovery timed out after {timeout}s.[/yellow]")
        process.terminate()
        process.join()
        return []
    urls = queue.get() if not queue.empty() else []
    return urls or _sitemap_direct(base_url)


def from_rss(base_url: str) -> list[str]:
    """Discover article URLs through feed autodiscovery and common feed paths."""
    try:
        from trafilatura.feeds import find_feed_urls

        urls = find_feed_urls(base_url)
        articles = [url for url in (urls or []) if not url.endswith((".xml", ".rss", ".atom"))]
        if articles:
            return articles
        base = base_url.rstrip("/")
        for path in _COMMON_FEED_PATHS:
            urls = find_feed_urls(base + path)
            articles = [
                url for url in (urls or []) if not url.endswith((".xml", ".rss", ".atom"))
            ]
            if articles:
                return articles
    except Exception:
        pass
    return []


def discover_urls(base_url: str, source_type: str = "auto") -> tuple[list[str], str]:
    """Discover URLs through the shared sitemap-then-feed policy."""
    if source_type in ("auto", "sitemap"):
        urls = from_sitemap(base_url)
        if urls:
            return urls, "sitemap"
    if source_type in ("auto", "rss"):
        urls = from_rss(base_url)
        if urls:
            return urls, "RSS/Atom"
    return [], source_type
