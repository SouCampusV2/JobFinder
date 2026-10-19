"""Resource + data path resolution that works both in dev and when frozen
by PyInstaller into a macOS .app bundle.

- `app_root()` - where bundled read-only resources live (templates, prompts).
  In dev this is the project directory; when frozen it is PyInstaller's
  extraction dir (`sys._MEIPASS`).
- `user_data_dir()` - a writable per-user directory for the database and any
  runtime files, because the .app bundle itself is read-only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def app_root() -> Path:
    """Directory that contains bundled resources (templates/, matcher/prompts/…)."""
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def user_data_dir() -> Path:
    """Writable app-support directory. Honors JOBFINDER_DATA_DIR if set."""
    override = os.getenv("JOBFINDER_DATA_DIR")
    if override:
        p = Path(override).expanduser()
    elif sys.platform == "darwin":
        p = Path.home() / "Library" / "Application Support" / "Job Finder"
    elif sys.platform.startswith("win"):
        p = Path(os.getenv("APPDATA", Path.home())) / "Job Finder"
    else:
        p = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "job-finder"
    p.mkdir(parents=True, exist_ok=True)
    return p
