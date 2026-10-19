"""Titles that repeat themselves.

LinkedIn renders the title twice in a card - a visible span plus a
screen-reader copy suffixed "with verification". An older extension build read
the wrapper element and sent both glued together, which showed up in the job
list, in the Telegram digest, and (worse) in the dedup fingerprint.
"""

from __future__ import annotations

import pytest

from scrapers.base import JobListing, clean_title


@pytest.mark.parametrize("stored, expected", [
    ("Project Manager (Remote)Project Manager (Remote)", "Project Manager (Remote)"),
    ("Customer Success ManagerCustomer Success Manager", "Customer Success Manager"),
    ("Strategy & Operations Manager Strategy & Operations Manager with verification",
     "Strategy & Operations Manager"),
    ("Product Manager, Billing Platform Product Manager, Billing Platform with verification",
     "Product Manager, Billing Platform"),
    ("Business Development Manager (Higher Education) – UAE (Commission Only)"
     "Business Development Manager (Higher Education) – UAE (Commission Only)",
     "Business Development Manager (Higher Education) – UAE (Commission Only)"),
])
def test_a_doubled_title_is_collapsed(stored, expected):
    assert clean_title(stored) == expected


@pytest.mark.parametrize("title", [
    "Project Manager",
    "Senior Project Manager, Operations",
    "Manager of Managers",                  # repeats a word, not itself
    "Head of Growth",
    "Product Manager / Product Owner",      # two different roles
    "QA QA",                                # too short to be the known defect
    "Project Manager with verification",    # suffix alone is not a doubling
])
def test_a_normal_title_is_left_alone(title):
    assert clean_title(title) == title


def test_whitespace_is_normalised():
    assert clean_title("  Project   Manager\n") == "Project Manager"


def test_a_missing_title_does_not_crash():
    assert clean_title(None) == ""


def test_every_listing_is_cleaned_on_construction():
    listing = JobListing(source="linkedin", external_id="1",
                         title="Growth Manager (Remote)Growth Manager (Remote)")

    assert listing.title == "Growth Manager (Remote)"


async def test_repair_fixes_stored_rows_and_their_fingerprint(db):
    # Simulate what the old extension wrote: bypass JobListing, which now cleans.
    import aiosqlite
    from config import settings

    async with aiosqlite.connect(settings.db_path) as raw:
        await raw.execute(
            "INSERT INTO jobs (source, external_id, title, company, scraped_at, "
            "dedup_key, status) VALUES ('linkedin', 'x1', ?, 'Acme', '2026-07-01', ?, 'new')",
            ("Growth ManagerGrowth Manager", db.dedup_key("Growth ManagerGrowth Manager", "Acme")),
        )
        await raw.commit()

    assert await db.repair_doubled_titles() == 1

    job = await db.get_job(1)
    assert job["title"] == "Growth Manager"
    assert job["dedup_key"] == db.dedup_key("Growth Manager", "Acme")


async def test_repair_is_a_no_op_on_clean_data(db, listing):
    await db.insert_job(listing(title="Project Manager"))

    assert await db.repair_doubled_titles() == 0


async def test_a_repaired_row_collapses_into_its_correctly_read_twin(db, listing):
    import aiosqlite
    from config import settings

    async with aiosqlite.connect(settings.db_path) as raw:
        await raw.execute(
            "INSERT INTO jobs (source, external_id, title, company, scraped_at, "
            "dedup_key, status) VALUES ('linkedin', 'old', ?, 'Acme', '2026-07-01', ?, 'new')",
            ("Growth ManagerGrowth Manager", db.dedup_key("Growth ManagerGrowth Manager", "Acme")),
        )
        await raw.commit()
    await db.insert_job(listing(title="Growth Manager", company="Acme"))

    await db.repair_doubled_titles()
    removed = await db.purge_duplicates()

    assert removed == 1
