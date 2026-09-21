from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

import httpx

from aidar.core.analyzer import Analyzer
from aidar.core.fetcher import FetchError, FetchResult
from aidar.core.scorer import compute_aggregate
from aidar.models.config import AppConfig
from aidar.models.result import AggregateResult

_NON_PROSE_SUFFIXES = {
    ".7z",
    ".avi",
    ".css",
    ".csv",
    ".doc",
    ".docx",
    ".epub",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".mov",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rar",
    ".rss",
    ".svg",
    ".tar",
    ".tsv",
    ".wav",
    ".webm",
    ".webp",
    ".xls",
    ".xlsx",
    ".xml",
    ".zip",
}
_NON_PROSE_SEGMENTS = {
    "archive",
    "archives",
    "author",
    "authors",
    "category",
    "categories",
    "doc",
    "docs",
    "feed",
    "feeds",
    "login",
    "page",
    "search",
    "signin",
    "tag",
    "tags",
}


@dataclass(frozen=True)
class URLFilterResult:
    kept: list[str]
    rejected: Counter[str]


@dataclass(frozen=True)
class ScanOutcome:
    url: str
    result: AggregateResult | None = None
    reason: str | None = None


@dataclass
class ScanSummary:
    discovered: int = 0
    filtered: int = 0
    attempted: int = 0
    saved: int = 0
    failed: int = 0
    reasons: Counter[str] = field(default_factory=Counter)

    def record_rejections(self, rejected: Counter[str]) -> None:
        self.filtered += sum(rejected.values())
        self.reasons.update(rejected)

    def record_outcomes(self, outcomes: list[ScanOutcome]) -> None:
        self.attempted += len(outcomes)
        for outcome in outcomes:
            if outcome.result is not None:
                self.saved += 1
            else:
                self.failed += 1
                self.reasons[outcome.reason or "unknown_failure"] += 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "discovered": self.discovered,
            "filtered": self.filtered,
            "attempted": self.attempted,
            "saved": self.saved,
            "failed": self.failed,
            "reasons": dict(sorted(self.reasons.items())),
        }


def classify_url(url: str, base_url: str | None = None) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "invalid_url"
    if base_url:
        expected = urlparse(base_url).netloc.lower().removeprefix("www.")
        actual = parsed.netloc.lower().removeprefix("www.")
        if actual != expected:
            return "external_host"
    suffix = "" if parsed.path.endswith("/") else PurePosixPath(parsed.path.lower()).suffix
    if suffix in _NON_PROSE_SUFFIXES:
        return "non_prose_extension"
    segments = {part.lower() for part in parsed.path.split("/") if part}
    if segments & _NON_PROSE_SEGMENTS:
        return "non_prose_path"
    return None


def filter_prose_urls(
    urls: list[str],
    *,
    base_url: str | None = None,
    skip_patterns: tuple[str, ...] = (),
) -> URLFilterResult:
    kept: list[str] = []
    rejected: Counter[str] = Counter()
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            rejected["duplicate"] += 1
            continue
        seen.add(url)
        reason = classify_url(url, base_url)
        if reason is None and any(pattern in url for pattern in skip_patterns):
            reason = "custom_skip_pattern"
        if reason:
            rejected[reason] += 1
        else:
            kept.append(url)
    return URLFilterResult(kept=kept, rejected=rejected)


def validate_fetch(fetch: FetchResult, min_words: int, requested_url: str | None = None) -> str | None:
    if requested_url and fetch.final_url:
        requested_host = urlparse(requested_url).netloc.lower().removeprefix("www.")
        final_host = urlparse(fetch.final_url).netloc.lower().removeprefix("www.")
        if requested_host != final_host:
            return "external_redirect"
        redirected_reason = classify_url(fetch.final_url)
        if redirected_reason:
            return f"redirect_{redirected_reason}"
    if fetch.word_count < min_words:
        return "short_text"
    if fetch.language and fetch.language.lower().split("-")[0] != "en":
        return "non_english"
    return None


async def scan_one(
    url: str,
    analyzer: Analyzer,
    config: AppConfig,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    *,
    delay: float = 0.0,
    min_words: int = 50,
) -> ScanOutcome:
    async with semaphore:
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            from aidar.core.fetcher import fetch_url_async

            fetch = await fetch_url_async(url, client)
            reason = validate_fetch(fetch, min_words, url)
            if reason:
                return ScanOutcome(url=url, reason=reason)
            vector = analyzer.run(fetch.text, fetch.word_count, raw_html=fetch.raw_html)
            return ScanOutcome(
                url=url,
                result=compute_aggregate(
                    vector,
                    config,
                    url=url,
                    word_count=fetch.word_count,
                    published_date=fetch.published_date,
                    title=fetch.title,
                ),
            )
        except FetchError as exc:
            return ScanOutcome(url=url, reason=exc.reason)
        except Exception:
            return ScanOutcome(url=url, reason="unexpected_error")


async def scan_urls(
    urls: list[str],
    analyzer: Analyzer,
    config: AppConfig,
    *,
    concurrency: int = 10,
    delay: float = 0.0,
    min_words: int = 50,
    client: httpx.AsyncClient | None = None,
) -> list[ScanOutcome]:
    semaphore = asyncio.Semaphore(concurrency)

    async def run(active_client: httpx.AsyncClient) -> list[ScanOutcome]:
        tasks = [
            scan_one(
                url,
                analyzer,
                config,
                active_client,
                semaphore,
                delay=delay,
                min_words=min_words,
            )
            for url in urls
        ]
        return await asyncio.gather(*tasks)

    if client is not None:
        return await run(client)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as owned_client:
        return await run(owned_client)
