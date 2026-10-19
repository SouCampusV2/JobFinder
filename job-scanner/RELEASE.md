# Releasing Job Finder

Read this before publishing anything. It exists because releases 1.2.0 through
1.2.3 — four in a row — went out with macOS assets only. Nothing was broken:
the Windows installer builds fine on this Mac and had simply not been built, and
the publish command named two files where it should have named three. Windows
users found out for us.

**One command checks all of it:**

```
cd job-scanner && ./desktop/preflight.sh
```

It changes nothing. It prints either what is not ready, or the exact publish
command with every asset filled in.

---

## The sequence

### 1. Know what is shipping

`git status --short` and `CHANGES-since-1.1.0.md`. Every user-visible change in
the tree belongs in the release notes; anything in the tree that is *not* ready
to ship must come out before the build, not be explained away in the notes.

### 2. Tests

```
.venv/bin/python -m pytest tests -q
```

Green, all of it. No network, no API calls, so a failure is a real failure.
A new guard is only worth having if it was **mutation-tested**: reintroduce the
bug once, watch the test fail, put the code back.

### 3. What the tests cannot see

The suite never opens a window. Before every release, start the app and check
the things that only exist at runtime:

- `./run-dev.sh`, then click through Jobs → a job → Profile → Settings.
- The **native window** specifically, if anything under `desktop/` changed —
  the packaged app is a different environment from the dev server. Text
  selection, the context menu and the update check only exist there.
- Generate one cover letter. It is the only path that spends money and the one
  a person waits on.

### 4. Bump the version

`desktop/version.py` → `__version__`. This is what the updater compares against
the published tag, so an unbumped version means nobody is offered the update.

### 5. Build **both** platforms

```
./desktop/build_macos.sh                      # → dist/JobFinder-macOS.zip, dist/JobFinder.dmg
./desktop/build_windows_installer_macos.sh    # → dist/JobFinder-Setup.exe   (needs: brew install makensis)
```

The Windows installer is built **on macOS** — embeddable CPython plus win_amd64
wheels, compiled by NSIS. No Windows machine is involved, which is also its
weakness: it cannot be run here, so it is verified only by someone installing it
on real Windows.

### 6. Gate

```
.venv/bin/python desktop/check_release_assets.py
```

Refuses to pass unless all three assets exist, are a plausible size, and are
**newer than the newest source file**. That last one is not paranoia: a
`JobFinder-Setup.exe` from an earlier release sits in `dist/` and would
otherwise be attached to a new version quite happily.

### 7. Commit and push the code

To the code repo `andrii424/JobFinder`. Message written for a product
audience: what changed and what got better, never the architecture.
**No `Co-Authored-By` trailer** — commits are signed by the maintainer alone.

### 8. READMEs

This repo's, and the public `andrii424/JobFinder-releases` one, which is the
page strangers land on. Update them only if what they say is now wrong.

### 9. Publish, with every asset in one command

```
gh release create v<x.y.z> \
  dist/JobFinder-macOS.zip \
  dist/JobFinder.dmg \
  dist/JobFinder-Setup.exe \
  -R andrii424/JobFinder-releases \
  --title "<x.y.z> — <what got better>" \
  --notes-file <notes.md>
```

Release notes in the same product voice as the commit.

### 10. Verify what actually went out

```
gh release view v<x.y.z> -R andrii424/JobFinder-releases --json assets --jq '.assets[].name'
```

Three names. If there are two, the release is incomplete — upload the third
immediately rather than waiting for the next version:

```
gh release upload v<x.y.z> dist/JobFinder-Setup.exe -R andrii424/JobFinder-releases
```

---

## If something is wrong after publishing

A release can be edited. Assets can be added and replaced without cutting a new
version, and that is almost always better than leaving a broken one up:

```
gh release upload  v<x> <file> -R andrii424/JobFinder-releases --clobber
gh release delete-asset v<x> <name> -R andrii424/JobFinder-releases
```

Only cut a new version when the *code* is wrong. The installed app is what
everyone uses all day, and it moves only when a release is
published — so a bad release is not academic.

---

## Known gaps

- **The in-app updater is macOS-only.** `desktop/updater.py` looks for a `.zip`
  whose name contains "macOS" and gives up when it does not find one, on every
  platform. A Windows user is therefore never told an update exists, even when
  `JobFinder-Setup.exe` is attached to it. Shipping the installer fixes the
  first complaint; it does not fix this one.
- **The Windows build is unverifiable here.** It is assembled on macOS and can
  only be proven by installing it on Windows 10/11. It needs the WebView2
  runtime (standard on current Windows); PDF export needs GTK and degrades
  without it.
