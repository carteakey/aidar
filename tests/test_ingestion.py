from __future__ import annotations

import asyncio
import json

import httpx
from click.testing import CliRunner

from aidar.cli.main import aidar
from aidar.core.discovery import discover_urls
from aidar.core.fetcher import FetchError, FetchResult, fetch_url_async
from aidar.core.ingestion import ScanSummary, filter_prose_urls, scan_urls
from aidar.models.config import AppConfig, WeightConfig
from aidar.models.result import ScoreVector


class FakeAnalyzer:
    def run(self, text: str, word_count: int, raw_html: str | None = None) -> ScoreVector:
        return ScoreVector()


def test_mixed_sitemap_filters_navigation_docs_assets_external_and_duplicates() -> None:
    urls = [
        "https://example.com/posts/one",
        "https://example.com/posts/one",
        "https://example.com/tag/python/",
        "https://example.com/doc/paper",
        "https://example.com/files/report.pdf",
        "https://cdn.example.net/post",
        "https://example.com/posts/working-with-node.js/",
        "https://example.com/posts/two",
    ]

    result = filter_prose_urls(urls, base_url="https://example.com")

    assert result.kept == [
        "https://example.com/posts/one",
        "https://example.com/posts/working-with-node.js/",
        "https://example.com/posts/two",
    ]
    assert result.rejected == {
        "duplicate": 1,
        "non_prose_path": 2,
        "non_prose_extension": 1,
        "external_host": 1,
    }


def test_large_mixed_sitemap_keeps_only_article_routes() -> None:
    articles = [f"https://example.com/2026/post-{index}" for index in range(600)]
    navigation = [f"https://example.com/tag/topic-{index}/" for index in range(300)]
    assets = [f"https://example.com/files/report-{index}.pdf" for index in range(100)]

    result = filter_prose_urls(articles + navigation + assets, base_url="https://example.com")

    assert result.kept == articles
    assert result.rejected == {"non_prose_path": 300, "non_prose_extension": 100}


def test_discovery_falls_back_to_rss(monkeypatch) -> None:
    monkeypatch.setattr("aidar.core.discovery.from_sitemap", lambda base_url: [])
    monkeypatch.setattr(
        "aidar.core.discovery.from_rss",
        lambda base_url: ["https://example.com/posts/from-feed"],
    )

    urls, method = discover_urls("https://example.com")

    assert urls == ["https://example.com/posts/from-feed"]
    assert method == "RSS/Atom"


def test_fetch_reports_403_without_retry() -> None:
    calls = 0

    def blocked(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(403, request=request)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(blocked)) as client:
            try:
                await fetch_url_async("https://example.com/blocked", client)
            except FetchError as exc:
                assert exc.reason == "http_403"
            else:
                raise AssertionError("expected FetchError")

    asyncio.run(run())
    assert calls == 1


def test_fetch_reports_timeout_without_retry() -> None:
    calls = 0

    def timeout(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("slow publisher", request=request)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
            try:
                await fetch_url_async("https://example.com/slow", client)
            except FetchError as exc:
                assert exc.reason == "timeout"
            else:
                raise AssertionError("expected FetchError")

    asyncio.run(run())
    assert calls == 1


def test_fetch_follows_redirect_and_extracts_prose() -> None:
    def redirect(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(302, headers={"location": "/article"}, request=request)
        html = "<html><body><article><p>" + ("useful prose " * 80) + "</p></article></body></html>"
        return httpx.Response(
            200,
            text=html,
            headers={"content-type": "text/html"},
            request=request,
        )

    async def run() -> FetchResult:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(redirect), follow_redirects=True
        ) as client:
            return await fetch_url_async("https://example.com/old", client)

    result = asyncio.run(run())
    assert result.word_count >= 80


def test_scan_outcomes_separate_short_non_english_and_saved(monkeypatch) -> None:
    async def fake_fetch(url: str, client: object) -> FetchResult:
        if url.endswith("short"):
            return FetchResult("too short", 2, language="en")
        if url.endswith("french"):
            return FetchResult("texte " * 100, 100, language="fr")
        return FetchResult("article " * 100, 100, language="en")

    monkeypatch.setattr("aidar.core.fetcher.fetch_url_async", fake_fetch)
    config = AppConfig(patterns_dir="patterns", weights=WeightConfig())
    outcomes = asyncio.run(
        scan_urls(
            [
                "https://example.com/short",
                "https://example.com/french",
                "https://example.com/article",
            ],
            FakeAnalyzer(),
            config,
            min_words=50,
        )
    )
    summary = ScanSummary(discovered=3)
    summary.record_outcomes(outcomes)

    assert [outcome.reason for outcome in outcomes] == ["short_text", "non_english", None]
    assert summary.as_dict() == {
        "discovered": 3,
        "filtered": 0,
        "attempted": 3,
        "saved": 1,
        "failed": 2,
        "reasons": {"non_english": 1, "short_text": 1},
    }


def test_scan_rejects_external_redirect(monkeypatch) -> None:
    async def fake_fetch(url: str, client: object) -> FetchResult:
        return FetchResult(
            "article " * 100,
            100,
            language="en",
            final_url="https://accounts.example.net/login",
        )

    monkeypatch.setattr("aidar.core.fetcher.fetch_url_async", fake_fetch)
    config = AppConfig(patterns_dir="patterns", weights=WeightConfig())
    outcomes = asyncio.run(
        scan_urls(
            ["https://example.com/article"],
            FakeAnalyzer(),
            config,
        )
    )

    assert outcomes[0].reason == "external_redirect"
    assert outcomes[0].result is None


def test_corpus_audit_flags_existing_non_prose_without_deleting(tmp_path) -> None:
    from aidar.db.database import get_connection

    db_path = tmp_path / "audit.db"
    conn = get_connection(db_path)
    conn.executemany(
        """
        INSERT INTO scans
            (url, domain, word_count, score, label, score_json, scanned_at)
        VALUES (?, 'example.com', ?, 0, 'LIKELY HUMAN', '{}', '2026-01-01T00:00:00')
        """,
        [
            ("https://example.com/tag/python/", 500),
            ("https://example.com/article", 12),
            ("https://example.com/good-article", 500),
        ],
    )
    conn.commit()

    result = CliRunner().invoke(
        aidar,
        ["--output", "json", "audit-corpus", "--db", str(db_path)],
    )

    assert result.exit_code == 0
    report = json.loads(result.output)
    assert report["flagged_rows"] == 2
    assert report["reasons"] == {"non_prose_path": 1, "short_text": 1}
    assert conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0] == 3
