"""The Sanity API is JSON: fetch it plainly even for a js_rendered venue."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "pipeline"))

import fetch  # noqa: E402
from strategies import extract_sanity  # noqa: E402


def test_sanity_query_is_never_rendered(monkeypatch):
    seen = []

    def fake_get(url, use_cache=True, render=None, max_age=0):
        seen.append(render)
        return json.dumps({"result": []})

    monkeypatch.setattr(fetch, "polite_get", fake_get)
    venue = {"id": "the-yard", "fetch_method": "js_rendered",
             "whats_on_url": "https://www.theyardtheatre.co.uk/whats-on",
             "sanity": {"project_id": "x"}}
    with fetch.render_for(venue):
        assert extract_sanity(venue, use_cache=False) == []
    assert seen == [False]
