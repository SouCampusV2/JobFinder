"""The letterhead a cover letter is printed on.

The PDF used to be the letter body alone: no date, no addressee, no sender
block. Next to the CV, which does have a document layout, it read as a note.
"""

from __future__ import annotations

from datetime import date


import letter_template as lt


def test_the_default_template_uses_every_placeholder_it_documents():
    for name in lt.PLACEHOLDERS:
        assert "{{" + name + "}}" in lt.DEFAULT_TEMPLATE


def test_the_letter_body_is_placed_into_the_letterhead():
    out = lt.render(lt.DEFAULT_TEMPLATE, body_html="<p>Dear Hiring Team,</p>",
                    company="Docplanner", job_title="Design Coordinator")

    assert "Dear Hiring Team," in out
    assert "Docplanner" in out
    assert "Design Coordinator" in out
    assert "{{" not in out


def test_a_company_name_with_punctuation_cannot_break_the_document():
    out = lt.render("<div>{{company}}</div>", body_html="", company="Smith & <Sons>")

    assert "&amp;" in out and "&lt;Sons&gt;" in out


def test_a_multi_line_address_keeps_its_lines():
    out = lt.render("<div>{{company_address}}</div>", body_html="",
                    company_address="Musterstraße 1\n10115 Berlin")

    assert "<br>" in out
    assert "Musterstra" in out


def test_the_body_is_not_escaped_because_it_is_already_html():
    out = lt.render("{{body}}", body_html="<p>Two</p><p>paragraphs</p>")

    assert out == "<p>Two</p><p>paragraphs</p>"


def test_an_unknown_placeholder_is_left_visible():
    """Blanking it would hide the typo; leaving it shows the user what to fix."""
    out = lt.render("{{company}} {{invented}}", body_html="", company="X")

    assert out == "X {{invented}}"


def test_the_date_reads_like_a_letter_not_a_timestamp():
    assert lt.format_date(date(2026, 8, 2)) == "2 August 2026"


def test_whitespace_inside_a_placeholder_is_tolerated():
    assert lt.render("{{ company }}", body_html="", company="X") == "X"


def test_the_document_carries_its_own_print_styles():
    doc = lt.document(lt.DEFAULT_TEMPLATE, body_html="<p>x</p>", company="X")

    assert doc.startswith("<!doctype html>")
    assert "@page" in doc and "A4" in doc


async def test_the_shipped_default_is_used_until_the_user_writes_one(db):
    assert await db.get_letter_template() == lt.DEFAULT_TEMPLATE


async def test_a_saved_template_wins(db):
    await db.save_letter_template("<div>mine {{body}}</div>")

    assert await db.get_letter_template() == "<div>mine {{body}}</div>"


async def test_clearing_the_template_restores_the_default(db):
    await db.save_letter_template("<div>mine</div>")

    await db.save_letter_template("   ")

    assert await db.get_letter_template() == lt.DEFAULT_TEMPLATE
