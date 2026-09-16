"""What polite_get is allowed to serve from cache, and for how long.

Rendered fetches use a separate cache key so an empty JS shell cannot be
reused as a listing page, listings expire long before show pages, and a
render that never finished is not cached at all.
"""
import hashlib
import os
import pathlib
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "pipeline"))

import browser  # noqa: E402
import fetch  # noqa: E402


def test_rendered_cache_key_is_distinct(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "CACHE", tmp_path)
    monkeypatch.setattr(fetch, "DELAY", 0)

    def fake_get(url, headers=None, timeout=None):
        class R:
            text = "<html>shell</html>"
            def raise_for_status(self):
                return None
        return R()

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    monkeypatch.setattr("browser.rendered_get",
                        lambda url, wait_for=None: "<html>hydrated</html>")

    url = "https://example.com/whats-on"
    shell = fetch.polite_get(url, use_cache=False, render=False)
    live = fetch.polite_get(url, use_cache=False, render=True)
    assert shell == "<html>shell</html>"
    assert live == "<html>hydrated</html>"
    digest = hashlib.sha1(url.encode()).hexdigest()
    assert (tmp_path / f"{digest}.html").exists()
    assert (tmp_path / f"{digest}.rendered.html").exists()


def test_render_for_flips_polite_get(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "CACHE", tmp_path)
    monkeypatch.setattr(fetch, "DELAY", 0)
    seen = []

    def fake_rendered(url, wait_for=None):
        seen.append(wait_for)
        return "<html>ok</html>"

    monkeypatch.setattr("browser.rendered_get", fake_rendered)
    venue = {"fetch_method": "rendered", "render_wait": ".event-card"}
    with fetch.render_for(venue):
        fetch.polite_get("https://example.com/a", use_cache=False)
    assert seen == [".event-card"]
    # outside the context it must not touch Chromium
    class R:
        text = "<html>plain</html>"
        def raise_for_status(self):
            return None
    monkeypatch.setattr(fetch.requests, "get", lambda *a, **k: R())
    assert fetch.polite_get("https://example.com/b", use_cache=False) == "<html>plain</html>"


def test_a_listing_goes_stale_long_before_a_show_page(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "CACHE", tmp_path)
    monkeypatch.setattr(fetch, "DELAY", 0)
    calls = []

    class R:
        text = "<html>fresh</html>"
        def raise_for_status(self):
            return None

    monkeypatch.setattr(fetch.requests, "get",
                        lambda url, **k: (calls.append(url), R())[1])

    url = "https://example.com/whats-on"
    key = tmp_path / (hashlib.sha1(url.encode()).hexdigest() + ".html")
    key.write_text("<html>stale</html>")
    three_days = time.time() - 3 * 86400
    os.utime(key, (three_days, three_days))

    assert fetch.polite_get(url, max_age=fetch.DETAIL_MAX_AGE) == "<html>stale</html>"
    assert calls == []
    assert fetch.polite_get(url, max_age=fetch.LISTING_MAX_AGE) == "<html>fresh</html>"
    assert calls == [url]


def test_an_unfinished_render_is_not_cached(tmp_path, monkeypatch):
    """Otherwise a venue reads as having no shows, and stays that way."""
    monkeypatch.setattr(fetch, "CACHE", tmp_path)
    monkeypatch.setattr(fetch, "DELAY", 0)

    def never_renders(url, wait_for=None):
        raise browser.RenderWaitTimeout(f"{wait_for!r} never appeared at {url}")

    monkeypatch.setattr("browser.rendered_get", never_renders)
    venue = {"fetch_method": "rendered", "render_wait": ".event-card"}
    with pytest.raises(browser.RenderWaitTimeout):
        with fetch.render_for(venue):
            fetch.polite_get("https://example.com/whats-on", use_cache=False)
    assert list(tmp_path.iterdir()) == []
