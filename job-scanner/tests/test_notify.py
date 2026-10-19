"""Telegram digest: who gets sent, when, and what happens if sending fails.

Two problems shaped this. The digest used to include everything scored, red
band and all, so a scan of 300 jobs became a wall of junk on the phone. And it
fired once per ingest batch - the extension posts every few seconds, which
produced five messages in three minutes, one job each.

So: only jobs at or above DIGEST_MIN_SCORE, and only once MIN_DIGEST_JOBS of
them have piled up.
"""

from __future__ import annotations

import itertools


from scheduler import jobs as sched
from telegram_bot import notifier


_seq = itertools.count()


async def _score(db, listing, score: int) -> int:
    """Store one scored job. The title has to be unique: content dedup collapses
    same-title/same-company rows, so five jobs at 85 would silently become one."""
    job_id = await db.insert_job(listing(title=f"Role {score} #{next(_seq)}"))
    await db.save_quick_score(job_id, score, "summary", [])
    return job_id


async def test_only_matches_at_or_above_the_threshold_are_sent(db, listing):
    for score in (10, 55, 60, 90):
        await _score(db, listing, score)

    to_notify = await db.get_jobs_to_notify(sched.DIGEST_MIN_SCORE)

    assert [j["score"] for j in to_notify] == [90]


async def test_low_scores_leave_the_queue_so_they_are_not_reconsidered(db, listing, monkeypatch):
    await _score(db, listing, 20)
    highs = [await _score(db, listing, 85) for _ in range(sched.MIN_DIGEST_JOBS)]
    sent: list[list[dict]] = []

    async def fake_send(jobs, allow_empty=False):
        sent.append(jobs)
        return True

    monkeypatch.setattr(sched, "send_digest", fake_send)

    count = await sched.notify_scored()

    assert count == sched.MIN_DIGEST_JOBS
    assert sorted(j["id"] for j in sent[0]) == sorted(highs)
    # Nothing is left in 'scored', so the next cycle starts clean.
    assert await db.get_jobs_to_notify(0) == []


async def test_a_failed_send_keeps_the_queue_for_the_next_cycle(db, listing, monkeypatch):
    for _ in range(sched.MIN_DIGEST_JOBS):
        await _score(db, listing, 85)

    async def fake_send(jobs, allow_empty=False):
        return False

    monkeypatch.setattr(sched, "send_digest", fake_send)

    assert await sched.notify_scored() == 0
    assert len(await db.get_jobs_to_notify(sched.DIGEST_MIN_SCORE)) == sched.MIN_DIGEST_JOBS


async def test_nothing_to_send_still_drains_and_sends_no_message(db, listing, monkeypatch):
    await _score(db, listing, 15)
    calls = []

    async def fake_send(jobs, allow_empty=False):
        calls.append(jobs)
        return True

    monkeypatch.setattr(sched, "send_digest", fake_send)

    assert await sched.notify_scored() == 0
    assert calls == []                      # no empty digest goes out
    assert await db.get_jobs_to_notify(0) == []


async def test_a_single_match_waits_for_company(db, listing, monkeypatch):
    """One job is not worth a notification. The extension posts a batch every
    few seconds, and one digest per batch is what drove the phone mad."""
    await _score(db, listing, 90)
    calls: list[list[dict]] = []

    async def fake_send(jobs, allow_empty=False):
        calls.append(jobs)
        return True

    monkeypatch.setattr(sched, "send_digest", fake_send)

    assert await sched.notify_scored() == 0
    assert calls == []
    # It waits in the queue rather than being thrown away.
    assert len(await db.get_jobs_to_notify(sched.DIGEST_MIN_SCORE)) == 1


async def test_matches_accumulate_until_the_batch_is_worth_sending(db, listing, monkeypatch):
    calls: list[list[dict]] = []

    async def fake_send(jobs, allow_empty=False):
        calls.append(jobs)
        return True

    monkeypatch.setattr(sched, "send_digest", fake_send)

    for i in range(sched.MIN_DIGEST_JOBS):
        await _score(db, listing, 90)
        sent = await sched.notify_scored()
        if i < sched.MIN_DIGEST_JOBS - 1:
            assert sent == 0, f"sent after only {i + 1} matches"

    assert len(calls) == 1
    assert len(calls[0]) == sched.MIN_DIGEST_JOBS


async def test_the_digest_bar_is_higher_than_the_apps_review_bar(db):
    """The app is for looking through everything worth a glance; the phone is
    only for what is worth interrupting you."""
    settings_row = await db.get_app_settings()

    assert sched.DIGEST_MIN_SCORE > int(settings_row.get("copilot_min_score") or 60)


async def test_a_held_digest_still_drains_the_jobs_it_will_never_send(db, listing, monkeypatch):
    """Low scores must not sit in the queue forever waiting for a batch that
    will never include them."""
    await _score(db, listing, 30)
    await _score(db, listing, 90)

    monkeypatch.setattr(sched, "send_digest", _never_called)

    assert await sched.notify_scored() == 0
    left = await db.get_jobs_to_notify(0)
    assert [j["score"] for j in left] == [90]


async def _never_called(jobs, allow_empty=False):
    raise AssertionError("send_digest must not be called")


# --------------------------------------------------------------------------- #
# Credentials                                                                  #
# --------------------------------------------------------------------------- #

async def test_a_blank_token_keeps_the_saved_one(db):
    await db.save_telegram_settings("123:ABC", "42", True)

    await db.save_telegram_settings("", "99", True)   # user re-saved the form

    s = await db.get_app_settings()
    assert s["telegram_bot_token"] == "123:ABC"
    assert s["telegram_chat_id"] == "99"


class _Env:
    """Stand-in for the frozen settings object, which cannot be patched."""
    telegram_bot_token = "env-token"
    telegram_chat_id = "env-chat"


async def test_credentials_prefer_the_ui_over_env(db, monkeypatch):
    monkeypatch.setattr(notifier, "settings", _Env)
    await db.save_telegram_settings("ui-token", "ui-chat", True)

    assert await notifier.credentials() == ("ui-token", "ui-chat", True)


async def test_credentials_fall_back_to_env_when_the_ui_is_empty(db, monkeypatch):
    monkeypatch.setattr(notifier, "settings", _Env)

    token, chat_id, enabled = await notifier.credentials()

    assert (token, chat_id) == ("env-token", "env-chat")
    # .env supplies credentials but never switches notifications on by itself.
    assert enabled is False


async def test_notifications_are_off_until_switched_on(db):
    await db.save_telegram_settings("t", "c", False)

    assert await notifier.credentials() == ("t", "c", False)


async def test_the_digest_lists_matches_without_score_bands(db):
    """Everything that reaches the phone is already above the bar, so grouping
    by band produced headed sections with one line each."""
    jobs = [{"id": 1, "title": "A", "company": "X", "score": 85, "match_summary": "• good"},
            {"id": 2, "title": "B", "company": "Y", "score": 82, "match_summary": ""}]

    text = notifier._build_digest(jobs)

    assert "🔴" not in text and "🟡" not in text
    assert "A" in text and "B" in text


async def test_every_digest_entry_links_back_into_the_app(db):
    """"The bot sent me something I cannot find" needs a one-tap answer."""
    text = notifier._build_digest([{"id": 4242, "title": "A", "company": "X", "score": 90}])

    assert "/jobs/4242" in text


async def test_the_highest_score_is_listed_first(db):
    jobs = [{"id": 1, "title": "Lower", "company": "X", "score": 81},
            {"id": 2, "title": "Higher", "company": "Y", "score": 95}]

    text = notifier._build_digest(jobs)

    assert text.index("Higher") < text.index("Lower")


# --------------------------------------------------------------------------- #
# The scheduled digest                                                         #
# --------------------------------------------------------------------------- #

async def test_a_scheduled_digest_goes_out_even_with_nothing_to_report(db, monkeypatch):
    """Silence cannot be told apart from a scan that never ran. "Nothing today"
    is the whole point of the message."""
    sent: list[list[dict]] = []

    async def fake_send(jobs, allow_empty=False):
        sent.append(jobs)
        return True

    monkeypatch.setattr(sched, "send_digest", fake_send)

    assert await sched.notify_scored(scheduled=True) == 0
    assert sent == [[]]


async def test_an_unprompted_digest_stays_quiet_when_there_is_nothing(db, monkeypatch):
    async def fake_send(jobs, allow_empty=False):
        raise AssertionError("must not send")

    monkeypatch.setattr(sched, "send_digest", fake_send)

    assert await sched.notify_scored() == 0


async def test_a_scheduled_digest_ignores_the_batch_size(db, listing, monkeypatch):
    """The floor exists to stop per-batch spam from the extension. A scan the
    user planned is not spam, so one match is worth sending."""
    await _score(db, listing, 90)
    sent: list[list[dict]] = []

    async def fake_send(jobs, allow_empty=False):
        sent.append(jobs)
        return True

    monkeypatch.setattr(sched, "send_digest", fake_send)

    assert await sched.notify_scored(scheduled=True) == 1
    assert len(sent[0]) == 1


async def test_an_empty_digest_says_so_in_words():
    from telegram_bot.notifier import EMPTY_DIGEST, _build_digest

    assert _build_digest([]) == EMPTY_DIGEST
    assert "80+" in EMPTY_DIGEST


async def test_an_empty_send_is_refused_unless_it_was_scheduled():
    from telegram_bot import notifier

    assert await notifier.send_digest([]) is False


async def test_the_real_sender_accepts_an_empty_scheduled_digest(db, monkeypatch):
    """Covers send_digest itself, not a stand-in: the empty case has to survive
    the early return and actually reach Telegram."""
    from telegram_bot import notifier

    sent: list[dict] = []

    class FakeBot:
        async def send_message(self, **kw):
            sent.append(kw)

    async def fake_bot():
        return FakeBot(), "chat-1"

    monkeypatch.setattr(notifier, "_bot", fake_bot)

    assert await notifier.send_digest([], allow_empty=True) is True
    assert sent[0]["text"] == notifier.EMPTY_DIGEST


async def test_the_real_sender_refuses_an_empty_unscheduled_digest(db, monkeypatch):
    from telegram_bot import notifier

    async def fake_bot():
        raise AssertionError("must not even look for a bot")

    monkeypatch.setattr(notifier, "_bot", fake_bot)

    assert await notifier.send_digest([]) is False


async def test_a_scheduled_scan_always_ends_in_a_digest(db, monkeypatch):
    """The scan cycle must ask for the SCHEDULED digest. Calling the plain one
    would make a quiet scan silent, which is the thing this is meant to fix."""
    calls: list[dict] = []

    async def fake_notify(scheduled: bool = False):
        calls.append({"scheduled": scheduled})
        return 0

    monkeypatch.setattr(sched, "notify_scored", fake_notify)

    await sched.run_scan_cycle()          # no searches configured - a no-op cycle

    assert calls == [{"scheduled": True}]
