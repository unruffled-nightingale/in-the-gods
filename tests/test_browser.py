"""Rendered fetches use a separate cache key so an empty JS shell cannot
be reused as a listing page."""
import hashlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "pipeline"))

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
