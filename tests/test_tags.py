"""Form tags on extract records — not vibe keywords."""
from datetime import date
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "pipeline"))

from build_extract import build, tag  # noqa: E402

EXTRACT_KEYS = {
    "venue_id", "title", "byline", "description", "first_date", "last_date",
    "url", "tags",
}


def test_default_is_theatre():
    assert tag("Fire Fire", "By John Webber", "A two-hander about climate.") == ["theatre"]


def test_musical_from_prose():
    assert tag("The Producers", None, "this outrageous musical has audiences roaring") == ["musical"]


def test_opera_not_operation():
    assert tag("Operation Mincemeat", None, "a wartime deception") == ["theatre"]
    assert tag("Giulio Cesare", None, "Handel's opera seria at studio scale") == ["opera"]


def test_dance_not_movement():
    assert tag("Midnight", None, "tensions rise at the start of a historic movement") == ["theatre"]
    assert tag("Screendance", None, "a new dance work for the studio") == ["dance"]


def test_stand_up_hyphenation():
    assert tag("Late Night", None, "an hour of stand-up") == ["stand-up"]
    assert tag("Open Mic", None, "standup from new acts") == ["stand-up"]


def test_concert():
    assert tag("Songbook", None, "an evening of live music") == ["concert"]


def test_scraped_cpt_comedy_is_stand_up():
    assert tag("Friday Night", None, "a night of jokes", ["Comedy"]) == ["stand-up"]


def test_scraped_musical_tag():
    assert tag("New Work", None, "a workshop showing", ["Music/Musical"]) == ["musical"]


def test_scraped_circus_tag():
    assert tag("By A Thread", None, "seven acrobats", ["Circus"]) == ["circus"]


def test_extract_shape_drops_internal_fields():
    records, dropped, _ = build([{
        "venue_id": "arcola",
        "title": "Fire Fire",
        "credits": "By John Webber",
        "space": "Studio 2",
        "first_date": "2026-09-09",
        "last_date": "2026-10-03",
        "url": "https://example.com/fire",
        "description": "A two-hander about climate activism.",
        "venue_tags": ["Puppetry"],
        "needs_detail_fetch": False,
    }], window=(date(2026, 9, 6), date(2026, 11, 1)))
    assert dropped == []
    assert len(records) == 1
    assert set(records[0]) == EXTRACT_KEYS
    assert records[0]["tags"] == ["theatre"]
    # no byline on the row, so the opening of the copy becomes one
    assert records[0]["byline"] == "A two-hander about climate activism."
    assert records[0]["description"] is None


def test_raw_dump_keeps_per_venue_lookahead():
    """Fetch already windowed the rows. Don't drop a Young Vic autumn opener
    just because it sits past the dump's global 8-week horizon."""
    events = [{
        "venue_id": "young-vic",
        "title": "Eurotrash",
        "first_date": "2026-11-13",
        "last_date": "2027-01-09",
        "url": "https://www.youngvic.org/whats-on/eurotrash/",
        "description": "A new play.",
    }]
    window = (date(2026, 9, 7), date(2026, 11, 2))
    kept, dropped, _ = build(events, window, apply_window=False)
    assert [r["title"] for r in kept] == ["Eurotrash"]
    assert dropped == []
    gone, dropped, _ = build(events, window)
    assert gone == []
    assert dropped[0][2] == "outside window"
