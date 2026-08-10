from __future__ import annotations

import io
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from aidar.db.database import get_connection
from aidar.db.queries import (
    count_domain_leaderboard,
    delete_domain,
    get_corpus_percentile,
    get_domain_extremes,
    get_domain_leaderboard,
    get_domain_scans,
    get_domain_stats,
    get_domain_trend,
    get_global_stats,
    get_pattern_detail,
    get_pattern_stats,
    get_recent_scans,
)

DB_PATH = os.environ.get("AIDAR_DB", "aidar.db")
ADMIN_KEY = os.environ.get("AIDAR_ADMIN_KEY", "")

app = FastAPI(title="aidar.lol", docs_url=None, redoc_url=None)

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# In-memory scan status (per-dyno). NOTE: on Heroku without Postgres,
# scans are written to an ephemeral SQLite and won't survive a dyno restart.
# Add DATABASE_URL (Heroku Postgres) to make web-triggered scans persistent.
_scan_status: dict[str, str] = {}
_scan_summaries: dict[str, dict] = {}
_scan_last_completed: dict[str, float] = {}  # domain → unix timestamp

RATE_LIMIT_SECONDS = 60 * 60 * 6  # 6 hours between web-triggered rescans

# Lazy-loaded analyzer singleton (loaded once at first scan request)
_analyzer = None
_analyzer_config = None


def _normalize_submitted_domain(value: str) -> str:
    candidate = value.strip()
    parsed = urlparse(candidate if "://" in candidate else f"//{candidate}")
    return parsed.netloc.lower().rstrip(".")


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
    from aidar.core.discovery import discover_urls, normalize_domain
    from aidar.core.ingestion import ScanSummary, filter_prose_urls, scan_urls
    from aidar.db.queries import store_result, url_already_scanned

    _scan_status[domain] = "running"
    try:
        base_url = normalize_domain(domain)
        urls, _ = discover_urls(base_url)
        summary = ScanSummary(discovered=len(urls))
        if not urls:
            _scan_summaries[domain] = summary.as_dict()
            _scan_status[domain] = "error:no_urls"
            return

        filtered = filter_prose_urls(urls, base_url=base_url)
        urls = filtered.kept
        summary.record_rejections(filtered.rejected)

        conn = get_conn()
        before = len(urls)
        urls = [u for u in urls if not url_already_scanned(conn, u)]
        existing = before - len(urls)
        summary.filtered += existing
        if existing:
            summary.reasons["already_scanned"] += existing
        if len(urls) > limit:
            deferred = len(urls) - limit
            summary.filtered += deferred
            summary.reasons["limit"] += deferred
            urls = urls[:limit]
        if not urls:
            _scan_summaries[domain] = summary.as_dict()
            _scan_status[domain] = "done"
            return

        analyzer, config = _get_analyzer()
        outcomes = await scan_urls(urls, analyzer, config, concurrency=5)
        summary.record_outcomes(outcomes)
        for outcome in outcomes:
            if outcome.result is not None:
                store_result(conn, outcome.result)

        _scan_summaries[domain] = summary.as_dict()
        _scan_status[domain] = "done"
        _scan_last_completed[domain] = time.time()
    except Exception:
        _scan_status[domain] = "error"


def get_conn():
    return get_connection(DB_PATH)


def _read_only() -> bool:
    """Whether this web process must reject all mutating routes."""
    return os.environ.get("AIDAR_READ_ONLY", "").strip().lower() in {"1", "true", "yes", "on"}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    conn = get_conn()
    conn.execute("SELECT 1").fetchone()
    return {"status": "ok", "read_only": "true" if _read_only() else "false"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, q: str = "", page: int = 1, limit: int = 50, label: str = ""):
    allowed_labels = {"LIKELY AI", "UNCERTAIN", "LIKELY HUMAN"}
    if label and label not in allowed_labels:
        raise HTTPException(status_code=400, detail="Invalid label filter")
    page = max(page, 1)
    limit = max(1, min(limit, 100))
    conn = get_conn()
    label_filter = label or None
    total_domains = count_domain_leaderboard(conn, label_filter)
    leaderboard = get_domain_leaderboard(
        conn,
        limit=limit,
        offset=(page - 1) * limit,
        label_filter=label_filter,
    )
    stats = get_global_stats(conn)
    total_pages = max((total_domains + limit - 1) // limit, 1)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "leaderboard": leaderboard,
            "stats": stats,
            "q": q,
            "label": label,
            "page": page,
            "limit": limit,
            "total_domains": total_domains,
            "total_pages": total_pages,
        },
    )


@app.post("/submit", response_class=HTMLResponse)
async def submit_site(request: Request, background_tasks: BackgroundTasks):
    from fastapi.responses import RedirectResponse

    if _read_only():
        raise HTTPException(status_code=403, detail="Read-only web replica")
    form = await request.form()
    domain = _normalize_submitted_domain(str(form.get("domain", "")))
    if not domain:
        conn = get_conn()
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "request": request,
                "leaderboard": get_domain_leaderboard(conn, limit=100),
                "stats": get_global_stats(conn),
                "submit_error": "Enter a domain.",
            },
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
            from datetime import datetime

            latest_dt = datetime.fromisoformat(stats["latest"].replace("Z", "+00:00"))
            age_s = (datetime.now(UTC) - latest_dt).total_seconds()
            if age_s < RATE_LIMIT_SECONDS:
                return RedirectResponse(url=f"/domain/{domain}", status_code=303)
        except Exception:
            pass

    _scan_status[domain] = "queued"
    background_tasks.add_task(_run_domain_scan, domain)
    return RedirectResponse(url=f"/domain/{domain}", status_code=303)


@app.get("/domain/{domain:path}", response_class=HTMLResponse)
async def domain_page(request: Request, domain: str, sort: str = "recent"):
    conn = get_conn()
    stats = get_domain_stats(conn, domain)
    scan_status = _scan_status.get(domain)
    if stats.get("scans", 0) == 0:
        status_code = 200 if scan_status in ("queued", "running") else 404
        return templates.TemplateResponse(
            request=request,
            name="domain_missing.html",
            context={"request": request, "domain": domain, "scan_status": scan_status},
            status_code=status_code,
        )
    sort = sort if sort in ("recent", "highest", "lowest") else "recent"
    scans = get_domain_scans(conn, domain, limit=200, sort=sort)
    trend = get_domain_trend(conn, domain)
    percentile = get_corpus_percentile(conn, int(stats.get("avg_score", 0)))
    top_pages, bottom_pages = get_domain_extremes(conn, domain, n=5)

    for scan in scans:
        try:
            scan["categories"] = json.loads(scan.get("score_json") or "{}")
        except Exception:
            scan["categories"] = {}

    analyzer, _ = _get_analyzer()
    pattern_catalog = {pattern.id: pattern for pattern in analyzer.registry.all_patterns()}
    domain_pattern_values: dict[str, list[float]] = {}
    for scan in scans:
        for pattern in scan.get("patterns", []):
            domain_pattern_values.setdefault(pattern["pattern_id"], []).append(
                float(pattern.get("norm_score") or 0.0)
            )
    strongest_patterns = [
        {
            "id": pattern_id,
            "name": pattern_catalog[pattern_id].name if pattern_id in pattern_catalog else pattern_id,
            "avg_score": round(sum(values) / len(values), 3),
            "version": pattern_catalog[pattern_id].version if pattern_id in pattern_catalog else None,
        }
        for pattern_id, values in sorted(
            domain_pattern_values.items(),
            key=lambda item: (-sum(item[1]) / len(item[1]), item[0]),
        )[:8]
    ]

    return templates.TemplateResponse(
        request=request,
        name="domain.html",
        context={
            "request": request,
            "domain": domain,
            "stats": stats,
            "scans": scans,
            "trend": trend,
            "percentile": percentile,
            "top_pages": top_pages,
            "bottom_pages": bottom_pages,
            "strongest_patterns": strongest_patterns,
            "sort": sort,
            "admin_key_set": bool(ADMIN_KEY),
        },
    )


@app.post("/admin/delete-domain", response_class=HTMLResponse)
async def admin_delete_domain(request: Request):
    from fastapi.responses import RedirectResponse

    if _read_only():
        raise HTTPException(status_code=403, detail="Read-only web replica")
    if not ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Admin key not configured.")
    form = await request.form()
    key = str(form.get("admin_key", ""))
    domain = str(form.get("domain", "")).strip()
    if key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key.")
    if not domain:
        raise HTTPException(status_code=400, detail="No domain specified.")
    deleted = delete_domain(get_conn(), domain)
    return RedirectResponse(url=f"/?deleted={domain}&rows={deleted}", status_code=303)


@app.get("/patterns", response_class=HTMLResponse)
async def patterns_page(request: Request):
    conn = get_conn()
    pattern_stats = get_pattern_stats(conn)
    global_stats = get_global_stats(conn)

    # Build a lookup from pattern_id → PatternDef for the template
    analyzer, _ = _get_analyzer()
    catalog: dict[str, dict] = {}
    for pat in analyzer.registry.all_patterns():
        catalog[pat.id] = {
            "name": pat.name,
            "description": pat.description,
            "category": pat.category,
            "detection_type": pat.detection_type,
            "version": pat.version,
            "severity": pat.severity,
        }

    return templates.TemplateResponse(
        request=request,
        name="patterns.html",
        context={"request": request, "patterns": pattern_stats, "stats": global_stats, "catalog": catalog},
    )


@app.get("/patterns/{pattern_id}", response_class=HTMLResponse)
async def pattern_detail_page(request: Request, pattern_id: str):
    analyzer, _ = _get_analyzer()
    pattern = analyzer.registry.get_pattern(pattern_id)
    if pattern is None:
        raise HTTPException(status_code=404, detail="Unknown pattern")
    conn = get_conn()
    detail = get_pattern_detail(conn, pattern_id)
    return templates.TemplateResponse(
        request=request,
        name="pattern_detail.html",
        context={
            "request": request,
            "pattern": pattern,
            "detail": detail,
            "references": pattern.references,
        },
    )


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse(request=request, name="about.html", context={"request": request})


@app.get("/api/leaderboard")
async def api_leaderboard(limit: int = 100, offset: int = 0, label: str | None = None):
    allowed_labels = {"LIKELY AI", "UNCERTAIN", "LIKELY HUMAN"}
    if label and label not in allowed_labels:
        raise HTTPException(status_code=400, detail="Invalid label filter")
    limit = max(1, min(limit, 100))
    offset = max(offset, 0)
    conn = get_conn()
    items = get_domain_leaderboard(conn, limit=limit, offset=offset, label_filter=label)
    total = count_domain_leaderboard(conn, label)
    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        "total": total,
        "next_offset": offset + limit if offset + limit < total else None,
    }


@app.get("/api/docs")
async def api_docs() -> dict:
    """Machine-readable public API contract for lightweight consumers."""
    return {
        "version": "1",
        "description": "Aidar stylistic trend index; not an authorship verdict.",
        "endpoints": {
            "/api/leaderboard": {
                "method": "GET",
                "params": {"limit": "1-100", "offset": "0+", "label": ["LIKELY AI", "UNCERTAIN", "LIKELY HUMAN"]},
                "response": "{items, limit, offset, total, next_offset}",
            },
            "/api/domain/{domain}": {
                "method": "GET",
                "response": "{stats, scans}; scans include pattern evidence and scorer metadata",
            },
            "/api/scan-status/{domain}": {"method": "GET", "response": "{domain, status, summary}"},
            "/feed.xml": {"method": "GET", "response": "RSS 2.0 (bounded recent scans)"},
        },
        "limits": {"leaderboard_default": 100, "leaderboard_max": 100, "feed_max": 50},
    }


@app.get("/feed.xml")
async def feed() -> Response:
    """Return a bounded RSS feed of recently persisted page scans."""
    conn = get_conn()
    root = ElementTree.Element(
        "rss",
        {"version": "2.0", "xmlns:atom": "http://www.w3.org/2005/Atom"},
    )
    channel = ElementTree.SubElement(root, "channel")
    ElementTree.SubElement(channel, "title").text = "aidar.lol recent scans"
    ElementTree.SubElement(channel, "link").text = "https://aidar.lol/"
    ElementTree.SubElement(channel, "description").text = "Recent stylistic index scans"
    for item in get_recent_scans(conn, limit=50):
        entry = ElementTree.SubElement(channel, "item")
        title = item.get("title") or item.get("url") or item.get("domain") or "Aidar scan"
        ElementTree.SubElement(entry, "title").text = str(title)
        url = item.get("url")
        if url:
            ElementTree.SubElement(entry, "link").text = str(url)
            ElementTree.SubElement(entry, "guid", {"isPermaLink": "true"}).text = str(url)
        ElementTree.SubElement(entry, "description").text = (
            f"{item.get('domain', '')}: stylistic index {item.get('score', '—')} "
            f"({item.get('label', 'UNCERTAIN')})"
        )
        scanned_at = item.get("scanned_at")
        if scanned_at:
            try:
                parsed = datetime.fromisoformat(str(scanned_at).replace("Z", "+00:00"))
                ElementTree.SubElement(entry, "pubDate").text = parsed.strftime(
                    "%a, %d %b %Y %H:%M:%S %z"
                )
            except ValueError:
                pass
    body = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
    return Response(
        content=body,
        media_type="application/rss+xml",
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.get("/api/domain/{domain:path}")
async def api_domain(domain: str):
    conn = get_conn()
    stats = get_domain_stats(conn, domain)
    if stats.get("scans", 0) == 0:
        raise HTTPException(status_code=404)
    scans = get_domain_scans(conn, domain)
    for scan in scans:
        try:
            scan["score_vector"] = json.loads(scan.get("score_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            scan["score_vector"] = {}
        scan.pop("score_json", None)
    return {
        "api_version": "1",
        "description": "Aidar stylistic trend index; not an authorship verdict.",
        "stats": stats,
        "scans": scans,
        "limits": {"scan_rows": 100},
    }


@app.get("/api/scan-status/{domain:path}")
async def api_scan_status(domain: str):
    return {
        "domain": domain,
        "status": _scan_status.get(domain, "unknown"),
        "summary": _scan_summaries.get(domain),
    }


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
    lw = len(left) * 7 + 10  # approx pixel width of left label
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
    return Response(
        content=svg, media_type="image/svg+xml", headers={"Cache-Control": "max-age=3600"}
    )


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
        font_big = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 96
        )
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
    return StreamingResponse(buf, media_type="image/png", headers={"Cache-Control": "max-age=3600"})
