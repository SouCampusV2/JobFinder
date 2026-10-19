// Popup logic. MV3 forbids inline scripts, so this lives in its own file.
// Reads/writes settings in chrome.storage.local and can trigger a manual scan.

const $ = (id) => document.getElementById(id);

const DEFAULTS = {
  searchUrls: [],
  apiUrl: "http://localhost:8000",
  pagesPerSearch: 10,
};

function portFromApiUrl(apiUrl) {
  const m = String(apiUrl).match(/:(\d+)/);
  return m ? m[1] : "8000";
}

async function load() {
  const s = { ...DEFAULTS, ...(await chrome.storage.local.get(DEFAULTS)) };
  $("urls").value = (s.searchUrls || []).join("\n");
  $("api").value = portFromApiUrl(s.apiUrl);
  $("pages").value = s.pagesPerSearch || 10;
  renderStatus();
  checkConnection();
  refreshPeopleTarget();
  showSchedule();
}

// There is one schedule and it lives in the app's Settings. Showing it here
// stops the extension from looking like it has a mind of its own.
async function showSchedule() {
  const el = $("schedule");
  const port = Math.max(1, Number($("api").value) || 8000);
  try {
    const j = await (await fetch(`http://localhost:${port}/api/scan-schedule`)).json();
    if (!j.times || !j.times.length) {
      el.textContent = "Schedule: off. Automatic scans run only when times are set "
        + "in the app's Settings.";
      return;
    }
    const times = j.times.map(([h, m]) =>
      String(h).padStart(2, "0") + ":" + String(m).padStart(2, "0")).join(", ");
    const days = j.days && j.days.length ? j.days.join(", ") : "every day";
    el.textContent = `Schedule: ${times} on ${days} (${j.timezone}). Set in the app's Settings.`;
  } catch (e) {
    el.textContent = "Schedule: unavailable — the app is not running.";
  }
}

async function save() {
  const searchUrls = $("urls")
    .value.split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
  const port = Math.max(1, Number($("api").value) || 8000);
  const apiUrl = `http://localhost:${port}`;
  const pagesPerSearch = Math.min(40, Math.max(1, Number($("pages").value) || 10));

  await chrome.storage.local.set({ searchUrls, apiUrl, pagesPerSearch });
  flash("Saved", "");
  checkConnection();
}

// The single most common failure is the app listening on a different port than
// the one saved here, which used to look like "the extension is broken".
async function checkConnection() {
  const port = Math.max(1, Number($("api").value) || 8000);
  const dot = $("conn-dot");
  const text = $("conn-text");
  dot.className = "dot";
  text.textContent = "checking…";
  try {
    const res = await fetch(`http://localhost:${port}/api/health`, { cache: "no-store" });
    if (res.ok) {
      dot.className = "dot on";
      text.textContent = `connected on ${port}`;
      return;
    }
    throw new Error(String(res.status));
  } catch (e) {
    dot.className = "dot off";
    text.textContent = `no app on ${port}`;
  }
}

function paint(kind, title, body, diag) {
  const box = $("status");
  box.className = "status" + (kind ? " " + kind : "");
  $("status-title").textContent = title;
  $("status-body").textContent = body || "";
  const el = $("status-diag");
  if (diag) {
    el.hidden = false;
    el.textContent = diag;
  } else {
    el.hidden = true;
  }
}

async function renderStatus() {
  const { status } = await chrome.storage.local.get("status");
  if (!status) {
    paint("", "Not run yet", "Save your searches, then press Scan now.");
    return;
  }

  // Always show a diagnostics line so "0 jobs" can be localised without DevTools.
  let diag = "no diagnostics — the scanning tab never reported back "
    + "(timed out, redirected, or the extension was not reloaded after an update)";
  if (status.lastDebug) {
    const d = status.lastDebug;
    diag = `collected:${d.collected ?? "?"} occl:${d.occludable} jobId:${d.dataJobId} `
      + `links:${d.jobViewLinks} scroller:${d.scroller ? "y" : "n"} `
      + `logged-in:${d.loggedIn ? "yes" : "no"} hidden:${d.hidden ? "yes" : "no"}`;
  }

  if (status.paused) {
    const reason = {
      auth: "LinkedIn is asking you to sign in. Log in, then press Scan now.",
      timeout: "The tab never answered (redirect or slow page). Check the URL, then press Scan now.",
    }[status.lastOutcome] || "Nothing was found. Check the URL, then press Scan now.";
    paint("warn", "Paused", reason, diag);
    return;
  }

  const when = status.lastRun ? new Date(status.lastRun).toLocaleString() : "—";
  const bits = [];
  if (status.lastCount != null) bits.push(`${status.lastCount} jobs`);
  if (status.lastPages) bits.push(`${status.lastPages} pages`);
  if (status.lastOutcome) bits.push(status.lastOutcome);
  const kind = status.running ? "" : (status.lastCount ? "ok" : "warn");
  paint(kind,
        status.running ? "Scanning…" : `Last run: ${when}`,
        bits.join(" · "),
        diag);
}

let flashTimer;
function flash(title, body) {
  paint("", title, body);
  clearTimeout(flashTimer);
  flashTimer = setTimeout(renderStatus, 1500);
}

async function runNow() {
  await save();
  flash("Scanning…", "Opening your saved searches.");
  chrome.runtime.sendMessage({ type: "RUN_NOW" }, () => renderStatus());
}

async function runHere() {
  await save();
  flash("Reading the open tab…", "");
  chrome.runtime.sendMessage({ type: "RUN_ON_ACTIVE_TAB" }, () => renderStatus());
}

// The app parks the target job server-side; we ask for it and show which job
// the people on this page will be attached to.
async function refreshPeopleTarget() {
  const hint = $("people-hint");
  const port = Math.max(1, Number($("api").value) || 8000);
  try {
    const j = await (await fetch(`http://localhost:${port}/api/contacts/target`)).json();
    if (j && j.id) {
      hint.textContent = `Will attach to: ${j.title}${j.company ? " at " + j.company : ""}`;
      return j;
    }
  } catch (e) { /* app not running — the generic hint stays */ }
  hint.textContent = 'Press "Find people" on a job in the app first, then open the '
    + 'LinkedIn page it gives you and press this.';
  return null;
}

async function collectPeople() {
  const target = await refreshPeopleTarget();
  if (!target) {
    flash("No job selected", 'Press "Find people" on a job in the app first.');
    return;
  }
  flash("Reading people…", target.title);
  chrome.runtime.sendMessage({ type: "FIND_PEOPLE", jobId: target.id }, (r) => {
    if (!r) { paint("error", "No response", "Reload the extension and try again."); return; }
    if (r.ok) {
      paint("ok", `${r.count} people saved`,
            `Attached to "${target.title}". Reload the job page in the app.`);
    } else {
      paint("warn", "Nothing collected", r.error || "");
    }
  });
}

async function stopScan() {
  flash("Stopping…", "");
  chrome.runtime.sendMessage({ type: "RUN_STOP" }, () => renderStatus());
}

$("save").addEventListener("click", save);
$("run").addEventListener("click", runNow);
$("runhere").addEventListener("click", runHere);
$("stop").addEventListener("click", stopScan);
$("people").addEventListener("click", collectPeople);
$("api").addEventListener("change", function () { checkConnection(); showSchedule(); });
document.addEventListener("DOMContentLoaded", load);
load();
