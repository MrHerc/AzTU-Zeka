// The exam page (Task 27): no navigation, only this exam's routes (the session is scoped to it). States: checking,
// ready, running, submitted. Every answer is saved when it changes and every 20 seconds; while offline the answers wait
// in localStorage and go out when the connection is back; after a reload the attempt goes on. The timer counts the
// seconds the server gave, on the browser's monotonic clock, so a wrong system clock does not move the deadline.
// Task 29: a proctor may pause the attempt (the clock stands still, answers wait in the queue); the page tells the board
// when it loses focus, leaves full screen or comes back online.
import { t, LANG } from "./i18n.js";

const id = Number(new URLSearchParams(location.search).get("exam")) || 0;
const nonce = new URLSearchParams(location.search).get("n");      // Task 28: the session's one-time value for SEB
const pageUrl = location.href;                                     // taken at load: the URL SEB's JS API hashes
const KEY = `zeka-exam-${id}`;
const root = document.getElementById("exam");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

let view = null;          // GET /api/exams/{id}
let deadline = 0;         // performance.now() at which the attempt ends
let online = true;
let saving = false;
let submitting = false;
let lastBlur = 0;
let wasFull = false;
let sebTried = false;
let memQueue = null;      // the queue lives in memory; localStorage keeps a copy for a reload (Checkpoint D, SF-2)
let storageOk = true;
let flushing = null;      // the save that is running: a submit waits for it (SF-3)
let lateDropped = 0;      // answers that reached the server after the deadline, said on the final card (SF-9)
let loadTimer = 0;        // one retry timer for load() (SF-17)
let loadBusy = false;

// Task 28: Safe Exam Browser. On Windows SEB adds the hash header to this request itself; on macOS and iOS the JS API
// gives the hash of this page's URL. The server checks either against the exam's Config Key.
async function sebVerify() {
  if (!nonce) return false;
  const sec = window.SafeExamBrowser && window.SafeExamBrowser.security;
  let body = {};
  if (sec) {
    await new Promise((done) => { try { sec.updateKeys(() => done()); } catch { done(); } setTimeout(done, 3000); });
    body = { url: pageUrl, config_key_hash: sec.configKey };
  }
  const r = await api("POST", `/api/exams/${id}/seb-verify?n=${encodeURIComponent(nonce)}`, body);
  return r.status === 200;
}

function queue() {
  if (memQueue === null) { try { memQueue = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch { storageOk = false; memQueue = {}; } }
  return { ...memQueue };
}
function keep(q) {
  memQueue = { ...q };
  try { localStorage.setItem(KEY, JSON.stringify(q)); storageOk = true; } catch { storageOk = false; }   // memory still holds it
}

async function api(method, path, body) {
  try {
    const r = await fetch(path, { method, credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-Lang": LANG }, body: body === undefined ? undefined : JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    online = true;
    return { status: r.status, data };
  } catch {
    online = false;                       // the network: the answer stays in the queue
    return { status: 0, data: {} };
  }
}

function syncClock(seconds) { if (typeof seconds === "number") deadline = performance.now() + seconds * 1000; }
const left = () => Math.max(0, Math.round((deadline - performance.now()) / 1000));
const clock = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

function status() {
  const waiting = Object.keys(queue()).length;
  const warn = storageOk ? "" : `<span class="exam-badge warn">${esc(t("Brauzer cavabları yadda saxlaya bilmir: səhifəni bağlamayın"))}</span> `;
  return warn + badge(waiting);
}

function badge(waiting) {
  if (!online) return `<span class="exam-badge warn">${esc(t("Bağlantı yoxdur: {n} cavab növbədədir", { n: waiting }))}</span>`;
  if (saving || waiting) return `<span class="exam-badge">${esc(t("Saxlanılır…"))}</span>`;
  return `<span class="exam-badge ok">${esc(t("Hamısı saxlanılıb"))}</span>`;
}

function field(q, value) {
  if (q.qtype === "mcq" || q.qtype === "tf") {
    return `<div class="exam-options">${q.options.map((o, i) => {
      const v = q.qtype === "mcq" ? i : o;
      const on = value !== undefined && value !== null && String(value) === String(v);
      return `<label class="exam-option"><input type="radio" name="q${q.id}" data-q="${q.id}" data-v="${esc(JSON.stringify(v))}" ${on ? "checked" : ""}> <span>${esc(o)}</span></label>`;
    }).join("")}</div>`;
  }
  return `<input class="input exam-input" data-q="${q.id}" data-text value="${esc(value ?? "")}" aria-label="${esc(t("Cavab"))}"${q.unit ? ` placeholder="${esc(q.unit)}"` : ""}>`;
}

function draw() {
  if (!view) return;
  const e = view.exam, a = view.attempt;
  const head = `<header class="exam-head"><div><div class="exam-muted">${esc(t("İmtahan"))}</div><h1>${esc(e.title)}</h1></div>
    ${a && a.status === "in_progress" ? `<div class="exam-right"><div class="exam-timer" id="timer" role="timer">${clock(left())}</div><div id="status">${status()}</div>
      ${document.fullscreenEnabled ? `<button class="btn btn-sm" id="fs"${document.fullscreenElement ? " hidden" : ""}>${esc(t("Tam ekran"))}</button>` : ""}</div>` : ""}
    ${a && a.status === "paused" ? `<div class="exam-right"><div class="exam-timer paused" role="timer">${clock(a.remaining_s)}</div></div>` : ""}</header>`;
  if (!a) {
    root.innerHTML = `${head}<section class="exam-card"><p>${esc(t("Müddət: {n} dəqiqə. Vaxt server saatı ilə ölçülür; cavablar dəyişən kimi saxlanılır.", { n: e.duration_min }))}</p>
      <p class="exam-muted">${esc(t("Bağlantı kəsilsə cavablar bu brauzerdə saxlanılır və bağlantı qayıdanda göndərilir."))}</p>
      <button class="btn btn-primary" id="start">${esc(t("Başla"))}</button></section>`;
    return;
  }
  if (a.status === "paused") {
    root.innerHTML = `${head}<section class="exam-card"><h2>${esc(t("İmtahan dayandırılıb"))}</h2>
      <p>${esc(t("Nəzarətçi imtahanı müvəqqəti dayandırıb. Vaxt dayanıb; davam edəndə cavablarınız göndəriləcək."))}</p></section>`;
    return;
  }
  if (a.status !== "in_progress") {
    root.innerHTML = `${head}<section class="exam-card"><h2>${esc(t("Cavablarınız qəbul olundu"))}</h2>
      ${lateDropped ? `<p class="exam-badge warn">${esc(t("{n} cavab vaxt bitəndən sonra çatdı və qəbul olunmadı", { n: lateDropped }))}</p>` : ""}
      <p class="exam-muted">${esc(t("Nəticəni müəllim açıqlayandan sonra portalda görəcəksiniz."))}</p>
      <button class="btn" id="leave">${esc(t("Çıxış"))}</button></section>`;
    return;
  }
  const local = queue(), saved = a.answers || {};
  root.innerHTML = `${head}<ol class="exam-list">${view.questions.map((q, i) => {
      const v = q.id in local ? local[q.id] : saved[q.id] !== undefined ? JSON.parse(saved[q.id]) : undefined;
      return `<li class="exam-card"><div class="exam-muted">${esc(t("Sual {n}", { n: i + 1 }))}</div><p class="exam-q">${esc(q.text)}</p>${field(q, v)}</li>`;
    }).join("")}</ol>
    <footer class="exam-foot"><button class="btn btn-primary" id="submit">${esc(t("Təslim et"))}</button></footer>`;
}

function tick() {
  const el = document.getElementById("timer");
  if (el) el.textContent = clock(left());
  const st = document.getElementById("status");
  if (st) st.innerHTML = status();
  if (view && view.attempt && view.attempt.status === "in_progress" && left() === 0 && !submitting) submit(true);
}

async function load() {
  if (loadBusy) return false;
  loadBusy = true;
  try { return await loadOnce(); } finally { loadBusy = false; }
}

async function loadOnce() {
  clearTimeout(loadTimer);
  const r = await api("GET", `/api/exams/${id}`);
  if (r.status === 403 && nonce && !sebTried) {
    sebTried = true;
    if (await sebVerify()) return load();
  }
  if (r.status === 401 || r.status === 403 || r.status === 404) {
    root.innerHTML = `<section class="exam-card"><h1>${esc(t("İmtahan səhifəsi"))}</h1><p>${esc(r.data.error || t("İmtahana portaldan daxil olun."))}</p>
      <a class="btn" href="/">${esc(t("Portala qayıt"))}</a></section>`;
    return false;
  }
  if (r.status !== 200) {                                           // the server is busy or away: one retry timer, said on the page
    loadTimer = setTimeout(load, 3000);
    if (!view) root.innerHTML = `<section class="exam-card"><p>${esc(t("Server cavab vermir: yenidən cəhd edilir…"))}</p></section>`;
    return false;
  }
  view = r.data;
  if (view.attempt) syncClock(view.attempt.remaining_s);
  draw();
  return true;
}

function flush() {
  if (flushing) return flushing;
  if (!view || !view.attempt || view.attempt.status !== "in_progress") return Promise.resolve();
  const run = (async () => {
    saving = true;
    try {
      for (const [qid, value] of Object.entries(queue())) {
        const r = await api("PUT", `/api/exams/${id}/answers/${qid}`, { value });
        if (r.status === 0) break;                                 // offline: keep the rest for later
        const q = queue();
        if (r.status === 200) { if (JSON.stringify(q[qid]) === JSON.stringify(value)) delete q[qid]; keep(q); syncClock(r.data.remaining_s); }
        else if (r.status === 409) {                                 // paused, or over: the server's state wins
          await load();
          if (!view || !view.attempt || !["in_progress", "paused"].includes(view.attempt.status)) {
            lateDropped += Object.keys(queue()).length;                // said on the final card, never silently (SF-9)
            keep({});
            draw();
          }
          return;
        } else if (r.status === 400 || r.status === 404) { delete q[qid]; keep(q); }   // refused for good: not on the form
        else if (r.status === 401 || r.status === 403) { await load(); return; }       // the session or the network list: the page says why
        else { online = false; break; }                              // a 5xx, the gate's 503: the answer waits (Checkpoint D, SF-1)
      }
    } finally { saving = false; tick(); }
  })();
  // cleared after it settles: with an empty queue the body ends before `run` is assigned (security review, BUG-flush)
  flushing = run.finally(() => { flushing = null; });
  return flushing;
}

async function submit(auto = false) {
  if (submitting) return;
  if (!auto && !confirm(t("Təslim etmək istəyirsiniz? Bundan sonra cavab dəyişmir."))) return;
  submitting = true;
  try {
    await flush();
    await flush();                                    // the save that was running, then what came in meanwhile (SF-3)
    if (!auto && Object.keys(queue()).length) { alert(t("Bəzi cavablar hələ göndərilməyib: bağlantını yoxlayın və yenidən təslim edin")); return; }
    const r = await api("POST", `/api/exams/${id}/submit`, { auto });
    if (r.status === 200) { lateDropped += Object.keys(queue()).length; keep({}); view = r.data; draw(); }
    else if (r.status === 409) await load();          // the server's clock says more time (or a pause): go on (NEW-G1)
    else if (auto && (r.status === 0 || r.status >= 500)) setTimeout(() => submit(true), 3000);   // the server submits it at the deadline anyway
    else alert(r.data.error || t("Bağlantı yoxdur"));    // a manual submit that did not go through is never silent (SF-10)
  } finally { submitting = false; }
}

root.addEventListener("change", (ev) => {
  const el = ev.target;
  if (!el.dataset || !el.dataset.q) return;
  const q = queue();
  q[el.dataset.q] = el.dataset.text !== undefined ? el.value : JSON.parse(el.dataset.v);
  keep(q);
  flush();
});
function signal(kind) {
  if (view && view.attempt && view.attempt.status === "in_progress") api("POST", `/api/exams/${id}/signals`, { kind });
}

function fullScreen() {
  if (document.fullscreenEnabled && !document.fullscreenElement) document.documentElement.requestFullscreen().catch(() => {});
}

root.addEventListener("click", async (ev) => {
  const b = ev.target.closest("button");
  if (!b) return;
  if (b.id === "fs") fullScreen();
  else if (b.id === "start") {
    fullScreen();
    b.disabled = true;
    const r = await api("POST", `/api/exams/${id}/start`);
    if (r.status === 200) { view = r.data; syncClock(view.attempt && view.attempt.remaining_s); draw(); }
    else { b.disabled = false; alert(r.data.error || t("Bağlantı yoxdur")); }
  } else if (b.id === "submit") submit(false);
  else if (b.id === "leave") { await api("POST", `/api/exams/${id}/leave`); location.href = "/"; }
});
window.addEventListener("online", () => { online = true; flush(); signal("reconnect"); });
window.addEventListener("blur", () => { if (Date.now() - lastBlur > 3000) { lastBlur = Date.now(); signal("blur"); } });
document.addEventListener("fullscreenchange", () => {
  if (document.fullscreenElement) wasFull = true;
  else if (wasFull) { wasFull = false; signal("fullscreen_exit"); }
  const fs = document.getElementById("fs");          // not draw(): an answer being typed must not be wiped
  if (fs) fs.hidden = Boolean(document.fullscreenElement);
});
window.addEventListener("offline", () => { online = false; tick(); });
setInterval(tick, 1000);
setInterval(() => {
  if (!view || !view.attempt) return;
  const was = view.attempt.status;
  if (was === "in_progress" && Object.keys(queue()).length) { flush(); return; }
  if (was !== "in_progress" && was !== "submitted") return;      // submitted too: a proctor may reopen it (NEW-G2)
  api("GET", `/api/exams/${id}`).then((r) => {
    if (r.status === 401 || r.status === 403) { load(); return; }   // the session ended: the page says why (SF-17)
    if (r.status !== 200) return;
    if (r.data.attempt && r.data.attempt.status !== was) { view = r.data; syncClock(view.attempt.remaining_s); draw(); }
    else syncClock(r.data.attempt && r.data.attempt.remaining_s);
    tick();
  });
}, 20000);
setInterval(() => { if (view && view.attempt && view.attempt.status === "paused") load().then((ok) => { if (ok) flush(); }); }, 5000);
document.title = `${t("İmtahan")} · Zəka`;
await load();
flush();
