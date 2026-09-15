"""Show copy: chrome out, then the grab split off as the byline."""
import pathlib
import sys

from bs4 import BeautifulSoup

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "pipeline"))

from fetch import (  # noqa: E402
    apply_stage2,
    clean_text,
    full_title,
    is_chrome,
    is_credits,
    is_epigraph,
    is_full_synopsis,
    is_truncated,
    og_for_show,
    pick_description,
    split_hook,
    synopsis_from_soup,
    synopsis_paragraphs,
)

PLACE_HTML = """
<html><body>
<main>
<p>Book now</p>
<p>A woman walks into a cafe. She orders a coffee. The barista doesn't understand her request. The woman loses her sh*t. Chaos reigns.</p>
<p>This offbeat collaboration between award-winning playwright Vivienne Franzmann and choreographer and psychotherapist Frauke Requardt, brings together 22 very different eyewitness accounts of one everyday altercation to show how our nervous systems are stuck in the Stone Age.</p>
<p>Performed by two dancers, an actor and a drummer (and one bear). Anatomy of Survival is a show for all the nervous systems in the auditorium. Come and feel the rise and fall of yours.</p>
<p>Running time: 70 minutes</p>
</main>
</body></html>
"""

# Hampstead opens on a pull-quote, then runs three long paragraphs.
KIMBERLY = (
    "I want an adventure while I still can! And it's gonna be scary and fun and really stupid"
    "\n\n"
    "Kimberly Levaco is excited to celebrate her upcoming sweet 16 \u2013 never mind the fact "
    "she looks 74, due to a rare genetic condition prematurely ageing her about four times "
    "faster than her friends. Or, she would be excited if her family hadn\u2019t suddenly moved "
    "town under suspect circumstances, meaning she\u2019s a little short on friends right now."
)


def test_synopsis_is_the_three_paragraphs():
    text = synopsis_from_soup(BeautifulSoup(PLACE_HTML, "html.parser"))
    assert text.startswith("A woman walks into a cafe.")
    assert "one bear" in text
    assert "Book now" not in text
    assert "Running time" not in text


def test_byline_is_the_hook_and_description_is_the_rest():
    text = synopsis_from_soup(BeautifulSoup(PLACE_HTML, "html.parser"))
    byline, description = split_hook(text)
    assert byline == (
        "A woman walks into a cafe. She orders a coffee. The barista doesn't "
        "understand her request. The woman loses her sh*t. Chaos reigns."
    )
    assert description.startswith("This offbeat collaboration")
    assert "one bear" in description
    assert byline not in description


def test_long_opening_paragraph_gives_a_sentence_not_the_lot():
    byline, description = split_hook(
        "\n\n".join(KIMBERLY.split("\n\n")[1:])
    )
    assert byline.startswith("Kimberly Levaco is excited")
    assert byline.endswith("faster than her friends.")
    assert description.startswith("Or, she would be excited")


def test_opening_line_of_dialogue_is_not_the_byline():
    kept = synopsis_paragraphs(KIMBERLY.split("\n\n"))
    byline, _ = split_hook("\n\n".join(kept))
    assert byline.startswith("Kimberly Levaco is excited")


def test_epigraphs_need_real_copy_behind_them():
    quote = "I'm out for fame and fortune, not to be different or artistic!"
    assert is_epigraph(quote)
    # on its own it is all we have, so it stays
    assert synopsis_paragraphs([quote]) == [quote]


def test_a_proper_logline_is_not_an_epigraph():
    assert not is_epigraph(
        "A woman walks into a cafe. She orders a coffee. The barista doesn't "
        "understand her request. The woman loses her sh*t. Chaos reigns."
    )
    assert not is_epigraph(
        "Stories of love and violence, joy and survival - and what it feels "
        "like to come out the other side."
    )


def test_listing_that_only_repeats_its_own_headline_is_dropped():
    title = "Immersion (Colin Newman & Malka Spigel)"
    kept = synopsis_paragraphs(
        ["Immersion (Colin Newman & Malka Spigel) + BUNKR At Rich Mix",
         "Immersion are Malka Spigel and Colin Newman, best known for their "
         "work with Minimal Compact and Wire, crafting enthralling records."],
        title=title,
    )
    assert len(kept) == 1
    assert kept[0].startswith("Immersion are Malka Spigel")


def test_italic_epigraph_is_skipped_when_prose_follows():
    html = """
    <html><body><main>
    <p><em>I\u2019m out for fame and fortune, not to be different or artistic!</em></p>
    <p>Joe Bonaparte is a gifted young violinist with a future in music, until
    a chance at fame lures him into the brutal world of professional boxing.</p>
    </main></body></html>
    """
    text = synopsis_from_soup(BeautifulSoup(html, "html.parser"))
    assert text.startswith("Joe Bonaparte")


def test_italic_copy_is_kept_when_it_is_all_there_is():
    html = """
    <html><body><main>
    <p><em>Joe Bonaparte is a gifted young violinist with a future in music,
    until a chance at fame lures him into professional boxing.</em></p>
    </main></body></html>
    """
    assert synopsis_from_soup(BeautifulSoup(html, "html.parser")).startswith(
        "Joe Bonaparte")


def test_og_stub_loses_to_body_copy():
    chosen = pick_description(
        synopsis_from_soup(BeautifulSoup(PLACE_HTML, "html.parser")),
        "Anatomy of Survival at The Place.",
    )
    assert chosen.startswith("A woman walks into a cafe.")


def test_house_bio_og_is_not_this_show():
    """ICA (and similar) stamp the venue bio on every show page's og:description."""
    bio = ("The Institute of Contemporary Arts (ICA) is London's leading space "
           "for contemporary culture. We commission, produce and present new "
           "work in film, music, performance and the visual arts.")
    assert og_for_show(bio, "Destroyer (solo)") is None
    assert og_for_show(
        "Dan Bejar started Destroyer (solo) as a home-recording project.",
        "Destroyer (solo)",
    ) == "Dan Bejar started Destroyer (solo) as a home-recording project."
    row = {"title": "Destroyer (solo)",
           "description": "Dan Bejar started Destroyer as a solo project."}
    apply_stage2(row, {"description": og_for_show(bio, row["title"])})
    assert row["description"].startswith("Dan Bejar started Destroyer")


def test_short_card_stub_is_not_a_full_synopsis():
    assert not is_full_synopsis("A new dance work.")
    assert is_full_synopsis(
        "A woman walks into a cafe. She orders a coffee.\n\n"
        "This offbeat collaboration brings together 22 eyewitness accounts."
    )


def test_one_very_long_sentence_is_cut_for_the_byline():
    long_one = (
        "Pepys\u2019s immortal account of ordinary life in extraordinary times, "
        "brought to life by Edward Bennett (RSC Associate, Bridgerton, SAS Rogue "
        "Heroes) and leading Baroque soprano Grace Davidson, in a staging that "
        "runs without an interval at the Hall."
    )
    byline, description = split_hook(long_one)
    assert len(byline) <= 241
    assert byline.endswith("\u2026")
    # the paragraph itself survives in full
    assert description == long_one


def test_entities_and_run_together_sentences_are_cleaned():
    text = clean_text(
        "Don&#039;t miss this Halloween event for the whole family!Join Deaf "
        "Rave for a thrilling celebration designed for d/Deaf children."
    )
    assert text.startswith("Don't miss")
    assert "family! Join Deaf Rave" in text
    # with the boundary restored, a run-on blob yields a sentence or two,
    # not the 700-character wall it used to
    byline, description = split_hook(f"{text} {text}")
    assert byline.startswith("Don't miss this Halloween event")
    assert byline.endswith("d/Deaf children.")
    assert len(byline) < 200
    assert description.startswith("Don't miss")


def test_star_ratings_are_marketing_not_copy():
    assert is_chrome(
        "Hailed as \u2018the funniest show in London\u2019 (\u2605\u2605\u2605\u2605\u2605 "
        "The Standard), this outrageous musical has critics roaring."
    )


def test_chrome_covers_what_the_houses_actually_lead_with():
    assert is_chrome("\u201cHilarious. A witty adaptation of a Russian classic\u201d")
    assert is_chrome("\u2b50\u2b50\u2b50\u2b50\u2b50 \u201cRaucous\u201d The Arts Desk")
    assert is_chrome("Webber & Co. with Metal Rabbit in association with "
                     "Harlow Playhouse presents")
    assert is_chrome("Until 24 Oct Holloway Theatre (Bush Theatre's Main Space)")
    assert is_chrome("Content warning : Bloodsport contains frequent very "
                     "strong language, misogyny and murder.")
    assert is_chrome("A limited number of tickets will be released on Wed 9 Sep "
                     "from 1pm, with priority booking for members.")
    assert is_chrome("Charlie Burn and Ashley Gilmour performing at West End "
                     "Live, 2026. Videography: OfficialLondonTheatre .")
    assert not is_chrome("Hazel and Robin have survived a catastrophe, living "
                         "on the edge of a radiation exclusion zone.")


def test_account_modals_are_not_the_show():
    """The Barbican floats a login panel above the copy on every show page,
    and it was becoming the byline for all twelve of their listings."""
    assert is_chrome("Log in to access bookings, e-tickets, update your email "
                     "preferences and check out faster.")
    # 'sold-?out' missed the ordinary spelling, so the National's banner ran
    assert is_chrome("Pride is now SOLD OUT Check online regularly for returns.")
    assert is_chrome("This performance is sold out.")
    assert is_chrome("Please note : Latecomers may not be admitted and there "
                     "is no readmittance during the show .")
    assert not is_chrome("Sold, bought and fought over, the house itself is "
                         "the last witness.")


# Theatre503 cuts its card titles at a fixed width, so 14 of its 20 listings
# arrived as 'Advanced Playwriting with Satinder ...'.
def test_truncated_card_title_loses_to_the_show_page():
    assert is_truncated("Advanced Playwriting with Satinder ...")
    assert is_truncated("Character Building\u2026")
    assert not is_truncated("Chewing Gum Dreams")

    page = BeautifulSoup(
        '<html><head><meta property="og:title" '
        'content="Advanced Playwriting with Satinder Chohan | Theatre503">'
        "</head><body><h1>Advanced Playwriting</h1></body></html>",
        "html.parser")
    assert full_title(page) == "Advanced Playwriting with Satinder Chohan"

    row = {"title": "Advanced Playwriting with Satinder ..."}
    apply_stage2(row, {"full_title": "Advanced Playwriting with Satinder Chohan"})
    assert row["title"] == "Advanced Playwriting with Satinder Chohan"
    assert "full_title" not in row


def test_credits_are_not_the_story():
    """The Lyric's copy opened 'By Madeline Whitby and Elizabeth Whitby.
    Directed by Anna Girvan.' — a cast list, not a reason to book."""
    assert is_credits("By William Shakespeare")
    assert is_credits("By Madeline Whitby and Elizabeth Whitby. "
                      "Directed by Anna Girvan.")
    assert is_credits("Book by: Neil Simon Directed by: Nick Mouton")
    # a sentence that merely opens with 'by' is prose — the giveaway is that
    # what follows is not a name
    assert not is_credits("By the time she arrives, the house is already sold.")
    assert not is_credits("By Tuesday the whole street knew.")
    # and a real synopsis that happens to credit someone is too long to be one
    assert not is_credits(
        "By Arnold Wesker. Annie Wobbler is three women in one evening, and "
        "the actor playing her must change utterly between them, which is the "
        "whole point of a piece that has outlived nearly all its contemporaries.")


def test_nested_paragraphs_are_not_read_twice():
    """The Drayton Arms nests <p> inside <p>, so the outer one reads as the
    credit and the synopsis glued together."""
    page = BeautifulSoup(
        "<main><p><p>By William Shakespeare</p>"
        "<p>Viola is washed ashore in Illyria after surviving a shipwreck and "
        "disguises herself as a young man called Cesario to find work.</p>"
        "</p></main>", "html.parser")
    out = synopsis_from_soup(page)
    assert out.startswith("Viola is washed ashore")
    assert "By William Shakespeare" not in out


def test_ticketsolve_font_markup_is_the_synopsis():
    """OSO (and some Hoxton) booth pages have no <p>; the blurb is <font>."""
    page = BeautifulSoup(
        """
        <div class="max-h-60">
          <div><font size="3" face="inherit">Hauntings is a spellbinding evening
          of three tales of the supernatural from two of the world's greatest
          writers of ghost stories, E.F. Benson and M.R. James.</font></div>
          <div><font size="3" face="inherit">With masterful storytelling from
          the Olivier Award-nominated actor Gerard Logan, Hauntings will
          transport you to a world of invisible, but terrifyingly present,
          spirits.</font></div>
        </div>
        """,
        "html.parser",
    )
    out = synopsis_from_soup(page, title="Hauntings")
    assert out.startswith("Hauntings is a spellbinding evening")
    assert "Gerard Logan" in out


def test_copy_outside_an_empty_article_is_still_found():
    """Camden People's Theatre wraps the page in an <article> holding no
    paragraphs at all; scoping to it threw the synopsis away."""
    page = BeautifulSoup(
        "<body><article><div>Good Grief</div></article>"
        "<p>When Marc dies unexpectedly, something arrives to help him cope.</p>"
        "<p>Joe finds himself navigating funeral arrangements, family feuds "
        "and a companion with an unwavering belief he knows what is best.</p>"
        "</body>", "html.parser")
    out = synopsis_from_soup(page)
    assert "When Marc dies unexpectedly" in out
    assert "Joe finds himself" in out


def test_on_sale_notices_are_not_the_show():
    """Orange Tree and artsdepot lead some listings with the sale date."""
    assert is_chrome("General sale opens at 12pm on Wednesday 16 September.")
    assert is_chrome("General sale is open from Thu 18 Jun 2026 at 3:06pm.")
    assert not is_chrome("A general in a sales conference discovers the war "
                         "ended a decade ago and nobody thought to write.")


def test_house_notices_are_not_the_show():
    assert is_chrome("UNDER 18s ARE NOT PERMITTED INTO THE THEATRE "
                     "FOR THIS PERFORMANCE.")
    assert is_chrome("This Production has closed at The Golden Goose Theatre "
                     "or this page is no longer valid or existing.")
    assert is_chrome("Concessions are offered to pensioners, unemployed, "
                     "students, disabled and under16s.")
    assert is_chrome("Join our mailing list for show and exhibition updates "
                     "and offers!")
    assert is_chrome("Please email info@thehopetheatre.com for more information.")
    assert is_chrome("Iceberg Right Ahead comes to the White Bear Theatre. "
                     "Book your tickets today!")


def test_access_statements_are_not_the_show():
    assert is_chrome("At CPT we are committed to ensuring the best possible "
                     "experience for all artists and audience members.")
    assert is_chrome("If you have any questions or enquiries, please do get "
                     "in touch by phone at 020 7419 4841.")


def test_a_complete_card_title_is_left_alone():
    """The show page often appends the house name. Never overwrite a good one."""
    row = {"title": "Chewing Gum Dreams"}
    apply_stage2(row, {"full_title": "Chewing Gum Dreams at Theatre503"})
    assert row["title"] == "Chewing Gum Dreams"


def test_opera_house_chrome_is_not_the_show():
    assert is_chrome("*Young RBO ticket prices for selected performances")
    assert is_chrome(
        "The performance lasts about 3 hours and 30 minutes, "
        "including one interval."
    )
    assert is_chrome(
        "This production contains themes of violence and sexual harassment. "
        "There are strobe effects throughout."
    )
    assert is_chrome(
        "Sung in Italian with English surtitles, which are displayed on "
        "screens above the stage and around the auditorium."
    )
    assert is_chrome("There are currently no dates scheduled for this event.")
    assert is_chrome(
        "Royal Opera House Covent Garden Foundation, a charitable company "
        "limited by guarantee incorporated in England and Wales "
        "(Company number 480523) Charity Registered (Number 211775)"
    )
    assert not is_chrome(
        "A charming predator takes what he wants until a murdered father "
        "returns from the grave to drag him down."
    )


def test_synopsis_heading_beats_the_cast_blurb_above_it():
    """Royal Ballet and Opera puts ticket chrome and a cast line above the
    fold, then the plot under an h3 Synopsis. The three-paragraph budget
    used to fill up before it got there."""
    html = """
    <html><body><main>
    <h1>The Stone Guest</h1>
    <p>He's back. The infamous rake returns with an all-star cast
    headlined by Gordon, alongside three others, and a conductor.</p>
    <p>*Young RBO ticket prices for selected performances</p>
    <p>The performance lasts about 3 hours and 30 minutes, including one interval.</p>
    <h3>Synopsis</h3>
    <p>A charming predator takes what he wants until a murdered father
    returns from the grave to drag him down. The stone statue knocks,
    the earth opens, and the party is over.</p>
    <h3>A new commission</h3>
    <p>The staging captures the debauchery of desire while cutting through
    the sharp emotional tension of the score, with a set that blurs the
    boundary between the house and the Don's twisting interior world.</p>
    </main></body></html>
    """
    text = synopsis_from_soup(BeautifulSoup(html, "html.parser"),
                              title="The Stone Guest")
    assert text.startswith("A charming predator")
    assert "including one interval" not in text
    assert "ticket prices" not in text
    assert "He's back" not in text
    assert "debauchery of desire" in text
