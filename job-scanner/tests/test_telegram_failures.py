"""A notification that fails is worse than one that never existed.

On 13 August the laptop woke before its network and the digest died on DNS. On
18 August a proxy rewriting TLS killed another. Both were logged as one line
inside a 21 MB file and then forgotten: the scan had run, the jobs were there,
and the day looked exactly like a day with no matches.
"""

from __future__ import annotations

import pytest
from telegram.error import TelegramError

from telegram_bot import notifier


class _Bot:
    """Fails a given number of times, then succeeds."""

    def __init__(self, failures: int, error: str = "Network unreachable"):
        self.failures, self.error, self.calls = failures, error, 0

    async def send_message(self, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise TelegramError(self.error)


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """The retry delays are real seconds; the test does not need them."""
    monkeypatch.setattr(notifier, "_RETRY_DELAYS", (0, 0))


JOBS = [{"id": 1, "title": "Product Ops", "company": "Acme", "score": 82,
         "url": "https://e.test/1", "location": "Amsterdam"}]


async def test_a_momentary_failure_is_retried_not_dropped(db, monkeypatch):
    """Both real failures were transient. One retry turns them into a message."""
    bot = _Bot(failures=1)
    monkeypatch.setattr(notifier, "_bot", lambda: _pair(bot))

    assert await notifier.send_digest(JOBS) is True
    assert bot.calls == 2


async def test_it_gives_up_after_three_tries(db, monkeypatch):
    bot = _Bot(failures=99)
    monkeypatch.setattr(notifier, "_bot", lambda: _pair(bot))

    assert await notifier.send_digest(JOBS) is False
    assert bot.calls == 3


async def test_a_lost_digest_is_recorded_where_the_user_will_see_it(db, monkeypatch):
    monkeypatch.setattr(notifier, "_bot", lambda: _pair(_Bot(failures=99, error="TLS blew up")))

    await notifier.send_digest(JOBS)

    row = await db.get_app_settings()
    assert "TLS blew up" in row["telegram_error"]
    assert row["telegram_error_at"]


async def test_a_delivered_digest_clears_an_older_failure(db, monkeypatch):
    """Someone who fixed their network must not keep reading yesterday's alarm."""
    await db.record_telegram_result("ConnectError: no network")
    monkeypatch.setattr(notifier, "_bot", lambda: _pair(_Bot(failures=0)))

    await notifier.send_digest(JOBS)

    row = await db.get_app_settings()
    assert row["telegram_error"] == ""
    assert row["telegram_sent_at"]


async def test_the_settings_page_says_so(db, monkeypatch):
    from fastapi.testclient import TestClient

    import main

    await db.record_telegram_result("SSLError: certificate verify failed")
    with TestClient(main.app) as client:
        page = client.get("/settings").text

    assert "The last digest did not arrive" in page
    assert "certificate verify failed" in page
    assert "still on the Jobs page" in page


def test_a_long_digest_is_never_cut_through_a_tag():
    """A digest past the length limit must not be sliced mid-<a>: Telegram
    refuses it ("Can't parse entities: unclosed end tag") and nothing arrives.
    A long digest must stay valid HTML."""
    # Where the limit falls depends on title lengths, so one sample can land on
    # a tag boundary by luck - the first version of this test did, and passed
    # against the broken code. Sweep the padding so the cut lands everywhere.
    for pad in range(0, 40):
        many = [{"id": i, "title": "Product Operations Specialist " + "x" * pad,
                 "company": "Acme Corp", "score": 80 + i % 20,
                 "url": f"https://example.test/jobs/{i}",
                 "match_summary": "• Strong fit for delivery and operations work"}
                for i in range(60)]

        text = notifier._build_digest(many)

        assert len(text) <= notifier._MAX_MESSAGE_CHARS, pad
        for tag in ("a", "b"):
            assert text.count(f"<{tag}") == text.count(f"</{tag}>"), f"unclosed <{tag}> at pad {pad}"
        assert "more in Job Finder" in text, "the jobs that did not fit must be counted"


def test_a_digest_that_fits_is_sent_whole():
    few = [{"id": 1, "title": "PM", "company": "Acme", "score": 90, "url": "https://e.test/1"}]

    text = notifier._build_digest(few)

    assert "more in Job Finder" not in text
    assert "PM" in text


async def test_a_failed_notification_never_takes_the_scan_with_it(db, monkeypatch):
    """It runs at the end of a scan that already cost money."""
    monkeypatch.setattr(notifier, "_bot", lambda: _pair(_Bot(failures=99)))

    async def _explode(*a, **k):
        raise RuntimeError("database gone")

    monkeypatch.setattr("db.queries.record_telegram_result", _explode)

    assert await notifier.send_digest(JOBS) is False       # must not raise


async def _pair(bot):
    return bot, "12345"
