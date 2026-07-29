from __future__ import annotations

import asyncio
import sys
import types

from aidar.core.fetcher import FetchResult
from aidar.models.config import AppConfig, WeightConfig
from web import main as web_main


def test_normalize_submitted_domain_keeps_host_intact() -> None:
    assert web_main._normalize_submitted_domain("https://theverge.com") == "theverge.com"
    assert web_main._normalize_submitted_domain("http://huggingface.co") == "huggingface.co"
    assert web_main._normalize_submitted_domain("example.com/path") == "example.com"


def test_web_background_scan_passes_raw_html(monkeypatch, tmp_path) -> None:
    seen: dict[str, str | None] = {}

    class FakeAnalyzer:
        def run(self, text: str, word_count: int, raw_html: str | None = None):
            seen["raw_html"] = raw_html
            from aidar.models.result import ScoreVector

            return ScoreVector()

    config = AppConfig(patterns_dir=str(tmp_path), weights=WeightConfig())
    monkeypatch.setattr(web_main, "_get_analyzer", lambda: (FakeAnalyzer(), config))
    monkeypatch.setattr(web_main, "get_conn", lambda: object())
    monkeypatch.setattr("aidar.db.queries.url_already_scanned", lambda conn, url: False)
    monkeypatch.setattr("aidar.db.queries.store_result", lambda conn, result: None)

    async def fake_fetch_url_async(url: str, client: object) -> FetchResult:
        return FetchResult(
            text="hello world " * 150,
            word_count=300,
            raw_html="<html><strong>Example</strong></html>",
        )

    monkeypatch.setattr("aidar.core.fetcher.fetch_url_async", fake_fetch_url_async)
    monkeypatch.setitem(
        sys.modules,
        "trafilatura.sitemaps",
        types.SimpleNamespace(sitemap_search=lambda base_url: ["https://example.com/post"]),
    )
    monkeypatch.setitem(
        sys.modules,
        "trafilatura.feeds",
        types.SimpleNamespace(find_feed_urls=lambda base_url: []),
    )

    web_main._scan_status.clear()
    asyncio.run(web_main._run_domain_scan("example.com", limit=1))

    assert seen["raw_html"] == "<html><strong>Example</strong></html>"
