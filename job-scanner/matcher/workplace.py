"""Office requirements buried in the body of a posting.

`matcher.detect_workplace` reads the card metadata and the first 1200
characters, which is where LinkedIn's chip and most honest postings put the
work arrangement. It missed a whole class of ad: location says "United Kingdom
(Remote)", and three thousand characters down the page sits "fully hybrid
working model, with one two-day onsite session per month in Birmingham".

Reading the whole description for the word "hybrid" is not the fix. Of nine
matches in a real database, seven were something else entirely:

    "project delivery approaches (Agile, Waterfall, or hybrid)"   methodology
    "agile or hybrid delivery methodologies"                      methodology
    "willingness to travel occasionally for on-site meetings"     travel
    "fitness room and external sports ground ... on site"         facilities
    "remote or hybrid model - it's up to you!"                    the choice is
    "welcome to work remotely, on a hybrid basis ... as they wish"  the reader's

So this looks for phrases that describe the ARRANGEMENT of the job itself, and
throws the match away when the surrounding words show it is a methodology, a
trip, a perk, or an option the candidate gets to decline.
"""

from __future__ import annotations

import re

# Phrases that state how the job is worked, not what the team is called.
_REQUIREMENT = re.compile(
    r"\bhybrid\s+(?:working\s+)?(?:model|role|position|setup|set-up|arrangement|"
    r"schedule|pattern|basis|policy|environment)\b"
    r"|\b(?:this|the)\s+(?:role|position|job)\s+is\s+(?:a\s+)?(?:hybrid|on[\s-]?site)\b"
    r"|\b\d+\s*(?:\+\s*)?days?\s+(?:per|a|each)\s+week\s+(?:in|at|from)\s+the\s+office\b"
    r"|\bin\s+the\s+office\s+\d+\s*(?:\+\s*)?days?\b"
    r"|\bon[\s-]?site\s+(?:session|days?|presence|requirement|attendance|work)\b"
    r"|\bexpected\s+to\s+be\s+(?:in\s+the\s+office|on[\s-]?site)\b"
    r"|\brequires?\s+(?:regular\s+)?(?:office\s+attendance|on[\s-]?site\s+presence)\b",
    re.IGNORECASE)

# The match is about a delivery method, not a desk. "Agile, Waterfall, or
# hybrid" is the single commonest false positive in project-management ads.
_METHODOLOGY = re.compile(
    r"\b(?:agile|waterfall|scrum|kanban|safe|methodolog\w*|framework|approach\w*|"
    r"lifecycle|delivery\s+model)\b", re.IGNORECASE)

# The arrangement is offered, not imposed: fully remote is still on the table.
_OPTIONAL = re.compile(
    r"\b(?:up to you|as they wish|as you wish|your choice|your preference|"
    r"if you prefer|you (?:can|may) choose|remote or hybrid|hybrid or remote|"
    r"fully remote or|either\s+\w+\s+or)\b", re.IGNORECASE)

# A trip or a perk that happens to contain the words. "Occasional" is the word
# that separates a requirement from a visit: "occasional on-site work at
# customer locations" in an otherwise remote job is travel, not a desk.
_NOT_THE_JOB = re.compile(
    r"\b(?:travel|trips?|visits?|meetings?|workshops?|offsite|off-site|gym|"
    r"fitness|sports?|canteen|parking|events?|occasional|occasionally|"
    r"from time to time|mostly remote|fully remote)\b", re.IGNORECASE)

# How much text around a match is read to decide what it is about. One sentence
# either side: any wider and an unrelated clause starts vetoing real matches.
_CONTEXT = 130


def requires_office(description: str | None) -> str | None:
    """The office requirement stated in the body, or None.

    Returns the matched phrase so the caller can show the user what was found -
    a gate that silently lowers a score is one nobody trusts."""
    text = " ".join((description or "").split())
    for match in _REQUIREMENT.finditer(text):
        around = text[max(0, match.start() - _CONTEXT): match.end() + _CONTEXT]
        if _METHODOLOGY.search(around) or _OPTIONAL.search(around):
            continue
        if _NOT_THE_JOB.search(around) and "office" not in match.group(0).lower():
            continue
        return match.group(0)
    return None


def signals(job: dict) -> list[str]:
    """A line for the vacancy block, so the model sees what the code saw."""
    found = requires_office(job.get("description"))
    return [f"Office requirement in the body: \"{found}\""] if found else []
