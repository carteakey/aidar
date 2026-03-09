from __future__ import annotations

import sys
from urllib.parse import urlparse

import click

from aidar.cli.main import aidar
from aidar.output.renderer import console


def _normalize_domain(domain: str) -> str:
    """Accept 'example.com' or 'https://example.com', return base URL."""
    if not domain.startswith(("http://", "https://")):
        domain = "https://" + domain
    parsed = urlparse(domain)
    return f"{parsed.scheme}://{parsed.netloc}"


@aidar.command()
@click.argument("domain")
@click.option(
    "--output", "-o",
    default=None,
    type=click.Path(dir_okay=False, writable=True),
    help="Write URLs to file instead of stdout",
)
@click.option(
    "--limit",
    default=0,
    show_default=True,
    help="Max URLs to return (0 = all)",
)
@click.option(
    "--type", "source_type",
    type=click.Choice(["auto", "sitemap", "rss"]),
    default="auto",
    show_default=True,
    help="Discovery method",
)
@click.option(
    "--filter-ext",
    default=".html,.htm,/",
    show_default=True,
    help="Comma-separated URL suffixes/patterns to keep (empty = keep all)",
)
@click.pass_context
def discover(
    ctx: click.Context,
    domain: str,
    output: str | None,
    limit: int,
    source_type: str,
    filter_ext: str,
) -> None:
    """Discover article URLs for a domain via sitemap or RSS feed.

    Outputs one URL per line to stdout (or --output file).
    Pipe directly into --batch: aidar discover example.com -o urls.txt
    """
    base_url = _normalize_domain(domain)
    urls: list[str] = []

    click.echo(f"Discovering URLs for {base_url} ...", err=True)

    if source_type in ("auto", "sitemap"):
        urls = _from_sitemap(base_url)
        if urls:
            click.echo(f"Found {len(urls)} URLs via sitemap.", err=True)

    if not urls and source_type in ("auto", "rss"):
        urls = _from_rss(base_url)
        if urls:
            click.echo(f"Found {len(urls)} URLs via RSS/Atom feed.", err=True)

    if not urls:
        click.echo(
            f"No URLs found for {base_url}. "
            "Try --type rss or --type sitemap explicitly.",
            err=True,
        )
        raise SystemExit(1)

    # Filter to article-like URLs
    if filter_ext.strip():
        exts = [e.strip() for e in filter_ext.split(",") if e.strip()]
        filtered = [u for u in urls if any(u.endswith(e) or "/" in u.split(base_url)[-1] for e in exts)]
        # If filtering is too aggressive, fall back to all
        if len(filtered) < 3:
            filtered = urls
        urls = filtered

    # Deduplicate, preserve order
    seen: set[str] = set()
    deduped = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    urls = deduped

    if limit > 0:
        urls = urls[:limit]

    click.echo(f"Returning {len(urls)} URLs.", err=True)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write("\n".join(urls) + "\n")
        click.echo(f"Saved to {output}", err=True)
    else:
        for url in urls:
            click.echo(url)


def _sitemap_worker(base_url: str, queue) -> None:
    try:
        from trafilatura.sitemaps import sitemap_search
        urls = list(sitemap_search(base_url) or [])
        queue.put(urls)
    except Exception:
        queue.put([])


def _sitemap_direct(base_url: str) -> list[str]:
    """
    Fallback sitemap parser for sitemaps that use relative <loc> entries.
    trafilatura's sitemap_search silently drops relative URLs, so this fetches
    sitemap.xml directly and resolves all <loc> values against the base URL.
    Tries sitemap.xml and sitemap_index.xml.
    """
    import re
    import httpx

    candidates = [
        f"{base_url.rstrip('/')}/sitemap.xml",
        f"{base_url.rstrip('/')}/sitemap_index.xml",
    ]
    headers = {"User-Agent": "Mozilla/5.0 (compatible; aidar/0.1)"}

    for sitemap_url in candidates:
        try:
            r = httpx.get(sitemap_url, timeout=15, follow_redirects=True, headers=headers)
            if r.status_code != 200:
                continue
            raw_locs = re.findall(r"<loc>([^<]+)</loc>", r.text)
            if not raw_locs:
                continue
            urls = []
            for loc in raw_locs:
                loc = loc.strip()
                if loc.startswith(("http://", "https://")):
                    urls.append(loc)
                elif loc.startswith("/"):
                    urls.append(base_url.rstrip("/") + loc)
            if urls:
                return urls
        except Exception:
            continue
    return []


def _from_sitemap(base_url: str, timeout: int = 30) -> list[str]:
    """
    Try to extract URLs from sitemap.xml / sitemap_index.xml.
    First attempts trafilatura's sitemap_search (handles complex sitemap indexes).
    Falls back to direct XML parsing when the sitemap uses relative <loc> entries.
    """
    import multiprocessing
    queue = multiprocessing.Queue()
    p = multiprocessing.Process(target=_sitemap_worker, args=(base_url, queue))
    p.start()
    p.join(timeout=timeout)
    if p.is_alive():
        console.print(f"[yellow]Sitemap discovery timed out after {timeout}s.[/yellow]")
        p.terminate()
        p.join()
        return []
    urls = queue.get() if not queue.empty() else []
    if not urls:
        # trafilatura returned nothing — try direct parse (handles relative <loc> sitemaps)
        urls = _sitemap_direct(base_url)
    return urls


_COMMON_FEED_PATHS = [
    "/feed.xml", "/feed", "/rss.xml", "/rss", "/atom.xml",
    "/feeds/posts/default", "/feeds/all.atom.xml", "/index.xml",
]


def _from_rss(base_url: str) -> list[str]:
    """Try to find and parse RSS/Atom feeds. find_feed_urls returns article URLs directly."""
    try:
        from trafilatura.feeds import find_feed_urls
        urls = find_feed_urls(base_url)
        article_urls = [u for u in (urls or []) if not u.endswith((".xml", ".rss", ".atom"))]
        if article_urls:
            return article_urls
        # Some SPAs (e.g. LessWrong) don't expose feed autodiscovery links in HTML.
        # Try well-known feed paths directly.
        base = base_url.rstrip("/")
        for path in _COMMON_FEED_PATHS:
            direct_urls = find_feed_urls(base + path)
            article_urls = [u for u in (direct_urls or []) if not u.endswith((".xml", ".rss", ".atom"))]
            if article_urls:
                return article_urls
    except Exception:
        pass
    return []
