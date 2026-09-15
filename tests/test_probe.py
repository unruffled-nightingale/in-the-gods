"""Probe strategy recommendation — the mapping fetch validation depends on."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "pipeline"))

from probe import recommend_strategy, find_sanity_project  # noqa: E402


def test_cpt_jsonld_without_url_prefers_selectors():
    assert recommend_strategy({
        "url": "https://cptheatre.co.uk/Whats-On",
        "jsonld_events": 29,
        "jsonld_has_url": False,
        "card_candidates": [("event.subs", 29)],
        "sanity_project": None,
        "wp_rest": [],
        "js_rendered_suspect": False,
    }) == "selectors"


def test_jsonld_with_url_wins():
    assert recommend_strategy({
        "url": "https://example.com/whats-on",
        "jsonld_events": 8,
        "jsonld_has_url": True,
        "card_candidates": [("card", 8)],
        "sanity_project": None,
        "wp_rest": [],
        "js_rendered_suspect": False,
    }) == "jsonld"


def test_yard_sanity_beats_empty_shell():
    assert recommend_strategy({
        "url": "https://www.theyardtheatre.co.uk/whats-on",
        "jsonld_events": 0,
        "jsonld_has_url": False,
        "card_candidates": [],
        "sanity_project": "vs3yf10f",
        "wp_rest": [],
        "js_rendered_suspect": True,
    }) == "sanity"


def test_spektrix_does_not_win_over_cards():
    """Arcola/Wilton's: box office ≠ listings."""
    assert recommend_strategy({
        "url": "https://www.arcolatheatre.com/whats-on/",
        "jsonld_events": 0,
        "jsonld_has_url": False,
        "card_candidates": [("listing-item", 9)],
        "sanity_project": None,
        "wp_rest": [],
        "js_rendered_suspect": False,
        "platforms": ["spektrix", "wordpress"],
    }) == "selectors"


def test_sanity_project_parsed_from_cdn_url():
    html = 'src="https://cdn.sanity.io/images/vs3yf10f/production/abc.jpg"'
    assert find_sanity_project(html) == "vs3yf10f"
