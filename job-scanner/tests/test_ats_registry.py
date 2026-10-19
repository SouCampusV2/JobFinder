"""The ATS registry: parsers, the Europe gate, and the fairness cap.

No network here - each parser is fed a captured payload shape. The point is the
mapping (does the workplace flag reach the location string? does the date
survive?), because those two fields are what the scoring gates read.
"""

from __future__ import annotations

import json

import pytest

from scrapers import ats


class FakeResponse:
    def __init__(self, payload, status: int = 200):
        self.status_code = status
        self._payload = payload
        self.text = payload if isinstance(payload, str) else json.dumps(payload)

    def json(self):
        if isinstance(self._payload, str):
            raise ValueError("not json")
        return self._payload


class FakeClient:
    """Returns a canned response per call, in order."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls: list[str] = []

    async def get(self, url, **kw):
        self.calls.append(url)
        return self._responses.pop(0) if self._responses else FakeResponse({}, 404)


# --------------------------------------------------------------------------- #
# The Europe gate                                                              #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("location", [
    "Barcelona (Remote)", "Anywhere in Belgium", "All France (remote)",
    "England, United Kingdom", "Tallinn", "Berlin; New York", "Remote", "",
    None, "Warsaw, Poland", "München",
])
def test_european_and_unknown_locations_are_kept(location):
    assert ats._is_european(location)


@pytest.mark.parametrize("location", [
    "Kuwait - Main Office (OnSite)", "Bangalore, India", "São Paulo, Brazil",
    "Mountain View, California; Bellevue", "Chicago; San Francisco",
    "UAE Abu Dhabi", "Singapore", "Toronto, Canada",
])
def test_clearly_non_european_locations_are_dropped(location):
    assert not ats._is_european(location)


def test_a_mixed_location_passes_on_its_european_half():
    # Dropping "Berlin; New York" would lose a real Berlin opening.
    assert ats._is_european("Berlin; New York")


# --------------------------------------------------------------------------- #
# Workplace folding - the reason these sources beat a plain job board           #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("location, workplace, expected", [
    ("Berlin", "Hybrid", "Berlin (Hybrid)"),
    ("Madrid", "", "Madrid"),
    ("", "Remote", "Remote"),
    ("Barcelona (Remote)", "Remote", "Barcelona (Remote)"),   # no doubling
    (None, "On-site", "On-site"),
])
def test_workplace_is_folded_into_the_location(location, workplace, expected):
    assert ats._with_workplace(location, workplace) == expected


async def test_lever_workplace_reaches_the_location():
    client = FakeClient(FakeResponse([{
        "id": "abc", "text": "Project Manager", "workplaceType": "hybrid",
        "categories": {"location": "Paris"}, "descriptionPlain": "body",
        "hostedUrl": "https://jobs.lever.co/x/abc", "createdAt": 1772108232729,
    }]))

    jobs = await ats._fetch_lever(client, "qonto")

    assert jobs[0].location == "Paris (hybrid)"
    assert jobs[0].posted_at.startswith("2026-")
    assert jobs[0].source == "lever"


async def test_ashby_marks_remote_when_only_the_boolean_says_so():
    client = FakeClient(FakeResponse({"jobs": [{
        "id": "1", "title": "Ops Manager", "isRemote": True, "workplaceType": "",
        "location": "Spain", "descriptionPlain": "body",
        "jobUrl": "https://jobs.ashbyhq.com/x/1", "publishedAt": "2026-07-01T00:00:00Z",
    }]}))

    jobs = await ats._fetch_ashby(client, "pleo")

    assert jobs[0].location == "Spain (Remote)"


async def test_ashby_skips_unlisted_postings():
    client = FakeClient(FakeResponse({"jobs": [
        {"id": "1", "title": "Live", "isListed": True, "location": "Berlin"},
        {"id": "2", "title": "Hidden", "isListed": False, "location": "Berlin"},
    ]}))

    jobs = await ats._fetch_ashby(client, "x")

    assert [j.title for j in jobs] == ["Live"]


async def test_recruitee_booleans_become_a_workplace_word():
    client = FakeClient(FakeResponse({"offers": [{
        "id": 1, "title": "Ops", "hybrid": True, "remote": False, "on_site": False,
        "location": "Amsterdam", "description": "<p>body</p>", "requirements": "<p>req</p>",
        "careers_url": "https://x.recruitee.com/o/ops", "published_at": "2026-07-01",
    }]}))

    jobs = await ats._fetch_recruitee(client, "x")

    assert jobs[0].location == "Amsterdam (Hybrid)"
    assert "body" in jobs[0].description and "req" in jobs[0].description


async def test_greenhouse_unescapes_its_double_escaped_html():
    client = FakeClient(FakeResponse({"jobs": [{
        "id": 7, "title": "PM", "company_name": "Celonis",
        "location": {"name": "Munich"},
        "content": "&lt;p&gt;We are hiring&lt;/p&gt;",
        "absolute_url": "https://job-boards.greenhouse.io/celonis/jobs/7",
        "first_published": "2026-07-20T00:00:00Z",
    }]}))

    jobs = await ats._fetch_greenhouse(client, "celonis")

    assert jobs[0].description == "We are hiring"
    assert jobs[0].company == "Celonis"
    assert jobs[0].posted_at == "2026-07-20T00:00:00Z"


async def test_a_failing_board_yields_nothing_instead_of_raising():
    client = FakeClient(FakeResponse({}, 503))

    assert await ats._fetch_greenhouse(client, "gone") == []


# --------------------------------------------------------------------------- #
# The registry file itself                                                     #
# --------------------------------------------------------------------------- #

def test_every_registry_entry_names_a_parser_we_have():
    boards = ats.load_registry()

    assert boards, "the shipped registry must not be empty"
    assert all(b["ats"] in ats._PARSERS for b in boards)
    assert all(b["slug"] for b in boards)


def test_the_registry_has_no_duplicate_boards():
    boards = ats.load_registry()

    keys = [(b["ats"], b["slug"]) for b in boards]
    assert len(keys) == len(set(keys))


def test_a_missing_registry_file_is_not_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(ats, "REGISTRY_PATH", tmp_path / "nope.json")

    assert ats.load_registry() == []


# --------------------------------------------------------------------------- #
# Fairness cap                                                                 #
# --------------------------------------------------------------------------- #

async def test_no_single_board_may_consume_the_whole_quota(monkeypatch):
    """The first version let the first big board to answer fill all 50 slots,
    so the other 116 boards never appeared in the results."""
    from scrapers.base import JobListing

    def rows(company: str, n: int) -> list[JobListing]:
        return [JobListing(source="greenhouse", external_id=f"{company}-{i}",
                           title=f"Manager {company} {i}", company=company,
                           location="Berlin", description="body")
                for i in range(n)]

    boards = [{"ats": "greenhouse", "slug": s} for s in ("big", "small_a", "small_b")]
    monkeypatch.setattr(ats, "load_registry", lambda: boards)

    async def fake_board(client, board):
        return rows(board["slug"], 100)

    monkeypatch.setattr(ats, "_board", fake_board)

    got = [j async for j in ats.iter_ats_boards({"keywords": "manager", "max_jobs": 24})]

    per_company = {}
    for job in got:
        per_company[job.company] = per_company.get(job.company, 0) + 1
    assert len(per_company) == 3, f"one board dominated: {per_company}"
    assert max(per_company.values()) <= 24 // 8 + 1


async def test_the_title_is_what_the_keyword_matches(monkeypatch):
    """Matching the description too let a data-scientist ad through a
    'project manager' search, because both words occur in any long posting."""
    from scrapers.base import JobListing

    monkeypatch.setattr(ats, "load_registry", lambda: [{"ats": "lever", "slug": "x"}])

    async def fake_board(client, board):
        return [
            JobListing(source="lever", external_id="1", title="Data Scientist",
                       company="X", location="Berlin",
                       description="You will work with our project manager daily."),
            JobListing(source="lever", external_id="2", title="Project Manager",
                       company="X", location="Berlin", description="short"),
        ]

    monkeypatch.setattr(ats, "_board", fake_board)

    got = [j async for j in ats.iter_ats_boards({"keywords": "project manager"})]

    assert [j.title for j in got] == ["Project Manager"]
