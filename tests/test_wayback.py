from __future__ import annotations

from datetime import date

import httpx

from aidar.core.wayback import discover_wayback_snapshots


def test_wayback_discovery_is_opt_in_and_bounded(monkeypatch) -> None:
    seen: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[list[str]]:
            return [
                ["timestamp", "original", "statuscode", "mimetype"],
                ["20200102030405", "https://example.com/post", "200", "text/html"],
            ]

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        seen["url"] = url
        seen["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr(httpx, "get", fake_get)
    snapshots = discover_wayback_snapshots(
        "example.com",
        from_date=date(2020, 1, 1),
        to_date=date(2020, 12, 31),
        limit=10,
    )

    assert snapshots[0].original_url == "https://example.com/post"
    assert snapshots[0].snapshot_url.endswith("/https://example.com/post")
    assert seen["url"] == "https://web.archive.org/cdx/search/cdx"
    params = seen["kwargs"]["params"]
    assert params["limit"] == "10"
    assert params["from"] == "20200101"
    assert params["to"] == "20201231"
