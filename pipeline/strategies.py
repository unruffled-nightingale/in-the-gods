"""Stage-1 listing extractors, keyed by the `strategy` field in venues.yaml.

Families, not venues. A new venue should pick one of these and put its
parameters in yaml — not grow a new class.

The `credits` selector is the card's who-made-it line. It is not the byline:
the byline is the opening of the show copy, split out in fetch.finalise_copy.

Two selector keys narrow a listing rather than read a field. `space_allow`
keeps only the cards whose space matches one of its values, for houses that
advertise transfers and screenings next to their own rooms. `exclude` drops
cards whose title or url contains one of its values, for touring companies
whose site lists every city they play.
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup


def extract(venue, use_cache=True):
    """Dispatch to the venue's strategy. Unknown names raise."""
    name = resolve_strategy(venue)
    try:
        fn = STRATEGIES[name]
    except KeyError as e:
        raise SystemExit(f"unknown strategy {name!r} on {venue.get('id')}") from e
    return fn(venue, use_cache)


def resolve_strategy(venue) -> str:
    if venue.get("strategy"):
        return venue["strategy"]
    if venue.get("fetch_method") == "js_rendered":
        return "skip"
    if not venue.get("whats_on_url"):
        return "skip"
    return "auto"


def extract_skip(venue, use_cache=True):
    return []


def extract_auto(venue, use_cache=True):
    """JSON-LD if the listings page has Event objects, else CSS selectors."""
    rows = extract_jsonld(venue, use_cache)
    if rows:
        return rows
    return extract_selectors(venue, use_cache)


def extract_jsonld(venue, use_cache=True):
    from fetch import jsonld_events, polite_get, parse_date_range

    url = venue["whats_on_url"]
    soup = BeautifulSoup(polite_get(url, use_cache), "html.parser")
    rows = []
    for e in jsonld_events(soup):
        start = (e.get("startDate") or "")[:10] or None
        end = (e.get("endDate") or e.get("startDate") or "")[:10] or None
        if not start:
            start, end = parse_date_range(
                " ".join(filter(None, [e.get("startDate"), e.get("endDate")]))
            )
        rows.append({
            "title": e.get("name"),
            "url": e.get("url") or url,
            "first_date": start,
            "last_date": end,
            "description": e.get("description"),
            "source": "jsonld",
        })
    return [r for r in rows if r["title"]]


def extract_dated_clusters(venue, use_cache=True):
    """Pair each dated scrap of text with the nearest heading and link.

    Wix and a few other builders position every show as its own absolutely
    placed box, so there is no repeating card class that survives a republish.
    The date, the title and the show-page link *are* in the same small
    subtree — walk up from the date until that subtree appears.
    """
    from fetch import polite_get, parse_date_range

    url = venue["whats_on_url"]
    soup = BeautifulSoup(polite_get(url, use_cache), "html.parser")
    rows, seen = [], set()

    for el in soup.find_all(["p", "h2", "h3", "h4", "h5", "span", "time", "div"]):
        text = el.get_text(" ", strip=True)
        if not text or len(text) > 80:
            continue
        start, end = parse_date_range(text)
        if not start:
            continue
        cluster = _smallest_show_cluster(el)
        if cluster is None:
            continue
        title, href = cluster
        key = (title.lower(), start)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "title": title,
            "url": urljoin(url, href) if href else url,
            "first_date": start,
            "last_date": end,
            "description": None,
            "source": "dated_clusters",
        })
    return rows


_TIME_ONLY = re.compile(
    r"^\d{1,2}(?:[.:]\d{2})?\s*(?:am|pm)"
    r"(?:\s*[&+,]\s*\d{1,2}(?:[.:]\d{2})?\s*(?:am|pm))*$",
    re.I,
)
_NOT_TITLE = re.compile(
    r"^(book now|tickets?|more info|read more|buy now|dates?|until|"
    r"what'?s on|upcoming|your visit|about us|buy tickets|"
    r"(?:spring|summer|autumn|winter|fall)\s+20\d{2})$",
    re.I,
)


def _looks_like_title(text):
    from fetch import parse_date_range
    t = (text or "").strip()
    if len(t) < 3 or len(t) > 120:
        return False
    if parse_date_range(t)[0]:
        return False
    if _TIME_ONLY.match(t) or _NOT_TITLE.match(t):
        return False
    return True


def _slugish(text):
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _best_href(hrefs, title):
    """Prefer a link whose last path segment looks like the title.

    Walking up from a Wix date often lands in a parent that already
    contains the previous show's link; taking hrefs[0] then attaches
    Iceberg Right Ahead to We'll Always Have Paris.
    """
    needle = _slugish(title)
    if len(needle) >= 6:
        for href in hrefs:
            slug = _slugish(href.rstrip("/").rsplit("/", 1)[-1])
            if len(slug) >= 6 and (needle[:8] in slug or slug[:8] in needle):
                return href
    return hrefs[0]


def _smallest_show_cluster(date_el):
    """Pair a dated node with the heading before it and that heading's link.

    Walk up from the title, not the date: Wix date widgets sit in a
    shared calendar that already contains every other show's href.
    """
    title = None
    title_el = None
    if hasattr(date_el, "find_all"):
        for h in date_el.find_all(["h1", "h2", "h3", "h4", "h5"]):
            text = h.get_text(" ", strip=True)
            if _looks_like_title(text):
                title_el = h
                title = text
                break
    if title_el is None:
        for prev in date_el.previous_elements:
            name = getattr(prev, "name", None)
            if name in ("h1", "h2", "h3", "h4", "h5"):
                text = prev.get_text(" ", strip=True)
                if _looks_like_title(text):
                    title = text
                    title_el = prev
                    break
            if name in ("body", "html"):
                break
    if not title_el:
        return None
    node = title_el
    for _ in range(8):
        node = node.parent
        if node is None or node.name in ("body", "html"):
            return None
        hrefs = []
        for a in node.find_all("a", href=True):
            href = a.get("href") or ""
            if href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            hrefs.append(href)
        if hrefs:
            return title, _best_href(hrefs, title)
    return None


def extract_selectors(venue, use_cache=True):
    from fetch import polite_get, parse_date_range

    url = venue["whats_on_url"]
    soup = BeautifulSoup(polite_get(url, use_cache), "html.parser")
    sel = venue.get("selectors") or {}
    card_sel = sel.get("show_card")
    if not card_sel:
        return []

    allow = [a.lower() for a in (sel.get("space_allow") or [])]
    exclude = [x.lower() for x in (sel.get("exclude") or [])]

    rows = []
    for card in soup.select(card_sel):
        title = _pick_text(card, sel.get("title"))
        if not title:
            continue
        space = _pick_text(card, sel.get("space"))
        if venue.get("require_space") and not space:
            continue
        # a multi-space house lists its own auditoria alongside transfers,
        # tours, cinema screenings and streaming. Keep only its own rooms.
        if allow and not any(a in (space or "").lower() for a in allow):
            continue

        href = _pick_href(card, sel.get("link"), url)
        # touring companies list every city they play; drop the ones abroad
        if exclude:
            blob = f"{title} {href or ''}".lower()
            if any(x in blob for x in exclude):
                continue
        if sel.get("title_cut_dates"):
            title = re.split(r"\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b", title, maxsplit=1)[0].strip()
        date_text = (_pick_text(card, sel.get("dates"))
                     if sel.get("dates") else card.get_text(" ", strip=True))
        start, end = parse_date_range(date_text)
        rows.append({
            "title": title,
            "credits": _pick_text(card, sel.get("credits") or sel.get("byline")),
            "space": space,
            "first_date": start,
            "last_date": end,
            "url": href or url,
            "description": _pick_blurb(card, sel),
            "venue_tags": _pick_tags(card, sel),
            "source": "selectors",
        })
    return rows


def extract_wp_rest(venue, use_cache=True):
    """WordPress REST collection (e.g. /wp-json/wp/v2/productions).

    Useful when the CPT is public. Performance dates are often *not* in the
    collection — those still need stage 2 or selectors.
    """
    from fetch import polite_get, parse_date_range

    cfg = venue.get("wp_rest") or {}
    endpoint = cfg.get("endpoint")
    if not endpoint:
        return []
    per_page = int(cfg.get("per_page") or 50)
    url = f"{endpoint}{'&' if '?' in endpoint else '?'}per_page={per_page}"
    data = json.loads(polite_get(url, use_cache))
    if not isinstance(data, list):
        return []

    rows = []
    for item in data:
        title = _wp_rendered(item.get("title")) or item.get("production_title")
        if not title:
            continue
        start, end = parse_date_range(item.get(cfg.get("dates_field") or "") or "")
        rows.append({
            "title": title,
            "credits": _wp_rendered(item.get("producer")) or item.get("producer"),
            "space": None,
            "first_date": start,
            "last_date": end,
            "url": item.get("link") or venue.get("whats_on_url"),
            "description": _strip_html(_wp_rendered(item.get("excerpt"))),
            "source": "wp_rest",
        })
    return rows


def extract_sanity(venue, use_cache=True):
    """GROQ query against a public Sanity dataset. Used by The Yard."""
    from fetch import polite_get

    cfg = venue.get("sanity") or {}
    project = cfg.get("project_id")
    dataset = cfg.get("dataset") or "production"
    api_ver = cfg.get("api_version") or "2021-10-21"
    query = cfg.get("query") or (
        '*[_type=="event" && defined(duration.end) && duration.end >= now()]'
        '| order(duration.start asc){title, description, duration, "slug": slug.current}'
    )
    if not project:
        return []

    api = (f"https://{project}.api.sanity.io/v{api_ver}/data/query/{dataset}"
           f"?query={quote(query)}")
    payload = json.loads(polite_get(api, use_cache))
    result = payload.get("result") or []

    pattern = venue.get("show_url_pattern") or (venue.get("whats_on_url", "").rstrip("/") + "/{slug}")
    rows = []
    for item in result:
        slug = item.get("slug")
        duration = item.get("duration") or {}
        start = _iso_day(duration.get("start"))
        end = _iso_day(duration.get("end")) or start
        url = pattern.replace("{slug}", slug) if slug else venue.get("whats_on_url")
        # Sanity `description` is usually an SEO stub ("Title at The Yard Theatre").
        # Leave it empty so stage 2 can pull og:description from the show page.
        desc = item.get("description") or ""
        if desc.lower().rstrip(" .").endswith("theatre") and len(desc) < 120:
            desc = None
        rows.append({
            "title": item.get("title"),
            "url": url,
            "first_date": start,
            "last_date": end,
            "description": desc or None,
            "source": "sanity",
        })
    return [r for r in rows if r["title"]]


def _pick_text(card, selector):
    if not selector:
        return None
    el = card.select_one(selector)
    if not el:
        return None
    text = el.get_text(" ", strip=True)
    if not text and el.name == "img":
        text = (el.get("alt") or "").strip()
    return text or None


def _pick_href(card, selector, base):
    import re
    a = card.select_one(selector) if selector else None
    if a is None and card.name == "a" and card.get("href"):
        a = card
    if a is None:
        a = card.find("a", href=True)
    href = a.get("href") if a is not None else None
    if href and href.startswith("#"):
        href = None
    if not href:
        blob = " ".join(f"{k}={v}" for k, v in card.attrs.items())
        m = re.search(r"goToUrl\('([^']+)'", blob)
        href = m.group(1) if m else None
    if not href:
        return None
    return urljoin(base, href)


def _pick_blurb(card, sel):
    raw = _pick_text(card, sel.get("blurb"))
    if not raw:
        return None
    strip_sel = sel.get("blurb_strip")
    if strip_sel:
        el = card.select_one(sel["blurb"])
        if el:
            clone = BeautifulSoup(str(el), "html.parser")
            for drop in clone.select(strip_sel):
                drop.decompose()
            raw = clone.get_text(" ", strip=True)
    return raw or None


def _pick_tags(card, sel):
    tag_sel = sel.get("tags")
    if not tag_sel:
        return []
    out = []
    for a in card.select(tag_sel):
        t = a.get_text(strip=True)
        if t and t not in out:
            out.append(t)
    return out


def _wp_rendered(value):
    if isinstance(value, dict):
        return value.get("rendered")
    return value


def _strip_html(html):
    if not html:
        return None
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True) or None


def _iso_day(value):
    if not value:
        return None
    return str(value)[:10]


def extract_immersive_rumours(venue, use_cache=True):
    """Parse immersiverumours.com/current-shows-london.

    Wix puts each show in its own column-strip: an h2, the copy, then 📍 / 🕒
    / 🎟️ lines. Section h6s split London, at-home, and outside-London. At-home
    (and WhatsApp) rows are tagged venue_id=home so In the Gods shows HOME.
    """
    from datetime import date, timedelta
    from fetch import polite_get, parse_date_range

    url = venue["whats_on_url"]
    soup = BeautifulSoup(polite_get(url, use_cache), "html.parser")
    today = date.today()
    section = "london"
    rows = []

    for el in soup.find_all(["h2", "h6"]):
        heading = el.get_text(" ", strip=True)
        if not heading:
            continue
        if el.name == "h6":
            low = heading.lower()
            if "at home" in low:
                section = "home"
            elif "outside of london" in low:
                section = "outside"
            elif any(k in low for k in (
                "immersive/interactive", "dining", "cocktail",
                "vr and", "coming soon",
            )):
                section = "london"
            continue
        if section == "outside":
            continue

        block = el
        for _ in range(10):
            if block is None:
                break
            cls = " ".join(block.get("class") or [])
            if block.name == "section" and "column-strip" in cls:
                break
            block = block.parent
        if block is None:
            continue
        blob = block.get_text("\n", strip=True)

        loc = None
        m = re.search(r"📍\s*(.+)", blob)
        if m:
            loc = m.group(1).strip().split("\n")[0].strip()
        date_text = ""
        m = re.search(r"🕒\s*(.+)", blob)
        if m:
            date_text = m.group(1).strip().split("\n")[0].strip()

        href = None
        for a in block.find_all("a", href=True):
            h = a["href"]
            if (h.startswith("http") and "immersiverumours.com" not in h
                    and "wix.com" not in h):
                href = h
                break

        start, end = parse_date_range(date_text)
        if re.search(r"\bongoing\b", date_text, re.I):
            start = today.isoformat()
            end = (today + timedelta(days=400)).isoformat()
        elif re.search(r"late summer", date_text, re.I):
            yrs = re.findall(r"20\d{2}", date_text)
            yr = int(yrs[0]) if yrs else today.year
            start, end = f"{yr}-08-01", f"{yr}-09-30"
        elif (re.search(r"\bfrom\b", date_text, re.I) and start
              and start == end):
            end = (date.fromisoformat(start) + timedelta(days=400)).isoformat()

        loc_l = (loc or "").lower()
        at_home = (section == "home"
                   or loc_l in {"at home", "whatsapp", "online"})

        paras = []
        for line in blob.split("\n"):
            line = line.strip()
            if not line or line == heading:
                continue
            if line.startswith(("📍", "💰", "🕒", "🎟️", "★")):
                continue
            if re.match(r"(click to read|save \d|interview:|jump to)", line, re.I):
                continue
            paras.append(line)
        desc = "\n\n".join(paras[:5]) or None

        row = {
            "title": heading,
            "url": href or url,
            "first_date": start,
            "last_date": end,
            "description": desc,
            "venue_tags": ["immersive"],
            "source": "immersive_rumours",
        }
        if at_home:
            row["venue_id"] = "home"
        rows.append(row)
    return [r for r in rows if r["title"]]


STRATEGIES = {
    "auto": extract_auto,
    "skip": extract_skip,
    "jsonld": extract_jsonld,
    "selectors": extract_selectors,
    "dated_clusters": extract_dated_clusters,
    "wp_rest": extract_wp_rest,
    "sanity": extract_sanity,
    "immersive_rumours": extract_immersive_rumours,
}
