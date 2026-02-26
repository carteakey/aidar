from __future__ import annotations

import asyncio
import io
import json
import os
import time
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from aidar.db.database import get_connection
from aidar.db.queries import (
    get_corpus_percentile,
    get_domain_leaderboard,
    get_domain_scans,
    get_domain_stats,
    get_domain_trend,
    get_global_stats,
    get_pattern_stats,
)

DB_PATH = os.environ.get("AIDAR_DB", "aidar.db")

app = FastAPI(title="aidar.lol", docs_url=None, redoc_url=None)

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# In-memory scan status (per-dyno). NOTE: on Heroku without Postgres,
# scans are written to an ephemeral SQLite and won't survive a dyno restart.
# Add DATABASE_URL (Heroku Postgres) to make web-triggered scans persistent.
_scan_status: dict[str, str] = {}
_scan_last_completed: dict[str, float] = {}  # domain → unix timestamp

RATE_LIMIT_SECONDS = 60 * 60 * 6  # 6 hours between web-triggered rescans

# Lazy-loaded analyzer singleton (loaded once at first scan request)
_analyzer = None
_analyzer_config = None


def _get_analyzer():
    global _analyzer, _analyzer_config
    if _analyzer is None:
        from aidar.core.analyzer import Analyzer
        from aidar.models.config import AppConfig
        from aidar.patterns.loader import load_patterns, load_weight_config
        from aidar.patterns.registry import PatternRegistry

        pd_env = os.environ.get("AIDAR_PATTERNS_DIR")
        pd = Path(pd_env) if pd_env else Path(__file__).parent.parent / "patterns"
        patterns = load_patterns(pd)
        weights = load_weight_config(pd)
        registry = PatternRegistry(patterns)
        _analyzer = Analyzer(registry)
        _analyzer_config = AppConfig(patterns_dir=str(pd), weights=weights)
    return _analyzer, _analyzer_config


async def _run_domain_scan(domain: str, limit: int = 200) -> None:
    """Background task: discover → filter → scan → store results for a domain."""
    from urllib.parse import urlparse

    from aidar.core.fetcher import fetch_url_async
    from aidar.core.scorer import compute_aggregate
    from aidar.db.queries import store_result, url_already_scanned

    def _normalize(d: str) -> str:
        if not d.startswith(("http://", "https://")):
            d = "https://" + d
        p = urlparse(d)
        return f"{p.scheme}://{p.netloc}"

    def _discover(base_url: str) -> list[str]:
        try:
            from trafilatura.sitemaps import sitemap_search
            urls = list(sitemap_search(base_url) or [])
            if urls:
                return urls
        except Exception:
            pass
        try:
            from trafilatura.feeds import find_feed_urls
            urls = find_feed_urls(base_url) or []
            return [u for u in urls if not u.endswith((".xml", ".rss", ".atom"))]
        except Exception:
            return []

    _scan_status[domain] = "running"
    try:
        base_url = _normalize(domain)
        urls = _discover(base_url)
        if not urls:
            _scan_status[domain] = "error:no_urls"
            return

        # Filter common non-article URL patterns
        skip = ("/tag/", "/page/", "/author/", "/category/")
        urls = [u for u in urls if not any(p in u for p in skip)]

        conn = get_conn()
        urls = [u for u in urls if not url_already_scanned(conn, u)][:limit]
        if not urls:
            _scan_status[domain] = "done"
            return

        analyzer, config = _get_analyzer()
        semaphore = asyncio.Semaphore(5)

        async def _scan_one(url: str, client: httpx.AsyncClient):
            async with semaphore:
                try:
                    fetch = await fetch_url_async(url, client)
                    sv = analyzer.run(fetch.text, fetch.word_count)
                    return compute_aggregate(
                        sv, config,
                        url=url,
                        word_count=fetch.word_count,
                        published_date=fetch.published_date,
                        title=fetch.title,
                    )
                except Exception:
                    return None

        async with httpx.AsyncClient(timeout=30) as client:
            results = await asyncio.gather(*[_scan_one(u, client) for u in urls])

        for r in results:
            if r is not None:
                store_result(conn, r)

        _scan_status[domain] = "done"
        _scan_last_completed[domain] = time.time()
    except Exception:
        _scan_status[domain] = "error"


def get_conn():
    return get_connection(DB_PATH)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, q: str = ""):
    conn = get_conn()
    leaderboard = get_domain_leaderboard(conn, limit=100)
    stats = get_global_stats(conn)
    # Add percentile to each leaderboard row
    total = stats.get("total_scans") or 1
    for row in leaderboard:
        below = conn.execute(
            "SELECT COUNT(*) FROM scans WHERE domain != '' GROUP BY domain HAVING AVG(score) <= ?",
            (row["avg_score"],),
        ).fetchall()
        row["percentile"] = round(len(below) / max(len(leaderboard), 1) * 100)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "leaderboard": leaderboard, "stats": stats, "q": q},
    )


@app.post("/submit", response_class=HTMLResponse)
async def submit_site(request: Request, background_tasks: BackgroundTasks):
    from fastapi.responses import RedirectResponse

    form = await request.form()
    domain = str(form.get("domain", "")).strip().lstrip("https://").lstrip("http://").rstrip("/")
    if not domain:
        conn = get_conn()
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "leaderboard": get_domain_leaderboard(conn, limit=100),
             "stats": get_global_stats(conn), "submit_error": "Enter a domain."},
        )

    # Rate limit: already in flight?
    if _scan_status.get(domain) in ("queued", "running"):
        return RedirectResponse(url=f"/domain/{domain}", status_code=303)

    # Rate limit: scanned too recently (in-memory)
    last = _scan_last_completed.get(domain, 0)
    if time.time() - last < RATE_LIMIT_SECONDS:
        return RedirectResponse(url=f"/domain/{domain}", status_code=303)

    # Rate limit: check DB for recent scan (survives dyno restarts)
    conn = get_conn()
    stats = get_domain_stats(conn, domain)
    if stats.get("latest"):
        try:
            from datetime import datetime, timezone
            latest_dt = datetime.fromisoformat(stats["latest"].replace("Z", "+00:00"))
            age_s = (datetime.now(timezone.utc) - latest_dt).total_seconds()
            if age_s < RATE_LIMIT_SECONDS:
                return RedirectResponse(url=f"/domain/{domain}", status_code=303)
        except Exception:
            pass

    _scan_status[domain] = "queued"
    background_tasks.add_task(_run_domain_scan, domain)
    return RedirectResponse(url=f"/domain/{domain}", status_code=303)


@app.get("/domain/{domain:path}", response_class=HTMLResponse)
async def domain_page(request: Request, domain: str):
    conn = get_conn()
    stats = get_domain_stats(conn, domain)
    scan_status = _scan_status.get(domain)
    if stats.get("scans", 0) == 0:
        status_code = 200 if scan_status in ("queued", "running") else 404
        return templates.TemplateResponse(
            "domain_missing.html",
            {"request": request, "domain": domain, "scan_status": scan_status},
            status_code=status_code,
        )
    scans = get_domain_scans(conn, domain, limit=100)
    trend = get_domain_trend(conn, domain)
    percentile = get_corpus_percentile(conn, int(stats.get("avg_score", 0)))

    for scan in scans:
        try:
            scan["categories"] = json.loads(scan.get("score_json") or "{}")
        except Exception:
            scan["categories"] = {}

    return templates.TemplateResponse(
        "domain.html",
        {
            "request": request,
            "domain": domain,
            "stats": stats,
            "scans": scans,
            "trend": trend,
            "percentile": percentile,
        },
    )


@app.get("/patterns", response_class=HTMLResponse)
async def patterns_page(request: Request):
    conn = get_conn()
    pattern_stats = get_pattern_stats(conn)
    global_stats = get_global_stats(conn)
    return templates.TemplateResponse(
        "patterns.html",
        {"request": request, "patterns": pattern_stats, "stats": global_stats},
    )


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})


@app.get("/api/leaderboard")
async def api_leaderboard(limit: int = 100):
    conn = get_conn()
    return get_domain_leaderboard(conn, limit=limit)


@app.get("/api/domain/{domain:path}")
async def api_domain(domain: str):
    conn = get_conn()
    stats = get_domain_stats(conn, domain)
    if stats.get("scans", 0) == 0:
        raise HTTPException(status_code=404)
    scans = get_domain_scans(conn, domain)
    return {"stats": stats, "scans": scans}


@app.get("/api/scan-status/{domain:path}")
async def api_scan_status(domain: str):
    return {"domain": domain, "status": _scan_status.get(domain, "unknown")}


@app.get("/badge/{domain:path}")
async def badge(domain: str):
    """SVG badge for embedding: ![aidar](https://aidar.lol/badge/example.com)"""
    conn = get_conn()
    stats = get_domain_stats(conn, domain)

    if stats.get("scans", 0) == 0:
        right_text = "no data"
        color = "#9f9f9f"
    else:
        avg = stats["avg_score"]
        right_text = f"{avg}/100"
        if avg >= 65:
            color = "#e05d44"
        elif avg >= 35:
            color = "#dfb317"
        else:
            color = "#4c9"

    left = "aidar"
    lw = len(left) * 7 + 10   # approx pixel width of left label
    rw = len(right_text) * 7 + 10
    total = lw + rw
    lx = lw // 2
    rx = lw + rw // 2

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20">
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r"><rect width="{total}" height="20" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{lw}" height="20" fill="#555"/>
    <rect x="{lw}" width="{rw}" height="20" fill="{color}"/>
    <rect width="{total}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="{lx}" y="15" fill="#010101" fill-opacity=".3">{left}</text>
    <text x="{lx}" y="14">{left}</text>
    <text x="{rx}" y="15" fill="#010101" fill-opacity=".3">{right_text}</text>
    <text x="{rx}" y="14">{right_text}</text>
  </g>
</svg>"""
    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "max-age=3600"})


@app.get("/og/{domain:path}")
async def og_image(domain: str):
    """1200×630 Open Graph preview image for a domain."""
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1200, 630
    BG = (10, 10, 10)
    FG = (212, 212, 212)
    DIM = (102, 102, 102)
    GREEN = (74, 222, 128)
    YELLOW = (250, 204, 21)
    RED = (248, 113, 113)

    conn = get_conn()
    stats = get_domain_stats(conn, domain)
    avg = stats.get("avg_score", 0) if stats.get("scans", 0) else None

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Try to load a decent font; fall back to default
    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 96)
        font_med = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 36)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 24)
    except Exception:
        font_big = ImageFont.load_default(size=96)
        font_med = ImageFont.load_default(size=36)
        font_sm = ImageFont.load_default(size=24)

    # Top-left brand
    draw.text((60, 50), "aidar.lol", font=font_sm, fill=GREEN)

    # Domain name (centered, possibly truncated)
    disp_domain = domain if len(domain) <= 30 else domain[:28] + "…"
    bbox = draw.textbbox((0, 0), disp_domain, font=font_med)
    dw = bbox[2] - bbox[0]
    draw.text(((W - dw) // 2, 180), disp_domain, font=font_med, fill=FG)

    # Score (big, centered)
    if avg is not None:
        score_text = str(int(avg))
        color = RED if avg >= 65 else (YELLOW if avg >= 35 else GREEN)
        bbox2 = draw.textbbox((0, 0), score_text, font=font_big)
        sw = bbox2[2] - bbox2[0]
        draw.text(((W - sw) // 2, 270), score_text, font=font_big, fill=color)

        # Label below score
        label = "LIKELY AI" if avg >= 65 else ("MIXED SIGNALS" if avg >= 35 else "MOSTLY HUMAN")
        bbox3 = draw.textbbox((0, 0), label, font=font_sm)
        lw2 = bbox3[2] - bbox3[0]
        draw.text(((W - lw2) // 2, 390), label, font=font_sm, fill=color)

        scans = stats.get("scans", 0)
        sub_text = f"avg ai index across {scans} pages"
        bbox4 = draw.textbbox((0, 0), sub_text, font=font_sm)
        sw2 = bbox4[2] - bbox4[0]
        draw.text(((W - sw2) // 2, 440), sub_text, font=font_sm, fill=DIM)
    else:
        msg = "not yet scanned"
        bbox2 = draw.textbbox((0, 0), msg, font=font_med)
        mw = bbox2[2] - bbox2[0]
        draw.text(((W - mw) // 2, 300), msg, font=font_med, fill=DIM)

    # Bottom tagline
    tagline = "// is the internet writing itself yet?"
    bbox5 = draw.textbbox((0, 0), tagline, font=font_sm)
    tw = bbox5[2] - bbox5[0]
    draw.text(((W - tw) // 2, 560), tagline, font=font_sm, fill=DIM)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png",
                             headers={"Cache-Control": "max-age=3600"})
