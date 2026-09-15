"""Haiku Ask order with a fake model. No API key in CI."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from server.ask import apply_order, compact, expand_queries, retrieve, rerank, split_query
from server.vectors import Hit


def _hit(i, title, tags=None, **extra):
    event = {
        "venue_id": extra.get("venue", "soho-theatre"),
        "title": title,
        "byline": extra.get("byline", title),
        "description": extra.get("description", title),
        "tags": tags or ["theatre"],
    }
    return Hit(f"e{i:03d}", 1.0 - i * 0.1, event)


HITS = [
    _hit(0, "Brechtian puppet horror", ["puppetry", "theatre"]),
    _hit(1, "Kids yoga morning", ["class"]),
    _hit(2, "Macabre contemporary dance", ["dance"]),
    _hit(3, "Friday night concert", ["concert"]),
]


def test_apply_order_puts_named_first_and_keeps_the_rest():
    ordered = apply_order(HITS, ["e002", "e000", "e999", "e002"])
    assert [h.id for h in ordered] == ["e002", "e000", "e001", "e003"]


def test_apply_order_empty_or_unknown_is_junk():
    assert apply_order(HITS, []) is None
    assert apply_order(HITS, ["e999"]) is None


def test_compact_truncates_and_keeps_id():
    long = _hit(0, "X", description="d" * 500, venue="no-such-house")
    row = compact([long])[0]
    assert row["id"] == "e000"
    assert row["d"].endswith("…")
    assert len(row["d"]) == 401
    assert "where" not in row


def test_compact_includes_place_when_present():
    hit = _hit(0, "X", venue="arcola")
    hit.event["venue_name"] = "Arcola Theatre"
    hit.event["venue_area"] = "Dalston, E8"
    row = compact([hit])[0]
    assert row["where"] == "Arcola Theatre · Dalston, E8"


def test_rerank_reorders_and_keeps_every_hit():
    def order(_system, payload):
        assert payload["q"] == "adult puppet horror, not kids"
        assert [c["id"] for c in payload["candidates"]] == [
            "e000", "e001", "e002", "e003",
        ]
        return ["e000", "e002"]

    out = rerank("adult puppet horror, not kids", HITS, call=order)
    assert [h.id for h in out] == ["e000", "e002", "e001", "e003"]
    assert out[0].event["title"] == "Brechtian puppet horror"
    assert {h.id for h in out} == {h.id for h in HITS}


def test_rerank_empty_ids_falls_back():
    out = rerank("ice hockey", HITS, call=lambda *_: [])
    assert [h.id for h in out] == ["e000", "e001", "e002", "e003"]


def test_rerank_falls_back_when_call_raises():
    def boom(*_a, **_k):
        raise RuntimeError("nope")

    out = rerank("spooky", HITS, call=boom)
    assert [h.id for h in out] == ["e000", "e001", "e002", "e003"]


def test_rerank_falls_back_on_junk_ids():
    out = rerank("spooky", HITS, call=lambda *_: ["nope"])
    assert [h.id for h in out] == ["e000", "e001", "e002", "e003"]


def test_rerank_skips_haiku_when_query_empty_or_one_hit():
    calls = []

    def order(*_a, **_k):
        calls.append(1)
        return ["e000"]

    assert rerank("", HITS, call=order) is HITS
    assert rerank("spooky", HITS[:1], call=order) == HITS[:1]
    assert calls == []


def test_expand_queries_keeps_original_and_adds_neighbours():
    out = expand_queries(
        "spooky puppets",
        call=lambda *_: ["shadow play", "spooky puppets", "gothic visual theatre"],
    )
    assert out[0] == "spooky puppets"
    assert out.count("spooky puppets") == 1
    assert "shadow play" in out
    assert "gothic visual theatre" in out


def test_expand_queries_falls_back_to_original():
    def boom(*_a, **_k):
        raise RuntimeError("nope")
    assert expand_queries("macabre", call=boom) == ["macabre"]
    assert expand_queries("") == []


def test_split_query_keeps_place_and_type_clauses():
    parts = split_query("spooky, puppetry in Dalston")
    assert "spooky" in parts
    assert "puppetry" in parts
    assert "Dalston" in parts


def test_expand_queries_splits_place_and_type_when_haiku_down():
    def boom(*_a, **_k):
        raise RuntimeError("nope")
    out = expand_queries("spooky, puppetry in Dalston", call=boom)
    assert out[0] == "spooky, puppetry in Dalston"
    assert "spooky" in out
    assert "puppetry" in out
    assert "Dalston" in out


def test_retrieve_passes_owners_and_expanded_phrases():
    import numpy as np
    from server.vectors import l2_normalize

    events = [
        {
            "venue_id": "arcola",
            "title": "Handmade shadows",
            "byline": "A horned shadow.",
            "description": "Shadow-play in Dalston.",
            "tags": ["puppetry", "theatre"],
        },
        {
            "venue_id": "artsdepot",
            "title": "Kids yoga",
            "byline": "Stretch.",
            "description": "Family class.",
            "tags": ["class"],
        },
    ]
    matrix = l2_normalize(np.array([
        [1.0, 0.0],
        [0.9, 0.1],
        [0.0, 1.0],
    ], dtype=np.float32))
    owners = np.array([0, 0, 1], dtype=np.int32)
    spooky = np.array([1.0, 0.0], dtype=np.float32)
    out = retrieve(
        "puppetry in Dalston",
        limit=2,
        expand=lambda *_: ["shadow-play Highgate"],
        order=lambda *_: ["e000", "e001"],
        events=events,
        matrix=matrix,
        owners=owners,
        query_vec=spooky,
    )
    assert [h.id for h in out] == ["e000", "e001"]
