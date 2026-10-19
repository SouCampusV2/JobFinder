"""Public LinkedIn job fetcher - no login, no account, no browser.

Reads LinkedIn's PUBLIC guest endpoint that powers the "see more jobs" list on
job-search pages:

    https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
        ?keywords=...&location=...&start=...&f_TPR=r<seconds>

It returns an HTML fragment of <li> job cards and requires no authentication.
Because we never touch a logged-in session, the user's LinkedIn account is not
involved at all (this is the same approach "safe" tools like First 2 Apply use).

We are polite: a normal browser User-Agent, small randomized delays between
pages, a capped number of results per cycle, and we stop on the first HTTP error
or empty page. This still runs against LinkedIn's ToS in the strict sense, but it
carries no personal-account risk.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from config import settings
from scrapers.base import JobListing

logger = logging.getLogger(__name__)

_GUEST_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    "?keywords={keywords}&location={location}&start={start}"
)
# Public job-detail endpoint (no login) - gives us the full description so we can
# (a) pre-filter cheaply without spending AI tokens and (b) score with real text.
_JOB_DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
SOURCE = "linkedin"

# STRONG, unambiguous on-site phrases only (avoid perks like "relocation package"
# or generic "office culture" that falsely flag remote jobs as on-site).
_STRONG_ONSITE = ("on-site", "on site", "onsite", "must be based in",
                  "in-office role", "fully on-site", "100% on-site")
_STRONG_HYBRID = ("hybrid", "days a week in the office", "days per week in the office",
                  "days in the office per week")
_REMOTE_KW = ("remote", "work from home", "fully remote",
              "work from anywhere", "remote-first", "100% remote")


def workplace_allowed(
    listing: JobListing, allowed: set[str], is_remote: bool | None = None
) -> bool:
    """Does this job match the search's workplace filter?

    `allowed` = requested LinkedIn workplace codes (1 on-site, 2 remote, 3 hybrid);
    empty = no filter. `is_remote` is the AUTHORITATIVE structured signal parsed
    from JSON-LD (jobLocationType == TELECOMMUTE); None means unknown.

    Very conservative: a job is kept unless we are confident it contradicts the
    filter. A confirmed-remote job (structured signal or the word "remote") is
    NEVER dropped - that was the bug where remote roles in EU cities got cut.
    """
    if not allowed or allowed == {"1", "2", "3"}:
        return True

    text = f"{listing.title} {listing.location} {listing.description}".lower()
    remote = is_remote is True or any(k in text for k in _REMOTE_KW)

    # Remote-only search.
    if allowed == {"2"}:
        if remote:
            return True                       # confirmed remote - always keep
        if is_remote is False:                # structured signal says NOT remote
            return False
        # Otherwise only drop on a STRONG on-site/hybrid phrase; else keep.
        strong_onsite = any(k in text for k in _STRONG_ONSITE) or \
            any(k in text for k in _STRONG_HYBRID)
        return not strong_onsite

    return True


def _card_to_listing(card) -> JobListing | None:
    """Parse one <li>/<div class="base-card"> guest card into a JobListing."""
    # job id: prefer data-entity-urn (urn:li:jobPosting:1234567890)
    holder = card.select_one("[data-entity-urn]") or card
    urn = holder.get("data-entity-urn", "") if hasattr(holder, "get") else ""
    m = re.search(r"jobPosting:(\d+)", urn or "")
    job_id = m.group(1) if m else None

    link_el = card.select_one("a.base-card__full-link") or card.select_one(
        "a[href*='/jobs/view/']"
    )
    url = link_el.get("href", "").split("?")[0] if link_el else None
    if not job_id and url:
        m2 = re.search(r"-(\d+)$", url) or re.search(r"/jobs/view/(\d+)", url)
        job_id = m2.group(1) if m2 else None
    if not job_id:
        return None

    def txt(selector: str) -> str | None:
        el = card.select_one(selector)
        return el.get_text(strip=True) if el else None

    title = txt("h3.base-search-card__title") or txt("[class*='title']")
    company = txt("h4.base-search-card__subtitle") or txt("[class*='subtitle']")
    location = txt(".job-search-card__location") or txt("[class*='location']")

    time_el = card.select_one("time")
    posted_at = (
        time_el.get("datetime") or time_el.get_text(strip=True)
        if time_el
        else None
    )

    listing = JobListing(
        source=SOURCE,
        external_id=job_id,
        title=title or "(no title)",
        company=company,
        location=location,
        url=url or f"https://www.linkedin.com/jobs/view/{job_id}/",
        posted_at=posted_at,
    )
    return listing if listing.is_valid() else None


def parse_cards(html: str) -> list[JobListing]:
    """Parse a guest HTML fragment into JobListings (exposed for unit tests)."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("li") or soup.select("div.base-card")
    listings: list[JobListing] = []
    seen: set[str] = set()
    for card in cards:
        listing = _card_to_listing(card)
        if listing and listing.external_id not in seen:
            seen.add(listing.external_id)
            listings.append(listing)
    return listings


# LinkedIn prints four structured facts at the bottom of every public job page.
# The card list carries none of them - measured, zero occurrences of "remote",
# "hybrid" or "on-site" in a whole page of search results - which is why the
# app's own scanning recovered the work arrangement for 0% of its jobs while
# the extension, which reads the logged-in card, got 100%. The detail page is
# already fetched for the description, so these cost nothing extra.
def job_criteria(html: str) -> dict[str, str]:
    """{'Seniority level': 'Mid-Senior level', 'Employment type': 'Full-time', …}"""
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, str] = {}
    for item in soup.select("li.description__job-criteria-item"):
        label = item.select_one(".description__job-criteria-subheader")
        value = item.select_one(".description__job-criteria-text")
        if label and value:
            out[label.get_text(strip=True)] = value.get_text(strip=True)
    return out


def _parse_detail(html: str) -> tuple[str | None, bool | None]:
    """Return (description_text, is_remote) from a guest job-detail page.

    Description comes from the HTML block, with the JSON-LD `description` as a
    reliable fallback. is_remote comes from JSON-LD `jobLocationType ==
    'TELECOMMUTE'` (authoritative); None when the field is absent.
    """
    soup = BeautifulSoup(html, "html.parser")
    el = soup.select_one(
        ".description__text, .show-more-less-html__markup, div[class*='description']"
    )
    # Preserve line breaks so the description reads like the original posting
    # (paragraphs/bullets) instead of one solid wall of text.
    desc = _clean_text(el.get_text("\n")) if el else None

    is_remote: bool | None = None
    jsonld_desc: str | None = None
    for s in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(s.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        for item in (data if isinstance(data, list) else [data]):
            if not isinstance(item, dict) or item.get("@type") != "JobPosting":
                continue
            lt = item.get("jobLocationType")
            if isinstance(lt, str):
                is_remote = lt.upper() == "TELECOMMUTE"
            raw = item.get("description")
            if raw and not jsonld_desc:
                jsonld_desc = _clean_text(
                    BeautifulSoup(raw, "html.parser").get_text("\n")
                )

    return (desc or jsonld_desc or None), is_remote


def _clean_text(text: str) -> str:
    """Collapse runs of blank lines and trailing spaces, keep paragraph breaks."""
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    out: list[str] = []
    blank = 0
    for ln in lines:
        if ln.strip():
            out.append(ln.strip())
            blank = 0
        else:
            blank += 1
            if blank <= 1:
                out.append("")
    return "\n".join(out).strip()


def _with_workplace(desc: str | None, is_remote: bool | None) -> str | None:
    """Prepend an explicit, authoritative workplace line so the AI never has to
    guess remote/on-site from ambiguous prose."""
    if is_remote is True:
        tag = "Workplace: Remote."
    elif is_remote is False:
        tag = "Workplace: On-site or Hybrid."
    else:
        return desc
    return f"{tag}\n{desc}" if desc else tag


async def fetch_job_detail_full(
    client: httpx.AsyncClient, job_id: str
) -> tuple[str | None, bool | None, dict[str, str]]:
    """Description, remote flag and the page's structured criteria.

    One request for all three. The criteria are the only place the app's own
    scanning can learn the employment type and LinkedIn's own seniority label -
    the search results carry neither."""
    try:
        resp = await client.get(_JOB_DETAIL_URL.format(job_id=job_id))
    except httpx.HTTPError:
        return None, None, {}
    if resp.status_code != 200 or not resp.text.strip():
        return None, None, {}
    desc, is_remote = _parse_detail(resp.text)
    return desc, is_remote, job_criteria(resp.text)


async def fetch_job_detail(
    client: httpx.AsyncClient, job_id: str
) -> tuple[str | None, bool | None]:
    """Description + remote flag. Kept for callers that want nothing else."""
    desc, is_remote, _ = await fetch_job_detail_full(client, job_id)
    return desc, is_remote


async def fetch_description(client: httpx.AsyncClient, job_id: str) -> str | None:
    """Description-only helper (used by the extension-ingest path)."""
    desc, _ = await fetch_job_detail(client, job_id)
    return desc


def _build_filter_suffix(cfg: dict) -> str:
    """Translate a search_config row into LinkedIn guest URL filter params.

    f_TPR = date posted (r<seconds>), f_E = experience level (1..6),
    f_JT = job type (F/P/C/T/I/V/O), f_WT = workplace type (1 on-site,
    2 remote, 3 hybrid). Multi-value filters are comma-separated.
    """
    parts: list[str] = []
    tpr = int(cfg.get("tpr_seconds") or 0)
    if tpr > 0:
        parts.append(f"f_TPR=r{tpr}")
    for key, param in (("experience", "f_E"), ("job_types", "f_JT"), ("remote", "f_WT")):
        val = (cfg.get(key) or "").strip()
        if val:
            # normalise "1, 2 ,3" -> "1,2,3"
            clean = ",".join(p.strip() for p in val.split(",") if p.strip())
            if clean:
                parts.append(f"{param}={quote_plus(clean, safe=',')}")
    return ("&" + "&".join(parts)) if parts else ""


async def iter_public_cards(cfg: dict | None = None):
    """Yield public LinkedIn job CARDS one at a time (title/company/location/url),
    WITHOUT fetching each job's description.

    The description fetch (an HTTP round-trip) and full AI scoring are the
    expensive steps, so the caller does a cheap title screen first and only
    fetches the description for jobs that pass. Never raises - a failed request
    just ends the stream.
    """
    cfg = cfg or {}
    query = (cfg.get("keywords") or settings.search_query).strip()
    location = (cfg.get("location") or settings.search_location).strip()
    max_jobs = int(cfg.get("max_jobs") or settings.max_jobs_per_cycle)
    filter_suffix = _build_filter_suffix(cfg)

    headers = {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }

    yielded = 0
    seen: set[str] = set()
    start = 0

    async with httpx.AsyncClient(
        headers=headers, timeout=20.0, follow_redirects=True
    ) as client:
        while yielded < max_jobs:
            url = _GUEST_URL.format(
                keywords=quote_plus(query),
                location=quote_plus(location),
                start=start,
            ) + filter_suffix

            try:
                resp = await client.get(url)
            except httpx.HTTPError as exc:
                logger.warning("[linkedin_public] request error at start=%s: %s", start, exc)
                break

            body = resp.text
            logger.info(
                "[linkedin_public] GET start=%s -> %s (%d bytes)",
                start, resp.status_code, len(body),
            )
            if resp.status_code == 429:
                logger.warning("[linkedin_public] rate-limited (429) — stopping cycle")
                break
            if resp.status_code != 200 or not body.strip():
                logger.info("[linkedin_public] empty response — likely no results "
                            "for this query/location/filters")
                break

            page = parse_cards(body)
            if not page:
                logger.info(
                    "[linkedin_public] 0 cards parsed from %d bytes — LinkedIn "
                    "returned no jobs for these filters (check location/date/filters)",
                    len(body),
                )
                break

            new_this_page = 0
            for listing in page:
                if listing.external_id in seen:
                    continue
                seen.add(listing.external_id)
                yield listing
                yielded += 1
                new_this_page += 1
                if yielded >= max_jobs:
                    break

            # LinkedIn's guest endpoint has a finite unique result set; once you
            # page past it, it just repeats the tail. If a whole page was already
            # seen, we've exhausted the results - stop, otherwise the loop grinds
            # through duplicate pages for minutes while progress appears frozen.
            if new_this_page == 0:
                logger.info("[linkedin_public] no new cards at start=%s — "
                            "exhausted results (%d unique), stopping", start, yielded)
                break

            # Advance by the number of cards actually returned (not a fixed step),
            # so pages don't overlap and we don't re-fetch the same window.
            start += len(page)
            await asyncio.sleep(
                random.uniform(settings.fetch_delay_min, settings.fetch_delay_max)
            )

    logger.info("[linkedin_public] stream done: %d cards", yielded)
