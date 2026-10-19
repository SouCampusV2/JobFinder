"""The one place that decides whether a job is worth a model call.

Jobs arrive by two roads - the scheduled scan of public sources, and the
extension posting what it read in the user's own LinkedIn session - and each
road used to carry its own copy of this decision. They drifted, predictably:
the free gates and the batched title screen were added to the scheduled scan
and the extension path kept paying full price for 56% of all jobs.

So the POLICY lives here and the PLUMBING stays with each caller. What differs
between the two roads is real (one has a JobListing not yet stored, the other a
row already in the database) and does not belong in a shared function pretending
otherwise. What must never differ is which jobs get screened out and why.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from typing import Any

from matcher import matcher as matcher_mod
from matcher import residency, seniority, workplace

logger = logging.getLogger(__name__)

# Verdicts. `REJECT` costs nothing, `SCREENED` costs a share of one batched
# call, `KEEP` costs a full score.
REJECT = "reject"
SCREENED = "screened"
KEEP = "keep"


def as_job(card: Any) -> dict[str, Any]:
    """A plain dict, whether the caller holds a JobListing or a database row."""
    return asdict(card) if is_dataclass(card) else dict(card)


def free_reject(card: Any, instructions: str | None) -> str | None:
    """Why this job needs no model call at all, or None.

    Every rule here is read from the candidate's own instructions, and an
    unstated rule blocks nothing. Both gates existed before this function; they
    ran at the END of scoring, after two model calls had been paid for, which on
    a real database meant 1273 of 5886 jobs reached a verdict the code held from
    the start."""
    job = as_job(card)

    level = seniority.blocking_level(job, instructions)
    if level:
        return f"says {level.title()}, which your instructions reject"

    place = office_abroad(job, instructions)
    if place:
        return f"{place[0]} in {place[1]}, where you do not live"

    # "Poland (Remote)" is remote FROM Poland. The country beside the chip is
    # not decoration - it is where the company can employ you. This was 77 of
    # 138 jobs scoring 60+, every one of them past every other gate.
    pinned = residency.blocking_countries(job, instructions)
    if pinned:
        return (f"remote, but tied to {residency.as_text(pinned)}, "
                f"where you do not live")
    return None


def office_abroad(card: Any, instructions: str | None) -> tuple[str, str] | None:
    """(arrangement, country) when a job needs you at a desk you cannot reach.

    Hybrid and on-site only work where you already live. The card's own chip
    says which it is and the location says where, but nothing compared the two -
    so "Stockholm, Sweden (Hybrid)" passed as "somewhere in Europe, remote-ish".

    Returns None whenever anything is unknown: a country that could not be
    parsed must not cost a job its score."""
    job = as_job(card)
    arrangement = matcher_mod.detect_workplace(job)
    if arrangement not in ("Hybrid", "On-site"):
        # The metadata says remote. The body may still disagree - that is the
        # case where the card said "United Kingdom (Remote)" and three thousand
        # characters down sat a hybrid model with monthly sessions in Birmingham.
        if not workplace.requires_office(job.get("description")):
            return None
        arrangement = "Hybrid/on-site"

    where = residency.country_of(job.get("location"))
    home = residency.home_countries(instructions)
    if not where or not home or where in home:
        return None
    return arrangement, where


async def title_verdicts(cards: list[Any], matcher, instructions: str | None):
    """Screen a list of cards in batches. Yields (card, verdict, payload).

    `payload` is the rejection reason for REJECT, the TitleResult for SCREENED
    and KEEP. Order is preserved so a caller can zip it against its own state.
    """
    free: list[tuple[Any, str]] = []
    survivors: list[Any] = []
    for card in cards:
        reason = free_reject(card, instructions)
        if reason:
            free.append((card, reason))
        else:
            survivors.append(card)

    if free:
        logger.info("Screened %d of %d jobs for free (no model call)",
                    len(free), len(cards))
    for card, reason in free:
        yield card, REJECT, reason

    size = getattr(matcher, "BATCH_SIZE", 10)
    for start in range(0, len(survivors), size):
        chunk = survivors[start:start + size]
        results = await matcher.title_screen_batch(
            [as_job(c) for c in chunk], instructions or "")
        for card, title in zip(chunk, results):
            yield card, (KEEP if title.plausible else SCREENED), title
