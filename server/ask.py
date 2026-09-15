"""Haiku order on MiniLM Ask hits. No explanations, ids only.

Vectors retrieve a shortlist. Haiku reorders it best-first for the query
and never drops a row. If the key is missing or the call fails, the
vector order is kept.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys

from server.vectors import Hit

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL = "claude-haiku-4-5"
POOL = 80

TOOL = {
    "name": "order_shows",
    "description": "Return every candidate id, best match first. Never drop one.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["ids"],
        "properties": {
            "ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "All candidate ids, best match first.",
            }
        },
    },
}

SYSTEM = (
    "You reorder London fringe and off-West End listings for a visitor search.\n\n"
    "The candidates are already a shortlist from embedding search. Return "
    "every candidate id, best match first. Never drop a listing. Do not "
    "invent ids. No explanations.\n\n"
    "Best first means more of the query's constraints, not one loud word. "
    "Shadow-play, visual theatre, and object theatre count as craft / "
    "puppetry. If they asked for adults, put kids' and family work after "
    "adult work. If they named a neighbourhood, house, or form (opera, "
    "cabaret, puppetry), put those closer to the front."
)

EXPAND_TOOL = {
    "name": "expand_query",
    "description": "Neighbouring phrases to embed, not a filter.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["phrases"],
        "properties": {
            "phrases": {
                "type": "array",
                "items": {"type": "string"},
                "description": "5 to 8 short embedding queries.",
            }
        },
    },
}

EXPAND_SYSTEM = (
    "You write extra embedding queries for a London fringe listings search.\n\n"
    "One vector of the visitor's sentence is too narrow: a shadow-play "
    "Minotaur piece will miss 'puppetry' and 'lightshow' even when it is "
    "the right show. Place and type are first-class: 'puppetry in Dalston' "
    "or 'opera in Islington' should stay as their own short phrases.\n\n"
    "Return 5 to 8 short phrases (2–8 words). Cover neighbouring forms "
    "and places, not just the words they typed. Examples: spooky → "
    "macabre, gothic, haunting, mythic, dark; puppetry → shadow-play, "
    "visual theatre, object theatre, devised; craft / set / lightshow → "
    "design, lantern, projection, handmade, atmospheric staging; for "
    "adults → not kids, late night; Dalston / Hackney / Highgate → that "
    "area and nearby houses; opera / cabaret / dance → keep the form. "
    "Include one tight paraphrase of the original. Do not invent show "
    "titles."
)

_SPLIT = re.compile(r"\s*(?:,|;|/|\band\b|\bin\b)\s*", re.I)


def split_query(query: str) -> list[str]:
    """Comma / and clauses as extra embedding phrases."""
    out = []
    seen = set()
    for raw in _SPLIT.split(query or ""):
        p = " ".join(raw.split()).strip(" .")
        if len(p) < 4:
            continue
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out

_client = False


def load_dotenv(path: pathlib.Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def make_client():
    try:
        import anthropic
    except ImportError:
        return None
    load_dotenv(ROOT / ".env")
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        return None
    return anthropic.Anthropic(api_key=key)


def get_client():
    global _client
    if _client is False:
        _client = make_client()
    return _client


_venues = None


def load_venue_meta() -> dict:
    global _venues
    if _venues is None:
        path = ROOT / "data" / "extracts" / "latest.venues.json"
        try:
            _venues = json.loads(path.read_text()) if path.exists() else {}
        except (OSError, json.JSONDecodeError):
            _venues = {}
    return _venues


def compact(hits: list[Hit]) -> list[dict]:
    rows = []
    venues = load_venue_meta()
    for hit in hits:
        event = hit.event
        desc = event.get("description") or ""
        if len(desc) > 400:
            desc = desc[:400] + "…"
        vid = event.get("venue_id")
        meta = venues.get(vid) or {}
        name = event.get("venue_name") or meta.get("name")
        area = event.get("venue_area") or meta.get("area")
        row = {
            "id": hit.id,
            "v": vid,
            "t": event.get("title"),
            "b": (event.get("byline") or "")[:240],
            "d": desc,
            "tags": event.get("tags") or [],
        }
        where = " · ".join(p for p in (name, area) if p)
        if where:
            row["where"] = where
        rows.append(row)
    return rows


def parse_ids(message) -> list[str]:
    blocks = getattr(message, "content", None) or []
    for block in blocks:
        kind = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        name = block.get("name") if isinstance(block, dict) else getattr(block, "name", None)
        if kind == "tool_use" and name == "order_shows":
            data = block.get("input") if isinstance(block, dict) else block.input
            return [str(i) for i in (data or {}).get("ids") or []]
    raise RuntimeError("Haiku did not call order_shows")


def parse_phrases(message) -> list[str]:
    blocks = getattr(message, "content", None) or []
    for block in blocks:
        kind = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        name = block.get("name") if isinstance(block, dict) else getattr(block, "name", None)
        if kind == "tool_use" and name == "expand_query":
            data = block.get("input") if isinstance(block, dict) else block.input
            return [str(p).strip() for p in (data or {}).get("phrases") or [] if str(p).strip()]
    raise RuntimeError("Haiku did not call expand_query")


def call_haiku(client, system: str, payload: dict) -> list[str]:
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=[{
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }],
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "order_shows"},
        messages=[{
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False),
        }],
    )
    return parse_ids(msg)


def call_expand(client, system: str, payload: dict) -> list[str]:
    msg = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=[{
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }],
        tools=[EXPAND_TOOL],
        tool_choice={"type": "tool", "name": "expand_query"},
        messages=[{
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False),
        }],
    )
    return parse_phrases(msg)


def apply_order(hits: list[Hit], ids: list[str]) -> list[Hit] | None:
    """Haiku order first, leftovers in vector order. None means junk ids."""
    by_id = {h.id: h for h in hits}
    out = []
    seen = set()
    for i in ids:
        hit = by_id.get(i)
        if hit is None or i in seen:
            continue
        out.append(hit)
        seen.add(i)
    if not out:
        return None
    for hit in hits:
        if hit.id not in seen:
            out.append(hit)
    return out


def expand_queries(query: str, *, call=None) -> list[str]:
    """Original query, Haiku neighbours, then local place/type clauses."""
    query = (query or "").strip()
    if not query:
        return []
    phrases = [query]
    seen = {query.lower()}
    extra = []

    def add(raw: str) -> None:
        p = " ".join(str(raw).split())
        if not p or p.lower() in seen or len(phrases) >= 8:
            return
        seen.add(p.lower())
        phrases.append(p)

    if call is None:
        client = get_client()
        if client is not None:
            def call(system, payload):
                return call_expand(client, system, payload)
    if call is not None:
        try:
            extra = call(EXPAND_SYSTEM, {"q": query}) or []
        except Exception as exc:
            print(f"ask: expand skipped ({exc})", file=sys.stderr)
            extra = []
    for raw in extra:
        add(raw)
    for part in split_query(query):
        add(part)
    return phrases


def rerank(query: str, hits: list[Hit], *, call=None) -> list[Hit]:
    """Best-first order for the query. Vector order if Haiku is unavailable."""
    query = (query or "").strip()
    if not query or len(hits) < 2:
        return hits
    if call is None:
        client = get_client()
        if client is None:
            return hits

        def call(system, payload):
            return call_haiku(client, system, payload)

    try:
        ids = call(SYSTEM, {"q": query, "candidates": compact(hits)})
    except Exception as exc:
        print(f"ask: Haiku skipped ({exc})", file=sys.stderr)
        return hits
    ordered = apply_order(hits, ids)
    if ordered is None:
        return hits
    return ordered


def retrieve(
    query: str,
    tags: list[str] | None = None,
    venue: str | None = None,
    limit: int = 20,
    *,
    expand=None,
    order=None,
    events: list[dict] | None = None,
    matrix=None,
    owners=None,
    query_vec=None,
    query_vecs=None,
) -> list[Hit]:
    """Expand, max-pool MiniLM over chunks, then Haiku order. Never drops a row."""
    from server.vectors import search

    query = (query or "").strip()
    limit = max(1, min(int(limit or 20), 80))
    if not query:
        return search(
            "", tags=tags, venue=venue, limit=limit,
            events=events, matrix=matrix, owners=owners,
        )
    phrases = expand_queries(query, call=expand)
    pool = min(80, max(limit, POOL))
    hits = search(
        query, tags=tags, venue=venue, limit=pool,
        events=events, matrix=matrix, owners=owners,
        query_vec=query_vec, query_vecs=query_vecs,
        queries=None if (query_vec is not None or query_vecs is not None) else phrases,
    )
    hits = rerank(query, hits, call=order)
    return hits[:limit]
