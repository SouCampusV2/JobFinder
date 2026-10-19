"""Lightweight GitHub-Releases auto-updater for the macOS app.

Flow:
  1. On launch, ask GitHub for the latest release of GITHUB_REPO.
  2. If its tag (e.g. "v1.1.0") is newer than the bundled __version__, prompt.
  3. On accept: download the release's macOS .zip asset, unpack the new
     Job Finder.app, then hand off to a small detached shell script that waits
     for THIS process to quit, swaps the .app in place, and relaunches it.

Only stdlib is used (urllib/json/zipfile) so nothing extra needs bundling.
Everything is best-effort and never raises into the app: a failed check just
means "no update this time".
"""

from __future__ import annotations

import json
import logging
import ssl
import subprocess
import sys
import tempfile
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

try:
    from desktop.version import (GITHUB_REPO, MACOS_ASSET_HINT,
                                 WINDOWS_ASSET_HINT, __version__)
except Exception:  # when run as a bundled top-level module
    from version import (GITHUB_REPO, MACOS_ASSET_HINT,  # type: ignore
                         WINDOWS_ASSET_HINT, __version__)

logger = logging.getLogger("jobfinder.updater")

_API = "https://api.github.com/repos/{repo}/releases/latest"


# --------------------------------------------------------------------------- #
# Version helpers                                                             #
# --------------------------------------------------------------------------- #
def _parse(v: str) -> tuple[int, ...]:
    v = (v or "").strip().lstrip("vV")
    parts: list[int] = []
    for chunk in v.split("."):
        num = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts) or (0,)


def is_newer(latest: str, current: str) -> bool:
    a, b = _parse(latest), _parse(current)
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return a > b


# --------------------------------------------------------------------------- #
# Release lookup                                                              #
# --------------------------------------------------------------------------- #
def asset_for_platform(assets: list, platform: str | None = None) -> str | None:
    """The download that belongs to the machine asking.

    Returns None when the release carries nothing for this platform. That is a
    real answer and the caller must report "no update" rather than hand back
    somebody else's build - which is what happened for two years of releases:
    the search was for a macOS zip whatever the platform, so a Windows user was
    never offered an update at all."""
    plat = platform or sys.platform
    for a in assets or []:
        name = (a.get("name") or "").lower()
        if plat.startswith("win"):
            if name.endswith(".exe") and WINDOWS_ASSET_HINT.lower() in name:
                return a.get("browser_download_url")
        elif plat == "darwin":
            if name.endswith(".zip") and (MACOS_ASSET_HINT.lower() in name or "mac" in name):
                return a.get("browser_download_url")
    return None


def check_latest() -> dict | None:
    """Return {'version','tag','url','notes'} for the latest release, or None."""
    if not GITHUB_REPO or "/" not in GITHUB_REPO:
        return None
    url = _API.format(repo=GITHUB_REPO)
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "JobFinder-Updater",
    })
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.info("Update check skipped: %s", exc)
        return None

    tag = data.get("tag_name") or ""
    asset_url = asset_for_platform(data.get("assets", []))
    return {
        "version": tag.lstrip("vV"),
        "tag": tag,
        "url": asset_url,
        "notes": (data.get("body") or "").strip(),
    }


def update_available() -> dict | None:
    """Latest release info if it is strictly newer than the running build."""
    info = check_latest()
    if info and info.get("url") and is_newer(info["version"], __version__):
        return info
    return None


# --------------------------------------------------------------------------- #
# Applying an update                                                          #
# --------------------------------------------------------------------------- #
def _current_app_bundle() -> Path | None:
    """Path to the running `Job Finder.app` (…/Job Finder.app), or None in dev."""
    exe = Path(sys.executable).resolve()
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent
    return None


def download_and_apply(asset_url: str) -> bool:
    """Download the new .app zip and relaunch into it. Returns True if the
    hand-off script was started (the app should then quit)."""
    if sys.platform.startswith("win"):
        # An installer cannot replace the .exe that is running it, and swapping
        # files under a live process is exactly what broke the Profile page on
        # macOS. Hand the download to the browser; the user installs it with the
        # app closed, which is how Windows installers work anyway.
        logger.info("Windows: opening the installer download rather than swapping files.")
        webbrowser.open(asset_url)
        return False

    app_bundle = _current_app_bundle()
    if app_bundle is None:
        logger.warning("Not running from an .app bundle — opening the download page instead.")
        subprocess.Popen(["open", asset_url])
        return False

    tmp = Path(tempfile.mkdtemp(prefix="jobfinder-update-"))
    zip_path = tmp / "update.zip"
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(asset_url, headers={"User-Agent": "JobFinder-Updater"})
        with urllib.request.urlopen(req, timeout=60, context=ctx) as r, open(zip_path, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
    except Exception as exc:  # noqa: BLE001
        logger.error("Update download failed: %s", exc)
        return False

    new_app = None
    for p in tmp.rglob("*.app"):
        new_app = p
        break
    if new_app is None:
        logger.error("No .app found inside the update archive.")
        return False

    # Detached script: wait for us to exit, replace the bundle, relaunch.
    script = tmp / "swap.sh"
    dest = app_bundle
    script.write_text(
        "#!/bin/bash\n"
        "set -e\n"
        f'NEW="{new_app}"\n'
        f'DEST="{dest}"\n'
        "for i in $(seq 1 50); do\n"
        f'  if ! pgrep -f "{dest.name}/Contents/MacOS" >/dev/null; then break; fi\n'
        "  sleep 0.2\n"
        "done\n"
        'sleep 0.5\n'
        'rm -rf "$DEST"\n'
        'ditto "$NEW" "$DEST"\n'
        'xattr -dr com.apple.quarantine "$DEST" || true\n'
        'open "$DEST"\n'
    )
    script.chmod(0o755)
    subprocess.Popen(["/bin/bash", str(script)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True
