"""State employment boards: Arbeitsagentur (DE) and Platsbanken (SE).

No network. Each test feeds a captured payload shape and checks the mapping,
because the fields that matter here are the ones the scoring gates read: the
posting body, the date, and the remote flag.
"""

from __future__ import annotations

import base64
import json


from scrapers import national


class FakeResponse:
    def __init__(self, payload, status: int = 200):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeClient:
    """Stands in for httpx.AsyncClient, routing by URL substring."""

    def __init__(self, routes: dict[str, FakeResponse]):
        self.routes = routes
        self.requests: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, **kw):
        self.requests.append((url, params or {}))
        # Longest fragment first: the service path is ".../jobsuche-service/...",
        # so a bare "/jobs" also matches the detail URL and would answer a
        # description request with the search payload.
        for fragment in sorted(self.routes, key=len, reverse=True):
            if fragment in url:
                return self.routes[fragment]
        return FakeResponse({}, 404)


def install(monkeypatch, client: FakeClient) -> None:
    monkeypatch.setattr(national.httpx, "AsyncClient", lambda **kw: client)
    monkeypatch.setattr(national.asyncio, "sleep", _no_sleep)


async def _no_sleep(_seconds):
    return None


# --------------------------------------------------------------------------- #
# Germany                                                                      #
# --------------------------------------------------------------------------- #

_BA_SEARCH = FakeResponse({"stellenangebote": [{
    "refnr": "12288-4905218638-S",
    "titel": "Projektmanager (m/w/d)",
    "beruf": "Projektleiter/in",
    "arbeitgeber": "RLE INTERNATIONAL Group",
    "arbeitsort": {"ort": "Ostercappeln", "region": "Niedersachsen"},
    "aktuelleVeroeffentlichungsdatum": "2026-07-30",
    "externeUrl": "https://www.persy.jobs/persy/l/job-jbe1v-b",
}]})


async def test_germany_fetches_the_body_the_search_does_not_return(monkeypatch):
    client = FakeClient({
        "/jobs": _BA_SEARCH,
        "/jobdetails/": FakeResponse({
            "stellenangebotsBeschreibung": "Über Uns " + "x" * 500,
            "homeofficemoeglich": False,
        }),
    })
    install(monkeypatch, client)

    jobs = [j async for j in national.iter_arbeitsagentur({"keywords": "Projektmanager"})]

    assert len(jobs) == 1
    assert jobs[0].description.startswith("Über Uns")
    assert jobs[0].location == "Ostercappeln, Niedersachsen"
    assert jobs[0].posted_at == "2026-07-30"
    assert jobs[0].source == "arbeitsagentur"


async def test_germany_marks_home_office_where_the_workplace_gate_reads_it(monkeypatch):
    client = FakeClient({
        "/jobs": _BA_SEARCH,
        "/jobdetails/": FakeResponse({"stellenangebotsBeschreibung": "text",
                                      "homeofficemoeglich": True}),
    })
    install(monkeypatch, client)

    jobs = [j async for j in national.iter_arbeitsagentur({})]

    assert jobs[0].location.endswith("(Remote)")


async def test_germany_encodes_the_reference_the_way_the_api_expects(monkeypatch):
    client = FakeClient({"/jobs": _BA_SEARCH,
                         "/jobdetails/": FakeResponse({"stellenangebotsBeschreibung": "t"})})
    install(monkeypatch, client)

    [j async for j in national.iter_arbeitsagentur({})]

    detail_url = [u for u, _ in client.requests if "jobdetails" in u][0]
    token = detail_url.rsplit("/", 1)[1]
    assert base64.b64decode(token).decode() == "12288-4905218638-S"


async def test_germany_survives_a_missing_description(monkeypatch):
    client = FakeClient({"/jobs": _BA_SEARCH, "/jobdetails/": FakeResponse({}, 500)})
    install(monkeypatch, client)

    jobs = [j async for j in national.iter_arbeitsagentur({})]

    assert len(jobs) == 1 and jobs[0].description == ""


async def test_germany_asks_the_server_for_recent_postings_only(monkeypatch):
    client = FakeClient({"/jobs": _BA_SEARCH,
                         "/jobdetails/": FakeResponse({"stellenangebotsBeschreibung": "t"})})
    install(monkeypatch, client)

    [j async for j in national.iter_arbeitsagentur({"location": "Berlin"})]

    _, params = client.requests[0]
    assert params["veroeffentlichtseit"] == 7
    assert params["wo"] == "Berlin" and params["umkreis"] == 50


async def test_germany_caps_the_detail_fetches(monkeypatch):
    many = {"stellenangebote": [
        {"refnr": f"r{i}", "titel": f"Job {i}", "arbeitsort": {}} for i in range(200)]}
    client = FakeClient({"/jobs": FakeResponse(many),
                         "/jobdetails/": FakeResponse({"stellenangebotsBeschreibung": "t"})})
    install(monkeypatch, client)

    jobs = [j async for j in national.iter_arbeitsagentur({"max_jobs": 500})]

    assert len(jobs) <= national._BA_DETAIL_CAP


async def test_a_failing_german_search_yields_nothing(monkeypatch):
    install(monkeypatch, FakeClient({"/jobs": FakeResponse({}, 503)}))

    assert [j async for j in national.iter_arbeitsagentur({})] == []


# --------------------------------------------------------------------------- #
# Sweden                                                                       #
# --------------------------------------------------------------------------- #

_SE_HIT = {
    "id": "31302369",
    "headline": "Project Manager",
    "employer": {"name": "NDP IT AB"},
    "workplace_address": {"municipality": "Helsingborg", "region": "Skåne län"},
    "description": {"text": "We are looking for a project manager."},
    "webpage_url": "https://arbetsformedlingen.se/platsbanken/annonser/31302369",
    "publication_date": "2026-07-29T11:24:00",
}


async def test_sweden_maps_a_hit_completely(monkeypatch):
    install(monkeypatch, FakeClient({"jobsearch": FakeResponse({"hits": [_SE_HIT]})}))

    jobs = [j async for j in national.iter_platsbanken({"keywords": "project manager"})]

    assert len(jobs) == 1
    j = jobs[0]
    assert (j.title, j.company) == ("Project Manager", "NDP IT AB")
    assert j.location == "Helsingborg, Skåne län"
    assert j.description == "We are looking for a project manager."
    assert j.posted_at == "2026-07-29T11:24:00"
    assert j.source == "platsbanken"


async def test_sweden_marks_remote_postings(monkeypatch):
    install(monkeypatch, FakeClient(
        {"jobsearch": FakeResponse({"hits": [{**_SE_HIT, "remote_work": True}]})}))

    jobs = [j async for j in national.iter_platsbanken({})]

    assert jobs[0].location.endswith("(Remote)")


async def test_sweden_requests_newest_first_and_honours_the_cap(monkeypatch):
    client = FakeClient({"jobsearch": FakeResponse({"hits": [_SE_HIT] * 5})})
    install(monkeypatch, client)

    jobs = [j async for j in national.iter_platsbanken({"max_jobs": 2, "location": "Malmö"})]

    _, params = client.requests[0]
    assert params["sort"] == "pubdate-desc"
    assert params["municipality"] == "Malmö"
    assert len(jobs) == 2


async def test_a_failing_swedish_search_yields_nothing(monkeypatch):
    install(monkeypatch, FakeClient({"jobsearch": FakeResponse({}, 429)}))

    assert [j async for j in national.iter_platsbanken({})] == []


# --------------------------------------------------------------------------- #
# Wiring                                                                       #
# --------------------------------------------------------------------------- #

def test_both_boards_are_selectable_as_sources():
    from scheduler.jobs import SOURCE_FETCHERS

    assert SOURCE_FETCHERS["arbeitsagentur"] is national.iter_arbeitsagentur
    assert SOURCE_FETCHERS["platsbanken"] is national.iter_platsbanken


def test_every_fetcher_has_a_label_in_the_search_ui():
    import main
    from scheduler.jobs import SOURCE_FETCHERS

    labelled = {value for value, _, _ in main.SEARCH_SOURCE_OPTIONS}
    assert set(SOURCE_FETCHERS) <= labelled
