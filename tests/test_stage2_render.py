"""Stage 2 renders a show page without waiting for the listing selector."""
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "pipeline"))

import fetch  # noqa: E402


def _fake_browser(monkeypatch, seen):
    mod = types.ModuleType("browser")

    def rendered_get(url, wait_for=None, timeout_ms=0):
        seen.append(wait_for)
        return "<html><body><p>A show.</p></body></html>"

    mod.rendered_get = rendered_get
    monkeypatch.setitem(sys.modules, "browser", mod)


def test_show_page_does_not_wait_for_listing_cards(monkeypatch, tmp_path):
    seen = []
    _fake_browser(monkeypatch, seen)
    monkeypatch.setattr(fetch, "CACHE", tmp_path)
    venue = {"id": "the-place", "fetch_method": "rendered",
             "render_wait": "a.c-event-card"}
    with fetch.render_for(venue):
        fetch.stage2("https://stage2-test.invalid/events/a-show", use_cache=False)
    assert seen == [None]


def test_listing_still_waits_for_its_cards(monkeypatch, tmp_path):
    seen = []
    _fake_browser(monkeypatch, seen)
    monkeypatch.setattr(fetch, "CACHE", tmp_path)
    venue = {"id": "the-place", "fetch_method": "rendered",
             "render_wait": "a.c-event-card"}
    with fetch.render_for(venue):
        fetch.polite_get("https://stage2-test.invalid/whats-on", use_cache=False)
    assert seen == ["a.c-event-card"]
