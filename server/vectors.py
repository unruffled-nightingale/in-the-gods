"""Local MiniLM embeddings for Ask / MCP. No keyword matching.

Listings are split into short chunks (title+place+type, byline,
description slices, craft cues). Each chunk is a row in
latest.embeddings.npz with `owners[i]` = event index. Queries can be
several phrases; a show's score is the best chunk × best phrase.
"""
from __future__ import annotations

import json
import pathlib
import re
from typing import NamedTuple

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "data" / "extracts" / "latest.json"
EMBEDDINGS = ROOT / "data" / "extracts" / "latest.embeddings.npz"
VENUES = ROOT / "data" / "venues.yaml"
MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_model = None

VENUE_OVERRIDES = {
    "arcola": {"name": "Arcola Theatre", "area": "Dalston, E8"},
    "southwark-playhouse": {"name": "Southwark Playhouse", "area": "Borough, SE1"},
    "wiltons": {"name": "Wilton's Music Hall", "area": "Shadwell, E1"},
    "camden-peoples-theatre": {"name": "Camden People's Theatre", "area": "Euston, NW1"},
    "the-yard": {"name": "The Yard", "area": "Hackney Wick, E9"},
}


class SearchUnavailable(Exception):
    """Embeddings missing or out of date with the extract."""


class Hit(NamedTuple):
    id: str
    score: float
    event: dict


def event_id(index: int) -> str:
    return f"e{index:03d}"


# Neighbouring forms so a shadow-play listing can still match "puppetry"
# or "lightshow" without turning Ask into keyword search.
_FORM_GLOSS = (
    (re.compile(r"shadow[\s-]*play", re.I),
     "shadow-play puppetry visual theatre object theatre handmade craft lighting"),
    (re.compile(r"\bpuppets?\b|\bpuppetry\b", re.I),
     "puppetry handmade visual theatre craft"),
    (re.compile(r"minotaur|labyrinth", re.I),
     "mythic macabre spooky dark adult"),
    (re.compile(r"projection|\blanterns?\b|lightshow|lighting design", re.I),
     "lightshow lighting design atmospheric set craft"),
    (re.compile(r"\bmasks?\b|\bobject theatre\b", re.I),
     "visual theatre devised craft"),
)


def form_cues(blob: str) -> str:
    bits = []
    seen: set[str] = set()
    for rx, gloss in _FORM_GLOSS:
        if rx.search(blob) and gloss not in seen:
            seen.add(gloss)
            bits.append(gloss)
    return " ".join(bits)


def split_copy(text: str) -> list[str]:
    """Paragraphs, then sentences if a paragraph is long."""
    text = (text or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    out: list[str] = []
    for para in paras:
        if len(para) <= 280:
            out.append(para)
            continue
        buf = ""
        for sent in re.split(r"(?<=[.!?])\s+", para):
            sent = sent.strip()
            if not sent:
                continue
            if buf and len(buf) + 1 + len(sent) > 220:
                out.append(buf)
                buf = sent
            else:
                buf = f"{buf} {sent}".strip()
        if buf:
            out.append(buf)
    return out


def load_venues(path: pathlib.Path = VENUES) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if path.exists():
        try:
            import yaml
        except ImportError:
            yaml = None
        if yaml is not None:
            cfg = yaml.safe_load(path.read_text()) or {}
            for v in cfg.get("venues") or []:
                loc = v.get("location") or {}
                out[v["id"]] = {
                    "name": v.get("name") or v["id"],
                    "area": loc.get("area") or "",
                }
    out.update(VENUE_OVERRIDES)
    return out


def event_chunks(event: dict, venue: dict | None = None) -> list[str]:
    """Short strings MiniLM can match, including place and type."""
    venue = venue or {}
    name = (
        venue.get("name")
        or event.get("venue_name")
        or event.get("venue_id")
        or ""
    )
    area = venue.get("area") or event.get("venue_area") or ""
    tags = " ".join(event.get("tags") or [])
    title = event.get("title") or ""
    where = " · ".join(p for p in (title, name, area, tags) if p)
    chunks: list[str] = []
    if where:
        chunks.append(where)
    byline = (event.get("byline") or "").strip()
    if byline:
        chunks.append(byline)
    chunks.extend(split_copy(event.get("description") or ""))
    cues = form_cues(" ".join(
        p for p in (title, byline, event.get("description") or "") if p
    ))
    if cues:
        chunks.append(cues)
    return chunks


def event_text(event: dict, venue: dict | None = None) -> str:
    return "\n".join(event_chunks(event, venue))


def l2_normalize(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-12)


def filter_indices(
    events: list[dict],
    tags: list[str] | None = None,
    venue: str | None = None,
) -> list[int]:
    want = set(tags) if tags else None
    out = []
    for i, event in enumerate(events):
        if venue and event.get("venue_id") != venue:
            continue
        if want and not (want & set(event.get("tags") or [])):
            continue
        out.append(i)
    return out


def rank(
    matrix: np.ndarray,
    query: np.ndarray,
    indices: list[int],
    limit: int,
    owners: np.ndarray | None = None,
) -> list[tuple[int, float]]:
    """Best cosine per event. `owners[chunk] = event index` when chunked."""
    if not indices:
        return []
    q = l2_normalize(query)
    if q.ndim == 1:
        q = q.reshape(1, -1)
    n_events = int(max(indices)) + 1 if indices else 0
    if owners is None:
        owners = np.arange(matrix.shape[0], dtype=np.int64)
        n_events = max(n_events, matrix.shape[0])
    else:
        owners = np.asarray(owners, dtype=np.int64)
        n_events = max(n_events, int(owners.max()) + 1 if owners.size else 0)
    sims = matrix @ q.T
    n_q = sims.shape[1]
    phrase_best = np.full((n_events, n_q), -1.0, dtype=np.float32)
    for k in range(n_q):
        np.maximum.at(phrase_best[:, k], owners, sims[:, k].astype(np.float32))
    best = phrase_best.sum(axis=1)
    idx = np.asarray(indices, dtype=np.int64)
    scores = best[idx]
    order = np.argsort(-scores)[: max(0, limit)]
    return [(int(idx[j]), float(scores[j])) for j in order]


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(model_name=MODEL)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    model = _get_model()
    vecs = list(model.embed(texts))
    return l2_normalize(np.asarray(vecs, dtype=np.float32))


def load_index(
    events: list[dict] | None = None,
    matrix: np.ndarray | None = None,
    owners: np.ndarray | None = None,
) -> tuple[list[dict], np.ndarray, np.ndarray]:
    if events is None:
        events = json.loads(EXTRACT.read_text())["events"]
    if matrix is None:
        if not EMBEDDINGS.exists():
            raise SearchUnavailable(
                "embeddings file missing; run python pipeline/embed.py"
            )
        data = np.load(EMBEDDINGS)
        matrix = data["vectors"]
        if owners is None and "owners" in data.files:
            owners = data["owners"]
    matrix = np.asarray(matrix, dtype=np.float32)
    if matrix.ndim != 2:
        raise SearchUnavailable(
            f"embeddings {getattr(matrix, 'shape', None)} not a 2d matrix"
        )
    if owners is None:
        if matrix.shape[0] != len(events):
            raise SearchUnavailable(
                f"embeddings {matrix.shape} != events {len(events)}"
            )
        owners = np.arange(len(events), dtype=np.int32)
    else:
        owners = np.asarray(owners, dtype=np.int32)
        if owners.shape[0] != matrix.shape[0]:
            raise SearchUnavailable(
                f"owners {owners.shape} != embeddings {matrix.shape}"
            )
        if owners.size and int(owners.max()) >= len(events):
            raise SearchUnavailable(
                f"owners max {int(owners.max())} >= events {len(events)}"
            )
    return events, matrix, owners


def search(
    query: str = "",
    tags: list[str] | None = None,
    venue: str | None = None,
    limit: int = 20,
    *,
    events: list[dict] | None = None,
    matrix: np.ndarray | None = None,
    owners: np.ndarray | None = None,
    query_vec: np.ndarray | None = None,
    query_vecs: np.ndarray | None = None,
    queries: list[str] | None = None,
) -> list[Hit]:
    """Filter by tag/venue, then rank shows by best chunk × best phrase."""
    limit = max(1, min(int(limit or 20), 80))
    events, matrix, owners = load_index(events, matrix, owners)
    indices = filter_indices(events, tags=tags, venue=venue)
    q = None
    if query_vecs is not None:
        q = np.asarray(query_vecs, dtype=np.float32)
    elif query_vec is not None:
        q = np.asarray(query_vec, dtype=np.float32)
    elif queries:
        texts = [t.strip() for t in queries if str(t).strip()]
        if texts:
            q = embed_texts(texts)
    elif query.strip():
        q = embed_texts([query.strip()])
    if q is None:
        return [
            Hit(event_id(i), 0.0, events[i])
            for i in indices[:limit]
        ]
    ranked = rank(matrix, q, indices, limit, owners=owners)
    return [Hit(event_id(i), score, events[i]) for i, score in ranked]


def embed_extract(
    src: pathlib.Path = EXTRACT,
    dest: pathlib.Path = EMBEDDINGS,
) -> pathlib.Path:
    events = json.loads(src.read_text())["events"]
    venues = load_venues()
    chunks: list[str] = []
    owners: list[int] = []
    for i, event in enumerate(events):
        venue = venues.get(event.get("venue_id") or "")
        for chunk in event_chunks(event, venue):
            chunks.append(chunk)
            owners.append(i)
    vectors = embed_texts(chunks)
    dest.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        dest,
        vectors=vectors,
        owners=np.asarray(owners, dtype=np.int32),
    )
    meta = {
        vid: {"name": v.get("name") or vid, "area": v.get("area") or ""}
        for vid, v in venues.items()
    }
    dest.with_name("latest.venues.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=0) + "\n"
    )
    return dest
