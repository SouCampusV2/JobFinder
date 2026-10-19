## The filter now decides in code, and it looks in more places

Two things changed in this release. The scoring stopped taking the model's word for facts it can check itself, and the app stopped depending on a single job board.

### The model judges, the code decides

Four facts are now read out of a posting and enforced before a score is trusted. Each one is here because prompt wording could not fix it:

- **Language.** A vacancy written in a language you do not speak used to be scored on its merits. Detection covers 18 languages plus Cyrillic. If you never stated a language requirement, nothing is blocked.
- **Seniority.** Titles reading "Senior" scored 65-75 against instructions that reject the level. It is read from the title now, with parentheses ignored — "Project Manager (Senior Stakeholders)" is not a senior role, and "Lead Generation Specialist" is not a lead.
- **Years of experience.** A number counts as a requirement only when it sits next to the word "experience". A founder's biography saying "15 years in the industry" is no longer read as a demand for fifteen years.
- **Residency.** "Remote, but you must live in Switzerland" satisfies a rule that says "remote within Europe" while being unavailable to someone living elsewhere. Country lists are read whole, so a posting open to Germany, Spain or Portugal will not be held against a candidate in Spain. This one lowers the score instead of blocking: a move is expensive, not impossible.

Which levels and countries are unacceptable is read from your own AI Instructions. Nothing is hardcoded, and a rule you never wrote blocks nothing.

**Work arrangement** (remote, hybrid, on-site) is read from the card metadata and from the ATS fields directly, then folded into the location. It is almost never stated in the description text, which is why on-site roles used to read as good remote matches.

### 119 new places to find work

- **117 European company career pages**, read from the systems that host them: Greenhouse, Lever, Ashby, Personio, Teamtailor, Recruitee and SmartRecruiters. These are jobs posted by a company to its own site, many of which never reach LinkedIn. Every entry was verified with a live request before shipping.
- **Two state employment services**: the German Arbeitsagentur and the Swedish Platsbanken. Expect the language filter to reject most German postings and to let most Swedish ones through, since Swedish employers advertise professional roles in English far more often.

Norway's NAV was tested and left out. Its public search returns no posting text, and a job the scorer cannot read is worse than no job at all.

### Duplicate titles are gone

LinkedIn writes each job title twice in the page: once visibly and once for screen readers, suffixed "with verification". The extension was gluing both copies together, so the list was full of entries like "Project Manager (Remote)Project Manager (Remote)". Fixed at the source and repaired in place — 2125 stored titles were corrected on first launch, and 151 rows turned out to be duplicates of jobs already in the list.

### Referral outreach

Jobs above your match threshold now have a **People** section. Open the company's page on LinkedIn, press **Collect people** in the extension, and the app sorts who is worth contacting: hiring managers on the same subject first, then recruiters, then everyone else.

How you can reach someone decides what gets written. A first-degree connection gets a full message. A second-degree connection gets a 200-character invite note, or better, an invite with no note and a full message once they accept — that spends none of the five personalised notes a free LinkedIn account gets each month. A third-degree connection gets nothing, because nothing can be sent.

**The app never sends anything.** It writes the draft, you copy it and send it yourself. Automated sending is the one behaviour that gets accounts permanently banned, and it is deliberately absent.

### Telegram digests that are worth reading

The digest used to fire after every batch the extension posted — five messages in three minutes, one job each — and included everything scored, however weak.

Now it sends jobs at 80 and above, either on your schedule or once five of them have piled up. A scheduled digest is sent even when there is nothing, saying so in one line, because silence is indistinguishable from a scan that never ran. Each entry links back into the app as well as to the original posting.

The bot token and chat id moved from the environment file to the **Settings** page, with a **Send test message** button.

### One schedule instead of two

The browser extension used to run its own timer, on its own interval, with its own random delay, invisible to the app. Scans fired at times you could not see in Settings and could not turn off.

There is one schedule now — the one on the Settings page. The extension reads it and obeys it. If the app is not running, the extension does not scan. A slot missed because the laptop was asleep is picked up within three hours of waking, so a machine that sleeps every night no longer skips most of its scans.

### Also in this release

- A **Statistic** tab: how many jobs were scanned, how many matched, how many you applied to, where they came from, and how the scores are distributed.
- **To review** is the first tab and the default view.
- CV and cover letter editing as a conversation, written out as it is generated.
- Cover letters are barred from em dashes, semicolons and a list of machine-sounding vocabulary.
- The extension popup is in English, matches the app's design, and shows a connection indicator naming the port the app is on — the failure that used to look like a broken extension.

### Under the hood

283 automated tests, up from none. Every filter added here was checked by breaking it on purpose and confirming a test fails.

> **Set Fast model to `gpt-4.1-mini`** in Settings if you have not already. On `gpt-4o-mini` scoring collapses to all-or-nothing and the graded rules cannot work.

## Windows will warn you before installing

The installer is not code-signed. SmartScreen will say "Windows protected your PC" — click **More info**, then **Run anyway**.

On macOS, an unsigned app is reported as "damaged". Drag Job Finder into Applications, then run once in Terminal:

```
xattr -cr "/Applications/Job Finder.app"
```
