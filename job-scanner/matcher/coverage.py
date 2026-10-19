"""Where the vacancy's demands are answered by the candidate's own record.

The deep check already says "you fit, here are three strengths". That is an
opinion, and an opinion about your career is exactly the thing you cannot check.
This module turns it into something checkable: each claim is pinned to the
sentence in the advert that prompted it, and to the story or line in the CV that
answers it.

THE MODEL DOES NOT GET TO REWRITE THE ADVERT. It returns short quotes; the code
finds each one in the real description and marks it there. A quote that is not
present character for character is dropped, never approximated - a highlight
sitting on the neighbouring sentence is worse than no highlight, because it
looks like evidence.

The same rule covers attribution: a case story is named by its title, and a
title that is not in the case bank is thrown away rather than shown. Otherwise
the one place claiming to be proof would be the easiest place to invent.
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# The three answers a requirement can get.
COVERED = "covered"     # green - the record answers this
PARTIAL = "partial"     # amber - adjacent, arguable, not direct
MISSING = "missing"     # red   - nothing in the record answers it
VERDICTS = (COVERED, PARTIAL, MISSING)

LABELS = {COVERED: "You have this", PARTIAL: "Partly", MISSING: "Not in your record"}

# A quote is a demand, not a paragraph. Longer than this and the highlight stops
# pointing at anything in particular, so the digest shows a trimmed version -
# the highlight itself still covers whatever actually matched.
DIGEST_CHARS = 120

# More than this and the page is a wall of colour, which reads as decoration
# rather than as findings.
MAX_MARKS = 14


@dataclass
class Mark:
    """One demand from the advert, and what answers it."""
    start: int
    end: int
    verdict: str
    quote: str                  # exactly as it appears in the description
    source: str = ""            # case story title, or "CV", or ""
    evidence: str = ""          # one line: what the candidate actually did

    @property
    def digest(self) -> str:
        text = " ".join(self.quote.split())
        return text if len(text) <= DIGEST_CHARS else text[:DIGEST_CHARS - 1].rstrip() + "…"

    @property
    def attribution(self) -> str:
        """What to show under the quote. A case story is named; the CV is quoted."""
        if self.source and self.source != "CV":
            return self.source
        return self.evidence


@dataclass
class Coverage:
    marks: list[Mark] = field(default_factory=list)
    dropped: int = 0            # quotes that were not in the description

    @property
    def counts(self) -> dict[str, int]:
        return {v: sum(1 for m in self.marks if m.verdict == v) for v in VERDICTS}

    def __bool__(self) -> bool:
        return bool(self.marks)


def _norm(text: str) -> str:
    """Whitespace-insensitive form. Adverts are full of hard line breaks and
    double spaces, and a model quoting them collapses those without meaning to.
    Nothing else is normalised: a changed word is a changed quote."""
    return re.sub(r"\s+", " ", text or "").strip()


def _find(description: str, quote: str) -> tuple[int, int] | None:
    """Where this quote sits in the description, tolerating only whitespace.

    Matching is done on a normalised copy and mapped back to real offsets, so
    the marked text is the original with its own line breaks intact."""
    quote_n = _norm(quote)
    if len(quote_n) < 8:        # too short to be a demand; would match anywhere
        return None

    # Map every non-space character of the original to its index.
    positions: list[int] = []
    flat: list[str] = []
    previous_space = True
    for i, ch in enumerate(description):
        if ch.isspace():
            if not previous_space:
                flat.append(" ")
                positions.append(i)
            previous_space = True
            continue
        flat.append(ch)
        positions.append(i)
        previous_space = False
    haystack = "".join(flat)

    at = haystack.find(quote_n)
    if at < 0:
        # Case-insensitive is still exact wording, only a different shift key.
        at = haystack.lower().find(quote_n.lower())
        if at < 0:
            return None
    start = positions[at]
    end = positions[at + len(quote_n) - 1] + 1
    return start, end


def build(description: str, findings: list[dict], case_titles: list[str] | None = None
          ) -> Coverage:
    """Turn the model's findings into marks on the real description."""
    if not (description or "").strip() or not findings:
        return Coverage()
    known = {t.strip().lower(): t.strip() for t in (case_titles or []) if t.strip()}

    marks: list[Mark] = []
    dropped = 0
    for item in findings:
        if not isinstance(item, dict):
            continue
        verdict = str(item.get("verdict") or "").strip().lower()
        if verdict not in VERDICTS:
            continue
        span = _find(description, str(item.get("quote") or ""))
        if span is None:
            dropped += 1
            continue

        source = str(item.get("source") or "").strip()
        # A story the candidate never wrote is not evidence. Keep the finding,
        # drop the claim about where it came from.
        if source and source.upper() != "CV" and source.lower() not in known:
            logger.info("Coverage cited a case that does not exist: %.60s", source)
            source = ""
        elif source and source.upper() == "CV":
            source = "CV"
        elif source:
            source = known[source.lower()]

        start, end = span
        marks.append(Mark(
            start=start, end=end, verdict=verdict,
            quote=description[start:end],
            source=source,
            evidence=" ".join(str(item.get("evidence") or "").split()),
        ))

    marks = _without_overlaps(marks)
    if dropped:
        logger.info("Coverage: %d of %d quotes were not in the description",
                    dropped, dropped + len(marks))
    return Coverage(marks=marks[:MAX_MARKS], dropped=dropped)


def _without_overlaps(marks: list[Mark]) -> list[Mark]:
    """Two marks cannot share a character - the markup would not nest and the
    reader could not tell which colour belonged to which claim. The longer span
    wins, being the more specific quote; ties go to the earlier one."""
    ordered = sorted(marks, key=lambda m: (-(m.end - m.start), m.start))
    kept: list[Mark] = []
    for mark in ordered:
        if any(mark.start < k.end and k.start < mark.end for k in kept):
            continue
        kept.append(mark)
    return sorted(kept, key=lambda m: m.start)


def render(description: str, coverage: Coverage) -> str:
    """The description as HTML, with the marks wrapped in place.

    Everything is escaped; the only tags in the output are the ones written
    here. The description is a stranger's text and it is never trusted."""
    if not coverage.marks:
        return html.escape(description or "")
    out: list[str] = []
    at = 0
    for mark in coverage.marks:
        out.append(html.escape(description[at:mark.start]))
        title = mark.attribution or LABELS[mark.verdict]
        out.append(
            f'<mark class="cov cov--{mark.verdict}" '
            f'data-label="{html.escape(LABELS[mark.verdict])}" '
            f'title="{html.escape(title)}">'
            f"{html.escape(description[mark.start:mark.end])}</mark>"
        )
        at = mark.end
    out.append(html.escape(description[at:]))
    return "".join(out)
