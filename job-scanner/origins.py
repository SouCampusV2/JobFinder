"""Who is allowed to talk to a server that has no password.

The app listens on 127.0.0.1 and asks nobody to log in, which is right for a
tool that runs on your own laptop. What was wrong was the second half: it also
answered every website with `Access-Control-Allow-Origin: *`.

Those two together are not "no auth", they are "auth for everyone". While the
app is running, any page in the same browser - an ad on a news site, a link a
recruiter sent - can fetch http://127.0.0.1:8000/profile in the background and
READ the answer: the CV, the instructions, the case bank. And a plain form on
that page can POST /jobs/clear, because a form submission does not need CORS at
all.

So the rule is inverted here. Two kinds of caller are known and expected:

  * the browser extension, which posts scraped vacancies from its service
    worker and identifies itself as chrome-extension://<id>;
  * the app's own pages, served from this very machine.

Anything else that announces where it came from is refused. A request with no
Origin at all - the desktop window's own navigation, curl, the scheduler - is
not a cross-site request and passes untouched.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

# Chrome and Edge extension pages. The id is 32 letters a-p; Firefox uses a
# uuid under moz-extension. Matching the scheme is the point - an extension had
# to be installed deliberately, a web page did not.
_EXTENSION = re.compile(r"^(chrome-extension|moz-extension|extension)://[a-z0-9-]+/?$", re.I)

# Loopback under any port: the app picks 8000 but walks up to 8010 when taken.
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def is_extension(origin: str) -> bool:
    return bool(_EXTENSION.match((origin or "").strip()))


def is_local(origin: str) -> bool:
    """The app's own pages, whichever port it managed to bind."""
    parts = urlsplit((origin or "").strip())
    if parts.scheme not in ("http", "https"):
        return False
    return (parts.hostname or "") in _LOCAL_HOSTS or f"[{parts.hostname}]" in _LOCAL_HOSTS


def allowed(origin: str | None, extra: list[str] | None = None) -> bool:
    """Whether a request carrying this Origin may be served.

    `None` and "" mean the browser did not consider this a cross-origin request
    - or that there is no browser. Those are not the attack, and refusing them
    would break the desktop window itself."""
    if not origin:
        return True
    origin = origin.strip()
    if origin == "null":            # sandboxed iframe, data: URL, file://
        return False
    if is_extension(origin) or is_local(origin):
        return True
    return origin in {o.strip() for o in (extra or []) if o.strip() and o.strip() != "*"}


# Handed to CORSMiddleware so the browser is told the same thing the server
# enforces. Written as a regex because the extension's id is not known here and
# the port is not known until the app binds one.
ALLOW_REGEX = r"^(chrome-extension|moz-extension|extension)://[a-z0-9-]+$|^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$"
