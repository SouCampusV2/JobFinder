# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Job Finder on WINDOWS.

Build (on a Windows machine):
    cd job-scanner
    pyinstaller desktop\\JobFinder-win.spec --noconfirm
Output:
    dist\\Job Finder\\Job Finder.exe   (a folder - zip the whole "Job Finder" folder to share)

Note: PyInstaller does NOT cross-compile. Run this ON Windows.
"""
import os
from PyInstaller.utils.hooks import collect_submodules

SPECPATH = os.path.abspath(os.path.dirname(SPEC))       # noqa: F821
ROOT = os.path.dirname(SPECPATH)

datas = [
    (os.path.join(ROOT, "templates"), "templates"),
    (os.path.join(ROOT, "matcher", "prompts"), os.path.join("matcher", "prompts")),
]

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
    # pywebview's Windows (EdgeChromium / WebView2) backend
    "webview.platforms.winforms", "clr",
]

icon = os.path.join(ROOT, "desktop", "icon.ico")
icon = icon if os.path.exists(icon) else None

a = Analysis(
    [os.path.join(ROOT, "desktop", "launcher.py")],
    pathex=[ROOT],
    binaries=[],
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
    console=False,          # no console window
    icon=icon,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, name="Job Finder",
)
