## Windows launch fix, part two

1.0.4 got past the first crash and straight into a second one. Both are fixed here, and Job Finder now starts on Windows.

**What was wrong:** Windows, unlike macOS and Linux, ships no time zone database at all — Python gets one from a separate `tzdata` package that was missing from the installer. The scheduler asked the system for the local zone, got `No time zone found with key Europe/Kiev`, and the whole app aborted during startup before serving a single page.

**Two fixes, so this cannot happen again:**

- `tzdata` is now bundled with the Windows build.
- The scheduler no longer takes the app down when a time zone can't be resolved. It falls back to UTC and says so in the log — a schedule in the wrong zone is an annoyance, an app that won't open is a brick.

**Better diagnostics.** When startup failed, the error dialog could only say "the local server did not start within 20 seconds", because the real traceback went to the log and the process exited cleanly. The dialog now names the actual error.

Everything from 1.0.3 and 1.0.4 is included — duplicate removal, working non-LinkedIn sources, the language filter, softer scoring rules, per-job cover-letter notes, inline CV editing, and the `pythonw.exe` stdout fix.

> **After updating, set Fast model to `gpt-4.1-mini`** in Settings. On `gpt-4o-mini` scoring collapses to all-or-nothing and the graded rules cannot work.

## Windows will warn you before installing

The installer is not code-signed, so Microsoft Defender SmartScreen shows **"Windows protected your PC"**. That is a warning about an unknown publisher, not a detection of anything harmful.

1. Click **More info**, then **Run anyway**.
2. If Windows blocks the file before it even runs: right-click `JobFinder-Setup.exe` → **Properties** → tick **Unblock** at the bottom → **OK**, then run it again.

## Downloads

- Windows: **JobFinder-Setup.exe** · macOS: **JobFinder.dmg** (drag to Applications)
- macOS is unsigned: right-click the app → **Open** the first time.
