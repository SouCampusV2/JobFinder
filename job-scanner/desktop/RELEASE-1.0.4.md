## Windows launch fix

**Job Finder now starts on Windows.** Until this build it died instantly and silently — no window, no message, nothing to report.

The cause, confirmed and reproduced: the Start-menu shortcut runs `pythonw.exe` so no console window appears, and Python then gives the process no `stdout`/`stderr` at all. The web server's logger asked whether the console supported colour, and the app crashed on the spot with `ValueError: Unable to configure formatter 'default'` before it could serve a single page.

The launcher now hands the process real (null) streams before anything else runs, keeps its own logging instead of the server's colour-aware one, and no longer attaches a console log handler when there is no console.

If you hit a different startup problem, the 1.0.3 diagnostics still apply: the error dialog names the cause, the **Job Finder (show errors)** shortcut runs the app with the console visible, and the full log is at `%APPDATA%\Job Finder\jobfinder.log`.

Everything from 1.0.3 is included — duplicate removal, working non-LinkedIn sources, the language filter, the softer scoring rules, per-job cover-letter notes and inline CV editing. See the [1.0.3 notes](https://github.com/andrii424/JobFinder-releases/releases/tag/v1.0.3).

> **After updating, set Fast model to `gpt-4.1-mini`** in Settings. On `gpt-4o-mini` scoring collapses to all-or-nothing and the graded rules cannot work.

## Windows will warn you before installing

The installer is not code-signed, so Microsoft Defender SmartScreen shows **"Windows protected your PC"** for it. That is a warning about an unknown publisher, not a detection of anything harmful.

1. Click **More info**, then **Run anyway**.
2. If Windows blocks the file before it even runs: right-click `JobFinder-Setup.exe` → **Properties** → tick **Unblock** at the bottom → **OK**, then run it again.

## Downloads

- Windows: **JobFinder-Setup.exe** · macOS: **JobFinder.dmg** (drag to Applications)
- macOS is unsigned: right-click the app → **Open** the first time.
