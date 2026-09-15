"""
Date parser tests.

These are not decorative. Two of them (the 'four digit year' and
'cross year range' cases) were written after the parser got those
wrong in a way that produced plausible-looking dates rather than an
obvious crash. Venue listings phrase dates a dozen ways and a silent
misparse puts a show in the wrong month in the digest.

    python -m pytest tests/ -q
"""
import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "pipeline"))

from fetch import parse_date_range  # noqa: E402


@pytest.mark.parametrize("text,expected", [
    # --- the common shapes ---
    ("11 Sep - 10 Oct 2026",            ("2026-09-11", "2026-10-10")),
    ("2 - 5 Sep 2026",                  ("2026-09-02", "2026-09-05")),
    ("6 Oct 2026",                      ("2026-10-06", "2026-10-06")),

    # --- weekday names must not contribute day numbers ---
    ("Wed 9 September to Sat 3 October 2026",
                                        ("2026-09-09", "2026-10-03")),
    ("Thurs 8 - Sat 17 Oct 2026 at 7:15pm",
                                        ("2026-10-08", "2026-10-17")),

    # --- REGRESSION: '2026' was being read as day 20 then day 26 ---
    ("1 - 30 November 2026",            ("2026-11-01", "2026-11-30")),
    ("2026 season: 4 Dec",              ("2026-12-04", "2026-12-04")),

    # --- REGRESSION: cross-year ranges anchored on the wrong year ---
    ("3 Dec 2026 - 2 Jan 2027",         ("2026-12-03", "2027-01-02")),
    ("16 Dec - 4 Jan 2026",             ("2026-12-16", "2027-01-04")),

    # --- times and am/pm must not leak in as days ---
    ("12 Oct 2026, 7.30pm",             ("2026-10-12", "2026-10-12")),
    ("5 Nov 2026 at 8pm",               ("2026-11-05", "2026-11-05")),

    # --- month forward-fill from the trailing month ---
    ("22 - 24 Oct 2026",                ("2026-10-22", "2026-10-24")),

    # --- all-caps months (Young Vic cards) ---
    ("3 SEP - 24 OCT",                  ("2026-09-03", "2026-10-24")),
    ("27 SEP 2026",                     ("2026-09-27", "2026-09-27")),
    ("22 OCT - 21 NOV",                 ("2026-10-22", "2026-11-21")),

    # --- month before day (Albany cards: 'Fri September 25, 2026') ---
    ("Fri September 25, 2026",          ("2026-09-25", "2026-09-25")),
    ("September 25, 2026",              ("2026-09-25", "2026-09-25")),

    # --- ordinals (Punchdrunk writes '25th - 27th September') ---
    ("25th - 27th September",           ("2026-09-25", "2026-09-27")),
    ("1st Oct 2026",                    ("2026-10-01", "2026-10-01")),
    ("3rd - 22nd Nov 2026",             ("2026-11-03", "2026-11-22")),

    # --- REGRESSION: a named closing year must be used, not inferred.
    # Barbican runs long installations: '10 Feb 2025 - 1 Jan 2027' was
    # collapsing to 2026 because the end reused the opening year and then
    # rolled forward by exactly one.
    ("Mon 10 Feb 2025 - Fri 1 Jan 2027", ("2025-02-10", "2027-01-01")),
    ("6 Sep 2026 - 4 Jan 2028",         ("2026-09-06", "2028-01-04")),

    # --- month named, no day (Troubadour open runs, ENO 'June 2027') ---
    ("Now booking until February 2027", ("TODAY", "2027-02-28")),
    ("until February 2027",             ("TODAY", "2027-02-28")),
    ("March 2028",                      ("2028-03-01", "2028-03-31")),
    ("June 2027",                       ("2027-06-01", "2027-06-30")),
])
def test_parses(text, expected):
    from datetime import date
    start, end = expected
    if start == "TODAY":
        start = date.today().isoformat()
    assert parse_date_range(text) == (start, end)


@pytest.mark.parametrize("text", [
    None,
    "",
    "Coming soon",
    "Dates TBC",
    "Every Thursday",          # no day number at all
])
def test_unparseable_returns_none(text):
    """Returning (None, None) is correct. Guessing is not."""
    assert parse_date_range(text) == (None, None)


def test_default_year_used_when_absent():
    assert parse_date_range("6 Oct", default_year=2027) == ("2027-10-06",
                                                            "2027-10-06")


def test_explicit_year_beats_default():
    """A year in the text always wins over the caller's hint."""
    assert parse_date_range("6 Oct 2026", default_year=2030) == ("2026-10-06",
                                                                 "2026-10-06")


def test_month_abbreviated_with_a_full_stop():
    """Piehouse renders dates through Django's date filter: 'Sept. 9, 2026'."""
    assert parse_date_range("Sept. 9, 2026, 7 p.m.") == ("2026-09-09", "2026-09-09")
    assert parse_date_range("Sep. 9, 2026") == ("2026-09-09", "2026-09-09")
    assert parse_date_range("Oct. 1, 2026 - Oct. 5, 2026") == ("2026-10-01",
                                                               "2026-10-05")
    # the unabbreviated forms must keep working
    assert parse_date_range("September 9, 2026") == ("2026-09-09", "2026-09-09")
    assert parse_date_range("9 Sept 2026") == ("2026-09-09", "2026-09-09")


def test_implausible_runs_are_rejected():
    """Finborough's permanently-open online archive pages publish JSON-LD end
    dates of 2028 and 2050, which sailed through the 8-week window because a
    range containing today always overlaps it."""
    from fetch import plausible_run
    assert plausible_run("2026-09-02", "2026-09-26")
    # a Barbican installation is long but real, and must survive
    assert plausible_run("2025-02-10", "2027-01-01")
    assert not plausible_run("2025-08-15", "2050-08-15")
    assert not plausible_run("2022-02-01", "2028-12-30")
    # backwards is not a run either
    assert not plausible_run("2026-10-01", "2026-09-01")
    # a missing end is not yet a problem; the window filter handles it
    assert plausible_run("2026-09-02", None)


def test_until_uses_today_as_start():
    """'Until 24 Oct' is a close date, not a one-night on the 24th."""
    from datetime import date
    today = date.today().isoformat()
    assert parse_date_range("Until 24 Oct") == (today, "2026-10-24")
    assert parse_date_range("Until Sat 3 Oct") == (today, "2026-10-03")
