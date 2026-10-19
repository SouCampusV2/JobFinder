"""The evidence behind the deep check.

"You fit, here are three strengths" is an opinion about someone's career, which
is the one thing they cannot check. Coverage pins each claim to the sentence in
the advert that prompted it and to the story that answers it - so every rule
here exists to stop that evidence from being invented.
"""

from __future__ import annotations

from matcher import coverage as cov

AD = """Product Operations Manager

We are looking for someone with 5+ years in B2B SaaS delivery.
You will own the release process across three engineering teams.
Fluent German is required.
We offer a great culture and free fruit."""

CASES = ["Release cycle turnaround", "Vendor consolidation"]


def _finding(quote, verdict="covered", source="", evidence=""):
    return {"quote": quote, "verdict": verdict, "source": source, "evidence": evidence}


# --------------------------------------------------------------------------- #
# The advert is never rewritten                                                #
# --------------------------------------------------------------------------- #

def test_a_quote_that_is_not_in_the_advert_is_dropped():
    """The whole point. A highlight is a claim that the text says something, and
    a model that paraphrases would make the app assert it about words nobody
    published."""
    found = cov.build(AD, [_finding("7+ years in B2B SaaS delivery")], CASES)

    assert found.marks == []
    assert found.dropped == 1


def test_the_marked_text_is_the_advert_character_for_character():
    found = cov.build(AD, [_finding("5+ years in B2B SaaS delivery")], CASES)

    mark = found.marks[0]
    assert AD[mark.start:mark.end] == "5+ years in B2B SaaS delivery"
    assert mark.quote == "5+ years in B2B SaaS delivery"


def test_line_breaks_and_double_spaces_do_not_defeat_a_true_quote():
    """Adverts are full of hard wrapping and a model quoting them collapses it
    without meaning to. Whitespace is the ONLY thing forgiven."""
    ad = "You will own\nthe release   process across three teams."
    found = cov.build(ad, [_finding("own the release process")], CASES)

    assert len(found.marks) == 1
    # …and the marked range is the original text, wrapping intact.
    assert "\n" in ad[found.marks[0].start:found.marks[0].end]


def test_a_changed_word_is_a_changed_quote():
    """Whitespace is forgiven; wording is not. 'three' → 'several' is the model
    rewriting the requirement it is supposed to be citing."""
    found = cov.build(AD, [_finding("own the release process across several "
                                    "engineering teams")], CASES)

    assert found.marks == []


def test_a_fragment_too_short_to_mean_anything_is_refused():
    """Two words match half the page and would colour the wrong thing."""
    assert cov.build(AD, [_finding("teams")], CASES).marks == []


# --------------------------------------------------------------------------- #
# Attribution cannot be invented either                                        #
# --------------------------------------------------------------------------- #

def test_a_case_story_that_does_not_exist_is_not_shown():
    """The one place claiming to be proof is the easiest place to make things
    up. The finding survives; the false claim about where it came from does not."""
    found = cov.build(AD, [_finding("5+ years in B2B SaaS delivery",
                                    source="Global Rollout of SAP")], CASES)

    assert len(found.marks) == 1
    assert found.marks[0].source == ""


def test_a_real_case_story_is_kept_under_its_own_title():
    found = cov.build(AD, [_finding("5+ years in B2B SaaS delivery",
                                    source="release cycle turnaround")], CASES)

    assert found.marks[0].source == "Release cycle turnaround", "the stored spelling wins"
    assert found.marks[0].attribution == "Release cycle turnaround"


def test_the_cv_answers_with_one_line_of_what_was_actually_done():
    found = cov.build(AD, [_finding("Fluent German is required", verdict="partial",
                                    source="CV", evidence="B1 German, daily standups in German")],
                      CASES)

    assert found.marks[0].source == "CV"
    assert found.marks[0].attribution == "B1 German, daily standups in German"


def test_a_missing_requirement_claims_nothing():
    found = cov.build(AD, [_finding("Fluent German is required", verdict="missing")], CASES)

    assert found.marks[0].verdict == "missing"
    assert found.marks[0].attribution == ""


def test_an_unknown_verdict_is_not_rendered_as_a_colour():
    assert cov.build(AD, [_finding("5+ years in B2B SaaS delivery", verdict="maybe")],
                     CASES).marks == []


# --------------------------------------------------------------------------- #
# Two claims cannot own the same words                                         #
# --------------------------------------------------------------------------- #

def test_overlapping_marks_are_resolved_to_the_more_specific_one():
    """Nested markup would not render, and the reader could not tell which
    colour belonged to which claim."""
    found = cov.build(AD, [
        _finding("5+ years in B2B SaaS delivery"),
        _finding("years in B2B SaaS", verdict="partial"),
    ], CASES)

    assert len(found.marks) == 1
    assert found.marks[0].quote == "5+ years in B2B SaaS delivery"


def test_marks_come_back_in_reading_order():
    found = cov.build(AD, [
        _finding("Fluent German is required", verdict="missing"),
        _finding("5+ years in B2B SaaS delivery"),
    ], CASES)

    assert [m.start for m in found.marks] == sorted(m.start for m in found.marks)


# --------------------------------------------------------------------------- #
# Rendering                                                                    #
# --------------------------------------------------------------------------- #

def test_the_advert_cannot_inject_markup():
    """A description is a stranger's text on the internet, and it is now being
    printed as HTML rather than escaped by the template."""
    ad = 'Requires <script>alert(1)</script> and 5+ years of "delivery" & rigour.'
    found = cov.build(ad, [_finding("5+ years of \"delivery\" & rigour")], CASES)
    out = cov.render(ad, found)

    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "&amp;" in out and "&quot;" in out
    assert out.count("<mark") == 1


def test_an_unmarked_advert_is_still_escaped():
    assert cov.render("a < b & c", cov.Coverage()) == "a &lt; b &amp; c"


def test_the_evidence_travels_with_the_mark():
    found = cov.build(AD, [_finding("5+ years in B2B SaaS delivery",
                                    source="Release cycle turnaround")], CASES)
    out = cov.render(AD, found)

    assert 'class="cov cov--covered"' in out
    assert 'title="Release cycle turnaround"' in out


def test_a_long_quote_is_trimmed_in_the_digest_but_marked_in_full():
    """He reads the digest as a list, and a paragraph in a list is not a list."""
    long_ad = "You will " + "own the release process across many teams " * 6 + "here."
    quote = long_ad[9:9 + 240]
    found = cov.build(long_ad, [_finding(quote)], CASES)

    mark = found.marks[0]
    assert len(mark.digest) <= cov.DIGEST_CHARS
    assert mark.digest.endswith("…")
    assert mark.end - mark.start > cov.DIGEST_CHARS, "the highlight itself is not trimmed"


def test_the_page_is_not_turned_into_a_wall_of_colour():
    findings = [_finding(f"unique requirement number {i} spelled out here")
                for i in range(30)]
    ad = "\n".join(f["quote"] for f in findings)

    assert len(cov.build(ad, findings, CASES).marks) <= cov.MAX_MARKS


def test_no_findings_leaves_the_description_exactly_as_it_was():
    """The colour is an addition. Without it the page must be what it was."""
    assert cov.build(AD, [], CASES).marks == []
    assert cov.build("", [_finding("anything at all here")], CASES).marks == []


# --------------------------------------------------------------------------- #
# End to end, through the app                                                  #
# --------------------------------------------------------------------------- #

async def test_the_check_stores_only_verified_findings(db, add_job, monkeypatch):
    """Verification happens before storage, so a bad quote never reaches the
    database and cannot be resurrected by a later page load."""
    import json

    import main
    from fastapi.testclient import TestClient
    from matcher.matcher import AdvancedResult

    job_id = await add_job(score=90, description=AD)
    await db.add_case("Cut release cycle time 40%.", "Release cycle turnaround")

    async def _fake(self, job, profile):
        return AdvancedResult(
            strengths=["Owns delivery"], weaknesses=[], score=80,
            coverage=[
                _finding("5+ years in B2B SaaS delivery", source="Release cycle turnaround"),
                _finding("10+ years of Kubernetes"),          # not in the advert
                _finding("Fluent German is required", verdict="missing"),
            ])

    monkeypatch.setattr(main.AIMatcher, "advanced", _fake)
    with TestClient(main.app) as client:
        client.post(f"/jobs/{job_id}/advanced", follow_redirects=False)

    stored = json.loads((await db.get_assets(job_id))[main.COVERAGE_KIND])
    assert len(stored) == 2, "the invented quote must not be stored"
    assert {s["verdict"] for s in stored} == {"covered", "missing"}


async def test_the_job_page_shows_the_marks(db, add_job, monkeypatch):
    import main
    from fastapi.testclient import TestClient
    from matcher.matcher import AdvancedResult

    job_id = await add_job(score=90, description=AD)
    await db.add_case("Cut release cycle time 40%.", "Release cycle turnaround")

    async def _fake(self, job, profile):
        return AdvancedResult(
            strengths=["s"], weaknesses=[], score=80,
            coverage=[_finding("5+ years in B2B SaaS delivery",
                               source="Release cycle turnaround"),
                      _finding("Fluent German is required", verdict="missing")])

    monkeypatch.setattr(main.AIMatcher, "advanced", _fake)
    with TestClient(main.app) as client:
        client.post(f"/jobs/{job_id}/advanced", follow_redirects=False)
        page = client.get(f"/jobs/{job_id}").text

    assert 'class="cov cov--covered"' in page
    assert 'class="cov cov--missing"' in page
    assert "Release cycle turnaround" in page
    assert "1 you have" in page and "1 not in your record" in page


async def test_a_job_never_checked_shows_a_plain_description(db, add_job):
    """The feature is additive. Without a check the page is what it was."""
    from fastapi.testclient import TestClient

    import main

    job_id = await add_job(score=90, description=AD)
    with TestClient(main.app) as client:
        page = client.get(f"/jobs/{job_id}").text

    assert "<mark class=\"cov" not in page, "nothing is marked without a check"
    assert '<div class="cov-legend">' not in page
    assert "5+ years in B2B SaaS delivery" in page


async def test_a_redescribed_job_does_not_keep_stale_highlights(db, add_job, monkeypatch):
    """Descriptions get re-fetched and enriched. Stored character offsets would
    then point at the wrong words, so the marks are rebuilt from the quotes."""
    import main
    from fastapi.testclient import TestClient
    from matcher.matcher import AdvancedResult

    job_id = await add_job(score=90, description=AD)

    async def _fake(self, job, profile):
        return AdvancedResult(strengths=["s"], weaknesses=[], score=80,
                              coverage=[_finding("5+ years in B2B SaaS delivery")])

    monkeypatch.setattr(main.AIMatcher, "advanced", _fake)
    with TestClient(main.app) as client:
        client.post(f"/jobs/{job_id}/advanced", follow_redirects=False)
        await db.update_job_description(job_id, "PREAMBLE ADDED LATER.\n\n" + AD)
        page = client.get(f"/jobs/{job_id}").text

    marked = page[page.index('<mark class="cov'):]
    assert marked.startswith('<mark class="cov cov--covered"')
    assert "5+ years in B2B SaaS delivery</mark>" in marked
