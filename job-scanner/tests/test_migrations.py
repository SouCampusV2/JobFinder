"""Migrations run on every startup against a database that may be months old
and full of real data. A broken one is unrecoverable for the user."""

import aiosqlite

from config import settings
from db.models import _MIGRATIONS, init_db



async def _columns(table: str) -> set[str]:
    async with aiosqlite.connect(settings.db_path) as con:
        cur = await con.execute(f"PRAGMA table_info({table})")
        return {r[1] for r in await cur.fetchall()}


async def test_every_declared_migration_is_applied(db):
    for table, column, _ in _MIGRATIONS:
        assert column in await _columns(table), f"{table}.{column} missing after init_db"


async def test_init_db_is_idempotent(db):
    """It runs on every launch; a second pass must not fail or duplicate."""
    await init_db()
    await init_db()

    async with aiosqlite.connect(settings.db_path) as con:
        cur = await con.execute("SELECT COUNT(*) FROM profile")
        assert (await cur.fetchone())[0] == 1, "profile row duplicated"
        cur = await con.execute("SELECT COUNT(*) FROM app_settings")
        assert (await cur.fetchone())[0] == 1


async def test_migration_preserves_existing_rows(db, listing):
    """The upgrade path: data written by an older version must survive."""
    job_id = await db.insert_job(listing(title="Keep me"))
    await db.save_quick_score(job_id, 77, "still here", ["flag"])

    await init_db()

    job = await db.get_job(job_id)
    assert job["title"] == "Keep me"
    assert job["score"] == 77
    assert job["red_flags"] == ["flag"]


async def test_dedup_index_exists(db):
    async with aiosqlite.connect(settings.db_path) as con:
        cur = await con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_jobs_dedup'"
        )
        assert await cur.fetchone() is not None, "dedup lookups would full-scan"


async def test_upgrade_from_a_pre_migration_schema(db):
    """Simulate the oldest shipped schema, then upgrade it in place."""
    async with aiosqlite.connect(settings.db_path) as con:
        await con.execute("DROP TABLE jobs")
        await con.execute(
            """CREATE TABLE jobs (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 source TEXT NOT NULL, external_id TEXT NOT NULL,
                 title TEXT NOT NULL, company TEXT, location TEXT,
                 description TEXT, url TEXT, posted_at TEXT,
                 scraped_at TEXT NOT NULL, score INTEGER, match_summary TEXT,
                 red_flags TEXT, status TEXT NOT NULL DEFAULT 'new',
                 UNIQUE(source, external_id))"""
        )
        await con.execute(
            "INSERT INTO jobs (source, external_id, title, scraped_at) "
            "VALUES ('linkedin', 'old-1', 'Legacy job', '2026-01-01T00:00:00+00:00')"
        )
        await con.commit()

    await init_db()

    cols = await _columns("jobs")
    assert {"applied", "pinned", "dedup_key", "fetched_via"} <= cols
    rows = await db.list_jobs()
    assert len(rows) == 1 and rows[0]["title"] == "Legacy job"
