"""Which build a machine is offered.

The updater looked for a zip with "macOS" in its name and gave up when it did
not find one - on every platform, because nothing in that branch asked what it
was running on. A Windows user was never told an update existed, however
faithfully the installer was attached to the release.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))

import updater  # noqa: E402
from version import MACOS_ASSET_HINT, WINDOWS_ASSET_HINT  # noqa: E402

FULL_RELEASE = [
    {"name": "JobFinder-macOS.zip", "browser_download_url": "https://x/mac.zip"},
    {"name": "JobFinder.dmg", "browser_download_url": "https://x/mac.dmg"},
    {"name": "JobFinder-Setup.exe", "browser_download_url": "https://x/win.exe"},
]


def test_each_platform_is_offered_its_own_build():
    assert updater.asset_for_platform(FULL_RELEASE, "darwin") == "https://x/mac.zip"
    assert updater.asset_for_platform(FULL_RELEASE, "win32") == "https://x/win.exe"


def test_the_dmg_is_never_offered_to_the_updater():
    """It is what a new user installs from by hand. The running app updates from
    the zip, which it can unpack itself."""
    assert not (updater.asset_for_platform(FULL_RELEASE, "darwin") or "").endswith(".dmg")


def test_a_release_missing_your_platform_offers_nothing():
    """Rather than handing back somebody else's build. Releases 1.2.0 to 1.2.3
    carried no Windows installer at all."""
    mac_only = FULL_RELEASE[:2]

    assert updater.asset_for_platform(mac_only, "win32") is None
    assert updater.asset_for_platform(mac_only, "darwin") is not None


def test_an_empty_release_is_not_an_update():
    assert updater.asset_for_platform([], "darwin") is None
    assert updater.asset_for_platform(None, "win32") is None


def test_an_unknown_platform_is_offered_nothing_rather_than_a_guess():
    assert updater.asset_for_platform(FULL_RELEASE, "linux") is None


def test_the_hints_match_what_the_release_gate_requires():
    """The updater looks for the same file names the publish check insists on;
    if those two drift, one of them is wrong about every release."""
    from desktop.check_release_assets import REQUIRED

    names = [a.name for a in REQUIRED]
    assert any(MACOS_ASSET_HINT.lower() in n.lower() for n in names)
    assert any(WINDOWS_ASSET_HINT.lower() in n.lower() for n in names)


def test_windows_does_not_swap_files_under_a_running_app(monkeypatch):
    """An installer cannot replace the .exe running it. Swapping files under a
    live process is what broke the Profile page on macOS."""
    opened = []
    monkeypatch.setattr(updater.sys, "platform", "win32")
    monkeypatch.setattr(updater.webbrowser, "open", lambda url: opened.append(url) or True)

    started = updater.download_and_apply("https://x/win.exe")

    assert started is False, "the app must not think a hand-off is in progress"
    assert opened == ["https://x/win.exe"], "the download was not handed to the browser"
