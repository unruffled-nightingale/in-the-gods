#!/usr/bin/env python3
"""
patch_venue.py — merge verified fetch config into venues.yaml in place.

venues.yaml is hand-edited and carries comments and deliberate ordering, so
this replaces the `fetch_method / one_stage / url_verified` block inside a
named venue rather than round-tripping the whole file through yaml.

The patch file is a mapping of venue id to the fields to write:

    national-theatre:
      fetch_method: static
      strategy: selectors
      url_verified: true
      selectors:
        show_card: .c-event-card

    python pipeline/patch_venue.py --patch .cache/onboard.yaml
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import yaml

# always superseded, whether or not the patch names them: these three are the
# markers of an un-onboarded venue
STALE = ("fetch_method", "one_stage", "url_verified", "strategy", "last_verified")


def render(fields, indent="  "):
    body = yaml.dump(fields, default_flow_style=False, sort_keys=False,
                     allow_unicode=True, width=200)
    return "".join(f"{indent}{line}\n" for line in body.splitlines())


def patch(lines, patches):
    """Rewrite each named venue's config, leaving its identity fields alone.

    A patch owns exactly the keys it names, plus the un-onboarded markers.
    Any other key in the block — and its nested lines — is left untouched, so
    curated fields like `notes` survive unless the patch replaces them.
    """
    id_re = re.compile(r"^- id: (\S+)\s*$")
    key_re = re.compile(r"^  ([a-z_]+):")

    out, applied = [], []
    current, fields, written = None, None, False
    dropping = False
    for line in lines:
        m = id_re.match(line)
        if m:
            current, fields, written, dropping = m.group(1), patches.get(m.group(1)), False, False
            out.append(line)
            continue

        if fields:
            km = key_re.match(line)
            if km:
                stale = set(STALE)
                # a verified venue is no longer blocked; drop the reason
                if fields.get("url_verified"):
                    stale.add("blocked_by")
                dropping = km.group(1) in stale or km.group(1) in fields
                if dropping and not written:
                    out.append(render(fields))
                    applied.append(current)
                    written = True
                if dropping:
                    continue
            elif dropping and line.startswith("    "):
                continue                     # nested child of a dropped key
            elif dropping and not line.strip():
                continue
            else:
                dropping = False
        out.append(line)
    return out, applied


def dedupe(lines):
    """Drop earlier copies of a repeated key within a venue block.

    The bootstrap wrote `last_verified` into the identity section and the
    onboarding pass wrote it again below, so 32 venues carry the key twice.
    The yaml loader already resolves that to the last one, which is the
    intended value — this only removes the shadowed line and its children.
    """
    id_re = re.compile(r"^- id: (\S+)\s*$")
    key_re = re.compile(r"^  ([a-z_]+):")

    blocks, current = [], []
    for line in lines:
        if id_re.match(line) and current:
            blocks.append(current)
            current = []
        current.append(line)
    if current:
        blocks.append(current)

    out, removed = [], []
    for block in blocks:
        keys = [key_re.match(l).group(1) for l in block if key_re.match(l)]
        dupes = {k for k in keys if keys.count(k) > 1}
        if not dupes:
            out.extend(block)
            continue
        vid = id_re.match(block[0]).group(1) if id_re.match(block[0]) else "?"
        left = dict.fromkeys(dupes)
        for k in dupes:
            left[k] = keys.count(k)
        keep, dropping = [], False
        for line in block:
            km = key_re.match(line)
            if km:
                k = km.group(1)
                dropping = k in dupes and left[k] > 1
                if dropping:
                    left[k] -= 1
                    removed.append((vid, k))
                    continue
            elif dropping and (line.startswith("    ") or not line.strip()):
                continue
            else:
                dropping = False
            keep.append(line)
        out.extend(keep)
    return out, removed


def duplicate_keys(text):
    """Guard against a patch leaving two of the same key in one block."""
    id_re = re.compile(r"^- id: (\S+)\s*$")
    key_re = re.compile(r"^  ([a-z_]+):")
    bad, current, seen = [], None, set()
    for line in text.splitlines():
        m = id_re.match(line)
        if m:
            current, seen = m.group(1), set()
            continue
        km = key_re.match(line)
        if not km:
            continue
        if km.group(1) in seen:
            bad.append((current, km.group(1)))
        seen.add(km.group(1))
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--venues", default="data/venues.yaml")
    ap.add_argument("--patch")
    ap.add_argument("--dedupe", action="store_true",
                    help="drop shadowed duplicate keys, write nothing else")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.patch and not args.dedupe:
        ap.error("need --patch or --dedupe")

    if args.dedupe:
        path = Path(args.venues)
        before = yaml.safe_load(path.read_text())
        lines, removed = dedupe(path.read_text().splitlines(keepends=True))
        text = "".join(lines)
        after = yaml.safe_load(text)
        assert before == after, "dedupe changed the parsed registry"
        for vid, key in removed:
            print(f"  dropped shadowed {key:<16} on {vid}")
        print(f"\n{len(removed)} lines removed, "
              f"{len(after['venues'])} venues, parsed result identical")
        if not args.dry_run:
            path.write_text(text)
            print(f"wrote {path}")
        return 0

    patches = yaml.safe_load(Path(args.patch).read_text()) or {}
    for fields in patches.values():
        fields.setdefault("last_verified", date.today().isoformat())

    path = Path(args.venues)
    lines = path.read_text().splitlines(keepends=True)
    out, applied = patch(lines, patches)

    missing = sorted(set(patches) - set(applied))
    for vid in applied:
        v = patches[vid]
        print(f"  patched {vid:22} verified={v.get('url_verified')} "
              f"strategy={v.get('strategy')}")
    for vid in missing:
        print(f"  MISS    {vid:22} not found in {path}")

    text = "".join(out)
    reparsed = yaml.safe_load(text)          # never write a broken registry
    print(f"\nregistry parses: {len(reparsed['venues'])} venues")

    dupes = duplicate_keys(text)
    mine = [d for d in dupes if d[0] in set(applied)]
    if dupes:
        print(f"\n{len(dupes)} duplicate keys in the registry "
              f"(the yaml loader keeps the last silently):")
        for vid, key in dupes[:8]:
            print(f"  {vid}: {key}")
        if len(dupes) > 8:
            print(f"  ... and {len(dupes) - 8} more")
    if mine:
        raise SystemExit("refusing to write: this patch would leave duplicate "
                         f"keys on {', '.join(v for v, _ in mine)}")

    if args.dry_run:
        print("dry run, nothing written")
        return 0
    path.write_text(text)
    print(f"wrote {path}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
