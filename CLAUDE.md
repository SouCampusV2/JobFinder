# Job Finder

[`job-scanner/PROJECT_NOTEBOOK.md`](job-scanner/PROJECT_NOTEBOOK.md) is the architecture reference — read it
before scanning the tree. **Read only the section you need**: it opens with an index saying which section
covers what, so `grep -n "^## "` and a ranged Read beat loading all of it. Keep it updated when architecture
or behaviour changes, and date the entries.

## Where things are

- `job-scanner/` — the app (FastAPI + Jinja2 + aiosqlite + APScheduler). `main.py` is the entry point.
- `job-scanner-extension/` — Chrome MV3 extension that scrapes LinkedIn in the user's own session.
- `job-scanner/desktop/` — pywebview + PyInstaller packaging for macOS and Windows.
- `job-scanner/CHANGES-since-1.1.0.md` — user-facing changelog since 1.1.0.
- `job-scanner/RELEASE.md` — how a release is built and published. A release always carries three assets,
  `JobFinder-macOS.zip`, `JobFinder.dmg` and `JobFinder-Setup.exe`; run `./desktop/preflight.sh` first.

## Commands

Run from `job-scanner/`:

```
.venv/bin/python -m pytest tests -q     # tests: no network, no API calls
./run-dev.sh                            # dev server
```

## Standing rules

- **Nothing is copied from the FindsYouJobs repo.** It was read for ideas only, and the clone is deleted.
  Ideas may be reused; not a line of their code. It is GPL/AGPL and this project is not.
- **Settings must say plainly that data leaves the EU** when a non-OpenAI provider is chosen — job
  descriptions, the CV and the user's instructions.
- **API keys live on this machine only.** Key fields render blank and a blank submission keeps the stored
  key rather than wiping it.
- **Two AI roles, not one.** Scanning (`ai_provider`) judges at volume and returns numbers; writing
  (`writer_provider`) produces the few texts a person reads and sends to an employer. They are chosen
  independently. A structural test in `tests/test_providers.py` parses `main.py` and fails if a new
  writing call site takes the scanning model.
- **The model judges, the code decides.** Deterministic gates in Python beat rules stated in a prompt.
- Tests are **verified by mutation**: reintroduce the bug once and check the test actually fails.
  Their scope is code that destroys or hides data, not coverage for its own sake.
