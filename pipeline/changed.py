#!/usr/bin/env python3
"""
Exit 0 if the extract's events differ from the last committed snapshot,
1 if they don't.

`generated` and `window` shift on every run, so comparing whole files
would commit an identical extract every Monday forever. Only the events
decide, and they're normalised first so key ordering can't fake a change.

    python pipeline/changed.py data/extracts/latest.json
"""
import hashlib
import json
import pathlib
import subprocess
import sys


def fingerprint(events) -> str:
    canonical = json.dumps(events, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def committed_version(path: pathlib.Path):
    """The version of this file at HEAD, or None if it's new/unreadable."""
    try:
        blob = subprocess.run(
            ["git", "show", f"HEAD:{path.as_posix()}"],
            capture_output=True, check=True, text=True,
        ).stdout
        return json.loads(blob)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None


def main() -> int:
    path = pathlib.Path(sys.argv[1])
    new = json.loads(path.read_text())["events"]

    old_doc = committed_version(path)
    if old_doc is None:
        print("No committed extract to compare against — treating as changed.")
        return 0

    old = old_doc["events"]
    if fingerprint(old) == fingerprint(new):
        return 1

    old_keys = {(e["venue_id"], e["title"]) for e in old}
    new_keys = {(e["venue_id"], e["title"]) for e in new}
    added, gone = new_keys - old_keys, old_keys - new_keys

    print(f"{len(old)} -> {len(new)} events")
    for v, t in sorted(added):
        print(f"  + {t}  ({v})")
    for v, t in sorted(gone):
        print(f"  - {t}  ({v})")
    if not added and not gone:
        print("  (same shows, changed details)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
