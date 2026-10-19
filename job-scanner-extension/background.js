// Service worker: schedules scans and reads LinkedIn results.
//
// ROBUST design (MV3-safe): it reads a tab with chrome.scripting.executeScript,
// which returns the parsed jobs DIRECTLY. No content-script handshake, no
// in-memory tab map (that gets wiped when Chrome suspends the worker — the bug
// that made scans silently report nothing).
//
// Safety ("wise & safe"): READ-ONLY (no clicks/apply/login automation), gentle
// human-like scroll, first results page only, jitter + pauses, and it BACKS OFF
// (pauses auto-scan) when LinkedIn shows an auth wall or returns nothing.

const ALARM_NAME = "job-scanner-scan";
const DEFAULTS = {
  searchUrls: [],
  apiUrl: "http://localhost:8000",
  pagesPerSearch: 10,        // 25 jobs/page → up to ~250 per search, paced
};

const JITTER_MAX_MS = 90 * 1000;
const BETWEEN_URLS_MIN_MS = 20 * 1000;
const BETWEEN_URLS_MAX_MS = 45 * 1000;
const LOAD_TIMEOUT_MS = 25 * 1000;
const RENDER_WAIT_MS = 2500;              // let results paint after load
const RUN_STALE_MS = 4 * 60 * 1000;
const MAX_BAD_RUNS_BEFORE_PAUSE = 2;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rand = (min, max) => min + Math.random() * (max - min);

// A run spans minutes (multiple links, pauses between them). MV3 suspends an
// idle service worker after ~30s, which would kill the run after the first link.
// Ping a chrome API every 20s while a run is active to keep the worker alive.
let scanStop = false;
let keepAliveTimer = null;
function startKeepAlive() {
  if (keepAliveTimer) return;
  keepAliveTimer = setInterval(() => chrome.runtime.getPlatformInfo(() => {}), 20000);
}
function stopKeepAlive() {
  if (keepAliveTimer) { clearInterval(keepAliveTimer); keepAliveTimer = null; }
}

async function getSettings() {
  return { ...DEFAULTS, ...(await chrome.storage.local.get(DEFAULTS)) };
}
async function getStatus() {
  return (await chrome.storage.local.get("status")).status || {};
}
async function setStatus(patch) {
  const cur = await getStatus();
  await chrome.storage.local.set({ status: { ...cur, ...patch } });
}

// The alarm is only a heartbeat now. It used to BE the schedule — its own
// interval, its own random jitter, invisible to the app — so scans fired at
// times the user could neither see in Settings nor turn off. There is one
// schedule now, the app's, and this just checks whether a slot has come up.
const TICK_MINUTES = 5;

async function ensureAlarm() {
  chrome.alarms.create(ALARM_NAME, { periodInMinutes: TICK_MINUTES });
}

// How long after a missed slot it is still worth running. A laptop that was
// shut at 10:00 and opened at 12:30 should still get its morning scan; one
// opened at midnight should not suddenly scan for the morning it slept through.
const CATCHUP_MINUTES = 180;

// The scheduled slot that is currently owed, or null. Returns a stable key like
// "2026-07-31T10:00" so a slot runs once, whether it fires on time or late.
function slotDue(schedule, now = new Date()) {
  if (!schedule || !Array.isArray(schedule.times) || !schedule.times.length) return null;
  const dayNames = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
  if (schedule.days && schedule.days.length && !schedule.days.includes(dayNames[now.getDay()])) {
    return null;
  }
  const minutesNow = now.getHours() * 60 + now.getMinutes();
  // Latest slot that has already come round today. Only the most recent one is
  // owed: waking at 18:05 should not replay 10:00 and 14:00 as well.
  let best = null;
  for (const [h, m] of schedule.times) {
    const slot = h * 60 + m;
    if (slot <= minutesNow && (best === null || slot > best[0] * 60 + best[1])) {
      best = [h, m];
    }
  }
  if (!best) return null;
  if (minutesNow - (best[0] * 60 + best[1]) > CATCHUP_MINUTES) return null;
  const [h, m] = best;
  // Local date, not toISOString(): that converts to UTC and would hand back
  // yesterday's date for any slot before the timezone offset.
  const day = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-`
            + `${String(now.getDate()).padStart(2, "0")}`;
  return `${day}T${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

// Report our own state on the way past. The app cannot see inside Chrome, so
// an extension that pauses itself after a run of empty scans simply goes quiet:
// the Jobs page keeps looking normal while nothing arrives for days. This is
// the only request the extension makes on its own, so it is the only place the
// app can learn why.
async function fetchSchedule(apiUrl, status) {
  const base = await resolveApi(apiUrl);
  if (!base) return null;
  const st = status || (await getStatus());
  const q = new URLSearchParams({
    v: chrome.runtime.getManifest().version,
    paused: st.paused ? "1" : "0",
    stopped: st.stopped ? "1" : "0",
  });
  if (st.lastError) q.set("error", String(st.lastError).slice(0, 200));
  if (st.lastOutcome) q.set("outcome", st.lastOutcome);
  if (st.lastRunAt) q.set("last_run", st.lastRunAt);
  try {
    const r = await fetch(base + "/api/scan-schedule?" + q.toString(),
                          { cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch (e) {
    return null;
  }
}
chrome.runtime.onInstalled.addListener(ensureAlarm);
chrome.runtime.onStartup.addListener(ensureAlarm);
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.apiUrl) ensureAlarm();
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== ALARM_NAME) return;
  const status = await getStatus();
  const { apiUrl } = await getSettings();
  // Poll first, even when paused: the request carries our state to the app.
  const schedule = await fetchSchedule(apiUrl, status);
  if (status.paused || status.stopped) {
    console.log("[job-finder] paused — skipping scheduled run.");
    return;
  }
  if (!schedule) return;          // app not running: nowhere to send jobs anyway
  const slot = slotDue(schedule);
  if (!slot) return;
  if (status.lastSlot === slot) return;   // this slot already ran
  await setStatus({ lastSlot: slot });
  await sleep(rand(0, JITTER_MAX_MS));    // stay inside the slot, arrive human
  runScan("scheduled");
});

// --- Injected page collector (runs IN the LinkedIn tab; self-contained) ---- //
async function collectJobsInPage() {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const text = (el) => (el ? el.textContent.trim().replace(/\s+/g, " ") : null);

  // LinkedIn renders the title twice: a visible span plus a screen-reader copy
  // ("Project Manager" + "Project Manager with verification"). A comma-separated
  // querySelector returns the first match in DOCUMENT order, not the first
  // selector listed — so the wrapping link won, and its textContent glued both
  // copies together. Try the selectors strictly in priority order instead.
  const firstMatch = (card, selectors) => {
    for (const sel of selectors) {
      const hit = text(card.querySelector(sel));
      if (hit) return hit;
    }
    return null;
  };

  // Belt and braces: strip an exact self-repetition if a future layout glues
  // the two copies together again.
  const undouble = (s) => {
    if (!s) return s;
    const m = s.match(/^(.{6,}?)\s*\1(?:\s+with verification)?$/i);
    return m ? m[1].trim() : s;
  };

  const byId = new Map();

  // Find the actual scrollable list container (robust to class renames): the
  // nearest scrollable ancestor of a job card. LinkedIn virtualizes the list, so
  // we must scroll THIS element to render more cards.
  function findScroller() {
    let el = document.querySelector("[data-occludable-job-id], [data-job-id]");
    while (el && el !== document.body) {
      const s = getComputedStyle(el);
      if ((s.overflowY === "auto" || s.overflowY === "scroll") &&
          el.scrollHeight > el.clientHeight + 50) return el;
      el = el.parentElement;
    }
    return null;
  }

  // Read whatever cards are rendered RIGHT NOW and merge (keep the version that
  // actually has a title — virtualized placeholders have the id but no content).
  function harvestVisible() {
    document.querySelectorAll('script[type="application/ld+json"]').forEach((s) => {
      let data; try { data = JSON.parse(s.textContent); } catch { return; }
      (Array.isArray(data) ? data : [data]).forEach((item) => {
        if (!item || item["@type"] !== "JobPosting") return;
        const url = item.url || "";
        const m = url.match(/(\d{6,})/);
        const jobId = m ? m[1] : url;
        if (!jobId) return;
        const org = item.hiringOrganization || {};
        const addr = (item.jobLocation && item.jobLocation.address) || {};
        byId.set(String(jobId), { job_id: String(jobId), title: item.title || "",
          company: org.name || null,
          location: addr.addressLocality || addr.addressRegion || null,
          url: url || null, posted_at: item.datePosted || null,
          description: item.description || null, source: "linkedin",
          workplace: item.jobLocationType === "TELECOMMUTE" ? "Remote" : null });
      });
    });
    document.querySelectorAll("[data-job-id], [data-occludable-job-id]").forEach((card) => {
      const jobId = card.getAttribute("data-job-id") || card.getAttribute("data-occludable-job-id");
      if (!jobId || jobId === "search") return;
      const title = undouble(firstMatch(card, [
        "a[href*='/jobs/view/'] span[aria-hidden='true']",
        "[class*='job-card-list__title'] span[aria-hidden='true']",
        "[class*='job-card-job-posting-card-wrapper__title'] span[aria-hidden='true']",
        "[class*='job-card-list__entity-lockup'] a strong",
        ".job-card-list__title",
        "[class*='job-card-list__title']",
        "[class*='job-card-job-posting-card-wrapper__title']",
        "a.job-card-container__link",
        "[class*='job-card-container__link']",
      ]));
      const existing = byId.get(String(jobId));
      if (!title && existing) return;               // keep an earlier good read
      const link = card.querySelector("a[href*='/jobs/view/']");
      const company = text(card.querySelector(
        "[class*='job-card-container__primary-description'], [class*='company-name'], " +
        "[class*='artdeco-entity-lockup__subtitle']"));
      const location = text(card.querySelector(
        "[class*='job-card-container__metadata'], [class*='artdeco-entity-lockup__caption'], " +
        "li[class*='metadata']"));
      const time = card.querySelector("time");
      // Work arrangement is a chip, not part of the description, so the app
      // never saw it and rated on-site jobs as good matches. Scan the whole
      // card text: robust to LinkedIn renaming its classes. Hybrid is checked
      // first because hybrid ads usually mention "remote" as well.
      const cardText = (card.innerText || "").toLowerCase();
      const workplace = /\bhybrid\b/.test(cardText) ? "Hybrid"
        : /\bon[\s-]?site\b/.test(cardText) ? "On-site"
        : /\bremote\b/.test(cardText) ? "Remote" : null;
      byId.set(String(jobId), { job_id: String(jobId), title: title || "",
        company: company || null, location: location || null, workplace,
        url: link ? link.href.split("?")[0] : `https://www.linkedin.com/jobs/view/${jobId}/`,
        posted_at: time ? (time.getAttribute("datetime") || text(time)) : null,
        description: null, source: "linkedin" });
    });
  }

  // Incremental scroll: step down and harvest at each step so every virtualized
  // card gets rendered (and captured) as it passes through the viewport.
  const scroller = findScroller();
  const scrollTop = () => (scroller ? scroller.scrollTop : window.scrollY);
  const scrollMax = () => (scroller
    ? scroller.scrollHeight - scroller.clientHeight
    : document.body.scrollHeight - window.innerHeight);
  const step = (scroller ? scroller.clientHeight : window.innerHeight) * 0.6 || 400;
  harvestVisible();
  let prev = -1;
  for (let i = 0; i < 30; i++) {
    const cur = scrollTop();
    if (cur >= scrollMax() - 5 && cur === prev) break;   // reached the bottom
    prev = cur;
    const next = Math.min(cur + step, scrollMax());
    if (scroller) scroller.scrollTop = next; else window.scrollTo(0, next);
    await sleep(450 + Math.random() * 350);
    harvestVisible();
  }
  harvestVisible();

  const jobs = [...byId.values()].filter((j) => j.job_id && j.title);
  return {
    jobs,
    debug: {
      dataJobId: document.querySelectorAll("[data-job-id]").length,
      occludable: document.querySelectorAll("[data-occludable-job-id]").length,
      jobViewLinks: document.querySelectorAll('a[href*="/jobs/view/"]').length,
      jsonld: document.querySelectorAll('script[type="application/ld+json"]').length,
      collected: jobs.length,
      scroller: !!scroller,
      loggedIn: !!document.querySelector(
        ".global-nav__me, img.global-nav__me-photo, .global-nav__primary-items, " +
        '[data-control-name="nav.settings"], a[href*="/in/"]'),
      hidden: document.visibilityState !== "visible",
    },
  };
}

// Run the collector in a tab and POST results to the backend (from here, so no
// page-origin CORS). Returns { outcome, count, debug }.
// The desktop app wants port 8000 but silently falls back to another one when
// it is taken (a second instance, a dev server). The extension then posted into
// the void and scans looked like they simply did nothing. So: find the app.
let RESOLVED_API = null;

async function resolveApi(preferred) {
  const candidates = [];
  if (preferred) candidates.push(preferred.replace(/\/$/, ""));
  if (RESOLVED_API) candidates.push(RESOLVED_API);
  for (let port = 8000; port <= 8010; port++) candidates.push(`http://localhost:${port}`);
  for (const base of candidates) {
    try {
      const res = await fetch(base + "/api/health", { method: "GET" });
      if (res.ok) { RESOLVED_API = base; return base; }
    } catch (e) { /* not this one */ }
  }
  return null;
}

async function harvestTab(tabId, apiUrl) {
  let injection;
  try {
    injection = await chrome.scripting.executeScript({ target: { tabId }, func: collectJobsInPage });
  } catch (e) {
    return { outcome: "error", count: 0, debug: null, error: String(e) };
  }
  const result = injection && injection[0] && injection[0].result;
  const jobs = (result && result.jobs) || [];
  const debug = (result && result.debug) || null;
  if (jobs.length) {
    const base = await resolveApi(apiUrl);
    if (!base) {
      return { outcome: "error", count: jobs.length, debug,
               error: "Job Finder is not running (checked ports 8000-8010)" };
    }
    try {
      const res = await fetch(base + "/api/ingest", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jobs }),
      });
      if (!res.ok) return { outcome: "error", count: jobs.length, debug,
                            error: "ingest HTTP " + res.status };
    } catch (e) {
      return { outcome: "error", count: jobs.length, debug, error: "backend unreachable" };
    }
  }
  const outcome = jobs.length > 0 ? "ok" : (debug && !debug.loggedIn ? "auth" : "empty");
  return { outcome, count: jobs.length, debug, ids: jobs.map((j) => j.job_id) };
}

// Set the LinkedIn ?start= pagination offset on a search URL.
function withStart(url, start) {
  try { const u = new URL(url); u.searchParams.set("start", String(start)); return u.toString(); }
  catch { return url; }
}

// Read a search across MANY pages: harvest page 1, then navigate the same tab to
// start=25, 50, 75… harvesting each, until a page adds no new jobs (results
// exhausted) or maxPages is hit. Sequential + paced (human-like) — never parallel.
async function harvestPaginated(tabId, apiUrl, maxPages) {
  const seen = new Set();
  let lastDebug = null, pages = 0, sawAuth = false, err = null;
  for (let p = 0; p < maxPages; p++) {
    if (p > 0) {
      let curUrl;
      try { curUrl = (await chrome.tabs.get(tabId)).url; } catch { break; }
      await chrome.tabs.update(tabId, { url: withStart(curUrl, p * 25) });
      await waitForComplete(tabId, LOAD_TIMEOUT_MS);
      await sleep(RENDER_WAIT_MS + rand(700, 1800));  // human-ish gap between pages
    }
    if (scanStop) break;
    const r = await harvestTab(tabId, apiUrl);
    pages++;
    if (r.debug) lastDebug = r.debug;
    if (r.error) err = r.error;
    if (r.outcome === "auth") { sawAuth = true; break; }
    const before = seen.size;
    (r.ids || []).forEach((id) => seen.add(id));
    // Live progress so the popup shows movement mid-run instead of "no data".
    await setStatus({ running: true, lastCount: seen.size, lastPages: pages, lastDebug });
    if (p > 0 && seen.size === before) break;   // page repeated → exhausted
  }
  const outcome = seen.size > 0 ? (err ? "error" : "ok")
    : sawAuth ? "auth" : (lastDebug && !lastDebug.loggedIn ? "auth" : "empty");
  return { outcome, count: seen.size, debug: lastDebug, pages, error: err };
}

function waitForComplete(tabId, timeoutMs) {
  return new Promise((resolve) => {
    let done = false;
    const finish = () => { if (!done) { done = true; chrome.tabs.onUpdated.removeListener(listener); resolve(); } };
    const listener = (id, info) => { if (id === tabId && info.status === "complete") finish(); };
    chrome.tabs.onUpdated.addListener(listener);
    chrome.tabs.get(tabId, (t) => { if (t && t.status === "complete") finish(); });
    setTimeout(finish, timeoutMs);
  });
}

// Open one search URL in a tab, harvest it across pages, close it. `active`
// (visible) makes LinkedIn render the virtualized list reliably — used for a
// manual "Scan now"; scheduled runs use a background tab to stay unobtrusive.
async function scanOneUrl(url, apiUrl, active) {
  const tab = await chrome.tabs.create({ url, active: !!active });
  try {
    await waitForComplete(tab.id, LOAD_TIMEOUT_MS);
    await sleep(RENDER_WAIT_MS);
    const { pagesPerSearch } = await getSettings();
    return await harvestPaginated(tab.id, apiUrl, Math.max(1, Number(pagesPerSearch) || 1));
  } catch (e) {
    return { outcome: "error", count: 0, debug: null, error: String(e) };
  } finally {
    chrome.tabs.remove(tab.id).catch(() => {});
  }
}

async function runScan(trigger) {
  const { searchUrls, apiUrl } = await getSettings();
  if (!searchUrls.length) { console.log("[job-scanner] no search URLs"); return; }

  const status = await getStatus();
  if (status.running && status.runStartedAt && Date.now() - status.runStartedAt < RUN_STALE_MS) {
    console.log("[job-scanner] already running — ignoring", trigger); return;
  }
  scanStop = false;
  startKeepAlive();
  await setStatus({ lastRun: new Date().toISOString(), running: true,
                    runStartedAt: Date.now(), lastError: null });

  // Manual "Scan now" → visible tabs (reliable rendering); scheduled → background.
  const active = trigger === "manual";
  const results = [];
  try {
    for (let i = 0; i < searchUrls.length; i++) {
      if (scanStop) break;
      results.push(await scanOneUrl(searchUrls[i], apiUrl, active));
      if (scanStop || i >= searchUrls.length - 1) continue;
      // Stop-aware pause between links (re-checks the flag each second).
      const gap = rand(BETWEEN_URLS_MIN_MS, BETWEEN_URLS_MAX_MS);
      for (let t = 0; t < gap && !scanStop; t += 1000) await sleep(1000);
    }
  } finally {
    stopKeepAlive();
  }

  const stopped = scanStop;
  const gotJobs = results.some((r) => r.outcome === "ok");
  const authWall = results.some((r) => r.outcome === "auth");
  const totalCount = results.reduce((n, r) => n + (r.count || 0), 0);
  const lastDebug = results.map((r) => r.debug).filter(Boolean).pop() || null;
  const badRuns = (gotJobs || stopped) ? 0 : (status.badRuns || 0) + 1;
  const paused = !stopped && badRuns >= MAX_BAD_RUNS_BEFORE_PAUSE;

  await setStatus({
    running: false, runStartedAt: null, badRuns, paused,
    lastRunAt: new Date().toISOString(),
    lastCount: totalCount, lastDebug,
    lastOutcome: stopped ? "stopped" : gotJobs ? "ok" : authWall ? "auth" : "empty",
    lastError: paused
      ? (authWall ? "Paused: LinkedIn asked to sign in. Sign in, then Scan now."
                  : "Paused: no jobs found. Check your search URLs, then Scan now.")
      : null,
  });
}


// --- Injected people collector (runs IN a LinkedIn people/search tab) ------ //
// Read-only, exactly like the job collector: no clicks, no messages, no invites.
// The degree of connection is the point of this pass — it decides whether the
// app can draft a direct message, an invite note, or nothing at all.
async function collectPeopleInPage() {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const text = (el) => (el ? el.textContent.trim().replace(/\s+/g, " ") : null);

  // LinkedIn writes the degree several ways: a "2nd" badge, "· 3rd+", or the
  // screen-reader phrase "2nd degree connection". Take whichever is present.
  const degreeOf = (card) => {
    const raw = (card.innerText || "").replace(/\s+/g, " ");
    const m = raw.match(/(?:^|[\s·•|])(1st|2nd|3rd\+?)(?:[\s·•|]|$)/i)
           || raw.match(/(1st|2nd|3rd)\s+degree/i);
    if (!m) return null;
    return { "1st": 1, "2nd": 2, "3rd": 3, "3rd+": 3 }[m[1].toLowerCase()] || null;
  };

  // The name sits in a link to /in/<slug>. Same double-render trap as the job
  // cards: a visible span plus a screen-reader copy, glued by textContent.
  const undouble = (s) => {
    if (!s) return s;
    const m = s.match(/^(.{3,}?)\s*\1$/i);
    return m ? m[1].trim() : s;
  };

  const byUrl = new Map();

  function harvest() {
    document.querySelectorAll('a[href*="/in/"]').forEach((link) => {
      const href = (link.href || "").split("?")[0];
      if (!/\/in\/[^/]+\/?$/.test(href)) return;
      // Walk up to the card that carries the headline and the degree badge.
      let card = link;
      for (let i = 0; i < 6 && card.parentElement; i++) {
        card = card.parentElement;
        if (card.innerText && card.innerText.length > 40) break;
      }
      const name = undouble(text(link.querySelector('span[aria-hidden="true"]')) || text(link));
      if (!name || name.length > 80 || /^\d/.test(name)) return;
      const lines = (card.innerText || "").split("\n").map((x) => x.trim()).filter(Boolean);
      // The headline is the first line after the name that is not the degree
      // badge, a connection count, or a button label.
      const headline = lines.find((l) =>
        l !== name && l.length > 3 && l.length < 160 &&
        !/^(1st|2nd|3rd\+?|connect|follow|message|view profile|\d+ (mutual|connections))/i.test(l)
      ) || null;
      const existing = byUrl.get(href);
      if (existing && existing.headline && !headline) return;
      byUrl.set(href, { name, headline, profile_url: href, degree: degreeOf(card) });
    });
  }

  harvest();
  for (let i = 0; i < 8; i++) {
    window.scrollBy(0, window.innerHeight * 0.7);
    await sleep(500 + Math.random() * 300);
    harvest();
  }

  const people = [...byUrl.values()];
  return {
    people,
    debug: {
      profileLinks: document.querySelectorAll('a[href*="/in/"]').length,
      collected: people.length,
      withDegree: people.filter((p) => p.degree).length,
      loggedIn: !/\/authwall|\/login/.test(location.href),
    },
  };
}

// Read the people the user is looking at and send them to the app for one job.
async function harvestPeople(tabId, apiUrl, jobId) {
  let result;
  try {
    const [{ result: r } = {}] = await chrome.scripting.executeScript({
      target: { tabId }, func: collectPeopleInPage, world: "MAIN",
    });
    result = r;
  } catch (e) {
    return { ok: false, count: 0, error: "could not read the tab: " + e.message };
  }
  const people = (result && result.people) || [];
  if (!people.length) {
    return { ok: false, count: 0, debug: result && result.debug,
             error: (result && result.debug && !result.debug.loggedIn)
               ? "LinkedIn asked to sign in." : "No people found on this page." };
  }
  const base = await resolveApi(apiUrl);
  if (!base) return { ok: false, count: 0, error: "Job Finder is not running (ports 8000-8010)" };
  try {
    const res = await fetch(base + "/api/contacts", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId, people }),
    });
    if (!res.ok) return { ok: false, count: 0, error: "contacts HTTP " + res.status };
    const body = await res.json();
    return { ok: true, count: body.stored, received: body.received, debug: result.debug };
  } catch (e) {
    return { ok: false, count: 0, error: "backend unreachable" };
  }
}

// Harvest the tab the USER is looking at (reliable: visible tab always renders).
async function runOnActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/https:\/\/www\.linkedin\.com\/jobs/.test(tab.url || "")) {
    await setStatus({ lastRun: new Date().toISOString(), lastCount: 0, lastOutcome: "empty",
                      lastDebug: null,
                      lastError: "Open a LinkedIn job-search tab (linkedin.com/jobs/search) and try again." });
    return { ok: false };
  }
  const { apiUrl, pagesPerSearch } = await getSettings();
  const r = await harvestPaginated(tab.id, apiUrl, Math.max(1, Number(pagesPerSearch) || 1));
  await setStatus({ lastRun: new Date().toISOString(), lastCount: r.count, lastOutcome: r.outcome,
                    lastDebug: r.debug, paused: false, badRuns: 0, lastPages: r.pages,
                    lastError: r.error || null });
  return { ok: true };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "RUN_NOW") {
    setStatus({ paused: false, badRuns: 0 }).then(() =>
      runScan("manual").then(() => sendResponse({ ok: true })));
    return true;
  }
  if (msg.type === "RUN_ON_ACTIVE_TAB") {
    scanStop = false;
    runOnActiveTab().then((r) => sendResponse(r));
    return true;
  }
  if (msg.type === "FIND_PEOPLE") {
    (async () => {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab || !/linkedin\.com\/(company|search|in)\//.test(tab.url || "")) {
        sendResponse({ ok: false,
          error: "Open the company's People page on LinkedIn, then press this." });
        return;
      }
      const { apiUrl } = await getSettings();
      sendResponse(await harvestPeople(tab.id, apiUrl, msg.jobId));
    })();
    return true;
  }
  if (msg.type === "RUN_STOP") {
    scanStop = true;                       // loops check this and bail out
    setStatus({ running: false, runStartedAt: null, lastOutcome: "stopped" })
      .then(() => sendResponse({ ok: true }));
    return true;
  }
});
