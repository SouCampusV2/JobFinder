"""National public employment services.

State job boards are the half of the European market that never reaches an
English-language aggregator: a German Mittelstand company or a Swedish public
employer posts to the state board and nowhere else. Both APIs below are public,
key-free (the Arbeitsagentur key is the static one its own web client uses) and
return the full posting text, so a job from here can be scored like any other.

  * Arbeitsagentur (Germany)   - rest.arbeitsagentur.de, the Bundesagentur's own
    jobsuche service. The search returns metadata only, so the description costs
    one extra request per job; capped accordingly.
  * Platsbanken (Sweden)       - jobsearch.api.jobtechdev.se, the JobTech open
    API behind Arbetsförmedlingen. Description is included in the search hit.

**Expect the language gate to reject most of these.** Both boards are dominated
by German and Swedish postings, and `matcher.language` blocks a posting written
in a language the candidate did not list. That is the gate working, not a bug -
what remains is the genuinely English-language subset of two markets that
LinkedIn indexes poorly.

Norway's NAV was probed and left out: its public search returns no posting body,
and a job the scorer cannot read is worse than no job at all.
"""

from __future__ import annotations

import asyncio
import base64
import logging

import httpx

from config import settings
from scrapers.base import JobListing

logger = logging.getLogger(__name__)

# The static key the Arbeitsagentur's own job-search front-end sends. Public by
# construction - there is no registration and no per-user quota.
_BA_KEY = "jobboerse-jobsuche"
_BA_BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4"

_JOBTECH = "https://jobsearch.api.jobtechdev.se/search"

# Each German description is a separate request. Cap it: the board answers with
# thousands of hits for a common role and we only ever score the newest few.
_BA_DETAIL_CAP = 25

# Gap between description fetches - a state service, not a CDN.
_BA_PAUSE_S = 0.15


def _headers(extra: dict | None = None) -> dict:
    base = {"User-Agent": settings.user_agent, "Accept": "application/json"}
    return {**base, **(extra or {})}


async def iter_arbeitsagentur(cfg: dict):
    """Germany's federal employment agency. Yields JobListing, never raises."""
    keywords = (cfg.get("keywords") or "").strip()
    location = (cfg.get("location") or "").strip()
    max_jobs = min(int(cfg.get("max_jobs") or settings.max_jobs_per_cycle), _BA_DETAIL_CAP)

    params: dict = {"size": max_jobs, "page": 1}
    if keywords:
        params["was"] = keywords
    if location:
        params["wo"] = location
        params["umkreis"] = 50          # km - a city name alone misses the region
    # 7 = "veröffentlicht seit 7 Tagen"; the scheduler re-checks recency anyway,
    # but asking the server first saves fetching a month of stale detail pages.
    params["veroeffentlichtseit"] = 7

    try:
        async with httpx.AsyncClient(headers=_headers({"X-API-Key": _BA_KEY}),
                                     timeout=25.0, follow_redirects=True) as client:
            r = await client.get(f"{_BA_BASE}/jobs", params=params)
            logger.info("[arbeitsagentur] GET -> %s", r.status_code)
            if r.status_code != 200:
                return
            hits = r.json().get("stellenangebote", [])

            for item in hits[:max_jobs]:
                refnr = item.get("refnr")
                if not refnr:
                    continue
                where = item.get("arbeitsort") or {}
                city = ", ".join(filter(None, [where.get("ort"), where.get("region")]))

                description, remote = "", False
                try:
                    token = base64.b64encode(str(refnr).encode()).decode()
                    d = await client.get(f"{_BA_BASE}/jobdetails/{token}")
                    if d.status_code == 200:
                        detail = d.json()
                        description = (detail.get("stellenangebotsBeschreibung") or "").strip()
                        remote = bool(detail.get("homeofficemoeglich"))
                except httpx.HTTPError as exc:
                    logger.info("[arbeitsagentur] detail %s failed: %s", refnr, exc)
                await asyncio.sleep(_BA_PAUSE_S)

                # The board's own home-office flag, folded where detect_workplace
                # reads it. Absent the flag we say nothing rather than guess.
                if remote and city:
                    city = f"{city} (Remote)"

                yield JobListing(
                    source="arbeitsagentur",
                    external_id=str(refnr),
                    title=item.get("titel") or item.get("beruf") or "",
                    company=item.get("arbeitgeber"),
                    location=city or None,
                    description=description,
                    url=(item.get("externeUrl")
                         or f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"),
                    posted_at=item.get("aktuelleVeroeffentlichungsdatum"),
                )
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("[arbeitsagentur] failed: %s", exc)


async def iter_platsbanken(cfg: dict):
    """Sweden's Platsbanken via the JobTech open API. Yields JobListing."""
    keywords = (cfg.get("keywords") or "").strip()
    location = (cfg.get("location") or "").strip()
    max_jobs = int(cfg.get("max_jobs") or settings.max_jobs_per_cycle)

    params: dict = {"limit": min(max_jobs, 100), "sort": "pubdate-desc"}
    if keywords:
        params["q"] = keywords
    if location:
        # The free-text municipality filter; the API resolves names itself.
        params["municipality"] = location

    try:
        async with httpx.AsyncClient(headers=_headers(), timeout=25.0,
                                     follow_redirects=True) as client:
            r = await client.get(_JOBTECH, params=params)
            logger.info("[platsbanken] GET -> %s", r.status_code)
            if r.status_code != 200:
                return
            hits = r.json().get("hits", [])
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("[platsbanken] failed: %s", exc)
        return

    for j in hits[:max_jobs]:
        where = j.get("workplace_address") or {}
        city = ", ".join(filter(None, [where.get("municipality"), where.get("region")]))
        if j.get("remote_work") and city:
            city = f"{city} (Remote)"
        yield JobListing(
            source="platsbanken",
            external_id=str(j.get("id")),
            title=j.get("headline") or "",
            company=(j.get("employer") or {}).get("name"),
            location=city or None,
            description=((j.get("description") or {}).get("text") or "").strip(),
            url=j.get("webpage_url"),
            posted_at=j.get("publication_date"),
        )
