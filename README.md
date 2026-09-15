# In the Gods

Taste-filtered London theatre. Live at [inthegods.co.uk](https://inthegods.co.uk).

Scrapes a fixed list of London venues weekly, filters for the weird end
of the programme — puppetry, live art, devised, formally strange, spooky
— and renders it as a browsable page with a natural-language search box.

Built for one person's taste. Not a listings site.

---

## Layout

```
data/
  venues.yaml            working venues. THE source of truth. Hand-edited.
  venues-ignored.yaml    researched but not crawled, and why
  venues.sample.yaml     5 venues, for quick test runs
  extracts/
    latest.json          most recent extract — what the frontend reads
    YYYY-MM-DD.json      weekly snapshots, kept for history

.cache/                  crawler dumps, probes, url maps. gitignored.

pipeline/
  resolve_urls.py        find a working whats_on_url from url_candidates
  probe.py               diagnose scrape strategy per venue (read-only)
  inspect_cards.py       print card markup so selectors can be read off it
  patch_urls.py          write resolved urls into venues.yaml
  patch_venue.py         write verified fetch config into venues.yaml
  audit_copy.py          grade byline/description; --live vs the real page
  fetch.py               two-stage crawler -> .cache/raw.json
  browser.py             Playwright Chromium for JS-only listings
  strategies.py          listing extractors (selectors, dated_clusters, …)
  build_extract.py       normalise, tag, window-filter -> latest.json
  refine.py              Haiku drop/retag/prestar (cache: data/refine-cache.json)
  changed.py             CI change detection
  bootstrap_registry.py  one-time generator. DO NOT RE-RUN.

frontend/
  template.html          source. edit this.
  make_artifact.py       injects events into template -> theatre.html
  theatre.html           built output. do not hand-edit.

server/
  app.py                 FastAPI: site + /api/shows + /mcp

tests/
  test_*.py              dates, strategies, tags, synopsis, shrink guard
                         143 tests; every trap below has one

.github/workflows/
  fetch.yml              Monday 06:00 UTC
```

---

## Pipeline

Run order:

    probe.py           diagnose how each venue can be scraped  (read-only)
    fetch.py           two-stage crawl -> .cache/raw.json
    build_extract.py   normalise + tag       -> data/extracts/latest.json
    refine.py          Haiku drop/retag/prestar (data/refine-cache.json)
    changed.py         did anything move?    (used by CI)

`bootstrap_registry.py` generated the first `data/venues.yaml`. It is a
one-time script kept for provenance. **Do not re-run it** — see the
warning at the top of the file.

Venues with `fetch_method: rendered` (or `js_rendered`) are fetched
through Playwright Chromium so JavaScript-built listings exist in the
HTML. Install the browser once with `python -m playwright install chromium`.
CI does this every weekly run.

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -q

# rebuild the page from the committed extract
python frontend/make_artifact.py
open frontend/theatre.html
```

---

## State of things

**Works, verified.** Date parser and form tagger. Registry of 89 working
venues, live-fetched weekly. 46 more sit in `venues-ignored.yaml` (gone,
blocked, or not a house). An 8-week window. 98% carry a byline and 94% a description, audited against
the live pages with `audit_copy.py`. Extract records are `venue_id, title, byline, description,
first_date, last_date, url, tags`. Byline is the opening grab of the show
copy, capped at 240 characters. Description is the rest of the synopsis.
Tags are form only: theatre, musical, stand-up, concert, opera, dance.

**Live crawl.** `probe.py` and `fetch.py` run against real venues. Stage 2
hops to the show page when the listing has no real synopsis *or* no dates.
Young Vic show pages 403 (Cloudflare); those blurbs stay missing.

**Serving.** `server/app.py` is the live app at inthegods.co.uk: the page,
`/api/shows`, and `/mcp` for Claude.

---

## Onboarding a venue

The four steps, in order. Nothing here rewrites the identity fields in
`venues.yaml` — those are researched by hand.

```bash
# 1. which of the url_candidates actually serves a listing?
python pipeline/resolve_urls.py --ids gate-theatre,lift
python pipeline/patch_urls.py --maps .cache/url_map.json

# 2. what kind of page is it?
python pipeline/probe.py --ids gate-theatre

# 3. read the selectors off the real markup
python pipeline/inspect_cards.py --id gate-theatre --suggest
python pipeline/inspect_cards.py --id gate-theatre --card .event-card \
    --title h3 --dates .date --link a
# JS-only listings: --render drives Chromium so the cards actually exist
python pipeline/inspect_cards.py --id woolwich-works --render --suggest

# 4. write it in, then prove it pulls dated, linked events
python pipeline/patch_venue.py --patch .cache/onboard.yaml --dry-run
python pipeline/fetch.py --ids gate-theatre --weeks 8 --out /tmp/one.json
```

Step 3 is the whole job. `probe.py` counts repeated class signatures,
which is enough to tell JSON-LD from cards but *not* enough to write a
selector — the most common signature on a listing page is usually the
nav. Look at the markup.

Two selector keys narrow the listing rather than read a field:

- `space_allow` — keep only cards whose space matches. The National
  advertises Broadway transfers, cinema screenings and streaming next to
  its three auditoria; without this you capture all of them.
- `exclude` — drop cards whose title or url contains a value. Touring
  companies list every city they play.

And `detail_selectors.dates` tells stage 2 where the run lives on the
show page, for listings that publish no dates at all.

Wix houses have no repeating card class. `strategy: dated_clusters` walks
up from each dated scrap of text, takes the heading immediately before
it, and prefers a link whose slug looks like that title. Hope, Golden
Goose, Playground and White Bear use it. `fetch_method: rendered` is what
makes the dates exist in the HTML in the first place.

---

## What the probe found

59 of the 115 venues have been probed. The answer to the question the
architecture was resting on — how many publish JSON-LD — is essentially
none. One venue in 59 got a `jsonld` recommendation, and even that one
carried no Event objects with their own url. **CSS selectors are the
job**, not a fallback, which is why the two narrowing keys above exist.

Ticketing platform detection is a red herring worth stating plainly:
Spektrix, TicketSolve and TicketSource turn up all over the results and
tell you nothing about the listing page. They sell seats.

The wall is JavaScript. Of the 28 tier-1 venues probed in the last pass,
15 returned only nav and footer classes with almost no text in the raw
HTML, and Tara Theatre returned 23 characters — a Nuxt shell. Those need
a rendering strategy or a platform API, not a better selector.

**Every unscraped venue records why.** `data/venues-ignored.yaml` is the
graveyard: 44 houses with an `id` and a `reason`. If it is not in
`venues.yaml`, we do not crawl it.

**Ask the site where its listing is.** The candidate-path list only ever
guesses (`/whats-on/`, `/events/`, `/programme/`). Venues label the page
in their own nav and the labels are unguessable: Jermyn Street calls it
`now-next`, Pentameters serves `WhatsOn.html`, the Hope hyphenates it
`what-s-on`, Theatre Deli buries it under `/Pages/Events/Category/`.
`resolve_urls.py` now follows the site's own nav link whenever the
candidates fail *or* land on a bare homepage, which is what a homepage
usually is — not the listing.

**A moved venue looks exactly like a dead one.** The resolver only tries
the registry's domain, so three venues were sitting in the dead pile
having simply rebranded: the Old Red Lion is now `weareoldred.co.uk`,
Etcetera is `etceteratheatrecamden.com`, and the Playground moved from
`.london` to `.org.uk`. Etcetera turned out to be the single richest
tier-2 source in the registry. Re-check the dead pile against a search
engine now and then; a `ConnectionError` is evidence about a domain, not
about a theatre.

**The Wix wall, mostly cleared.** Wix renders each block into a container
with a hashed class that changes when the venue republishes, and there is
no repeating card class to anchor to. `dated_clusters` does not need one
— it pairs each date with the heading in front of it — so Hope, Golden
Goose, Playground and White Bear now scrape. The four that remain either
have no dates after Chromium (Well Walk, Barons Court), 404 their listing
(Rosemary Branch), or serve a members login (Arches Lane).

**Do not trust the probe's card ranking.** It counts repeated class
signatures, and on most listing pages the most repeated class is the
navigation. Six of the tier-2 venues onboarded in the last pass were
sitting in the probe's "needs a closer look" pile with a perfectly good
`.eventCard` or `.each-activity` one line further down. Use `probe.py`
to tell JSON-LD from cards from a JS shell, then read the markup with
`inspect_cards.py`.

---

## Traps already found

Recording these because each one produced plausible-looking wrong output
rather than an error.

**Trailing slashes are per-venue.** Camden People's Theatre slugs take
*no* trailing slash. Appending one broke all 23 of their links at once.
Wilton's and Arcola were inferred from observed URLs, never tested — same
bug could be sitting there. Never construct a slug; scrape the href.

**CPT slugs are case-sensitive and literal** — `Standing-Ovation-wip`
lowercase on the last word, `Like-a-Rat-` with a trailing hyphen. Scrape
them from the href. Never construct them from the title.

**Storage keys must not be positional.** The frontend originally keyed
saved shows by array index, so next week's extract would silently
reattach your stars to different shows. Now keyed
`venue_id::slugified-title`, verified collision-free across all 50
events. Known tradeoff: a revived production next year gets the same key
and inherits the old verdict. Left deliberately.

**`2026` parses as day 20 then day 26** if you scan for day numbers
before stripping four-digit years. Covered by a regression test.

**Cross-year ranges** must anchor on the *first* year in the string.
`3 Dec 2026 - 2 Jan 2027` starts in 2026. Also covered.

**CPT will dominate the digest.** They list ~23 events per 8 weeks
against Southwark's 5. Cap picks per venue or the whole thing becomes a
CPT newsletter.

**Show-page copy beats the listing stub.** A card subtitle is a byline.
The synopsis lives on the show page. `one_stage: true` used to skip that
hop and left descriptions empty.

**A named closing year must be used, not inferred.** The end of a range
reused the *opening* year and then rolled forward by one when it landed
before the start. `10 Feb 2025 - 1 Jan 2027` came out as 2026. Barbican
runs installations for two years, which is how this surfaced. Anchor the
start on the first year in the string and the end on the last.

**Ordinals hide the day.** `25th - 27th September` parsed as nothing at
all, because the `th` sat between the digits and the month and broke the
pairing. Strip ordinal suffixes before looking for days.

**A listing page need not carry dates.** The Barbican's cards show only
`Final week` style labels. Do not let the date parser fall back to the
whole card text there — a stray number in the blurb becomes a date, and
because stage 2 only fills *empty* fields it would then block the real
run from the show page. Point `dates` at a class the cards don't carry
and let stage 2 do it.

**Big houses list things you cannot attend.** Half the National's
what's-on is cinema broadcasts, NT at Home streaming and West End or
Broadway transfers. They look exactly like listings and about half carry
no parseable date, so they fail quietly rather than loudly.

**A festival is not a venue.** Grimeborn's `whats_on_url` and card
selector are Arcola's, because it *is* Arcola's festival. Onboarding it
would have duplicated all nine of Arcola's rows under a second venue id,
and the de-duplication in `fetch.py` is per-venue, so nothing would have
caught it. Darkfield is the same shape: a touring company whose London
dates are already captured under Shoreditch Town Hall.

**Duplicate yaml keys are silent.** 32 venues carried `last_verified`
twice — once from the bootstrap, once from onboarding. The loader keeps
the last and says nothing. `patch_venue.py --dedupe` clears them and
refuses to write a patch that would create more.

**A card per performance is not a show per performance.** The Courtyard
lists every night separately, each with its own See Tickets link, so the
url de-duplication in `fetch.py` could not tell they were one production
and Serious Money appeared ten times. `merge_runs` collapses rows that
share a title within a venue, taking the union of the dates and the
fullest blurb. Run it *before* the copy is split, so the byline comes
off the best description rather than whichever card sorted first.

**An open-ended run sails through the window filter.** A range that
contains today always overlaps an 8-week window, so Finborough's
permanently-open online archive pages — carrying JSON-LD end dates of
2028 and one of **2050** — were being treated as current shows. Stage 2
now rejects a span longer than three years. The threshold has to be that
generous because the Barbican really does run a 690-day installation.

**A semantic root can be empty.** The synopsis extractor scoped itself to
`article, main, [role=main], .entry-content` on the reasonable assumption
that show copy lives there. Camden People's Theatre wraps its pages in an
`<article>` containing no paragraphs at all, so 18 of its listings lost
their description while the copy sat in the document just outside it. Now
the root is only used if it actually holds paragraphs. Worth 19 recovered
descriptions across the registry.

**Some sites nest `<p>` inside `<p>`.** The Drayton Arms does, so the
outer paragraph reads as every child glued together and every byline came
out as `By William Shakespeare Viola is washed ashore in Illyria...`.
Prefer leaf paragraphs — but fall back, because St Bride's nests the
other way round and keeps only the address and charity number in its
leaves.

**A credit is not a hook.** `By Madeline Whitby and Elizabeth Whitby.
Directed by Anna Girvan.` is a fine thing to know and a terrible reason
to click. `is_credits` drops a paragraph whose every sentence is nothing
but names. The test that matters is the one for `By Tuesday the whole
street knew` — the giveaway is a lowercase word that is not joining two
names, not the word `by`.

**Listings truncate titles.** Theatre503 cuts card titles at a fixed
width, so 14 of its 20 rows arrived as `Advanced Playwriting with
Satinder ...`. Stage 2 is already on the show page, so it recovers the
real title from `og:title` — but only when the card's version is
visibly truncated, because the show page usually appends the house name.

**`python pipeline/fetch.py` loads a second `fetch` module.** `strategies`
does `from fetch import polite_get`. When the file runs as `__main__`,
that import is a different module with its own ContextVar, so
`render_for` is a no-op and every JS venue returns 0 rows. `run()`
aliases `sys.modules["fetch"]` to `__main__` before the first venue.

**Playwright wants chrome-headless-shell.** Recent Playwright launches
that binary by default. `playwright install chromium` must land both it
and full Chromium; a repo-local `.playwright/` directory is used when
the user cache is missing, and launch falls back to system Chrome.

**TicketSolve copy is often `<font>`, not `<p>`.** The hop to the booth
show page does fetch the blurb (Hauntings at OSO was in the cache), but
the editor writes it as nested `<font>` tags. `synopsis_from_soup` only
read `<p>`, so those listings came back empty. Fall back to leaf `<font>`
blocks when paragraphs yield nothing.

**Opera-house production pages hide the plot under Synopsis.** Royal Ballet
and Opera listing cards are title and date; the hop finds a cast line and
ticket-price chrome first, and the three-paragraph budget fills before
the h3 Synopsis. Start the walk at that heading, and treat ticket prices,
running times and surtitles as chrome.

**Wix date widgets share a parent.** Walking up from the date attaches
the previous show's URL, so Iceberg Right Ahead linked to We'll Always
Have Paris. Walk up from the heading instead, and prefer a href whose
slug looks like the title.

**Chromium is not a strategy.** Tara still serves 12 characters, Peckham's
Line-up widget stays empty, Arches Lane is a Wix login wall, and
TicketSource Cloudflare-challenges a real browser. `blocked_by` stays.

---

## The weekly job

`fetch.yml` runs Monday 06:00 UTC, installs Chromium, then `make recollect`
(fetch, extract, refine, rebuild `theatre.html`). It commits a dated snapshot
**only when the shows actually changed** — `changed.py` fingerprints the events
alone, because `generated` and `window` move every run and would otherwise
produce an identical commit every week forever. A change also runs
`make deploy`, so inthegods.co.uk picks up the new extract.

The dated snapshots are what make went/skipped history possible later.
Don't prune them.

---

## Distribution

The Docker image serves three things from one process:

1. **The page** at `/` (`theatre.html`).
2. **JSON** at `/api/shows`.
3. **MCP** at `/mcp` (Streamable HTTP). Claude Desktop can use
   `http://localhost:8080/mcp`. Claude.ai custom connectors need
   `https://inthegods.co.uk/mcp`.

---

## Open questions

- **Ten events still have no copy at all**, and each is blocked rather
  than missed: the Young Vic's four sit behind Cloudflare, the
  Courtyard's five link only to See Tickets, which publishes no synopsis.
  Twenty-five more have a byline but no description because the venue
  genuinely published only a sentence or two. `audit_copy.py --live`
  prints any of them next to the real page.
- **The tagger has no way to say "not a show."** Everything it cannot
  place falls to `theatre`, which is now the tag on 438 of 637 events.
  That was fine for producing houses and is wrong for mixed-use venues:
  Alexandra Palace brings 35 rows of ice hockey, basketball and
  lifestyle expos, artsdepot's 8-week window is entirely yoga, pilates
  and painting classes, Theatre503's is mostly playwriting courses, and
  Bridewell's is letterpress workshops. All captured correctly — the
  listings really do say that. Either the tagger needs a drop verdict or
  those venues need a narrower listing url. This is the single biggest
  quality problem in the extract.
- 58 venues are still unonboarded, and most of them are accounted for.
  Nine are `status: gone` — expired Squarespace accounts, Wix domains
  detached from their sites, and domains that no longer resolve at all.
  Thirteen are deliberate exclusions: touring companies and festivals
  (Darkfield, Gecko, Ockham's Razor, ZU-UK, Nunkie, Charles Court Opera,
  SPILL, Voila!, Grimeborn, GDIF, Mime London) whose London dates belong
  to whichever house hosts them. Six are behind the Wix wall above. The
  honest remainder is small.
- Pentameters is dark rather than broken: its What's On page says all
  events are suspended over a dispute with its landlord. The page is
  maintained, so it is worth re-checking rather than removing.
- **The remaining wall is JavaScript and ticketing platforms.** Bernie
  Grant publishes no listings on its own site at all — everything is on
  TicketSource, which answers a plain fetch with a 403 interstitial.
  TicketSource also fronts Hoxton Hall and part of Bridge House, and
  Young Vic's Cloudflare block is the same shape. One rendering
  strategy would unlock a dozen venues; nothing else will.
- Prices are extracted by stage 2 but not yet shown in the frontend —
  the most valuable missing field given the £35 ceiling.
- Registry is hand-curated. Should it discover new venues itself?
- Friends layer deferred: self-asserted names, per-person shared keys
  (`stars:rob`) so nobody clobbers anyone else's list.
