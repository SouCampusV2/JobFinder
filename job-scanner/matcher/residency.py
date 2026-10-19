"""Residency requirements, read in code rather than left to the model.

A remote posting can still demand that you *live* somewhere: "our partner is
looking for a Design Coordinator based in Switzerland". Nothing about that is a
relocation outside Europe and nothing about it is on-site, so a rule set written
as "accept remote within Europe / reject relocation outside Europe" accepts it -
and the model was right to score it 85. The rule simply had no concept of
residency.

Two traps this module is built around:

* **Whose country is it?** "A company based in Switzerland" is not "a candidate
  based in Switzerland". The same mistake once read a CEO's biography as a years
  requirement, so the patterns here anchor on the PERSON being hired and a
  company word standing between the verb and "based in" disqualifies the match.
* **A region is not a residency.** Someone who accepts "remote within Europe"
  has not thereby become a Swiss resident. Only a country the candidate named
  for themselves satisfies a country-specific requirement.

Nothing personal is hardcoded: which countries the candidate can work from is
read from their own instructions, and when they name none, nothing is blocked.
"""

from __future__ import annotations

import re

# Countries a posting might demand residency in. Kept to Europe plus the
# handful of non-European countries that show up in European job feeds - a
# posting demanding residency somewhere not on this list is rare enough that
# missing it costs less than a bad guess would.
_COUNTRIES: dict[str, str] = {
    "united kingdom": "United Kingdom", "great britain": "United Kingdom",
    "uk": "United Kingdom", "england": "United Kingdom", "scotland": "United Kingdom",
    "wales": "United Kingdom", "ireland": "Ireland", "germany": "Germany",
    "deutschland": "Germany", "france": "France", "spain": "Spain",
    "españa": "Spain", "portugal": "Portugal", "italy": "Italy",
    "netherlands": "Netherlands", "the netherlands": "Netherlands",
    "belgium": "Belgium", "luxembourg": "Luxembourg", "austria": "Austria",
    "switzerland": "Switzerland", "poland": "Poland", "czechia": "Czechia",
    "czech republic": "Czechia", "slovakia": "Slovakia", "hungary": "Hungary",
    "romania": "Romania", "bulgaria": "Bulgaria", "greece": "Greece",
    "croatia": "Croatia", "slovenia": "Slovenia", "serbia": "Serbia",
    "denmark": "Denmark", "sweden": "Sweden", "norway": "Norway",
    "finland": "Finland", "iceland": "Iceland", "estonia": "Estonia",
    "latvia": "Latvia", "lithuania": "Lithuania", "ukraine": "Ukraine",
    "moldova": "Moldova", "cyprus": "Cyprus", "malta": "Malta",
    "turkey": "Turkey", "united states": "United States", "usa": "United States",
    "canada": "Canada", "india": "India", "australia": "Australia",
    "singapore": "Singapore", "brazil": "Brazil", "mexico": "Mexico",
    "israel": "Israel", "south africa": "South Africa",
}

# Longest first so "united kingdom" wins over "uk" inside the same sentence.
_COUNTRY_ALT = "|".join(
    re.escape(name) for name in sorted(_COUNTRIES, key=len, reverse=True))

# Words naming the person being hired. "looking for a Design Coordinator based
# in Switzerland" must match; "a company based in Switzerland" must not.
_ROLE_WORD = (
    r"candidates?|applicants?|you|talent|professionals?|someone|somebody|"
    r"hires?|employees?|contractors?|freelancers?|"
    r"[a-z]*(?:manager|coordinator|specialist|engineer|designer|analyst|"
    r"developer|consultant|associate|director|lead|assistant|officer|architect)s?"
)

# Phrases that mean the country belongs to the COMPANY, not to the person.
_COMPANY_CONTEXT = re.compile(
    r"\b(?:compan(?:y|ies)|firm|business|startup|start-up|organi[sz]ation|group|"
    r"agency|client|partner|employer|team|office|offices|headquarters|hq|"
    r"headquartered|founded|incorporated|registered|brand|subsidiary)\b",
    re.IGNORECASE)

_PATTERNS: tuple[re.Pattern[str], ...] = (
    # "looking for a Design Coordinator based in Switzerland"
    re.compile(rf"(?:looking for|seeking|hiring|recruiting)\s+(?:an?\s+)?"
               rf"[\w\s/&,-]{{0,60}}?\b(?:based|located|living|residing)\s+in\s+"
               rf"(?:the\s+)?({_COUNTRY_ALT})\b", re.IGNORECASE),
    # "candidates must be based in Germany", "you should be located in Spain"
    re.compile(rf"\b(?:{_ROLE_WORD})\b[^.]{{0,40}}?\b(?:must|should|need to|have to|"
               rf"are required to)\s+(?:be\s+)?(?:based|located|living|residing|reside)\s+"
               rf"(?:in|within)\s+(?:the\s+)?({_COUNTRY_ALT})\b", re.IGNORECASE),
    # "must reside in Ireland", "must be located in Portugal"
    re.compile(rf"\bmust\s+(?:be\s+)?(?:reside|residing|based|located|living)\s+"
               rf"(?:in|within)\s+(?:the\s+)?({_COUNTRY_ALT})\b", re.IGNORECASE),
    # "open to residents of Poland", "residents of Spain only"
    re.compile(rf"\bresidents?\s+of\s+(?:the\s+)?({_COUNTRY_ALT})\b", re.IGNORECASE),
    # "you must be legally authorised to work in Germany"
    re.compile(rf"\b(?:authori[sz]ed|eligible|permitted|right)\s+to\s+work\s+"
               rf"(?:in|within)\s+(?:the\s+)?({_COUNTRY_ALT})\b", re.IGNORECASE),
    # "open to candidates based in Germany, Spain, Portugal or the UK"
    re.compile(rf"\bopen to\s+(?:{_ROLE_WORD})\s+(?:who\s+(?:are|is)\s+)?"
               rf"(?:based|located|living|residing)\s+(?:in|within)\s+(?:the\s+)?"
               rf"({_COUNTRY_ALT})\b", re.IGNORECASE),
    # "a Germany-based role", "UK based", "Spain-based team member"
    # The trailing word is captured on purpose: "Germany-based role" is the
    # job, "Germany-based company" is the employer's address, and the company
    # guard can only veto what the match itself contains.
    re.compile(rf"\b(?:the\s+)?(?:role|position|candidate|hire|you)?\s*(?:is\s+|will\s+be\s+)?"
               rf"({_COUNTRY_ALT})[- ]based\s*(?:\w+)?", re.IGNORECASE),
    # "Remote (Germany)", "Remote - Germany", "Remote, Germany", "Remote | UK"
    re.compile(rf"\bremote\s*[(\[|,–-]\s*(?:in\s+|from\s+)?(?:the\s+)?"
               rf"({_COUNTRY_ALT})\b", re.IGNORECASE),
    # "Location: Germany", "Country: Poland", "Work location - Spain"
    re.compile(rf"\b(?:work\s+)?(?:location|country|based)\s*[:–-]\s*(?:the\s+)?"
               rf"({_COUNTRY_ALT})\b", re.IGNORECASE),
    # "this role is open to candidates in Sweden only"
    re.compile(rf"\b(?:{_ROLE_WORD})\s+(?:based\s+)?in\s+(?:the\s+)?"
               rf"({_COUNTRY_ALT})\s+only\b", re.IGNORECASE),
)

# How much of the posting to read. Residency requirements are stated up front -
# the Jobgether template puts it in the very first sentence - and scanning the
# whole body only adds chances to trip over a company address in the footer.
_HEAD_CHARS = 1500

# Continuation of a country list. The separator may be two words at once -
# "Ukraine, Portugal, or Poland" - and an earlier version that allowed only one
# silently dropped the last country of every Oxford-comma list.
_LIST_TAIL = re.compile(
    rf"(?:,\s*(?:or\s+|and\s+)?|\s+(?:or|and)\s+|\s*/\s*)"
    rf"(?:the\s+)?({_COUNTRY_ALT})\b", re.IGNORECASE)

# Abbreviations spelled with dots defeat the word boundaries above. Only these
# three are expanded: a bare "US" cannot be, because "us" is also a pronoun
# ("join us in Berlin") and would fire on half the postings in the database.
_ABBREVIATIONS = (("U.S.A.", "United States"), ("U.K.", "United Kingdom"),
                  ("U.S.", "United States"))

def required_countries(description: str | None) -> set[str]:
    """Every country a posting will accept the hire living in.

    A set, not one country, because the requirement is usually a list: "open to
    candidates based in Germany, Spain, Portugal or the UK". Reading only the
    first name would have blocked that posting for someone in Spain, which is
    exactly backwards - Spain is on the list.

    An empty set means the posting does not say, which is the common case and
    must never be read as "anywhere is fine": it means no gate applies."""
    text = " ".join((description or "")[:_HEAD_CHARS].split())
    for dotted, plain in _ABBREVIATIONS:
        text = text.replace(dotted, plain)
    for pattern in _PATTERNS:
        for match in pattern.finditer(text):
            # Look INSIDE the match only. Reading the text before it as well
            # threw away the commonest real case there is: "Our partner is
            # looking for a Design Coordinator based in Switzerland" - the word
            # "partner" sits in front, but the country plainly belongs to the
            # coordinator. What must disqualify a match is a company word
            # standing between the verb and "based in", as in "looking for a
            # partner company based in Germany".
            if _COMPANY_CONTEXT.search(match.group(0)):
                continue
            found = {_COUNTRIES[match.group(1).lower()]}
            pos = match.end()
            while (tail := _LIST_TAIL.match(text, pos)) is not None:
                found.add(_COUNTRIES[tail.group(1).lower()])
                pos = tail.end()
            return found
    return set()


def country_of(location: str | None) -> str | None:
    """The country a location string names, if any.

    "United Kingdom (Remote)" is the United Kingdom whatever the chip says: the
    parenthetical describes the desk, not the border."""
    text = " ".join((location or "").split())
    for dotted, plain in _ABBREVIATIONS:
        text = text.replace(dotted, plain)
    match = re.search(rf"\b({_COUNTRY_ALT})\b", text, re.IGNORECASE)
    return _COUNTRIES[match.group(1).lower()] if match else None


def home_countries(instructions: str | None) -> set[str]:
    """Countries the candidate said they can work from, in their own words.

    Read from the lines under their LOCATION heading, before any "Reject"
    heading. An empty set disables the gate entirely - this never invents a
    home for someone who did not state one."""
    text = instructions or ""
    match = re.search(r"^\s*LOCATION\b.*$", text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return set()
    # Their location rules run until the next ALL-CAPS heading or a horizontal
    # rule, whichever comes first.
    chunk = text[match.end():]
    chunk = re.split(r"\n\s*-{3,}|\n[A-Z][A-Z /()]{3,}:", chunk)[0]
    # Only the "accept" half: a country named under Reject is not a home.
    reject = re.search(r"^\s*(reject|not interested|avoid|exclude)\b",
                       chunk, re.IGNORECASE | re.MULTILINE)
    if reject:
        chunk = chunk[:reject.start()]
    found = set()
    for name in re.findall(rf"\b({_COUNTRY_ALT})\b", chunk, re.IGNORECASE):
        found.add(_COUNTRIES[name.lower()])
    return found


# Phrases that widen a country-specific card back out. A posting whose card
# says "Poland (Remote)" but whose body says "anywhere in Europe" is open.
_WIDE_OPEN = re.compile(
    r"\banywhere in (?:the )?(?:europe|world|eu)\b|\bacross europe\b"
    r"|\beurope[- ]wide\b|\beu[- ]wide\b|\bany (?:eu|european) country\b"
    r"|\bremote (?:in|across|within) europe\b|\bemea[- ]wide\b"
    r"|\bfully remote worldwide\b|\bwork from anywhere\b", re.IGNORECASE)

# How much of the body to read for that. Same window as the requirement scan.
_WIDE_CHARS = 2500


def card_country(job: dict) -> str | None:
    """The country a REMOTE card names, or None.

    Deliberately NOT used as a gate. Companies fill the location field with
    their own address and then hire across Europe anyway, so blocking on it
    alone removed 108 of 138 jobs from the review list - most of them wrongly.
    What counts is the DESCRIPTION saying it outright, which `required_countries`
    reads. This stays for the vacancy block, where the model can weigh it."""
    where = country_of(job.get("location"))
    if not where:
        return None
    body = " ".join((job.get("description") or "")[:_WIDE_CHARS].split())
    if _WIDE_OPEN.search(body):
        return None
    return where


def blocking_countries(job: dict, instructions: str | None) -> set[str]:
    """The residency requirement the candidate does not satisfy, or an empty set.

    Empty when the posting says nothing, when the candidate named no country of
    their own, or when ANY country the posting accepts is one they named."""
    home = home_countries(instructions)
    if not home:
        return set()           # nothing stated by the candidate - nothing to enforce

    required = required_countries(job.get("description"))
    if required:
        return set() if required & home else required

    return set()


def as_text(countries: set[str]) -> str:
    """"Germany, Portugal or Spain" - stable order so prompts stay cacheable."""
    names = sorted(countries)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def signals(job: dict) -> list[str]:
    """Human-readable residency facts for the vacancy block sent to the model."""
    required = required_countries(job.get("description"))
    if not required:
        return []
    return [f"Residency required: {as_text(required)} (the hire must live there)"]
