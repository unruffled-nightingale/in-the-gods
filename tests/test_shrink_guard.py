"""Shrink guard: a bad live fetch must not replace a good extract."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "pipeline"))

from build_extract import seasonal_ids, shrink_guard  # noqa: E402


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


def test_seasonal_venue_may_go_dark(tmp_path):
    old = tmp_path / "old.json"
    _extract(old, [
        {"venue_id": "arcola", "title": "Fire"},
        {"venue_id": "regents-park", "title": "Evita"},
    ])
    new = [{"venue_id": "arcola", "title": "Fire"}, {"venue_id": "arcola", "title": "Screw"}]
    assert shrink_guard(new, old, seasonal={"regents-park"}) is None


def test_unflagged_venue_at_zero_still_fails_beside_a_seasonal_one(tmp_path):
    old = tmp_path / "old.json"
    _extract(old, [
        {"venue_id": "arcola", "title": "Fire"},
        {"venue_id": "wiltons", "title": "Caligari"},
        {"venue_id": "regents-park", "title": "Evita"},
    ])
    new = [{"venue_id": "arcola", "title": "Fire"}, {"venue_id": "arcola", "title": "Screw"}]
    reason = shrink_guard(new, old, seasonal={"regents-park"})
    assert reason and "wiltons" in reason and "regents-park" not in reason


def test_seasonal_ids_reads_the_flag(tmp_path):
    reg = tmp_path / "venues.yaml"
    reg.write_text("venues:\n- id: regents-park\n  seasonal: true\n- id: arcola\n")
    assert seasonal_ids(reg) == {"regents-park"}
