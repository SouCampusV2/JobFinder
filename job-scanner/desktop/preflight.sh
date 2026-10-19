#!/usr/bin/env bash
# Everything that must be true before a release is published, in one command.
#
#   cd job-scanner && ./desktop/preflight.sh
#
# It changes nothing and publishes nothing. It either prints the exact publish
# command with every asset filled in, or it says what is not ready and why.
# See RELEASE.md for the full sequence this belongs to.
set -uo pipefail
cd "$(dirname "$0")/.."

PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"
FAIL=0
say() { printf '\n\033[1m%s\033[0m\n' "$1"; }

say "1/4  Tests"
if $PY -m pytest tests -q; then
  echo "     ✓ suite green"
else
  echo "     ✗ tests failed — nothing else matters until they pass"
  FAIL=1
fi

say "2/4  Version"
VERSION="$($PY -c 'import sys; sys.path.insert(0,"desktop"); from version import __version__; print(__version__)')"
REPO="$($PY -c 'import sys; sys.path.insert(0,"desktop"); from version import GITHUB_REPO; print(GITHUB_REPO)')"
LATEST="$(gh release view --repo "$REPO" --json tagName --jq .tagName 2>/dev/null || echo "none")"
echo "     desktop/version.py : $VERSION"
echo "     published latest   : $LATEST"
if [ "v$VERSION" = "$LATEST" ]; then
  echo "     ✗ version.py still matches the published release — bump it first"
  FAIL=1
else
  echo "     ✓ v$VERSION is not published yet"
fi

say "3/4  Build artifacts"
if ! $PY desktop/check_release_assets.py; then
  FAIL=1
fi

say "4/4  What ships"
git status --short || true

if [ "$FAIL" -ne 0 ]; then
  say "NOT READY — fix the above, then run this again."
  exit 1
fi

say "READY. Publish with:"
cat <<CMD

  gh release create v$VERSION \\
    dist/JobFinder-macOS.zip \\
    dist/JobFinder.dmg \\
    dist/JobFinder-Setup.exe \\
    -R $REPO \\
    --title "$VERSION — <what got better>" \\
    --notes-file <notes.md>

CMD
