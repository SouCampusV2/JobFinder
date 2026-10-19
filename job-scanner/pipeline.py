"""Where an application currently stands.

The app counted applications and nothing after them, so the one question worth
asking - does filtering 3 300 jobs down to 30 actually produce more interviews
than spraying 300 - had no answer. A single field fixes that, provided the
stages are the ones a real process has rather than a tidy invention.

Deliberately one field and not an event log. A history table would answer "how
long did they sit on the assignment", which nobody has asked; a current stage
answers "how far did this get", which is the whole point. The timestamp comes
along for free and leaves the door open.
"""

from __future__ import annotations

# Ordered as the process runs. The order is load-bearing: it drives the funnel
# on the Statistic page and the sort of the filter chips.
APPLIED = "applied"
ASSIGNMENT = "assignment"
HR_INTERVIEW = "hr_interview"
TECH_INTERVIEW = "tech_interview"
FINAL_INTERVIEW = "final_interview"
OFFER = "offer"
REJECTED = "rejected"

STAGES: tuple[str, ...] = (
    APPLIED, ASSIGNMENT, HR_INTERVIEW, TECH_INTERVIEW, FINAL_INTERVIEW, OFFER, REJECTED,
)

LABELS: dict[str, str] = {
    APPLIED: "Applied",
    ASSIGNMENT: "Test task",
    HR_INTERVIEW: "HR interview",
    TECH_INTERVIEW: "Tech interview",
    FINAL_INTERVIEW: "Final interview",
    OFFER: "Offer",
    REJECTED: "Rejected",
}

# Everything up to and including an offer is progress. Rejection is an outcome,
# not a step, and is reachable from any stage - which is why it sits outside the
# funnel rather than at the end of it.
FUNNEL: tuple[str, ...] = (APPLIED, ASSIGNMENT, HR_INTERVIEW, TECH_INTERVIEW,
                           FINAL_INTERVIEW, OFFER)

# The stages that mean somebody actually spoke to you. Used for the one ratio
# that says whether the filtering is working.
INTERVIEW_STAGES: tuple[str, ...] = (HR_INTERVIEW, TECH_INTERVIEW, FINAL_INTERVIEW)

# Stages after which nothing else happens.
TERMINAL: tuple[str, ...] = (OFFER, REJECTED)


# Depth of each funnel stage, for "did this go further than that". Rejection
# has no depth of its own - it is an outcome that can land on any stage.
_DEPTH: dict[str, int] = {name: i for i, name in enumerate(FUNNEL)}


def depth(stage: str | None) -> int:
    return _DEPTH.get(stage or APPLIED, 0)


def furthest(current_best: str | None, new_stage: str) -> str:
    """The deeper of the two. A rejection never overwrites how far you got."""
    if new_stage == REJECTED:
        return current_best or APPLIED
    return new_stage if depth(new_stage) >= depth(current_best) else (current_best or APPLIED)


def is_valid(stage: str | None) -> bool:
    return stage in STAGES


def label(stage: str | None) -> str:
    return LABELS.get(stage or APPLIED, LABELS[APPLIED])


def reached_interview(stage: str | None) -> bool:
    """True once a human has spent time on you.

    A rejection says nothing about how far you got, so it does not count here
    even though it often follows an interview - the stage field holds the last
    thing that happened, and this asks about the best thing that happened."""
    return stage in INTERVIEW_STAGES or stage == OFFER
