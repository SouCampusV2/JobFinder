"""Office requirements hidden in the body of a posting.

The card said "United Kingdom (Remote)" and the metadata gate believed it.
Three thousand characters down: "fully hybrid working model, with one two-day
onsite session per month in Birmingham". It scored 80.

Reading the whole description for the word "hybrid" is not the fix. Of nine
matches in the real database, seven meant something else - every one of them is
a test case below.
"""

from __future__ import annotations

import pytest

from matcher import residency, workplace

_INSTRUCTIONS = """
LOCATION:

Accept:
- Remote within Europe
- Spain remote, hybrid, or onsite
"""


# --------------------------------------------------------------------------- #
# What counts                                                                  #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text", [
    "Fully hybrid working model, with one two-day onsite session per month in Birmingham",
    "This is a hybrid role based out of our Dublin office",
    "We work a hybrid schedule of 3 days per week in the office",
    "Candidates are expected to be in the office 2 days per week",
    "The position is on-site at our Munich headquarters",
    "This role requires regular office attendance",
    "On site work. Office: Madrid",
])
def test_a_stated_arrangement_is_found(text):
    assert workplace.requires_office(text)


@pytest.mark.parametrize("text", [
    # Methodology, not a desk. The commonest false positive in PM adverts.
    "Understanding of project delivery approaches (Agile, Waterfall, or hybrid)",
    "Understand delivery methodologies, including Agile, Scrum, Kanban, and hybrid approaches",
    "Experience with agile or hybrid delivery methodologies",
    # A trip.
    "Willingness to travel occasionally for on-site meetings",
    "Mostly remote, with occasional on-site work at customer locations",
    # A perk.
    "Fitness room and external sports ground (football, basketball) on site",
    # An option the reader gets to decline.
    "Remote or hybrid model - it's up to you!",
    "Our team members are welcome to work remotely, on a hybrid basis or fully office based as they wish",
    "",
    None,
])
def test_something_that_only_contains_the_words_is_not_a_requirement(text):
    assert workplace.requires_office(text) is None


def test_the_phrase_found_is_returned_so_it_can_be_shown():
    """A gate that silently lowers a score is one nobody trusts."""
    found = workplace.requires_office("We run a hybrid working policy here.")

    assert found and "hybrid working policy" in found.lower()


def test_the_requirement_reaches_the_model_as_a_stated_fact():
    job = {"description": "This is a hybrid role, three days per week in the office."}

    assert workplace.signals(job)
    assert "hybrid" in workplace.signals(job)[0].lower()


def test_a_clean_posting_adds_no_line():
    assert workplace.signals({"description": "Fully remote, anywhere in Europe."}) == []


# --------------------------------------------------------------------------- #
# Which country the desk is in                                                 #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("location, expected", [
    ("United Kingdom (Remote)", "United Kingdom"),
    ("Berlin, Germany", "Germany"),
    ("Barcelona, Spain (Hybrid)", "Spain"),
    ("Anywhere in the World", None),
    ("Remote", None),
    ("", None),
    (None, None),
])
def test_the_country_is_read_from_the_location(location, expected):
    assert residency.country_of(location) == expected


def test_a_remote_chip_does_not_erase_the_country():
    """"United Kingdom (Remote)" is still the United Kingdom: the parenthetical
    describes the desk, not the border."""
    assert residency.country_of("United Kingdom (Remote)") == "United Kingdom"


# --------------------------------------------------------------------------- #
# The cap                                                                      #
# --------------------------------------------------------------------------- #

def test_an_office_requirement_abroad_lowers_the_score():
    from matcher.matcher import _RESIDENCY_CAP, _apply_blocker

    job = {
        "title": "Project Manager",
        "location": "United Kingdom (Remote)",
        "description": "x" * 3000 + " Fully hybrid working model, with one "
                       "two-day onsite session per month in Birmingham.",
    }

    assert _apply_blocker(80, {}, job, _INSTRUCTIONS) == _RESIDENCY_CAP


def test_an_office_requirement_at_home_is_fine():
    """The candidate's own instructions accept hybrid in Spain."""
    from matcher.matcher import _apply_blocker

    job = {"title": "PM", "location": "Barcelona, Spain",
           "description": "This is a hybrid role, two days per week in the office."}

    assert _apply_blocker(85, {}, job, _INSTRUCTIONS) == 85


def test_an_unreadable_location_is_left_alone():
    """Dropping a job because its country could not be parsed is worse than
    scoring one that did not need scoring."""
    from matcher.matcher import _apply_blocker

    job = {"title": "PM", "location": "Anywhere in the World",
           "description": "We run a hybrid working model."}

    assert _apply_blocker(85, {}, job, _INSTRUCTIONS) == 85


def test_a_candidate_who_named_no_country_is_never_capped():
    from matcher.matcher import _apply_blocker

    job = {"title": "PM", "location": "Berlin, Germany",
           "description": "This is a hybrid role."}

    assert _apply_blocker(85, {}, job, "") == 85


def test_a_remote_posting_that_states_its_country_is_capped():
    from matcher.matcher import _RESIDENCY_CAP, _apply_blocker

    job = {"title": "PM", "location": "Poland (Remote)",
           "description": "This is a Poland-based role. Fully remote."}

    assert _apply_blocker(85, {}, job, _INSTRUCTIONS) == _RESIDENCY_CAP


def test_a_card_naming_a_country_is_not_enough_on_its_own():
    """Companies put their own address there and hire across Europe anyway."""
    from matcher.matcher import _apply_blocker

    job = {"title": "PM", "location": "Poland (Remote)",
           "description": "Fully remote. Understand Agile, Scrum and hybrid approaches."}

    assert _apply_blocker(85, {}, job, _INSTRUCTIONS) == 85


def test_a_remote_posting_with_no_country_is_untouched():
    from matcher.matcher import _apply_blocker

    job = {"title": "PM", "location": "Remote",
           "description": "Fully remote. Understand Agile, Scrum and hybrid approaches."}

    assert _apply_blocker(85, {}, job, _INSTRUCTIONS) == 85


# --------------------------------------------------------------------------- #
# The obvious case: the card says it outright                                  #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("location, expected", [
    ("Stockholm, Sweden (Hybrid)", ("Hybrid", "Sweden")),
    ("Berlin, Germany (On-site)", ("On-site", "Germany")),
    ("Munich, Germany (Hybrid)", ("Hybrid", "Germany")),
    # The candidate's own instructions accept hybrid and onsite in Spain.
    ("Barcelona, Spain (Hybrid)", None),
    ("Madrid, Spain (On-site)", None),
    # Remote anywhere in Europe is what they asked for.
    ("Poland (Remote)", None),
    # Never punish a location that could not be parsed.
    ("Anywhere in the World", None),
    ("", None),
])
def test_a_desk_in_a_country_you_do_not_live_in_is_caught(location, expected):
    """The chip said Hybrid and the location said Sweden, and nothing compared
    the two - so "Stockholm, Sweden (Hybrid)" scored like a remote job."""
    from scheduler.screening import office_abroad
    from scrapers.base import JobListing

    card = JobListing(source="linkedin", external_id="1", title="PM",
                      company="X", location=location, description="")

    assert office_abroad(card, _INSTRUCTIONS) == expected


def test_a_card_that_claims_remote_is_still_checked_against_the_body():
    """"United Kingdom (Remote)" with a hybrid model buried three thousand
    characters down is the case the metadata gate believed."""
    from scheduler.screening import office_abroad
    from scrapers.base import JobListing

    card = JobListing(
        source="linkedin", external_id="1", title="PM", company="X",
        location="United Kingdom (Remote)",
        description="x" * 3000 + " Fully hybrid working model, with one "
                    "two-day onsite session per month in Birmingham.")

    found = office_abroad(card, _INSTRUCTIONS)

    assert found and found[1] == "United Kingdom"


def test_a_candidate_who_named_no_country_is_never_screened_out():
    from scheduler.screening import office_abroad
    from scrapers.base import JobListing

    card = JobListing(source="linkedin", external_id="1", title="PM",
                      company="X", location="Berlin, Germany (Hybrid)", description="")

    assert office_abroad(card, "") is None
