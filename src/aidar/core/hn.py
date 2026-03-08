from __future__ import annotations

from collections import Counter
from urllib.parse import urlparse

import httpx

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"
HN_EXCLUDED_HOSTS = {"news.ycombinator.com"}


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


def get_hn_trending_domains(
    *,
    story_limit: int = 200,
    top_domains: int = 25,
    min_story_count: int = 2,
    timeout: float = 12.0,
) -> list[tuple[str, int]]:
    """
    Return trending external domains from HN top stories.

    Ranking metric: count of stories per domain in the sampled top list.
    """
    limit = max(1, min(int(story_limit), 500))
    keep = max(1, int(top_domains))
    minimum = max(1, int(min_story_count))

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            top_ids_resp = client.get(f"{HN_API_BASE}/topstories.json")
            top_ids_resp.raise_for_status()
            story_ids = top_ids_resp.json()[:limit]

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
    except Exception:
        return []

    ranked = [(domain, count) for domain, count in counts.most_common() if count >= minimum]
    return ranked[:keep]
