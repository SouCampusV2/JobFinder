"""One way to open the database, with the two settings that decide whether a
scan can write while you are looking at a page.

SQLite's default journal blocks readers and writers against each other. This app
has one long writer - a scan storing hundreds of rows - and a steady reader: the
page polling /api/scan-status every few seconds while it runs. Sooner or later
they meet, and the loser gets `database is locked` after five seconds of
waiting - which can lose a whole search: fetched, scored, paid for, and never
stored.

WAL removes the collision rather than lengthening the wait - readers and one
writer proceed at the same time. It is a property of the database FILE, so it
is set once at startup and stays. `busy_timeout` covers what is left, which is
writer against writer.
"""

from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

from config import settings

logger = logging.getLogger(__name__)

# How long to wait for another writer before giving up. The default is five
# seconds, which a scan storing a few hundred rows can exceed.
BUSY_TIMEOUT_S = 15.0


def connect(db_path: str | Path | None = None) -> aiosqlite.Connection:
    """A connection to the app's database. Use this, never aiosqlite directly:
    a connection opened without the timeout is the one that raises."""
    return aiosqlite.connect(db_path or settings.db_path, timeout=BUSY_TIMEOUT_S)


async def apply_pragmas(db: aiosqlite.Connection) -> str:
    """Put the file in WAL mode. Returns the journal mode actually in force.

    Never raises: a database on a filesystem that cannot do WAL (some network
    shares) must keep working in its old mode rather than refuse to start."""
    try:
        cur = await db.execute("PRAGMA journal_mode=WAL")
        mode = (await cur.fetchone())[0]
        await db.execute(f"PRAGMA busy_timeout={int(BUSY_TIMEOUT_S * 1000)}")
        await db.commit()
        if str(mode).lower() != "wal":
            logger.warning("Database is in %s mode, not WAL — scans may collide "
                           "with the page while they run", mode)
        return str(mode)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not set the journal mode: %s", exc)
        return "unknown"
