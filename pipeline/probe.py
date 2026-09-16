#!/usr/bin/env python3
"""
probe.py — diagnose the best extraction strategy for each venue in venues.yaml

For each venue, reports:
  - HTTP status / final URL
  - JSON-LD presence, and whether it contains schema.org Event objects
  - RSS/Atom feed links and sitemap availability
  - Ticketing platform hints (Spektrix, TicketSolve, TicketSource, etc.)
  - Whether the page is JS-rendered (little/no text in raw HTML)
  - Rough text volume + candidate repeated blocks (show cards)

Writes .cache/probe_results.json for later inspection.
"""

import json
import re
import sys
from collections import Counter
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

# Kinsta and friends 403 any UA advertising a browser this far out of date,
# so this needs bumping when it drifts. Two-part versions look fake: real
# Chrome sends four.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9"}
TIMEOUT = 25

PLATFORM_PATTERNS = {
    "spektrix":    r"spektrix\.com|spektrix\.js|SpektrixSecure",
    "ticketsolve": r"ticketsolve\.com",
    "ticketsource": r"ticketsource\.co\.uk|ticketsource\.com",
    "eventbrite":  r"eventbrite\.co\.uk|eventbrite\.com",
    "seetickets":  r"seetickets\.com",
    "ticketco":    r"ticketco\.events",
    "tickettailor": r"tickettailor\.com",
    "citizenticket": r"citizenticket\.co\.uk",
    "line-up":     r"lineupnow\.com|line-up\.io",
    "wordpress":   r"/wp-content/|/wp-json/",
    "squarespace": r"squarespace\.com|static1\.squarespace",
    "nextjs":      r"__NEXT_DATA__|/_next/static",
    "nuxt":        r"__NUXT__",
    "react-root":  r'<div id="root"></div>|<div id="__next"></div>',
    "sanity":      r"cdn\.sanity\.io|sanity\.io",
}

# CPTs that actually hold listings (not WP internals).
WP_LISTING_TYPES = {
    "productions", "production", "whatson", "whats-on", "event", "events",
    "show", "shows", "performance", "performances",
}

SANITY_PROJECT_RE = re.compile(
    r"cdn\.sanity\.io/(?:images|files)/([a-z0-9]+)/", re.I
)


def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        return r, None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def find_jsonld(soup):
    """Return (count, event_count, sample_keys) for JSON-LD blocks."""
    blocks = soup.find_all("script", type="application/ld+json")
    events, sample_keys, types_seen = 0, [], Counter()
    for b in blocks:
        raw = b.string or b.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # some sites emit multiple concatenated objects or trailing commas
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                t = node.get("@type")
                tl = [t] if isinstance(t, str) else (t or [])
                for tt in tl:
                    types_seen[tt] += 1
                    if "Event" in str(tt):
                        events += 1
                        if not sample_keys:
                            sample_keys = sorted(node.keys())
                for v in node.values():
                    if isinstance(v, (dict, list)):
                        stack.append(v)
    return len(blocks), events, sample_keys, dict(types_seen)


def find_feeds(soup, base):
    feeds = []
    for link in soup.find_all("link", rel=lambda v: v and "alternate" in v):
        t = (link.get("type") or "").lower()
        if "rss" in t or "atom" in t or "xml" in t:
            feeds.append(urljoin(base, link.get("href", "")))
    return feeds


def detect_platforms(html):
    hits = []
    for name, pat in PLATFORM_PATTERNS.items():
        if re.search(pat, html, re.IGNORECASE):
            hits.append(name)
    return hits


def candidate_cards(soup):
    """Find repeated class signatures that look like show cards."""
    counter = Counter()
    for el in soup.find_all(["article", "li", "div", "a"]):
        cls = el.get("class")
        if not cls:
            continue
        sig = ".".join(sorted(cls))
        if len(sig) > 120:
            continue
        counter[sig] += 1
    # repeated 3-60 times = plausible list of shows
    cands = [(s, n) for s, n in counter.items() if 3 <= n <= 60]
    cands.sort(key=lambda x: -x[1])
    return cands[:8]


def visible_text_len(soup):
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return len(re.sub(r"\s+", " ", soup.get_text(" ", strip=True)))


def check_sitemap(base_url):
    root = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    for path in ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml"):
        r, err = fetch(root + path)
        if r is not None and r.status_code == 200 and "<" in r.text[:200]:
            return root + path
    return None


def find_sanity_project(html):
    m = SANITY_PROJECT_RE.search(html or "")
    return m.group(1) if m else None


def find_wp_listing_types(base_url):
    """Return [{slug, rest_base, endpoint}] for listing-like WordPress CPTs."""
    root = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    r, err = fetch(root + "/wp-json/wp/v2/types")
    if err or r is None or r.status_code != 200:
        return []
    try:
        types = r.json()
    except json.JSONDecodeError:
        return []
    out = []
    for slug, meta in (types or {}).items():
        if slug not in WP_LISTING_TYPES:
            continue
        rest = (meta or {}).get("rest_base") or slug
        out.append({
            "slug": slug,
            "rest_base": rest,
            "endpoint": f"{root}/wp-json/wp/v2/{rest}",
        })
    return out


def recommend_strategy(out):
    """Map probe signals onto fetch.py strategy names.

    Ticketing platforms (Spektrix etc.) are *not* a listings strategy — they
    sell seats. Prefer JSON-LD only when Event objects carry their own URL;
    otherwise a card selector usually has the deep link (CPT).
    """
    if out.get("error") or not out.get("url"):
        return "skip"
    if out.get("sanity_project"):
        return "sanity"
    jsonld_ok = (out.get("jsonld_events") or 0) > 0
    jsonld_has_url = bool(out.get("jsonld_has_url"))
    has_cards = bool(out.get("card_candidates"))
    if jsonld_ok and jsonld_has_url:
        return "jsonld"
    if has_cards:
        return "selectors"
    if jsonld_ok:
        return "jsonld"
    if out.get("wp_rest"):
        return "wp_rest"
    if out.get("js_rendered_suspect"):
        return "skip"
    return "selectors"


def probe(venue):
    vid = venue.get("id")
    url = venue.get("whats_on_url")
    out = {"id": vid, "name": venue.get("name"), "url": url}

    if not url:
        out["error"] = "no whats_on_url"
        out["recommended_strategy"] = "skip"
        out["recommended_tier"] = "skip"
        return out

    r, err = fetch(url)
    if err:
        out["error"] = err
        out["recommended_strategy"] = "skip"
        out["recommended_tier"] = "skip"
        return out

    out["status"] = r.status_code
    out["final_url"] = r.url
    html = r.text
    out["html_bytes"] = len(html)

    soup = BeautifulSoup(html, "html.parser")

    n_blocks, n_events, keys, types_seen = find_jsonld(soup)
    out["jsonld_blocks"] = n_blocks
    out["jsonld_events"] = n_events
    out["jsonld_event_keys"] = keys
    out["jsonld_types"] = types_seen
    out["jsonld_has_url"] = "url" in (keys or [])

    out["feeds"] = find_feeds(soup, r.url)
    out["platforms"] = detect_platforms(html)
    out["text_len"] = visible_text_len(BeautifulSoup(html, "html.parser"))
    out["js_rendered_suspect"] = out["text_len"] < 1500
    out["card_candidates"] = candidate_cards(soup)
    out["sitemap"] = check_sitemap(r.url)
    out["sanity_project"] = find_sanity_project(html)
    out["wp_rest"] = find_wp_listing_types(r.url) if "wordpress" in out["platforms"] else []

    # recommend a tier (legacy) and a fetch strategy name
    if n_events > 0:
        tier = "1_jsonld"
    elif out["sanity_project"]:
        tier = "2_cms"
    elif any(p in out["platforms"] for p in
             ("spektrix", "ticketsolve", "ticketsource", "tickettailor")):
        tier = "2_platform"
    elif out["feeds"] or out["sitemap"] or out["wp_rest"]:
        tier = "3_feed_or_selectors"
    elif out["js_rendered_suspect"]:
        tier = "4_bespoke_or_search"
    else:
        tier = "3_feed_or_selectors"
    out["recommended_tier"] = tier
    out["recommended_strategy"] = recommend_strategy(out)
    return out


def main():
    import argparse
    from pathlib import Path

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("config", nargs="?",
                    help="path to venues.yaml (positional, optional)")
    ap.add_argument("--venues", dest="venues",
                    help="path to venues.yaml (preferred)")
    ap.add_argument("--out", default=".cache/probe_results.json")
    ap.add_argument("--venue", help="restrict the probe to a single venue id")
    ap.add_argument("--ids", help="comma-separated venue ids")
    args = ap.parse_args()

    path = args.venues or args.config or "data/venues.yaml"
    with open(path) as fh:
        cfg = yaml.safe_load(fh)

    want = None
    if args.ids:
        want = {i.strip() for i in args.ids.split(",") if i.strip()}
    elif args.venue:
        want = {args.venue}

    results = []
    for v in cfg.get("venues", []):
        if want and v.get("id") not in want:
            continue
        print(f"--- probing {v.get('id')} ...", flush=True)
        res = probe(v)
        results.append(res)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        json.dump(results, fh, indent=2)

    # summary table
    print("\n" + "=" * 88)
    print(f"{'venue':<24}{'stat':<6}{'JSON-LD':<10}{'text':<9}{'strategy':<12}{'tier'}")
    print("=" * 88)
    for r in results:
        if "error" in r:
            print(f"{r['id']:<24}{'ERR':<6}{'-':<10}{'-':<9}{r.get('recommended_strategy','skip'):<12}{r['error'][:28]}")
            continue
        jl = f"{r['jsonld_events']}ev/{r['jsonld_blocks']}b"
        print(f"{r['id']:<24}{r['status']:<6}{jl:<10}"
              f"{r['text_len']:<9}{r.get('recommended_strategy',''):<12}{r['recommended_tier']}")
    print("=" * 88)

    for r in results:
        if "error" in r:
            continue
        print(f"\n### {r['id']}")
        print(f"  platforms : {r['platforms'] or 'none detected'}")
        print(f"  feeds     : {r['feeds'] or 'none'}")
        print(f"  sitemap   : {r['sitemap'] or 'none'}")
        if r["jsonld_types"]:
            print(f"  ld types  : {r['jsonld_types']}")
        if r["jsonld_event_keys"]:
            print(f"  ev keys   : {r['jsonld_event_keys'][:12]}")
        if r.get("sanity_project"):
            print(f"  sanity    : {r['sanity_project']}")
        if r.get("wp_rest"):
            print(f"  wp rest   : {[w['endpoint'] for w in r['wp_rest']]}")
        print(f"  strategy  : {r.get('recommended_strategy')}")
        if r["card_candidates"]:
            print("  card cands:")
            for sig, n in r["card_candidates"][:4]:
                print(f"      {n:>3}x  .{sig[:70]}")


if __name__ == "__main__":
    main()
