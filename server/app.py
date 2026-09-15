"""Website + JSON API + MCP from one process.

    /            theatre.html
    /logo.png    favicon / share / home-screen icon
    /api/shows   latest extract
    /api/search  expanded MiniLM shortlist, then Haiku order
    /mcp         Streamable HTTP MCP (Claude Desktop / Claude.ai connector)

Claude Desktop: add a connector with URL http://localhost:8080/mcp
(or https://inthegods.co.uk/mcp after deploy).
"""
from __future__ import annotations

import asyncio
import json
import pathlib

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from server.ask import retrieve
from server.vectors import SearchUnavailable

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "data" / "extracts" / "latest.json"
FRONTEND = ROOT / "frontend"
LOGO = FRONTEND / "logo.png"

mcp = FastMCP("inthegods")


def load_events() -> list[dict]:
    return json.loads(EXTRACT.read_text())["events"]


def _parse_tags(raw: list[str] | str | None) -> list[str] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        return parts or None
    parts = [str(p).strip() for p in raw if str(p).strip()]
    return parts or None


@mcp.tool()
async def search_shows(
    query: str = "",
    tags: list[str] | None = None,
    venue: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search current In the Gods listings by meaning.

    Args:
        query: natural-language vibe, place, or form (macabre handmade,
            puppetry in Dalston, opera in Islington). Empty returns the
            tag/venue filter only, extract order.
        tags: any of theatre, musical, stand-up, comedy, concert, opera,
            dance, circus, immersive, puppetry, cabaret, magic,
            spoken-word, talk, class, social, exhibition.
        venue: venue id, e.g. 'camden-peoples-theatre'.
        limit: max rows to return.
    """
    hits = await asyncio.to_thread(
        retrieve, query, tags, venue, limit,
    )
    out = []
    for hit in hits:
        row = dict(hit.event)
        row["id"] = hit.id
        row["score"] = round(hit.score, 4)
        out.append(row)
    return out


@mcp.tool()
async def list_venues() -> list[dict]:
    """Venues currently in the extract, with how many shows each has on."""
    counts: dict[str, int] = {}
    for e in load_events():
        vid = e.get("venue_id") or ""
        counts[vid] = counts.get(vid, 0) + 1
    return [{"venue_id": v, "shows": n} for v, n in sorted(counts.items())]


def _logo(_request: Request) -> Response:
    return FileResponse(LOGO, media_type="image/png")


@mcp.custom_route("/", methods=["GET"])
async def index(request: Request) -> Response:
    return FileResponse(FRONTEND / "theatre.html")


@mcp.custom_route("/logo.png", methods=["GET"])
async def logo_png(request: Request) -> Response:
    return _logo(request)


@mcp.custom_route("/favicon.ico", methods=["GET"])
async def favicon(request: Request) -> Response:
    return _logo(request)


@mcp.custom_route("/apple-touch-icon.png", methods=["GET"])
async def apple_touch_icon(request: Request) -> Response:
    return _logo(request)


@mcp.custom_route("/apple-touch-icon-precomposed.png", methods=["GET"])
async def apple_touch_icon_precomposed(request: Request) -> Response:
    return _logo(request)


@mcp.custom_route("/site.webmanifest", methods=["GET"])
async def webmanifest(request: Request) -> Response:
    return JSONResponse(
        {
            "name": "In the Gods",
            "short_name": "In the Gods",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#EFEEE8",
            "theme_color": "#6E2431",
            "icons": [
                {
                    "src": "/logo.png",
                    "sizes": "1738x1736",
                    "type": "image/png",
                    "purpose": "any",
                }
            ],
        },
        media_type="application/manifest+json",
    )


@mcp.custom_route("/api/shows", methods=["GET"])
async def api_shows(request: Request) -> Response:
    return JSONResponse(json.loads(EXTRACT.read_text()))


@mcp.custom_route("/api/search", methods=["GET"])
async def api_search(request: Request) -> Response:
    q = (request.query_params.get("q") or "").strip()
    tags = _parse_tags(request.query_params.get("tags"))
    venue = (request.query_params.get("venue") or "").strip() or None
    try:
        limit = int(request.query_params.get("limit") or 20)
    except ValueError:
        limit = 20
    limit = max(1, min(limit, 80))
    try:
        hits = await asyncio.to_thread(retrieve, q, tags, venue, limit)
    except SearchUnavailable as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    return JSONResponse({
        "ids": [h.id for h in hits],
        "scores": [round(h.score, 4) for h in hits],
        "count": len(hits),
    })


app = mcp.http_app(
    path="/mcp",
    stateless_http=True,
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["Mcp-Session-Id", "mcp-session-id"],
        ),
    ],
)
