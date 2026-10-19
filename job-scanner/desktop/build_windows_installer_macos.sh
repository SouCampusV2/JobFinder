#!/usr/bin/env bash
# Build the Windows installer (JobFinder-Setup.exe) ENTIRELY ON macOS — no
# Windows machine and no PyInstaller. It bundles an embeddable CPython for
# Windows + all dependencies as win_amd64 wheels + the app source, then compiles
# an NSIS installer with makensis.
#
# Prereqs (one-time):  brew install makensis
# Run:                 cd job-scanner && ./desktop/build_windows_installer_macos.sh
# Output:              dist/JobFinder-Setup.exe
#
# ⚠️ This build is UNTESTED on macOS by definition — it can only be verified by
# running it on a real Windows 10/11 machine (which needs the WebView2 runtime,
# standard on current Windows). PDF export needs the GTK runtime on Windows and
# degrades gracefully without it.
set -euo pipefail
cd "$(dirname "$0")/.."                     # project root (job-scanner)

PY_EMBED_VER="3.11.9"                        # must stay on the 3.11 line (cp311 wheels)
ABI="cp311"; PYVER="3.11"; PLAT="win_amd64"
APPVERSION="$(python3 - <<'PY'
import re,sys
sys.path.insert(0,"desktop")
from version import __version__; print(__version__)
PY
)"
WS="build/winstaller"
SP="$WS/payload/python/Lib/site-packages"

command -v makensis >/dev/null || { echo "makensis not found — run: brew install makensis"; exit 1; }

echo "==> Clean workspace"
rm -rf "$WS"; mkdir -p "$WS/wheels" "$WS/wheels2" "$SP" "$WS/payload/app"

echo "==> Download embeddable Python $PY_EMBED_VER ($PLAT)"
curl -sSL -o "$WS/py-embed.zip" \
  "https://www.python.org/ftp/python/${PY_EMBED_VER}/python-${PY_EMBED_VER}-embed-amd64.zip"
unzip -q "$WS/py-embed.zip" -d "$WS/payload/python"

echo "==> Download Windows wheels (from requirements.txt, minus mac/build-only)"
# Note: uvicorn (not [standard]) — uvloop has no Windows wheel. pythonnet is
# pywebview's Windows .NET bridge (marker-guarded, so request it explicitly).
# tzdata is REQUIRED on Windows: unlike macOS/Linux it ships no system time
# zone database, so zoneinfo/APScheduler fail with ZoneInfoNotFoundError and
# the app never starts. This cost a release to find — do not drop it.
python3 -m pip download --only-binary=:all: --platform "$PLAT" \
  --python-version "$PYVER" --implementation cp --abi "$ABI" -d "$WS/wheels" \
  fastapi==0.115.0 uvicorn==0.30.6 jinja2==3.1.4 python-multipart==0.0.9 \
  aiosqlite==0.20.0 openai==1.55.3 httpx==0.27.2 python-telegram-bot==21.6 \
  python-dotenv==1.0.1 beautifulsoup4==4.12.3 APScheduler==3.10.4 pypdf==5.1.0 \
  markdown==3.7 weasyprint==62.3 pydyf==0.11.0 pythonnet tzdata

echo "==> Download pywebview 5.x + its pure-python deps"
# pywebview's 'proxy_tools' is sdist-only, so a bare --only-binary resolve
# silently backtracks to ancient pywebview 2.x. Pull 5.x with --no-deps and add
# its deps separately.
python3 -m pip download --no-deps --only-binary=:all: --platform "$PLAT" \
  --python-version "$PYVER" --implementation cp --abi "$ABI" -d "$WS/wheels2" pywebview==5.4
python3 -m pip download --no-deps -d "$WS/wheels2" bottle
python3 -m pip wheel   --no-deps -w "$WS/wheels2" proxy_tools

echo "==> Unpack wheels into site-packages"
for w in "$WS"/wheels/*.whl "$WS"/wheels2/*.whl; do unzip -qo "$w" -d "$SP"; done
rm -rf "$SP"/*.data                          # wheel data dirs (scripts) not needed

echo "==> Configure embeddable python path file"
cat > "$WS/payload/python/python311._pth" <<'PTH'
python311.zip
.
Lib\site-packages
import site
PTH

echo "==> Copy app source"
rsync -a --exclude='.venv' --exclude='data' --exclude='dist' --exclude='build' \
  --exclude='__pycache__' --exclude='.git' --exclude='.env' --exclude='.DS_Store' \
  --exclude='*.pyc' --exclude='*.spec' --exclude='run-*.sh' ./ "$WS/payload/app/"

echo "==> Compile installer with makensis (v$APPVERSION)"
cp desktop/installer.nsi "$WS/installer.nsi"
( cd "$WS" && makensis -DAPPVERSION="$APPVERSION" installer.nsi >/dev/null )
mkdir -p dist
mv "$WS/JobFinder-Setup.exe" dist/JobFinder-Setup.exe

echo
echo "✅ Done → dist/JobFinder-Setup.exe  (version $APPVERSION)"
echo "   Attach to a release:  gh release upload v$APPVERSION dist/JobFinder-Setup.exe -R andrii424/JobFinder-releases"
echo "   ⚠️ Test on a real Windows 10/11 box (needs the WebView2 runtime)."
