"""Who may talk to a server that has no password on it.

The app binds 127.0.0.1 and asks nobody to log in - correct for a tool on your
own laptop. It also answered every website with `Access-Control-Allow-Origin: *`,
and those two together meant any page in the same browser could read the CV out
of it, or clear the job list with a form.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import origins

EXTENSION = "chrome-extension://ajdkflajsdkflajsdkflajsdkflajsdk"


# --------------------------------------------------------------------------- #
# The rule                                                                     #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("origin", [
    EXTENSION,
    "moz-extension://8a4c1e2f-0000-4000-8000-abcdefabcdef",
    "http://127.0.0.1:8000",
    "http://localhost:8007",          # the app walks up to 8010 when 8000 is taken
    "http://[::1]:8000",
])
def test_the_two_callers_that_are_meant_to_be_here(origin):
    assert origins.allowed(origin)


@pytest.mark.parametrize("origin", [
    "https://evil.example",
    "http://evil.example:8000",
    "https://127.0.0.1.evil.example",   # the classic: loopback as a subdomain
    "https://linkedin.com",
    "null",                             # sandboxed iframe, data: URL, file://
])
def test_a_website_is_refused(origin):
    assert not origins.allowed(origin)


def test_no_origin_at_all_is_not_a_cross_site_request():
    """The desktop window's own navigation, curl, and the scheduler send none.
    Refusing those would break the app rather than protect it."""
    assert origins.allowed(None)
    assert origins.allowed("")


def test_a_star_in_the_settings_cannot_bring_the_old_behaviour_back():
    """CORS_ORIGINS is still overridable, but the one value that made this a
    hole is not a valid answer any more."""
    assert not origins.allowed("https://evil.example", ["*"])
    assert origins.allowed("https://trusted.example", ["https://trusted.example"])


def test_the_shipped_default_allows_nobody_extra():
    from config import settings

    assert "*" not in settings.cors_origins, (
        "a star anywhere in this list re-opens the door, including from .env"
    )


# --------------------------------------------------------------------------- #
# Through the app                                                              #
# --------------------------------------------------------------------------- #

async def test_a_website_cannot_read_the_cv(db):
    """The exfiltration half. /profile carries the résumé, the instructions and
    the case bank."""
    import main

    with TestClient(main.app) as client:
        blocked = client.get("/profile", headers={"Origin": "https://evil.example"})
        own = client.get("/profile", headers={"Origin": "http://127.0.0.1:8000"})

    assert blocked.status_code == 403
    assert "résumé" not in blocked.text and "cv-name" not in blocked.text
    assert own.status_code == 200


async def test_a_website_cannot_clear_the_job_list(db, add_job):
    """The destructive half, and the one CORS never protected against: a plain
    cross-site form POST is sent and acted on whatever the CORS headers say."""
    import main

    await add_job(score=90)
    with TestClient(main.app) as client:
        r = client.post("/jobs/clear", data={"view": "all"},
                        headers={"Origin": "https://evil.example"},
                        follow_redirects=False)

    assert r.status_code == 403
    assert len(await db.list_jobs()) == 1, "the jobs were deleted by a foreign page"


async def test_the_extension_can_still_post_jobs(db):
    """The one caller this app is built around."""
    import main

    payload = {"jobs": [{"source": "linkedin", "job_id": "x1",
                         "title": "Product Ops", "company": "Acme",
                         "location": "Amsterdam", "url": "https://e.test/x1",
                         "description": "text"}]}
    with TestClient(main.app) as client:
        r = client.post("/api/ingest", json=payload, headers={"Origin": EXTENSION})

    assert r.status_code == 200


async def test_the_app_serves_its_own_pages(db):
    import main

    with TestClient(main.app) as client:
        assert client.get("/", headers={"Origin": "http://localhost:8003"}).status_code == 200
        assert client.get("/").status_code == 200            # no Origin: the desktop window


async def test_the_browser_is_told_the_same_thing_the_server_enforces(db):
    """Belt and braces: the header stops the read, the middleware stops the
    write. A mismatch between them is how one of the two gets quietly dropped."""
    import main

    with TestClient(main.app) as client:
        good = client.get("/api/health", headers={"Origin": EXTENSION})
        bad = client.get("/api/health", headers={"Origin": "https://evil.example"})

    assert good.headers.get("access-control-allow-origin") == EXTENSION
    assert bad.status_code == 403
    assert bad.headers.get("access-control-allow-origin") in (None, "")
