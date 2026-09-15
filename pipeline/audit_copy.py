#!/usr/bin/env python3
"""
audit_copy.py — is the byline a hook, and does the description say more?

The crawler cannot tell good copy from bad, only present from absent. This
grades what came out and, with --live, re-fetches show pages so you can read
the extract against what the venue actually published. Every rule here was
added because it caught something real; see the traps in the README.

    python pipeline/audit_copy.py
    python pipeline/audit_copy.py --venue kings-head --live
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Each rule is (label, predicate over (byline, description, title)).
RULES = [
    ("no copy at all",
     lambda b, d, t: not b and not d),
    ("byline but no description",
     lambda b, d, t: bool(b) and not d),
    ("byline is a credit, not a hook",
     lambda b, d, t: bool(re.match(r"^(by|written by|directed by|book by)\b",
                                   b, re.I))),
    ("byline is booking chrome",
     lambda b, d, t: bool(re.search(
         r"\b(general sale|book(ing)? now|£\d|box office|running time|"
         r"latecomers|on sale)\b", b, re.I))),
    ("boilerplate leaked in",
     lambda b, d, t: bool(re.search(
         r"(cookie|newsletter|committed to ensuring|enable javascript|"
         r"privacy policy)", f"{b} {d}", re.I))),
    ("byline only restates the title",
     lambda b, d, t: bool(b) and b.strip().rstrip(".").lower() == t.strip().lower()),
    ("description just repeats the byline",
     lambda b, d, t: bool(b) and bool(d) and d.startswith(b)),
    ("byline too short to sell anything",
     lambda b, d, t: bool(b) and len(b) < 25),
]


def grade(events):
    hits = defaultdict(list)
    for e in events:
        b = (e.get("byline") or "").strip()
        d = (e.get("description") or "").strip()
        for label, rule in RULES:
            if rule(b, d, e.get("title") or ""):
                hits[label].append(e)
                if label == "no copy at all":
                    break
    return hits


def live_compare(event, paras=4):
    """Print the extract next to the paragraphs the page actually serves."""
    from bs4 import BeautifulSoup

    from fetch import polite_get

    print(f"  url: {event['url']}")
    print(f"  BYLINE ({len(event.get('byline') or '')}): {event.get('byline')}")
    desc = event.get("description") or ""
    print(f"  DESCR  ({len(desc)}): {desc[:300]}{'...' if len(desc) > 300 else ''}")
    try:
        soup = BeautifulSoup(polite_get(event["url"]), "html.parser")
    except Exception as e:                                    # noqa: BLE001
        print(f"  live: unreachable — {type(e).__name__}")
        return
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    body = [re.sub(r"\s+", " ", p.get_text(" ", strip=True))
            for p in soup.find_all("p")]
    print("  --- what the page says ---")
    for p in [p for p in body if len(p) > 45][:paras]:
        print(f"    {p[:200]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--extract", default="data/extracts/latest.json")
    ap.add_argument("--venue", help="only this venue id")
    ap.add_argument("--live", action="store_true",
                    help="re-fetch show pages and print them alongside")
    ap.add_argument("--limit", type=int, default=3,
                    help="examples shown per problem")
    args = ap.parse_args()

    events = json.loads(Path(args.extract).read_text())["events"]
    if args.venue:
        events = [e for e in events if e["venue_id"] == args.venue]
    if not events:
        print("no events matched")
        return 1

    bl = [len(e["byline"]) for e in events if e.get("byline")]
    de = [len(e["description"]) for e in events if e.get("description")]
    n = len(events)
    print(f"{n} events / {len({e['venue_id'] for e in events})} venues")
    if bl:
        print(f"  byline      {len(bl):>4} ({100 * len(bl) // n}%)  "
              f"median {statistics.median(bl):.0f}  max {max(bl)}")
    if de:
        print(f"  description {len(de):>4} ({100 * len(de) // n}%)  "
              f"median {statistics.median(de):.0f}  max {max(de)}")

    hits = grade(events)
    if not hits:
        print("\nnothing flagged")
    for label, rows in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        venues = dict(Counter(e["venue_id"] for e in rows).most_common(4))
        print(f"\n{len(rows):>4}  {label}\n        {venues}")
        for e in rows[:args.limit]:
            print(f"        - [{e['venue_id']}] {e['title'][:40]!r}: "
                  f"{(e.get('byline') or '')[:70]!r}")

    if args.live:
        seen = set()
        for rows in hits.values():
            for e in rows[:args.limit]:
                if e["url"] in seen:
                    continue
                seen.add(e["url"])
                print("\n" + "=" * 78)
                print(f"[{e['venue_id']}] {e['title']}")
                live_compare(e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
