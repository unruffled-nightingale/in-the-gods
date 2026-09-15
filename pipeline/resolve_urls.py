#!/usr/bin/env python3
"""
resolve_urls.py — pick a working whats_on_url from url_candidates.

Does not rewrite venues.yaml (the file is hand-edited). Prints the winner
per venue so you can paste it back, or write a small JSON map.

    python pipeline/resolve_urls.py --venues data/venues.yaml \
        --ids almeida,young-vic,donmar
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9"}
TIMEOUT = 20


def candidates_for(venue):
    seen, out = set(), []
    for u in [venue.get("whats_on_url"), *(venue.get("url_candidates") or [])]:
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def try_url(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    except Exception as e:  # noqa: BLE001
        return {"url": url, "ok": False, "error": f"{type(e).__name__}: {e}"}
    final = r.url
    # treat soft-404s and tiny challenge pages as misses
    ok = r.status_code == 200 and len(r.text) > 800
    same_host = urlparse(url).netloc.replace("www.", "") in urlparse(final).netloc.replace("www.", "")
    return {
        "url": url,
        "ok": ok and same_host,
        "status": r.status_code,
        "final_url": final,
        "bytes": len(r.text),
        "same_host": same_host,
    }


# The guessable paths only get you so far. Venues label the page in their
# own nav: 'what-s-on' with hyphens, 'WhatsOn.html', 'now-next', '/Pages/
# Events/'. Four of the last batch were found this way and none of them
# would ever have been guessed.
NAV_TEXT = re.compile(
    r"^(what'?s\s*on|whats\s*on|now\s*&\s*next|events?|programme|program|"
    r"listings?|shows?|productions?|calendar)$", re.I)


def nav_listing_url(base_url):
    """Follow the site's own 'What's On' link. Prefers staying on the host."""
    try:
        r = requests.get(base_url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:  # noqa: BLE001
        return None

    host = urlparse(base_url).netloc.replace("www.", "")
    onsite, offsite = [], []
    for a in soup.find_all("a", href=True):
        if not NAV_TEXT.match(a.get_text(" ", strip=True)):
            continue
        href = urljoin(base_url, a["href"])
        if href.rstrip("/") == base_url.rstrip("/"):
            continue
        (onsite if host in urlparse(href).netloc.replace("www.", "")
         else offsite).append(href)
    for href in onsite + offsite:
        if try_url(href).get("ok"):
            return href
    return None


def _is_bare_home(url):
    return urlparse(url).path.strip("/") in ("", "index.php", "index.html")


def resolve_venue(venue):
    tried, winner = [], None
    for url in candidates_for(venue):
        hit = try_url(url)
        tried.append(hit)
        if hit.get("ok"):
            # prefer the candidate we asked for if it 200'd; keep final_url if redirected
            winner = hit["final_url"] if hit["final_url"].rstrip("/") != url.rstrip("/") else url
            break

    # A homepage is rarely the listing. Ask the site where it keeps one.
    if winner is None or _is_bare_home(winner):
        home = winner or f"https://{venue['domain']}/" if venue.get("domain") else winner
        found = nav_listing_url(home) if home else None
        if found:
            tried.append({"url": found, "ok": True, "via": "nav"})
            return found, tried
    return winner, tried


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--venues", default="data/venues.yaml")
    ap.add_argument("--ids", help="comma-separated venue ids (default: unverified only)")
    ap.add_argument("--out", default=".cache/url_map.json")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.venues).read_text())
    want = {i.strip() for i in args.ids.split(",")} if args.ids else None

    results = {}
    print(f"{'venue':<24}{'winner'}")
    print("-" * 78)
    for venue in cfg.get("venues", []):
        vid = venue["id"]
        if want and vid not in want:
            continue
        if not want and venue.get("whats_on_url"):
            continue
        print(f"--- {vid} ...", flush=True)
        winner, tried = resolve_venue(venue)
        results[vid] = {"whats_on_url": winner, "tried": tried}
        print(f"{vid:<24}{winner or 'NONE'}")
        if not winner:
            for t in tried:
                print(f"  {t.get('status') or 'ERR':<5} {t.get('url')}  "
                      f"{t.get('error') or t.get('bytes')}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2))
    print(f"\nwrote {args.out}")
    missing = [k for k, v in results.items() if not v["whats_on_url"]]
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
