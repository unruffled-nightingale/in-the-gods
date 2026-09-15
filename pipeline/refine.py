#!/usr/bin/env python3
"""Post-extract cleanup: drop films/fitness, retag.

    python pipeline/refine.py --in data/extracts/latest.json --out data/extracts/latest.json

This week's unrefined extract is the membership list. Haiku only sees rows
whose (venue, title, copy, taste) fingerprint is not in
data/refine-cache.json — keeps and drops both. The weekly job commits
that file as the judgement log.

Fingerprints not seen for cache_prune_weeks (and not in this run) are
dropped from the cache so it cannot grow without bound. --limit skips
prune, so a cheap trial cannot wipe judgements.

Key from ANTHROPIC_API_KEY, or from a .env file at the repo root.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
import unicodedata
from datetime import date, timedelta

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_TASTE = ROOT / "data" / "taste.yaml"
DEFAULT_CACHE = ROOT / "data" / "refine-cache.json"

TOOL = {
    "name": "classify_events",
    "description": "Keep/drop and retag each listed event.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["results"],
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["i", "keep", "tags", "star"],
                    "properties": {
                        "i": {"type": "integer"},
                        "keep": {"type": "boolean"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "star": {"type": "boolean"},
                        "why": {"type": "string"},
                    },
                },
            }
        },
    },
}


def load_taste(path: pathlib.Path) -> dict:
    taste = yaml.safe_load(path.read_text()) or {}
    tags = list(taste.get("allowed_tags") or [])
    if not tags:
        raise SystemExit(f"{path} has no allowed_tags")
    taste["allowed_tags"] = tags
    taste["allowed_set"] = set(tags)
    taste["model"] = taste.get("model") or "claude-haiku-4-5"
    taste["batch_size"] = int(taste.get("batch_size") or 20)
    taste["cache_prune_weeks"] = int(taste.get("cache_prune_weeks") or 12)
    blob = json.dumps(
        {k: taste[k] for k in ("model", "allowed_tags", "drop", "interests")
         if k in taste},
        sort_keys=True,
    )
    taste["hash"] = hashlib.sha256(blob.encode()).hexdigest()[:16]
    return taste


def event_fp(event: dict, taste_hash: str) -> str:
    payload = json.dumps({
        "taste": taste_hash,
        "venue_id": event.get("venue_id"),
        "title": event.get("title"),
        "byline": event.get("byline") or "",
        "description": event.get("description") or "",
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def load_cache(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def save_cache(path: pathlib.Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")


def clamp_verdict(raw: dict, allowed: set[str]) -> dict:
    tags = [t for t in (raw.get("tags") or []) if t in allowed]
    keep = bool(raw.get("keep"))
    if keep and not tags:
        tags = ["theatre"]
    return {
        "keep": keep,
        "tags": tags,
        "star": bool(raw.get("star")) and keep,
        "why": (raw.get("why") or "")[:120],
    }


def put_cache(cache: dict, fp: str, verdict: dict, today: date) -> None:
    cache[fp] = {
        "keep": verdict["keep"],
        "tags": verdict["tags"],
        "star": verdict["star"],
        "why": verdict.get("why") or "",
        "last_seen": today.isoformat(),
    }


def prune_cache(cache: dict, seen_fps: set[str], today: date, weeks: int):
    """Drop judgements that this run did not see and that are older than weeks.

    Anything in seen_fps is kept even if last_seen in git is stale — we
    only commit the cache when the extract itself changes.
    """
    if weeks <= 0:
        return cache, 0
    cutoff = today - timedelta(weeks=weeks)
    kept, n = {}, 0
    for fp, val in cache.items():
        if fp in seen_fps:
            kept[fp] = val
            continue
        raw = val.get("last_seen") if isinstance(val, dict) else None
        try:
            seen = date.fromisoformat(raw) if raw else None
        except ValueError:
            seen = None
        if seen is None or seen < cutoff:
            n += 1
            continue
        kept[fp] = val
    return kept, n


# Cheap English check so we do not wait on Haiku for a Turkish listing.
# Short rows (title only) pass. Opera in Italian with an English synopsis
# passes because the stopwords live in the copy.
_EN_STOP = frozenset("""
the and for from into with this that these those of on to is
are was were been being not nor than then too very first
can will just about you they she his her our their
""".split())


def is_english_listing(event: dict) -> bool:
    """True if the listing copy is English enough to keep."""
    blob = " ".join(
        p for p in (
            event.get("title") or "",
            event.get("byline") or "",
            event.get("description") or "",
        ) if p
    )
    letters = [c for c in blob if c.isalpha()]
    if len(letters) >= 30:
        non_latin = 0
        for c in letters:
            name = unicodedata.name(c, "")
            if "LATIN" not in name:
                non_latin += 1
        if non_latin / len(letters) >= 0.35:
            return False
    words = re.findall(r"[^\W\d_]+", blob.lower(), flags=re.UNICODE)
    if len(words) < 20:
        return True
    hits = {w for w in words if w in _EN_STOP}
    return len(hits) >= 2


def compact_event(i: int, event: dict) -> dict:
    desc = event.get("description") or ""
    if len(desc) > 400:
        desc = desc[:400] + "…"
    return {
        "i": i,
        "v": event.get("venue_id"),
        "t": event.get("title"),
        "b": (event.get("byline") or "")[:240],
        "d": desc,
        "tags": event.get("tags") or [],
    }


def system_prompt(taste: dict) -> str:
    allowed = ", ".join(taste["allowed_tags"])
    return (
        "You clean a London fringe/off-West-End listings extract.\n\n"
        f"Allowed tags (pick one or two): {allowed}\n\n"
        "Drop rules:\n"
        f"{(taste.get('drop') or '').strip()}\n\n"
        "For every input object, return one result with the same i. "
        "why is at most 8 words. Do not invent tags outside the allowed list. "
        "If it is a film, a fitness class, or not in English, keep=false. "
        "Always set star=false; starring is the visitor's choice."
    )


def parse_tool_input(message) -> list[dict]:
    blocks = getattr(message, "content", None) or []
    for block in blocks:
        kind = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        name = block.get("name") if isinstance(block, dict) else getattr(block, "name", None)
        if kind == "tool_use" and name == "classify_events":
            data = block.get("input") if isinstance(block, dict) else block.input
            return list((data or {}).get("results") or [])
    raise RuntimeError("Haiku did not call classify_events")


def call_haiku(client, model: str, system: str, batch: list[dict]) -> list[dict]:
    msg = client.messages.create(
        model=model,
        max_tokens=4096,
        system=[{
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }],
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "classify_events"},
        messages=[{
            "role": "user",
            "content": json.dumps(batch, ensure_ascii=False),
        }],
    )
    return parse_tool_input(msg)


def apply_verdict(event: dict, verdict: dict) -> dict | None:
    if not verdict["keep"]:
        return None
    out = dict(event)
    out["tags"] = verdict["tags"]
    out.pop("prestar", None)
    return out


def refine(events: list[dict], taste: dict, client, cache: dict,
           call=call_haiku, today: date | None = None) -> tuple[list[dict], dict]:
    today = today or date.today()
    allowed = taste["allowed_set"]
    system = system_prompt(taste)
    stats = {
        "cache_hits": 0,
        "api_events": 0,
        "dropped": 0,
        "retagged": 0,
        "api_calls": 0,
        "seen_fps": set(),
    }

    pending = []
    verdicts: dict[int, dict] = {}
    for i, event in enumerate(events):
        fp = event_fp(event, taste["hash"])
        stats["seen_fps"].add(fp)
        if not is_english_listing(event):
            verdict = {
                "keep": False, "tags": [], "star": False, "why": "not English",
            }
            put_cache(cache, fp, verdict, today)
            verdicts[i] = verdict
            continue
        hit = cache.get(fp)
        if hit:
            stats["cache_hits"] += 1
            verdict = clamp_verdict(hit, allowed)
            put_cache(cache, fp, verdict, today)
            verdicts[i] = verdict
        else:
            pending.append(i)

    size = taste["batch_size"]
    if pending and call is not None and client is not None:
        for start in range(0, len(pending), size):
            idxs = pending[start:start + size]
            batch = [compact_event(j, events[idx]) for j, idx in enumerate(idxs)]
            raw = call(client, taste["model"], system, batch)
            by_i = {int(r["i"]): r for r in raw if "i" in r}
            stats["api_calls"] += 1
            stats["api_events"] += len(idxs)
            for j, idx in enumerate(idxs):
                row = by_i.get(j)
                if row is None:
                    # leave uncached; keep original tags
                    continue
                verdict = clamp_verdict(row, allowed)
                fp = event_fp(events[idx], taste["hash"])
                put_cache(cache, fp, verdict, today)
                verdicts[idx] = verdict

    kept = []
    for i, event in enumerate(events):
        verdict = verdicts.get(i)
        if verdict is None:
            event = dict(event)
            event.pop("prestar", None)
            kept.append(event)
            continue
        old_tags = event.get("tags") or []
        applied = apply_verdict(event, verdict)
        if applied is None:
            stats["dropped"] += 1
            continue
        if applied.get("tags") != old_tags:
            stats["retagged"] += 1
        kept.append(applied)
    return kept, stats


def load_dotenv(path: pathlib.Path) -> None:
    """Load KEY=VALUE lines without overwriting a real environment variable."""
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
    except ImportError as e:
        raise SystemExit("pip install anthropic") from e
    load_dotenv(ROOT / ".env")
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        return None
    return anthropic.Anthropic(api_key=key)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="src", default="data/extracts/latest.json")
    ap.add_argument("--out", default="data/extracts/latest.json")
    ap.add_argument("--taste", default=str(DEFAULT_TASTE))
    ap.add_argument("--cache", default=str(DEFAULT_CACHE))
    ap.add_argument("--limit", type=int, default=0,
                    help="only the first N events (cheap local trial)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = pathlib.Path(args.src)
    doc = json.loads(src.read_text())
    events = list(doc.get("events") or [])
    if args.limit:
        events = events[: args.limit]

    taste = load_taste(pathlib.Path(args.taste))
    cache = load_cache(pathlib.Path(args.cache))
    client = make_client()
    if client is None:
        print("ANTHROPIC_API_KEY missing — local drop rules only.",
              file=sys.stderr)
        kept, stats = refine(events, taste, client=None, cache=cache, call=None)
    else:
        kept, stats = refine(events, taste, client, cache)
    pruned = 0
    if not args.limit:
        cache, pruned = prune_cache(
            cache, stats["seen_fps"], date.today(), taste["cache_prune_weeks"],
        )
    save_cache(pathlib.Path(args.cache), cache)

    print(f"refine: {len(events)} in, {len(kept)} kept, "
          f"{stats['dropped']} dropped, {stats['retagged']} retagged, "
          f"{stats['cache_hits']} cache hits, "
          f"{stats['api_calls']} Haiku calls ({stats['api_events']} events)"
          + (f", {pruned} cache pruned" if pruned else ""))

    if args.dry_run:
        return 0

    doc["events"] = kept
    doc["count"] = len(kept)
    out = pathlib.Path(args.out)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
