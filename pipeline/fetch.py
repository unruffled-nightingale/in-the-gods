#!/usr/bin/env python3
"""
fetch.py — two-stage crawler for In the Gods.

  Stage 1  listings page  -> title, byline, dates, show URL
  Stage 2  show page      -> a few paragraphs of synopsis (description)

Hop to the show page whenever the listing card has no real synopsis.
A one-line card stub is not enough; og:description is a fallback only.

Usage:
    python3 fetch.py venues.yaml --weeks 8
    python3 fetch.py venues.yaml --no-cache --venue arcola
"""

import argparse
import hashlib
import html
import json
import re
import sys
import time
from contextvars import ContextVar
import calendar
from datetime import date, timedelta
from pathlib import Path
import requests
import yaml
from bs4 import BeautifulSoup

# Kinsta and friends 403 any UA advertising a browser this far out of date,
# so this needs bumping when it drifts. Two-part versions look fake: real
# Chrome sends four.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9"}
CACHE = Path(".cache/http")   # matches the actions/cache path in fetch.yml
DELAY = 1.5          # seconds between requests to the same host
TIMEOUT = 25

# A listing page that never expires will happily replay a dead venue's shows
# for weeks, so those are refetched every run. Show pages are written once and
# rarely touched again, which is where the cache actually earns its keep.
LISTING_MAX_AGE = 12 * 3600
DETAIL_MAX_AGE = 30 * 86400


# --------------------------------------------------------------------------- #
# fetching                                                                     #
# --------------------------------------------------------------------------- #

_last_hit = {}
# When set, polite_get drives Chromium instead of requests. fetch.run sets
# this for any venue whose listings never appear in the raw HTML.
_render_opts = ContextVar("render_opts", default=None)


def render_for(venue):
    """Context manager: every polite_get inside this venue uses Chromium."""
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        want = (venue.get("fetch_method") in ("rendered", "js_rendered")
                or venue.get("render"))
        token = _render_opts.set(
            {"wait_for": venue.get("render_wait")} if want else None
        )
        try:
            yield
        finally:
            _render_opts.reset(token)
    return _cm()


def polite_get(url, use_cache=True, render=None, max_age=DETAIL_MAX_AGE):
    """GET with on-disk cache and per-host rate limiting.

    `render=True` (or a venue inside render_for()) fetches the page through
    Chromium so JavaScript-built listings actually exist in the HTML. The
    cache key is different, so an empty shell from a plain GET cannot be
    reused as a rendered page.

    `max_age` is how many seconds a cached copy stays usable.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    opts = _render_opts.get()
    do_render = bool(opts) if render is None else render
    suffix = ".rendered.html" if do_render else ".html"
    key = CACHE / (hashlib.sha1(url.encode()).hexdigest() + suffix)
    if use_cache and key.exists() and time.time() - key.stat().st_mtime < max_age:
        return key.read_text(encoding="utf-8", errors="replace")

    host = requests.utils.urlparse(url).netloc
    gap = time.time() - _last_hit.get(host, 0)
    delay = 3.0 if do_render else DELAY
    if gap < delay:
        time.sleep(delay - gap)
    _last_hit[host] = time.time()

    if do_render:
        from browser import rendered_get
        wait_for = (opts or {}).get("wait_for") if render is None else None
        text = rendered_get(url, wait_for=wait_for)
    else:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        text = r.text
    key.write_text(text, encoding="utf-8")
    return text


# --------------------------------------------------------------------------- #
# parsing helpers                                                              #
# --------------------------------------------------------------------------- #

MONTHS = ("jan feb mar apr may jun jul aug sep oct nov dec".split())
MONTH_RE = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*"
PRICE_RE = re.compile(r"£\s?(\d+(?:\.\d{2})?)")


def parse_date_range(text, default_year=None):
    """
    Handle the formats venues actually use:
      '11 Sep - 10 Oct 2026'   '2 - 5 Sep 2026'   '6 Oct'
      'Wed 9 September to Sat 3 October'
      'Thurs 8 - Sat 17 Oct at 7:15pm'
    Returns (start_iso, end_iso) or (None, None).
    """
    if not text:
        return None, None
    year = default_year or date.today().year
    years = re.findall(r"\b(20\d{2})\b", text)
    start_year = end_year = year
    if years:
        # anchor the start on the FIRST year. When the text names a second
        # year ('10 Feb 2025 - 1 Jan 2027') the end belongs to that one;
        # otherwise the end-before-start rule below rolls it forward.
        start_year = int(years[0])
        end_year = int(years[-1])

    # strip weekday names, times and 4-digit years — all of which produce
    # spurious day numbers ('2026' reads as day 20 then day 26)
    t = re.sub(r"\b20\d{2}\b", " ", text)
    # '25th - 27th September' — ordinals hide the day from the month pairing
    t = re.sub(r"(\d{1,2})(?:st|nd|rd|th)\b", r"\1", t, flags=re.I)
    # 'Sept. 9' — Django's date filter abbreviates with a full stop, which
    # otherwise reads as the end of a sentence
    t = re.sub(r"\b(%s)[a-z]*\.\s*" % "|".join(MONTHS), r"\1 ", t, flags=re.I)
    t = re.sub(r"\b(Mon|Tue|Tues|Wed|Weds|Thu|Thur|Thurs|Fri|Sat|Sun)[a-z]*\b",
               " ", t, flags=re.I)
    t = re.sub(r"\bat\b.*$", "", t, flags=re.I)
    t = re.sub(r"\d{1,2}[:.]\d{2}\s*(?:am|pm)?", " ", t, flags=re.I)
    t = re.sub(r"\b\d{1,2}\s*(?:am|pm)\b", " ", t, flags=re.I)

    hits = re.findall(rf"(\d{{1,2}})\s*({MONTH_RE})?", t, flags=re.I)
    parts = [(int(d), m) for d, m in hits if d and 1 <= int(d) <= 31]
    months = [m for _, m in parts if m]
    # 'September 25, 2026' / 'Fri September 25' — month before the day
    if not months:
        hits2 = re.findall(rf"({MONTH_RE})\s+(\d{{1,2}})", t, flags=re.I)
        parts = [(int(d), m) for m, d in hits2 if d and 1 <= int(d) <= 31]
        months = [m for _, m in parts if m]
    if not parts:
        return _parse_month_only(text, year)
    if not months:
        return None, None

    def to_iso(day, mon, yr):
        mi = MONTHS.index(mon.lower()[:3]) + 1
        return date(yr, mi, day).isoformat()

    # forward-fill a missing month from the next one that has it ('2 - 5 Sep')
    filled, last = [], months[-1]
    for d, m in parts:
        filled.append((d, m or last))
    try:
        start = to_iso(*filled[0], start_year)
        end = to_iso(*filled[-1], end_year)
    except (ValueError, IndexError):
        return None, None
    # '16 Oct - 21 Nov' spanning a year boundary. Only roll forward when the
    # text did not name the closing year itself.
    if end < start and start_year == end_year:
        end = date(end_year + 1, MONTHS.index(filled[-1][1].lower()[:3]) + 1,
                   filled[-1][0]).isoformat()
    # 'Until 24 Oct' / 'Until Sat 3 Oct' — listings name the close, not the
    # opening. Treat today as the start so a currently-running show stays
    # in the window instead of collapsing to a one-night on closing night.
    if re.search(r"\buntil\b", text, flags=re.I):
        today_iso = date.today().isoformat()
        start = today_iso if today_iso <= end else end
    return start, end


def _month_end(mon, yr):
    mi = MONTHS.index(mon.lower()[:3]) + 1
    return date(yr, mi, calendar.monthrange(yr, mi)[1])


def _parse_month_only(text, default_year):
    """'Until February 2027' / 'March 2028' — a month named, no day.

    Troubadour writes 'Now booking until February 2027' for an open run.
    ENO writes 'June 2027' for a month that is not yet on sale. Guessing a
    Thursday from 'Every Thursday' is still forbidden; that has no month.
    """
    m = re.search(rf"\buntil\s+({MONTH_RE})(?:\s+(20\d{{2}}))?", text, flags=re.I)
    if m:
        mon = m.group(1)
        yr = int(m.group(2)) if m.group(2) else default_year
        end = _month_end(mon, yr).isoformat()
        today_iso = date.today().isoformat()
        start = today_iso if today_iso <= end else end
        return start, end
    m = re.search(rf"\b({MONTH_RE})\s+(20\d{{2}})\b", text, flags=re.I)
    if m:
        mon, yr = m.group(1), int(m.group(2))
        mi = MONTHS.index(mon.lower()[:3]) + 1
        start = date(yr, mi, 1).isoformat()
        end = _month_end(mon, yr).isoformat()
        return start, end
    return None, None


def jsonld_events(soup):
    """Pull schema.org Event objects out of JSON-LD, if present."""
    out = []
    for blk in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads((blk.string or "").strip())
        except (json.JSONDecodeError, AttributeError):
            continue
        stack = [data]
        while stack:
            n = stack.pop()
            if isinstance(n, list):
                stack.extend(n)
            elif isinstance(n, dict):
                t = n.get("@type", "")
                if "Event" in str(t):
                    out.append(n)
                stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
    return out


def meta(soup, *names):
    for n in names:
        el = (soup.find("meta", property=n) or soup.find("meta", attrs={"name": n}))
        if el and el.get("content"):
            return el["content"].strip()
    return None


# --------------------------------------------------------------------------- #
# synopsis / byline                                                            #
# --------------------------------------------------------------------------- #

SYNOPSIS_MIN_CHARS = 280
BYLINE_MAX = 240

# Paragraphs that are not the show: booking, access, venue and site chrome.
_CHROME = re.compile(
    r"cookie|book (?:now|tickets|your tickets)|buy tickets|add to (?:calendar|basket|cart)|"
    r"newsletter|subscribe|privacy policy|terms and conditions|sign up|"
    r"follow us|share this|click here|"
    r"running time|age guidance|content warning|strong language|"
    r"ticket prices?|the performance lasts|including (?:one |an )?interval|"
    r"this production contains|surtitles|strobe effects|"
    r"flashing lights|access performances|bsl interpreted|audio described|"
    r"relaxed (?:environment|performance)|captioned|wheelchair|"
    r"limited number of tickets|priority booking|multibuy|members? offer|"
    r"% off|sold[-\s]?out|£\d|videography|did you know we are a charity|"
    r"3d tour|access for all|join club|recoup the cost|"
    r"access requirements|please contact|please email|call 020|"
    # account and booking modals that sit on every page of a house's site
    r"log ?in to|sign in to|e-tickets|email preferences|check out faster|"
    r"check (?:online|back) (?:regularly )?for returns|join the waiting list|"
    r"latecomers|readmittance|please note|"
    # the access-and-contact statement most houses repeat on every show page
    r"committed to ensuring|if you have any (?:questions|enquiries)|"
    r"get in touch by phone|\[email protected\]|"
    # 'General sale opens at 12pm on Wednesday 16 September.'
    r"general sale|goes on sale|on sale (?:now|from)|presale|"
    r"mailing list|under 18s? are not permitted|"
    r"this production has closed|concessions are offered|"
    r"no dates scheduled|was last on \d|"
    r"charitable company limited by guarantee|charity registered",
    re.I,
)
_ROLES = ("written|adapted|devised|directed|choreographed|designed|"
          "presented|produced|created|composed")
_CREDIT_LEAD = re.compile(
    r"^(?:(?:book|music|lyrics|text|words|choreography)\s+)?"
    r"(?:%s)?\s*by:?\s+" % _ROLES, re.I)
# words that can sit between names without making the line prose
_CREDIT_GLUE = frozenset(
    ("and", "with", "the", "of", "by", "by:", "from", "&")
    + tuple(_ROLES.split("|")) + ("book", "music", "lyrics", "text", "words"))


def _is_credit_sentence(sentence):
    lead = _CREDIT_LEAD.match(sentence)
    if not lead:
        return False
    rest = sentence[lead.end():].strip().rstrip(".!?")
    names = 0
    for token in re.split(r"[\s,]+", rest):
        if not token or token.lower().rstrip(":") in _CREDIT_GLUE:
            continue
        # 'By Tuesday the whole street knew' — prose gives itself away with a
        # lowercase word that is not joining two names together
        if not token[0].isupper():
            return False
        names += 1
    return 1 <= names <= 6


def is_credits(text, limit=200):
    """True for a paragraph that is nothing but production credits."""
    t = str(text or "").strip()
    if not t or len(t) > limit:
        return False
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]
    return bool(sentences) and all(_is_credit_sentence(s) for s in sentences)


# 'Webber & Co. with Metal Rabbit ... presents' — the producer, not the story.
_PRESENTS_TAIL = re.compile(r"\bpresents?\s*:?\s*$", re.I)
_PRESENTS_LEAD = re.compile(r"^.{0,140}?\bpresents?\s*:?\s+", re.I)
# Review pull-quotes and star ratings.
_QUOTE_LEAD = re.compile(r"^\s*(?:[\u2b50\u2605\u2606]|[\u201c\u201e\"'\u2018])")
_QUOTE_TAIL = re.compile(r"[\u201d\"']\s*[-\u2013\u2014]?\s*[A-Z][\w' ]{2,40}\.?$")
_STARS = re.compile(r"[\u2b50\u2605\u2606]{2,}")
# 'Until 24 Oct Holloway Theatre' — dates and room names off the listing card.
_WHEN_STUB = re.compile(r"^\s*(?:until|from|opens?)\s+\d{1,2}\s+\w{3}", re.I)
# Houses like to open on a line of dialogue. It grabs, but it says nothing
# about the show, so it is not the byline.
_FIRST_PERSON = re.compile(r"^\s*(?:I|I'm|I\u2019m|I've|I\u2019ve|We|We're|My)\b")


def is_chrome(text):
    """True for paragraphs that describe the booking, not the show."""
    t = " ".join(str(text or "").split())
    if not t:
        return True
    if _WHEN_STUB.match(t):
        return True
    if _PRESENTS_TAIL.search(t):
        return True
    if _QUOTE_LEAD.match(t) or _QUOTE_TAIL.search(t) or _STARS.search(t):
        return True
    if t.isupper() and len(t) < 160:
        return True
    return bool(_CHROME.search(t))


def is_epigraph(text, limit=170):
    """A short scrap of dialogue standing in front of the real copy."""
    t = " ".join(str(text or "").split())
    if not t or len(t) > limit:
        return False
    return bool(_FIRST_PERSON.match(t)) or t[-1] not in ".?!"


def _echoes_title(text, title):
    """The listing repeating its own headline ('X + Y At Rich Mix')."""
    if not title:
        return False
    t = " ".join(str(text).split())
    name = " ".join(str(title).split())
    if len(t) > 140 or len(name) < 8:
        return False
    return name.lower() in t.lower() and len(name) / len(t) > 0.5


def clean_text(value):
    """Collapse whitespace and undo the entities some feeds double-escape."""
    t = html.unescape(str(value or ""))
    if "&" in t:
        t = html.unescape(t)
    # feeds sometimes run sentences together: 'family!Join Deaf Rave for...'
    t = re.sub(r"(?<=[.!?])(?=[A-Z\u201c])", " ", t)
    return " ".join(t.split())


def _clean_para(el):
    return clean_text(el.get_text(" ", strip=True))


def _is_quote_markup(p):
    """Houses set epigraphs and pull-quotes in italics or a blockquote."""
    if p.find_parent("blockquote"):
        return True
    kids = [c for c in p.children if getattr(c, "name", None) or str(c).strip()]
    return len(kids) == 1 and getattr(kids[0], "name", None) in ("em", "i")


def synopsis_paragraphs(paras, max_paras=3, title=None):
    """Keep the paragraphs that actually describe the show."""
    kept = []
    for t in paras:
        t = clean_text(t)
        if (len(t) < 50 or is_chrome(t) or is_credits(t)
                or _echoes_title(t, title)):
            continue
        # some houses glue 'X presents TITLE' onto the opening sentence
        t = _PRESENTS_LEAD.sub("", t, count=1).strip()
        if kept and t == kept[-1]:
            continue
        kept.append(t)
        if len(kept) >= max_paras + 1:
            break

    # drop a leading line of dialogue, but only if real copy follows it
    if len(kept) > 1 and is_epigraph(kept[0]):
        kept = kept[1:]
    return kept[:max_paras]


def is_full_synopsis(text):
    """True when the text already looks like a few paragraphs of copy."""
    if not text:
        return False
    if "hellip" in str(text).lower() or str(text).rstrip().endswith("\u2026"):
        return False
    paras = [p.strip() for p in re.split(r"\n\s*\n", str(text).strip())
             if len(p.strip()) >= 40]
    if len(paras) >= 2:
        return True
    return len(text) >= SYNOPSIS_MIN_CHARS


_SYNOPSIS_HEADING = re.compile(
    r"^(?:synopsis|about the (?:show|production)|the story|the plot)$",
    re.I,
)


def _synopsis_heading(root):
    """Opera houses tuck the plot under a Synopsis heading, below the fold."""
    for h in root.find_all(["h2", "h3", "h4"]):
        label = " ".join(h.get_text(" ", strip=True).split())
        if _SYNOPSIS_HEADING.match(label):
            return h
    return None


def _p_tags(root, after=None):
    if after is None:
        return root.find_all("p")
    seen = False
    out = []
    for el in root.descendants:
        if el is after:
            seen = True
            continue
        if seen and getattr(el, "name", None) == "p":
            out.append(el)
    return out


def _kept_from_p(found, max_paras, title):
    # The Drayton Arms nests its paragraphs, so the outer one reads as the
    # whole page glued together — 'By William Shakespeare Viola is washed
    # ashore...'. The children carry the same text, properly separated. St
    # Bride's nests differently and keeps only furniture in the leaves, so
    # fall back rather than lose the copy.
    leaves = [p for p in found if not p.find("p")]
    paras = [(_clean_para(p), _is_quote_markup(p)) for p in leaves]
    if not synopsis_paragraphs([t for t, _ in paras], max_paras, title):
        paras = [(_clean_para(p), _is_quote_markup(p)) for p in found]
    prose = [t for t, quoted in paras if not quoted]
    return (synopsis_paragraphs(prose, max_paras, title)
            or synopsis_paragraphs([t for t, _ in paras], max_paras, title))


def synopsis_from_soup(soup, max_paras=3, title=None):
    """A few body paragraphs of show copy, booking chrome dropped."""
    root = soup.select_one("article, main, [role='main'], .entry-content")
    # Camden People's Theatre wraps the page in an <article> that holds no
    # paragraphs at all — the copy sits outside it. Scoping to a semantic
    # root is only worth it if the root actually has the prose in it.
    if root is None or not root.find_all("p"):
        root = soup
    heading = _synopsis_heading(root)
    found = _p_tags(root, heading)
    kept = _kept_from_p(found, max_paras, title) if found else None
    # empty under the heading (or all chrome) — walk the whole page instead
    if not kept and heading:
        kept = _kept_from_p(root.find_all("p"), max_paras, title)
    if kept:
        return "\n\n".join(kept)
    # TicketSolve's editor pastes copy as <font> inside a div, with no <p>
    # at all. Hauntings at OSO was in the DOM and still came back empty.
    fonts = [f for f in root.find_all("font") if not f.find("font")]
    if fonts:
        kept = synopsis_paragraphs(
            [_clean_para(f) for f in fonts], max_paras, title
        )
        if kept:
            return "\n\n".join(kept)
    return None


def pick_description(*candidates):
    """Prefer a multi-paragraph synopsis over a short meta stub."""
    viable = [c.strip() for c in candidates if c and str(c).strip()]
    if not viable:
        return None
    full = [c for c in viable if is_full_synopsis(c)]
    pool = full or viable
    return max(pool, key=len)


def og_for_show(og, title):
    """Drop a site-wide meta description that is not about this show.

    ICA puts the house bio in og:description on every page. That text is
    longer than a listing blurb, so apply_stage2 would replace the real
    card copy with 'London's leading space for contemporary culture'.
    """
    if not og:
        return None
    t = (title or "").strip()
    if len(t) >= 8 and t.lower() not in og.lower():
        return None
    return og


_SENTENCE_END = re.compile(r"(?<=[.!?\u2026])\s+")


def split_hook(text, limit=BYLINE_MAX):
    """Split show copy into (byline, description).

    The byline is the grab: the opening sentence or two, enough to decide
    whether to click. The description is everything after it.
    """
    if not text:
        return None, None
    paras = [p.strip() for p in re.split(r"\n\s*\n", str(text).strip()) if p.strip()]
    if not paras:
        return None, None

    first, rest = paras[0], paras[1:]
    if len(first) <= limit:
        return first, ("\n\n".join(rest) or None)

    hook = ""
    for sentence in _SENTENCE_END.split(first):
        candidate = f"{hook} {sentence}".strip()
        if hook and len(candidate) > limit:
            break
        hook = candidate
        if len(hook) >= 80:
            break
    tail = first[len(hook):].strip()
    if len(hook) > limit:
        # one very long sentence: cut a teaser, keep the paragraph intact
        hook, tail = _cut_clause(first, limit), first
    return hook, ("\n\n".join(([tail] if tail else []) + rest) or None)


def _cut_clause(text, limit):
    cut = text[:limit]
    for sep in ("; ", " \u2013 ", " \u2014 ", ", "):
        i = cut.rfind(sep)
        if i > limit // 3:
            return cut[:i].rstrip(",;: ") + "\u2026"
    return cut.rsplit(" ", 1)[0].rstrip(",;: ") + "\u2026"


# --------------------------------------------------------------------------- #
# stage 1 — listings (strategy dispatch)                                       #
# --------------------------------------------------------------------------- #

def stage1(venue, use_cache=True):
    """Return list of dicts with at minimum {title, url}; dates where available."""
    from strategies import extract
    return extract(venue, use_cache)


# --------------------------------------------------------------------------- #
# stage 2 — per-show detail                                                    #
# --------------------------------------------------------------------------- #

# The Barbican runs installations for the better part of two years, so this
# has to be generous. Finborough's permanently-open online archive pages
# carry JSON-LD end dates of 2028 and 2050.
MAX_RUN_DAYS = 3 * 365


def plausible_run(start, end):
    """False for a span no theatre programme could mean literally."""
    if not start or not end:
        return True
    try:
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
    except ValueError:
        return False
    return 0 <= (e - s).days <= MAX_RUN_DAYS


def detail_dates(soup, selector):
    """Read a run of dates off a show page.

    Some houses (Barbican) publish no dates on the listing at all. Prefer a
    machine-readable `datetime` attribute over the printed text, which tends
    to carry weekday names and stray punctuation.
    """
    if not selector:
        return None, None
    el = soup.select_one(selector)
    if el is None:
        return None, None
    stamps = [t["datetime"][:10] for t in el.select("[datetime]")
              if t.get("datetime")]
    if el.get("datetime"):
        stamps.insert(0, el["datetime"][:10])
    stamps = [s for s in stamps if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s)]
    if stamps:
        return stamps[0], stamps[-1]
    return parse_date_range(el.get_text(" ", strip=True))


# Theatre503 cuts card titles at a fixed width: 'Advanced Playwriting with...'
_TRUNCATED = re.compile(r"(?:\u2026|\.\.\.)\s*$")


def is_truncated(title):
    return bool(_TRUNCATED.search(str(title or "")))


def full_title(soup):
    """The show page's own title, for listings that cut theirs short."""
    for value in (meta(soup, "og:title", "twitter:title"),
                  soup.h1.get_text(" ", strip=True) if soup.h1 else None):
        t = clean_text(value)
        # 'Chewing Gum Dreams | Theatre503' — drop the site name
        t = re.split(r"\s+[|\u2013\u2014]\s+", t)[0].strip()
        if t and not is_truncated(t):
            return t
    return None


def stage2(show_url, use_cache=True, title=None, detail_sel=None):
    """Fetch a show page and pull a few paragraphs of synopsis."""
    try:
        html = polite_get(show_url, use_cache)
    except Exception as e:                                    # noqa: BLE001
        return {"detail_error": f"{type(e).__name__}: {e}"}

    soup = BeautifulSoup(html, "html.parser")
    out = {}

    jsonld_desc = None
    for e in jsonld_events(soup):
        jsonld_desc = e.get("description") or jsonld_desc
        start = (e.get("startDate") or "")[:10] or None
        end = (e.get("endDate") or "")[:10] or None
        if plausible_run(start, end):
            if start:
                out["first_date"] = start
            if end:
                out["last_date"] = end
        offers = e.get("offers")
        if isinstance(offers, dict) and offers.get("price"):
            try:
                out["price_min"] = float(offers["price"])
            except (TypeError, ValueError):
                pass
        break

    if not out.get("first_date"):
        s, e_ = detail_dates(soup, (detail_sel or {}).get("dates"))
        if s and plausible_run(s, e_):
            out["first_date"], out["last_date"] = s, e_

    out["full_title"] = full_title(soup)

    og = og_for_show(
        meta(soup, "og:description", "twitter:description", "description"),
        title,
    )
    out["description"] = pick_description(synopsis_from_soup(soup, title=title),
                                          jsonld_desc, og)

    text = soup.get_text(" ", strip=True)
    if "price_min" not in out:
        prices = [float(p) for p in PRICE_RE.findall(text)]
        if prices:
            out["price_min"] = min(prices)
            out["price_max"] = max(prices)
    return out


def apply_stage2(row, detail):
    """Fold show-page fields onto a listing row. Keep the longer synopsis."""
    incoming = detail.get("description")
    existing = row.get("description")
    if incoming and (not existing or len(incoming) > len(existing)):
        row["description"] = incoming
    # a card that cut its own title short loses to the show page's version
    recovered = detail.pop("full_title", None)
    if recovered and is_truncated(row.get("title")):
        row["title"] = recovered
    for k, v in detail.items():
        if k == "description" or v is None:
            continue
        if not row.get(k):
            row[k] = v


def _title_key(title):
    return re.sub(r"\W+", " ", str(title or "").lower()).strip()


def merge_runs(rows):
    """Collapse a venue's per-performance cards into one row per show.

    Some houses publish a card per date — the Courtyard listed Serious Money
    ten times, once per night, each with its own booking link, so the url
    de-duplication upstream could not see them as the same thing. The run is
    the union of the dates; the copy is the fullest of them.
    """
    out, index = [], {}
    for row in rows:
        key = _title_key(row.get("title"))
        keep = index.get(key)
        if keep is None:
            if key:
                index[key] = row
            out.append(row)
            continue
        starts = [d for d in (keep.get("first_date"), row.get("first_date")) if d]
        ends = [d for d in (keep.get("last_date"), row.get("last_date")) if d]
        if starts:
            keep["first_date"] = min(starts)
        if ends:
            keep["last_date"] = max(ends)
        if len(row.get("description") or "") > len(keep.get("description") or ""):
            keep["description"] = row["description"]
        lows = [p for p in (keep.get("price_min"), row.get("price_min")) if p]
        highs = [p for p in (keep.get("price_max"), row.get("price_max")) if p]
        if lows:
            keep["price_min"] = min(lows)
        if highs:
            keep["price_max"] = max(highs)
    return out


def finalise_copy(row):
    """Clean the show copy, then split its opening off as the byline."""
    paras = re.split(r"\n\s*\n", row.get("description") or "")
    kept = synopsis_paragraphs(paras, title=row.get("title"))
    if not kept:
        # nothing survived the filter — better a raw blurb than an empty card
        kept = [p.strip() for p in paras if p.strip()][:1]
    byline, description = split_hook("\n\n".join(kept))
    row["byline"], row["description"] = byline, description


# --------------------------------------------------------------------------- #
# orchestration                                                                #
# --------------------------------------------------------------------------- #

def venue_horizon(today, weeks, venue):
    """ISO end-date for this house. `lookahead_weeks` stretches one venue
    (Young Vic's autumn season) without widening the whole digest."""
    w = int(venue.get("lookahead_weeks") or weeks)
    return (today + timedelta(weeks=w)).isoformat()


def run(cfg, weeks, only=None, use_cache=True):
    # `python pipeline/fetch.py` loads this file as __main__. strategies then
    # does `from fetch import polite_get` and would otherwise get a second copy
    # of the module — with its own ContextVar, so render_for would not apply.
    if __name__ == "__main__":
        sys.modules["fetch"] = sys.modules["__main__"]

    today = date.today()
    today_iso = today.isoformat()
    only_set = None
    if only:
        only_set = {only} if isinstance(only, str) else set(only)

    all_events, report = [], []
    for venue in cfg["venues"]:
        vid = venue["id"]
        if only_set and vid not in only_set:
            continue
        from strategies import resolve_strategy
        if resolve_strategy(venue) == "skip":
            why = ("no whats_on_url (unverified)" if not venue.get("whats_on_url")
                   else "js_rendered, needs a strategy")
            report.append((vid, 0, 0, f"skipped: {why}"))
            continue

        print(f"{vid}...", flush=True)
        horizon = venue_horizon(today, weeks, venue)
        try:
            with render_for(venue):
                rows = stage1(venue, use_cache)
        except Exception as e:                                # noqa: BLE001
            report.append((vid, 0, 0, f"stage1 failed: {type(e).__name__}: {e}"))
            continue

        # window filter before stage 2 — never pay for a show you'd discard
        kept = []
        seen_urls = set()
        for r in rows:
            s, e_ = r.get("first_date"), r.get("last_date")
            if s and e_ and (e_ < today_iso or s > horizon):
                continue
            key = (r.get("url") or "").rstrip("/")
            if key and key in seen_urls:
                continue
            if key:
                seen_urls.add(key)
            kept.append(r)

        hops = 0
        listings = (venue.get("whats_on_url") or "").rstrip("/")
        detail_sel = venue.get("detail_selectors")
        # Ticket booths and Wix banners have no show-page copy worth a hop.
        if not venue.get("skip_stage2"):
            with render_for(venue):
                for r in kept:
                    show_url = (r.get("url") or "").rstrip("/")
                    # hop for copy, and also when the listing published no dates at all
                    wants = (not is_full_synopsis(r.get("description"))
                             or not r.get("first_date"))
                    if show_url and show_url != listings and wants:
                        try:
                            apply_stage2(r, stage2(r["url"], use_cache,
                                                   r.get("title"), detail_sel))
                        except Exception as e:                    # noqa: BLE001
                            r["detail_error"] = f"{type(e).__name__}: {e}"
                        hops += 1

        # merge before the copy is split, so the fullest blurb wins the byline
        kept = merge_runs(kept)
        for r in kept:
            finalise_copy(r)

        # dates that only arrived in stage 2 still have to face the window
        kept = [r for r in kept
                if not (r.get("first_date") and r.get("last_date")
                        and (r["last_date"] < today_iso
                             or r["first_date"] > horizon))]

        for r in kept:
            r.setdefault("venue_id", vid)
        all_events.extend(kept)
        report.append((vid, len(kept), hops, "ok"))

    all_events.sort(key=lambda r: (r.get("first_date") or "9999", r["venue_id"]))
    return all_events, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config", nargs="?",
                    help="path to venues.yaml (positional, optional)")
    ap.add_argument("--venues", dest="venues",
                    help="path to venues.yaml (preferred; matches fetch.yml)")
    ap.add_argument("--weeks", type=int, default=8)
    ap.add_argument("--venue", help="restrict the run to a single venue id")
    ap.add_argument("--ids", help="comma-separated venue ids")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--out", default=".cache/raw.json")
    args = ap.parse_args()

    venues_path = args.venues or args.config or "data/venues.yaml"
    cfg = yaml.safe_load(Path(venues_path).read_text())
    only = None
    if args.ids:
        only = [i.strip() for i in args.ids.split(",") if i.strip()]
    elif args.venue:
        only = args.venue
    try:
        events, report = run(cfg, args.weeks, only, not args.no_cache)
    finally:
        from browser import close as close_browser
        close_browser()

    today = date.today()
    horizon = (today + timedelta(weeks=args.weeks)).isoformat()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(
        {"generated": today.isoformat(),
         "window": [today.isoformat(), horizon],
         "horizon_weeks": args.weeks,
         "count": len(events),
         "events": events}, indent=2))

    print(f"\n{'venue':<26}{'shows':<8}{'hops':<7}status")
    print("-" * 66)
    for vid, n, hops, status in report:
        print(f"{vid:<26}{n:<8}{hops:<7}{status}")
    print("-" * 66)
    print(f"{len(events)} events -> {args.out}")

    no_copy = [e for e in events
               if not e.get("byline") and not e.get("description")]
    if no_copy:
        print(f"\n{len(no_copy)} with no copy at all:")
        for e in no_copy:
            print(f"  {e['venue_id']:<24}{e['title'][:44]}")


if __name__ == "__main__":
    sys.exit(main())
