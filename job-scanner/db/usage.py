"""What each model call actually cost, as the provider reported it.

Every answer carries a `usage` block - tokens in, tokens out, and how many of
the input tokens were served from cache. The app has never stored one, so every
cost figure it or anyone else has produced was arithmetic over measured prompts
rather than a fact. That arithmetic was wrong at least twice: once about the
price list, once about whether caching was working at all.

Four numbers per call, written after the answer arrives. It is deliberately not
in the hot path's way: recording failures are swallowed, because a bookkeeping
error must never cost a scored job.
"""

from __future__ import annotations

import logging
from typing import Any

import aiosqlite

from db import conn

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS model_usage (
    id            INTEGER PRIMARY KEY,
    at            TEXT NOT NULL,
    stage         TEXT NOT NULL,          -- title | quick | advanced | write
    model         TEXT NOT NULL,
    prompt        INTEGER NOT NULL DEFAULT 0,
    cached        INTEGER NOT NULL DEFAULT 0,
    completion    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_usage_at ON model_usage(at);
"""


def _cached_from(usage: Any) -> int:
    """How many input tokens were served from cache.

    Every provider reports this under a different name, and getting it wrong
    reads as 'caching does not work' rather than as a parsing bug:
      * OpenAI   → prompt_tokens_details.cached_tokens
      * DeepSeek → prompt_cache_hit_tokens
    """
    hit = getattr(usage, "prompt_cache_hit_tokens", None)
    if hit is not None:
        return int(hit)
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        value = getattr(details, "cached_tokens", None)
        if value is None and isinstance(details, dict):
            value = details.get("cached_tokens")
        if value is not None:
            return int(value)
    return 0


async def record(stage: str, model: str, usage: Any) -> None:
    """Store one call's usage. Never raises."""
    if usage is None:
        return
    try:
        from db.queries import _utc_now_iso

        async with conn.connect() as db:
            await db.execute(
                "INSERT INTO model_usage (at, stage, model, prompt, cached, completion) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (_utc_now_iso(), stage, model or "",
                 int(getattr(usage, "prompt_tokens", 0) or 0),
                 _cached_from(usage),
                 int(getattr(usage, "completion_tokens", 0) or 0)),
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001 - bookkeeping must never cost a job
        logger.debug("Could not record usage: %s", exc)


async def totals(days: int = 30) -> list[dict[str, Any]]:
    """Per stage over the last N days: calls, tokens, and the cache hit rate."""
    async with conn.connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT stage, model,
                   COUNT(*)        AS calls,
                   SUM(prompt)     AS prompt,
                   SUM(cached)     AS cached,
                   SUM(completion) AS completion
              FROM model_usage
             WHERE at >= datetime('now', ?)
             GROUP BY stage, model
             ORDER BY prompt DESC
            """,
            (f"-{int(days)} days",),
        )
        return [dict(r) for r in await cur.fetchall()]
