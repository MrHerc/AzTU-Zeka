// Core helpers for the Zəka SPA (no external dependencies)
import { t, tl, LANG, L10N, locale } from "./i18n.js";

export { t, tl, LANG };
export const S = { user: null, app: null, theme: localStorage.getItem("zeka-theme") || "light", lang: LANG };
export const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---------------------------------------------------------------- templating
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const raw = (s) => ({ __html: String(s ?? "") });
const val = (v) => (v == null || v === false ? "" : Array.isArray(v) ? v.map(val).join("") : v.__html !== undefined ? v.__html : esc(v));
export function html(strings, ...vals) {
  let out = strings[0];
  vals.forEach((v, i) => { out += val(v) + strings[i + 1]; });
  return raw(out);
}
export function mount(el, tpl) { el.innerHTML = tpl && tpl.__html !== undefined ? tpl.__html : String(tpl ?? ""); return el; }
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export function on(root, ev, sel, fn) {
  root.addEventListener(ev, (e) => { const tg = e.target.closest(sel); if (tg && root.contains(tg)) fn(e, tg); });
}

// ---------------------------------------------------------------- api
// Status of the most recent failed request: failed() shows "not found" with a way back instead of a pointless retry for a 404.
let lastFailStatus = null;
async function req(method, url, body) {
  lastFailStatus = null;
  const opt = { method, headers: { "X-Lang": LANG }, credentials: "same-origin" };
  const sid = sessionStorage.getItem("zeka-sid");
  if (sid) opt.headers["X-Session"] = sid;
  if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  let r;
  try { r = await fetch(url, opt); } catch { const e = new Error(t("Serverlə əlaqə yoxdur. İnternet bağlantısını yoxlayın.")); e.status = 0; lastFailStatus = 0; throw e; }
  let data = null;
  try { data = await r.json(); } catch { data = null; }
  if (!r.ok) {
    const err = new Error((data && data.error) || t("Xəta baş verdi ({status})", { status: r.status }));
    err.status = r.status;
    lastFailStatus = r.status;
    if (r.status === 401 && !url.includes("/api/bootstrap")) { location.hash = "#/login"; }
    throw err;
  }
  return data;
}
export const api = {
  get: (u) => req("GET", u), post: (u, b = {}) => req("POST", u, b), put: (u, b = {}) => req("PUT", u, b), del: (u) => req("DELETE", u),
};

// ---------------------------------------------------------------- router
const routes = [];
export function route(pattern, handler) {
  const keys = [];
  const rx = new RegExp("^" + pattern.replace(/\/:(\w+)(\?)?/g, (_, k, opt) => { keys.push(k); return opt ? "(?:/([^/]+))?" : "/([^/]+)"; }) + "/?$");
  routes.push({ rx, keys, handler, pattern });
}
export function matchRoute(path) {
  for (const r of routes) {
    const m = path.match(r.rx);
    if (m) { const params = {}; r.keys.forEach((k, i) => { if (m[i + 1] !== undefined) params[k] = decodeURIComponent(m[i + 1]); }); return { ...r, params }; }
  }
  return null;
}
export const go = (path) => { if (location.hash !== "#" + path) location.hash = "#" + path; else window.dispatchEvent(new HashChangeEvent("hashchange")); };
export function currentPath() {
  const h = location.hash.slice(1) || "/";
  const [p, q] = h.split("?");
  return { path: p, query: Object.fromEntries(new URLSearchParams(q || "")) };
}

// ---------------------------------------------------------------- page tours registry (engine: tour.js)
// registerTour("student.home", { route: "/student", roles: ["student"], title: t("…"), steps: [{ sel, title, text }] })
export const TOURS = new Map();
const patternRx = (p) => new RegExp("^" + p.replace(/\/:(\w+)(\?)?/g, (_, k, opt) => (opt ? "(?:/[^/]+)?" : "/[^/]+")) + "/?$");
export function registerTour(key, def) { TOURS.set(key, { key, ...def, rx: typeof def.route === "string" ? patternRx(def.route) : def.route }); }
export function tourFor(path, role) {
  for (const tr of TOURS.values()) if ((!tr.roles || tr.roles.includes(role)) && tr.rx && tr.rx.test(path)) return tr;
  return null;
}

// ---------------------------------------------------------------- formatting
const pad = (n) => String(n).padStart(2, "0");
const D = (s) => { const d = s instanceof Date ? s : new Date(s); return isNaN(d) ? null : d; };
export const fmtDate = (s) => { const d = s && D(s); if (!d) return "—"; const p = L10N.dateSep; return `${pad(d.getDate())}${p}${pad(d.getMonth() + 1)}${p}${d.getFullYear()}`; };
export const fmtTime = (s) => { const d = s && D(s); return d ? `${pad(d.getHours())}:${pad(d.getMinutes())}` : "—"; };
export const fmtDateTime = (s) => (s && D(s) ? `${fmtDate(s)} ${fmtTime(s)}` : "—");
export const MONTHS = L10N.months;
export const MONTHS_FULL = L10N.monthsFull;
export const WEEKDAYS = L10N.weekdays;
export const fmtDayLong = (s) => {
  const d = D(s); if (!d) return "—";
  const wd = WEEKDAYS[d.getDay()];
  if (LANG === "en") return `${wd}, ${d.getDate()} ${L10N.monthsGen[d.getMonth()]}`;
  return `${d.getDate()} ${L10N.monthsGen[d.getMonth()]}, ${wd.toLowerCase()}`;
};
export const fmtMonthYear = (s) => { const d = D(s); return d ? `${L10N.monthsFull[d.getMonth()]} ${d.getFullYear()}` : "—"; };
export const fmtDayMonth = (s) => { const d = D(s); return d ? (LANG === "en" ? `${d.getDate()} ${L10N.months[d.getMonth()]}` : `${d.getDate()} ${L10N.monthsGen[d.getMonth()]}`) : "—"; };
export function ago(s) {
  const d = s && D(s); if (!d) return "";
  const sec = (Date.now() - d.getTime()) / 1000;
  if (sec < 0) return fmtDateTime(s);
  if (sec < 60) return t("indicə");
  if (sec < 3600) return t("{n} dəq əvvəl", { n: Math.floor(sec / 60) });
  if (sec < 86400) return t("{n} saat əvvəl", { n: Math.floor(sec / 3600) });
  if (sec < 172800) return t("dünən");
  if (sec < 604800) return t("{n} gün əvvəl", { n: Math.floor(sec / 86400) });
  return fmtDate(s);
}
export const initials = (n) => String(n || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
export const avatar = (name, color, cls = "") => html`<span class="avatar ${cls}" style="background:${color || "#64748b"}" aria-hidden="true">${initials(name)}</span>`;
// Numbers follow the interface language, not the browser's locale data (Edge without Azerbaijani ICU data printed "88.6" next to
// server-formatted "4,0"): az/ru "3 680" and "88,6" (non-breaking space, decimal comma), en "3,680" and "88.6". Negative sign: "−".
const NUM_SEP = { az: ["\u00a0", ","], ru: ["\u00a0", ","], en: [",", "."] };
export const num = (n, dec) => {
  if (n == null || n === "" || isNaN(n)) return "—";
  const v = Number(n);
  const d = dec == null ? (String(Math.round(Math.abs(v) * 1000) / 1000).split(".")[1] || "").length : dec;
  const [grp, point] = NUM_SEP[LANG] || NUM_SEP.az;
  const [int, frac] = Math.abs(v).toFixed(d).split(".");
  const neg = v < 0 && Number(Math.abs(v).toFixed(d)) !== 0;
  return (neg ? "−" : "") + int.replace(/\B(?=(\d{3})+(?!\d))/g, grp) + (frac ? point + frac : "");
};
export const greeting = () => { const h = new Date().getHours(); return h < 12 ? t("Sabahınız xeyir") : h < 18 ? t("Günortanız xeyir") : t("Axşamınız xeyir"); };

export const STATUS = {
  submitted: [t("Yeni"), "b-blue"], in_progress: [t("İcrada"), "b-violet"], ready: [t("Hazırdır"), "b-green"], returned: [t("Düzəlişə qaytarılıb"), "b-amber"],
  rejected: [t("Rədd edilib"), "b-red"], valid: [t("Etibarlıdır"), "b-green"], revoked: [t("Ləğv edilib"), "b-red"], draft: [t("Qaralama"), "b-amber"],
  approved: [t("Təsdiqlənib"), "b-green"], open: [t("Cavab gözləyir"), "b-amber"], answered: [t("Cavablandırılıb"), "b-green"],
  cancelled: [t("Ləğv edilib"), "b-gray"], present: [t("İştirak edib"), "b-green"], absent: [t("Qayıb"), "b-red"], excused: [t("Üzrlü"), "b-blue"], late: [t("Gecikib"), "b-amber"],
  published: [t("Dərc olunub"), "b-green"], waiting: [t("Cavabınız gözlənilir"), "b-amber"], resolved: [t("Həll olunub"), "b-green"], closed: [t("Bağlanıb"), "b-gray"],
  operational: [t("İşləyir"), "b-green"], degraded: [t("Məhdud rejim"), "b-amber"], down: [t("İşləmir"), "b-red"], planned: [t("Planlaşdırılıb"), "b-gray"],
};
export const statusLabel = (s) => (STATUS[s] || [s])[0];
export const badge = (status, label) => { const [tx, c] = STATUS[status] || [status, "b-gray"]; return html`<span class="badge ${c}">${label || tx}</span>`; };
export const MODE_LABEL = { socratic: t("Sokratik"), explain: t("İzah"), practice: t("Məşq") };
export const QTYPE = { mcq: t("Çoxseçimli"), tf: t("Doğru / Yanlış"), numeric: t("Hesablama") };

// ---------------------------------------------------------------- toast & modal
export function toast(msg, type = "") {
  const box = document.getElementById("toasts");
  if (!box) return;
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.setAttribute("role", type === "err" ? "alert" : "status");
  el.innerHTML = `${type === "ok" ? icon("check", 18) : type === "err" ? icon("alert", 18) : icon("info", 18)}<span>${esc(msg)}</span>
    <button class="toast-x" aria-label="${esc(t("Bağla"))}">${icon("x", 14)}</button>`;
  box.appendChild(el);
  const kill = () => { el.classList.add("out"); setTimeout(() => el.remove(), 260); };
  el.querySelector(".toast-x").addEventListener("click", kill);
  setTimeout(kill, type === "err" ? 6000 : 3800);
}
export function modal({ title, body, size = "", actions = [], onMount, onClose, dismissable = true, cls = "" }) {
  const rootEl = document.getElementById("modal-root");
  const wrap = document.createElement("div");
  wrap.className = "modal-back";
  const prevFocus = document.activeElement;
  wrap.innerHTML = `<div class="modal ${size} ${cls}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
    <div class="modal-h"><h3>${esc(title)}</h3>${dismissable ? `<button class="btn btn-ghost btn-icon" data-close aria-label="${esc(t("Bağla"))}">${icon("x", 18)}</button>` : ""}</div>
    <div class="modal-b">${val(body)}</div>
    ${actions.length ? `<div class="modal-f">${actions.map((a, i) => `<button class="btn ${a.cls || ""}" data-act="${i}">${a.html || esc(a.label)}</button>`).join("")}</div>` : ""}
  </div>`;
  let closed = false;
  const close = () => {
    if (closed) return; closed = true;
    document.removeEventListener("keydown", onKey);
    wrap.classList.add("closing");
    setTimeout(() => { wrap.remove(); onClose && onClose(); if (prevFocus && prevFocus.focus) prevFocus.focus(); }, REDUCED ? 0 : 170);
  };
  const onKey = (e) => {
    if (e.key === "Escape" && dismissable && wrap === rootEl.lastElementChild) { e.stopPropagation(); close(); }
    if (e.key === "Tab") { // keep focus inside the dialog
      const f = $$("button, [href], input, select, textarea, iframe, [tabindex]:not([tabindex='-1'])", wrap).filter((x) => !x.disabled && x.offsetParent !== null);
      if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f.at(-1).focus(); }
      else if (!e.shiftKey && document.activeElement === f.at(-1)) { e.preventDefault(); f[0].focus(); }
    }
  };
  document.addEventListener("keydown", onKey);
  wrap.addEventListener("click", async (e) => {
    if (e.target === wrap && dismissable) return close();
    if (e.target.closest("[data-close]")) return close();
    const b = e.target.closest("[data-act]");
    if (b) {
      const a = actions[+b.dataset.act];
      if (!a.onClick) return close();
      b.disabled = true;
      try { const r = await a.onClick(wrap, close); if (r !== false) close(); } catch (err) { toast(err.message, "err"); } finally { b.disabled = false; }
    }
  });
  rootEl.appendChild(wrap);
  onMount && onMount(wrap, close);
  const f = wrap.querySelector(".modal-b input:not([type=checkbox]):not([type=radio]), .modal-b textarea, .modal-b select") || wrap.querySelector("[data-act], [data-close]");
  f && setTimeout(() => f.focus(), 60);
  return { el: wrap, close };
}
export const confirmBox = (title, text, okLabel = t("Təsdiqlə"), danger = false) => new Promise((res) => {
  let done = false;
  modal({ title, size: "sm", body: html`<p style="margin:0">${text}</p>`, onClose: () => { if (!done) res(false); },
    actions: [{ label: t("Ləğv et"), cls: "btn-ghost", onClick: () => { done = true; res(false); } },
              { label: okLabel, cls: danger ? "btn-danger" : "btn-primary", onClick: () => { done = true; res(true); } }] });
});

// Loading skeleton (shimmer). Use inside pages and cards while data loads.
export const loading = (text = t("Yüklənir…")) => html`<div class="skel-wrap" aria-busy="true" role="status"><span class="sr-only">${text}</span>
  <div class="skel skel-title"></div><div class="skel skel-line" style="width:46%"></div>
  <div class="skel-grid"><div class="skel skel-card"></div><div class="skel skel-card"></div><div class="skel skel-card"></div></div>
  <div class="skel skel-block"></div></div>`;
export const skelLines = (n = 3) => html`<div class="skel-wrap" aria-busy="true">${Array.from({ length: n }, (_, i) => html`<div class="skel skel-line" style="width:${92 - i * 13}%"></div>`)}</div>`;
export const spinner = (size = 16) => html`<span class="spinner" style="width:${size}px;height:${size}px" aria-hidden="true"></span>`;
// Empty state. action: html | { label, go, icon, cls }
export const empty = (ic_, title, text = "", action = null) => html`<div class="empty"><div class="ic">${raw(icon(ic_, 24))}</div><b>${title}</b>
  ${text ? html`<div class="small mt-sm">${text}</div>` : ""}
  ${action ? html`<div class="mt">${action.__html !== undefined ? action : html`<button class="btn ${action.cls || "btn-primary"} btn-sm" ${action.go ? raw(`data-go="${esc(action.go)}"`) : ""} ${action.id ? raw(`id="${esc(action.id)}"`) : ""}>${action.icon ? ic(action.icon, 15) : ""} ${action.label}</button>`}</div>` : ""}</div>`;
// Error state with retry button (data-retry); the page re-renders on click. A 404 (deleted request, old notification link) cannot be
// fixed by retrying, so it gets a "not found" state with a way back (#back-page, handled in main.js).
export const failed = (msg) => (lastFailStatus === 404
  ? empty("compass", t("Tapılmadı"), msg || t("Keçid köhnəlmiş ola bilər."), { label: t("Geri qayıt"), icon: "back", cls: "btn", id: "back-page" })
  : empty("alert", t("Məlumat yüklənmədi"), msg || "", { label: t("Yenidən cəhd et"), icon: "refresh", cls: "btn", id: "retry-page" }));

// Secondary information behind an (i) button. Shows on hover, focus and tap.
export const infoTip = (text, label = t("Ətraflı məlumat")) => raw(`<button type="button" class="info-tip" data-tip="${esc(text)}" aria-label="${esc(label + ": " + text)}">${icon("info", 15)}</button>`);

// ---------------------------------------------------------------- references (verified external sources, content/references.json)
// Titles and sections arrive in the language of the source; kind and lang are codes. One link per row: the whole row opens the
// source in a new tab. The server only sends https links.
const REF_KIND = {
  book: ["book", t("Dərslik")], course: ["cap", t("Açıq kurs")], docs: ["file", t("Rəsmi sənədləşmə")], guide: ["compass", t("Metodik vəsait")],
  policy: ["shield", t("Rəhbər sənəd")], article: ["flask", t("Elmi məqalə")], standard: ["scale", t("Standart")],
  database: ["grid", t("Məlumat bazası")], org: ["building", t("Rəsmi qurum")],
};
export const refList = (refs) => html`<div class="ref-list">${(refs || []).map((r) => {
  const [icn, kind] = REF_KIND[r.kind] || REF_KIND.docs;
  const meta = [r.authors, r.publisher].filter(Boolean).join(" · ");
  return html`<a class="ref-item" href="${r.url}" target="_blank" rel="noopener noreferrer">
    <span class="stat-ic ic-navy ref-ic" aria-hidden="true">${ic(icn, 16)}</span>
    <span class="ref-body"><span class="ref-t">${r.work}</span>${r.part ? html`<span class="ref-part">${r.part}</span>` : ""}
      <span class="ref-meta">${meta ? html`<span class="tiny muted">${meta}</span>` : ""}<span class="badge b-gray">${kind}</span>${r.lang && r.lang !== LANG ? html`<span class="badge b-blue" title="${t("Mənbənin dili")}">${r.lang.toUpperCase()}</span>` : ""}</span></span>
    <span class="ref-ext" aria-hidden="true">${ic("external", 15)}</span><span class="sr-only">${t("yeni pəncərədə açılır")}</span></a>`;
})}</div>`;
// Card for course pages and AI Akademiya modules; renders nothing when there are no references. checked = ISO date of the link check.
export function refCard(refs, checked, { title = t("Tövsiyə olunan mənbələr"), note = "", tour = "refs" } = {}) {
  if (!refs || !refs.length) return "";
  return html`<div class="card" data-tour="${tour}"><div class="card-h"><h3>${ic("book", 17)} ${title}
      ${infoTip(t("Bütün keçidlər {d} tarixində açılıb yoxlanılıb. Mənbələr öz dilində, əsasən ingilis dilində verilir.", { d: fmtDate(checked) }))}</h3>
    <span class="small muted ref-count">${t("{n} mənbə", { n: refs.length })}</span></div>
    <div class="card-b">${refList(refs)}${note ? html`<div class="tiny muted mt-sm">${note}</div>` : ""}</div></div>`;
}

// ---------------------------------------------------------------- icons (stroke)
const P = {
  home: "M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z",
  sparkles: "M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9zM19 15l.8 2.2 2.2.8-2.2.8L19 21l-.8-2.2L16 18l2.2-.8zM5 2l.6 1.4L7 4l-1.4.6L5 6l-.6-1.4L3 4l1.4-.6z",
  help: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01",
  quiz: "M9 3h6v4H9zM7 5H5v16h14V5h-2M9 13l2 2 4-4",
  file: "M14 3H6v18h12V7zM14 3v4h4M9 13h6M9 17h6",
  book: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5zM4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5",
  wand: "M15 4V2M15 10V8M11 6H9M21 6h-2M17.8 3.2l-1.4 1.4M17.8 8.8l-1.4-1.4M3 21l9.5-9.5 2 2L5 23z",
  message: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
  award: "M12 15a6 6 0 1 0 0-12 6 6 0 0 0 0 12zM8.2 13.4 7 22l5-3 5 3-1.2-8.6",
  chart: "M3 3v18h18M7 15l4-4 3 3 5-6",
  sliders: "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6",
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8",
  bell: "M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.9 1.9 0 0 0 3.4 0",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3",
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  check: "M20 6 9 17l-5-5",
  x: "M18 6 6 18M6 6l12 12",
  clock: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zM9 12l2 2 4-4",
  logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  chevron: "M9 18l6-6-6-6",
  back: "M19 12H5M12 19l-7-7 7-7",
  plus: "M12 5v14M5 12h14",
  send: "M22 2 11 13M22 2l-7 20-4-9-9-4z",
  up: "M7 10v12M15 5.9 14 10h5.8a2 2 0 0 1 1.9 2.6l-2.3 8a2 2 0 0 1-1.9 1.4H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.8a2 2 0 0 0 1.8-1.1L12 2a3.1 3.1 0 0 1 3 3.9z",
  trash: "M3 6h18M19 6l-1 14H6L5 6M8 6V4h8v2",
  refresh: "M21 12a9 9 0 1 1-3-6.7L21 8M21 3v5h-5",
  lock: "M5 11h14v11H5zM7 11V7a5 5 0 0 1 10 0v4",
  edit: "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z",
  eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  download: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3",
  printer: "M6 9V2h12v7M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v8H6z",
  sun: "M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  calendar: "M3 4h18v18H3zM16 2v4M8 2v4M3 10h18",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  alert: "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01",
  cap: "M22 10 12 5 2 10l10 5 10-5zM6 12v5c3 3 9 3 12 0v-5",
  bolt: "M13 2 3 14h9l-1 8 10-12h-9z",
  external: "M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6",
  copy: "M9 9h13v13H9zM5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1",
  target: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 18a6 6 0 1 0 0-12 6 6 0 0 0 0 12zM12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  layers: "M12 2 2 7l10 5 10-5zM2 17l10 5 10-5M2 12l10 5 10-5",
  cpu: "M5 5h14v14H5zM9 9h6v6H9zM9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3",
  qr: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h3v3h-3zM20 14v.01M14 20h.01M17 17h4v4h-4",
  trend: "M22 7 13.5 15.5 8.5 10.5 2 17M16 7h6v6",
  play: "M6 3l14 9-14 9z",
  inbox: "M22 12h-6l-2 3h-4l-2-3H2M5.5 5h13L22 12v7H2v-7z",
  building: "M3 21h18M5 21V7l7-4 7 4v14M9 9h1M14 9h1M9 13h1M14 13h1M9 17h1M14 17h1",
  calcheck: "M3 4h18v18H3zM16 2v4M8 2v4M3 10h18M9 16l2 2 4-4",
  heart: "M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8z",
  idcard: "M3 5h18v14H3zM7 9h4v4H7zM14 10h4M14 14h4M7 16h4",
  pause: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM10 9v6M14 9v6",
  scale: "M12 3v18M7 21h10M5 7h14M5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0z",
  wallet: "M3 7h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM3 7l12-4 2 4M16 13h2",
  news: "M4 4h13v16H6a2 2 0 0 1-2-2zM17 8h3v10a2 2 0 0 1-2 2M8 8h5M8 12h5M8 16h3",
  megaphone: "M3 11v3a1 1 0 0 0 1 1h3l6 4V6L7 10H4a1 1 0 0 0-1 1zM17 9a4 4 0 0 1 0 6M7 15l1 5h3",
  briefcase: "M3 7h18v13H3zM8 7V4h8v3M3 12h18",
  flask: "M9 3h6M10 3v6L4 19a2 2 0 0 0 2 3h12a2 2 0 0 0 2-3l-6-10V3M7 15h10",
  globe: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20",
  compass: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM16 8l-2 6-6 2 2-6z",
  menu: "M3 6h18M3 12h18M3 18h18",
  bookmark: "M6 3h12v18l-6-4-6 4z",
  pin: "M12 21s-7-6.1-7-12a7 7 0 0 1 14 0c0 5.9-7 12-7 12zM12 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  clip: "M21 11.5 12.5 20a5 5 0 0 1-7-7l8.5-8.5a3.3 3.3 0 0 1 4.7 4.7L10.2 17.7a1.7 1.7 0 0 1-2.4-2.4L15.5 7.6",
  user: "M20 21a8 8 0 0 0-16 0M12 13a5 5 0 1 0 0-10 5 5 0 0 0 0 10z",
  mail: "M3 5h18v14H3zM3 6l9 7 9-7",
  keyboard: "M2 6h20v12H2zM6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10",
  buoy: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4.9 4.9l4.3 4.3M14.8 14.8l4.3 4.3M14.8 9.2l4.3-4.3M4.9 19.1l4.3-4.3",
  grid: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  arrow: "M5 12h14M13 5l7 7-7 7",
  star: "M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9z",
  timer: "M10 2h4M12 14l3-3M12 22a8 8 0 1 0 0-16 8 8 0 0 0 0 16z",
  panel: "M3 3h18v18H3zM9 3v18",
  phone: "M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z",
  map: "M1 6v16l7-4 8 4 7-4V2l-7 4-8-4zM8 2v16M16 6v16",
  zoom: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3M11 8v6M8 11h6",
  ticket: "M3 7a2 2 0 0 0 2-2h14a2 2 0 0 0 2 2v3a2 2 0 0 0 0 4v3a2 2 0 0 0-2 2H5a2 2 0 0 0-2-2v-3a2 2 0 0 0 0-4zM13 5v2M13 11v2M13 17v2",
  activity: "M22 12h-4l-3 9L9 3l-3 9H2",
  trophy: "M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0zM17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3",
  rocket: "M4.5 16.5c-1.5 1.3-2 5-2 5s3.7-.5 5-2c.7-.8.7-2.1-.1-2.9a2.2 2.2 0 0 0-2.9-.1zM12 15l-3-3a22 22 0 0 1 2-3.9A12.9 12.9 0 0 1 22 2c0 2.7-.8 7.5-6 11a22.4 22.4 0 0 1-4 2zM9 12H4s.6-3 2-4c1.6-1.1 5 0 5 0M12 15v5s3-.6 4-2c1.1-1.6 0-5 0-5",
  facebook: "M15 3h-3a4 4 0 0 0-4 4v3H6v4h2v7h4v-7h3l1-4h-4V7a1 1 0 0 1 1-1h3z",
  instagram: "M7 2h10a5 5 0 0 1 5 5v10a5 5 0 0 1-5 5H7a5 5 0 0 1-5-5V7a5 5 0 0 1 5-5zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM17.5 6.5h.01",
  linkedin: "M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-4 0v7h-4v-7a6 6 0 0 1 6-6zM2 9h4v12H2zM4 6a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  youtube: "M22.5 6.4a2.8 2.8 0 0 0-2-2C18.8 4 12 4 12 4s-6.8 0-8.5.4a2.8 2.8 0 0 0-2 2A29 29 0 0 0 1 12a29 29 0 0 0 .5 5.6 2.8 2.8 0 0 0 2 2C5.2 20 12 20 12 20s6.8 0 8.5-.4a2.8 2.8 0 0 0 2-2A29 29 0 0 0 23 12a29 29 0 0 0-.5-5.6zM10 15.5v-7l6 3.5z",
  wikipedia: "M3 5h18v14H3zM7 9l2 7 3-5 3 5 2-7",
  smile: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01",
};
export function icon(name, size = 18, extra = "") {
  const d = name === "down" ? P.up : P[name] || P.info;
  const rot = name === "down" ? ' transform="rotate(180 12 12)"' : "";
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false" ${extra}><path d="${d}"${rot}/></svg>`;
}
export const ic = (name, size) => raw(icon(name, size));

// ---------------------------------------------------------------- markdown (light)
function inline(s) {
  let x = esc(s);
  x = x.replace(/`([^`]+)`/g, "<code>$1</code>");
  x = x.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  x = x.replace(/(^|[\s(])\*([^*\s][^*]*?)\*(?=[\s).,!?:;]|$)/g, "$1<em>$2</em>");
  x = x.replace(/\[(\d{1,2})\]/g, (m, n) => `<button class="cite" data-cite="${n}" title="${esc(t("Mənbə {n}", { n }))}">${n}</button>`);
  return x;
}
export function md(src) {
  const blocks = [];
  const text = String(src ?? "").replace(/```(\w+)?\n([\s\S]*?)```/g, (_, lg, code) => {
    blocks.push(`<pre><code>${esc(code.replace(/\n$/, ""))}</code></pre>`);
    return `\n\u0000${blocks.length - 1}\u0000\n`;
  });
  const out = [];
  let list = null, para = [];
  const fp = () => { if (para.length) { out.push(`<p>${inline(para.join(" "))}</p>`); para = []; } };
  const fl = () => { if (list) { out.push(`<${list.t}>${list.items.map((i) => `<li>${inline(i)}</li>`).join("")}</${list.t}>`); list = null; } };
  for (const rawLine of text.split("\n")) {
    const l = rawLine.trimEnd();
    let m;
    if ((m = l.match(/^\u0000(\d+)\u0000$/))) { fp(); fl(); out.push(blocks[+m[1]]); continue; }
    if (!l.trim()) { fp(); fl(); continue; }
    if ((m = l.match(/^#{1,4}\s+(.*)/))) { fp(); fl(); out.push(`<h4>${inline(m[1])}</h4>`); continue; }
    if ((m = l.match(/^>\s?(.*)/))) { fp(); fl(); out.push(`<div class="formula">${inline(m[1])}</div>`); continue; }
    if ((m = l.match(/^\s*[-*]\s+(.*)/))) { fp(); if (!list || list.t !== "ul") { fl(); list = { t: "ul", items: [] }; } list.items.push(m[1]); continue; }
    if ((m = l.match(/^\s*\d+[.)]\s+(.*)/))) { fp(); if (!list || list.t !== "ol") { fl(); list = { t: "ol", items: [] }; } list.items.push(m[1]); continue; }
    fl(); para.push(l);
  }
  fp(); fl();
  return raw(`<div class="md">${out.join("")}</div>`);
}
const FOLD = { "ə": "e", "ı": "i", "ö": "o", "ü": "u", "ş": "s", "ç": "c", "ğ": "g" };
export const fold = (s) => String(s).replace(/I/g, "ı").replace(/İ/g, "i").toLowerCase().replace(/[əıöüşçğ]/g, (c) => FOLD[c]);
export function highlight(htmlStr, query) {
  const stems = [...new Set(fold(query).match(/[a-z0-9а-яё]{4,}/g) || [])].map((w) => w.slice(0, 5));
  if (!stems.length) return htmlStr;
  return htmlStr.replace(/>([^<]+)</g, (m, txt) => ">" + txt.replace(/[0-9A-Za-zƏÖÜŞÇĞİIəıöüşçğА-Яа-яЁё]{4,}/g, (w) => (stems.some((s) => fold(w).startsWith(s)) ? `<mark>${w}</mark>` : w)) + "<");
}

// ---------------------------------------------------------------- charts (SVG, animated in CSS)
const niceMax = (v) => { if (v <= 0) return 1; const p = Math.pow(10, Math.floor(Math.log10(v))); const n = v / p; return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p; };
function smooth(pts) {
  if (pts.length < 2) return "";
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6], c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ` C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d;
}
let gid = 0;
export function lineChart({ labels, series, height = 230, suffix = "", target = null, max = null, label = "" }) {
  const W = 640, H = height, L = 40, R = 14, T = 14, B = 28;
  const all = series.flatMap((s) => s.values).concat(target ? [target.value] : []);
  const yMax = max || niceMax(Math.max(...all, 0) * 1.08);
  const x = (i) => L + (i * (W - L - R)) / Math.max(1, labels.length - 1);
  const y = (v) => T + (H - T - B) * (1 - v / yMax);
  const id = `g${++gid}`;
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="${esc(label || series.map((x_) => x_.name).join(", "))}" style="overflow:visible">`;
  s += `<defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${series[0].color}" stop-opacity=".22"/><stop offset="1" stop-color="${series[0].color}" stop-opacity="0"/></linearGradient></defs>`;
  for (let k = 0; k <= 4; k++) {
    const v = (yMax * k) / 4, yy = y(v);
    s += `<line x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}" stroke="var(--border)" stroke-dasharray="${k ? "3 4" : ""}"/>`;
    s += `<text x="${L - 8}" y="${yy + 4}" text-anchor="end" font-size="11" fill="var(--muted)">${num(+v.toFixed(1))}${suffix}</text>`;
  }
  labels.forEach((lb, i) => { s += `<text x="${x(i)}" y="${H - 8}" text-anchor="middle" font-size="11" fill="var(--muted)">${esc(lb)}</text>`; });
  if (target) {
    s += `<line x1="${L}" x2="${W - R}" y1="${y(target.value)}" y2="${y(target.value)}" stroke="var(--red)" stroke-dasharray="6 5" stroke-width="1.5"/>`;
    s += `<text x="${L + 6}" y="${y(target.value) - 6}" text-anchor="start" font-size="11" fill="var(--red)">${esc(target.label)}</text>`;
  }
  series.forEach((se, si) => {
    const pts = se.values.map((v, i) => [x(i), y(v)]);
    const d = smooth(pts);
    if (si === 0) s += `<path class="chart-area" d="${d} L${x(se.values.length - 1)},${y(0)} L${x(0)},${y(0)} Z" fill="url(#${id})"/>`;
    s += `<path class="chart-line" pathLength="1" d="${d}" fill="none" stroke="${se.color}" stroke-width="2.6" stroke-linecap="round"/>`;
    pts.forEach((p, i) => { s += `<circle class="chart-dot" style="--i:${i}" cx="${p[0]}" cy="${p[1]}" r="${i === pts.length - 1 ? 4.5 : 3}" fill="var(--surface)" stroke="${se.color}" stroke-width="2"><title>${esc(se.name)} · ${esc(labels[i])}: ${num(se.values[i])}${suffix}</title></circle>`; });
  });
  return raw(s + "</svg>");
}
export function barChart({ labels, values, colors, color = "#2563eb", height = 220, suffix = "", label = "" }) {
  const W = 640, H = height, L = 36, R = 10, T = 16, B = 30;
  const yMax = niceMax(Math.max(...values, 1) * 1.1);
  const bw = ((W - L - R) / values.length) * 0.56;
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="${esc(label)}">`;
  for (let k = 0; k <= 4; k++) {
    const v = (yMax * k) / 4, yy = T + (H - T - B) * (1 - k / 4);
    s += `<line x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}" stroke="var(--border)" stroke-dasharray="${k ? "3 4" : ""}"/><text x="${L - 6}" y="${yy + 4}" text-anchor="end" font-size="11" fill="var(--muted)">${num(+v.toFixed(0))}</text>`;
  }
  values.forEach((v, i) => {
    const cx = L + ((i + 0.5) * (W - L - R)) / values.length, h = ((H - T - B) * v) / yMax, c = (colors && colors[i]) || color;
    s += `<rect class="chart-bar" style="--i:${i}" x="${cx - bw / 2}" y="${H - B - h}" width="${bw}" height="${Math.max(h, 1)}" rx="7" fill="${c}"><title>${esc(labels[i])}: ${num(v)}${suffix}</title></rect>`;
    s += `<text class="chart-val" x="${cx}" y="${H - B - h - 6}" text-anchor="middle" font-size="11.5" font-weight="700" fill="var(--text-2)">${num(v)}${suffix}</text>`;
    s += `<text x="${cx}" y="${H - 9}" text-anchor="middle" font-size="11" fill="var(--muted)">${esc(labels[i])}</text>`;
  });
  return raw(s + "</svg>");
}
export function ring(pct, size = 64, color = "url(#ringg)", label = null, stroke = 7) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, p = Math.max(0, Math.min(100, pct || 0)), len = (c * p) / 100;
  return raw(`<svg class="ring" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="${esc(label ?? Math.round(p) + "%")}"><defs><linearGradient id="ringg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2b5aa8"/><stop offset="1" stop-color="#5a9bd3"/></linearGradient></defs>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--surface-3)" stroke-width="${stroke}"/>
    <circle class="ring-arc" style="--len:${len.toFixed(1)}" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${color}" stroke-width="${stroke}" stroke-linecap="round" stroke-dasharray="${len} ${c}" transform="rotate(-90 ${size / 2} ${size / 2})"/>
    <text x="50%" y="50%" text-anchor="middle" dominant-baseline="central" font-size="${size / 4.4}" font-weight="750" fill="var(--text)">${esc(label ?? Math.round(p) + "%")}</text></svg>`);
}
export function sparkline(values, color = "#2563eb", w = 120, h = 34) {
  if (!values || values.length < 2) return raw("");
  const mn = Math.min(...values), mx = Math.max(...values), span = mx - mn || 1;
  const pts = values.map((v, i) => [(i * (w - 4)) / (values.length - 1) + 2, h - 4 - ((v - mn) * (h - 8)) / span]);
  return raw(`<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><path class="chart-line" pathLength="1" d="${smooth(pts)}" fill="none" stroke="${color}" stroke-width="2.2" stroke-linecap="round"/><circle cx="${pts.at(-1)[0]}" cy="${pts.at(-1)[1]}" r="3" fill="${color}"/></svg>`);
}
export const progress = (pct, cls = "", label = "") => html`<div class="progress ${cls}" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(pct || 0)}" ${label ? raw(`aria-label="${esc(label)}"`) : ""}><span style="width:${Math.max(0, Math.min(100, pct || 0))}%"></span></div>`;
// Animated number: counts up from 0 when it scrolls into view. Text content is already the final value.
export const cnt = (value, { dec = 0, prefix = "", suffix = "" } = {}) =>
  html`<span class="count-up" data-count="${value}" data-dec="${dec}" data-prefix="${prefix}" data-suffix="${suffix}">${prefix}${num(value, dec)}${suffix}</span>`;

// ---------------------------------------------------------------- page chrome
// pageHead(title, sub, actions, crumbs, { info }) — keep `sub` to one short line; put details into `info` (shown behind ⓘ).
export function pageHead(title, sub = "", actions = "", crumbs = null, opts = {}) {
  const cr = crumbs && crumbs.length ? html`<nav class="crumbs" aria-label="${t("Naviqasiya zənciri")}">${crumbs.map((c, i) => html`${i ? raw('<span aria-hidden="true">/</span>') : ""}${c[1] ? html`<a href="#${c[1]}">${c[0]}</a>` : html`<span aria-current="page">${c[0]}</span>`}`)}</nav>` : "";
  const tourBtn = S.user && tourFor(currentPath().path, S.user.role)
    ? html`<button class="btn btn-ghost btn-sm page-tour-btn" data-page-tour title="${t("Bu səhifə necə işləyir?")}">${ic("compass", 15)}<span>${t("Səhifə bələdçisi")}</span></button>` : "";
  return html`<div class="page-head"><div class="ph-main">${cr}<div class="ph-title"><h1>${title}</h1>${opts.info ? infoTip(opts.info) : ""}</div>${sub ? html`<p>${sub}</p>` : ""}</div>
    <div class="row wrap ph-actions">${tourBtn}${actions}</div></div>`;
}
export const fmtSize = (n) => (n > 1048576 ? `${num(n / 1048576, 1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
export const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export function cover(c, size = 44, cls = "") {
  const tone = (c && c.tone) || "navy";
  return html`<div class="cover tone-${tone} ${cls}" aria-hidden="true">${ic((c && c.icon) || "news", size)}</div>`;
}
export function datebox(s) {
  const d = new Date(s);
  return html`<div class="datebox" aria-hidden="true"><div class="m">${MONTHS[d.getMonth()]}</div><div class="d">${d.getDate()}</div></div>`;
}
export function fileToB64(file) {
  return new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1] || ""); r.onerror = () => rej(new Error(t("Fayl oxunmadı"))); r.readAsDataURL(file); });
}
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export function copyText(text) {
  const done = () => toast(t("Kopyalandı"), "ok");
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
  fallbackCopy(text, done);
}
function fallbackCopy(text, done) { const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); done(); } catch { /* ignore */ } ta.remove(); }

// ---------------------------------------------------------------- in-app viewer (documents, syllabi, attachments)
// Everything opens inside the portal: no pop-up windows and no dependency on the browser's PDF plug-in.
const LINKS = { doc: (id) => `/api/documents/${id}/link`, syl: (id) => `/api/syllabus/${id}/link`, file: (id) => `/api/files/${id}/link` };
async function oneTimeUrl(kind, id) { const r = await api.post(LINKS[kind](id)); return r.url + (r.url.includes("?") ? "&" : "?") + "lang=" + LANG; }
export async function openInNewTab(kind, id) {
  const w = window.open("about:blank", "_blank");
  try { const u = await oneTimeUrl(kind, id); if (w) { w.opener = null; w.location.href = u; } else location.href = u; }
  catch (err) { if (w) w.close(); toast(err.message, "err"); }
}
export async function downloadFile(id, filename = "") {
  try {
    const u = (await oneTimeUrl("file", id)) + "&download=1";
    const a = document.createElement("a"); a.href = u; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  } catch (err) { toast(err.message, "err"); }
}
async function viewPage(kind, id, title) {
  const m = modal({ title, size: "xl", cls: "viewer", body: html`<div class="viewer-bar">
      <button class="btn btn-sm" data-v="print">${ic("printer", 15)} ${t("Çap et / PDF")}</button>
      <button class="btn btn-sm btn-ghost" data-v="tab">${ic("external", 15)} ${t("Yeni pəncərədə aç")}</button>
      <span class="grow"></span><span class="tiny muted">${ic("shield", 13)} ${t("Birdəfəlik təhlükəsiz keçid")}</span></div>
    <div class="viewer-stage"><div class="viewer-load">${spinner(22)}</div><iframe class="viewer-frame" title="${esc(title)}" hidden></iframe></div>` });
  const fr = m.el.querySelector("iframe");
  try {
    fr.src = (await oneTimeUrl(kind, id)) + "&embed=1";
    fr.addEventListener("load", () => { fr.hidden = false; m.el.querySelector(".viewer-load")?.remove(); }, { once: true });
  } catch (err) { m.el.querySelector(".viewer-stage").innerHTML = failed(err.message).__html; }
  on(m.el, "click", "[data-v]", (e, b) => {
    if (b.dataset.v === "print") { try { fr.contentWindow.focus(); fr.contentWindow.print(); } catch { openInNewTab(kind, id); } }
    else openInNewTab(kind, id);
  });
}
export const openDoc = (id, title = t("Sənəd")) => viewPage("doc", id, title);
export const openSyllabus = (id, title = t("Sillabus")) => viewPage("syl", id, title);
export async function openFile(id, title = "") {
  const m = modal({ title: title || t("Fayla baxış"), size: "lg", cls: "viewer", body: html`<div class="viewer-stage">${skelLines(6)}</div>` });
  const stage = m.el.querySelector(".viewer-stage");
  let f;
  try { f = await api.get(`/api/files/${id}/preview`); } catch (err) { stage.innerHTML = failed(err.message).__html; return; }
  m.el.querySelector(".modal-h h3").textContent = f.filename;
  const bar = html`<div class="viewer-bar"><span class="badge b-gray">${(f.filename.split(".").pop() || "").toUpperCase()}</span><span class="tiny muted">${fmtSize(f.size)} · ${fmtDateTime(f.created_at)}</span>
    <span class="grow"></span>
    ${f.kind === "pdf" && f.pages.length ? html`<div class="seg" role="tablist"><button class="active" data-pv="text" role="tab">${t("Önizləmə")}</button><button data-pv="orig" role="tab">${t("Orijinal")}</button></div>` : ""}
    <button class="btn btn-sm" data-v="dl">${ic("download", 15)} ${t("Yüklə")}</button>
    <button class="btn btn-sm btn-ghost" data-v="tab" title="${t("Yeni pəncərədə aç")}">${ic("external", 15)}</button></div>`;
  const paper = () => html`<div class="paper">${f.pages.map((p, i) => html`<article class="paper-page"><pre class="paper-text">${p}</pre><div class="paper-no">${i + 1} / ${f.pages.length}</div></article>`)}</div>`;
  const orig = async () => {
    const box = m.el.querySelector(".viewer-body");
    box.innerHTML = `<div class="viewer-load">${spinner(22).__html}</div>`;
    try {
      const u = await oneTimeUrl("file", id);
      box.innerHTML = f.kind === "image"
        ? `<div class="img-stage"><img class="viewer-img" src="${esc(u)}" alt="${esc(f.filename)}"></div>`
        : `<iframe class="viewer-frame" src="${esc(u)}" title="${esc(f.filename)}"></iframe><p class="tiny muted center mt-sm">${esc(t("Fayl görünmürsə, “Yüklə” düyməsindən istifadə edin."))}</p>`;
    } catch (err) { box.innerHTML = failed(err.message).__html; }
  };
  let body;
  if (f.kind === "image") body = "";
  else if (f.pages.length) body = paper();
  else body = empty("file", t("Bu fayl üçün önizləmə mövcud deyil"), t("Faylı yükləyib kompüterinizdə aça bilərsiniz."), { label: t("Faylı yüklə"), icon: "download", id: "pv-dl" });
  stage.innerHTML = html`${bar}<div class="viewer-body">${body}</div>`.__html;
  if (f.kind === "image" || (f.kind === "pdf" && !f.pages.length)) orig();
  on(m.el, "click", "[data-pv]", (e, b) => {
    $$("[data-pv]", m.el).forEach((x) => x.classList.toggle("active", x === b));
    if (b.dataset.pv === "orig") orig(); else m.el.querySelector(".viewer-body").innerHTML = paper().__html;
  });
  on(m.el, "click", "[data-v=dl], #pv-dl", () => downloadFile(id, f.filename));
  on(m.el, "click", "[data-v=tab]", () => openInNewTab("file", id));
  on(m.el, "click", ".viewer-img", (e, img) => img.classList.toggle("zoomed"));
}

// ---------------------------------------------------------------- motion: route progress, reveal, count-up, tab ink, ripple, tips
export const routeProgress = (() => {
  let el = null, timer = null, w = 0;
  const ensure = () => { if (!el) { el = document.createElement("div"); el.id = "route-progress"; el.setAttribute("aria-hidden", "true"); document.body.appendChild(el); } return el; };
  return {
    start() { const b = ensure(); clearInterval(timer); w = 8; b.style.opacity = "1"; b.style.width = w + "%"; timer = setInterval(() => { w = Math.min(90, w + (90 - w) * 0.12); b.style.width = w + "%"; }, 180); },
    done() { if (!el) return; clearInterval(timer); el.style.width = "100%"; setTimeout(() => { el.style.opacity = "0"; setTimeout(() => { el.style.width = "0%"; }, 260); }, 180); },
  };
})();

function animateCount(el) {
  const target = parseFloat(el.dataset.count), dec = +el.dataset.dec || 0, pre = el.dataset.prefix || "", suf = el.dataset.suffix || "";
  if (!isFinite(target) || REDUCED) return;
  const t0 = performance.now(), dur = Math.min(1400, 600 + Math.abs(target) * 6);
  const step = (now) => {
    // rAF timestamps can be earlier than t0 (frame start vs call time): clamp, or the first frame shows a negative value.
    const k = Math.max(0, Math.min(1, (now - t0) / dur)), e = 1 - Math.pow(1 - k, 3);
    el.textContent = pre + num(target * e, dec) + suf;
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
let io = null, lastInk = null;
function scanMotion(root) {
  if (!io) io = new IntersectionObserver((ents) => ents.forEach((en) => {
    if (!en.isIntersecting) return;
    const el = en.target; io.unobserve(el);
    if (el.dataset.count !== undefined) animateCount(el); else el.classList.add("rv-in");
  }), { rootMargin: "0px 0px -6% 0px" });
  $$("[data-count]:not([data-cd])", root).forEach((el) => { el.dataset.cd = "1"; io.observe(el); });
  if (!REDUCED) {
    const H = window.innerHeight;
    $$(".page .card:not([data-rv]), .page .reveal:not([data-rv])", root).forEach((el) => {
      el.dataset.rv = "1";
      if (el.getBoundingClientRect().top > H * 0.92) { el.classList.add("rv"); io.observe(el); }
    });
  }
  $$(".tabs, .seg", root).forEach((tabs) => {
    const act = tabs.querySelector(".active");
    let ink = tabs.querySelector(":scope > .tab-ink");
    if (!act) { if (ink) ink.style.opacity = "0"; return; }
    if (!ink) {
      ink = document.createElement("span"); ink.className = "tab-ink"; ink.setAttribute("aria-hidden", "true"); tabs.appendChild(ink);
      const key = location.hash.split("?")[0] + "|" + tabs.className;
      if (lastInk && lastInk.key === key && !REDUCED) { ink.style.transition = "none"; ink.style.left = lastInk.left + "px"; ink.style.width = lastInk.width + "px"; ink.getBoundingClientRect(); ink.style.transition = ""; }
    }
    const left = act.offsetLeft, width = act.offsetWidth;
    if (ink.style.left !== left + "px" || ink.style.width !== width + "px") { ink.style.left = left + "px"; ink.style.width = width + "px"; }
    ink.style.opacity = "1";
    lastInk = { key: location.hash.split("?")[0] + "|" + tabs.className, left, width };
  });
}
let tipEl = null, tipFor = null;
function showTip(btn) {
  if (!tipEl) { tipEl = document.createElement("div"); tipEl.className = "tip-pop"; tipEl.id = "tip-pop"; tipEl.setAttribute("role", "tooltip"); document.body.appendChild(tipEl); }
  tipFor = btn; tipEl.textContent = btn.dataset.tip; tipEl.classList.add("show");
  btn.setAttribute("aria-describedby", "tip-pop");
  const r = btn.getBoundingClientRect(), w = Math.min(320, window.innerWidth - 24);
  tipEl.style.maxWidth = w + "px";
  const tw = tipEl.offsetWidth, th = tipEl.offsetHeight;
  let left = Math.min(Math.max(12, r.left + r.width / 2 - tw / 2), window.innerWidth - tw - 12);
  let top = r.bottom + 8;
  if (top + th > window.innerHeight - 8) top = r.top - th - 8;
  tipEl.style.left = left + "px"; tipEl.style.top = top + "px";
}
function hideTip() { if (tipEl) tipEl.classList.remove("show"); if (tipFor) tipFor.removeAttribute("aria-describedby"); tipFor = null; }
export function initMotion() {
  const root = document.getElementById("root");
  let pending = false;
  const schedule = () => { if (pending) return; pending = true; requestAnimationFrame(() => { pending = false; scanMotion(document); }); };
  new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
  window.addEventListener("resize", schedule);
  document.addEventListener("pointerdown", (e) => {
    const b = e.target.closest(".btn, .tile, .role-card, .nav-item");
    if (!b || REDUCED || b.disabled) return;
    const r = b.getBoundingClientRect(), s = document.createElement("span");
    const d = Math.max(r.width, r.height) * 2;
    s.className = "ripple"; s.style.width = s.style.height = d + "px"; s.style.left = e.clientX - r.left - d / 2 + "px"; s.style.top = e.clientY - r.top - d / 2 + "px";
    b.appendChild(s); setTimeout(() => s.remove(), 600);
  });
  document.addEventListener("mouseover", (e) => { const b = e.target.closest(".info-tip"); if (b && b !== tipFor) showTip(b); else if (!b && tipFor && !e.target.closest(".tip-pop")) hideTip(); });
  document.addEventListener("focusin", (e) => { const b = e.target.closest(".info-tip"); if (b) showTip(b); else hideTip(); });
  document.addEventListener("click", (e) => { const b = e.target.closest(".info-tip"); if (b) { e.preventDefault(); e.stopPropagation(); if (tipFor === b && tipEl.classList.contains("show")) hideTip(); else showTip(b); } else hideTip(); }, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hideTip(); });
  window.addEventListener("scroll", hideTip, { passive: true });
  scanMotion(root || document);
}
