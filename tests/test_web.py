from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from aidar.core.fetcher import FetchResult
from aidar.models.config import AppConfig, WeightConfig
from web import main as web_main


def test_domain_share_link_uses_public_site_url() -> None:
    template = Path("web/templates/domain.html").read_text()

    assert "https%3A%2F%2Faidar.lol%2Fdomain%2F" in template
    assert "airdar.lol" not in template


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
    monkeypatch.setattr(
        "aidar.core.discovery.discover_urls",
        lambda base_url: (["https://example.com/post"], "sitemap"),
    )

    web_main._scan_status.clear()
    web_main._scan_summaries.clear()
    asyncio.run(web_main._run_domain_scan("example.com", limit=1))

    assert seen["raw_html"] == "<html><strong>Example</strong></html>"
    assert web_main._scan_summaries["example.com"]["saved"] == 1


def test_read_only_mode_rejects_mutations(monkeypatch) -> None:
    monkeypatch.setenv("AIDAR_READ_ONLY", "true")
    assert web_main._read_only() is True

    async def run() -> None:
        with pytest.raises(web_main.HTTPException) as exc:
            await web_main.submit_site(object(), object())
        assert exc.value.status_code == 403
        with pytest.raises(web_main.HTTPException) as delete_exc:
            await web_main.admin_delete_domain(object())
        assert delete_exc.value.status_code == 403

    asyncio.run(run())
