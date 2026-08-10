from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

import httpx


class WaybackError(Exception):
    """A structured, non-scoring Wayback discovery failure."""

    def __init__(self, message: str, reason: str = "wayback_error") -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class WaybackSnapshot:
    original_url: str
    snapshot_url: str
    timestamp: str


def discover_wayback_snapshots(
    domain: str,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = 100,
    timeout: float = 30.0,
) -> list[WaybackSnapshot]:
    """Opt-in CDX discovery of bounded HTML snapshots for a domain."""
    params = {
        "url": f"{domain.rstrip('/') }/*",
        "output": "json",
        "filter": ["statuscode:200", "mimetype:text/html"],
        "fl": "timestamp,original,statuscode,mimetype",
        "collapse": "urlkey",
        "limit": str(max(1, min(limit, 1000))),
    }
    if from_date:
        params["from"] = from_date.strftime("%Y%m%d")
    if to_date:
        params["to"] = to_date.strftime("%Y%m%d")
    try:
        response = httpx.get(
            "https://web.archive.org/cdx/search/cdx",
            params=params,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "aidar/0.5 (historical opt-in discovery)"},
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise WaybackError(f"Wayback HTTP {exc.response.status_code}", "http_error") from exc
    except (httpx.RequestError, json.JSONDecodeError, ValueError) as exc:
        raise WaybackError(f"Wayback request failed: {exc}", "network_error") from exc

    if not isinstance(payload, list) or len(payload) < 2:
        return []
    snapshots: list[WaybackSnapshot] = []
    for row in payload[1:]:
        if not isinstance(row, list) or len(row) < 2:
            continue
        timestamp, original = str(row[0]), str(row[1])
        if not timestamp or not original.startswith(("http://", "https://")):
            continue
        snapshots.append(
            WaybackSnapshot(
                original_url=original,
                snapshot_url=f"https://web.archive.org/web/{timestamp}id_/{original}",
                timestamp=timestamp,
            )
        )
    return snapshots
