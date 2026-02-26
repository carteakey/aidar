from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from aidar.db.database import get_connection
from aidar.db.queries import (
    get_domain_leaderboard,
    get_domain_scans,
    get_domain_stats,
    get_global_stats,
    get_pattern_stats,
)

DB_PATH = os.environ.get("AIDAR_DB", "aidar.db")

app = FastAPI(title="aidar.lol", docs_url=None, redoc_url=None)

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def get_conn():
    return get_connection(DB_PATH)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    conn = get_conn()
    leaderboard = get_domain_leaderboard(conn, limit=100)
    stats = get_global_stats(conn)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "leaderboard": leaderboard, "stats": stats},
    )


@app.get("/domain/{domain:path}", response_class=HTMLResponse)
async def domain_page(request: Request, domain: str):
    conn = get_conn()
    stats = get_domain_stats(conn, domain)
    if stats.get("scans", 0) == 0:
        raise HTTPException(status_code=404, detail="Domain not found")
    scans = get_domain_scans(conn, domain, limit=100)

    # Parse score_json for each scan to get category breakdown
    for scan in scans:
        try:
            scan["categories"] = json.loads(scan.get("score_json") or "{}")
        except Exception:
            scan["categories"] = {}

    return templates.TemplateResponse(
        "domain.html",
        {"request": request, "domain": domain, "stats": stats, "scans": scans},
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
