#!/usr/bin/env python3
"""Normalise crawler rows into the In the Gods extract.

Each event is: venue_id, title, byline, description, first_date, last_date,
url, tags. The byline is the grab — the opening sentence or two of the show
copy. The description is the paragraphs after it. tags are form only
(theatre, musical, stand-up, concert, opera, dance); default theatre.
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from fetch import split_hook

# Window used when building from the built-in curated seed (offline reproduction
# of the committed extract). Live runs take their window from the crawler dump.
SEED_WINDOW = (date(2026, 9, 5), date(2026, 11, 5))

# title, byline, space, start, end, slug, source_tags, description
RAW = {
    "arcola": {
        "base": "https://www.arcolatheatre.com/event/",
        "one_stage": False,
        "shows": [
            ("Giulio Cesare in Egitto", "Music by George Frideric Handel", "Studio 1",
             "2026-09-02", "2026-09-05", "giulio-cesare-in-egitto", [],
             "Handel's opera seria staged in the Arcola's larger studio as part of "
             "the Grimeborn festival's tail end. Baroque opera at studio scale and "
             "studio prices."),
            ("Fire Fire", "By John Webber, dir. Jennifer Tang", "Studio 2",
             "2026-09-09", "2026-10-03", "fire-fire", [],
             "A two-hander about climate activism, class and grief set around a "
             "protest in South Essex. Paige, a middle-class queer activist of "
             "Nigerian heritage, and Eddie, a retired oil worker attending a "
             "memorial for his brother, meet on opposing sides at a country park "
             "and keep colliding until they join forces. Webber drew on growing up "
             "in Thurrock, once a primary UK oil refining hub."),
            ("The Turn of the Screw",
             "Adapted by Morgan Lloyd Malcolm from Henry James, dir. Nicky Allpress",
             "Studio 1", "2026-09-11", "2026-10-10", "the-turn-of-the-screw", [],
             "A governess takes a post caring for two children in a remote house and "
             "becomes convinced they are being haunted by sinister forces. Billed as "
             "shadows, secrets and creeping dread. Arcola/Blackeyed Theatre, ahead of "
             "a UK tour — the ambiguity about whether she sees anything at all is the "
             "whole point, and a 100-seat studio is the right room for it."),
            ("The Banality of Evil: Hannah Arendt, France, 1940",
             "Written and directed by Julia Pascal", "Studio 2",
             "2026-10-08", "2026-11-07", "the-banality-of-evil", [],
             "Examines exile and survival through the stories of three women "
             "imprisoned during the Second World War, framed by Arendt's idea of "
             "evil as bureaucratic rather than monstrous. World premiere."),
            ("The Master Builder",
             "Ibsen, in a version by David Edgar, dir. Mehmet Ergen", "Studio 1",
             "2026-10-16", "2026-11-21", "the-master-builder", [],
             "Olivier-nominated Greg Hicks as architect Halvard Solness, in a play "
             "about ambition, legacy and the fear of irrelevance. Ibsen's strangest "
             "late work — half psychological realism, half something closer to a "
             "haunting."),
        ],
        "excluded": [("Workshop: The Dramatic Question", "workshop, not a production")],
    },
    "wiltons": {
        "base": "https://wiltons.org.uk/whats-on/",
        "one_stage": False,
        "shows": [
            ("The Elixir of Love", "Donizetti; Waterperry Opera / Charles Court Opera",
             None, "2026-09-08", "2026-09-19", "the-elixir-of-love", [],
             "Donizetti's romantic comedy sung in a new English translation, in the "
             "world's oldest surviving grand music hall. Small-scale opera in a room "
             "with charring still visible in the rafters."),
            ("Private Peaceful", "Simon Reade, from Michael Morpurgo", None,
             "2026-09-21", "2026-09-23", "private-peaceful", [],
             "Stage adaptation of Morpurgo's First World War novel."),
            ("FLOP! The Best Songs from the Worst Musicals", "Arthur Hull, London debut",
             None, "2026-09-24", "2026-09-26", "flop", [],
             "A fast-paced love letter to musical theatre, celebrating Broadway and "
             "West End shows that were critically panned, misunderstood or financial "
             "disasters. Failure as a subject rather than an accident."),
            ("Tim Key: Loganberry", "Comedy", None,
             "2026-09-28", "2026-10-03", "tim-key-loganberry", [],
             "Key's deadpan poetry-and-monologue act — closer to performance art than "
             "stand-up, and a good fit for the room."),
            ("The Cabinet of Dr. Caligari", "Silent film with new live piano score",
             None, "2026-10-06", "2026-10-06", "cabinet-of-dr-caligari", [],
             "Robert Wiene's 1920 German Expressionist horror — painted shadows, "
             "impossible angles, a somnambulist and an unreliable narrator — with a "
             "brand-new live piano score. One night only. The single strongest match "
             "on this list for the handmade/spooky register."),
            ("Incendiary: Samuel Pepys in Words and Music", "Hambletts", None,
             "2026-10-07", "2026-10-08", "incendiary", [],
             "Pepys's diaries — plague, fire, and the domestic pettiness in between — "
             "set to music."),
            ("Phil Ellis: Bath Mat", "Avalon", None,
             "2026-10-10", "2026-10-10", "bath-mat", [],
             "Comedy. Ellis works in the anti-comedy/deliberate-shambles tradition."),
            ("A Brief Case of Crazy",
             "Shoddy Theatre & Skedaddle w/ York Theatre Royal", None,
             "2026-10-12", "2026-10-14", "a-brief-case-of-crazy", [],
             "A silent love story with a very loud heart — physical comedy in the Mr "
             "Bean lineage, which won Rowan Armitt-Brewster Best Staging at the 2026 "
             "Offies. Reviewers called it an evolution of silent film humour into the "
             "21st century, with sharp timing and unexpected depth. Pure craft, no "
             "dialogue."),
            ("Romeo and Juliet", "Duke's Theatre Co, original music by Rob Millett",
             None, "2026-10-15", "2026-10-17", "romeo-and-juliet", [],
             "A bold new staging with original music."),
            ("OneTrackMinds", "VERYFINE", None,
             "2026-10-19", "2026-10-19", "onetrackminds", [],
             "Returning storytelling night in which speakers unpack a single song "
             "that changed their life."),
            ("Cally Beaton: Namaste Motherf*ckers", "Gag Reflex", None,
             "2026-10-20", "2026-10-20", "namaste", [], "Stand-up."),
            ("Players' Theatre 90th Birthday Music Hall Gala", "Variety gala", None,
             "2026-10-21", "2026-10-21", "players-theatre-90th", [],
             "The Players' Theatre marks 90 years with a music hall gala — actual "
             "Victorian variety repertoire performed in an actual Victorian music "
             "hall. A living-history oddity more than a normal night out."),
            ("Pea Green Boat", "By Stewart Lee", None,
             "2026-10-22", "2026-10-22", "pea-green-boat", [],
             "Presented by Sally Homer and John MacKay. Lee writing for the stage "
             "rather than performing — worth a look on curiosity alone."),
            ("Soho Songs", "Barb Jungr, Cahoots Theatre Company", None,
             "2026-10-23", "2026-10-24", "soho-songs", [],
             "Jungr leads a company of performers through songs of Soho."),
            ("Stoker Wilde", "Eric Rosen, music by Rodney Bush, dir. Séimí Campbell",
             None, "2026-10-27", "2026-10-31", "stoker-wilde", [],
             "World premiere glam-rock musical concert uncovering the rivalry and "
             "connection between Bram Stoker and Oscar Wilde. Halloween week, "
             "Dracula's author, and glam rock, in a Victorian music hall — deranged "
             "in exactly the right direction."),
            ("Hooray for Hollywood", "Liza Pulman and Joe Stilgoe", None,
             "2026-11-03", "2026-11-07", "hooray-for-hollywood", [],
             "Highfield Productions; songbook cabaret."),
        ],
        "excluded": [
            ("Wiesenthal", "ended 5 Sep, effectively past"),
            ("The Signalman", "3 Sep, outside window"),
        ],
    },
    "southwark-playhouse": {
        "base": "https://southwarkplayhouse.co.uk/productions/",
        "one_stage": False,
        "shows": [
            ("Bury the Hatchet", None, "Borough / The Little",
             "2026-08-12", "2026-09-05", "bury-the-hatchet", [], None),
            ("Night City", "Max Wilkinson, dir. Ebenezer Bamgboye",
             "Borough / The Little", "2026-09-09", "2026-10-03", "night-city", [],
             "An epic modern drama with sharp, dark humour, incorporating movement "
             "and an electric soundtrack across three intersecting stories about "
             "London's gig economy. A driver, a care worker and a waitress pushed to "
             "their limits — late-night rides and invisible labour, based on real "
             "experiences. An ode to the city's unseen workforce."),
            ("Twenty Thousand Streets Under the Sky", "Patrick Hamilton",
             "Borough / The Large", "2026-09-10", "2026-10-17",
             "twenty-thousand-streets-under-the-sky", [],
             "Hamilton's interwar trilogy of Fitzrovia pub life, obsession and quiet "
             "desperation. Same author as Rope and Gaslight — the macabre is in the "
             "DNA even when nobody dies."),
            ("Dog Mom", None, "Borough / The Little",
             "2026-10-14", "2026-11-07", "dog-mom", [], None),
            ("Memoriam", "Noga Flaishon", "Borough / The Large",
             "2026-10-22", "2026-11-21", "memoriam", [],
             "Picked up from the Royal Court's Open Submissions Festival, selected "
             "from roughly 4,000 scripts submitted annually."),
        ],
        "excluded": [("Mona Loser", "workshop presentation")],
    },
    "camden-peoples-theatre": {
        "base": "https://cptheatre.co.uk/whatson/",
        "one_stage": True,
        "trailing_slash": False,   # CPT slugs take NO trailing slash
        "shows": [
            ("Sound Strokes", "Cross-cultural music", None, "2026-09-05", "2026-09-06",
             "Sound-Strokes-A-Harmonious-Blend-of-Chinese-and-Scottish-Music",
             ["Hire", "Live Art", "Music/Musical"],
             "Blends guzheng, harp and bodhrán/percussion in an intimate performance "
             "of reimagined folk melodies, original works and improvisation, where "
             "Chinese and Celtic traditions meet in a poetic musical dialogue."),
            ("Good Grief (WIP)", "Joe Mulcrone", None, "2026-09-26", "2026-09-27",
             "Good-Grief", ["Comedy", "Solo Performance"],
             "When Marc dies unexpectedly, something arrives to help. A surreal "
             "tragicomedy about family, loss and the strange business of carrying on."),
            ("Tripping Out (WIP)", "Compact Disc", None, "2026-10-06", "2026-10-06",
             "Tripping-Out-WIP",
             ["History", "Live Art", "Technology", "Work In Progress"],
             "Part history play. Part mind control experiment. Part LSD light show. "
             "Enter the world of MK ULTRA and the CIA — what can you be made to do?"),
            ("Standing Ovation (WIP)", "XO", None, "2026-10-06", "2026-10-06",
             "Standing-Ovation-wip",
             ["Comedy", "Poetry", "Puppetry", "Solo Performance", "Work In Progress"],
             "Ever wanted to laugh at a disabled person? Miggy tries to keep you "
             "entertained for an hour whilst managing PIP assessments, broken lifts "
             "and overbearing allies. Tagged by the venue as puppetry."),
            ("How to Create a Life (WIP)", "Francesca D'Souza", None,
             "2026-10-07", "2026-10-07", "How-to-Create-a-Life-WIP",
             ["Feminist", "Solo Performance", "Work In Progress"],
             "Warm, irreverent and occasionally unhinged verbatim work-in-progress "
             "with a big heart, asking the big questions in life."),
            ("We Talk About Death In The Swimming Pool (WIP)", "Beth Bowden / SALTHOUSE",
             None, "2026-10-07", "2026-10-07",
             "We-Talk-About-Death-In-The-Swimming-Pool-WIP",
             ["Physical Theatre", "Poetry", "Work In Progress"],
             "A new multidisciplinary theatre work exploring the political and "
             "personal dimensions of grief, illness and end-of-life choice."),
            ("Trans People Are Awful", "Beth Sitek / Ros Watt / CPT", None,
             "2026-10-08", "2026-10-17", "Trans-People-Are-Awful-26",
             ["Solo Performance"],
             "Transitioning's hard, finding the right parts is harder. In a garage in "
             "North-East Scotland, a young trans guy invites you to witness his "
             "genius in hunting cis-men for body parts. Body horror played for "
             "comedy — the closest thing CPT has to folk horror this season."),
            ("I AM JOHNNY", "Tessa Parr", None, "2026-10-08", "2026-10-09",
             "I-AM-JOHNNY",
             ["Comedy", "Feminist", "Live Art", "Poetry", "Queer", "Spoken Word"],
             "Fresh off the FlixBus from Edinburgh Fringe, white thirty-something "
             "poet-manchild Johnny returns for two more chances to battle the "
             "absurdities of his complex existence."),
            ("Queer Revolutionary Singalong", "Black Smock Band / Daedalus", None,
             "2026-10-10", "2026-10-10", "Queer-Revolutionary-Singalong-26",
             ["Music/Musical", "Queer"],
             "Fiery folk tunes and leftie singalong classics, from Bread and Roses to "
             "Solidarity Forever. Bring your singing voice and your revolutionary "
             "fervour."),
            ("Default (WIP)", "Yaren-Medine Kesen", None, "2026-10-13", "2026-10-13",
             "Default-WIP", ["Solo Performance", "Work In Progress"],
             "mundane. human. questions. probably no answers."),
            ("Eat Me (WIP)", "ANTS Theatre", None, "2026-10-13", "2026-10-13",
             "Eat-Me-WIP", ["International", "Work In Progress"],
             "The Royal Tastebuds will now determine your right to remain. What will "
             "you cook? The King is waiting. He's salivating. A cooking-contest "
             "format turned into an immigration nightmare."),
            ("Pretty Ugly", "Theo Chen", None, "2026-10-14", "2026-10-16",
             "Pretty-Ugly",
             ["International", "Music/Musical", "Queer", "Solo Performance"],
             "Military service in Singapore, Sondheim and family history intertwine "
             "to determine why Theo feels so ugly, and whether it matters that they "
             "do."),
            ("SIGH (WIP)", "Francisco Díaz Pacheco", None, "2026-10-20", "2026-10-20",
             "SIGH-WIP",
             ["Puppetry", "Queer", "Solo Performance", "Work In Progress"],
             "A bold physical theatre piece where one phone call breaks Patíco's "
             "routine, exposing queer identity, family rejection, desire and the "
             "legacy of unresolved trauma. Venue-tagged as puppetry — the blurb "
             "doesn't say so, which is exactly why the venue's own tags are worth "
             "trusting over inference."),
            ("Deen over Dunya (WIP)", "Amina Aaliya Beg / James Baker", None,
             "2026-10-20", "2026-10-20", "Deen-over-Dunya-WIP",
             ["Climate Change", "Music/Musical", "Work In Progress"],
             "A musical exploring the commercialisation of Islam and "
             "environmentalism from an Islamic point of view."),
            ("The Only Brown Deaf Man in England", "Fuse Theatre / Mercury Colchester",
             None, "2026-10-21", "2026-11-07", "The-Only-Brown-Deaf-Man-in-England-26",
             ["Solo Performance"],
             "From 1970s Bangladesh to Brick Lane to the post-9/11 present, follows "
             "Rajkumar, a Deaf Bengali amateur batsman, navigating the chaos, comedy "
             "and contradictions of life in Britain, one ball at a time."),
            ("Trash Salad", "Rosa Garland", None, "2026-10-23", "2026-10-24",
             "Trash-Salad-26",
             ["Comedy", "Feminist", "Live Art", "Queer", "Solo Performance"],
             "Sex. Love. Lettuce. Gorgeous clown Trash Salad on a quest for "
             "connection: a genre-bending burlesque adventure using lip sync, strip "
             "tease and song on a mission to understand intimacy."),
            ("Dottie", "Ruby Glyne", None, "2026-10-25", "2026-10-26", "Dottie", [],
             "A new jazz musical about Dorothy Dandridge, and Lola, a young "
             "mixed-race actress today who finds out how far she'll go to make it "
             "big."),
            ("Chicken Girl (WIP)", "Miranda Prag", None, "2026-10-27", "2026-10-27",
             "Chicken-Girl-WIP", ["Comedy", "Solo Performance", "Work In Progress"],
             "A show about chickens. Part story, part slideshow, a surreal comedy for "
             "the eco-conscious, the eco-confused and anyone who's ever loved — or "
             "eaten — a chicken."),
            ("Bubbly (WIP)", "Functional Delusion Productions", None,
             "2026-10-27", "2026-10-27", "Bubbly-WIP",
             ["Comedy", "Feminist", "Music/Musical", "Work In Progress"],
             "A darkly funny pop musical about three sisters and their internal "
             "battles with self-image and identity."),
            ("RAT RAT RAT", "EggGen", None, "2026-10-28", "2026-10-31", "RAT-RAT-RAT",
             ["International", "Physical Theatre"],
             "Fresh from two sold-out performances, three strangely adorable rat "
             "students invite you to this Halloween's most unsettling lesson in "
             "movement theatre, creature costumes, obedience and systemic cruelty. "
             "Handmade costumes, Halloween timing, and a premise that's funny right "
             "up until it isn't."),
            ("The Show I Feel I Cannot Do (WIP)", "Len Gwyn", None,
             "2026-11-03", "2026-11-03", "The-Show-I-Feel-I-Cannot-Do-WIP",
             ["Music/Musical", "Queer", "Solo Performance", "Work In Progress"],
             "A solo show with music, interviews with friends and the myth of the "
             "trans warrior Caeneus."),
            ("She Was There (WIP)", "Tasnim Siddiqa Amin", None,
             "2026-11-03", "2026-11-03", "She-Was-There",
             ["Feminist", "History", "Solo Performance", "Work In Progress"],
             "A playful exploration of the lives and hidden histories of women who "
             "resisted racism in 1970s and 80s London."),
            ("Sketchy Muslims", "Fatima Mian", None, "2026-11-04", "2026-11-05",
             "Sketchy-Muslims", ["Comedy"],
             "An all-Muslim women comedy sketch show which answers the age-old "
             "question: are Muslim women funny, or is that just BBC propaganda?"),
        ],
        "excluded": [],
    },
    "the-yard": {
        "base": "https://theyardtheatre.co.uk/whats-on",
        "one_stage": False,
        "shows": [
            ("for colored girls who have considered suicide / when the rainbow is enuf",
             "Ntozake Shange, dir. Diane Page, music by Jammz", None,
             "2026-09-02", "2026-10-03", None, [],
             "Shange's choreopoem — poetry, dance and music rather than conventional "
             "drama — marking 50 years since its premiere, with talks and screenings "
             "alongside. Also the first chance to see the rebuilt 220-seat Yard: "
             "mirrored ceiling panels, terracotta-pink walls, neon-traced corridors."),
        ],
        "excluded": [],
        "note": "JS-rendered; recovered via search fallback, no deep link available",
    },
}

# Form, not vibe. Ask reads the blurb for spooky / handmade / etc.
# Word boundaries so "operation" is not opera and "movement" is not dance.
FORM_FROM_SCRAPE = {
    "Comedy": "stand-up",
    "Music/Musical": "musical",
    "Opera": "opera",
    "Dance": "dance",
    "Circus": "circus",
    "immersive": "immersive",
}
FORM_PATTERNS = {
    "musical": [r"\bmusical\b", r"\bbook and lyrics\b", r"\bsung-through\b"],
    "stand-up": [r"\bstand-?up\b", r"\bstandup\b"],
    "concert": [r"\bconcerts?\b", r"\bgigs?\b", r"\blive music\b"],
    "opera": [r"\boperas?\b"],
    "dance": [r"\bdance\b", r"\bballet\b", r"\bchoreograph", r"\bscreendance\b"],
    "circus": [r"\bcircus\b"],
}


def tag(title, credits, desc, source_tags=None):
    """Return form tags: musical, stand-up, concert, opera, dance, else theatre."""
    tags = {FORM_FROM_SCRAPE[t] for t in (source_tags or []) if t in FORM_FROM_SCRAPE}
    blob = f"{title} {credits or ''} {desc or ''}"
    for name, pats in FORM_PATTERNS.items():
        if any(re.search(p, blob, flags=re.I) for p in pats):
            tags.add(name)
    return sorted(tags) or ["theatre"]


def in_window(s, e, window):
    start, end = window
    return not (date.fromisoformat(e) < start or date.fromisoformat(s) > end)


def raw_events_from_seed():
    """Flatten the curated RAW dict into the raw-event shape fetch.py emits.

    This is the offline seed: the hand-fetched rows the committed extract was
    built from, expressed as the crawler's output contract so build() has one
    input format whether rows came from a live fetch or from here.
    """
    events = []
    for vid, data in RAW.items():
        base = data["base"]
        trailing = data.get("trailing_slash", True)
        for title, credits, space, start, end, slug, src, desc in data["shows"]:
            url = (base + slug + ("/" if trailing else "")) if slug else base
            events.append({
                "venue_id": vid,
                "title": title,
                "credits": credits,
                "space": space,
                "first_date": start,
                "last_date": end,
                "url": url,
                "description": desc,
                "venue_tags": src,
            })
    return events


def build(events, window, apply_window=True):
    """Normalise raw rows into the In the Gods schema (window filter + tagging)."""
    records, dropped, missing_desc = [], [], []
    for e in events:
        title = e.get("title")
        start, end = e.get("first_date"), e.get("last_date")
        if not (start and end):
            dropped.append((e.get("venue_id"), title, "no parseable dates"))
            continue
        if apply_window and not in_window(start, end, window):
            dropped.append((e.get("venue_id"), title, "outside window"))
            continue
        byline, desc = e.get("byline"), e.get("description")
        if not byline:
            # rows built offline (or by an older crawl) arrive unsplit
            byline, desc = split_hook(desc)
        if not (byline or desc):
            missing_desc.append((e.get("venue_id"), title))
        records.append({
            "venue_id": e.get("venue_id"),
            "title": title,
            "byline": byline,
            "description": desc,
            "first_date": start,
            "last_date": end,
            "url": e.get("url"),
            "tags": tag(title, e.get("credits"), f"{byline or ''} {desc or ''}",
                        e.get("venue_tags") or []),
        })
    records.sort(key=lambda r: (r["first_date"], r["venue_id"]))
    return records, dropped, missing_desc


def shrink_guard(new_records, compare_path, min_ratio=0.5):
    """Refuse to replace an extract that just lost most of its listings.

    Returns an error string, or None if the write is safe.
    """
    p = Path(compare_path) if compare_path else None
    if not p or not p.exists():
        return None
    try:
        old = json.loads(p.read_text()).get("events") or []
    except (json.JSONDecodeError, OSError):
        return None
    if not old:
        return None
    if len(new_records) < len(old) * min_ratio:
        return (f"refusing to write: {len(new_records)} events vs previous "
                f"{len(old)} ({compare_path}) — below {min_ratio:.0%} floor")
    old_venues = {e.get("venue_id") for e in old if e.get("venue_id")}
    new_counts = Counter(e.get("venue_id") for e in new_records)
    vanished = sorted(v for v in old_venues if new_counts.get(v, 0) == 0)
    if vanished:
        return ("refusing to write: previously listed venues now have 0 events: "
                + ", ".join(vanished))
    return None


def load_source(args):
    """Return (raw_events, window_or_None). Prefers --raw, falls back to seed."""
    if not args.seed and args.raw:
        p = Path(args.raw)
        if p.exists():
            doc = json.loads(p.read_text())
            win = doc.get("window")
            window = ((date.fromisoformat(win[0]), date.fromisoformat(win[1]))
                      if win else None)
            return doc.get("events", []), window
        print(f"note: {p} not found — building from the built-in seed instead",
              file=sys.stderr)
    return raw_events_from_seed(), SEED_WINDOW


def resolve_window(args, source_window):
    if args.window_start and args.window_end:
        return (date.fromisoformat(args.window_start),
                date.fromisoformat(args.window_end))
    if source_window:
        return source_window
    today = date.today()
    return today, today + timedelta(weeks=args.weeks)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", help="crawler output (.cache/raw.json). Omit to build "
                                  "from the built-in curated seed.")
    ap.add_argument("--seed", action="store_true",
                    help="force the built-in curated seed, ignoring --raw")
    ap.add_argument("--out", default="data/extracts/latest.json")
    ap.add_argument("--weeks", type=int, default=8,
                    help="window length when it can't be taken from the crawler dump")
    ap.add_argument("--window-start", help="ISO date; overrides the window start")
    ap.add_argument("--window-end", help="ISO date; overrides the window end")
    ap.add_argument("--generated", help="ISO date stamped on the extract "
                                        "(defaults to the window start)")
    ap.add_argument("--compare", default="data/extracts/latest.json",
                    help="existing extract to guard against shrinking; empty to skip")
    ap.add_argument("--force", action="store_true",
                    help="write even if the shrink guard would refuse")
    args = ap.parse_args()

    events, source_window = load_source(args)
    window = resolve_window(args, source_window)
    # Fetch already windowed each house (including per-venue lookahead_weeks).
    # Re-applying the dump's global window would drop those extras (Eurotrash).
    # Seed builds and explicit --window-* still filter here.
    apply_window = bool(args.seed or args.window_start or args.window_end
                        or not args.raw)
    records, dropped, missing_desc = build(events, window,
                                           apply_window=apply_window)

    generated = args.generated or window[0].isoformat()
    out = Path(args.out)
    if not args.force:
        reason = shrink_guard(records, args.compare)
        if reason:
            print(reason, file=sys.stderr)
            sys.exit(2)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "window": [window[0].isoformat(), window[1].isoformat()],
        "generated": generated,
        "count": len(records),
        "events": records,
    }, indent=2))

    print(f"{len(records)} events | {len(dropped)} dropped | "
          f"{len(missing_desc)} with no copy -> {out}\n")
    print("BY VENUE   ", dict(Counter(r["venue_id"] for r in records)))
    print("BY TAG     ", dict(Counter(t for r in records for t in r["tags"])))
    if missing_desc:
        print("\nNO COPY")
        for v, t in missing_desc:
            print(f"  {v:<22}{t}")
    if dropped:
        print("\nDROPPED")
        for v, t, why in dropped:
            print(f"  {v:<22}{(t or '')[:42]:<44}{why}")


if __name__ == "__main__":
    main()
