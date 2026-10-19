"""Is the browser extension still working?

The app cannot see inside Chrome. The extension pauses itself after two runs
that find nothing - a sign-in wall, a search URL that stopped matching - and
that state lived only in browser storage. What the user saw was a Jobs page that
looked entirely healthy while nothing new arrived for days, with no way to tell
a paused extension from a quiet job market.

So this reports what the extension SAYS about itself, and nothing else.

It used to also warn when the extension had simply gone quiet for half an hour.
That was wrong: the extension only polls while Chrome is open, so the banner
appeared every evening, every night and every weekend, saying "check that the
extension is enabled" about a browser its owner had deliberately closed. A
warning that is right every evening is furniture, and furniture is what people
stop reading - including on the morning it means something.
"""

from __future__ import annotations

_REASONS = {
    "auth": "LinkedIn asked it to sign in.",
    "empty": "Its last scans found no jobs — check the search URLs.",
}


def status(settings_row: dict) -> dict | None:
    """A banner for the Jobs page, or None when there is nothing to say.

    Returns None when the extension has never been heard from at all: a user who
    has not installed it should not be told it is broken."""
    if not (settings_row.get("extension_seen_at") or "").strip():
        return None

    state = (settings_row.get("extension_state") or "ok").strip()
    error = (settings_row.get("extension_error") or "").strip()

    if state == "stopped":
        return {"level": "warn", "state": "stopped",
                "text": "The browser extension is stopped. Open it and press "
                        "Scan now to start it again."}

    if state == "paused":
        why = _REASONS.get(error, error or "Two scans in a row came back empty.")
        return {"level": "warn", "state": "paused",
                "text": f"The browser extension paused itself. {why} "
                        "Open it and press Scan now once the cause is fixed."}

    return None
