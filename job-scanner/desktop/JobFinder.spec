# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Job Finder (macOS .app).

Build:  cd job-scanner && pyinstaller desktop/JobFinder.spec --noconfirm
Output: dist/Job Finder.app
"""
import os, sys
from PyInstaller.utils.hooks import collect_submodules

SPECPATH = os.path.abspath(os.path.dirname(SPEC))       # noqa: F821 (SPEC injected)
ROOT = os.path.dirname(SPECPATH)                         # the job-scanner project dir
sys.path.insert(0, os.path.join(ROOT, "desktop"))

# Single source of truth for the version - the bundle used to hardcode 1.0.0
# and drifted, so Finder showed 1.0.0 for a 1.0.3 build.
from version import __version__ as APP_VERSION  # noqa: E402

# Templates are listed one by one, so a subdirectory can keep its own name in
# the bundle (see below) instead of being flattened into templates/.
datas = [
    (os.path.join(ROOT, "matcher", "prompts"), os.path.join("matcher", "prompts")),
]
for _name in sorted(os.listdir(os.path.join(ROOT, "templates"))):
    if _name.startswith("."):
        continue
    _src = os.path.join(ROOT, "templates", _name)
    # A subdirectory (e.g. templates/partials) must keep its name in the
    # destination, or PyInstaller copies its files into templates/ flat and an
    # include like 'partials/_x.html' cannot be found at runtime.
    _dest = "templates" if os.path.isfile(_src) else os.path.join("templates", _name)
    datas.append((_src, _dest))

# Native libraries for WeasyPrint (pango/cairo/…) so PDF export works.
binaries = []
try:
    from macos_libs import collect_binaries
    binaries = collect_binaries()
except Exception as _exc:
    print("[spec] WeasyPrint dylib collection skipped:", _exc)

hiddenimports = []
for pkg in ("uvicorn", "apscheduler", "aiosqlite", "anyio", "openai", "httpx", "webview"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass
hiddenimports += [
    "uvicorn.lifespan.on", "uvicorn.lifespan.off",
    "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "bs4", "dotenv",
]

# Text codecs, by name, because nothing imports them by name. Python looks a
# codec up as a string at the moment it is needed, so the packaged app carried
# no windows-1252 - and BeautifulSoup decodes `&#150;`, the en dash half the
# job ads in Europe are written with, through exactly that codec. It raised
# `LookupError: unknown encoding: windows-1252` from inside a parser call and
# killed 84 whole searches over seven days. No test could see it: a normal
# Python install has every codec, so it only ever happened in a build.
hiddenimports += collect_submodules("encodings")

a = Analysis(
    [os.path.join(ROOT, "desktop", "launcher.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Job Finder",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # no terminal window
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, name="Job Finder",
)

app = BUNDLE(
    coll,
    name="Job Finder.app",
    icon=os.path.join(ROOT, "desktop", "icon.icns") if os.path.exists(
        os.path.join(ROOT, "desktop", "icon.icns")) else None,
    bundle_identifier="com.andriistakhov.jobfinder",
    info_plist={
        "CFBundleName": "Job Finder",
        "CFBundleDisplayName": "Job Finder",
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
    },
)
