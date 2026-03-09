from __future__ import annotations

from collections import Counter
from urllib.parse import urlparse

import httpx

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"
HN_EXCLUDED_HOSTS = {"news.ycombinator.com"}

# Map friendly story type names to HN API endpoints
_STORY_ENDPOINTS = {
    "top": "topstories",
    "new": "newstories",
    "best": "beststories",
}


def _normalize_host(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    host = (parsed.netloc or "").lower().strip()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    if host in HN_EXCLUDED_HOSTS:
        return None
    return host


def _fetch_domains_from_endpoint(
    client: httpx.Client,
    endpoint: str,
    story_limit: int,
) -> Counter:
    """Fetch story IDs from one HN endpoint and count domains."""
    resp = client.get(f"{HN_API_BASE}/{endpoint}.json")
    resp.raise_for_status()
    story_ids = resp.json()[:story_limit]
    counts: Counter[str] = Counter()
    for story_id in story_ids:
        item_resp = client.get(f"{HN_API_BASE}/item/{story_id}.json")
        item_resp.raise_for_status()
        item = item_resp.json() or {}
        url = item.get("url")
        if not url:
            continue
        host = _normalize_host(url)
        if host:
            counts[host] += 1
    return counts


def get_hn_trending_domains(
    *,
    story_limit: int = 200,
    top_domains: int = 25,
    min_story_count: int = 2,
    story_type: str = "top",
    timeout: float = 12.0,
) -> list[tuple[str, int]]:
    """
    Return trending external domains from HN stories.

    story_type: "top" (default), "new", or "best".
    Ranking metric: count of stories per domain in the sampled list.
    For "new", min_story_count defaults to 1 since new stories rarely share domains.
    """
    limit = max(1, min(int(story_limit), 500))
    keep = max(1, int(top_domains))
    # New stories are unique enough that requiring 2+ would exclude everything
    minimum = min_story_count if story_type != "new" else min(min_story_count, 1)
    endpoint = _STORY_ENDPOINTS.get(story_type, "topstories")

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            counts = _fetch_domains_from_endpoint(client, endpoint, limit)
    except Exception:
        return []

    ranked = [(domain, count) for domain, count in counts.most_common() if count >= minimum]
    return ranked[:keep]
