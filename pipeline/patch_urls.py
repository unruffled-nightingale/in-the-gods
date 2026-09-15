#!/usr/bin/env python3
"""
patch_urls.py — write resolved whats_on_url values into venues.yaml in place.

venues.yaml is hand-edited and carries comments and deliberate ordering, so
this does targeted line edits rather than a yaml round-trip.

    python pipeline/patch_urls.py --maps .cache/url_map.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def load_winners(paths):
    winners = {}
    for p in paths:
        data = json.loads(Path(p).read_text())
        for vid, rec in data.items():
            url = rec.get("whats_on_url") if isinstance(rec, dict) else rec
            if url:
                winners[vid] = url
    return winners


def patch(lines, winners):
    """Replace the whats_on_url line inside each named venue block."""
    id_re = re.compile(r"^- id: (\S+)\s*$")
    url_re = re.compile(r"^(\s+)whats_on_url:\s*(.*)$")

    current = None
    done, skipped = {}, {}
    for i, line in enumerate(lines):
        m = id_re.match(line)
        if m:
            current = m.group(1)
            continue
        if current is None or current not in winners:
            continue
        m = url_re.match(line)
        if not m:
            continue
        indent, existing = m.group(1), m.group(2).strip()
        if existing and existing != "null":
            skipped[current] = existing
        else:
            lines[i] = f"{indent}whats_on_url: {winners[current]}\n"
            done[current] = winners[current]
        current = None  # only the first whats_on_url in a block
    return done, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--venues", default="data/venues.yaml")
    ap.add_argument("--maps", required=True, help="comma-separated url_map json files")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    winners = load_winners([p.strip() for p in args.maps.split(",") if p.strip()])
    path = Path(args.venues)
    lines = path.read_text().splitlines(keepends=True)
    done, skipped = patch(lines, winners)

    for vid, url in sorted(done.items()):
        print(f"  set  {vid:24} {url}")
    for vid, url in sorted(skipped.items()):
        print(f"  kept {vid:24} {url}")
    missing = sorted(set(winners) - set(done) - set(skipped))
    for vid in missing:
        print(f"  MISS {vid:24} not found in {path}")

    if args.dry_run:
        print("\ndry run, nothing written")
        return 0

    path.write_text("".join(lines))
    print(f"\npatched {len(done)} urls -> {path}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
