import { api, html, raw, mount, on, md, ic, toast, modal, confirmBox, route, go, S, pageHead, badge, infoTip,
  fmtDate, fmtDateTime, fmtTime, fmtDayLong, fmtDayMonth, ago, loading, skelLines, empty, failed, cover, datebox,
  progress, copyText, registerTour, t, $, $$, esc } from "./core.js";
import { HOME, refreshBadges } from "./shell.js";

// News kinds and seeded titles are localized by the server; staff drafts stay in the language they were written in.
// Never compare human-readable kind names — only kind codes.
const KIND_BADGE = { news: "b-navy", event: "b-coral", announcement: "b-amber", opportunity: "b-violet", career: "b-blue", campus: "b-green" };
const kindName = (k) => (S.app.news_kinds || {})[k] || k;
const homeOf = () => HOME[S.user.role] || "/office";
const isStaff = () => ["office", "leader", "admin"].includes(S.user.role);
const AUDIENCE = () => ({ all: t("Hamı"), students: t("Tələbələr"), teachers: t("Müəllimlər") });

// ---------------------------------------------------------------- feed building blocks
function flags(n) {
  return html`${n.important ? html`<span class="badge b-red">${t("Vacib")}</span>` : ""}
    ${n.pinned ? html`<span class="badge b-coral">${ic("pin", 11)} ${t("Sabitlənib")}</span>` : ""}
    ${!n.read ? raw(`<span class="unread-dot" title="${esc(t("Oxunmayıb"))}" aria-hidden="true"></span>`) : ""}
    ${n.saved ? html`<span class="saved-star" title="${t("Yadda saxlanılıb")}">${ic("star", 14)}</span>` : ""}`;
}

function newsCard(n) {
  const full = n.capacity && n.registered_count >= n.capacity;
  return html`<a class="news-card" href="#/news/${n.id}">
    <div class="news-cover">${cover(n.cover, 46)}</div>
    <div class="news-body">
      <div class="row wrap news-tags"><span class="badge ${KIND_BADGE[n.kind] || "b-gray"}">${kindName(n.kind)}</span>${flags(n)}</div>
      <h3>${n.title}</h3><p>${n.summary}</p>
      <div class="news-meta">${n.event_start
        ? html`<span>${ic("calendar", 13)} ${fmtDayMonth(n.event_start)}, ${fmtTime(n.event_start)}</span><span>${ic("pin", 13)} ${n.location}</span>
            ${n.registered ? html`<span class="badge b-green">${ic("check", 11)} ${t("Qeydiyyatdasınız")}</span>`
              : full ? html`<span class="badge b-amber">${t("Yer yoxdur")}</span>` : ""}`
        : html`<span>${ic("clock", 13)} ${ago(n.published_at)}</span>`}</div></div></a>`;
}

function eventRow(n) {
  const full = n.capacity && n.registered_count >= n.capacity;
  return html`<div class="list-item event-row">${datebox(n.event_start)}
    <div class="grow"><a href="#/news/${n.id}"><b class="small">${n.title}</b></a>
      <div class="tiny muted">${fmtTime(n.event_start)} · ${n.location}</div>
      ${n.capacity ? html`<div class="tiny muted">${t("{a} / {b} yer", { a: n.registered_count, b: n.capacity })}</div>` : ""}</div>
    ${n.registration && !n.past ? html`<button class="btn btn-sm ${n.registered ? "" : "btn-accent"}" data-rsvp="${n.id}" ${full && !n.registered ? "disabled" : ""}>
      ${n.registered ? t("Ləğv et") : full ? t("Yer yoxdur") : t("Qeydiyyat")}</button>`
      : n.past ? html`<span class="badge b-gray">${t("Başa çatıb")}</span>` : ""}</div>`;
}

const achievementsBanner = () => html`<a class="ach-banner" href="#/achievements">
  <span class="ach-banner-ic">${ic("trophy", 22)}</span>
  <span class="grow"><b>${t("AzTU-nun nailiyyətləri")}</b><span class="tiny muted">${t("Reytinqlər, elm və tələbə uğurları — rəsmi mənbələrlə.")}</span></span>
  ${ic("arrow", 16)}</a>`;

async function rsvp(id) {
  const r = await api.post(`/api/news/${id}/rsvp`);
  toast(r.registered ? t("Qeydiyyatınız təsdiqləndi. Tədbiri təqviminizə əlavə edə bilərsiniz.") : t("Qeydiyyatınız ləğv edildi."), "ok");
  refreshBadges();
  return r;
}

async function downloadIcs(id) {
  const sid = sessionStorage.getItem("zeka-sid");
  let resp;
  try { resp = await fetch(`/api/news/${id}/ics`, { headers: sid ? { "X-Session": sid } : {}, credentials: "same-origin" }); }
  catch { return toast(t("Serverlə əlaqə yoxdur. İnternet bağlantısını yoxlayın."), "err"); }
  if (!resp.ok) return toast(t("Təqvim faylı yaradılmadı"), "err");
  const url = URL.createObjectURL(await resp.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: `tedbir-${id}.ics` });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  toast(t("Təqvim faylı yükləndi. Outlook və ya Google Calendar-da aça bilərsiniz."), "ok");
}

async function shareLink() {
  const url = location.href;
  if (navigator.share) { try { await navigator.share({ title: document.title, url }); return; } catch { /* user cancelled or unsupported → copy */ } }
  copyText(url);
}

// ---------------------------------------------------------------- feed
route("/news", async (el, p, q) => {
  mount(el, loading());
  const params = new URLSearchParams();
  if (q.kind) params.set("kind", q.kind);
  if (q.saved) params.set("saved", "1");
  if (q.mine) params.set("mine", "1");
  let d;
  try { d = await api.get(`/api/news?${params}`); } catch (err) { mount(el, failed(err.message)); return; }

  const filtered = !!(q.kind || q.saved || q.mine);
  const featured = !filtered ? d.items.find((n) => n.pinned) || d.items[0] : null;
  let term = "";

  const draw = () => {
    const items = d.items.filter((n) => n !== featured
      && (!term || (n.title + " " + n.summary + " " + n.tags.join(" ")).toLowerCase().includes(term)));
    let view;
    if (items.length) view = html`<div class="news-grid">${items.map(newsCard)}</div>`;
    else if (term) view = empty("search", t("Axtarışa uyğun xəbər yoxdur"), t("Başqa açar söz yoxlayın və ya filtri sıfırlayın."), { label: t("Bütün xəbərlər"), go: "/news", cls: "btn" });
    else if (q.saved) view = empty("star", t("Yadda saxladığınız xəbər yoxdur"), t("Xəbəri açıb ulduz düyməsi ilə yadda saxlayın — sonra bu bölmədə görünəcək."), { label: t("Xəbər lentinə keç"), go: "/news", cls: "btn" });
    else if (q.mine) view = empty("calcheck", t("Qeydiyyatlı tədbiriniz yoxdur"), t("Tədbirin səhifəsindən qeydiyyatdan keçin — tədbirlər burada toplanacaq."), { label: t("Tədbirlərə bax"), go: "/news?kind=event", cls: "btn" });
    else view = empty("news", t("Hələ xəbər yoxdur"), t("Yeni elan və tədbirlər dərc olunan kimi burada görünəcək."));
    mount($("#feed", el), view);
  };

  const chip = (code, label, flag) => {
    const active = flag ? q[flag] : code ? q.kind === code : !filtered;
    const target = code ? `/news?kind=${code}` : flag ? `/news?${flag}=1` : "/news";
    return html`<button class="chip ${active ? "on" : ""}" data-go="${target}" aria-pressed="${active}">${label}</button>`;
  };

  mount(el, html`${pageHead(t("Xəbərlər və tədbirlər"),
      t("Universitetin elanları, tədbirləri və fürsətləri."),
      isStaff() ? html`<button class="btn btn-primary" data-go="/staff/news?new=1">${ic("plus", 15)} ${t("Xəbər dərc et")}</button>` : "",
      [[t("Əsas"), homeOf()], [t("Xəbərlər")]],
      { info: t("Təqaüd, mübadilə və karyera fürsətləri “Fürsətlər” filtrindədir. Qeydiyyatdan keçdiyiniz tədbirlər və “Vacib” elanlar barədə bildiriş alacaqsınız.") })}
    ${featured ? html`<a class="news-featured card hover" href="#/news/${featured.id}">
      <div class="nf-cover">${cover(featured.cover, 72, "lg")}</div>
      <div class="nf-body"><div class="row wrap news-tags"><span class="badge ${KIND_BADGE[featured.kind] || "b-gray"}">${kindName(featured.kind)}</span>${flags(featured)}</div>
        <h2>${featured.title}</h2><p>${featured.summary}</p>
        <span class="small muted">${featured.event_start ? html`${ic("calendar", 13)} ${fmtDayLong(featured.event_start)}, ${fmtTime(featured.event_start)}` : ago(featured.published_at)}</span></div></a>` : ""}
    <div class="grid g-12">
      <div class="news-main">
        <div class="news-toolbar row wrap between">
          <div class="chips">${chip("", t("Hamısı"))}${Object.entries(d.kinds).map(([code, label]) => chip(code, label))}
            ${chip("", html`${ic("star", 13)} ${t("Yadda saxlananlar")}`, "saved")}${chip("", html`${ic("calcheck", 13)} ${t("Qeydiyyatlarım")}`, "mine")}</div>
          <div class="news-search"><input class="input" id="nf" placeholder="${t("Xəbərlərdə axtarın…")}" aria-label="${t("Xəbərlərdə axtarış")}"></div>
        </div>
        <div id="feed"></div>
      </div>
      <div class="stack news-side">
        <div class="card"><div class="card-h"><h3>${ic("calendar", 17)} ${t("Yaxınlaşan tədbirlər")}</h3></div>
          <div class="card-b list" id="upc">${d.upcoming.length ? d.upcoming.map(eventRow)
            : empty("calendar", t("Yaxın tədbir yoxdur"), t("Yeni tədbirlər elan olunan kimi burada görünəcək."))}</div></div>
        ${achievementsBanner()}
        <div class="notice info">${ic("bell", 16)}<div>${t("Vacib elanlar və qeydiyyatdan keçdiyiniz tədbirlər barədə bildiriş alacaqsınız.")}</div></div>
        <div class="tiny muted">${ic("info", 12)} ${t("Demo məzmunu — xəbərlər nümunə üçün hazırlanıb.")}</div>
      </div></div>`);
  draw();
  $("#nf", el).addEventListener("input", (e) => { term = e.target.value.trim().toLowerCase(); draw(); });
  on(el, "click", "[data-rsvp]", async (e, b) => {
    e.preventDefault();
    try {
      const r = await rsvp(b.dataset.rsvp);
      const i = d.upcoming.findIndex((x) => x.id === r.id); if (i >= 0) d.upcoming[i] = r;
      const j = d.items.findIndex((x) => x.id === r.id); if (j >= 0) d.items[j] = { ...d.items[j], ...r };
      mount($("#upc", el), html`${d.upcoming.length ? d.upcoming.map(eventRow) : empty("calendar", t("Yaxın tədbir yoxdur"))}`);
      draw();
    } catch (err) { toast(err.message, "err"); }
  });
});

// ---------------------------------------------------------------- detail
route("/news/:id", async (el, p) => {
  mount(el, loading());
  let n;
  try { n = await api.get(`/api/news/${p.id}`); } catch (err) { mount(el, failed(err.message)); return; }
  refreshBadges();

  const draw = () => {
    const full = n.capacity && n.registered_count >= n.capacity;
    const crumb = n.title.length > 42 ? n.title.slice(0, 42) + "…" : n.title;
    mount(el, html`${pageHead("", "", "", [[t("Əsas"), homeOf()], [t("Xəbərlər"), "/news"], [crumb]])}
      <div class="grid g-12">
        <article class="article news-article">
          <div class="na-cover">${cover(n.cover, 80, "lg")}</div>
          <div class="row wrap news-tags mt"><span class="badge ${KIND_BADGE[n.kind] || "b-gray"}">${kindName(n.kind)}</span>
            ${n.important ? html`<span class="badge b-red">${t("Vacib")}</span>` : ""}${n.tags.map((tag) => html`<span class="badge b-gray">#${tag}</span>`)}</div>
          <h1 class="na-title">${n.title}</h1>
          <div class="row wrap small muted na-byline">
            <span>${ic("clock", 13)} ${fmtDateTime(n.published_at)}</span><span>·</span><span>${n.author}</span><span>·</span>
            <span>${ic("eye", 13)} ${t("{n} oxunma", { n: n.reads })}</span>
            <button class="btn btn-sm btn-ghost" id="save">${ic("star", 14)} ${n.saved ? t("Yadda saxlanılıb") : t("Yadda saxla")}</button>
            <button class="btn btn-sm btn-ghost" id="share">${ic("copy", 14)} ${t("Keçidi kopyala")}</button>
            ${isStaff() ? html`<button class="btn btn-sm btn-ghost" data-go="/staff/news">${ic("edit", 14)} ${t("İdarə et")}</button>` : ""}</div>
          <p class="na-lead"><b>${n.summary}</b></p>
          ${n.body ? md(n.body) : html`<p class="muted">${t("Bu xəbər üçün ətraflı mətn əlavə edilməyib.")}</p>`}
        </article>
        <div class="stack news-side">
          ${n.event_start ? html`<div class="card accent event-card"><div class="card-h"><h3>${ic("calendar", 17)} ${t("Tədbir")}</h3>${n.past ? html`<span class="badge b-gray">${t("Başa çatıb")}</span>` : ""}</div>
            <div class="card-b stack">
              <div class="row event-when">${datebox(n.event_start)}<div><b>${fmtDayLong(n.event_start)}</b><div class="small muted">${fmtTime(n.event_start)} – ${fmtTime(n.event_end)}</div></div></div>
              <div class="row small">${ic("pin", 15)} ${n.location}</div>
              ${n.capacity ? html`<div><div class="row between small"><span class="muted">${t("Qeydiyyat")}</span><b>${t("{a} / {b}", { a: n.registered_count, b: n.capacity })}</b></div>
                ${progress((100 * n.registered_count) / n.capacity, "coral", t("Qeydiyyat doluluğu"))}</div>` : ""}
              ${n.registration && !n.past
                ? html`<button class="btn btn-lg ${n.registered ? "" : "btn-accent"} btn-block" id="rsvp" ${full && !n.registered ? "disabled" : ""}>
                    ${n.registered ? html`${ic("check", 16)} ${t("Qeydiyyatdasınız — ləğv et")}` : full ? t("Bütün yerlər tutulub") : html`${ic("calcheck", 16)} ${t("Qeydiyyatdan keç")}`}</button>
                  ${full && !n.registered ? html`<div class="tiny muted center">${t("Bütün yerlər tutulub. Yer boşalarsa, yenidən cəhd edin.")}</div>` : ""}`
                : n.past ? html`<div class="tiny muted center">${t("Tədbir başa çatıb. Qeydiyyat bağlıdır.")}</div>`
                : n.event_start ? html`<div class="tiny muted center">${t("Bu tədbir üçün qeydiyyat tələb olunmur.")}</div>` : ""}
              <button class="btn btn-block" id="ics">${ic("download", 15)} ${t("Təqvimə əlavə et (.ics)")}</button></div></div>` : ""}
          ${n.related.length ? html`<div class="card"><div class="card-h"><h3>${ic("news", 17)} ${t("Oxşar xəbərlər")}</h3></div>
            <div class="card-b list">${n.related.map((r) => html`<a class="list-item click" href="#/news/${r.id}">
              <span class="stat-ic tone-${(r.cover || {}).tone || "navy"}" style="width:34px;height:34px;color:#fff">${ic((r.cover || {}).icon || "news", 16)}</span>
              <div class="grow"><b class="small">${r.title}</b><div class="tiny muted">${ago(r.published_at)}</div></div>${ic("chevron", 14)}</a>`)}</div></div>` : ""}
          ${achievementsBanner()}
        </div></div>`);
  };
  draw();
  on(el, "click", "#rsvp", async () => { try { const r = await rsvp(n.id); n = { ...n, ...r }; draw(); } catch (err) { toast(err.message, "err"); } });
  on(el, "click", "#save", async () => { const r = await api.post(`/api/news/${n.id}/save`); n = { ...n, saved: r.saved }; toast(r.saved ? t("Yadda saxlanıldı") : t("Siyahıdan çıxarıldı"), "ok"); draw(); });
  on(el, "click", "#ics", () => downloadIcs(n.id));
  on(el, "click", "#share", shareLink);
});

// ---------------------------------------------------------------- editor (office / leader / admin)
const TONES = ["navy", "blue", "coral", "green", "amber", "violet", "teal"];
const ICONS = ["news", "calendar", "megaphone", "cap", "cpu", "globe", "briefcase", "award", "book", "shield", "building", "bolt", "target", "flask", "lock", "sparkles"];

route("/staff/news", async (el, p, q) => {
  if (!isStaff()) return go("/news");
  mount(el, loading());
  let d;
  try { d = await api.get("/api/news/manage"); } catch (err) { mount(el, failed(err.message)); return; }
  const canDelete = ["leader", "admin"].includes(S.user.role);
  const aud = AUDIENCE();

  const draw = () => {
    const drafts = d.items.filter((n) => n.status === "draft");
    const live = d.items.filter((n) => n.status === "published");
    const section = (title, list, isDraft) => html`<div class="card"><div class="card-h"><h3>${ic(isDraft ? "edit" : "news", 17)} ${title}</h3><span class="muted small">${t("{n}", { n: list.length })}</span></div>
      <div class="card-b ${list.length ? "no-pad" : ""}">${list.length ? html`<div class="table-wrap"><table class="table"><thead><tr>
        <th>${t("Xəbər")}</th><th>${t("Növ")}</th><th>${t("Auditoriya")}</th><th>${t("Dərc")}</th><th>${t("Oxunma")}</th><th>${t("Qeydiyyat")}</th><th class="right">${t("Əməliyyatlar")}</th></tr></thead><tbody>
        ${list.map((n) => html`<tr><td><div class="row"><span class="stat-ic tone-${(n.cover || {}).tone || "navy"}" style="width:34px;height:34px;color:#fff">${ic((n.cover || {}).icon || "news", 16)}</span>
          <div><b class="small">${n.title}</b><div class="tiny muted">${n.pinned ? html`${ic("pin", 11)} ` : ""}${n.important ? t("Vacib") + " · " : ""}${n.author}</div></div></div></td>
          <td><span class="badge ${KIND_BADGE[n.kind] || "b-gray"}">${kindName(n.kind)}</span></td>
          <td class="small">${aud[n.audience] || n.audience}</td>
          <td class="small nowrap">${isDraft ? badge("draft") : fmtDate(n.published_at)}</td>
          <td>${n.reads}</td>
          <td class="small">${n.registration ? `${n.registered_count}${n.capacity ? " / " + n.capacity : ""}` : "—"}</td>
          <td class="right nowrap"><div class="row wrap" style="justify-content:flex-end;gap:4px">
            <button class="btn btn-sm" data-edit="${n.id}" title="${t("Redaktə et")}">${ic("edit", 14)}</button>
            <a class="btn btn-sm" href="#/news/${n.id}" title="${t("Bax")}">${ic("eye", 14)}</a>
            ${!isDraft ? html`<button class="btn btn-sm" data-unpub="${n.id}" title="${t("Qaralamaya qaytar")}">${ic("eye", 14)} ${t("Gizlət")}</button>` : ""}
            ${canDelete ? html`<button class="btn btn-sm btn-danger" data-del="${n.id}" title="${t("Sil")}">${ic("trash", 14)}</button>` : ""}</div></td></tr>`)}</tbody></table></div>`
        : empty(isDraft ? "edit" : "news", isDraft ? t("Qaralama yoxdur") : t("Dərc olunmuş xəbər yoxdur"),
            isDraft ? t("Yarımçıq xəbərlər qaralama kimi burada saxlanılır.") : t("İlk xəbərinizi dərc edin — auditoriya onu lentdə görəcək."),
            isDraft ? null : { label: t("Yeni xəbər"), id: "empty-new", icon: "plus" })}</div></div>`;
    mount(el, html`${pageHead(t("Xəbərlərin idarə edilməsi"),
        t("Xəbər, elan və tədbirləri yaradın və dərc edin."),
        html`<button class="btn btn-primary" id="new">${ic("plus", 15)} ${t("Yeni xəbər")}</button>`,
        [[t("Əsas"), homeOf()], [t("Xəbərlərin idarə edilməsi")]],
        { info: t("“Vacib” işarəli xəbər dərc olunduqda auditoriyaya bildiriş kimi göndərilir. Qaralama yalnız sizə görünür; dərc etdikdə lentdə görünəcək.") })}
      <div class="stack">${drafts.length ? section(t("Qaralamalar"), drafts, true) : ""}${section(t("Dərc olunmuş xəbərlər"), live, false)}</div>`);
  };
  draw();

  const editor = (n = null) => {
    const v = n
      ? { ...n, icon: (n.cover || {}).icon || "news", tone: (n.cover || {}).tone || "navy", tags: (n.tags || []).join(", "),
          event: !!n.event_start, start: n.event_start ? n.event_start.slice(0, 16) : "",
          duration_h: n.event_start ? Math.round((new Date(n.event_end) - new Date(n.event_start)) / 36e5 * 10) / 10 : 2 }
      : { kind: "announcement", title: "", summary: "", body: "", audience: "students", icon: "megaphone", tone: "navy", tags: "",
          pinned: false, important: false, event: false, start: "", duration_h: 2, location: "", capacity: 100, registration: true };

    const preview = () => html`<div class="news-card preview-card">
      <div class="news-cover">${cover({ icon: v.icon, tone: v.tone }, 40)}</div>
      <div class="news-body"><div class="row wrap news-tags"><span class="badge ${KIND_BADGE[v.kind] || "b-gray"}">${kindName(v.kind)}</span>
        ${v.important ? html`<span class="badge b-red">${t("Vacib")}</span>` : ""}${v.pinned ? html`<span class="badge b-coral">${ic("pin", 11)} ${t("Sabitlənib")}</span>` : ""}</div>
        <h3>${v.title || t("Başlıq")}</h3><p>${v.summary || t("Qısa məzmun")}</p>
        ${v.event && v.start ? html`<div class="news-meta"><span>${ic("calendar", 13)} ${fmtDayMonth(v.start)}, ${fmtTime(v.start)}</span>${v.location ? html`<span>${ic("pin", 13)} ${v.location}</span>` : ""}</div>` : ""}</div></div>
      ${v.body ? html`<div class="preview-body">${md(v.body)}</div>` : ""}`;

    const m = modal({ title: n ? t("Xəbəri redaktə et") : t("Yeni xəbər"), size: "xl",
      body: html`<div class="grid g-12"><form class="form-grid" id="e-form" novalidate>
        <label class="field"><span>${t("Növ")}</span><select class="input" data-v="kind">${Object.entries(d.kinds).map(([code, label]) => html`<option value="${code}" ${v.kind === code ? "selected" : ""}>${label}</option>`)}</select></label>
        <label class="field"><span>${t("Auditoriya")}</span><select class="input" data-v="audience">${[["students", aud.students], ["teachers", aud.teachers], ["all", aud.all]].map(([k, l]) => html`<option value="${k}" ${v.audience === k ? "selected" : ""}>${l}</option>`)}</select></label>
        <label class="field full"><span>${t("Başlıq")}</span><input class="input" data-v="title" value="${v.title}" maxlength="200" placeholder="${t("Məsələn: Robototexnika üzrə açıq seminar")}"></label>
        <label class="field full"><span>${t("Qısa məzmun")}</span><input class="input" data-v="summary" value="${v.summary}" maxlength="400" placeholder="${t("Lentdə görünən bir cümləlik xülasə")}"></label>
        <label class="field full"><span>${t("Mətn")} ${infoTip(t("Markdown dəstəklənir: **qalın**, *maili*, başlıqlar və - ilə siyahı. Sağdakı önizləmədə dərhal görünür."))}</span><textarea class="input" data-v="body" rows="7" placeholder="${t("Məsələn: Seminar barədə ətraflı məlumat, iştirak şərtləri və proqram.")}">${v.body}</textarea></label>
        <div class="field full"><span>${t("Qapaq")}</span><div class="row wrap cover-pick">${TONES.map((tone) => html`<button type="button" class="tone-dot tone-${tone} ${v.tone === tone ? "on" : ""}" data-tone="${tone}" aria-label="${tone}" aria-pressed="${v.tone === tone}"></button>`)}
          <select class="input" data-v="icon" aria-label="${t("İkon")}">${ICONS.map((i) => html`<option ${v.icon === i ? "selected" : ""}>${i}</option>`)}</select></div></div>
        <label class="field full"><span>${t("Teqlər")} <span class="muted">(${t("vergüllə ayırın")})</span></span><input class="input" data-v="tags" value="${v.tags}" placeholder="${t("Məsələn: seminar, robototexnika")}"></label>
        <label class="check-row full"><span class="switch"><input type="checkbox" data-c="important" ${v.important ? "checked" : ""}><span></span></span><div><b class="small">${t("Vacib")}</b><div class="tiny muted">${t("Dərc olunduqda auditoriyaya bildiriş göndərilir")}</div></div></label>
        <label class="check-row full"><span class="switch"><input type="checkbox" data-c="pinned" ${v.pinned ? "checked" : ""}><span></span></span><div><b class="small">${t("Yuxarıda sabitlə")}</b><div class="tiny muted">${t("Xəbər lentin başında görünür")}</div></div></label>
        <label class="check-row full"><span class="switch"><input type="checkbox" data-c="event" ${v.event ? "checked" : ""}><span></span></span><div><b class="small">${t("Bu, tədbirdir")}</b><div class="tiny muted">${t("Tarix, yer və qeydiyyat əlavə olunur")}</div></div></label>
        <label class="field ev"><span>${t("Başlama vaxtı")}</span><input class="input" type="datetime-local" data-v="start" value="${v.start}"></label>
        <label class="field ev"><span>${t("Müddət (saat)")}</span><input class="input" type="number" data-v="duration_h" value="${v.duration_h}" min="0.5" step="0.5"></label>
        <label class="field ev full"><span>${t("Yer")}</span><input class="input" data-v="location" value="${v.location || ""}" placeholder="${t("Məsələn: Baş korpus, akt zalı")}"></label>
        <label class="field ev"><span>${t("Yer sayı")} ${infoTip(t("0 — limitsiz. Yerlər tükəndikdə qeydiyyat bağlanır."))}</span><input class="input" type="number" data-v="capacity" value="${v.capacity || 0}" min="0"></label>
        <label class="check-row ev"><span class="switch"><input type="checkbox" data-c="registration" ${v.registration ? "checked" : ""}><span></span></span><b class="small">${t("Qeydiyyat açıqdır")}</b></label>
      </form>
      <div class="editor-preview"><div class="field-l">${t("Önizləmə")}</div><div id="pvw">${preview()}</div></div></div>`,
      actions: [{ label: t("Ləğv et"), cls: "btn-ghost" },
        { label: t("Qaralama kimi saxla"), onClick: (w, close) => save(true, close) },
        { html: `${ic("send", 15).__html} ${esc(t("Dərc et"))}`, cls: "btn-primary", onClick: (w, close) => save(false, close) }] });
    const w = m.el;
    const sync = () => { $$(".ev", w).forEach((x) => x.classList.toggle("hidden", !v.event)); mount($("#pvw", w), preview()); };
    w.addEventListener("input", (e) => { const k = e.target.dataset.v; if (k) { v[k] = e.target.value; mount($("#pvw", w), preview()); } });
    w.addEventListener("change", (e) => { const k = e.target.dataset.v || e.target.dataset.c; if (!k) return; v[k] = e.target.dataset.c ? e.target.checked : e.target.value; sync(); });
    on(w, "click", "[data-tone]", (e, b) => { v.tone = b.dataset.tone; $$("[data-tone]", w).forEach((x) => { const on_ = x === b; x.classList.toggle("on", on_); x.setAttribute("aria-pressed", String(on_)); }); mount($("#pvw", w), preview()); });
    sync();

    async function save(draft, close) {
      v.title = v.title.trim(); v.summary = v.summary.trim();
      if (v.title.length < 5) { toast(t("Başlıq ən azı 5 simvol olmalıdır"), "err"); return false; }
      if (!v.summary) { toast(t("Qısa məzmunu yazın"), "err"); return false; }
      if (v.event) {
        if (!v.start) { toast(t("Tədbirin başlama vaxtını seçin"), "err"); return false; }
        if (!(v.location || "").trim()) { toast(t("Tədbirin keçiriləcəyi yeri yazın"), "err"); return false; }
      }
      if (!draft) {
        const ok = await confirmBox(t("Xəbəri dərc etmək?"),
          v.important ? t("Xəbər dərc olunacaq və auditoriyaya bildiriş göndəriləcək.") : t("Xəbər dərc olunacaq və auditoriyaya görünəcək."),
          t("Dərc et"));
        if (!ok) return false;
      }
      const body = { kind: v.kind, title: v.title, summary: v.summary, body: v.body, audience: v.audience, icon: v.icon, tone: v.tone,
        tags: v.tags, pinned: v.pinned, important: v.important, draft,
        ...(v.event ? { event_start: v.start, duration_h: v.duration_h, location: v.location, capacity: v.capacity, registration: v.registration } : {}) };
      try {
        const r = n ? await api.put(`/api/news/${n.id}`, body) : await api.post("/api/news", body);
        toast(draft ? t("Qaralama saxlanıldı") : v.important ? t("Dərc olundu və auditoriyaya bildiriş göndərildi") : t("Xəbər dərc olundu"), "ok");
        close();
        if (draft) { d = await api.get("/api/news/manage"); draw(); }
        else go(`/news/${r.id}`);
      } catch (err) { toast(err.message, "err"); return false; }
    }
  };

  on(el, "click", "#new, #empty-new", () => editor());
  on(el, "click", "[data-edit]", (e, b) => editor(d.items.find((x) => x.id === +b.dataset.edit)));
  on(el, "click", "[data-unpub]", async (e, b) => {
    const n = d.items.find((x) => x.id === +b.dataset.unpub); if (!n) return;
    if (!(await confirmBox(t("Xəbəri gizlətmək?"), t("Xəbər qaralamaya qaytarılacaq və auditoriyadan gizlədiləcək. Qeydiyyatlar saxlanılır."), t("Gizlət")))) return;
    try {
      await api.put(`/api/news/${n.id}`, { kind: n.kind, title: n.title, summary: n.summary, body: n.body, audience: n.audience,
        icon: (n.cover || {}).icon, tone: (n.cover || {}).tone, tags: (n.tags || []).join(", "), pinned: n.pinned, important: false, draft: true,
        ...(n.event_start ? { event_start: n.event_start.slice(0, 16), duration_h: Math.round((new Date(n.event_end) - new Date(n.event_start)) / 36e5 * 10) / 10, location: n.location, capacity: n.capacity || 0, registration: n.registration } : {}) });
      toast(t("Xəbər qaralamaya qaytarıldı"), "ok");
      d = await api.get("/api/news/manage"); draw();
    } catch (err) { toast(err.message, "err"); }
  });
  on(el, "click", "[data-del]", async (e, b) => {
    if (!(await confirmBox(t("Xəbəri silmək?"), t("Xəbər, qeydiyyatlar və statistika birdəfəlik silinəcək. Bu əməliyyat geri qaytarılmır."), t("Sil"), true))) return;
    try { await api.del(`/api/news/${b.dataset.del}`); toast(t("Xəbər silindi"), "ok"); d = await api.get("/api/news/manage"); draw(); }
    catch (err) { toast(err.message, "err"); }
  });
  if (q.new) editor();
});

// ---------------------------------------------------------------- page guides
registerTour("news.feed", { route: "/news", title: t("Xəbərlər və tədbirlər"), group: t("Universitet"), icon: "news", steps: [
  { sel: ".news-toolbar .chips", title: t("Filtrlər"), text: t("Xəbərləri növ üzrə süzün, yadda saxladıqlarınıza və qeydiyyatlı tədbirlərinizə baxın.") },
  { sel: ".news-search", title: t("Axtarış"), text: t("Başlıq, məzmun və teqlər üzrə dərhal axtarın.") },
  { sel: "#upc", title: t("Yaxınlaşan tədbirlər"), text: t("Növbəti tədbirlər və qeydiyyat düyməsi bir baxışda buradadır.") },
  { sel: ".ach-banner", title: t("Nailiyyətlər"), text: t("Universitetin rəsmi uğurlarına keçin — reytinqlər, elm və tələbə qələbələri.") },
] });
registerTour("news.detail", { route: "/news/:id", go: "/news/1", title: t("Xəbərin detalları"), group: t("Universitet"), icon: "news", steps: [
  { sel: ".na-byline", title: t("Əməliyyatlar"), text: t("Xəbəri yadda saxlayın və ya keçidini kopyalayın.") },
  { sel: ".na-lead", title: t("Xülasə"), text: t("Qısa məzmun və ardınca tam mətn.") },
  { sel: ".event-card", title: t("Tədbir"), text: t("Tədbir üçün qeydiyyatdan keçin və .ics faylı ilə təqviminizə əlavə edin.") },
] });
registerTour("news.manage", { route: "/staff/news", roles: ["office", "leader", "admin"], title: t("Xəbərlərin idarə edilməsi"), group: t("Kommunikasiya"), icon: "megaphone", steps: [
  { sel: "#new", title: t("Yeni xəbər"), text: t("Xəbər, elan və ya tədbir yaradın. Sağda canlı önizləmə görünür.") },
  { sel: ".table", title: t("Siyahı"), text: t("Qaralama və dərc olunmuş xəbərləri redaktə edin, gizlədin və ya baxın.") },
] });
