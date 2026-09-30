"""--include / --exclude choose which venues a refresh crawls."""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from fetch import select_ids  # noqa: E402

ALL = ["arcola", "donmar", "royal-court", "wiltons"]


def test_default_is_every_venue():
    assert select_ids(ALL) == ALL


def test_include_narrows():
    assert select_ids(ALL, include="donmar, wiltons") == ["donmar", "wiltons"]


def test_exclude_drops():
    assert select_ids(ALL, exclude="donmar,royal-court") == ["arcola", "wiltons"]


def test_include_then_exclude():
    assert select_ids(ALL, include="arcola,donmar", exclude="donmar") == ["arcola"]


def test_unknown_id_is_an_error():
    with pytest.raises(SystemExit, match="donmr"):
        select_ids(ALL, exclude="donmr")


def _build(tmp_path, excluded):
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"events": [
        {"venue_id": "arcola", "title": "Fire"},
        {"venue_id": "donmar", "title": "Hamlet"},
    ]}))
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps({
        "window": ["2026-09-30", "2026-11-25"], "excluded": excluded,
        "events": [{"venue_id": "arcola", "title": "Fire",
                    "first_date": "2026-10-01", "last_date": "2026-10-10",
                    "url": "https://arcolatheatre.com/fire"}]}))
    venues = tmp_path / "venues.yaml"
    venues.write_text("venues: []\n")
    return subprocess.run(
        [sys.executable, str(ROOT / "pipeline" / "build_extract.py"),
         "--raw", str(raw), "--out", str(tmp_path / "out.json"),
         "--compare", str(old), "--venues", str(venues)],
        capture_output=True, text=True, cwd=ROOT)


def test_excluded_venue_does_not_trip_the_empty_venue_check(tmp_path):
    assert _build(tmp_path, ["donmar"]).returncode == 0


def test_crawled_venue_at_zero_still_trips_it(tmp_path):
    r = _build(tmp_path, [])
    assert r.returncode == 2 and "donmar" in r.stderr
