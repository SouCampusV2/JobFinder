"""Residency requirements: "remote, but you must live in Switzerland".

The gate exists because a real posting scored 85%. The rules said "accept
remote within Europe / reject relocation outside Europe"; Switzerland is in
Europe and the role was remote, so the model was right and the rule set simply
had no concept of residency.
"""

from __future__ import annotations

import pytest

from matcher import residency

_INSTRUCTIONS = """
LOCATION:

Accept:
- Remote within Europe
- Spain remote, hybrid, or onsite
- European companies with English-speaking teams

Reject:
- Requires relocation outside Europe
- Requires mandatory office presence outside Europe

---

LANGUAGE (IMPORTANT):
Working language must be English.
"""


# --------------------------------------------------------------------------- #
# Reading the requirement                                                      #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text, expected", [
    ("Our partner is looking for a Design Coordinator based in Switzerland.",
     {"Switzerland"}),
    ("We are looking for a Project Manager based in Ireland to join the team.",
     {"Ireland"}),
    ("Candidates must be based in Germany.", {"Germany"}),
    ("You must reside in Portugal for this role.", {"Portugal"}),
    ("Open to residents of Poland only.", {"Poland"}),
    ("You must be legally authorized to work in the Netherlands.", {"Netherlands"}),
])
def test_a_stated_requirement_is_read(text, expected):
    assert residency.required_countries(text) == expected


@pytest.mark.parametrize("text", [
    "We are a company based in Switzerland with a remote-first culture.",
    "Our client, a fintech headquartered in Berlin, Germany, is growing fast.",
    "We are looking for a partner company based in Germany.",
    "The team is distributed; our office in Sweden hosts the design chapter.",
    "Founded in Estonia in 2019, we now serve customers worldwide.",
    "Fully remote role, open to anyone in Europe.",
    "",
    None,
])
def test_a_company_address_is_not_a_residency_requirement(text):
    assert residency.required_countries(text) == set()


def test_the_word_partner_in_front_does_not_kill_the_match():
    """The commonest real phrasing there is. An earlier version scanned the 60
    characters before the match too, saw "Our partner is", and threw it away."""
    text = ("This position is listed on behalf of a partner company, who manages all "
            "applications and next steps. Our partner is looking for a Design "
            "Coordinator based in Switzerland.")

    assert residency.required_countries(text) == {"Switzerland"}


# --------------------------------------------------------------------------- #
# Lists - the case that makes this a set and not a single country              #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text, expected", [
    ("This role is open to candidates based in Ukraine, Portugal, or Poland.",
     {"Ukraine", "Portugal", "Poland"}),
    ("100% remote and open to candidates based in Germany, Spain, Portugal or the U.K.",
     {"Germany", "Spain", "Portugal", "United Kingdom"}),
    ("Candidates must be based in France and Belgium.", {"France", "Belgium"}),
    ("Open to residents of Sweden/Norway.", {"Sweden", "Norway"}),
])
def test_a_country_list_is_read_whole(text, expected):
    assert residency.required_countries(text) == expected


def test_an_oxford_comma_does_not_drop_the_last_country():
    """", or Poland" is two separator tokens; allowing only one silently lost
    the last country of every list written this way."""
    got = residency.required_countries("open to candidates based in Ukraine, Portugal, or Poland")

    assert "Poland" in got


# --------------------------------------------------------------------------- #
# The candidate's own countries                                                #
# --------------------------------------------------------------------------- #

def test_home_countries_come_from_the_candidates_own_instructions():
    assert residency.home_countries(_INSTRUCTIONS) == {"Spain"}


def test_a_country_under_reject_is_not_a_home():
    instructions = """
LOCATION:

Accept:
- Remote within Europe

Reject:
- Anything requiring a move to Germany
"""

    assert residency.home_countries(instructions) == set()


def test_no_location_section_means_no_home():
    assert residency.home_countries("I want product operations roles.") == set()


def test_no_instructions_at_all_is_not_an_error():
    assert residency.home_countries(None) == set()


# --------------------------------------------------------------------------- #
# The gate                                                                     #
# --------------------------------------------------------------------------- #

def test_a_country_the_candidate_did_not_name_blocks():
    job = {"description": "Our partner is looking for a Design Coordinator based in Switzerland."}

    assert residency.blocking_countries(job, _INSTRUCTIONS) == {"Switzerland"}


def test_a_list_containing_the_candidates_own_country_does_not_block():
    """Blocking this would be exactly backwards - Spain is on the list."""
    job = {"description": "Remote, open to candidates based in Germany, Spain, Portugal or the U.K."}

    assert residency.blocking_countries(job, _INSTRUCTIONS) == set()


def test_a_region_is_not_a_residency():
    """"Remote within Europe" does not make anyone a Swiss resident. This is the
    exact hole the 85% posting fell through."""
    europe_only = "LOCATION:\nAccept:\n- Remote within Europe\n"
    job = {"description": "We are looking for a Coordinator based in Switzerland."}

    # No country named for themselves at all -> the gate stays out of the way.
    assert residency.blocking_countries(job, europe_only) == set()


def test_a_candidate_who_named_no_country_is_never_blocked():
    job = {"description": "Candidates must be based in Germany."}

    assert residency.blocking_countries(job, "") == set()


def test_a_posting_that_says_nothing_is_never_blocked():
    assert residency.blocking_countries({"description": "Fully remote."}, _INSTRUCTIONS) == set()


# --------------------------------------------------------------------------- #
# What the model is told                                                       #
# --------------------------------------------------------------------------- #

def test_the_requirement_is_stated_in_the_vacancy_block():
    job = {"description": "Our partner is looking for a Coordinator based in Switzerland."}

    assert residency.signals(job) == [
        "Residency required: Switzerland (the hire must live there)"]


def test_a_silent_posting_adds_no_line():
    assert residency.signals({"description": "Fully remote."}) == []


def test_country_lists_read_naturally():
    assert residency.as_text({"Spain"}) == "Spain"
    assert residency.as_text({"Germany", "Spain"}) == "Germany or Spain"
    assert residency.as_text({"Spain", "Germany", "Portugal"}) == "Germany, Portugal or Spain"


# --------------------------------------------------------------------------- #
# The cap                                                                      #
# --------------------------------------------------------------------------- #

def test_the_score_is_capped_softly_not_blocked():
    """A move is expensive, not impossible - unlike a Senior title or a
    German-only workplace, which are simply wrong for the candidate."""
    from matcher.matcher import _RESIDENCY_CAP, _apply_blocker

    job = {"title": "Design Coordinator",
           "description": "Our partner is looking for a Coordinator based in Switzerland."}

    assert _apply_blocker(85, {}, job, _INSTRUCTIONS) == _RESIDENCY_CAP
    assert 25 < _RESIDENCY_CAP < 60


def test_a_low_score_is_not_raised_by_the_cap():
    from matcher.matcher import _apply_blocker

    job = {"title": "X", "description": "Candidates must be based in Germany."}

    assert _apply_blocker(20, {}, job, _INSTRUCTIONS) == 20


def test_a_hard_blocker_still_wins_over_the_soft_cap():
    from matcher.matcher import _apply_blocker

    job = {"title": "Senior Product Manager",
           "description": "Our partner is looking for a Manager based in Switzerland."}
    instructions = _INSTRUCTIONS + "\nSENIORITY:\nReject:\n- Senior Product Manager\n"

    assert _apply_blocker(85, {}, job, instructions) == 25


def test_a_matching_country_leaves_the_score_alone():
    from matcher.matcher import _apply_blocker

    job = {"title": "Coordinator",
           "description": "Remote, open to candidates based in Germany, Spain or Portugal."}

    assert _apply_blocker(85, {}, job, _INSTRUCTIONS) == 85


# --------------------------------------------------------------------------- #
# The card pins the job to a country even when it says "Remote"                #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("location", [
    "Poland (Remote)", "Berlin, Berlin, Germany (Remote)", "United Kingdom (Remote)",
])
def test_the_card_alone_does_not_block(location):
    """Companies fill the location field with their own address and hire across
    Europe anyway. Blocking on the card alone removed 108 of 138 jobs from the
    review list, most of them wrongly. The DESCRIPTION has to say it."""
    job = {"location": location, "description": "An ordinary description."}

    assert residency.blocking_countries(job, _INSTRUCTIONS) == set()


@pytest.mark.parametrize("text, expected", [
    ("This is a Germany-based role, fully remote.", {"Germany"}),
    ("UK based, remote first company.", {"United Kingdom"}),
    ("Remote (Germany)", {"Germany"}),
    ("Remote - Poland", {"Poland"}),
    ("Location: Portugal", {"Portugal"}),
    # The employer's own address, not the hire's.
    ("We are a Germany-based company with offices worldwide.", set()),
    ("Our client is a Poland-based startup.", set()),
])
def test_the_description_saying_it_outright_does_block(text, expected):
    job = {"location": "Remote", "description": text}

    assert residency.blocking_countries(job, _INSTRUCTIONS) == expected


def test_a_country_list_containing_home_wins_over_a_single_mention():
    job = {"location": "Poland (Remote)",
           "description": "Open to candidates based in Germany, Spain or Portugal."}

    assert residency.blocking_countries(job, _INSTRUCTIONS) == set()


def test_nothing_blocks_when_the_candidate_named_no_country():
    job = {"location": "Remote", "description": "This is a Poland-based role."}

    assert residency.blocking_countries(job, "") == set()


def test_a_stated_country_is_screened_before_any_model_call():
    from scheduler.screening import free_reject

    job = {"title": "Product Manager", "location": "Remote",
           "description": "This is a Poland-based role, fully remote."}

    reason = free_reject(job, _INSTRUCTIONS)

    assert reason and "Poland" in reason


async def test_the_advanced_check_says_why_it_capped_the_score():
    """A score quietly capped with no gap explaining it reads as the model
    being wrong. The deep check is where a job is looked at seriously."""
    from matcher.matcher import AIMatcher

    m = AIMatcher(api_key="test-key")

    class Completions:
        async def create(self, **kw):
            body = ('{"strengths": ["Good ops overlap"], "weaknesses": ["Minor gap"], '
                    '"score": 85, "blocker": false}')
            return type("R", (), {"choices": [type("C", (), {
                "message": type("M", (), {"content": body})()})()]})()

    m._client = type("C", (), {"chat": type("Ch", (), {"completions": Completions()})()})()

    job = {"title": "PM", "location": "Germany (Remote)",
           "description": "This is a Germany-based role, fully remote."}
    result = await m.advanced(job, {"instructions": _INSTRUCTIONS, "resume_text": "",
                                    "case_bank": ""})

    assert any("Germany" in w for w in result.weaknesses), result.weaknesses
