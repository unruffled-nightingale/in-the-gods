"""render_wait must wait for the listing, not something already on the page."""
import pathlib

import yaml
from bs4 import BeautifulSoup

REGISTRY = pathlib.Path(__file__).resolve().parents[1] / "data" / "venues.yaml"


def _venue(vid):
    return next(v for v in yaml.safe_load(REGISTRY.read_text())["venues"] if v["id"] == vid)


def test_hen_and_chickens_waits_past_the_logo():
    # Before the events load, the page's only a.group is a logo link. Waiting on
    # bare a.group returned then, and the venue reported ok with 0 shows.
    shell = BeautifulSoup('<a class="group" href="https://uvff.co.uk">UVFF</a>', "html.parser")
    loaded = BeautifulSoup('<a class="group" href="/events/mara"><h3>Mara</h3></a>', "html.parser")
    wait = _venue("hen-and-chickens")["render_wait"]
    assert not shell.select(wait)
    assert loaded.select(wait)
