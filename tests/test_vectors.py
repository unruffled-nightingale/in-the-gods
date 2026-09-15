"""Filter-then-rank search with fake vectors. No MiniLM in CI."""
import os
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from server.vectors import (  # noqa: E402
    SearchUnavailable,
    event_chunks,
    event_id,
    event_text,
    filter_indices,
    l2_normalize,
    load_venues,
    rank,
    search,
    split_copy,
)


def _event(i, title, tags, venue="soho-theatre"):
    return {
        "venue_id": venue,
        "title": title,
        "byline": title,
        "description": title,
        "first_date": "2026-09-20",
        "last_date": "2026-09-26",
        "url": f"https://example.com/{i}",
        "tags": tags,
    }


EVENTS = [
    _event(0, "Brechtian puppet horror", ["puppetry", "theatre"]),
    _event(1, "Kids yoga morning", ["class"], venue="artsdepot"),
    _event(2, "Macabre contemporary dance", ["dance"]),
    _event(3, "Standard Friday standup", ["stand-up"]),
]


def _matrix():
    raw = np.array([
        [1.0, 0.0],
        [0.0, 1.0],
        [0.95, 0.05],
        [0.1, 0.9],
    ], dtype=np.float32)
    return l2_normalize(raw)


SPOOKY = np.array([1.0, 0.0], dtype=np.float32)


def test_event_id_matches_frontend_padding():
    assert event_id(0) == "e000"
    assert event_id(12) == "e012"
    assert event_id(925) == "e925"


def test_event_text_joins_title_tags_copy():
    text = event_text(EVENTS[0])
    assert "Brechtian puppet horror" in text
    assert "puppetry" in text


def test_event_chunks_include_place_and_type():
    chunks = event_chunks(
        {
            "title": "Long After the Labyrinth",
            "tags": ["theatre"],
            "byline": "A horned shadow looms.",
            "description": "Told via text, movement and shadow-play.",
        },
        venue={"name": "Upstairs at the Gatehouse", "area": "Highgate"},
    )
    where = chunks[0]
    assert "Long After the Labyrinth" in where
    assert "Upstairs at the Gatehouse" in where
    assert "Highgate" in where
    assert "theatre" in where
    joined = "\n".join(chunks)
    assert "shadow-play" in joined
    assert "puppetry" in joined
    assert "macabre" in joined


def test_event_chunks_split_long_copy():
    chunks = event_chunks({
        "title": "Long After the Labyrinth",
        "tags": ["theatre"],
        "byline": "A horned shadow looms.",
        "description": (
            "Told via shadow-play. Les Enfants Terribles and a long list of companies. "
            * 8
        ),
    })
    assert any("horned shadow" in c for c in chunks)
    assert any("shadow-play" in c and "Les Enfants" not in c for c in chunks)
    assert any("puppetry" in c for c in chunks)


def test_split_copy_keeps_short_paragraphs():
    assert split_copy("One para.\n\nTwo para.") == ["One para.", "Two para."]


def test_filter_indices_tags_and_venue():
    assert filter_indices(EVENTS, tags=["dance"]) == [2]
    assert filter_indices(EVENTS, venue="artsdepot") == [1]
    assert filter_indices(EVENTS, tags=["theatre"], venue="artsdepot") == []


def test_rank_prefers_the_close_vector():
    hits = rank(_matrix(), SPOOKY, [0, 1, 2, 3], 3)
    ids = [i for i, _ in hits]
    assert ids[0] == 0
    assert ids[1] == 2
    assert 1 not in ids[:2]


def test_rank_sums_phrases_so_place_and_type_both_count():
    matrix = l2_normalize(np.array([
        [1.0, 0.0],
        [0.0, 1.0],
        [0.72, 0.72],
    ], dtype=np.float32))
    owners = np.array([0, 1, 2], dtype=np.int32)
    both = l2_normalize(np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32))
    hits = rank(matrix, both, [0, 1, 2], 3, owners=owners)
    assert hits[0][0] == 2
    assert hits[0][1] > hits[1][1]
    assert hits[0][1] > hits[2][1]


def test_rank_max_over_chunks_of_one_show():
    matrix = l2_normalize(np.array([
        [1.0, 0.0],
        [0.0, 1.0],
        [0.2, 0.8],
    ], dtype=np.float32))
    owners = np.array([0, 0, 1], dtype=np.int32)
    q = np.array([0.0, 1.0], dtype=np.float32)
    hits = rank(matrix, q, [0, 1], 2, owners=owners)
    assert hits[0][0] == 0
    assert hits[0][1] > hits[1][1]


def test_search_query_orders_by_cosine():
    hits = search(
        "spooky handmade puppets",
        limit=3,
        events=EVENTS,
        matrix=_matrix(),
        query_vec=SPOOKY,
    )
    assert [h.id for h in hits] == ["e000", "e002", "e003"]
    assert hits[0].event["title"] == "Brechtian puppet horror"
    assert hits[0].score > hits[1].score > hits[2].score


def test_search_filters_then_ranks():
    hits = search(
        "macabre",
        tags=["dance"],
        events=EVENTS,
        matrix=_matrix(),
        query_vec=SPOOKY,
    )
    assert [h.id for h in hits] == ["e002"]


def test_search_empty_query_keeps_extract_order():
    hits = search("", tags=["theatre"], events=EVENTS, matrix=_matrix())
    assert [h.id for h in hits] == ["e000"]
    assert hits[0].score == 0.0


def test_search_two_query_vecs_surfaces_both_poles():
    both = l2_normalize(np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32))
    hits = search(
        "stacked ask",
        limit=4,
        events=EVENTS,
        matrix=_matrix(),
        query_vecs=both,
    )
    ids = {h.id for h in hits}
    assert "e000" in ids
    assert "e001" in ids


def test_search_chunk_owners_unique_event_ids():
    matrix = l2_normalize(np.array([
        [1.0, 0.0],
        [0.0, 1.0],
        [0.1, 0.9],
        [0.95, 0.05],
    ], dtype=np.float32))
    owners = np.array([0, 0, 1, 2], dtype=np.int32)
    hits = search(
        "place and type",
        limit=4,
        events=EVENTS[:3],
        matrix=matrix,
        owners=owners,
        query_vecs=l2_normalize(np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)),
    )
    ids = [h.id for h in hits]
    assert ids[0] == "e000"
    assert len(ids) == len(set(ids))
    assert "e001" in ids
    assert "e002" in ids


def test_search_rejects_row_mismatch():
    with pytest.raises(SearchUnavailable):
        search(
            "x",
            events=EVENTS,
            matrix=np.zeros((2, 2), dtype=np.float32),
            query_vec=SPOOKY,
        )


def test_search_rejects_owner_mismatch():
    with pytest.raises(SearchUnavailable):
        search(
            "x",
            events=EVENTS,
            matrix=_matrix(),
            owners=np.array([0, 1], dtype=np.int32),
            query_vec=SPOOKY,
        )


def test_load_venues_reads_area_and_overrides(tmp_path):
    p = tmp_path / "venues.yaml"
    p.write_text(
        "venues:\n"
        "- id: foo\n"
        "  name: Foo House\n"
        "  location:\n"
        "    area: Highgate\n"
        "- id: arcola\n"
        "  name: Arcola Theatre\n"
        "  location:\n"
        "    area: Dalston\n"
    )
    v = load_venues(p)
    assert v["foo"] == {"name": "Foo House", "area": "Highgate"}
    assert v["arcola"]["area"].startswith("Dalston")
    assert "E8" in v["arcola"]["area"]


@pytest.mark.skipif(not os.environ.get("LIVE_EMBED"), reason="LIVE_EMBED not set")
def test_live_embed_roundtrip():
    from server.vectors import embed_texts
    vecs = embed_texts(["a puppet horror", "a yoga class"])
    assert vecs.shape[0] == 2
    assert vecs.shape[1] > 0
    q = embed_texts(["puppet horror"])[0]
    assert float(vecs[0] @ q) > float(vecs[1] @ q)
