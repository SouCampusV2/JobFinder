## What's new

### Fewer duplicates, more real jobs

- **Duplicates are gone.** The same opening re-posted under a new id — or advertised once per city — is now recognised as one job. On a real database this removed **709 of 2609 stored jobs (27%)**. Existing duplicates are cleaned automatically on first launch; anything you applied to, saved or pinned is never touched.
- **Non-LinkedIn sources actually work now.** They were silently producing nothing: the "past 24 hours" filter dropped **1014 of 1014** cards from Remotive, Jobicy and RemoteOK in a single scan, because those boards publish a handful of matching roles per *week*. They now use a 7-day window; LinkedIn keeps its own filter.
- **Two new sources.** **Workable** pulls jobs straight from companies' own career pages and supports a real location filter (verified: 16 hits for Spain, 3 for Estonia on a single search). **WeWorkRemotely** adds remote roles via its feed.
- **You can see where a job came from** — every non-LinkedIn row now carries a source badge.

### Scoring that matches what you asked for

- **Foreign-language postings are filtered out.** If your instructions say English only, a vacancy written in German or Italian no longer scores 85 — it is detected in the app itself, before any AI call, so it also costs nothing.
- **Only three hard blockers:** location, language and seniority. Role type, industry, tools, salary and work authorisation now lower the score instead of killing the job outright.
- **Your rules stay yours.** No candidate-specific numbers are baked into the app any more — everything comes from your AI Instructions.

> **Recommended:** set **Fast model** to `gpt-4.1-mini` in Settings. On `gpt-4o-mini` the score collapses to all-or-nothing (measured: 2180 jobs at 0–29, six above 60, nothing in between), so graded scoring cannot work.

### Your data is safer

- **"Clear results" no longer wipes your Applied history.** It used to delete every scored job, including the ones you had applied to. Saved and pinned jobs are protected too.
- **No confirmation dialog when deleting a single job** — the row just goes, with an undo-free toast. Bulk clear still asks.
- **Lists are newest-first**, so a fresh scan reads as a feed. The score is shown on each row instead of driving the order.

### Cover letters and CV

- **Tell the app what to mention.** A new field in the Cover letter tab: "mention my Shopify work, I can start in two weeks, keep it under 200 words". It is saved with the job and reused every time you regenerate.
- **Edit the tailored CV in place.** The right-hand column of CV adjustment is now editable — fix the wording and hit Save PDF or Save to my CV. Your original CV stays untouched as the comparison baseline.

### Settings and scheduling

- **Scan interval removed.** Scans now run only at the times you list, so nothing runs on a hidden schedule you can't see. If the field is empty, only "Scan now" scans.
- "Strong matches" is now called **To review**.

### Desktop app

- **Right-click → Copy works again on macOS.** The window was stripping its own context menu.
- **Windows: failures are no longer silent.** If the app can't start you now get an error dialog naming the cause and the log path, and if the native window can't open (missing WebView2 runtime) the app falls back to your browser instead of dying. The installer checks for WebView2 and adds a "Job Finder (show errors)" shortcut for diagnosis.

### Under the hood

First test suite: 69 tests covering everything that deletes or hides data — bulk clear, duplicate purge, database migrations, tab filters and the scoring gates. Each one was verified by reintroducing the bug it guards against.

## Downloads

- macOS: **JobFinder.dmg** (drag to Applications) · Windows: **JobFinder-Setup.exe**
- macOS is unsigned: right-click the app → **Open** the first time.
