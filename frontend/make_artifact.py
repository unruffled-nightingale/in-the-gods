#!/usr/bin/env python3
"""Inject the extract into the HTML artifact template.

    python frontend/make_artifact.py \
        --events data/extracts/latest.json \
        --template frontend/template.html \
        --out frontend/theatre.html
"""
import argparse
import json
from pathlib import Path

import yaml

# Tighter labels for the original five. Everything else takes name/area from
# data/venues.yaml so new houses don't show up as raw ids.
VENUE_OVERRIDES = {
    "arcola": {"name": "Arcola Theatre", "area": "Dalston, E8"},
    "southwark-playhouse": {"name": "Southwark Playhouse", "area": "Borough, SE1"},
    "wiltons": {"name": "Wilton's Music Hall", "area": "Shadwell, E1"},
    "camden-peoples-theatre": {"name": "Camden People's Theatre", "area": "Euston, NW1"},
    "the-yard": {"name": "The Yard", "area": "Hackney Wick, E9"},
}


def load_venue_meta(path="data/venues.yaml"):
    p = Path(path)
    out = {}
    if p.exists():
        cfg = yaml.safe_load(p.read_text()) or {}
        for v in cfg.get("venues") or []:
            loc = v.get("location") or {}
            area = loc.get("area") or ""
            out[v["id"]] = {"name": v.get("name") or v["id"], "area": area}
    out.update(VENUE_OVERRIDES)
    return out

PLACEHOLDER = "/*__EVENTS__*/[]"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--events", default="data/extracts/latest.json")
    ap.add_argument("--template", default="frontend/template.html")
    ap.add_argument("--out", default="frontend/theatre.html")
    args = ap.parse_args()

    events = json.loads(Path(args.events).read_text())["events"]
    venues = load_venue_meta()

    for i, e in enumerate(events):
        e["id"] = f"e{i:03d}"
        v = venues.get(e["venue_id"], {})
        e["venue_name"] = v.get("name", e["venue_id"])
        e["venue_area"] = v.get("area", "")

    html = Path(args.template).read_text()
    if PLACEHOLDER not in html:
        raise SystemExit(f"placeholder {PLACEHOLDER!r} not found in {args.template}")
    html = html.replace(PLACEHOLDER, json.dumps(events, ensure_ascii=False))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print(f"wrote {len(events)} events -> {out}")


if __name__ == "__main__":
    main()
