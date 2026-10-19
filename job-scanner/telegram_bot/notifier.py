"""Telegram notifications.

Two entry points:
  * send_digest(jobs) - a compact digest of newly scored vacancies, grouped by
    score band (green/yellow/red). Sends nothing when the list is empty.
  * send_alert(text) - a plain operational alert (e.g. cookie expired, rate
    limited), used by the scheduler on ScraperBlocked.

Both degrade gracefully: if the bot token / chat id are missing, they log and
return instead of raising, so a mis-configured Telegram never breaks scraping.

Credentials come from the Settings UI (stored in `app_settings`) and fall back
to .env, so the packaged desktop app needs no environment file.
"""

from __future__ import annotations

import html
import asyncio
import logging
import os
from typing import Any

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from config import settings
from db import queries

logger = logging.getLogger(__name__)

# Score band thresholds (no magic numbers scattered around).
GREEN_MIN = 80
YELLOW_MIN = 60

# Telegram hard limit is 4096 chars per message; stay safely under.
_MAX_MESSAGE_CHARS = 3800


async def credentials() -> tuple[str, str, bool]:
    """(token, chat_id, enabled) - the UI wins, .env is the fallback."""
    try:
        s = await queries.get_app_settings()
    except Exception:  # noqa: BLE001 - DB not ready is not a Telegram error
        s = {}
    token = (s.get("telegram_bot_token") or settings.telegram_bot_token or "").strip()
    chat_id = str(s.get("telegram_chat_id") or settings.telegram_chat_id or "").strip()
    # The checkbox is the only switch. .env may supply credentials, but it can
    # never turn notifications on behind the user's back.
    enabled = bool(s.get("telegram_enabled"))
    return token, chat_id, enabled


async def _bot() -> tuple[Bot, str] | None:
    token, chat_id, enabled = await credentials()
    if not token or not chat_id:
        logger.warning("Telegram not configured — skipping notification")
        return None
    if not enabled:
        logger.info("Telegram notifications are switched off — skipping")
        return None
    return Bot(token=token), chat_id


def _app_url(job_id: Any) -> str:
    """Link back into the app itself.

    Without it, "the bot sent me something I cannot find" has no quick answer -
    with it, the answer is one tap."""
    port = os.getenv("JOBFINDER_RUNTIME_PORT") or str(settings.port)
    return f"http://localhost:{port}/jobs/{job_id}"


def _format_job(job: dict[str, Any]) -> str:
    title = html.escape(str(job.get("title") or "—"))
    company = html.escape(str(job.get("company") or "—"))
    score = job.get("score")
    url = job.get("url") or ""
    # First bullet of the summary as a one-liner.
    summary = (job.get("match_summary") or "").splitlines()
    one_line = html.escape(summary[0].lstrip("• ").strip()) if summary else ""
    header = f"<b>{title}</b> — {company} (<b>{score}</b>)"
    line = f"{header}\n{one_line}" if one_line else header
    links = [f'<a href="{_app_url(job.get("id"))}">Open in Job Finder</a>']
    if url:
        links.append(f'<a href="{html.escape(url)}">Original posting</a>')
    return line + "\n" + " · ".join(links)


# What a scheduled digest says when the scan found nothing. Sent on purpose:
# silence cannot be told apart from a scan that never ran.
EMPTY_DIGEST = "Scan finished. No matches at 80+ this time."


def _build_digest(jobs: list[dict[str, Any]]) -> str:
    """One flat list. The score bands are gone: everything that reaches the
    phone is already above the digest threshold, so grouping them split a short
    message into headed sections with one line each."""
    if not jobs:
        return EMPTY_DIGEST
    ordered = sorted(jobs, key=lambda j: j.get("score") or 0, reverse=True)
    text = f"<b>{len(jobs)} strong match{'' if len(jobs) == 1 else 'es'}</b>"
    # Whole job blocks only, best first, until the next one would not fit.
    # Slicing the finished string at the limit can cut through an <a> or <b>
    # tag, and Telegram rejects HTML with an unclosed tag outright.
    for shown, job in enumerate(ordered):
        block = "\n\n" + _format_job(job)
        rest = len(ordered) - shown
        tail = f"\n\n…and {rest} more in Job Finder"
        reserve = len(tail) if rest > 1 else 0      # the last job needs no tail
        if len(text) + len(block) + reserve > _MAX_MESSAGE_CHARS:
            return text + tail
        text += block
    return text


# Seconds to wait before retrying a digest.
_RETRY_DELAYS = (3, 15)


async def _remember(error: Exception | None) -> None:
    """Store the outcome for the UI. Never raises: a notification that failed
    must not also take down the scan that produced it."""
    try:
        from db import queries

        await queries.record_telegram_result(f"{type(error).__name__}: {error}" if error else "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not record the Telegram result: %s", exc)


async def send_digest(jobs: list[dict[str, Any]], allow_empty: bool = False) -> bool:
    """Send the digest. Returns True if a message was sent.

    `allow_empty` is the scheduled case: "nothing today" is worth saying, an
    unprompted "nothing" in the middle of the afternoon is not."""
    if not jobs and not allow_empty:
        logger.info("No new scored jobs — no digest sent")
        return False
    pair = await _bot()
    if pair is None:
        return False
    bot, chat_id = pair
    text = _build_digest(jobs)
    # Both failures seen in the wild are momentary - a laptop that woke before
    # its network did, and a captive proxy rewriting TLS. One retry costs a few
    # seconds and turns most of them into a delivered message.
    last: Exception | None = None
    for attempt in (1, 2, 3):
        try:
            await bot.send_message(
                chat_id=chat_id, text=text, parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            logger.info("Digest sent (%d jobs)%s", len(jobs),
                        f" on attempt {attempt}" if attempt > 1 else "")
            await _remember(None)
            return True
        except TelegramError as exc:
            last = exc
            logger.warning("Telegram digest attempt %d failed: %s", attempt, exc)
            if attempt < 3:
                await asyncio.sleep(_RETRY_DELAYS[attempt - 1])
    logger.error("Failed to send Telegram digest after 3 attempts: %s", last)
    # Recorded so the Settings page can say it out loud. A digest that silently
    # never arrives is indistinguishable from a day with no matches.
    await _remember(last)
    return False


async def send_alert(text: str) -> None:
    """Send an operational alert (backoff / cookie expiry / errors)."""
    pair = await _bot()
    if pair is None:
        return
    bot, chat_id = pair
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ {html.escape(text)}",
            parse_mode=ParseMode.HTML,
        )
    except TelegramError as exc:
        logger.error("Failed to send Telegram alert: %s", exc)


async def send_test() -> tuple[bool, str]:
    """Send a probe message. Returns (ok, message) for the Settings page.

    Ignores the on/off switch: the point of the button is to verify the token
    and chat id before switching notifications on."""
    token, chat_id, _ = await credentials()
    if not token:
        return False, "No bot token set."
    if not chat_id:
        return False, "No chat id set."
    try:
        await Bot(token=token).send_message(
            chat_id=chat_id,
            text="✅ Job Finder is connected. This is a test message.",
        )
        return True, "Sent — check Telegram."
    except TelegramError as exc:
        logger.error("Telegram test failed: %s", exc)
        return False, f"Telegram refused the request: {exc}"
