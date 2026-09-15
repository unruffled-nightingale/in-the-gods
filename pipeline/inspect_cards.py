#!/usr/bin/env python3
"""
inspect_cards.py — show the inside of a listing page's show cards.

Selector work needs to see the real markup, not a class-frequency count.
Point this at a venue and it prints the child structure of the first few
cards so the title/dates/link/credits selectors can be read straight off.

    # what repeats on the page?
    python pipeline/inspect_cards.py --id barbican --suggest

    # what is inside a specific card?
    python pipeline/inspect_cards.py --id barbican --card .listing--event

    # try a full selector set before writing it into yaml
    python pipeline/inspect_cards.py --id barbican --card .listing--event \
        --title .search-listing__title --dates .search-listing__date
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import yaml
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))

NAV = re.compile(r"nav|menu|footer|header|dropdown|social|search|cookie|skip",
                 re.I)
EVENTISH = re.compile(
    r"event|show|performance|production|listing|whats-on|card|summary-item|"
    r"collection-item|programme|calendar", re.I)


def sig(el):
    cls = el.get("class")
    return ".".join(sorted(cls)) if cls else ""


def suggest(soup):
    """Rank repeated class signatures that plausibly wrap one show each."""
    counter = Counter()
    for el in soup.find_all(["article", "li", "div", "a", "section"]):
        s = sig(el)
        if s and len(s) <= 120:
            counter[s] += 1
    rows = []
    for s, n in counter.items():
        if not 2 <= n <= 80 or NAV.search(s):
            continue
        rows.append((EVENTISH.search(s) is not None, n, s))
    rows.sort(key=lambda r: (-r[0], -r[1]))
    print(f"{'':2}{'n':>4}  {'eventish':<9} signature")
    print("-" * 78)
    for eventish, n, s in rows[:25]:
        print(f"  {n:>4}  {'yes' if eventish else '':<9} .{s}")


def outline(card, depth=0, max_depth=4):
    """Print tag/class/text for each descendant, shallow first."""
    for child in card.find_all(recursive=False):
        text = child.get_text(" ", strip=True)
        s = sig(child)
        label = child.name + (f".{s}" if s else "")
        href = child.get("href")
        extra = f"  href={href[:60]}" if href else ""
        snippet = text[:70].replace("\n", " ")
        print(f"{'  ' * (depth + 1)}{label:<52}{extra}")
        if snippet and len(child.find_all(recursive=False)) == 0:
            print(f"{'  ' * (depth + 2)}> {snippet!r}")
        if depth + 1 < max_depth:
            outline(child, depth + 1, max_depth)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--venues", default="data/venues.yaml")
    ap.add_argument("--id", required=True)
    ap.add_argument("--url", help="override the venue's whats_on_url")
    ap.add_argument("--card", help="card selector to look inside")
    ap.add_argument("--suggest", action="store_true",
                    help="list repeated class signatures instead")
    ap.add_argument("--title")
    ap.add_argument("--dates")
    ap.add_argument("--link")
    ap.add_argument("--credits")
    ap.add_argument("--blurb")
    ap.add_argument("--n", type=int, default=2, help="how many cards to show")
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--fresh", action="store_true", help="bypass the http cache")
    ap.add_argument("--render", action="store_true",
                    help="fetch through Chromium (also the default when the "
                         "venue's fetch_method is rendered)")
    args = ap.parse_args()

    from fetch import polite_get, parse_date_range, render_for
    from strategies import _pick_href, _pick_text

    cfg = yaml.safe_load(Path(args.venues).read_text())
    venue = next((v for v in cfg["venues"] if v["id"] == args.id), None)
    if venue is None:
        raise SystemExit(f"no venue {args.id!r}")
    url = args.url or venue.get("whats_on_url")
    if not url:
        raise SystemExit(f"{args.id} has no whats_on_url")
    if args.render:
        venue = {**venue, "render": True}

    print(f"# {args.id}  {url}\n")
    with render_for(venue):
        html = polite_get(url, use_cache=not args.fresh)
    soup = BeautifulSoup(html, "html.parser")

    if args.suggest or not args.card:
        suggest(soup)
        return 0

    cards = soup.select(args.card)
    print(f"{len(cards)} cards match {args.card!r}\n")
    if not cards:
        return 1

    # if a selector set was supplied, report what it would actually extract
    if args.title or args.dates or args.link:
        print("--- extraction preview ---")
        for card in cards[:12]:
            title = _pick_text(card, args.title)
            dates = (_pick_text(card, args.dates) if args.dates
                     else card.get_text(" ", strip=True))
            start, end = parse_date_range(dates or "")
            href = _pick_href(card, args.link, url)
            print(f"  {str(title)[:44]:<46}{str(start):<12}{str(end):<12}"
                  f"{(href or '')[:52]}")
            if args.credits:
                print(f"    credits: {_pick_text(card, args.credits)}")
            if args.blurb:
                print(f"    blurb  : {str(_pick_text(card, args.blurb))[:90]}")
        print()

    for i, card in enumerate(cards[:args.n]):
        print(f"--- card {i} <{card.name}.{sig(card)}> ---")
        if card.get("href"):
            print(f"  (card is itself a link: {card['href'][:70]})")
        outline(card, max_depth=args.depth)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
