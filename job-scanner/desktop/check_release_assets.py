"""The gate that stands between a build and a publish.

Four releases in a row went out with macOS assets only, and the first anyone
knew of it was Windows users saying the app did not exist. Nothing was broken:
the build script for Windows works and had simply not been run, and the publish
command named two files instead of three. A checklist made of prose failed at
exactly the step where prose is easiest to skim, so the check is code.

Run directly, or from `desktop/preflight.sh`:

    python desktop/check_release_assets.py            # checks dist/
    python desktop/check_release_assets.py --dist X   # checks X
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

# Every file a release must carry, why it exists, and how to make it. Adding a
# platform means adding a line here - and the publish then refuses until it is
# built, rather than quietly going out without it.
@dataclass(frozen=True)
class Asset:
    name: str
    purpose: str
    built_by: str
    min_bytes: int


REQUIRED: tuple[Asset, ...] = (
    Asset("JobFinder-macOS.zip",
          "what the in-app updater downloads on macOS",
          "./desktop/build_macos.sh", 5_000_000),
    Asset("JobFinder.dmg",
          "what a new macOS user installs from",
          "./desktop/build_macos.sh", 5_000_000),
    Asset("JobFinder-Setup.exe",
          "what a Windows user installs from",
          "./desktop/build_windows_installer_macos.sh", 5_000_000),
)


# Directories that hold outputs and copies rather than sources.
_SKIP = {"dist", "build", ".venv", "__pycache__", ".git", "node_modules"}


def newest_source(root: Path) -> tuple[Path | None, float]:
    """The most recently edited source file, and when. A build older than this
    is a build of something else."""
    newest, when = None, 0.0
    for path in root.rglob("*"):
        if path.suffix not in (".py", ".html", ".css", ".js", ".txt", ".sh"):
            continue
        if any(part in _SKIP for part in path.parts):
            continue
        mtime = path.stat().st_mtime
        if mtime > when:
            newest, when = path, mtime
    return newest, when


def problems(dist: Path, root: Path | None = None) -> list[str]:
    """Everything wrong with this dist/ directory, in the order a human fixes it."""
    found = []
    source, source_time = newest_source(root) if root else (None, 0.0)
    for asset in REQUIRED:
        path = dist / asset.name
        if not path.exists():
            found.append(f"MISSING  {asset.name} — {asset.purpose}. Build it: {asset.built_by}")
            continue
        size = path.stat().st_size
        if size < asset.min_bytes:
            found.append(
                f"TOO SMALL {asset.name} is {size / 1e6:.1f}MB, under "
                f"{asset.min_bytes / 1e6:.0f}MB — the build almost certainly failed. "
                f"Rebuild: {asset.built_by}")
            continue
        # The failure this check exists for: a Setup.exe from an earlier release
        # is still sitting in dist/, so "the file is there" says nothing at all.
        if source_time and path.stat().st_mtime < source_time:
            found.append(
                f"STALE    {asset.name} is older than {source.name if source else 'the code'} "
                f"— it was built before the change you are shipping. "
                f"Rebuild: {asset.built_by}")
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dist", default="dist", help="directory holding the built assets")
    args = ap.parse_args(argv)

    dist = Path(args.dist)
    found = problems(dist, root=Path(__file__).resolve().parents[1])
    if found:
        print(f"✗ Not ready to publish ({len(found)} problem(s)):\n")
        for line in found:
            print(f"   {line}")
        print("\nNothing was published. Fix the above and run this again.")
        return 1

    print("✓ All release assets present:\n")
    for asset in REQUIRED:
        size = (dist / asset.name).stat().st_size / 1e6
        print(f"   {asset.name:24} {size:6.1f}MB   {asset.purpose}")
    print("\nAttach ALL of them to the release, in one command.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
