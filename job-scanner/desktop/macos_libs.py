"""Collect the native dylibs WeasyPrint needs (pango, cairo, glib, harfbuzz,
fontconfig, freetype, gdk-pixbuf …) from Homebrew, so PDF export works inside
the packaged .app.

WeasyPrint dlopen()s these by bare name at runtime, so PyInstaller's static
analysis never sees them - we must gather them explicitly. Used by
JobFinder.spec at build time (macOS only). Returns PyInstaller `binaries`
tuples: (absolute_src, "."), which land in Contents/Frameworks.
"""

from __future__ import annotations

import glob
import os
import re
import subprocess
from pathlib import Path

# Library families the WeasyPrint text/graphics stack pulls in.
_FAMILIES = [
    "glib-2.0", "gobject-2.0", "gio-2.0", "gmodule-2.0", "gthread-2.0",
    "pango-1.0", "pangocairo-1.0", "pangoft2-1.0",
    "cairo", "cairo-gobject",
    "harfbuzz", "harfbuzz-subset", "fribidi",
    "fontconfig", "freetype",
    "gdk_pixbuf-2.0",
    "pixman-1", "png16", "jpeg", "tiff",
    "intl", "ffi", "graphite2", "pcre2-8", "z",
    "brotlicommon", "brotlidec", "brotlienc",
    "expat",
]


def _brew_prefix() -> str | None:
    for cmd in (["brew", "--prefix"],):
        try:
            out = subprocess.check_output(cmd, text=True).strip()
            if out and os.path.isdir(out):
                return out
        except Exception:
            pass
    for guess in ("/opt/homebrew", "/usr/local"):
        if os.path.isdir(os.path.join(guess, "lib")):
            return guess
    return None


def _deps(dylib: str) -> list[str]:
    """Transitive Homebrew/opt dependencies of a dylib via otool -L."""
    try:
        out = subprocess.check_output(["otool", "-L", dylib], text=True)
    except Exception:
        return []
    deps = []
    for line in out.splitlines()[1:]:
        m = re.match(r"\s+(\S+)", line)
        if not m:
            continue
        path = m.group(1)
        if any(seg in path for seg in ("/opt/homebrew/", "/usr/local/", "/Cellar/")):
            deps.append(path)
    return deps


def collect_binaries() -> list[tuple[str, str]]:
    prefix = _brew_prefix()
    if not prefix:
        print("[macos_libs] Homebrew not found — PDF export won't be bundled. "
              "Run: brew install pango")
        return []
    libdir = os.path.join(prefix, "lib")

    seeds: set[str] = set()
    for fam in _FAMILIES:
        for path in glob.glob(os.path.join(libdir, f"lib{fam}*.dylib")):
            seeds.add(path)

    # Walk the dependency graph so nothing is missed.
    seen: set[str] = set()
    stack = list(seeds)
    while stack:
        lib = stack.pop()
        real = str(Path(lib).resolve())
        if real in seen or not os.path.exists(real):
            continue
        seen.add(real)
        stack.extend(_deps(real))

    # Keep BOTH the resolved file and its symlink names (e.g. libpango-1.0.dylib
    # -> libpango-1.0.0.dylib) so bare-name dlopen resolves.
    out: dict[str, str] = {}
    for real in seen:
        out[real] = "."
    for path in seeds:
        out[path] = "."          # includes unversioned symlinks
    binaries = [(src, dest) for src, dest in out.items()]
    print(f"[macos_libs] bundling {len(binaries)} native dylibs for WeasyPrint")
    return binaries
