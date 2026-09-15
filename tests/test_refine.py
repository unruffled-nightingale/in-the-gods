"""Post-extract Haiku refine: drop / retag."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "pipeline"))

from datetime import date  # noqa: E402

from refine import (  # noqa: E402
    apply_verdict, clamp_verdict, event_fp, is_english_listing, prune_cache,
    refine,
)

ALLOWED = {
    "theatre", "musical", "stand-up", "comedy", "concert", "opera", "dance",
    "circus", "immersive", "puppetry", "cabaret", "magic", "spoken-word",
    "talk", "class", "social", "exhibition",
}

TASTE = {
    "model": "claude-haiku-4-5",
    "batch_size": 20,
    "allowed_tags": sorted(ALLOWED),
    "allowed_set": ALLOWED,
    "drop": "Drop films and yoga classes.",
    "interests": "Star puppetry.",
    "hash": "test-taste",
}


def _event(**kw):
    row = {
        "venue_id": "artsdepot",
        "title": "Yoga",
        "byline": "A weekly class.",
        "description": "Improve flexibility.",
        "first_date": "2026-09-10",
        "last_date": "2026-12-10",
        "url": "https://example.com/yoga",
        "tags": ["theatre"],
    }
    row.update(kw)
    return row


def test_clamp_drops_unknown_tags_and_defaults_theatre():
    v = clamp_verdict({"keep": True, "tags": ["spooky", "film"], "star": True}, ALLOWED)
    assert v["tags"] == ["theatre"]
    assert v["star"] is True


def test_clamp_no_star_when_dropped():
    v = clamp_verdict({"keep": False, "tags": ["theatre"], "star": True}, ALLOWED)
    assert v["star"] is False


def test_apply_verdict_drops_and_never_prestars():
    assert apply_verdict(_event(), {"keep": False, "tags": [], "star": False}) is None
    kept = apply_verdict(_event(title="Fire", prestar=True), {
        "keep": True, "tags": ["puppetry"], "star": True,
    })
    assert kept["tags"] == ["puppetry"]
    assert "prestar" not in kept


def test_refine_uses_cache_and_skips_api():
    events = [_event(title="Cached Yoga")]
    fp = event_fp(events[0], TASTE["hash"])
    cache = {fp: {"keep": False, "tags": [], "star": False, "why": "yoga class"}}
    calls = []

    def boom(*_a, **_k):
        calls.append(1)
        raise AssertionError("should not call the model")

    kept, stats = refine(events, TASTE, client=None, cache=cache, call=boom)
    assert kept == []
    assert stats["dropped"] == 1
    assert stats["cache_hits"] == 1
    assert calls == []


def test_refine_batches_and_retags(monkeypatch):
    play = _event(
        venue_id="arcola",
        title="The Table",
        byline="A puppet tragedy.",
        description="Two puppeteers, no speech.",
        tags=["theatre"],
    )
    yoga = _event()
    film = _event(
        venue_id="kiln",
        title="Brassed Off screening",
        byline="A screening of the film plus Q&A.",
        description="Following the screening, a Q&A.",
        tags=["theatre"],
    )

    def fake_call(_client, _model, _system, batch):
        out = []
        for row in batch:
            title = row["t"]
            if "Yoga" in title:
                out.append({"i": row["i"], "keep": False, "tags": [], "star": False})
            elif "screening" in title.lower():
                out.append({"i": row["i"], "keep": False, "tags": [], "star": False})
            else:
                out.append({
                    "i": row["i"], "keep": True,
                    "tags": ["puppetry"], "star": True,
                })
        return out

    kept, stats = refine(
        [play, yoga, film], TASTE, client=object(), cache={}, call=fake_call,
    )
    assert [e["title"] for e in kept] == ["The Table"]
    assert kept[0]["tags"] == ["puppetry"]
    assert "prestar" not in kept[0]
    assert stats["dropped"] == 2
    assert stats["api_calls"] == 1
    assert stats["api_events"] == 3


def test_prune_keeps_seen_even_when_last_seen_is_old():
    today = date(2026, 9, 8)
    cache = {
        "live": {"keep": True, "tags": ["theatre"], "star": False,
                 "last_seen": "2026-01-01"},
        "gone": {"keep": False, "tags": [], "star": False,
                 "last_seen": "2026-01-01"},
        "recent": {"keep": False, "tags": [], "star": False,
                   "last_seen": "2026-08-01"},
        "orphan": {"keep": False, "tags": [], "star": False},
    }
    kept, n = prune_cache(cache, {"live"}, today, weeks=12)
    assert set(kept) == {"live", "recent"}
    assert n == 2
    assert "gone" not in kept
    assert "orphan" not in kept


def test_limit_style_prune_is_skipped_by_not_calling_it():
    # --limit must not prune; this just documents the membership rule.
    today = date(2026, 9, 8)
    cache = {"other": {"keep": True, "tags": ["theatre"], "star": False,
                       "last_seen": "2026-09-01"}}
    kept, n = prune_cache(cache, set(), today, weeks=12)
    assert kept == cache
    assert n == 0


def test_turkish_listing_is_not_english():
    row = _event(
        venue_id="the-cockpit",
        title="Ben Çoktan Gidersiniz Sanmiştim - Tom Pain",
        byline=(
            "Bir adam, sözlük, Thom Pain, yalnızlık, çocukluk, bir arı ya da "
            "kelimeler, bencillik, aşk, kaybetmek, çok aşk, çok kaybetmek ve "
            "bir köpek; kocaman gözleri olan bir köpek."
        ),
        description=(
            "Çok severken kaybedenlerin oyunu BEN ÇOKTAN GİDERSİNİZ SANMIŞTIM, "
            "gerçek hayatın, insan ve hayvan arasındaki ilişkinin yakın bir "
            "örneği. Tek kelimeyle kusursuzluk diye tarif edilen bir aşkın "
            "içinde çok severken gidebilmek ya da romantizmin jargonunun "
            "dengeli olmak, beraber zaman geçirmek, dışarı çıkmak olarak "
            "belirlendiği bir dünyada bu kelimelerdeki acıyı anlamak için "
            "ciddi sarsılmalar, görme kaybı ve bir yıl evden çıkmama "
            "gerekliliği."
        ),
    )
    assert is_english_listing(row) is False


def test_english_listing_is_english():
    row = _event(
        title="Fire Fire",
        byline="A two-hander about climate activism, class and grief.",
        description=(
            "Paige and Eddie meet on opposing sides at a country park and "
            "keep colliding until they join forces. The play is set around "
            "a protest in South Essex."
        ),
    )
    assert is_english_listing(row) is True


def test_short_title_only_is_kept():
    assert is_english_listing(_event(
        title="Femina", byline=None, description=None,
    )) is True


def test_italian_title_english_synopsis_is_kept():
    row = _event(
        title="Giulio Cesare in Egitto",
        byline="Music by George Frideric Handel",
        description=(
            "Handel's opera seria staged in the Arcola's larger studio as "
            "part of the festival. Baroque opera at studio scale and studio "
            "prices."
        ),
    )
    assert is_english_listing(row) is True


def test_bilingual_english_lead_is_kept():
    row = _event(
        title="Chi Stand-up Comedy Special",
        byline="Hi! I'm Chi, a stand-up comedian from China. This is my first special.",
        description=(
            "I'm bringing you my best performance. "
            "In Chinese: 你好，我是池子，一名中國脫口秀演員。"
        ),
    )
    assert is_english_listing(row) is True


def test_refine_drops_non_english_without_calling_haiku():
    row = _event(
        venue_id="the-cockpit",
        title="Ben Çoktan Gidersiniz Sanmiştim - Tom Pain",
        byline=(
            "Bir adam, sözlük, Thom Pain, yalnızlık, çocukluk, bir arı ya da "
            "kelimeler, bencillik, aşk, kaybetmek, çok aşk, çok kaybetmek ve "
            "bir köpek; kocaman gözleri olan bir köpek."
        ),
        description=(
            "Çok severken kaybedenlerin oyunu BEN ÇOKTAN GİDERSİNİZ SANMIŞTIM, "
            "gerçek hayatın, insan ve hayvan arasındaki ilişkinin yakın bir "
            "örneği. Tek kelimeyle kusursuzluk diye tarif edilen bir aşkın "
            "içinde çok severken gidebilmek ya da romantizmin jargonunun "
            "dengeli olmak, beraber zaman geçirmek, dışarı çıkmak olarak "
            "belirlendiği bir dünyada bu kelimelerdeki acıyı anlamak için "
            "ciddi sarsılmalar, görme kaybı ve bir yıl evden çıkmama "
            "gerekliliği."
        ),
    )
    calls = []

    def boom(*_a, **_k):
        calls.append(1)
        raise AssertionError("should not call the model")

    kept, stats = refine(
        [row, _event(title="Yoga", prestar=True)], TASTE, client=None, cache={}, call=None,
    )
    assert "Tom Pain" not in " ".join(e["title"] for e in kept)
    assert stats["dropped"] == 1
    assert calls == []
    assert "prestar" not in kept[0]
