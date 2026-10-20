# Job Finder

A desktop app that finds job openings worth your time, and helps you apply to them properly.

I built it for my own job search and kept it because it worked.

---

## Who made this

I'm **Andrii Stakhov** — a Product Operations Manager. I'm from Ukraine and I live in Valencia, Spain.

I was applying for roles across Europe and losing entire evenings to the same three chores: scrolling
through listings that were never going to fit, re-reading the same rejections, and rewriting the same
cover letter for the tenth time. So I built something to do the boring parts.

This is a personal project, not a company. There's no team behind it and nothing is being sold.

If something breaks, or you want to ask what it does, [open an issue](https://github.com/andrii424/JobFinder/issues).

---

## What it does

**Finds openings.** It watches job boards across Europe on a schedule you set — the big remote boards,
company career pages, and national employment services — and collects what matches your searches.

**Reads them so you don't have to.** Every posting is compared against your CV and a set of rules you
write yourself, in plain language: the roles you want, the ones you don't, where you can legally work,
what languages you speak. Each one gets a score, a short summary, and the specific reasons it might not
be for you. You see a shortlist instead of a firehose.

**Helps you apply.** For a job you like, it drafts a cover letter grounded in your actual CV, suggests
targeted edits to that CV for the role, answers the screening questions employers ask, and exports both
CV and letter as proper PDFs. You can rewrite anything by just describing the change you want.

**Keeps track.** It remembers where each application stands — applied, test task, interviews, offer or
rejection — so you can see what your effort is actually producing.

**Tells you when something good appears.** Optional Telegram digest for the strong matches only.

It does **not** apply to jobs for you. Everything is drafted for you to read, edit and send yourself.

---

## How it works, briefly

Job Finder runs entirely on your own computer. There's no account to create, no server of mine to sign
into, and no copy of your CV anywhere but your own machine.

The scoring and writing are done by an AI service you choose and pay for directly — OpenAI, DeepSeek or
Google Gemini, and you can use a cheap one for scanning and a better one for writing. You paste your own
API key into the app's settings, and it's stored on your machine only. The app tells you plainly which
of your data goes to that service and where its servers are, so you can decide before you turn it on.

Beyond that, the only things it talks to are the job boards it's reading, Telegram if you switch the
digest on, and GitHub to check whether a newer version exists.

---

## Installing

Download the latest version from the
[releases page](https://github.com/andrii424/JobFinder-releases/releases/latest).

**macOS** — open the `.dmg` and drag Job Finder to Applications. The app isn't signed with a paid Apple
Developer certificate — it's a personal project, not a registered developer account — so macOS may say
it is **"damaged and can't be opened"**. It isn't damaged; macOS has quarantined a download it can't
verify. Don't move it to the Bin — open Terminal and run, once:

```
xattr -dr com.apple.quarantine "/Applications/Job Finder.app"
```

After that it opens normally with a double-click.

**Windows** — run the installer. Windows will show a "unrecognised app" notice for the same reason;
choose **More info → Run anyway**. No administrator rights are needed.

You'll need an API key from the AI service you want to use. The settings page links to where you get one.

---

## What it doesn't do

- It doesn't submit applications on your behalf.
- It doesn't log into any job board for you, and it never asks for your passwords.
- It doesn't collect analytics, usage data, or anything else about you.
- It doesn't send your CV anywhere except the AI service you chose, when you ask it to do something.

---

## Status

Working and in daily use — by me. It's built around how I search for work, so expect opinions baked in.
If you try it and something is confusing or broken, [open an issue](https://github.com/andrii424/JobFinder/issues).

Job Finder is open source under the [Apache License 2.0](../LICENSE). The code, and how to run it from
source, is described in the [repository README](../README.md).

© Andrii Stakhov
