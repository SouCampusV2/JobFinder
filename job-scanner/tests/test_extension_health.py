"""The extension failing where the user can see it.

It supplies 56% of every job in the database and pauses itself after two empty
scans. That state lived only in Chrome, so the failure mode was three days of an
entirely normal-looking Jobs page with nothing new on it - which is what
actually happened, and is only visible in hindsight in the ingest log.

What it must NOT do is warn about a closed browser. The extension polls only
while Chrome is running, so "it has not checked in for 30 minutes" was true
every evening and all night, and the banner told its owner to check that the
extension was enabled.
"""

from __future__ import annotations

import extension_health as health


def row(**kw):
    base = {"extension_seen_at": "2026-08-09T11:58:00+00:00",
            "extension_state": "ok", "extension_error": ""}
    base.update(kw)
    return base


def test_a_healthy_extension_says_nothing():
    """A banner that is always there is furniture, and stops being read."""
    assert health.status(row()) is None


def test_someone_who_never_installed_it_is_not_told_it_is_broken():
    """The app works without the extension. Warning about a component the user
    does not have would be noise on every single page load."""
    assert health.status({"extension_seen_at": ""}) is None
    assert health.status({}) is None


def test_a_paused_extension_is_reported():
    banner = health.status(row(extension_state="paused", extension_error="auth"))

    assert banner is not None
    assert banner["state"] == "paused"
    assert "sign in" in banner["text"].lower()


def test_a_pause_with_no_known_reason_still_says_something_useful():
    banner = health.status(row(extension_state="paused"))

    assert banner and banner["state"] == "paused"
    assert banner["text"].strip()


def test_a_stopped_extension_is_reported():
    banner = health.status(row(extension_state="stopped"))

    assert banner and banner["state"] == "stopped"


def test_a_closed_browser_is_not_a_fault():
    """Nine hours of silence with a last word of 'ok' is a laptop that was shut
    at six. The extension cannot poll while Chrome is closed, and saying so in
    an amber box every night trains the reader to skip the box."""
    quiet = row(extension_seen_at="2026-08-08T13:28:00+00:00")

    assert health.status(quiet) is None


def test_a_state_the_extension_reported_survives_the_browser_closing():
    """Paused is a fact about the extension, not about the browser: it is still
    paused tomorrow morning, and that is when it needs saying."""
    banner = health.status(
        row(extension_state="paused", extension_seen_at="2026-08-06T09:00:00+00:00"))

    assert banner and banner["state"] == "paused"


def test_an_unreadable_timestamp_does_not_take_the_page_down():
    assert health.status(row(extension_seen_at="whenever")) is None
    assert health.status(row(extension_seen_at="whenever",
                             extension_state="paused"))["state"] == "paused"
