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

---

## Venue research

### Unusual Theatre in London — Source List

A research list of venues, festivals and companies worth aggregating into a
personal events page. Ordered roughly by likely signal-to-noise for formally
strange, immersive, puppetry/object, site-specific, macabre and philosophically
odd work.

Columns to fill during research: **listings URL**, **ticketing platform**,
**feed available?**, **update cadence**, **hit rate** (what fraction of their
programme you'd actually want to see).

#### Tier 1 — High hit rate, check every season

| Venue | Area | Why it's on the list | Domain (verify) |
|---|---|---|---|
| New Diorama | Euston | Ensemble and devised work, 80 seats, the most influential studio theatre in the UK. Consistently the strangest programming per square metre. | newdiorama.com |
| Battersea Arts Centre | Battersea | Old Town Hall, scratch nights, live art, one-on-one work. Now leads LIFT. | bac.org.uk |
| The Yard | Hackney Wick | Hard, formally unstable new work. Live Drafts season for early-stage pieces. | theyardtheatre.co.uk |
| Camden People's Theatre | Camden | 60 seats, solo and hybrid work, themed mini-festivals (Sprint, Calm Down Dear). | cptheatre.co.uk |
| Little Angel Theatre | Islington | "The home of British puppetry." 1961, former temperance hall, 100 seats, plus Little Angel Studios. One of only three building-based puppet theatres in England. Rare double marionette bridge, being renovated for the 65th anniversary. Mostly children's work — but hosts visiting international companies, runs adult puppetry courses, and is the institutional centre of gravity for UK puppetry. Watch for the heritage strand and visiting-company slots rather than the family programme. | littleangeltheatre.com |
| Shoreditch Town Hall | Shoreditch | The Victorian basements are the draw. Site-responsive work, MimeLondon partner. | shoreditchtownhall.com |
| Toynbee Studios (Artsadmin) | Aldgate | Live art proper. Closest surviving thing to the Shunt lineage. | artsadmin.co.uk |
| Jacksons Lane | Highgate | UK's main contemporary circus house. | jacksonslane.org.uk |

#### Tier 2 — Worth a standing check

| Venue | Area | Why | Domain (verify) |
|---|---|---|---|
| Wilton's Music Hall | Wapping | The building does half the work. Folk horror, ghost stories, puppetry. | wiltons.org.uk |
| Arcola | Dalston | Mainly for **Grimeborn**, its alternative opera festival (Aug–Sep). | arcolatheatre.com |
| The Cockpit | Marylebone | In-the-round; birthplace of the Mime Festival in 1977. Oddities, improvised opera. | thecockpit.org.uk |
| Drayton Arms | South Kensington | Small pub theatre, but hosts the Lovecraft Festival. | — |
| Well Walk Theatre | Hampstead | Micro-venue. Included as your original reference point. | — |
| Lower Marsh Arts Club | Waterloo | The Glitch becomes LowMAC on 7 Sept 2026 — VAULT's successor. Up to three shows a night. Untested but promising. | wearevault.org |

#### South London cluster (your patch)

| Venue | Area | Notes | Domain (verify) |
|---|---|---|---|
| Brixton House | Brixton | Hosts LIFT co-productions. | brixtonhouse.co.uk |
| Omnibus | Clapham | Old library. 96 Festival, new writing. | omnibus-clapham.org |
| The Albany | Deptford | Hosted *Sun & Sea*, the Lithuanian beach opera. | thealbany.org.uk |
| Blue Elephant | Camberwell | Tiny, physical and international work. | blueelephanttheatre.co.uk |
| Southwark Playhouse | Borough + Elephant | Two buildings, three spaces. Borough (77–85 Newington Causeway) is the smaller, scrappier one and where the odd stuff lands; Elephant (Dante Place, opened 2023) leans musicals and bigger transfers. Remit is emerging practitioners, so hit rate is variable but volume is high and it's ten minutes from you. Typical Borough pricing £22–£24, £18–£19 concessions. | southwarkplayhouse.co.uk |
| Punchdrunk (One Cartridge Place) | Woolwich | *Lander 23* booked to May 2026 — check what replaced it. | punchdrunk.com |
| Bridge Command | Vauxhall | Parabolic Theatre's starship LARP. | bridgecommand.space |
| CLF Art Café / Bussey Building | Peckham | Unpredictable; performance on the upper floors. | — |

#### Festivals — calendar anchors

| Festival | When | Notes | Domain |
|---|---|---|---|
| MimeLondon | Late January | LIMF's successor. 2026 ran 21–31 Jan across Sadler's Wells, The Place, Peacock. Also an October slot — Baro d'evel at the Southbank. | mimelondon.com |
| London Lovecraft Festival | February | Sixth year in 2026, seven days at the Drayton Arms. Expanding into interactive work. | londonlovecraft.com |
| GDIF | Aug–Sep | Free, outdoor, South East London. 21 Aug – 6 Sep 2026. Highest volume of genuinely odd free work in your area. | festival.org |
| Grimeborn | Aug–Sep | Alternative opera at the Arcola. | arcolatheatre.com |
| Suspense | Autumn, odd years | Adult puppetry festival. Little Angel is a core partner — worth checking whether 2027 is confirmed. | — |
| LIFT | Biennial, summer | Now run by BAC. Next edition likely 2027. | liftfestival.com |
| SPILL / Voila! Europe / CASA | Sporadic | Smaller, reliably weird. Low volume, high variance. | — |

#### Cheap tier — under £20, high volume, high variance

Worth aggregating precisely *because* they're cheap: at £12–£18 a bad night
costs you nothing much, so you can take punts you wouldn't take at £40. Expect
a low hit rate and treat these as a lucky-dip feed rather than a curated one.

| Venue | Area | Notes | Domain (verify) |
|---|---|---|---|
| Theatre503 | Battersea | New writing only, above a pub. The best of the pub theatres by a distance. | theatre503.com |
| The Space | Isle of Dogs | Converted Presbyterian chapel. Genuinely odd programming, very cheap. | space.org.uk |
| Bread & Roses | Clapham | Above a socialist pub. Chaotic, occasionally excellent. | breadandrosestheatre.co.uk |
| Golden Goose | Camberwell | Small, local to you, unpredictable. | goldengoosetheatre.co.uk |
| Union Theatre | Southwark | Railway arch. Revivals and small-scale opera. | uniontheatre.biz |
| White Bear | Kennington | Long-running pub theatre, dark and small. | whitebeartheatre.co.uk |
| Old Red Lion | Angel | Same lineage; the Play That Goes Wrong started here. | oldredliontheatre.co.uk |
| King's Head | Islington | Moved to a purpose-built space; opera and queer work. | kingsheadtheatre.com |
| Tara Theatre | Earlsfield | South Asian and international work, small and warm. | tara-theatre.com |
| Greenwich Theatre | Greenwich | Cheap, and a GDIF partner. | greenwichtheatre.org.uk |
| Rich Mix | Shoreditch | Cross-artform; spoken word, dance, film, live art. | richmix.org.uk |
| Café OTO | Dalston | Not theatre, but the closest thing London has to a permanent home for the properly experimental. Worth the same feed. | cafeoto.co.uk |
| Chisenhale Dance Space | Bow | Artist-led, works-in-progress, near-free. | chisenhaledancespace.co.uk |

#### Getting in cheaply at the expensive venues

Worth encoding as flags on venue records rather than chasing manually:

- **Pay What You Can** — Arcola runs this as a standing scheme; several others
  do it on specific performances. Usually the first preview or a designated
  midweek night.
- **Previews** — routinely £10–£15 below run price, and at studio scale the
  show is essentially finished anyway.
- **Rush / day tickets** — Punchdrunk has run £25 rush tickets via Time Out for
  its Woolwich shows; worth checking whether that survives into the current
  production.
- **Free** — GDIF's outdoor programme is entirely free and unticketed. The
  single highest volume of unusual performance per pound in South East London,
  once a year.
- **Concessions** — most fringe venues knock £3–£5 off without checking
  anything.

#### Roving companies — follow, not venues

- **Darkfield** — binaural pieces in lightless shipping containers. Surfaces
  at Southbank, LFF, Edinburgh. (darkfield.org)
- **El Conde de Torrefiel** — Catalan, text-and-landscape, appears via GDIF and
  LIFT. Track through festivals, not a venue.
- **Ockham's Razor** — object/aerial, LIMF veterans.
- **Gecko** — physical theatre; *The Wedding* is the standard reference.
- **ZU-UK** — participatory work, often east London.

#### Registry — tested, not guessed

Every row below has been fetched at least once. This is the actual data the
chain should run against — status of "static" means the homepage or listings
page returns full show data (title, dates, venue space, direct link) to a plain
fetch; "JS-rendered" means it returns an empty shell and needs a different
approach.

| Venue | Direct URL to hit | Status | Notes |
|---|---|---|---|
| Arcola Theatre | arcolatheatre.com/whats-on/ | Static | Clean cards: title, venue space, dates, and a `/event/slug/` link per show. Also lists workshops and festivals (Grimeborn) on the same page — filter by "Studio 1/2" to catch the actual productions. |
| Southwark Playhouse | southwarkplayhouse.co.uk | Static | The homepage itself is the listings page — "Now Showing" and "Coming Soon" sections, full dates, venue (Borough/Elephant), theatre space, and `/productions/slug/` links. No deeper page needed. |
| Wilton's Music Hall | wiltons.org.uk/whats-on/the-signalman/ (per-show) | Static, per-show | The general `/whats-on/` listing page returned thin results in testing; per-show URLs (`/whats-on/show-slug/`) are reliable once you have the slug. Worth re-testing the listing page directly before relying on this. |
| The Yard Theatre | theyardtheatre.co.uk/whats-on | JS-rendered | Plain fetch returns an empty Next.js shell — no show data. Needs a search fallback or an RSS feed if one exists; don't rely on a direct fetch here. |
| Camden People's Theatre | cptheatre.co.uk/Whats-On | Static | Returns show titles, blurbs, and date ranges directly. |

**Not yet tested:** everything else in the venue lists below — New Diorama,
BAC, Jacksons Lane, Toynbee, the cheap tier, GDIF/festival sites. Same method
applies: fetch the venue's own root or listings URL once, note whether it
returns real data or a JS shell, and log it here before the chain relies on it.

#### Build notes

**The aggregation problem.** These venues don't share a listings standard.
Realistically three approaches, in order of effort:

1. **Ticketing platform APIs.** A large share of mid-size UK arts venues run on
   Spektrix, with TicketSolve and TicketSource common lower down the scale.
   Where a venue uses one, its instance often exposes structured JSON that's
   far cleaner than scraping the site. **First research task: for each venue
   above, open the booking flow and note which platform the checkout redirects
   to.** That single column will determine how much of this is easy.
2. **RSS / sitemap.** Several of these run WordPress. `/whats-on/feed/` or the
   XML sitemap will often give you a clean list of show pages to then parse
   individually.
3. **HTML scraping.** Last resort. Small venues redesign often and will break
   you.

**Schema suggestion**, given you'll want to filter rather than read:

```
venue_id, show_title, url, first_date, last_date, price_min,
form (physical / puppetry / immersive / live-art / opera / text),
source_platform, first_seen, notes
```

The `form` field is the one that earns its keep — it's what lets you ignore the
family puppetry at Little Angel and the new writing at Brixton House while
still tracking both venues.

**Cadence.** Most of these announce seasons twice a year (spring/summer and
autumn/winter), typically Nov–Dec and May–July. A weekly poll is more than
enough; a daily one just burns requests.

**Second-order sources** worth polling alongside the venues, since they catch
things that never appear on a venue's own site: Time Out's Experimental tag,
Stagedoor, Immersive Rumours, Everything Immersive, Everything Theatre, and
Theatre Weekly's press-release feed.

### London Theatres: A Comprehensive Tracking List (August 2026)

**TL;DR**

- This is a working list of ~110 currently-operating London venues in two
  tiers — (1) quality non-touristy producing houses and off-West End venues
  and (2) smaller pub/fringe/micro venues — with a heavy emphasis on the
  "artistic crafty flair" you want (puppetry, physical theatre, circus, live
  art, immersive, alternative opera, folk-horror/ghost programming).
- Verified status flags: Hope Theatre (Islington) still operating under Greene
  King; Matchstick Piehouse reopened as **Piehouse Co-op** (2025); Gate Theatre
  gave up Notting Hill and is now itinerant; Blue Elephant surrendered its
  Camberwell building (Dec 2024) but continues as a company; The Bunker is
  closed but the **Turbine reopened in 2025 as Arches Lane Theatre**; VAULT's
  successor **Lower Marsh Arts Club (LowMAC)** launches 7 September 2026.
- South London (your Crystal Palace base) is covered in depth, but all compass
  points and outer boroughs are included.

#### How to use this list

Each entry gives venue name, a short identity description, location
(neighbourhood + borough/compass + nearest station), and the venue's own
website domain (for your scraper — not ticket resellers). Excluded: West End
commercial houses, tourist musical barns, and permanently closed venues.
Where status is uncertain or recently changed, it is flagged.

#### Category 1 — Quality non-touristy producing houses and off-West End venues

##### Flagship producing houses / new-writing powerhouses

- **Almeida Theatre** — Islington powerhouse known for stunningly designed
  reimagined classics and new work that regularly transfers; the reference
  standard for this list. Islington (North), nearest Angel/Highbury &
  Islington. almeida.co.uk
- **Young Vic** — Leading directors' theatre near Waterloo, flexible main house
  plus Maria and Clare studios; bold reinventions of classics and international
  work. South Bank, Lambeth (South), nearest Waterloo/Southwark. youngvic.org
- **Donmar Warehouse** — 251-seat not-for-profit in Covent Garden; new writing,
  European classics, small-scale musicals, star-driven but serious. Covent
  Garden, Westminster (Central), nearest Covent Garden. donmarwarehouse.com
- **Royal Court Theatre** — The English Stage Company's home of new writing
  since 1956; Theatre Downstairs (380) and Theatre Upstairs (85). Sloane Square,
  Kensington & Chelsea (West), nearest Sloane Square. royalcourttheatre.com
- **Bush Theatre** — Champion of new writers in the former Shepherd's Bush
  Library; 144-seat main house plus studio. Shepherd's Bush, Hammersmith &
  Fulham (West), nearest Shepherd's Bush. bushtheatre.co.uk
- **Hampstead Theatre** — Main stage plus Hampstead Downstairs studio; draws
  big names for premieres (Pinter premiered here). Swiss Cottage, Camden
  (North), nearest Swiss Cottage. hampsteadtheatre.com
- **Kiln Theatre** — Kilburn's diverse producing house (formerly Tricycle),
  reflecting its multicultural home. Kilburn, Brent (North-West), nearest
  Kilburn. kilntheatre.com
- **Lyric Hammersmith** — Historic Frank Matcham auditorium plus studio;
  ambitious plays, musicals and a strong young-people's programme. Hammersmith
  (West), nearest Hammersmith. lyric.co.uk
- **Orange Tree Theatre** — Intimate theatre-in-the-round in Richmond;
  rediscovered classics and new writing. Richmond (South-West), nearest
  Richmond. orangetreetheatre.co.uk
- **Soho Theatre** — New comedy, cabaret and new writing engine in the West End
  fringe; hub for edgy stand-up and solo work. Soho, Westminster (Central),
  nearest Tottenham Court Road. sohotheatre.com
- **Park Theatre** — Finsbury Park two-space producing/receiving house (Park200
  and Park90); polished plays and revivals. Finsbury Park, Islington (North),
  nearest Finsbury Park. parktheatre.co.uk
- **Hackney Empire** — Grand Frank Matcham variety house; panto, comedy, music,
  community and touring drama. Hackney (East), nearest Hackney Central.
  hackneyempire.co.uk
- **Theatre Royal Stratford East** — Historic radical producing house; new
  musicals, diverse new writing, strong community roots. Stratford, Newham
  (East), nearest Stratford. stratfordeast.com
- **Coronet Theatre** — Notting Hill's atmospheric former cinema (ex-Print
  Room); European-leaning theatre, dance, music and art in a beautifully faded
  auditorium. Notting Hill, Kensington & Chelsea (West), nearest Notting Hill
  Gate. thecoronettheatre.com
- **Menier Chocolate Factory** — Southwark studio + restaurant known for
  acclaimed musical revivals and plays. Southwark (South/Central), nearest
  London Bridge. menierchocolatefactory.com
- **Barbican Centre** — Europe's largest performing arts centre, a Brutalist
  labyrinth in the City; the Barbican Theatre and The Pit host international
  theatre, dance and formally ambitious work (Complicité, Robert Lepage,
  Punchdrunk collaborations), alongside music, film and art — genuinely
  un-touristy despite its scale, and a natural home for anything strange, large
  and international. City of London (Central/East), nearest Barbican/Moorgate.
  barbican.org.uk

##### Experimental / live art / interdisciplinary institutions

- **Battersea Arts Centre (BAC)** — The home of experimental and devised
  theatre in the old Battersea Town Hall; pioneered the Scratch development
  model, one-on-one and building-wide work. Battersea, Wandsworth (South),
  nearest Clapham Junction. bac.org.uk
- **The Yard Theatre** — Hackney Wick's edgy artist-hub in a converted
  warehouse; formally strange new work, club nights, a genuine crucible of the
  weird (Peter Brook Empty Space Award-winning). Hackney Wick, Hackney (East),
  nearest Hackney Wick. theyardtheatre.co.uk
- **Camden People's Theatre (CPT)** — Proudly scruffy 60-seat Euston stalwart
  (in its fourth decade) for experimental, feminist, queer, physical and
  devised performance; where many artists premiere their first show. Euston,
  Camden (North/Central), nearest Warren Street/Euston. cptheatre.co.uk
- **Artsadmin / Toynbee Studios** — Producer and 280-seat art-deco theatre plus
  studios in Aldgate; live art, contemporary performance, interdisciplinary
  and socially/environmentally engaged work (est. 1979 by Judith Knight and
  Seonaid Stewart). Aldgate, Tower Hamlets (East), nearest Aldgate East.
  artsadmin.co.uk
- **Chisenhale Dance Space** — Artist member-led experimental dance and live
  art since 1984, atop a former veneer factory near Victoria Park; raw,
  process-driven, DIY (stairs-only, ~40 steps). Bow, Tower Hamlets (East),
  nearest Mile End. chisenhaledancespace.co.uk
- **Shoreditch Town Hall** — Grand Victorian civic building hosting immersive,
  site-responsive and large-scale independent theatre. Shoreditch, Hackney
  (East), nearest Shoreditch High Street/Old Street. shoreditchtownhall.com
- **New Diorama Theatre** — 80-seat Regent's Place theatre punching far above
  its weight; ensemble and devised companies, two Peter Brook awards and Fringe
  Theatre of the Year 2022; runs the free "Allotment" development space with
  Theatre Deli. Euston/Regent's Place, Camden (North/Central), nearest Great
  Portland Street/Warren Street. newdiorama.com
- **Rich Mix** — Five-floor converted leather factory; cross-arts cinema,
  theatre, dance, spoken word, music, host to diverse independent work.
  Shoreditch, Tower Hamlets (East), nearest Shoreditch High Street.
  richmix.org.uk
- **Wilton's Music Hall** — The world's oldest surviving grand music hall,
  gloriously patinaed; opera, puppetry, cabaret, magic, music and theatre (300+
  performances a year) in a Grade II*-listed heritage space. Shadwell/Wapping,
  Tower Hamlets (East), nearest Tower Hill/Aldgate East. wiltons.org.uk
- **Hoxton Hall** — Rare surviving Victorian saloon-style music hall;
  community-rooted theatre, cabaret and heritage programming. Hoxton, Hackney
  (East), nearest Hoxton/Old Street. hoxtonhall.co.uk
- **Jacksons Lane** — The UK's leading contemporary circus venue, in a
  converted Grade II-listed Edwardian Methodist church in Highgate; circus,
  cabaret, clowning, physical and family work, with major artist-development
  and 6.5m rigging facilities after a £5m 2022 refurbishment. Highgate,
  Haringey (North), nearest Highgate. jacksonslane.org.uk
- **Punchdrunk (One Cartridge Place)** — The immersive-theatre giants'
  permanent Woolwich home; vast, hyper-detailed masked worlds (*The Burnt
  City*, and *Lander 23*, booking to May 2026). Woolwich, Greenwich
  (South-East), nearest Woolwich (Elizabeth line)/Woolwich Arsenal.
  punchdrunk.com
- **Woolwich Works** — Multi-building Royal Arsenal creative district
  (resident companies incl. Punchdrunk, Chineke!, National Youth Jazz
  Orchestra); concerts, circus, performance, with a 1,200-capacity hall and
  600-seat courtyard. Woolwich, Greenwich (South-East), nearest Woolwich.
  woolwich.works

##### Puppetry and object theatre

- **Little Angel Theatre** — "Home of British Puppetry" since 1961; a 100-seat
  former temperance hall (14 Dagmar Passage, N1 2DN) plus a separate black-box
  studio on Sebbon Street. Mostly children's puppetry but institutionally vital
  to puppetry as an art form (included with that note). Islington (North),
  nearest Angel/Highbury & Islington. littleangeltheatre.com
- **Puppet Theatre Barge** — A magical 50-seat marionette theatre on a converted
  Thames barge; long-string marionette shows, moored in Little Venice (Oct–Jul)
  and Richmond (summer). Little Venice, Westminster (West/Central), nearest
  Warwick Avenue. puppetbarge.com

##### Community producing houses and mid-scale venues

- **Brixton House** — Modern producing theatre and cultural hub (successor to
  Ovalhouse, opened 2022), two auditoria (180 + 120); socially engaged, diverse,
  community-rooted work. Brixton, Lambeth (South), nearest Brixton.
  brixtonhouse.co.uk
- **Omnibus Theatre** — Multi-award-winning independent theatre in Clapham's
  old Victorian library; reimagined classics, new writing, strong LGBTQ+
  platform and the queer 96 Festival (London's longest-running queer arts
  festival). Clapham, Lambeth (South), nearest Clapham Common.
  omnibus-clapham.org
- **The Albany** — Deptford multi-arts centre (up to 300 seated/500 standing
  plus two studios); music, spoken word, theatre, family and community work
  reflecting South-East London's diversity; home to Apples & Snakes and Heart
  n Soul. Deptford, Lewisham (South-East), nearest Deptford/New Cross.
  thealbany.org.uk
- **Greenwich Theatre** — Mid-scale producing/receiving house (a former
  Victorian music hall); drama, musicals, comedy, panto and studio work.
  Greenwich (South-East), nearest Greenwich/Cutty Sark.
  greenwichtheatre.org.uk
- **Tara Theatre** — 100-seat producing house in Earlsfield; Britain's
  pioneering South Asian/global-majority theatre company (est. 1977),
  politically charged and cross-cultural. Earlsfield, Wandsworth (South-West),
  nearest Earlsfield. taratheatre.com
- **Streatham Space Project** — Purpose-built 120-seat neighbourhood arts venue
  (opened 2018); theatre, comedy, music (jazz to grime to folk), film and
  mini-festivals, platforming emerging artists. Streatham Hill, Lambeth
  (South), nearest Streatham Hill. streathamspaceproject.co.uk
- **CLF Art Café (Bussey Building)** — Multi-level former cricket-bat factory
  in Peckham; live music, theatre, opera, film, raves and experimental
  cross-arts work in a raw warehouse. Peckham, Southwark (South-East), nearest
  Peckham Rye. clfartcafe.org
- **Southwark Playhouse (Borough & Elephant)** — Two-site studio house across
  three spaces; new and emerging practitioners, plays and musicals. Elephant &
  Castle/Borough, Southwark (South/Central), nearest Elephant & Castle/Borough.
  southwarkplayhouse.co.uk
- **Theatre Peckham** — Producing house and training ground for young/diverse
  South-East London talent. Peckham, Southwark (South-East), nearest Peckham
  Rye. theatrepeckham.co.uk

##### Other important off-West End and mid-scale venues

- **Gate Theatre** — Storied international/experimental company (est. 1979)
  that left Notting Hill in 2022 for improved access; now itinerant/producing
  (recent shows at Chelsea's Playground Theatre) — verify current venue per
  production. Based Camden/roving (North/West). gatetheatre.co.uk
- **Marylebone Theatre** — Newer producing house near Baker Street; ambitious
  plays and premieres. Marylebone, Westminster (Central), nearest Baker Street.
  marylebonetheatre.com
- **Riverside Studios** — Hammersmith riverside arts complex; theatre, TV,
  film, dance and international work. Hammersmith (West), nearest Hammersmith.
  riversidestudios.co.uk
- **The Cockpit** — London's oldest purpose-built theatre-in-the-round (1970);
  jazz, new writing, emerging companies, scratch nights. Marylebone,
  Westminster (Central/North-West), nearest Edgware Road/Marylebone.
  thecockpit.org.uk
- **artsdepot** — Barnet's cultural hub (opened 2004); 395-seat Pentland
  Theatre + 148-seat Studio, gallery; theatre, dance, comedy, family. North
  Finchley, Barnet (North), nearest Woodside Park/West Finchley. artsdepot.co.uk
- **Bernie Grant Arts Centre** — David Adjaye-designed multi-arts centre
  (opened 2007) focused on culturally diverse/Black artists; operating but
  financially precarious (paused some activity in 2025, with a recovery plan
  announced — verify current programming). Tottenham, Haringey (North),
  nearest Seven Sisters. berniegrantcentre.co.uk
- **Chickenshed** — Long-established inclusive theatre company (est. 1974) in
  a purpose-built Southgate complex (292-seat Rayne Theatre + Studio); theatre
  made with people of all ages/abilities. Southgate, Enfield (North), nearest
  Cockfosters/Oakwood. chickenshed.org.uk
- **Alexandra Palace Theatre** — Atmospheric restored Victorian theatre with
  distressed-plaster charm; home of Mark Gatiss's annual "A Christmas Carol: A
  Ghost Story" — a strong fit for your spooky/ghost-story taste. Muswell
  Hill/Wood Green, Haringey (North), nearest Alexandra Palace (rail).
  alexandrapalace.com

#### Category 2 — Pub theatres, fringe, micro-venues and studios

##### Islington / North and North-East pub and fringe theatres

- **King's Head Theatre** — Historic pub theatre (est. 1970, once the oldest
  operating pub theatre in the UK), now in a purpose-built 220-seat space next
  to the original; joyful, irreverent, queer-focused programming. Islington
  (North), nearest Angel/Highbury & Islington. kingsheadtheatre.com
- **Hope Theatre** — Award-winning 50-seat black box above the Hope & Anchor;
  new writing and lost gems. It lost its original leadership/board in early
  2024 but Greene King committed to keeping it operating (verify current
  season). Islington (North), nearest Highbury & Islington/Angel.
  thehopetheatre.com
- **Old Red Lion Theatre** — Long-running 60-seat pub theatre; new writing and
  revivals; also a host for Nunkie's M.R. James ghost-story shows. Islington
  (North), nearest Angel. oldredliontheatre.co.uk
- **Hen & Chickens Theatre** — 54-seat theatre bar in Highbury (home to
  Unrestricted View); theatre, comedy, improv, experimental new writing.
  Highbury, Islington (North), nearest Highbury & Islington.
  thehenandchickenstheatrebar.co.uk
- **Rosemary Branch Theatre ("The Rosie")** — 60-seat theatre above a Victorian
  pub (a former music hall) by the Regent's Canal; feminist, LGBTQ+,
  family-friendly, plus puppetry, drag, cabaret and burlesque.
  Islington/Hackney border (North/East), nearest Haggerston/Angel.
  rosemarybranchtheatre.co.uk
- **Pleasance Theatre (Islington)** — London sibling of the Edinburgh Fringe
  venue; comedy, new theatre and emerging companies across multiple spaces.
  Caledonian Road, Islington (North), nearest Caledonian Road. pleasance.co.uk
- **Lion & Unicorn Theatre** — Kentish Town pub theatre; new writing, Camden
  Fringe hub, financially supported new-work seasons. Kentish Town, Camden
  (North), nearest Kentish Town. thelionandunicorntheatre.co.uk
- **Etcetera Theatre** — 42-seat black box above the Oxford Arms, Camden Town
  (est. 1986; launched careers of Simon Amstell, Al Murray, Russell Howard);
  new writing, comedy, Camden Fringe staple. Camden Town, Camden (North),
  nearest Camden Town. etceteratheatre.com
- **Upstairs at the Gatehouse** — 120–140-seat fringe venue in a refurbished
  1895 auditorium above the Gatehouse pub; reliable fringe musicals and plays.
  Highgate, Camden (North), nearest Highgate. upstairsatthegatehouse.com
- **Pentameters Theatre** — Long-running bohemian Hampstead pub theatre (est.
  1968); poetry-rooted, eclectic fringe. Hampstead, Camden (North), nearest
  Hampstead. pentameters.co.uk
- **Well Walk Theatre** — Tiny ~50-seat independent Hampstead venue (opened
  2024, founded by Zina Drouche and Dylan McNeil on Willow Road) with a
  children's bookshop and café; puppet shows, magic, silent films with live
  music — pure handmade craft energy. Won Theatre Building of the Year at The
  Stage Awards on 20 January 2025, praised as "small but perfectly formed."
  Hampstead, Camden (North), nearest Hampstead. thewellwalktheatre.com

##### Central and West pub/studio theatres

- **Finborough Theatre** — Influential 50-seat pub theatre in Earl's Court (est.
  1980, AD Neil McPherson); new British writing, rediscovered 19th/20th-century
  plays and music theatre; London Pub Theatre of the Year 2022. Earl's
  Court/West Brompton, Kensington & Chelsea (West), nearest West
  Brompton/Earl's Court. finboroughtheatre.co.uk
- **Jermyn Street Theatre** — 70-seat Off-West End studio just off Piccadilly;
  polished revivals, new plays, and Charles Court Opera's boutique pantos. St
  James's, Westminster (Central), nearest Piccadilly Circus.
  jermynstreettheatre.com
- **Drayton Arms Theatre** — 51-seat black box above a Grade II Victorian pub;
  new British and European companies seven days a week. South
  Kensington/Earl's Court, Kensington & Chelsea (West), nearest Gloucester
  Road. thedraytonarmstheatre.co.uk
- **Barons Court Theatre** — 52-seat basement theatre under the Curtains Up pub
  (run by Kibo Productions); short-run classics, new plays and afternoon magic
  shows. Barons Court/West Kensington, Hammersmith & Fulham (West), nearest
  Barons Court. baronscourttheatre.com
- **Canal Café Theatre** — 60-seat comedy/cabaret venue above the Bridge House
  in Little Venice (est. 1979); home of the record-breaking NewsRevue. Little
  Venice, Westminster (West/Central), nearest Warwick Avenue.
  canalcafetheatre.com
- **Theatre at the Tabard** — Intimate pub theatre above the Tabard in Chiswick;
  new writing and revivals. Chiswick, Hounslow (West), nearest Turnham Green.
  tabardtheatre.co.uk
- **Museum of Comedy** — Basement comedy/performance venue under St George's
  Church, Bloomsbury; stand-up, character comedy and offbeat nights.
  Bloomsbury, Camden (Central), nearest Holborn/Tottenham Court Road.
  museumofcomedy.com

##### South London pub/fringe/micro venues

- **Theatre503** — Battersea's custom-built ~63-seat new-writing hotspot above
  the Latchmere; one of the best places in London to find emerging playwrights.
  Battersea, Wandsworth (South), nearest Clapham Junction/Battersea Park.
  theatre503.com
- **White Bear Theatre** — 50-seat Kennington pub theatre (est. 1988); new
  writing and the Lost Classics Project reviving obscure plays. Kennington,
  Lambeth (South), nearest Kennington. whitebeartheatre.co.uk
- **Golden Goose Theatre** — 100-seat Camberwell venue (opened 2020, from the
  White Bear's AD); Offie-winning new work. Camberwell, Southwark (South-East),
  nearest Denmark Hill/Oval. goldengoosetheatre.co.uk
- **Bread & Roses Theatre** — Award-winning fringe theatre above the Bread &
  Roses pub in Clapham; new writing, underrepresented voices, devised and
  improvised work. Clapham, Lambeth (South), nearest Clapham North.
  breadandrosestheatre.co.uk
- **Brockley Jack Theatre (Jack Studio)** — 50-seat black box in the Brockley
  Jack pub; new writing, revivals, scratch nights, multiple Offie/Pub Theatre
  awards. Crofton Park/Brockley, Lewisham (South-East), nearest Crofton Park.
  brockleyjack.co.uk
- **The Bridge House Theatre** — Award-winning 50–60-seat black box above the
  Bridge House pub, right by Crystal Palace Park (your doorstep); new writing,
  underrepresented voices, comedy and the serial "Penge West," under AD Luke
  Adamson. Penge, Bromley (South-East), nearest Penge West.
  thebridgehousetheatre.co.uk
- **Arches Lane Theatre** — 94-seat theatre in the Battersea Power Station
  arches; reopened in 2025 (in the former Turbine Theatre space) under Kibo
  Productions, staging plays, musicals and panto. Nine Elms/Battersea,
  Wandsworth (South), nearest Battersea Power Station. archeslanetheatre.com
- **Blue Elephant Theatre** — 50-seat Camberwell fringe theatre nurturing
  emerging dance, physical theatre, puppetry and new writing — but the charity
  **surrendered its Bethwin Road building back to Southwark Council just before
  Christmas 2024** after losing its ~£70,000/year Arts Council NPO funding, and
  now intends to continue youth/early-years/family work "in new forms and
  spaces" (track as a company, not a fixed venue). Camberwell, Southwark
  (South-East), nearest Elephant & Castle/Oval. blueelephanttheatre.co.uk
- **Piehouse Co-op (formerly Matchstick Piehouse)** — Anti-capitalist,
  wheelchair-accessible DIY arts space in a Deptford railway arch; reopened
  2025 as a workers' co-op after covid rent arrears forced its 2023 closure;
  theatre, folk, jazz (Steam Down), queer cabaret, punk and radical performance.
  Deptford, Lewisham (South-East), nearest Deptford Bridge (DLR). piehouse.coop
- **Union Theatre** — Southwark fringe venue near Southwark station (est. 1998);
  strong reputation for musicals and revivals. Southwark (South/Central),
  nearest Southwark. uniontheatre.biz
- **Colour House Theatre** — ~70-seat studio in a Grade II-listed former dyeing
  house at Merton Abbey Mills craft village on the Wandle; weekend children's
  musical fairy-tales, blues club and chamber concerts. Merton Abbey Mills,
  Merton (South-West), nearest Colliers Wood/South Wimbledon.
  colourhousetheatre.co.uk
- **OSO Arts Centre** — ~130-seat community arts centre in the former sorting
  office on Barnes Green; theatre, music, comedy, cabaret and family shows
  (briefly closed Aug 2026 for a floor replacement). Barnes, Richmond
  (South-West), nearest Barnes Bridge. osoarts.org.uk

##### East London pub/fringe/micro venues

- **Arcola Theatre** — Dalston's respected two-space theatre in a former paint
  factory (est. 2000, AD Mehmet Ergen); daring international programming,
  Pay-What-You-Can nights and the annual **Grimeborn** alternative opera
  festival. Dalston, Hackney (East), nearest Dalston Junction/Dalston
  Kingsland. arcolatheatre.com
- **The Space** — Off-West End theatre in a Grade II-listed former church on the
  Isle of Dogs; year-round theatre, music, comedy and dance, with in-house
  company SpaceWorks. Isle of Dogs, Tower Hamlets (East), nearest Mudchute
  (DLR). space.org.uk
- **Ye Olde Rose & Crown Theatre** — ~70-seat pub theatre in Walthamstow; pub
  theatre, cabaret and pop-up variety (confirm domain via the pub site).
  Walthamstow, Waltham Forest (East), nearest Walthamstow Central.
  yeolderoseandcrown.co.uk
- **Half Moon Theatre** — Specialist young people's theatre in Limehouse,
  institutionally significant to youth theatre (included with that note).
  Limehouse, Tower Hamlets (East), nearest Limehouse. halfmoon.org.uk

##### Alternative opera, cabaret and music-hall-adjacent

- **Grimeborn Festival (at Arcola)** — Arcola's annual August festival
  unlocking bold, low-cost, innovative opera for young and diverse companies.
  Dalston, Hackney (East). arcolatheatre.com
- **Charles Court Opera** — Itinerant boutique chamber-opera and Gilbert &
  Sullivan company famous for its "Boutique Pantos"; performs at Wilton's
  Music Hall and Jermyn Street Theatre (no home venue — track by production).
  charlescourtopera.com
- **Underbelly Boulevard Soho** — ~200-seat cabaret/variety/theatre venue on
  the historic Boulevard Theatre site (reopened 2023 by Underbelly); circus,
  cabaret, comedy and late-night. Soho, Westminster (Central), nearest
  Piccadilly Circus. underbellyboulevard.com

##### Immersive, site-specific and folk-horror/ghost programming

- **Darkfield** — Immersive experiences in pitch-black shipping containers with
  binaural sound; unsettling, formally strange, sensory horror-adjacent work
  (touring/pop-up London locations — track via site). darkfield.org
- **Bridge Command** — Immersive spaceship-crew experience in Vauxhall where
  audiences role-play a starship bridge; playful, formally inventive,
  hands-on. Vauxhall, Lambeth (South), nearest Vauxhall. bridgecommand.co.uk
- **Nunkie Theatre Company** — Robert Lloyd Parry's one-man M.R. James
  ghost-story shows in candlelit Edwardian-storyteller style; stages around
  Christmas at the Old Red Lion and tours — a direct hit for folk-horror/ghost
  taste (track by production). nunkie.co.uk

##### Meanwhile-use and development spaces

- **Theatre Deli** — Meanwhile-use charity turning empty city spaces into
  creative venues; current main site at 107 Leadenhall Street (expanded 2025)
  plus Tower Hamlets/Hackney operations; experimental and emerging work,
  rehearsal space. City of London (Central/East), nearest Aldgate/Liverpool
  Street. theatredeli.co.uk
- **Lower Marsh Arts Club (LowMAC)** — VAULT Festival's successor (formerly The
  Glitch), officially launching 7 September 2026 in Waterloo under AD Oli
  Savage; hosts "up to three performances each night" of theatre, comedy and
  cabaret via open call-outs, plus three annual festivals (the Highlight
  fringe-previews festival in July and a new-writing festival in November) —
  the spiritual heir to VAULT's weird fringe energy. Waterloo, Lambeth
  (South/Central), nearest Waterloo/Lambeth North. vaultcreativearts.com
- **Calder Bookshop & Theatre** — Tiny literary theatre/bookshop on The Cut near
  Waterloo; readings, Beckett-leaning and European drama in miniature.
  Waterloo, Lambeth/Southwark (South/Central), nearest Southwark/Waterloo.
  calderbookshop.com

#### Recently closed / relocated — do not track as live venues

- **The Bunker** — closed 2020 (former Southwark car-park theatre).
- **Turbine Theatre** — closed 22 December 2024 after its adult panto, **but
  reopened in 2025 as Arches Lane Theatre** (now run by Kibo Productions) — so
  track the successor, listed above, not "Turbine."
- **Ovalhouse** — closed 2020; succeeded by **Brixton House**.
- **Gate Theatre (Notting Hill building)** — vacated 2022; company now
  itinerant.
- **VAULT Festival** — its final 2023 edition welcomed more than 100,000
  audience members across nearly 2,000 performances of over 500 productions;
  the festival closed in 2024 after losing its home, and is succeeded by
  **Lower Marsh Arts Club** (launching Sept 2026).
- **Matchstick Piehouse** — closed 2023; reopened 2025 as **Piehouse Co-op**.
- **Hope Theatre's original leadership model** ended in 2024, but the venue
  itself continues (see above).

#### Recommendations

1. **Seed the scraper first with the ~35 institutionally stable venues**
   (Category 1a–1d plus Arcola, Wilton's, BAC, Jacksons Lane, Little Angel) —
   these have reliable, well-structured "What's On" pages and won't churn.
2. **Add the pub/fringe tier next**, but expect volatility: pub theatres change
   hands and go dark between seasons. Re-verify Hope Theatre, Blue Elephant and
   Bernie Grant quarterly, since all three are in flux in 2024–26.
3. **Treat itinerant/company-based entries (Gate, Charles Court Opera, Nunkie,
   Darkfield, Blue Elephant) as "producer feeds" rather than fixed venues** —
   scrape the company site and follow their announced venues per show.
4. **Prioritise for your taste profile**: for weird/handmade/spooky, watch The
   Yard, CPT, BAC, Shoreditch Town Hall, Jacksons Lane, Wilton's, Punchdrunk,
   Darkfield, Bridge Command, Nunkie, Alexandra Palace, Little Angel, Puppet
   Theatre Barge, Well Walk Theatre and Piehouse Co-op most closely.
5. **Benchmark to prune**: if a venue hasn't posted a public performance in 6
   months, flag it dormant; if its domain 404s or redirects to a ticket
   reseller, mark for manual review.

#### Caveats

- Status is verified to August 2026 from venue sites, The Stage, Time Out, Arts
  Professional and Wikipedia, but small venues change fast — always re-check
  the venue's own site before relying on it.
- A few website domains (Ye Olde Rose & Crown, and LowMAC, which currently sits
  under vaultcreativearts.com) should be confirmed directly, as they trade
  under pub or parent-company sites; LowMAC will likely get its own domain
  around its 7 Sept 2026 launch.
- "Children's-only" venues are excluded, but Little Angel and Puppet Theatre
  Barge are included for their artform importance, and Well Walk / Colour House
  straddle family and adult craft programming.
- Omnibus's signature festival is the queer **96 Festival**, not ghost/spooky
  programming — noted in case that shaped expectations. For genuine
  folk-horror/ghost work, your best bets are **Nunkie Theatre Company** and
  **Alexandra Palace Theatre**'s annual ghost story.
- This list favours breadth over exhaustiveness at the micro end; further
  pub/room-above-a-pub spaces exist (e.g. Bridewell, Courtyard Theatre,
  Katzpace, Chelsea Theatre, Playground Theatre) and can be added as you prune
  and expand.
