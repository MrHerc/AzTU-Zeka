// The exam page (Task 27): no navigation, only this exam's routes (the session is scoped to it). States: checking,
// ready, running, submitted. Every answer is saved when it changes and every 20 seconds; while offline the answers wait
// in localStorage and go out when the connection is back; after a reload the attempt goes on. The timer counts the
// seconds the server gave, on the browser's monotonic clock, so a wrong system clock does not move the deadline.
import { t, LANG } from "./i18n.js";

const id = Number(new URLSearchParams(location.search).get("exam")) || 0;
const KEY = `zeka-exam-${id}`;
const root = document.getElementById("exam");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

let view = null;          // GET /api/exams/{id}
let deadline = 0;         // performance.now() at which the attempt ends
let online = true;
let saving = false;
let submitting = false;

function queue() { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch { return {}; } }
function keep(q) { try { localStorage.setItem(KEY, JSON.stringify(q)); } catch { /* private mode: the answer still goes out now */ } }

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
    ${a && a.status === "in_progress" ? `<div class="exam-right"><div class="exam-timer" id="timer" role="timer">${clock(left())}</div><div id="status">${status()}</div></div>` : ""}</header>`;
  if (!a) {
    root.innerHTML = `${head}<section class="exam-card"><p>${esc(t("Müddət: {n} dəqiqə. Vaxt server saatı ilə ölçülür; cavablar dəyişən kimi saxlanılır.", { n: e.duration_min }))}</p>
      <p class="exam-muted">${esc(t("Bağlantı kəsilsə cavablar bu brauzerdə saxlanılır və bağlantı qayıdanda göndərilir."))}</p>
      <button class="btn btn-primary" id="start">${esc(t("Başla"))}</button></section>`;
    return;
  }
  if (a.status !== "in_progress") {
    root.innerHTML = `${head}<section class="exam-card"><h2>${esc(t("Cavablarınız qəbul olundu"))}</h2>
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
  const r = await api("GET", `/api/exams/${id}`);
  if (r.status === 401 || r.status === 403 || r.status === 404) {
    root.innerHTML = `<section class="exam-card"><h1>${esc(t("İmtahan səhifəsi"))}</h1><p>${esc(r.data.error || t("İmtahana portaldan daxil olun."))}</p>
      <a class="btn" href="/">${esc(t("Portala qayıt"))}</a></section>`;
    return false;
  }
  if (r.status !== 200) { setTimeout(load, 3000); return false; }
  view = r.data;
  if (view.attempt) syncClock(view.attempt.remaining_s);
  draw();
  return true;
}

async function flush() {
  if (saving || !view || !view.attempt || view.attempt.status !== "in_progress") return;
  saving = true;
  try {
    for (const [qid, value] of Object.entries(queue())) {
      const r = await api("PUT", `/api/exams/${id}/answers/${qid}`, { value });
      if (r.status === 0) break;                                   // offline: keep the rest for later
      const q = queue();
      if (r.status === 200) { if (JSON.stringify(q[qid]) === JSON.stringify(value)) delete q[qid]; keep(q); syncClock(r.data.remaining_s); }
      else if (r.status === 409) { keep({}); await load(); return; }  // the time is over: the server's state wins
      else { delete q[qid]; keep(q); }                              // refused for good (not on the form): do not retry forever
    }
  } finally { saving = false; tick(); }
}

async function submit(auto = false) {
  if (submitting) return;
  if (!auto && !confirm(t("Təslim etmək istəyirsiniz? Bundan sonra cavab dəyişmir."))) return;
  submitting = true;
  await flush();
  const r = await api("POST", `/api/exams/${id}/submit`);
  submitting = false;
  if (r.status === 200) { keep({}); view = r.data; draw(); }
  else if (r.status === 0) setTimeout(() => submit(true), 3000);   // offline at the deadline: the server submits it anyway
}

root.addEventListener("change", (ev) => {
  const el = ev.target;
  if (!el.dataset || !el.dataset.q) return;
  const q = queue();
  q[el.dataset.q] = el.dataset.text !== undefined ? el.value : JSON.parse(el.dataset.v);
  keep(q);
  flush();
});
root.addEventListener("click", async (ev) => {
  const b = ev.target.closest("button");
  if (!b) return;
  if (b.id === "start") {
    b.disabled = true;
    const r = await api("POST", `/api/exams/${id}/start`);
    if (r.status === 200) { view = r.data; syncClock(view.attempt && view.attempt.remaining_s); draw(); }
    else { b.disabled = false; alert(r.data.error || t("Bağlantı yoxdur")); }
  } else if (b.id === "submit") submit(false);
  else if (b.id === "leave") { await api("POST", `/api/exams/${id}/leave`); location.href = "/"; }
});
window.addEventListener("online", () => { online = true; flush(); });
window.addEventListener("offline", () => { online = false; tick(); });
setInterval(tick, 1000);
setInterval(() => { if (Object.keys(queue()).length) flush(); else if (view && view.attempt && view.attempt.status === "in_progress") api("GET", `/api/exams/${id}`).then((r) => { if (r.status === 200) syncClock(r.data.attempt && r.data.attempt.remaining_s); tick(); }); }, 20000);
document.title = `${t("İmtahan")} · Zəka`;
await load();
flush();
