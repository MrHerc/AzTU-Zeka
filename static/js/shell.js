import { S, api, html, raw, mount, on, ic, icon, toast, go, avatar, ago, esc, $, $$, t, LANG, currentPath, tourFor, REDUCED } from "./core.js";
import { LANGS, setLang } from "./i18n.js";

export const HOME = { student: "/student", teacher: "/teacher", office: "/office", leader: "/leader", admin: "/admin" };
export const ROLES = [
  ["student", t("Tələbə"), t("Aysel Məmmədova · İT-25-1"), "cap", "ic-blue"],
  ["teacher", t("Müəllim"), t("Dos. Rauf Əliyev · Elektronika"), "book", "ic-navy"],
  ["office", t("Dekanlıq"), t("Nigar Rzayeva · müraciətlər"), "inbox", "ic-green"],
  ["leader", t("Rəhbərlik"), t("Rektorluq · pilot paneli"), "chart", "ic-amber"],
  ["admin", t("Administrator"), t("İT mərkəzi · platforma"), "sliders", "ic-coral"],
];
export const ROLE_LABEL = Object.fromEntries(ROLES.map((r) => [r[0], r[1]]));

const UNI = [t("Universitet"), [["news", t("Xəbərlər və tədbirlər"), "/news", "news"], ["trophy", t("Nailiyyətlər"), "/achievements"], ["phone", t("Əlaqə"), "/contact"]]];
const UNI_STAFF = [t("Universitet"), [["trophy", t("Nailiyyətlər"), "/achievements"], ["phone", t("Əlaqə"), "/contact"]]];
export const NAV = {
  student: [[t("Əsas"), [["home", t("Əsas səhifə"), "/student"], ["calendar", t("Dərs cədvəli"), "/student/schedule"]]],
            [t("Təhsil"), [["book", t("Fənlərim"), "/student/courses"], ["sparkles", t("AI tutor"), "/student/tutor"], ["quiz", t("Testlər"), "/student/quizzes"],
                           ["calcheck", t("Davamiyyət"), "/student/attendance", "absences"], ["target", t("Qiymətlərim"), "/student/grades"]]],
            [t("Xidmətlər"), [["grid", t("E-xidmətlər"), "/student/services"], ["inbox", t("Müraciətlərim"), "/student/requests", "requests"], ["help", t("Kampus köməkçisi"), "/student/campus"]]],
            UNI, [t("Kömək"), [["buoy", t("Bələdçi"), "/guide"], ["ticket", t("Dəstək"), "/support", "support"]]]],
  teacher: [[t("Əsas"), [["home", t("Əsas səhifə"), "/teacher"], ["calendar", t("Dərs cədvəli"), "/teacher/schedule"]]],
            [t("Tədris"), [["book", t("Fənlərim"), "/teacher/courses"], ["wand", t("Test studiyası"), "/teacher/studio"], ["inbox", t("Tələbə sualları"), "/teacher/questions", "questions"]]],
            [t("Peşəkar inkişaf"), [["cap", t("AI Akademiya"), "/teacher/academy"], ["cpu", t("Texnoloji həllər"), "/teacher/tools"], ["layers", t("Sillabus köməkçisi"), "/teacher/syllabus"]]],
            UNI, [t("Kömək"), [["buoy", t("Bələdçi"), "/guide"], ["ticket", t("Dəstək"), "/support", "support"]]]],
  office: [[t("Dekanlıq"), [["inbox", t("Müraciətlər"), "/office", "office"], ["qr", t("Sənəd reyestri"), "/office/registry"], ["ticket", t("Dəstək sorğuları"), "/staff/support", "support"]]],
           [t("Kommunikasiya"), [["megaphone", t("Xəbərlərin idarə edilməsi"), "/staff/news"], ["news", t("Xəbər lenti"), "/news"]]],
           UNI_STAFF, [t("Kömək"), [["buoy", t("Bələdçi"), "/guide"]]]],
  leader: [[t("Rəhbərlik"), [["chart", t("Pilot paneli"), "/leader"], ["smile", t("Rəylər və məmnuniyyət"), "/staff/feedback"], ["inbox", t("E-xidmətlər"), "/office", "office"], ["qr", t("Sənəd reyestri"), "/office/registry"]]],
           [t("Kommunikasiya"), [["megaphone", t("Xəbərlərin idarə edilməsi"), "/staff/news"], ["news", t("Xəbər lenti"), "/news"]]],
           UNI_STAFF, [t("Nəzarət"), [["list", t("Audit jurnalı"), "/admin/audit"]]], [t("Kömək"), [["buoy", t("Bələdçi"), "/guide"], ["ticket", t("Dəstək"), "/support", "support"]]]],
  admin: [[t("Platforma"), [["sliders", t("İdarəetmə"), "/admin"], ["ticket", t("Dəstək sorğuları"), "/staff/support", "support"], ["smile", t("Rəylər və məmnuniyyət"), "/staff/feedback"], ["list", t("Audit jurnalı"), "/admin/audit"]]],
          [t("Məzmun"), [["megaphone", t("Xəbərlərin idarə edilməsi"), "/staff/news"], ["inbox", t("Müraciətlər"), "/office", "office"]]], UNI_STAFF, [t("Kömək"), [["buoy", t("Bələdçi"), "/guide"]]]],
};
// Mobile bottom bar: 4 primary destinations per role (+ menu)
const BOTTOM = {
  student: [["home", t("Əsas"), "/student"], ["calendar", t("Cədvəl"), "/student/schedule"], ["sparkles", t("Tutor"), "/student/tutor"], ["grid", t("Xidmətlər"), "/student/services"]],
  teacher: [["home", t("Əsas"), "/teacher"], ["book", t("Fənlər"), "/teacher/courses"], ["wand", t("Studiya"), "/teacher/studio"], ["cap", t("Akademiya"), "/teacher/academy"]],
  office: [["inbox", t("Müraciətlər"), "/office"], ["qr", t("Reyestr"), "/office/registry"], ["ticket", t("Dəstək"), "/staff/support"], ["news", t("Xəbərlər"), "/news"]],
  leader: [["chart", t("Panel"), "/leader"], ["smile", t("Rəylər"), "/staff/feedback"], ["inbox", t("Xidmətlər"), "/office"], ["news", t("Xəbərlər"), "/news"]],
  admin: [["sliders", t("Panel"), "/admin"], ["ticket", t("Dəstək"), "/staff/support"], ["list", t("Audit"), "/admin/audit"], ["megaphone", t("Xəbərlər"), "/staff/news"]],
};
const QUICK = {
  student: [["file", t("Arayış sifariş et"), "/student/services?new=enrollment_certificate"], ["heart", t("Qayıbı üzrlü et (həkim arayışı)"), "/student/services?new=absence_excuse"],
            ["calcheck", t("Dərslərdən icazə istə"), "/student/services?new=leave_permission"], ["sparkles", t("AI tutora sual ver"), "/student/tutor"], ["ticket", t("Dəstəyə yaz"), "/support?tab=new"]],
  teacher: [["wand", t("AI ilə test yarat"), "/teacher/studio"], ["upload", t("Material yüklə"), "/teacher/courses"], ["layers", t("Sillabus hazırla"), "/teacher/syllabus"], ["cap", t("Akademiyada davam et"), "/teacher/academy"]],
  office: [["inbox", t("Yeni müraciətlər"), "/office"], ["megaphone", t("Xəbər dərc et"), "/staff/news?new=1"], ["qr", t("Sənədi yoxla"), "/office/registry"], ["ticket", t("Dəstək sorğuları"), "/staff/support"]],
  leader: [["chart", t("Pilot paneli"), "/leader"], ["smile", t("Rəylər və məmnuniyyət"), "/staff/feedback"], ["megaphone", t("Xəbər dərc et"), "/staff/news?new=1"]],
  admin: [["sliders", t("LLM tənzimləmələri"), "/admin"], ["list", t("Audit jurnalı"), "/admin/audit"], ["ticket", t("Dəstək sorğuları"), "/staff/support"]],
};
const N_ICON = { request: ["inbox", "ic-blue"], attendance: ["calcheck", "ic-green"], news: ["news", "ic-coral"], event: ["calendar", "ic-coral"], quiz: ["quiz", "ic-navy"],
  question: ["help", "ic-amber"], answer: ["message", "ic-green"], message: ["message", "ic-blue"], academy: ["cap", "ic-violet"], sla: ["alert", "ic-red"],
  report: ["chart", "ic-amber"], exam: ["clock", "ic-amber"], support: ["ticket", "ic-blue"] };
export const notifIcon = (kind) => N_ICON[kind] || ["bell", "ic-navy"];
let badgeTimer = null;
const isMobile = () => window.matchMedia("(max-width: 980px)").matches;

export function shell(root) {
  const u = S.user;
  const collapsed = (localStorage.getItem("zeka-sidebar") || (u.prefs && u.prefs.sidebar)) === "collapsed";
  mount(root, html`<div class="app ${collapsed ? "sb-collapsed" : ""}" id="app">
    <aside class="sidebar" id="sidebar" aria-label="${t("Əsas menyu")}">
      <div class="sb-head">
        <a class="brand" href="#${HOME[u.role]}" title="${t("AzTU Rəqəmsal Kampus")}"><img src="/static/img/brand/icon.png" alt="${t("AzTU loqosu")}">
          <div class="brand-txt"><div class="brand-name">Az<span>TU</span> ${t("Rəqəmsal Kampus")}</div><div class="brand-by">by <b>Safarov Industries</b></div></div></a>
        <button class="sb-close icon-btn" id="sb-close" aria-label="${t("Menyunu bağla")}">${ic("x", 18)}</button>
      </div>
      <nav class="nav" id="nav">${NAV[u.role].map(([sec, items]) => html`<div class="nav-section"><span>${sec}</span></div>${items.map(([i, l, p, b]) =>
        html`<a class="nav-item" href="#${p}" data-path="${p}" data-label="${l}">${ic(i, 18)}<span class="nav-l">${l}</span>${b ? html`<span class="count hidden" data-badge="${b}"></span>` : ""}</a>`)}`)}</nav>
      <div class="sidebar-foot">
        <div class="engine-pill" title="${S.app.engine.label}"><span class="dot ${S.app.engine.mode === "demo" ? "amber" : ""}"></span><span class="sf-l">${S.app.engine.label}</span></div>
        <div class="sf-l sf-sem">${S.app.semester}</div>
        <div class="sf-l sf-credit">Zəka v${S.app.version || "0.3"} · © 2026 Safarov Industries</div>
      </div>
      <button class="sb-collapse" id="sb-collapse" aria-controls="sidebar" aria-expanded="${!collapsed}">${ic("panel", 17)}<span class="nav-l">${t("Paneli yığ")}</span></button>
    </aside>
    <div class="main">
      <header class="topbar">
        <button class="icon-btn burger" id="burger" aria-label="${t("Menyunu aç və ya bağla")}" aria-controls="sidebar" title="${t("Menyu")} ( [ )">${ic("menu", 20)}</button>
        <button class="search-btn" id="search-btn" aria-label="${t("Axtarış")}">${ic("search", 16)}<span class="lbl">${t("Xidmət, fənn və ya xəbər axtarın…")}</span><span class="kbd">Ctrl K</span></button>
        <div class="spacer"></div>
        <div class="tb-rel"><button class="lang-btn" id="lang-btn" aria-label="${t("Dil seçimi")}" aria-haspopup="menu">${ic("globe", 16)}<span>${LANG.toUpperCase()}</span></button></div>
        <div class="tb-rel"><button class="icon-btn" id="help-btn" aria-label="${t("Kömək")}" aria-haspopup="menu" title="${t("Kömək və bələdçi")}">${ic("help", 19)}</button></div>
        <button class="icon-btn hide-sm" id="theme" aria-label="${t("Tema")}" title="${t("Açıq / tünd tema")}">${ic(S.theme === "dark" ? "sun" : "moon", 19)}</button>
        <div class="tb-rel"><button class="icon-btn" id="bell" aria-label="${t("Bildirişlər")}" aria-haspopup="dialog" title="${t("Bildirişlər")}">${ic("bell", 19)}<span class="pip hidden" id="bell-pip"></span></button></div>
        <div class="tb-rel"><button class="user-chip" id="user-btn" aria-label="${t("Profil menyusu")}" aria-haspopup="menu">${avatar(u.full_name, u.color)}
          <div class="who"><b>${u.full_name}</b><span>${u.title}</span></div>${ic("chevron", 14, 'transform="rotate(90 12 12)"')}</button></div>
      </header>
      <div id="content"></div>
    </div>
    <nav class="bottom-nav" aria-label="${t("Sürətli naviqasiya")}">${BOTTOM[u.role].map(([i, l, p]) => html`<a href="#${p}" data-path="${p}">${ic(i, 20)}<span>${l}</span></a>`)}
      <button id="bn-menu" aria-label="${t("Bütün bölmələr")}">${ic("menu", 20)}<span>${t("Menyu")}</span></button></nav>
    <button class="fab-feedback" id="fab-feedback" aria-label="${t("Rəy bildir")}" title="${t("Rəy bildir")}">${ic("smile", 19)}<span>${t("Rəy")}</span></button>
  </div>`);
  root.dataset.shell = u.role + ":" + u.id + ":" + LANG;
  const app = $("#app", root);
  syncCollapsedTitles(app);
  const toggle = () => { if (isMobile()) app.classList.toggle("nav-open"); else setCollapsed(app, !app.classList.contains("sb-collapsed")); };
  $("#burger", root).addEventListener("click", toggle);
  $("#sb-collapse", root).addEventListener("click", () => setCollapsed(app, !app.classList.contains("sb-collapsed")));
  $("#sb-close", root).addEventListener("click", () => app.classList.remove("nav-open"));
  $("#bn-menu", root).addEventListener("click", () => app.classList.add("nav-open"));
  app.addEventListener("click", (e) => { if (e.target === app) app.classList.remove("nav-open"); });
  $("#nav", root).addEventListener("click", (e) => { if (e.target.closest(".nav-item")) app.classList.remove("nav-open"); });
  $("#search-btn", root).addEventListener("click", () => palette());
  $("#theme", root).addEventListener("click", toggleTheme);
  $("#bell", root).addEventListener("click", (e) => { e.stopPropagation(); toggleNotifications($("#bell", root).parentElement); });
  $("#user-btn", root).addEventListener("click", (e) => { e.stopPropagation(); userMenu($("#user-btn", root).parentElement); });
  $("#help-btn", root).addEventListener("click", (e) => { e.stopPropagation(); helpMenu($("#help-btn", root).parentElement); });
  $("#lang-btn", root).addEventListener("click", (e) => { e.stopPropagation(); langMenu($("#lang-btn", root).parentElement); });
  $("#fab-feedback", root).addEventListener("click", () => window.dispatchEvent(new CustomEvent("zeka:feedback")));
  refreshBadges();
  clearInterval(badgeTimer);
  badgeTimer = setInterval(() => { if (S.user && document.visibilityState === "visible") refreshBadges(); }, 30000);
}

function syncCollapsedTitles(app) {
  const c = app.classList.contains("sb-collapsed");
  $$(".nav-item", app).forEach((a) => { if (c) a.title = a.dataset.label; else a.removeAttribute("title"); });
  const b = $("#sb-collapse", app);
  if (b) { b.setAttribute("aria-expanded", String(!c)); b.title = c ? t("Paneli aç") : t("Paneli yığ"); b.querySelector(".nav-l").textContent = c ? t("Paneli aç") : t("Paneli yığ"); }
}
export function setCollapsed(app, collapsed) {
  app = app || $("#app");
  if (!app) return;
  app.classList.toggle("sb-collapsed", collapsed);
  syncCollapsedTitles(app);
  localStorage.setItem("zeka-sidebar", collapsed ? "collapsed" : "open");
  S.user.prefs = { ...(S.user.prefs || {}), sidebar: collapsed ? "collapsed" : "open" };
  api.put("/api/me/prefs", { sidebar: collapsed ? "collapsed" : "open" }).catch(() => {});
}
function toggleTheme() {
  S.theme = S.theme === "dark" ? "light" : "dark";
  localStorage.setItem("zeka-theme", S.theme);
  document.documentElement.dataset.theme = S.theme;
  const b = $("#theme"); if (b) b.innerHTML = icon(S.theme === "dark" ? "sun" : "moon", 19);
}

export async function refreshBadges() {
  try {
    const b = await api.get("/api/badges");
    const pip = $("#bell-pip");
    if (pip) { pip.textContent = b.notifications > 9 ? "9+" : b.notifications; pip.classList.toggle("hidden", !b.notifications); }
    $$("[data-badge]").forEach((el) => { const n = b[el.dataset.badge] || 0; el.textContent = n; el.classList.toggle("hidden", !n); });
  } catch { /* ignore */ }
}

function closeDropdowns() { $$(".dropdown").forEach((d) => d.remove()); }
document.addEventListener("click", (e) => { if (!e.target.closest(".dropdown")) closeDropdowns(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDropdowns(); });
function dropdown(host, cls, htmlStr) {
  if (host.querySelector(".dropdown")) { closeDropdowns(); return null; }
  closeDropdowns();
  const dd = document.createElement("div");
  dd.className = "dropdown " + cls;
  dd.innerHTML = htmlStr;
  host.appendChild(dd);
  const first = dd.querySelector("a, button"); if (first) setTimeout(() => first.focus({ preventScroll: true }), 30);
  on(dd, "click", ".menu-item[href]", () => closeDropdowns());
  return dd;
}

async function toggleNotifications(host) {
  const dd = dropdown(host, "notif-dd", `<div class="notif-h"><b>${esc(t("Bildirişlər"))}</b></div><div class="notif-list">${'<div class="skel skel-line"></div>'.repeat(4)}</div>`);
  if (!dd) return;
  let r;
  try { r = await api.get("/api/notifications"); } catch (err) { dd.querySelector(".notif-list").innerHTML = `<div class="empty small">${esc(err.message)}</div>`; return; }
  mount(dd, html`<div class="notif-h"><b>${t("Bildirişlər")} ${r.unread ? html`<span class="badge b-coral">${t("{n} yeni", { n: r.unread })}</span>` : ""}</b>
      <button class="btn btn-ghost btn-sm" id="read-all" ${r.unread ? "" : "disabled"}>${ic("check", 14)} ${t("Hamısını oxunmuş et")}</button></div>
    <div class="notif-list">${r.items.length ? r.items.slice(0, 12).map((n) => { const [i, c] = notifIcon(n.kind);
      return html`<a class="notif ${n.read_at ? "" : "unread"}" href="#${n.link || "/"}" data-nid="${n.id}"><span class="ni ${c}">${ic(i, 16)}</span>
        <div class="grow"><b>${n.title}</b>${n.body ? html`<span>${n.body}</span>` : ""}<span class="tiny">${ago(n.created_at)}</span></div>${n.read_at ? "" : raw('<span class="nd" aria-hidden="true"></span>')}</a>`; })
      : html`<div class="empty">${ic("bell", 22)}<div class="mt-sm">${t("Bildiriş yoxdur")}</div></div>`}</div>
    <a class="notif-all" href="#/notifications">${t("Bütün bildirişlər")} ${ic("arrow", 14)}</a>`);
  on(dd, "click", "#read-all", async (e) => { e.stopPropagation(); await api.post("/api/notifications/read", { all: true }); refreshBadges(); closeDropdowns(); toast(t("Bütün bildirişlər oxunmuş kimi qeyd edildi"), "ok"); });
  on(dd, "click", "[data-nid]", (e, a) => { api.post("/api/notifications/read", { ids: [+a.dataset.nid] }).then(refreshBadges); closeDropdowns(); });
  on(dd, "click", ".notif-all", () => closeDropdowns());
}

function langMenu(host) {
  dropdown(host, "menu lang-dd", html`<div class="menu-label">${t("Interfeys dili")}</div>${LANGS.map((l) => html`<button class="menu-item" data-lang="${l.code}" lang="${l.code}">
      <span class="lang-code">${l.short}</span> ${l.label}${l.code === LANG ? raw(` <span class="badge b-green" style="margin-left:auto">${esc(t("seçilib"))}</span>`) : ""}</button>`)}
    <div class="menu-sep"></div><div class="menu-note">${t("Fənn materialları və AI tutorun sitatları tədris dilində qalır.")}</div>`.__html);
  const dd = host.querySelector(".dropdown");
  if (dd) on(dd, "click", "[data-lang]", (e, b) => { closeDropdowns(); switchLang(b.dataset.lang); });
}
export async function switchLang(code) {
  if (!setLang(code)) return;
  try { if (S.user) await api.put("/api/me/prefs", { lang: code }); } catch { /* offline: local choice still applies */ }
  document.body.classList.add("lang-switching");
  const url = new URL(location.href);
  url.searchParams.delete("lang");
  const target = url.toString();
  // location.replace() to the same address (only a #route) is an in-page fragment jump, not a reload: the page stayed dimmed.
  setTimeout(() => { if (target === location.href) location.reload(); else location.replace(target); }, REDUCED ? 0 : 160);
}

function userMenu(host) {
  const u = S.user;
  const dd = dropdown(host, "menu", html`<div class="row" style="padding:10px 11px">${avatar(u.full_name, u.color, "lg")}<div><b>${u.full_name}</b><div class="small muted">${u.title}</div></div></div>
    <div class="menu-sep"></div>
    <a class="menu-item" href="#/profile">${ic("user", 16)} ${t("Profil və tənzimləmələr")}</a>
    <a class="menu-item" href="#/notifications">${ic("bell", 16)} ${t("Bildirişlər")}</a>
    <a class="menu-item" href="#/support">${ic("ticket", 16)} ${t("Dəstək xidməti")}</a>
    <button class="menu-item show-sm" id="um-theme">${ic(S.theme === "dark" ? "sun" : "moon", 16)} ${S.theme === "dark" ? t("Açıq tema") : t("Tünd tema")}</button>
    <div class="menu-sep"></div><div class="menu-label">${t("Demo: rolu dəyiş")}</div>
    ${ROLES.map(([k, l, s, i]) => html`<button class="menu-item" data-switch="${k}">${ic(i, 16)} ${l}${k === u.role ? raw(` <span class="badge b-green" style="margin-left:auto">${esc(t("aktiv"))}</span>`) : ""}</button>`)}
    <div class="menu-sep"></div><button class="menu-item danger" id="logout">${ic("logout", 16)} ${t("Çıxış")}</button>`.__html);
  if (!dd) return;
  on(dd, "click", "[data-switch]", (e, b) => { closeDropdowns(); if (b.dataset.switch !== S.user.role) switchRole(b.dataset.switch); });
  on(dd, "click", "#um-theme", () => { closeDropdowns(); toggleTheme(); });
  on(dd, "click", "#logout", async () => { closeDropdowns(); await api.post("/api/auth/logout"); sessionStorage.removeItem("zeka-sid"); S.user = null; go("/login"); });
}

export async function switchRole(role) {
  const r = await api.post("/api/auth/demo", { role });
  sessionStorage.setItem("zeka-sid", r.token);
  S.user = r.user;
  document.getElementById("root").dataset.shell = "";
  go(r.home);
}

function helpMenu(host) {
  const tour = S.user && tourFor(currentPath().path, S.user.role);
  const dd = dropdown(host, "menu", html`${tour ? html`<button class="menu-item strong" id="hm-page">${ic("compass", 16)} ${t("Bu səhifəni izah et")}<span class="tiny muted" style="margin-left:auto">${tour.steps.length}</span></button>` : ""}
    <a class="menu-item" href="#/guide">${ic("buoy", 16)} ${t("Bələdçi mərkəzi")}</a>
    <button class="menu-item" id="hm-tour">${ic("play", 16)} ${t("Platforma ilə tanışlıq turu")}</button>
    <button class="menu-item" id="hm-keys">${ic("keyboard", 16)} ${t("Klaviatura qısayolları")}</button>
    <div class="menu-sep"></div>
    <a class="menu-item" href="#/support">${ic("ticket", 16)} ${t("Dəstək xidmətinə yaz")}</a>
    <button class="menu-item" id="hm-fb">${ic("smile", 16)} ${t("Rəy bildir")}</button>`.__html);
  if (!dd) return;
  on(dd, "click", "#hm-page", () => { closeDropdowns(); window.dispatchEvent(new CustomEvent("zeka:pagetour")); });
  on(dd, "click", "#hm-tour", () => { closeDropdowns(); window.dispatchEvent(new CustomEvent("zeka:tour", { detail: { force: true } })); });
  on(dd, "click", "#hm-keys", () => { closeDropdowns(); go("/guide?tab=shortcuts"); });
  on(dd, "click", "#hm-fb", () => { closeDropdowns(); window.dispatchEvent(new CustomEvent("zeka:feedback")); });
}

// ---------------------------------------------------------------- command palette (Ctrl+K)
export function palette() {
  if (!S.user || document.querySelector(".palette-back")) return;
  const pages = NAV[S.user.role].flatMap(([sec, items]) => items.map(([i, l, p]) => ({ group: t("Səhifələr"), title: l, sub: sec, link: p, icon: i })));
  pages.push({ group: t("Səhifələr"), title: t("Profil və tənzimləmələr"), sub: "", link: "/profile", icon: "user" }, { group: t("Səhifələr"), title: t("Bildirişlər"), sub: "", link: "/notifications", icon: "bell" });
  const quick = (QUICK[S.user.role] || []).map(([i, l, p]) => ({ group: t("Sürətli əməliyyatlar"), title: l, sub: "", link: p, icon: i }));
  const back = document.createElement("div");
  back.className = "palette-back";
  back.innerHTML = `<div class="palette" role="dialog" aria-modal="true" aria-label="${esc(t("Axtarış"))}"><div class="palette-in">${icon("search", 18)}<input id="pq" placeholder="${esc(t("Nə axtarırsınız? Məsələn: arayış, Kirxhof, hakaton"))}" autocomplete="off" aria-label="${esc(t("Axtarış sorğusu"))}"><span class="kbd">Esc</span></div>
    <div class="palette-res" id="pres" role="listbox"></div><div class="palette-foot"><span><span class="kbd">↑</span> <span class="kbd">↓</span> ${esc(t("seçim"))}</span><span><span class="kbd">Enter</span> ${esc(t("keçid"))}</span><span><span class="kbd">Esc</span> ${esc(t("bağla"))}</span></div></div>`;
  document.body.appendChild(back);
  const inp = back.querySelector("#pq"), res = back.querySelector("#pres");
  let items = [], sel = 0, timer = null, seq = 0;
  const close = () => { back.classList.add("closing"); setTimeout(() => back.remove(), 140); document.removeEventListener("keydown", onKey, true); };
  const draw = () => {
    if (!items.length) { res.innerHTML = `<div class="empty small">${esc(t("Heç nə tapılmadı"))}</div>`; return; }
    let g = null, out = "";
    items.forEach((it, i) => {
      if (it.group !== g) { g = it.group; out += `<div class="palette-group">${esc(g)}</div>`; }
      out += `<div class="palette-item ${i === sel ? "sel" : ""}" data-i="${i}" role="option" aria-selected="${i === sel}"><span class="pi">${icon(it.icon || "arrow", 16)}</span><div class="grow"><b>${esc(it.title)}</b>${it.sub ? `<span>${esc(it.sub)}</span>` : ""}</div>${icon("arrow", 14)}</div>`;
    });
    res.innerHTML = out;
    res.querySelector(".sel")?.scrollIntoView({ block: "nearest" });
  };
  const filterLocal = (q) => { const f = q.toLowerCase(); return [...quick, ...pages].filter((x) => !f || x.title.toLowerCase().includes(f) || (x.sub || "").toLowerCase().includes(f)); };
  const update = () => {
    const q = inp.value.trim();
    items = filterLocal(q).slice(0, q ? 8 : 16);
    sel = 0; draw();
    clearTimeout(timer);
    if (q.length < 2) return;
    const my = ++seq;
    timer = setTimeout(async () => {
      try { const r = await api.get(`/api/search?q=${encodeURIComponent(q)}`); if (my !== seq) return; items = [...filterLocal(q).slice(0, 5), ...r.results]; sel = 0; draw(); } catch { /* ignore */ }
    }, 180);
  };
  const choose = (i) => { const it = items[i]; if (!it) return; close(); go(it.link); };
  const onKey = (e) => {
    if (e.key === "Escape") { e.preventDefault(); close(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(items.length - 1, sel + 1); draw(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(0, sel - 1); draw(); }
    else if (e.key === "Enter") { e.preventDefault(); choose(sel); }
  };
  document.addEventListener("keydown", onKey, true);
  back.addEventListener("click", (e) => { if (e.target === back) close(); const it = e.target.closest("[data-i]"); if (it) choose(+it.dataset.i); });
  inp.addEventListener("input", update);
  update();
  setTimeout(() => inp.focus(), 30);
}
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); palette(); return; }
  const typing = e.target.closest && e.target.closest("input, textarea, select, [contenteditable]");
  if (e.key === "[" && !typing && !e.ctrlKey && !e.metaKey && S.user && !isMobile()) { const app = $("#app"); if (app) setCollapsed(app, !app.classList.contains("sb-collapsed")); }
});

export function setActiveNav(path) {
  let best = null;
  $$(".nav-item").forEach((a) => { const p = a.dataset.path; a.classList.remove("active"); a.removeAttribute("aria-current");
    if (path === p || path.startsWith(p + "/")) { if (!best || p.length > best.dataset.path.length) best = a; } });
  if (best) { best.classList.add("active"); best.setAttribute("aria-current", "page"); }
  let bb = null;
  $$(".bottom-nav a").forEach((a) => { const p = a.dataset.path; a.classList.remove("active"); if (path === p || path.startsWith(p + "/")) { if (!bb || p.length > bb.dataset.path.length) bb = a; } });
  if (bb) bb.classList.add("active");
  return best ? best.dataset.label : "";
}
