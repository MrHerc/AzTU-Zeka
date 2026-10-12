import { S, api, html, raw, mount, on, ic, toast, modal, matchRoute, currentPath, go, route, pageHead, fmtDateTime, openDoc, $, $$, t, tl, LANG,
  loading, empty, failed, infoTip, routeProgress, initMotion, REDUCED, ago, TOURS } from "./core.js";
import { shell, setActiveNav, ROLES, HOME, ROLE_LABEL, refreshBadges, switchLang, setCollapsed, notifIcon } from "./shell.js";
import { LANGS } from "./i18n.js";
import { startTour, tourDone, startPageTour, maybeHint, clearHint, tourCatalog } from "./tour.js";
import "./student.js";
import "./services.js";
import "./news.js";
import "./teacher.js";
import "./academy.js";
import "./staff.js";
import "./guide.js";
import "./support.js";
import "./achievements.js";

document.documentElement.dataset.theme = S.theme;
{ const sk = document.getElementById("skip-link"); if (sk) sk.textContent = t("Əsas məzmuna keç"); }
const AUDIT = new URLSearchParams(location.search).get("audit") === "1";
window.addEventListener("error", (e) => recordError(e.message));
window.addEventListener("unhandledrejection", (e) => recordError((e.reason && e.reason.message) || String(e.reason)));
function recordError(msg) {
  const box = document.getElementById("__errors");
  if (box) box.textContent += msg + "\n";
  if (msg && !/401|Daxil olmamısınız|Not signed in|Вы не вошли/.test(msg)) toast(msg, "err");
}

async function boot() {
  const b = await api.get("/api/bootstrap");
  S.user = b.user;
  S.app = b.app;
  if (S.user && S.user.prefs && S.user.prefs.lang && !localStorage.getItem("zeka-lang") && S.user.prefs.lang !== LANG) { switchLang(S.user.prefs.lang); return; }
  window.addEventListener("hashchange", render);
  window.addEventListener("zeka:tour", (e) => startTour(e.detail && e.detail.force));
  window.addEventListener("zeka:pagetour", () => { if (!startPageTour()) toast(t("Bu səhifə üçün bələdçi hələ hazırlanmayıb")); });
  initMotion();
  render();
}

// ---------------------------------------------------------------- login
function langSwitch(cls = "") {
  return html`<div class="seg lang-seg ${cls}" role="group" aria-label="${t("Dil seçimi")}">${LANGS.map((l) =>
    html`<button class="${l.code === LANG ? "active" : ""}" data-setlang="${l.code}" lang="${l.code}" title="${l.label}" aria-pressed="${l.code === LANG}">${l.short}</button>`)}</div>`;
}
async function loginPage(root) {
  const uni = S.app.university;
  mount(root, html`<div class="login">
    <div class="login-hero">
      <div class="row between"><div class="login-logo"><img src="/static/img/brand/icon.png" alt="${t("AzTU loqosu")}"><div><div class="ll-name">${t("Azərbaycan Texniki Universiteti")}</div>
        <div class="ll-sub">${t("Rəqəmsal Kampus")} · ${uni.platform}</div></div></div>${langSwitch("on-dark")}</div>
      <h1>${t("Universitetin")} <span>${t("süni intellektlə")}</span> ${t("işləyən rəqəmsal kampusu")}</h1>
      <p class="lead">${t("Tədris, qiymətləndirmə, e-xidmətlər və müəllim inkişafı — vahid platformada.")}</p>
      <div class="feats">${[["sparkles", t("Fənn materiallarına əsaslanan AI tutor"), t("Sokratik metod və hər cavabda mənbə")],
         ["grid", t("E-xidmətlər onlayn"), t("Arayışdan akademik məzuniyyətə qədər 13 xidmət")],
         ["calcheck", t("Davamiyyət və qiymətlər"), t("Qayıbların həkim arayışı ilə üzrlü edilməsi")],
         ["cap", t("Müəllimlər üçün AI Akademiya"), t("İngilis dilində tədris, sillabus və rəqəmsal alətlər")]].map(([i, ti, s]) =>
        html`<div class="feat"><span class="fi">${ic(i, 20)}</span><div><b>${ti}</b><span>${s}</span></div></div>`)}</div>
      <div class="login-ach" id="login-ach" aria-live="polite"></div>
      <div class="foot">${t("Demo versiya")} v${S.app.version || "0.3"} · ${t("məlumatlar sintetikdir")} · ${(S.app.contact && S.app.contact.address) || uni.address} · <b>by Safarov Industries</b></div>
    </div>
    <div class="login-side"><div class="login-card">
      <h2>${t("Xoş gəlmisiniz")}</h2><p class="muted" style="margin:6px 0 18px">${t("Demo üçün rol seçin.")} ${infoTip(t("Pilot mərhələsində giriş universitetin vahid hesabı (SSO) ilə olacaq. Demo girişi parolsuzdur və yalnız bu kompüterdə işləyir."))}</p>
      <button class="btn btn-block" disabled title="${t("Pilot mərhələsində aktiv olacaq")}">${ic("lock", 16)} ${t("AzTU hesabı ilə daxil ol (SSO)")}<span class="badge b-gray" style="margin-left:6px">${t("Pilotda")}</span></button>
      <div class="or">${t("demo rolları")}</div>
      <div class="role-grid">${ROLES.map(([k, l, s, i, c], idx) => html`<button class="role-card ${idx === 4 ? "wide" : ""}" data-role="${k}"><span class="ri ${c}">${ic(i, 20)}</span><div><b>${l}</b><span>${s.split(" · ").map((part, j) => html`${j ? " · " : ""}<span class="nw">${part}</span>`)}</span></div>${ic("arrow", 16)}</button>`)}</div>
      <p class="small muted mt">${ic("shield", 13)} ${t("Server yalnız bu kompüterdə (127.0.0.1) işləyir.")}</p>
    </div></div></div>`);
  on(root, "click", "[data-role]", async (e, b) => {
    b.classList.add("loading");
    try {
      const r = await api.post("/api/auth/demo", { role: b.dataset.role });
      sessionStorage.setItem("zeka-sid", r.token);
      S.user = r.user;
      go(r.home);
    } catch (err) { b.classList.remove("loading"); toast(err.message, "err"); }
  });
  try {
    const a = await api.get("/api/achievements");
    const box = $("#login-ach", root);
    if (!box) return;
    const top = a.items.filter((x) => x.featured).slice(0, 3);
    mount(box, html`<div class="la-h">${ic("trophy", 15)} ${t("AzTU-nun son nailiyyətləri")}</div>
      <div class="la-list">${top.map((x) => html`<a class="la-item" href="${x.sources[0].url}" target="_blank" rel="noopener noreferrer"><b>${x.highlight}</b><span>${x.title}</span>${ic("external", 13)}</a>`)}</div>`);
  } catch { /* the strip is optional */ }
}
document.addEventListener("click", (e) => { const b = e.target.closest("[data-setlang]"); if (b) { e.preventDefault(); switchLang(b.dataset.setlang); } });

function consentModal(then) {
  modal({
    title: t("Məlumatlarınızın emalı"), dismissable: false, body: html`<div class="stack">
      <p style="margin:0">${t("AI tutor və kampus köməkçisi suallarınızı emal edir. Davam etmək üçün razılığınızı təsdiqləyin.")}</p>
      <ul class="consent-list">
        <li>${ic("shield", 15)} <span>${t("Şəxsi məlumatlar (FİN, telefon, e-poçt) AI-yə göndərilməzdən əvvəl maskalanır.")}</span></li>
        <li>${ic("lock", 15)} <span>${t("Tələbə məlumatları AI modellərini öyrətmək üçün istifadə edilmir.")}</span></li>
        <li>${ic("eye", 15)} <span>${t("Tibbi sənədləri yalnız dekanlıq görür; müəllim fərdi söhbətlərinizi görmür.")}</span>
          ${infoTip(t("Söhbətlər universitet platformasında 180 gün saxlanılır. Hər sənədə baxış audit jurnalına yazılır."))}</li>
      </ul>
      <label class="check"><input type="checkbox" id="c1"> ${t("Suallarımın fənn materialları əsasında emalına razıyam")}</label>
      <label class="check"><input type="checkbox" id="c2"> ${t("Maskalanmış sualların xarici AI xidmətinə göndərilməsinə razıyam")} <span class="tiny muted">(${t("istəyə görə")})</span></label>
      <span class="tiny muted">${t("Razılığı istənilən vaxt “Profil” bölməsində geri götürə bilərsiniz.")}</span></div>`,
    actions: [{ label: t("Qəbul edirəm"), cls: "btn-primary", onClick: async (w) => {
      if (!w.querySelector("#c1").checked) { toast(t("Davam etmək üçün birinci razılıq tələb olunur"), "err"); return false; }
      const r = await api.post("/api/consent", { ai: true, external: w.querySelector("#c2").checked });
      S.user.consent_at = r.consent_at; toast(t("Razılığınız qeydə alındı"), "ok");
      setTimeout(then, 250);
    } }],
  });
}

// ---------------------------------------------------------------- router outlet with transitions
let renderSeq = 0;
async function render() {
  const root = document.getElementById("root");
  const { path, query } = currentPath();
  if (!S.user) { try { const b = await api.get("/api/bootstrap"); S.user = b.user; S.app = b.app; } catch { S.user = null; } }
  if (!S.user) { root.dataset.shell = ""; return loginPage(root); }
  if (path === "/" || path === "/login") return go(HOME[S.user.role]);
  if (root.dataset.shell !== `${S.user.role}:${S.user.id}:${LANG}`) shell(root);
  const r = matchRoute(path);
  const content = $("#content", root);
  const seq = ++renderSeq;
  if (S.curPath !== path) { S.prevPath = S.curPath || ""; S.curPath = path; }
  const el = document.createElement("main");
  el.className = "page enter";
  el.id = "page";
  el.tabIndex = -1;
  const swap = () => { content.replaceChildren(el); mount(el, loading()); };
  if (document.startViewTransition && !REDUCED && content.firstElementChild) {
    try { await document.startViewTransition(swap).updateCallbackDone; } catch { swap(); }
  } else swap();
  $$(".modal-back, .palette-back").forEach((m) => m.remove());
  clearHint();
  const label = setActiveNav(path);
  document.title = `${label ? label + " · " : ""}${t("AzTU Rəqəmsal Kampus")}`;
  window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
  if (!r) { mount(el, empty("compass", t("Səhifə tapılmadı"), t("Keçid köhnəlmiş ola bilər."), { label: t("Əsas səhifəyə qayıt"), go: HOME[S.user.role], icon: "home" })); return; }
  routeProgress.start();
  try { await r.handler(el, r.params, query); } catch (e) {
    if (seq !== renderSeq) return;
    if (e.status === 403) mount(el, empty("lock", t("Bu səhifəyə giriş icazəniz yoxdur"), e.message, { label: t("Əsas səhifə"), go: HOME[S.user.role], icon: "home" }));
    else if (e.status === 404) mount(el, empty("compass", t("Tapılmadı"), e.message, { label: t("Əsas səhifə"), go: HOME[S.user.role], icon: "home" }));
    else if (e.status !== 401) { mount(el, failed(e.message)); }
  } finally { if (seq === renderSeq) routeProgress.done(); }
  setTimeout(() => el.classList.remove("enter"), 900);
  if (AUDIT) setTimeout(reportOverflow, 1200);
  if (!S.user || seq !== renderSeq || AUDIT) return;
  const pend = sessionStorage.getItem("zeka-start-tour");
  if (pend) { sessionStorage.removeItem("zeka-start-tour"); setTimeout(() => { if (!startPageTour(pend)) toast(t("Bu səhifə üçün bələdçi hələ hazırlanmayıb")); }, 450); return; }
  const tourTime = () => setTimeout(() => startTour(false), 500);
  if (S.user.role === "student" && !S.user.consent_at) { if (!document.querySelector(".modal-back")) consentModal(tourTime); }
  else if (!tourDone(S.user.role) && path === HOME[S.user.role]) tourTime();
  else setTimeout(maybeHint, 1200);
}

// ---------------------------------------------------------------- profile & settings
route("/profile", async (el) => {
  const me = await api.get("/api/me");
  const rows_ = [[t("Ad, soyad"), `${me.full_name} ${me.patronymic || ""}`], [t("Rol"), ROLE_LABEL[me.role]], [t("Vəzifə / ixtisas"), me.title]];
  if (me.role === "student") rows_.push([t("Qrup"), me.group], [t("Tələbə bileti №"), me.student_no], [t("Qəbul ili"), me.admission_year], [t("Təhsilin əsası"), me.funding], [t("Fakültə"), me.faculty.name]);
  if (me.dept) rows_.push([t("Kafedra"), me.dept]);
  const tours = tourCatalog(me.role);
  const done = tours.filter((x) => x.done).length;
  const collapsed = document.getElementById("app")?.classList.contains("sb-collapsed");
  mount(el, html`${pageHead(t("Profil və tənzimləmələr"), t("Şəxsi məlumatlar, görünüş və məxfilik."), "", [[t("Əsas"), HOME[me.role]], [t("Profil")]])}
    <div class="grid g-2">
      <div class="stack">
        <div class="card"><div class="card-h"><h3>${ic("user", 17)} ${t("Şəxsi məlumatlar")}</h3><span class="badge b-gray">${t("Universitet reyestrindən")}</span></div>
          <div class="card-b"><div class="review-grid">${rows_.map(([k, v]) => html`<div>${k}</div><div>${v || "—"}</div>`)}</div>
          <p class="small muted mt">${t("Məlumatlarda səhv varsa, dekanlığa sərbəst ərizə ilə müraciət edin.")} ${me.role === "student" ? html`<a href="#/student/services?new=free_application">${t("Ərizə yaz")}</a>` : ""}</p></div></div>
        <div class="card"><div class="card-h"><h3>${ic("shield", 17)} ${t("Məxfilik")}</h3></div><div class="card-b stack">
          ${me.role === "student" ? html`<div class="notice ${me.consent_at ? "ok" : "warn"}">${ic(me.consent_at ? "check" : "alert", 16)}<div>${me.consent_at ? html`${t("AI emalına razılıq verilib")}: <b>${fmtDateTime(me.consent_at)}</b>` : t("Razılıq verilməyib")}</div></div>` : ""}
          <ul class="consent-list"><li>${ic("shield", 15)} <span>${t("Şəxsi məlumatlar AI xidmətlərinə göndərilməzdən əvvəl maskalanır.")}</span></li>
            <li>${ic("lock", 15)} <span>${t("Tələbə məlumatları ilə AI modeli öyrədilmir.")}</span></li>
            <li>${ic("eye", 15)} <span>${t("Tibbi və sosial sənədlərə yalnız dekanlıq baxa bilər; hər baxış audit jurnalına yazılır.")}</span></li></ul>
          ${me.role === "student" ? html`<button class="btn btn-danger btn-sm" id="revoke" style="align-self:flex-start">${t("Razılığı geri götür")}</button>` : ""}
        </div></div>
      </div>
      <div class="stack">
        <div class="card"><div class="card-h"><h3>${ic("sliders", 17)} ${t("Görünüş və dil")}</h3></div><div class="card-b stack">
          <div class="set-row"><div><b>${t("Interfeys dili")}</b><div class="small muted">${t("Fənn materialları tədris dilində qalır.")}</div></div>${langSwitch()}</div>
          <div class="set-row"><div><b>${t("Tema")}</b><div class="small muted">${t("Açıq və ya tünd görünüş")}</div></div>
            <div class="seg" role="group"><button class="${S.theme !== "dark" ? "active" : ""}" data-theme-set="light">${ic("sun", 14)} ${t("Açıq")}</button><button class="${S.theme === "dark" ? "active" : ""}" data-theme-set="dark">${ic("moon", 14)} ${t("Tünd")}</button></div></div>
          <div class="set-row"><div><b>${t("Sol panel")}</b><div class="small muted">${t("Yığılmış rejimdə yalnız ikonlar görünür. Qısayol: [")}</div></div>
            <div class="seg" role="group"><button class="${!collapsed ? "active" : ""}" data-sb="open">${t("Açıq")}</button><button class="${collapsed ? "active" : ""}" data-sb="collapsed">${t("Yığılmış")}</button></div></div>
        </div></div>
        <div class="card"><div class="card-h"><h3>${ic("compass", 17)} ${t("Bələdçilər")}</h3><span class="badge b-blue">${done} / ${tours.length}</span></div><div class="card-b stack">
          <div class="small muted">${t("Səhifə bələdçilərinin neçəsini keçdiyinizi göstərir.")}</div>
          <div class="progress"><span style="width:${tours.length ? Math.round((100 * done) / tours.length) : 0}%"></span></div>
          <div class="row wrap"><button class="btn btn-sm" id="tour">${ic("play", 15)} ${t("Tanışlıq turunu yenidən başlat")}</button>
            <button class="btn btn-sm" data-go="/guide">${ic("buoy", 15)} ${t("Bələdçi mərkəzi")}</button>
            <button class="btn btn-sm btn-ghost" id="reset-tours">${ic("refresh", 15)} ${t("Bələdçiləri sıfırla")}</button></div></div></div>
      </div></div>`);
  on(el, "click", "#tour", () => { go(HOME[me.role]); setTimeout(() => startTour(true), 700); });
  on(el, "click", "[data-theme-set]", (e, b) => { if ((S.theme === "dark") !== (b.dataset.themeSet === "dark")) document.getElementById("theme")?.click(); $$("[data-theme-set]", el).forEach((x) => x.classList.toggle("active", x === b)); });
  on(el, "click", "[data-sb]", (e, b) => { setCollapsed(null, b.dataset.sb === "collapsed"); $$("[data-sb]", el).forEach((x) => x.classList.toggle("active", x === b)); });
  on(el, "click", "#reset-tours", async () => {
    Object.keys(localStorage).filter((k) => k.startsWith("zeka-tour-") || k.startsWith("zeka-hint-")).forEach((k) => localStorage.removeItem(k));
    S.user.prefs = { ...(S.user.prefs || {}), tours: [] };
    await api.put("/api/me/prefs", { tours: [] });
    toast(t("Bələdçilər sıfırlandı. Səhifələrə daxil olduqda yenidən təklif olunacaq."), "ok");
  });
  on(el, "click", "#revoke", () => modal({ title: t("Razılığın geri götürülməsi"), size: "sm",
    body: html`<p style="margin:0">${t("Demo versiyada razılıq geri götürülmür. Pilot mərhələsində bu əməliyyat AI funksiyalarını söndürəcək və söhbət tarixçənizin silinməsi üçün sorğu yaradacaq.")}</p>`,
    actions: [{ label: t("Aydındır"), cls: "btn-primary" }] }));
});

// ---------------------------------------------------------------- notifications
route("/notifications", async (el, p, q) => {
  const draw = async () => {
    const r = await api.get("/api/notifications");
    const only = q.filter === "unread";
    const items = only ? r.items.filter((n) => !n.read_at) : r.items;
    mount(el, html`${pageHead(t("Bildirişlər"), t("Müraciətlər, testlər, elanlar və dəstək cavabları."), html`<button class="btn" id="all-read" ${r.unread ? "" : "disabled"}>${ic("check", 15)} ${t("Hamısını oxunmuş et")}</button>`, [[t("Əsas"), HOME[S.user.role]], [t("Bildirişlər")]])}
      <div class="tabs"><button class="tab ${only ? "" : "active"}" data-go="/notifications">${t("Hamısı")} <span class="count-pill">${r.items.length}</span></button>
        <button class="tab ${only ? "active" : ""}" data-go="/notifications?filter=unread">${t("Oxunmamış")} <span class="count-pill">${r.unread}</span></button></div>
      <div class="card"><div class="card-b list">${items.length ? items.map((n) => { const [i, c] = notifIcon(n.kind);
        return html`<a class="list-item click notif-row ${n.read_at ? "" : "unread"}" href="#${n.link || "/"}" data-nid="${n.id}"><span class="stat-ic ${c}" style="width:36px;height:36px">${ic(i, 17)}</span>
          <div class="grow"><b>${n.title}</b>${n.body ? html`<div class="small muted">${n.body}</div>` : ""}</div><span class="tiny muted nowrap">${ago(n.created_at)}</span>${n.read_at ? "" : raw('<span class="nd" aria-hidden="true"></span>')}</a>`; })
        : empty("bell", only ? t("Oxunmamış bildiriş yoxdur") : t("Bildiriş yoxdur"), t("Yeni hadisələr olduqda burada görünəcək."))}</div></div>`);
  };
  await draw();
  on(el, "click", "#all-read", async () => { await api.post("/api/notifications/read", { all: true }); refreshBadges(); toast(t("Bütün bildirişlər oxunmuş kimi qeyd edildi"), "ok"); draw(); });
  on(el, "click", "[data-nid]", (e, a) => { api.post("/api/notifications/read", { ids: [+a.dataset.nid] }).then(refreshBadges); });
});

// ---------------------------------------------------------------- audit helpers (automated checks only, ?audit=1)
function reportOverflow() {
  const W = document.documentElement.clientWidth;
  document.documentElement.dataset.vw = String(W);
  const box = document.getElementById("__errors");
  if (!box) return;
  const SCROLLS = ".table-wrap, .tabs, .seg, .chips, pre, .viewer-body";   // these scroll on purpose: their content may be wider
  const edge = (x) => {   // right edge of the box, or of text spilling out of a shrunken box
    const r = x.getBoundingClientRect();
    if (!(x instanceof HTMLElement)) return r.width ? r.right : -Infinity;   // SVG: the box is exact, scrollWidth is not
    if (!r.width && !x.scrollWidth) return -Infinity;
    return Math.max(r.right, getComputedStyle(x).overflowX === "visible" ? r.left + x.scrollWidth : r.right);
  };
  const inScroller = (x) => !!(x.parentElement && x.parentElement.closest(SCROLLS));
  const past = (x, limit) => !inScroller(x) && edge(x) > limit + 1;
  const leaves = (els, limit) => els.filter((x) => past(x, limit) && ![...x.children].some((ch) => past(ch, limit)));   // deepest culprits only
  const label = (x, limit) => `${x.tagName.toLowerCase()}.${[...x.classList].join(".")}(+${Math.round(edge(x) - limit)}px "${(x.textContent || "").trim().replace(/\s+/g, " ").slice(0, 30)}")`;
  if (document.documentElement.scrollWidth > W + 1) {
    const off = leaves($$("body *"), W).slice(0, 6).map((x) => label(x, W));
    box.textContent += `OVERFLOW ${document.documentElement.scrollWidth}px > ${W}px: ${off.join(" ")}\n`;
  }
  const CARDS = ".card, .tool, [class*='-card']";
  const spill = $$(CARDS, document.getElementById("root") || document).flatMap((card) => {
    if (getComputedStyle(card).overflowX !== "visible") return [];
    const right = card.getBoundingClientRect().right;
    return leaves($$("*", card).filter((x) => x.closest(CARDS) === card), right).map((x) => label(x, right));
  }).slice(0, 6);
  if (spill.length) box.textContent += `CARD SPILL: ${spill.join(" ")}\n`;   // content wider than its card overlaps the neighbour
}

// ---------------------------------------------------------------- global handlers
document.addEventListener("click", (e) => {
  const tg = e.target.closest("[data-go]");
  if (tg && !e.defaultPrevented) { e.preventDefault(); go(tg.dataset.go); }
});
document.addEventListener("click", (e) => {
  const a = e.target.closest('a[href^="/doc/"]');
  if (!a || e.defaultPrevented) return;
  e.preventDefault();
  openDoc(a.getAttribute("href").split("/")[2], a.textContent.trim() || t("Sənəd"));
});
document.addEventListener("click", (e) => {
  if (e.target.closest("#retry-page")) { e.preventDefault(); render(); }
  if (e.target.closest("#back-page")) { e.preventDefault(); if (history.length > 1) history.back(); else go(HOME[S.user.role]); }
  if (e.target.closest("[data-page-tour]")) { e.preventDefault(); if (!startPageTour()) toast(t("Bu səhifə üçün bələdçi hələ hazırlanmayıb")); }
});
window.addEventListener("zeka:badges", refreshBadges);
export const _tours = TOURS;
boot().catch((e) => { document.getElementById("root").innerHTML = `<div class="empty"><b>${t("Server ilə əlaqə qurulmadı")}</b><div class="small">${String(e.message).replace(/[<>&]/g, "")}</div><a class="btn mt" href="/">${t("Yenidən cəhd et")}</a></div>`; });
