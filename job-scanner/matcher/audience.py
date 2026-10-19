"""Who a contact is, and how you are allowed to reach them.

Both answers are mechanical, so neither costs a model call: the audience comes
from the person's own headline, and the route comes from the LinkedIn degree of
connection. Classifying ten contacts must not mean ten API calls.

The route matters more than the tone. LinkedIn gives three different channels:

  1st degree  - a direct message, no length limit
  2nd degree  - an invite first; the optional note is capped at 200 characters
                and free accounts get about five personalised ones per MONTH
  3rd degree  - nothing at all without Premium

So a draft written without knowing the degree is the wrong genre at best and
unsendable at worst. The recommended play for a 2nd-degree contact is an invite
with NO note, then the full message once they accept - that spends none of the
monthly five and produces a better message than 200 characters ever could.
"""

from __future__ import annotations

import re

from matcher import seniority

# Audiences, most specific first - first match wins.
RECRUITER = "recruiter"
LEADERSHIP = "leadership"
HIRING_MANAGER = "hiring_manager"
PEER = "peer"
OTHER = "other"

AUDIENCE_LABELS = {
    RECRUITER: "Recruiter",
    LEADERSHIP: "Leadership",
    HIRING_MANAGER: "Hiring manager",
    PEER: "Peer",
    OTHER: "Other",
}

# Routes.
DIRECT = "direct"          # 1st degree - message them now
INVITE = "invite"          # 2nd degree - invite, then message on acceptance
UNREACHABLE = "unreachable"  # 3rd degree - out of reach without Premium

ROUTE_LABELS = {
    DIRECT: "Message directly",
    INVITE: "Invite, then message",
    UNREACHABLE: "Out of reach",
}

# LinkedIn's cap on the personalised note attached to an invite. Free accounts
# get 200 characters; Premium gets 300. We write to the lower number, because a
# note that has to be trimmed by hand is worse than one that fits.
NOTE_MAX_CHARS = 200

_RECRUITER_WORDS = ("recruiter", "recruiting", "recruitment", "sourcer", "sourcing",
                    "talent acquisition", "talent partner", "talent", "people partner",
                    "hr business partner", "headhunter")

# Levels that mean the person sets direction rather than fills a seat. Built on
# the same vocabulary the seniority gate already uses, so the two never drift.
_LEADERSHIP_WORDS = ("chief", "c-level", "founder", "co-founder", "president",
                     "owner", "partner", "vp", "svp", "evp", "vice president",
                     "head of", "director", "principal")

_MANAGER_WORDS = ("manager", "lead", "team lead", "supervisor", "chapter lead",
                  "engineering manager", "product owner")


def _word(haystack: str, *words: str) -> bool:
    """Whole-word match. Substrings lie: "lead" fires inside "leaderboard" and
    "hr" inside "through" - the same lesson the seniority gate learned."""
    for word in words:
        if re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", haystack):
            return True
    return False


def classify(headline: str | None) -> str:
    """Which audience a person belongs to, from their headline alone."""
    hay = " ".join((headline or "").lower().split())
    if not hay:
        return OTHER
    if _word(hay, *_RECRUITER_WORDS):
        return RECRUITER
    if _word(hay, *_LEADERSHIP_WORDS) or seniority.title_level(hay) in (
            "chief", "director", "vp", "head of", "c-level", "principal"):
        return LEADERSHIP
    if _word(hay, *_MANAGER_WORDS):
        return HIRING_MANAGER
    return PEER


def route(degree: int | None) -> str:
    """What channel is actually open to this person."""
    if degree == 1:
        return DIRECT
    if degree == 2:
        return INVITE
    if degree is None:
        return INVITE          # unknown: assume the safe, two-step path
    return UNREACHABLE


def relevance(audience: str, headline: str | None, job_title: str | None) -> int:
    """0-3, how close this person sits to the decision on THIS job.

    A hiring manager whose headline echoes the job title outranks a recruiter,
    who outranks a random peer. Leadership is worth reaching at a small company
    and noise at a large one, which is why it sits below the hiring manager
    rather than above."""
    overlap = _title_overlap(headline, job_title)
    if audience == HIRING_MANAGER:
        return 3 if overlap else 2
    if audience == RECRUITER:
        return 2
    if audience == LEADERSHIP:
        return 2 if overlap else 1
    if audience == PEER:
        return 1 if overlap else 0
    return 0


_STOPWORDS = frozenset(
    "the a an and or of for to in at with senior junior lead head chief "
    "manager director specialist coordinator associate assistant officer "
    "remote hybrid onsite full time part".split())


def _title_overlap(headline: str | None, job_title: str | None) -> bool:
    """True when the person works on the same thing the job is about.

    Generic words are stripped first: every second headline contains "manager",
    and matching on it would make the whole ranking meaningless."""
    def terms(text: str | None) -> set[str]:
        words = re.findall(r"[a-z]{3,}", (text or "").lower())
        return {w for w in words if w not in _STOPWORDS}

    left, right = terms(headline), terms(job_title)
    if left & right:
        return True
    # Endings differ more often than meanings do: "Designer" against "Design",
    # "Operations" against "Operational". Compare on the shared stem instead,
    # requiring four characters so "ops" cannot match "operations by accident".
    return any(a.startswith(b) or b.startswith(a)
               for a in left for b in right
               if min(len(a), len(b)) >= 4)
