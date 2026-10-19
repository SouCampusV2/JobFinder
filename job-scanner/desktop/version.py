"""Single source of truth for the app version.

Bump this before every release and tag the GitHub release `v<version>` with a
matching macOS asset (see desktop/README.md). The updater compares this value
to the latest GitHub release tag.
"""

__version__ = "1.4.1"

# GitHub repo that hosts the releases (binaries only), separate from the code
# repo (andrii424/JobFinder). The updater reads it without authentication, so it
# must stay public.
GITHUB_REPO = "andrii424/JobFinder-releases"

# Which release asset belongs to which platform. The updater used to know only
# the first line and gave up when it did not find it - on every platform. A
# Windows user was therefore never told an update existed, however faithfully
# the installer was attached to the release.
MACOS_ASSET_HINT = "macOS"
WINDOWS_ASSET_HINT = "Setup.exe"
