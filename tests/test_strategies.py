"""Selector extraction against a frozen CPT card. Live sites will drift;
this just proves the strategy reads the fields we actually rely on."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "pipeline"))

from fetch import merge_runs  # noqa: E402
from strategies import extract_dated_clusters, extract_selectors  # noqa: E402


CPT_CARD = """
<html><body>
<div class="event feature subs">
  <h3 class="evtit"><a href="https://cptheatre.co.uk/whatson/SIGH-WIP">SIGH (WIP)</a></h3>
  <div class="edate">Tue 20 Oct at 7.15pm</div>
  <div class="etext">
    <div class="prods">Francisco Díaz Pacheco</div>
    <h3 class="evtit">SIGH (WIP)</h3>
    <div class="edate">Tue 20 Oct at 7.15pm</div>
    A bold physical theatre piece tagged puppetry even when the blurb never says so.
  </div>
  <div class="tags">
    <a href="https://cptheatre.co.uk/tag/Puppetry">Puppetry</a>
    <a href="https://cptheatre.co.uk/tag/Queer">Queer</a>
  </div>
</div>
</body></html>
"""


def test_cpt_selectors_get_blurb_tags_and_dates(tmp_path, monkeypatch):
    cache = tmp_path / "page.html"
    cache.write_text(CPT_CARD)

    def fake_get(url, use_cache=True, **kw):
        return CPT_CARD

    monkeypatch.setattr("fetch.polite_get", fake_get)

    venue = {
        "whats_on_url": "https://cptheatre.co.uk/Whats-On",
        "selectors": {
            "show_card": ".event.subs",
            "title": "h3.evtit",
            "dates": ".edate",
            "credits": ".prods",
            "blurb": ".etext",
            "blurb_strip": "h3, .edate, .prods",
            "tags": ".tags a",
            "link": "h3.evtit a",
        },
    }
    rows = extract_selectors(venue, use_cache=True)
    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == "SIGH (WIP)"
    assert row["first_date"] == "2026-10-20"
    assert "bold physical theatre" in row["description"]
    assert row["venue_tags"] == ["Puppetry", "Queer"]
    assert row["url"].endswith("/whatson/SIGH-WIP")


# The National's what's-on page mixes its three auditoria with West End
# transfers, tours, cinema screenings and streaming. Only the auditoria are
# events you can go to at the National.
MIXED_HOUSE = """
<html><body>
<div class="card"><h3 class="t">Some Woman</h3>
  <div class="d">7 October - 21 November 2026</div>
  <div class="loc">Dorfman Theatre -</div>
  <a href="/productions/some-woman/">book</a></div>
<div class="card"><h3 class="t">Inter Alia</h3>
  <div class="d">10 November 2026 - 21 February 2027</div>
  <div class="loc">Music Box Theatre</div>
  <a href="/productions/inter-alia/">book</a></div>
<div class="card"><h3 class="t">Our Town</h3>
  <div class="d">Now streaming</div>
  <div class="loc">Online</div>
  <a href="/productions/our-town/">book</a></div>
</body></html>
"""


def test_space_allow_keeps_only_the_venues_own_rooms(monkeypatch):
    monkeypatch.setattr("fetch.polite_get", lambda url, use_cache=True, **kw: MIXED_HOUSE)
    venue = {
        "whats_on_url": "https://www.nationaltheatre.org.uk/whats-on/",
        "selectors": {
            "show_card": ".card",
            "title": "h3.t",
            "dates": ".d",
            "space": ".loc",
            "space_allow": ["Olivier", "Lyttelton", "Dorfman"],
            "link": "a",
        },
    }
    rows = extract_selectors(venue, use_cache=True)
    assert [r["title"] for r in rows] == ["Some Woman"]
    assert rows[0]["space"] == "Dorfman Theatre -"


TOURING = """
<html><body>
<div class="card"><h3 class="t">Persephone</h3><div class="d">25th - 27th September</div>
  <a href="https://www.punchdrunk.com/work/persephone/">go</a></div>
<div class="card"><h3 class="t">Sleep No More</h3><div class="d">1st Dec 2016 - 31st Aug 2029</div>
  <a href="https://www.punchdrunk.com/work/sleep-no-more-shanghai/">go</a></div>
</body></html>
"""


def test_exclude_drops_the_overseas_productions(monkeypatch):
    """A company's own site lists every city. Matched on title and url."""
    monkeypatch.setattr("fetch.polite_get", lambda url, use_cache=True, **kw: TOURING)
    venue = {
        "whats_on_url": "https://www.punchdrunk.com/whats-on/",
        "selectors": {
            "show_card": ".card",
            "title": "h3.t",
            "dates": ".d",
            "link": "a",
            "exclude": ["shanghai"],
        },
    }
    rows = extract_selectors(venue, use_cache=True)
    assert [r["title"] for r in rows] == ["Persephone"]
    # and the ordinals still parse
    assert rows[0]["first_date"] == "2026-09-25"
    assert rows[0]["last_date"] == "2026-09-27"


def test_per_performance_cards_collapse_to_one_run():
    """The Courtyard lists a card per night, each with its own booking link,
    so Serious Money arrived ten times. The run is the union of the dates."""
    rows = [
        {"title": "Serious Money", "first_date": "2026-09-10",
         "last_date": "2026-09-10", "description": "short", "price_min": 18.0},
        {"title": "Serious Money", "first_date": "2026-09-08",
         "last_date": "2026-09-08", "description": "a much longer synopsis",
         "price_min": 14.0},
        {"title": "serious  money", "first_date": "2026-09-21",
         "last_date": "2026-09-21", "description": None},
        {"title": "Serious Money - Preview", "first_date": "2026-09-07",
         "last_date": "2026-09-07", "description": None},
    ]
    out = merge_runs(rows)
    assert len(out) == 2
    run = out[0]
    assert (run["first_date"], run["last_date"]) == ("2026-09-08", "2026-09-21")
    assert run["description"] == "a much longer synopsis"
    assert run["price_min"] == 14.0
    # a preview is its own title and stays separate
    assert out[1]["title"] == "Serious Money - Preview"


def test_dated_clusters_pair_a_wix_date_with_its_heading():
    """Wix puts each show in its own absolutely-placed box. The date, the
    title and the show-page link share a parent; nothing else is stable."""
    html = """
    <html><body>
      <div>
        <h5>Dandelions and Poppy</h5>
        <h5>1st - 3rd September</h5>
        <h5>7pm</h5>
        <a href="/dandelionsandpoppy">More info</a>
        <a href="https://www.ticketsource.com/x">Tickets</a>
      </div>
      <div>
        <h5>Does My Privilege Look Big In This?</h5>
        <h5>4th - 6th September</h5>
        <a href="/doesmyprivilege">More info</a>
      </div>
    </body></html>
    """
    venue = {"whats_on_url": "https://www.thehopetheatre.com/what-s-on"}

    def fake_get(url, use_cache=True, **kw):
        return html

    import fetch
    orig = fetch.polite_get
    fetch.polite_get = fake_get
    try:
        rows = extract_dated_clusters(venue)
    finally:
        fetch.polite_get = orig
    assert [r["title"] for r in rows] == [
        "Dandelions and Poppy",
        "Does My Privilege Look Big In This?",
    ]
    assert rows[0]["first_date"] == "2026-09-01"
    assert rows[0]["last_date"] == "2026-09-03"
    assert rows[0]["url"].endswith("/dandelionsandpoppy")
    # a heading that is only a time is not a title
    assert all("7pm" not in r["title"] for r in rows)


def test_dated_clusters_prefer_the_title_matching_link():
    """Wix date widgets live in a shared parent that already contains the
    previous show's href. Walking up from the date would attach Iceberg
    to We'll Always Have Paris; walking up from the heading does not."""
    html = """
    <html><body>
      <div class="page">
        <div>
          <h5>We'll Always Have Paris</h5>
          <a href="/whatson/well-always-have-paris">More info</a>
        </div>
        <div>15 Sep - 3 Oct</div>
        <div>
          <h5>Iceberg Right Ahead</h5>
          <a href="/whatson/iceberg-right-ahead">More info</a>
        </div>
        <div>20 Oct - 31 Oct</div>
      </div>
    </body></html>
    """
    venue = {"whats_on_url": "https://www.whitebeartheatre.co.uk/whatson"}
    import fetch
    orig = fetch.polite_get
    fetch.polite_get = lambda url, use_cache=True, **kw: html
    try:
        rows = extract_dated_clusters(venue)
    finally:
        fetch.polite_get = orig
    by_title = {r["title"]: r["url"] for r in rows}
    assert by_title["We'll Always Have Paris"].endswith(
        "/whatson/well-always-have-paris")
    assert by_title["Iceberg Right Ahead"].endswith(
        "/whatson/iceberg-right-ahead")
    rows = [{"title": "Yerma", "first_date": "2026-09-08", "last_date": "2026-09-09"},
            {"title": "Girls", "first_date": "2026-09-10", "last_date": "2026-09-11"}]
    assert len(merge_runs(rows)) == 2


# Young Vic puts festival promos in .c-billboard, not .c-event-card.
# Comma selectors have to read both shapes without the card's Book Now
# button stealing the festival link.
YOUNG_VIC = """
<html><body>
<div class="c-event-card">
  <a class="c-event-card__cover-link" href="/whats-on/art-cure/">Art Cure</a>
  <div class="c-event-card__time"><span>27 SEP 2026</span></div>
  <h3 class="c-event-card__title">Art Cure</h3>
  <span class="c-event-card__event-venue">Main House</span>
  <a class="c-btn c-btn--instance-list" href="/whats-on/art-cure/#instance-list">Book Now</a>
</div>
<div class="c-billboard">
  <h2 class="c-heading c-heading--h2">Shedinburgh Festival</h2>
  <div class="c-paragraph"><p><b>19 SEP</b> <b>-</b> <b>10 OCT 2026</b></p></div>
  <a class="c-btn c-btn--primary" href="/shedinburgh/">Explore the Festival</a>
</div>
</body></html>
"""


def test_young_vic_reads_cards_and_festival_billboard(monkeypatch):
    monkeypatch.setattr("fetch.polite_get", lambda url, use_cache=True, **kw: YOUNG_VIC)
    venue = {
        "whats_on_url": "https://www.youngvic.org/whats-on/",
        "selectors": {
            "show_card": ".c-event-card, .c-billboard",
            "title": "h3.c-event-card__title, h2.c-heading",
            "dates": ".c-event-card__time, .c-paragraph",
            "space": ".c-event-card__event-venue",
            "link": "a.c-event-card__cover-link, a.c-btn--primary",
        },
    }
    rows = extract_selectors(venue)
    by_title = {r["title"]: r for r in rows}
    assert set(by_title) == {"Art Cure", "Shedinburgh Festival"}
    assert by_title["Art Cure"]["first_date"] == "2026-09-27"
    assert by_title["Art Cure"]["url"].endswith("/whats-on/art-cure/")
    assert by_title["Shedinburgh Festival"]["first_date"] == "2026-09-19"
    assert by_title["Shedinburgh Festival"]["last_date"] == "2026-10-10"
    assert by_title["Shedinburgh Festival"]["url"].endswith("/shedinburgh/")


def test_venue_horizon_stretches_one_house():
    from datetime import date
    from fetch import venue_horizon
    today = date(2026, 9, 7)
    assert venue_horizon(today, 8, {}) == "2026-11-02"
    assert venue_horizon(today, 8, {"lookahead_weeks": 12}) == "2026-11-30"


# Jacksons Lane's /whats-on/ hub is a cookie/JS shell. All Performances is
# ordinary WordPress cards.
JACKSONS_LANE = """
<html><body>
<div class="event_item">
  <a href="https://www.jacksonslane.org.uk/events/by-a-thread/"><h6>Circus</h6></a>
  <h5>By A Thread: One Fell Swoop Circus</h5>
  <div class="post_meta">07 Sep 2026 - 08 Sep 2026</div>
  <div class="event_desc"><p>Seven acrobats. One web of rope.</p></div>
  <a class="btn" href="https://www.jacksonslane.org.uk/events/by-a-thread/">More Info</a>
  <a class="btn" href="https://www.jacksonslane.org.uk/events/by-a-thread/#book">Book Tickets</a>
</div>
</body></html>
"""


def test_jacksons_lane_all_performances_cards(monkeypatch):
    monkeypatch.setattr("fetch.polite_get", lambda url, use_cache=True, **kw: JACKSONS_LANE)
    venue = {
        "whats_on_url": "https://www.jacksonslane.org.uk/whats-on/all-performances/",
        "selectors": {
            "show_card": ".event_item",
            "title": "h5",
            "dates": ".post_meta",
            "blurb": ".event_desc",
            "tags": ".event_category h6",
            "link": "a.btn",
        },
    }
    rows = extract_selectors(venue)
    assert len(rows) == 1
    row = rows[0]
    assert row["title"].startswith("By A Thread")
    assert row["first_date"] == "2026-09-07"
    assert row["last_date"] == "2026-09-08"
    assert "acrobats" in row["description"]
    assert row["url"].endswith("/events/by-a-thread/")
    assert "#book" not in row["url"]


RUMOURS = """
<html><body>
<h6>Immersive/Interactive Shows</h6>
<section class="wixui-column-strip">
  <h2>Grease: The Immersive Movie Musical</h2>
  <p>Danny and Sandy in 1950s America.</p>
  <p>📍 Battersea Park</p>
  <p>🕒 Until 13th September 2026</p>
  <p>🎟️ Book via <a href="https://greasetheimmersivemoviemusical.com">grease</a></p>
</section>
<h6>IMMERSIVE AT HOME EXPERIENCES</h6>
<section class="wixui-column-strip">
  <h2>CLAWS by Candle House Collective</h2>
  <p>A phone-call thriller.</p>
  <p>📍 At Home</p>
  <p>🕒 Ongoing</p>
  <p>🎟️ Book via <a href="https://candlehousecollective.com/tickets/claws">claws</a></p>
</section>
<h6>Outside of London</h6>
<section class="wixui-column-strip">
  <h2>THE CRYSTAL MAZE: LIVE EXPERIENCE</h2>
  <p>📍 Castlefield, Manchester</p>
  <p>🕒 Ongoing</p>
  <p>🎟️ Book via <a href="https://the-crystal-maze.com/manchester">maze</a></p>
</section>
</body></html>
"""


def test_immersive_rumours_splits_home_and_skips_outside(monkeypatch):
    from strategies import extract_immersive_rumours
    monkeypatch.setattr("fetch.polite_get", lambda url, use_cache=True, **kw: RUMOURS)
    rows = extract_immersive_rumours({
        "whats_on_url": "https://www.immersiverumours.com/current-shows-london",
    })
    by = {r["title"]: r for r in rows}
    assert set(by) == {
        "Grease: The Immersive Movie Musical",
        "CLAWS by Candle House Collective",
    }
    assert "venue_id" not in by["Grease: The Immersive Movie Musical"]
    assert by["CLAWS by Candle House Collective"]["venue_id"] == "home"
    assert by["CLAWS by Candle House Collective"]["first_date"] is not None
    assert by["Grease: The Immersive Movie Musical"]["url"].endswith(
        "greasetheimmersivemoviemusical.com")
