# Job Finder — macOS desktop build

Packages the existing FastAPI app into a native `Job Finder.app` using
**pywebview** (native WKWebView window, no Chromium) + **PyInstaller**, with a
built-in **GitHub Releases auto-updater**.

## How it works

- `desktop/launcher.py` — starts the FastAPI server on a random local port
  inside the app process, then opens it in a native window. On launch it checks
  GitHub for a newer release and offers a one-click update.
- `desktop/updater.py` — compares `desktop/version.py` `__version__` to the
  latest GitHub release tag; downloads the macOS `.zip`, swaps the `.app`, and
  relaunches.
- Data (the SQLite DB) is stored in `~/Library/Application Support/Job Finder/`,
  not inside the read-only `.app`.

## 1. One-time setup

Edit `desktop/version.py`:
- `GITHUB_REPO = "your-github-user/your-repo"`
- keep `__version__` in sync with your release tags.

(Optional) add an icon at `desktop/icon.icns`.

## 2. Build

```bash
cd job-scanner
./desktop/build_macos.sh
```

Produces:
- `dist/Job Finder.app` — run with `open "dist/Job Finder.app"`
- `dist/JobFinder-macOS.zip` — attach this to the GitHub release

First launch of an **unsigned** app: right-click the app → **Open** → **Open**
(only needed once), or sign + notarize (below).

## 3. Release (so the updater works)

1. Bump `__version__` in `desktop/version.py` (e.g. `1.1.0`) and rebuild.
2. Create a GitHub release tagged **`v1.1.0`** (must match).
3. Upload `dist/JobFinder-macOS.zip` as a release asset (the updater looks for a
   `.zip` whose name contains `macOS`/`mac`).

Users on an older build get an "Update available" prompt on next launch.

## 4. (Optional) Sign & notarize — removes the Gatekeeper warning

Requires an Apple Developer account ($99/yr).

```bash
# Sign
codesign --deep --force --options runtime \
  --sign "Developer ID Application: Your Name (TEAMID)" \
  "dist/Job Finder.app"

# Notarize (needs an app-specific password stored once via notarytool)
ditto -c -k --keepParent "dist/Job Finder.app" "dist/JobFinder-macOS.zip"
xcrun notarytool submit "dist/JobFinder-macOS.zip" \
  --apple-id you@example.com --team-id TEAMID --password "app-specific-pw" --wait
xcrun stapler staple "dist/Job Finder.app"
# re-zip after stapling and use THAT zip for the release
```

## Updates UI

- **Automatic:** on launch the app checks GitHub and prompts if a newer release
  exists.
- **Manual:** menu bar → **Updates → Check for Updates…** (tells you either way).

## PDF export (WeasyPrint native libs)

`desktop/macos_libs.py` collects the `pango`/`cairo`/`glib`/`harfbuzz`/… dylibs
from Homebrew at build time and bundles them into `Contents/Frameworks`, so PDF
export works on machines without Homebrew.

- **Build prerequisite:** the build machine needs them installed once —
  `brew install pango` (pulls in the rest). If Homebrew isn't found, the build
  still succeeds but PDF export degrades gracefully (buttons show an error).
- WeasyPrint `dlopen()`s these by name, so at runtime the app sets
  `DYLD_FALLBACK_LIBRARY_PATH` to the bundled Frameworks dir and re-execs once
  (`_ensure_dyld()` in `launcher.py`).
- ⚠️ **Hardened runtime caveat:** macOS strips `DYLD_*` env vars from a
  **notarized / hardened-runtime** build, which would break this trick. For an
  unsigned "me + friends" build it works as-is. When you notarize, switch to
  rewriting the dylib load paths with `install_name_tool`/`@rpath` (or ship
  pango via a first-run `brew` helper). Text/scoring/scanning are unaffected —
  only PDF export depends on these libs.

## Windows build — two ways

### A. Installer built ON macOS (no Windows, no PyInstaller) — `JobFinder-Setup.exe`

You **can** produce a Windows installer from a Mac, because Python is interpreted
— you bundle it instead of compiling it. `desktop/build_windows_installer_macos.sh`
downloads an **embeddable CPython 3.11 for Windows** + all deps as `win_amd64`
wheels + the app source, then compiles an **NSIS** installer with `makensis`
(which runs on macOS).

```bash
brew install makensis                          # one-time
cd job-scanner
./desktop/build_windows_installer_macos.sh     # → dist/JobFinder-Setup.exe
```

Per-user installer (no admin/UAC), adds Start-Menu + Desktop shortcuts and an
uninstaller. It launches via bundled `pythonw.exe` (no console window); pywebview
uses the **WebView2/Edge** runtime (present on Win10/11), and pythonnet's default
**.NET Framework** runtime (also built into Windows) — so no extra runtimes.

> ⚠️ **Untested by construction.** A Mac can build this but cannot *run* it — the
> first real test is a Windows 10/11 machine. Risk areas: WebView2 init and PDF
> export (needs the GTK runtime; degrades gracefully without it). For a build you
> can actually iterate on, use option B.

### B. PyInstaller on real Windows (or a `windows-latest` CI runner) — `Job Finder.exe`

**PyInstaller does NOT cross-compile** — this path must run ON Windows (a real
PC, a Windows VM like Parallels/UTM, or a GitHub Actions `windows-latest`
runner). A Mac cannot produce this `.exe`.

On the Windows machine:
1. Install Python 3.11+ from python.org (tick **Add python.exe to PATH**).
2. Open Command Prompt, `cd` into the `job-scanner` folder.
3. Run: `desktop\build_windows.bat`

Output: `dist\Job Finder\Job Finder.exe`. Share the **whole `dist\Job Finder`
folder** (zip it) — the `.exe` needs the files next to it. pywebview uses the
built-in **WebView2/Edge** runtime (present on Win10/11).

Notes for Windows:
- **SmartScreen** will warn on an unsigned `.exe` (click *More info → Run
  anyway*), same idea as macOS Gatekeeper. Sign with an OV/EV cert or Azure
  Trusted Signing to remove it.
- **PDF export** needs the GTK (pango/cairo) runtime, which isn't bundled by the
  Windows spec yet — install "GTK3 runtime for Windows" or PDF export will
  degrade gracefully.
- The auto-updater's swap logic is macOS-only; on Windows the "update available"
  prompt opens the GitHub releases page in the browser instead.

## Known limitations

- Intel vs Apple Silicon: PyInstaller builds for the architecture you build on.
  Build on Apple Silicon for `arm64`; use a universal2 Python to ship both.
