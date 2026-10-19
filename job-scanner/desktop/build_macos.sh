#!/bin/bash
# Build Job Finder.app for macOS and zip it for a GitHub release.
#
#   cd job-scanner
#   ./desktop/build_macos.sh
#
# Output:
#   dist/Job Finder.app          ← the app you can run / drag to /Applications
#   dist/JobFinder.dmg           ← the finished installer to hand people (drag-to-Applications)
#   dist/JobFinder-macOS.zip     ← attach THIS to the GitHub release (updater looks for it)
set -euo pipefail

cd "$(dirname "$0")/.."          # project root (job-scanner)

echo "==> Using Python: $(which python3)"
echo "==> Installing build deps…"
python3 -m pip install -q -r requirements.txt
python3 -m pip install -q -r desktop/requirements-desktop.txt

echo "==> Cleaning previous build…"
rm -rf build "dist/Job Finder" "dist/Job Finder.app" dist/JobFinder-macOS.zip

echo "==> Running PyInstaller…"
# `python3 -m`, not the `pyinstaller` script: a virtualenv's console scripts
# carry the absolute path they were created with in their shebang, so every one
# of them broke the day this directory was renamed. The module entry point does
# not care where the venv lives.
python3 -m PyInstaller desktop/JobFinder.spec --noconfirm

APP="dist/Job Finder.app"
if [ ! -d "$APP" ]; then
  echo "!! Build failed: $APP not found"; exit 1
fi

echo "==> Zipping app for release (preserves symlinks with ditto)…"
( cd dist && ditto -c -k --sequesterRsrc --keepParent "Job Finder.app" "JobFinder-macOS.zip" )

echo "==> Building a drag-to-install DMG…"
rm -f dist/JobFinder.dmg
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"           # drag target
hdiutil create -volname "Job Finder" -srcfolder "$STAGE" \
  -fs HFS+ -format UDZO -ov "dist/JobFinder.dmg" >/dev/null
rm -rf "$STAGE"

echo ""
echo "✅ Done."
echo "   App:        $APP"
echo "   Installer:  dist/JobFinder.dmg          ← hand THIS to people"
echo "   Update zip: dist/JobFinder-macOS.zip     ← attach to the GitHub release"
echo ""
echo "Try it:  open dist/JobFinder.dmg   → drag Job Finder into Applications."
echo "First launch is unsigned → right-click the app → Open (once) to bypass Gatekeeper,"
echo "or sign+notarize later (see desktop/README.md)."
