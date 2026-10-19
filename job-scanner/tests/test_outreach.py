"""Referral outreach: who a contact is, how you can reach them, and what is stored.

Classification costs nothing - no model call - so it has to be right in code.
The degree of connection is the load-bearing field: it decides whether a draft
is a direct message, a 200-character invite note, or should not be written at
all because the person cannot be reached.
"""

from __future__ import annotations

import pytest

from matcher import audience
from matcher.generate import _fit_note


# --------------------------------------------------------------------------- #
# Who is this person                                                           #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("headline, expected", [
    ("Technical Recruiter", audience.RECRUITER),
    ("Talent Acquisition Partner", audience.RECRUITER),
    ("Sourcer, Product & Design", audience.RECRUITER),
    ("Head of Design", audience.LEADERSHIP),
    ("VP of Engineering", audience.LEADERSHIP),
    ("Chief Technology Officer", audience.LEADERSHIP),
    ("Co-Founder", audience.LEADERSHIP),
    ("Design Operations Manager", audience.HIRING_MANAGER),
    ("Engineering Manager", audience.HIRING_MANAGER),
    ("Team Lead, Platform", audience.HIRING_MANAGER),
    ("Senior Product Designer", audience.PEER),
    ("Software Engineer", audience.PEER),
    ("", audience.OTHER),
    (None, audience.OTHER),
])
def test_a_headline_places_someone_in_an_audience(headline, expected):
    assert audience.classify(headline) == expected


def test_a_substring_is_not_a_title():
    """"lead" inside "leaderboard" is the same trap the seniority gate hit."""
    assert audience.classify("Team Leaderboard enthusiast") == audience.PEER


def test_a_recruiter_wins_over_a_manager_word():
    """"Recruiting Manager" is a recruiter, not the hiring manager for the role."""
    assert audience.classify("Recruiting Manager") == audience.RECRUITER


# --------------------------------------------------------------------------- #
# How you can reach them - the field the whole feature turns on                 #
# --------------------------------------------------------------------------- #

def test_the_route_follows_the_degree():
    assert audience.route(1) == audience.DIRECT
    assert audience.route(2) == audience.INVITE
    assert audience.route(3) == audience.UNREACHABLE


def test_an_unknown_degree_takes_the_safe_two_step_path():
    """Guessing "direct" would produce a message that cannot be sent."""
    assert audience.route(None) == audience.INVITE


def test_the_note_limit_is_the_free_account_one():
    """200 for free accounts, 300 for Premium. Writing to the higher number
    means the note gets silently truncated for most people."""
    assert audience.NOTE_MAX_CHARS == 200


# --------------------------------------------------------------------------- #
# How close they sit to the decision                                           #
# --------------------------------------------------------------------------- #

def test_a_hiring_manager_on_the_same_subject_ranks_highest():
    top = audience.relevance(audience.HIRING_MANAGER, "Design Operations Manager",
                             "Design Coordinator")
    recruiter = audience.relevance(audience.RECRUITER, "Technical Recruiter",
                                   "Design Coordinator")

    assert top > recruiter


def test_an_unrelated_peer_ranks_bottom():
    assert audience.relevance(audience.PEER, "Warehouse Operative",
                              "Design Coordinator") == 0


def test_word_endings_do_not_break_the_match():
    """"Designer" against "Design" is the same subject; an exact-word match
    called it unrelated."""
    assert audience.relevance(audience.PEER, "Senior Product Designer",
                              "Design Coordinator") == 1


def test_a_generic_word_is_not_a_subject_match():
    """Half of all headlines contain "Manager"; matching on it would rank
    everyone equally and make the stars meaningless."""
    assert audience.relevance(audience.PEER, "Account Manager",
                              "Product Manager") == 0


# --------------------------------------------------------------------------- #
# The 200-character cap                                                        #
# --------------------------------------------------------------------------- #

def test_a_short_note_is_left_alone():
    assert _fit_note("Short note about the role.") == "Short note about the role."


def test_an_overlong_note_is_cut_at_a_sentence():
    text = ("Hi Anna, I saw the Design Coordinator opening at Docplanner and I have spent "
            "three years running design operations for a product team of forty. I would "
            "love to connect and hear how the team works today.")

    got = _fit_note(text)

    assert len(got) <= 200
    assert got.endswith(".")


def test_a_note_with_no_sentence_break_is_still_capped():
    assert len(_fit_note("A" * 260)) <= 200


def test_quotes_the_model_wrapped_around_it_are_removed():
    assert _fit_note('"Quoted note."') == "Quoted note."


# --------------------------------------------------------------------------- #
# Storage                                                                      #
# --------------------------------------------------------------------------- #

async def _job(db, listing) -> int:
    return await db.insert_job(listing(title="Design Coordinator", company="Acme"))


async def test_a_contact_is_stored_and_read_back(db, listing):
    job_id = await _job(db, listing)

    contact_id = await db.upsert_contact(
        job_id=job_id, name="Anna Weber", headline="Head of Design",
        profile_url="https://www.linkedin.com/in/annaweber", degree=2,
        audience="leadership", rank=2)

    contact = await db.get_contact(contact_id)
    assert contact["name"] == "Anna Weber"
    assert contact["degree"] == 2
    assert contact["status"] == "found"


async def test_a_nameless_or_linkless_row_is_rejected(db, listing):
    job_id = await _job(db, listing)

    assert await db.upsert_contact(job_id, "", None, "https://x", 2, "peer", 0) is None
    assert await db.upsert_contact(job_id, "Anna", None, "", 2, "peer", 0) is None


async def test_re_reading_the_page_does_not_reset_work_already_done(db, listing):
    """The user re-runs Find people; a draft they already have must survive."""
    job_id = await _job(db, listing)
    url = "https://www.linkedin.com/in/annaweber"
    contact_id = await db.upsert_contact(job_id, "Anna Weber", "Head of Design", url,
                                         2, "leadership", 2)
    await db.save_contact_draft(contact_id, "note", "my careful note")
    await db.set_contact_status(contact_id, "invited")

    again = await db.upsert_contact(job_id, "Anna Weber", "Head of Design Ops", url,
                                    1, "leadership", 3)

    assert again == contact_id
    contact = await db.get_contact(contact_id)
    assert contact["note"] == "my careful note"      # draft kept
    assert contact["status"] == "invited"            # progress kept
    assert contact["headline"] == "Head of Design Ops"  # facts refreshed
    assert contact["degree"] == 1


async def test_contacts_are_listed_closest_to_the_decision_first(db, listing):
    job_id = await _job(db, listing)
    await db.upsert_contact(job_id, "Low", None, "u1", 3, "peer", 0)
    await db.upsert_contact(job_id, "High", None, "u2", 2, "hiring_manager", 3)
    await db.upsert_contact(job_id, "Mid", None, "u3", 1, "recruiter", 2)

    names = [c["name"] for c in await db.list_contacts(job_id)]

    assert names == ["High", "Mid", "Low"]


async def test_archived_contacts_are_not_listed(db, listing):
    job_id = await _job(db, listing)
    contact_id = await db.upsert_contact(job_id, "Gone", None, "u1", 2, "peer", 1)
    await db.set_contact_status(contact_id, "archived")

    assert await db.list_contacts(job_id) == []


async def test_the_monthly_note_count_is_real(db, listing):
    job_id = await _job(db, listing)
    a = await db.upsert_contact(job_id, "A", None, "u1", 2, "peer", 1)
    b = await db.upsert_contact(job_id, "B", None, "u2", 2, "peer", 1)

    await db.set_contact_status(a, "invited", spent_note=True)
    await db.set_contact_status(b, "invited")          # invited without a note

    assert await db.notes_spent_this_month() == 1


async def test_a_contact_invited_long_ago_is_archived(db, listing):
    import aiosqlite
    from config import settings

    job_id = await _job(db, listing)
    contact_id = await db.upsert_contact(job_id, "Stale", None, "u1", 2, "peer", 1)
    await db.set_contact_status(contact_id, "invited")
    async with aiosqlite.connect(settings.db_path) as raw:
        await raw.execute("UPDATE contacts SET updated_at = '2020-01-01T00:00:00+00:00' "
                          "WHERE id = ?", (contact_id,))
        await raw.commit()

    assert await db.archive_stale_contacts() == 1
    assert (await db.get_contact(contact_id))["status"] == "archived"


async def test_an_accepted_contact_is_never_auto_archived(db, listing):
    """Only invites that were never answered go stale. A conversation in
    progress is exactly what the user came for."""
    import aiosqlite
    from config import settings

    job_id = await _job(db, listing)
    contact_id = await db.upsert_contact(job_id, "Live", None, "u1", 1, "peer", 1)
    await db.set_contact_status(contact_id, "accepted")
    async with aiosqlite.connect(settings.db_path) as raw:
        await raw.execute("UPDATE contacts SET updated_at = '2020-01-01T00:00:00+00:00' "
                          "WHERE id = ?", (contact_id,))
        await raw.commit()

    assert await db.archive_stale_contacts() == 0


async def test_the_extension_target_survives_a_round_trip(db, listing):
    job_id = await _job(db, listing)

    await db.set_people_target(job_id)

    target = await db.get_people_target()
    assert target["id"] == job_id
    assert target["title"] == "Design Coordinator"


async def test_no_target_reads_as_nothing_rather_than_an_error(db):
    assert await db.get_people_target() is None


def test_a_three_letter_prefix_is_not_a_subject_match():
    """"Art" prefixes "Article" without being about it. The stem comparison
    needs a floor or it starts matching noise."""
    assert audience.relevance(audience.PEER, "Art Director", "Article Editor") == 0


class _FakeChoice:
    def __init__(self, text):
        self.message = type("M", (), {"content": text})()


class _FakeCompletions:
    def __init__(self, text):
        self._text = text
        self.calls: list[dict] = []

    async def create(self, **kw):
        self.calls.append(kw)
        return type("R", (), {"choices": [_FakeChoice(self._text)]})()


def _generator(text: str):
    """A CopilotGenerator whose model always answers `text`."""
    from matcher.generate import CopilotGenerator

    generator = CopilotGenerator(api_key="test-key")
    completions = _FakeCompletions(text)
    generator._client = type("C", (), {"chat": type("Ch", (), {"completions": completions})()})()
    return generator, completions


async def test_the_generated_note_is_capped_before_it_is_stored():
    """The model overshoots a stated limit often enough that the cap cannot
    live in the prompt alone - LinkedIn truncates silently at 200."""
    generator, _ = _generator("Hi Anna. " + "This sentence is filler. " * 20)

    got = await generator.outreach({"name": "Anna"}, {"title": "X"}, {}, "note")

    assert len(got) <= audience.NOTE_MAX_CHARS


async def test_a_full_message_is_not_truncated():
    long_message = "Hi Anna. " + "This sentence is filler. " * 20
    generator, _ = _generator(long_message)

    got = await generator.outreach({"name": "Anna"}, {"title": "X"}, {}, "message")

    assert len(got) > audience.NOTE_MAX_CHARS


async def test_the_two_genres_use_different_prompts():
    generator, completions = _generator("text")

    await generator.outreach({"name": "A"}, {"title": "X"}, {}, "note")
    await generator.outreach({"name": "A"}, {"title": "X"}, {}, "message")

    note_prompt = completions.calls[0]["messages"][0]["content"]
    message_prompt = completions.calls[1]["messages"][0]["content"]
    assert note_prompt != message_prompt
    assert "200" in note_prompt


async def test_the_person_is_named_in_the_prompt():
    """A draft that does not know who it is addressed to is a template."""
    generator, completions = _generator("text")

    await generator.outreach({"name": "Anna Weber", "headline": "Head of Design"},
                             {"title": "Design Coordinator"}, {}, "message")

    user_prompt = completions.calls[0]["messages"][1]["content"]
    assert "Anna Weber" in user_prompt and "Head of Design" in user_prompt


async def test_an_unknown_genre_is_refused_without_calling_the_model():
    generator, completions = _generator("text")

    got = await generator.outreach({"name": "A"}, {"title": "X"}, {}, "telegram")

    assert "Unknown outreach type" in got
    assert completions.calls == []
