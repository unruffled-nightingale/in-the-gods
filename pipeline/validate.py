#!/usr/bin/env python3
"""
validate.py — does probe's recommended strategy actually extract listings?

For each venue, probe the listings page, then run fetch stage-1 extractors
against the same page (jsonld / yaml selectors / sanity / wp_rest). Score
each attempt and report whether probe would have picked a strategy that
returns dated, deep-linked shows.

Usage:
    python pipeline/validate.py --venues data/venues.sample.yaml
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

import yaml

# scripts are run as `python pipeline/validate.py`
sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe import probe  # noqa: E402
from strategies import extract  # noqa: E402


def score(rows, listings_url):
    listings = (listings_url or "").rstrip("/")
    n = len(rows)
    dated = sum(1 for r in rows if r.get("first_date"))
    own_url = 0
    for r in rows:
        u = (r.get("url") or "").rstrip("/")
        if u and u != listings:
            own_url += 1
    desc = sum(1 for r in rows if r.get("description"))
    tags = sum(1 for r in rows if r.get("venue_tags"))
    # dated deep-links are the thing we'd actually keep
    useful = sum(
        1 for r in rows
        if r.get("title") and r.get("first_date")
        and (r.get("url") or "").rstrip("/") != listings
    )
    return {
        "n": n,
        "dated": dated,
        "own_url": own_url,
        "desc": desc,
        "tags": tags,
        "useful": useful,
    }


def try_extract(venue, strategy, extra=None):
    v = deepcopy(venue)
    v["strategy"] = strategy
    if extra:
        v.update(extra)
    try:
        rows = extract(v, use_cache=True)
    except Exception as e:  # noqa: BLE001
        return [], f"{type(e).__name__}: {e}"
    return rows, None


def probe_guess_selectors(probe_out):
    """Turn the top card-candidate signature into a generic selector set."""
    cands = probe_out.get("card_candidates") or []
    if not cands:
        return None
    sig, _n = cands[0]
    card = "." + sig if not sig.startswith(".") else sig
    return {
        "show_card": card,
        "title": "h2, h3, h4, a",
        "dates": "[class*=date], time, .edate, .EV_ListDate",
        "link": "a[href]",
    }


def candidates_for(venue, probe_out):
    """Which fetch strategies are worth trying, given probe + yaml."""
    out = []
    out.append(("jsonld", None))
    if venue.get("selectors", {}).get("show_card"):
        out.append(("selectors", None))
    guess = probe_guess_selectors(probe_out)
    if guess:
        out.append(("selectors:probe", {"selectors": guess, "require_space": False}))
    sanity = (venue.get("sanity") or {})
    project = sanity.get("project_id") or probe_out.get("sanity_project")
    if project:
        extra = {}
        if not venue.get("sanity"):
            extra["sanity"] = {
                "project_id": project,
                "dataset": "production",
                "api_version": "2021-10-21",
            }
            # Yard (and most Sanity theatre sites) use /events/{slug}
            host = urlparse(probe_out.get("final_url") or venue.get("whats_on_url") or "").netloc
            extra["show_url_pattern"] = f"https://{host}/events/{{slug}}"
        out.append(("sanity", extra or None))
    wp = probe_out.get("wp_rest") or []
    if venue.get("wp_rest") or wp:
        extra = {}
        if not venue.get("wp_rest") and wp:
            extra["wp_rest"] = {"endpoint": wp[0]["endpoint"], "per_page": 20}
        out.append(("wp_rest", extra or None))
    return out


def fmt_score(s):
    if s is None:
        return "—"
    return f"{s['useful']}u/{s['n']}n"


def validate_venue(venue):
    vid = venue["id"]
    print(f"--- validating {vid} ...", flush=True)
    p = probe(venue)
    recommended = p.get("recommended_strategy") or "skip"
    yaml_strategy = venue.get("strategy") or "auto"

    attempts = {}
    for name, extra in candidates_for(venue, p):
        rows, err = try_extract(venue, name.split(":")[0], extra)
        attempts[name] = {
            "error": err,
            "score": None if err else score(rows, venue.get("whats_on_url")),
            "sample": [r.get("title") for r in rows[:3]] if rows else [],
        }

    scored = {k: v["score"] for k, v in attempts.items() if v["score"]}
    best_name, best = (None, None)
    if scored:
        best_name, best = max(scored.items(), key=lambda kv: (kv[1]["useful"], kv[1]["dated"], kv[1]["n"]))

    probe_score = None
    # selectors:probe is a stand-in when yaml has no selectors
    probe_key = recommended
    if recommended == "selectors" and "selectors" not in attempts and "selectors:probe" in attempts:
        probe_key = "selectors:probe"
    if probe_key in attempts:
        probe_score = attempts[probe_key]["score"]

    probe_works = bool(probe_score and probe_score["useful"] > 0)
    yaml_score = attempts.get(yaml_strategy, {}).get("score") if yaml_strategy in attempts else None
    agrees = (
        best_name is not None
        and recommended in (best_name, best_name.split(":")[0])
    ) or (
        probe_works and best is not None and probe_score["useful"] == best["useful"]
    )

    return {
        "id": vid,
        "probe": recommended,
        "yaml": yaml_strategy,
        "best": best_name,
        "agrees": agrees,
        "probe_works": probe_works,
        "attempts": attempts,
        "probe_raw": {
            "jsonld_events": p.get("jsonld_events"),
            "jsonld_has_url": p.get("jsonld_has_url"),
            "platforms": p.get("platforms"),
            "sanity_project": p.get("sanity_project"),
            "wp_rest": [w["slug"] for w in (p.get("wp_rest") or [])],
            "js_rendered_suspect": p.get("js_rendered_suspect"),
        },
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--venues", default="data/venues.sample.yaml")
    ap.add_argument("--venue")
    ap.add_argument("--ids", help="comma-separated venue ids")
    ap.add_argument("--out", default=".cache/probe_validation.json")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.venues).read_text())
    venues = cfg.get("venues", [])
    if args.ids:
        want = {i.strip() for i in args.ids.split(",") if i.strip()}
        venues = [v for v in venues if v.get("id") in want]
    elif args.venue:
        venues = [v for v in venues if v.get("id") == args.venue]

    results = [validate_venue(v) for v in venues]

    print("\n" + "=" * 96)
    print(f"{'venue':<24}{'probe':<12}{'yaml':<12}{'best':<16}{'jsonld':<10}{'sel':<10}{'sanity':<10}{'wp':<8}agree")
    print("=" * 96)
    for r in results:
        att = r["attempts"]
        def cell(key):
            a = att.get(key) or att.get(key + ":probe")
            if not a:
                return "—"
            if a["error"]:
                return "ERR"
            return fmt_score(a["score"])
        print(
            f"{r['id']:<24}{r['probe']:<12}{r['yaml']:<12}{(r['best'] or '—'):<16}"
            f"{cell('jsonld'):<10}{cell('selectors'):<10}{cell('sanity'):<10}{cell('wp_rest'):<8}"
            f"{'YES' if r['agrees'] else 'NO'}"
        )
    print("=" * 96)
    print("u = dated rows with a show URL distinct from the listings page (the keepable set).")
    print("n = raw rows the extractor returned.\n")

    for r in results:
        print(f"### {r['id']}  probe={r['probe']}  yaml={r['yaml']}  best={r['best']}")
        print(f"    signals: jsonld={r['probe_raw']['jsonld_events']}ev "
              f"url_in_ld={r['probe_raw']['jsonld_has_url']} "
              f"platforms={r['probe_raw']['platforms']} "
              f"sanity={r['probe_raw']['sanity_project']} "
              f"wp={r['probe_raw']['wp_rest']}")
        for name, att in r["attempts"].items():
            if att["error"]:
                print(f"    {name:<18} ERROR {att['error']}")
                continue
            s = att["score"]
            print(f"    {name:<18} {s['n']:>3} rows  {s['dated']:>3} dated  "
                  f"{s['own_url']:>3} deep-links  {s['desc']:>3} desc  "
                  f"{s['tags']:>3} tags  useful={s['useful']}"
                  + (f"  e.g. {att['sample']}" if att["sample"] else ""))
        print()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2, default=str))
    print(f"wrote {args.out}")

    failed = [r["id"] for r in results if not r["agrees"]]
    if failed:
        print(f"probe disagreed with fetch on: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
