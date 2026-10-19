"""The letterhead a cover letter is printed on.

The PDF used to be the letter body and nothing else: no date, no addressee, no
sender block. That is a note, not a letter, and it looks like one next to the
CV - which does have a proper document layout.

The template is HTML the user owns and can rewrite, because a letterhead is a
personal document and no default will match everyone's. Only the parts that
change per application are placeholders; the sender's own block is typed once,
into the template, exactly as it works on paper.
"""

from __future__ import annotations

import html
import re
from datetime import date

# Placeholders the template may use. Anything else is left alone, so a stray
# brace in the user's own text cannot break the render.
PLACEHOLDERS: dict[str, str] = {
    "date": "Today's date, written out (2 August 2026)",
    "company": "Company name from the job",
    "company_address": "Address you typed for this application",
    "job_title": "Job title from the posting",
    "body": "The letter itself",
}

# Shipped default. Deliberately plain: a business letter, not a design piece.
# The sender block is filled with obvious markers rather than left empty, so it
# is clear at a glance that it needs replacing.
DEFAULT_TEMPLATE = """<div class="sender">
  <div class="sender__name">Your Name</div>
  <div>Your street, City, Country</div>
  <div>you@example.com · +00 000 000 000</div>
  <div>linkedin.com/in/you</div>
</div>

<div class="date">{{date}}</div>

<div class="recipient">
  <div class="recipient__company">{{company}}</div>
  <div>{{company_address}}</div>
</div>

<div class="subject">Application for {{job_title}}</div>

<div class="body">{{body}}</div>
"""

# Print styles for the merged document. Kept next to the template because the
# two only make sense together.
LETTER_CSS = """
@page { size: A4; margin: 22mm 20mm; }
body {
  font-family: Calibri, Carlito, "Segoe UI", Helvetica, Arial, sans-serif;
  color: #111; font-size: 11pt; line-height: 1.5;
}
.sender { margin-bottom: 14mm; font-size: 10pt; line-height: 1.45; }
.sender__name { font-size: 12pt; font-weight: 700; margin-bottom: 2mm; }
.date { margin-bottom: 8mm; }
.recipient { margin-bottom: 10mm; line-height: 1.45; }
.recipient__company { font-weight: 700; }
.subject { font-weight: 700; margin-bottom: 7mm; }
.body p { margin: 0 0 .85em; }
.body h1, .body h2, .body h3 { font-size: 1em; font-weight: 700; margin: 0 0 .6em; }
"""

_TOKEN = re.compile(r"\{\{\s*(\w+)\s*\}\}")

# How long a description of the letterhead may be. Two hundred characters is
# not a technical limit - it is the point. A letterhead is a shape, not a
# document: "no date, put my name on the right, thin rule under it" is the
# whole brief. Given a paragraph, people start describing the letter instead,
# and the model rewrites the layout to suit prose it was never given.
BRIEF_MAX = 200

# The one placeholder a letterhead cannot lose: without it the letter itself
# has nowhere to go, and the user would be saving a blank page with a nice
# heading on it. The others are the user's own design decision - someone who
# says "no date" means it.
REQUIRED = "body"


def missing_tokens(template: str) -> list[str]:
    """Which of the known placeholders this template no longer carries."""
    present = set(_TOKEN.findall(template or ""))
    return [name for name in PLACEHOLDERS if name not in present]


def _sender_block(cv_html: str | None) -> str | None:
    """The sender's own block, built from the CV, or None if it isn't there.

    The letterhead shipped with "Your Name" and "you@example.com" in it, on the
    theory that a sender block is personal and typed once. But the CV already
    holds every line of it - name, city, phone, email, LinkedIn - and a document
    that greets you with placeholder text reads as broken, not as an invitation.
    So it is filled in from the CV, and the markers are what you get only when
    there is no CV to read."""
    from bs4 import BeautifulSoup

    if not (cv_html or "").strip():
        return None
    soup = BeautifulSoup(cv_html, "html.parser")

    def text_of(selector: str) -> str:
        el = soup.select_one(selector)
        return " ".join(el.get_text(" ").split()) if el else ""

    name = text_of(".cv-name")
    if not name:
        return None
    # CVs style the name in caps. A letter is not shouted.
    if name == name.upper():
        name = name.title()

    # The contact line is a pile of separated values in no fixed order, so each
    # one is recognised by what it looks like rather than by its position.
    parts = [p.strip() for p in re.split(r"[|·•]", text_of(".cv-contact")) if p.strip()]
    email = next((p for p in parts if "@" in p), "")
    linkedin = next((p for p in parts if "linkedin." in p.lower()), "")
    phone = next((p for p in parts
                  if p is not email and p is not linkedin
                  and sum(c.isdigit() for c in p) >= 7), "")

    # The subtitle is "Role | City, Country | …". The role belongs on the CV,
    # not above a letter, so only the place is taken.
    subtitle = [p.strip() for p in re.split(r"[|·•]", text_of(".cv-subtitle")) if p.strip()]
    place = next((p for p in subtitle[1:] if "," in p), "")

    lines = [f'  <div class="sender__name">{html.escape(name)}</div>']
    if place:
        lines.append(f"  <div>{html.escape(place)}</div>")
    contact = " · ".join(x for x in (email, phone) if x)
    if contact:
        lines.append(f"  <div>{html.escape(contact)}</div>")
    if linkedin:
        lines.append(f"  <div>{html.escape(linkedin)}</div>")
    return '<div class="sender">\n' + "\n".join(lines) + "\n</div>"


def default_template(cv_html: str | None = None) -> str:
    """The shipped letterhead, with the sender block taken from the CV."""
    sender = _sender_block(cv_html)
    if not sender:
        return DEFAULT_TEMPLATE
    head, _, tail = DEFAULT_TEMPLATE.partition("</div>\n\n<div class=\"date\">")
    return sender + '\n\n<div class="date">' + tail


def format_date(when: date | None = None) -> str:
    """"2 August 2026" - the form a letter uses, not an ISO stamp."""
    when = when or date.today()
    return f"{when.day} {when.strftime('%B %Y')}"


def render(template: str, *, body_html: str, company: str = "",
           company_address: str = "", job_title: str = "",
           when: date | None = None) -> str:
    """Merge the letter into the letterhead.

    Everything except the body is escaped: a company called "Smith & Sons"
    must not become malformed HTML. The body arrives as HTML already, having
    been converted from the markdown the model wrote."""
    values = {
        "date": html.escape(format_date(when)),
        "company": html.escape(company or ""),
        "company_address": html.escape(company_address or "").replace("\n", "<br>"),
        "job_title": html.escape(job_title or ""),
        "body": body_html or "",
    }
    # An unknown token is left as written rather than blanked, so a typo is
    # visible in the output instead of silently eating the line.
    return _TOKEN.sub(lambda m: values.get(m.group(1), m.group(0)), template or "")


def document(template: str, **kwargs) -> str:
    """A complete printable HTML document."""
    return (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        + LETTER_CSS
        + "</style></head><body>"
        + render(template, **kwargs)
        + "</body></html>"
    )
