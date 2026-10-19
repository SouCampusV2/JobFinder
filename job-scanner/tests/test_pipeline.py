"""What happens to an application after it is sent.

The app counted applications and nothing after them, so the question the whole
filtering strategy rests on - does showing 30 jobs instead of 3300 produce more
interviews - had no answer at all.
"""

from __future__ import annotations

import pytest

import pipeline


# --------------------------------------------------------------------------- #
# The stages                                                                   #
# --------------------------------------------------------------------------- #

def test_the_stages_are_a_real_process_in_order():
    assert pipeline.STAGES[0] == pipeline.APPLIED
    assert pipeline.FUNNEL[-1] == pipeline.OFFER
    # Rejection sits outside the funnel: it is an outcome, not a step.
    assert pipeline.REJECTED not in pipeline.FUNNEL
    assert pipeline.REJECTED in pipeline.STAGES


def test_every_stage_has_a_label():
    assert all(pipeline.LABELS.get(s) for s in pipeline.STAGES)


@pytest.mark.parametrize("stage, ok", [
    ("applied", True), ("hr_interview", True), ("offer", True),
    ("nonsense", False), ("", False), (None, False),
])
def test_only_known_stages_are_accepted(stage, ok):
    assert pipeline.is_valid(stage) is ok


# --------------------------------------------------------------------------- #
# How far it got, versus where it sits                                         #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("best, new, expected", [
    (None, "applied", "applied"),
    ("applied", "hr_interview", "hr_interview"),
    ("hr_interview", "offer", "offer"),
    ("offer", "hr_interview", "offer"),          # never goes backwards
    ("tech_interview", "rejected", "tech_interview"),
    ("applied", "rejected", "applied"),
])
def test_the_furthest_stage_only_moves_forward(best, new, expected):
    assert pipeline.furthest(best, new) == expected


def test_a_rejection_does_not_erase_the_interviews_that_led_to_it():
    """The whole reason for a second column. With one field, an application
    rejected after a tech interview reads as "rejected" and the funnel forgets
    the interview ever happened - under-reporting the only ratio that matters."""
    best = pipeline.furthest("applied", "hr_interview")
    best = pipeline.furthest(best, "tech_interview")
    best = pipeline.furthest(best, "rejected")

    assert best == "tech_interview"


def test_an_offer_counts_as_having_been_interviewed():
    assert pipeline.reached_interview("offer")
    assert pipeline.reached_interview("hr_interview")
    assert not pipeline.reached_interview("applied")
    assert not pipeline.reached_interview("rejected")


# --------------------------------------------------------------------------- #
# Storage                                                                      #
# --------------------------------------------------------------------------- #

async def test_setting_a_stage_marks_the_job_applied(db, listing):
    """An HR interview for a job you never applied to is not a state that
    exists. Requiring two clicks to say so would only produce rows that
    disagree with themselves."""
    job_id = await db.insert_job(listing())

    await db.set_stage(job_id, "hr_interview")

    job = await db.get_job(job_id)
    assert job["applied"] == 1
    assert job["applied_at"]
    assert job["stage"] == "hr_interview"


def _first_applied_at(job):
    return job["applied_at"]


async def test_the_original_application_date_is_not_overwritten(db, listing, monkeypatch):
    """"Applied on" must keep saying when you applied, not when you last
    touched the row. Two calls in the same second hide the difference, so the
    clock is moved between them."""
    import db.queries as q

    job_id = await db.insert_job(listing())
    monkeypatch.setattr(q, "_utc_now_iso", lambda: "2026-07-01T09:00:00+00:00")
    await db.set_stage(job_id, "applied")

    monkeypatch.setattr(q, "_utc_now_iso", lambda: "2026-07-20T18:30:00+00:00")
    await db.set_stage(job_id, "offer")

    job = await db.get_job(job_id)
    assert job["applied_at"] == "2026-07-01T09:00:00+00:00"   # when you applied
    assert job["stage_at"] == "2026-07-20T18:30:00+00:00"     # when it last moved


async def test_the_current_stage_and_the_furthest_one_are_both_stored(db, listing):
    job_id = await db.insert_job(listing())

    await db.set_stage(job_id, "tech_interview")
    await db.set_stage(job_id, "rejected")

    job = await db.get_job(job_id)
    assert job["stage"] == "rejected"          # where it stands
    assert job["stage_best"] == "tech_interview"   # how far it got


async def test_applications_can_be_listed_by_stage(db, listing):
    ids = [await db.insert_job(listing()) for _ in range(3)]
    await db.set_stage(ids[0], "hr_interview")
    await db.set_stage(ids[1], "hr_interview")
    await db.set_stage(ids[2], "offer")

    assert len(await db.list_applied("hr_interview")) == 2
    assert len(await db.list_applied("offer")) == 1
    assert len(await db.list_applied()) == 3


async def test_stage_counts_cover_only_applications(db, listing):
    applied = await db.insert_job(listing())
    await db.insert_job(listing())                # never applied to
    await db.set_stage(applied, "assignment")

    counts = await db.count_by_stage()

    assert counts == {"assignment": 1}


# --------------------------------------------------------------------------- #
# The funnel on the Statistic page                                             #
# --------------------------------------------------------------------------- #

async def test_the_funnel_counts_how_far_applications_got(db, listing):
    ids = [await db.insert_job(listing()) for _ in range(4)]
    await db.set_stage(ids[0], "applied")
    await db.set_stage(ids[1], "hr_interview")
    await db.set_stage(ids[2], "offer")
    await db.set_stage(ids[3], "tech_interview")
    await db.set_stage(ids[3], "rejected")        # rejected AFTER a tech interview

    stats = await db.get_statistics(60)
    by_stage = stats["by_stage"]

    assert stats["applied"] == 4
    assert by_stage.get("hr_interview") == 1
    assert by_stage.get("offer") == 1
    # The rejected one still counts as having reached a tech interview.
    assert by_stage.get("tech_interview") == 1
    assert stats["rejected"] == 1
