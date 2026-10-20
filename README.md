# Job Finder

A desktop app that reads job boards for you, scores every opening against your CV and your own
written rules, and helps you apply to the ones worth it: a cover letter grounded in your real CV,
targeted CV edits, answers to screening questions, and a tracker for where each application stands.

It runs entirely on your computer. You bring an API key for the AI service you want (OpenAI, DeepSeek
or Google Gemini), and nothing leaves the machine except the requests the app makes to that service and
to the job boards it reads.

**Just want to use it?** Download the macOS or Windows build from the
[releases page](https://github.com/andrii424/JobFinder-releases/releases/latest). What it does, in more
detail, is in [`job-scanner/README.md`](job-scanner/README.md).

## Repository layout

| Path | What it is |
|---|---|
| `job-scanner/` | The app: FastAPI + Jinja2 + SQLite (aiosqlite) + APScheduler. `main.py` is the entry point. |
| `job-scanner-extension/` | Chrome extension (Manifest V3) that reads job listings in your own signed-in browser session and hands them to the app. |
| `job-scanner/desktop/` | Packaging: pywebview window, PyInstaller build for macOS, an NSIS installer for Windows. |
| `job-scanner/PROJECT_NOTEBOOK.md` | Architecture notes. Start here before changing anything. |

## Running from source

You need Python 3.11+. PDF export uses WeasyPrint, which on macOS also needs `brew install pango`.

```sh
cd job-scanner
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env        # optional: the app works with no .env; keys are set in Settings
./run-dev.sh                # http://127.0.0.1:8001, its own database, scheduler off
```

Open **Settings**, choose an AI service and paste its key. Keys are stored in the local database and
never leave the machine except in calls to that service.

To read listings from a site you have to be signed in to, load the extension: `chrome://extensions` →
enable **Developer mode** → **Load unpacked** → pick `job-scanner-extension/`. It talks to the app on
`localhost`.

`./run-prod.sh` runs against `data/jobs.db` on port 8000 with the scheduler on.

## Tests

```sh
cd job-scanner
.venv/bin/python -m pytest tests -q
```

The suite makes no network calls and no API calls. A test earns its place by guarding something that
would otherwise destroy or hide data, and each one is checked by reintroducing the bug it describes and
watching it fail.

## Building the desktop app

See [`job-scanner/desktop/README.md`](job-scanner/desktop/README.md) and the release runbook in
[`job-scanner/RELEASE.md`](job-scanner/RELEASE.md). Both platforms are built on macOS.

## Working on it with Claude Code

[`CLAUDE.md`](CLAUDE.md) holds the project's standing rules and points at the architecture notes, so
an agent starts with the same context a person would.

## License

[Apache License 2.0](LICENSE). Copyright 2026 Andrii Stakhov.
