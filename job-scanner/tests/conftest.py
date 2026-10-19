"""Shared fixtures.

The whole suite runs against a THROWAWAY SQLite file. `config.settings` is a
frozen dataclass built at import time, so `DB_PATH` has to be set before any
application module is imported - hence the env assignment at the top of this
file, which pytest loads before collecting tests.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# --- must happen BEFORE importing config/db ------------------------------- #
_TMP_DB = Path(tempfile.gettempdir()) / "jobfinder-tests" / "test-jobs.db"
_TMP_DB.parent.mkdir(parents=True, exist_ok=True)
os.environ["DB_PATH"] = str(_TMP_DB)
# Importing the desktop launcher sets up logging in the user data dir;
# keep that out of the real ~/Library/Application Support too.
os.environ["JOBFINDER_DATA_DIR"] = str(_TMP_DB.parent)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from config import settings  # noqa: E402
from db import queries  # noqa: E402
from db.models import init_db  # noqa: E402
from scrapers.base import JobListing  # noqa: E402

# Guard rail: the real database lives in the user's Application Support dir.
# If anything ever mis-resolves the path, fail loudly instead of deleting it.
assert "jobfinder-tests" in str(settings.db_path), (
    f"Tests must not touch a real database (got {settings.db_path})"
)


@pytest_asyncio.fixture
async def db():
    """A fresh, migrated, empty database for every test."""
    if _TMP_DB.exists():
        _TMP_DB.unlink()
    await init_db()
    yield queries
    if _TMP_DB.exists():
        _TMP_DB.unlink()


@pytest.fixture
def listing():
    """Factory for a valid JobListing with sensible defaults."""
    counter = {"n": 0}

    def make(title=None, company="Acme", **kw):
        counter["n"] += 1
        # Unique by default: the app dedups by company+title, so identical
        # defaults would silently collapse fixtures into one row. Tests that
        # WANT a duplicate pass the same title explicitly.
        title = title or f"Product Manager {counter['n']}"
        fields = {
            "source": "linkedin",
            "external_id": f"ext-{counter['n']}",
            "title": title,
            "company": company,
            "location": "Berlin, Germany",
            "description": "We are looking for a product manager. " * 5,
            "url": "https://example.test/job",
            "posted_at": "2026-07-27T00:00:00+00:00",
        }
        fields.update(kw)
        return JobListing(**fields)

    return make


@pytest_asyncio.fixture
async def add_job(db, listing):
    """Insert a job and optionally score/flag it. Returns the row id."""

    async def _add(score=None, applied=0, favorite=0, pinned=0, **kw):
        job_id = await db.insert_job(listing(**kw))
        if job_id is None:
            return None
        if score is not None:
            await db.save_quick_score(job_id, score, "test summary", [])
        if applied:
            await db.set_applied(job_id, 1)
        if favorite:
            await db.toggle_favorite(job_id)
        if pinned:
            await db.toggle_pinned(job_id)
        return job_id

    return _add
