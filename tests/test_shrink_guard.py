"""Shrink guard: a bad live fetch must not replace a good extract."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "pipeline"))

from build_extract import shrink_guard  # noqa: E402


def _extract(path, events):
    path.write_text(json.dumps({"events": events}))


def test_refuses_when_count_halves(tmp_path):
    old = tmp_path / "old.json"
    _extract(old, [{"venue_id": "a", "title": str(i)} for i in range(10)])
    new = [{"venue_id": "a", "title": "only"}]
    reason = shrink_guard(new, old)
    assert reason and "below" in reason


def test_refuses_when_a_previous_venue_vanishes(tmp_path):
    old = tmp_path / "old.json"
    _extract(old, [
        {"venue_id": "arcola", "title": "Fire"},
        {"venue_id": "wiltons", "title": "Caligari"},
    ])
    new = [{"venue_id": "arcola", "title": "Fire"}, {"venue_id": "arcola", "title": "Screw"}]
    reason = shrink_guard(new, old)
    assert reason and "wiltons" in reason


def test_allows_growth(tmp_path):
    old = tmp_path / "old.json"
    _extract(old, [{"venue_id": "arcola", "title": "Fire"}])
    new = [
        {"venue_id": "arcola", "title": "Fire"},
        {"venue_id": "almeida", "title": "New"},
    ]
    assert shrink_guard(new, old) is None
