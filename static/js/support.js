import { S, api, html, raw, mount, on, ic, toast, modal, route, go, pageHead, loading, empty, failed, infoTip, badge, avatar, ago, fmtDateTime, fmtSize,
  fileToB64, openFile, t, $, $$, esc, num, cnt, barChart, lineChart, registerTour, currentPath } from "./core.js";
import { HOME, refreshBadges } from "./shell.js";

let META = null;
const meta = async () => (META ||= await api.get("/api/support/meta"));
const name = (list, key) => (list.find((x) => x.key === key) || { name: key }).name;
const PRIO_CLS = { low: "b-gray", normal: "b-blue", high: "b-amber", urgent: "b-red" };
const DESK = ["office", "admin"];
const EMOJI = ["😞", "😕", "😐", "🙂", "😍"];
const AREA_BY_ROUTE = [[/^\/student\/(tutor|campus)/, "tutor"], [/^\/(student\/services|student\/requests)/, "services"], [/^\/student\/(schedule|attendance)/, "schedule"],
  [/^\/student\/quizzes|^\/teacher\/studio/, "quizzes"], [/^\/news/, "news"], [/^\/teacher\/(academy|tools|syllabus)/, "academy"]];
const areaFor = (path) => (AREA_BY_ROUTE.find(([rx]) => rx.test(path)) || [null, "overall"])[1];
const prioBadge = (m, p) => html`<span class="badge ${PRIO_CLS[p] || "b-gray"}">${name(m.priorities, p)}</span>`;
const sBadge = (m, s) => badge(s, name(m.statuses, s));

// ---------------------------------------------------------------- quick feedback (floating button, help menu)
export async function feedbackModal(area) {
  const m = await meta();
  const path = currentPath().path;
  let score = 0, nps = null;
  modal({
    title: t("Rəyiniz bizim üçün vacibdir"), size: "sm", body: html`<div class="stack">
      <div><div class="small muted mb-sm">${t("Platformadan nə dərəcədə razısınız?")}</div>
        <div class="emoji-scale" role="radiogroup" aria-label="${t("Qiymət")}">${EMOJI.map((e, i) => html`<button type="button" role="radio" aria-checked="false" data-score="${i + 1}" title="${m.score_labels[i]}"><span>${e}</span><small>${m.score_labels[i]}</small></button>`)}</div></div>
      <label class="field"><span>${t("Bölmə")}</span><select class="input" id="fb-area">${m.areas.map((a) => html`<option value="${a.key}" ${a.key === (area || areaFor(path)) ? "selected" : ""}>${a.name}</option>`)}</select></label>
      <label class="field"><span>${t("Şərhiniz")} <span class="muted">(${t("istəyə görə")})</span></span><textarea class="input" id="fb-text" rows="3" maxlength="2000" placeholder="${t("Nə xoşunuza gəldi və ya nəyi yaxşılaşdıraq?")}"></textarea></label>
      <details class="fb-nps"><summary>${t("Platformanı həmkarlarınıza tövsiyə edərdinizmi?")} ${infoTip(t("0 — heç vaxt, 10 — mütləq. Bu, NPS (Net Promoter Score) göstəricisidir."))}</summary>
        <div class="nps-scale mt-sm">${Array.from({ length: 11 }, (_, i) => html`<button type="button" data-nps="${i}">${i}</button>`)}</div></details>
      <div class="tiny muted">${ic("shield", 12)} ${t("Rəy səhifə ünvanı ilə birlikdə anonim statistikaya daxil edilir.")}</div></div>`,
    onMount: (w) => {
      on(w, "click", "[data-score]", (e, b) => { score = +b.dataset.score; $$("[data-score]", w).forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-checked", String(x === b)); }); });
      on(w, "click", "[data-nps]", (e, b) => { nps = +b.dataset.nps; $$("[data-nps]", w).forEach((x) => x.classList.toggle("on", x === b)); });
    },
    actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Göndər"), cls: "btn-primary", onClick: async (w) => {
      if (!score) { toast(t("Əvvəlcə qiymət seçin"), "err"); return false; }
      await api.post("/api/feedback", { score, nps, area: w.querySelector("#fb-area").value, comment: w.querySelector("#fb-text").value, page: path });
      toast(t("Təşəkkür edirik! Rəyiniz qeydə alındı."), "ok");
    } }],
  });
}
window.addEventListener("zeka:feedback", (e) => feedbackModal(e.detail && e.detail.area));

// ---------------------------------------------------------------- support centre
function ticketRow(m, x, base) {
  return html`<a class="list-item click ticket-row" href="#${base}/${x.id}">
    <span class="stat-ic ic-blue" style="width:38px;height:38px">${ic((m.categories.find((c) => c.key === x.category) || {}).icon || "ticket", 17)}</span>
    <div class="grow"><div class="row wrap" style="gap:6px"><b>${x.subject}</b>${x.overdue ? html`<span class="badge b-red">${t("Müddəti keçib")}</span>` : ""}</div>
      <div class="small muted">№ ${x.id} · ${name(m.categories, x.category)} · ${ago(x.updated_at)}${x.messages ? html` · ${ic("message", 12)} ${x.messages}` : ""}</div></div>
    <div class="ticket-meta">${prioBadge(m, x.priority)}${sBadge(m, x.status)}</div></a>`;
}

async function statusCard() {
  try {
    const s = await api.get("/api/system/status");
    return html`<div class="card"><div class="card-h"><h3>${ic("activity", 17)} ${t("Sistemin vəziyyəti")}</h3>${badge(s.overall)}</div>
      <div class="card-b list">${s.components.map((c) => html`<div class="list-item status-row"><span class="sdot s-${c.status}" aria-hidden="true"></span>
        <div class="grow"><b class="small">${c.name}</b><div class="tiny muted">${c.note}</div></div>${badge(c.status)}</div>`)}
      <div class="tiny muted mt-sm">${t("Yoxlanılıb")}: ${fmtDateTime(s.checked_at)}</div></div></div>`;
  } catch { return ""; }
}
async function contactCard() {
  try {
    const c = await api.get("/api/contact");
    return html`<div class="card"><div class="card-h"><h3>${ic("building", 17)} ${t("Universitetlə əlaqə")}</h3></div><div class="card-b stack">
      <a class="contact-line" href="${c.phone_href}">${ic("phone", 15)} ${c.phone}</a>
      <a class="contact-line" href="mailto:${c.email}">${ic("mail", 15)} ${c.email}</a>
      <div class="contact-line">${ic("pin", 15)} ${c.address}</div>
      <a class="btn btn-sm" href="#/contact">${t("Bütün əlaqə vasitələri")} ${ic("arrow", 14)}</a></div></div>`;
  } catch { return ""; }
}

route("/support", async (el, p, q) => {
  const m = await meta();
  const tab = q.tab || (q.from ? "new" : "new");
  const tabs = [["new", t("Yeni sorğu"), "plus"], ["mine", t("Sorğularım"), "ticket"], ["feedback", t("Rəy və təkliflər"), "smile"], ["faq", t("Tez-tez verilən suallar"), "help"]];
  mount(el, html`${pageHead(t("Dəstək xidməti"), t("Sualınızı yazın — cavabı bu səhifədə və bildirişlərdə alacaqsınız."), m.desk ? html`<button class="btn" data-go="/staff/support">${ic("inbox", 15)} ${t("Sorğular növbəsi")}</button>` : "",
      [[t("Əsas"), HOME[S.user.role]], [t("Dəstək")]], { info: t("Sorğular rəqəmsal kampusun dəstək komandasına (İT mərkəzi və dekanlıq) çatır. Cavab müddəti prioritetdən asılıdır: təcili — 4 saat, yüksək — 8 saat, normal — 1 iş günü.") })}
    <div class="tabs" role="tablist">${tabs.map(([k, l, i]) => html`<button class="tab ${tab === k ? "active" : ""}" role="tab" aria-selected="${tab === k}" data-go="/support?tab=${k}">${ic(i, 15)} ${l}</button>`)}</div>
    <div class="grid g-12"><div id="sp-main">${loading()}</div><div class="stack" id="sp-side"></div></div>`);
  const main = $("#sp-main", el);
  Promise.all([statusCard(), contactCard()]).then(([a, b]) => { const side = $("#sp-side", el); if (side) mount(side, html`${a}${b}`); });
  if (tab === "new") {
    let cat = q.category && m.categories.some((c) => c.key === q.category) ? q.category : "", file = null;
    const from = q.from || S.prevPath || "";
    mount(main, html`<form class="card" id="tk-form" novalidate><div class="card-h"><h3>${ic("plus", 17)} ${t("Yeni dəstək sorğusu")}</h3></div><div class="card-b stack">
      <div><div class="field-l">${t("Mövzu nə ilə bağlıdır?")}</div><div class="cat-grid">${m.categories.map((c) => html`<button type="button" class="cat-tile ${cat === c.key ? "on" : ""}" data-cat="${c.key}" aria-pressed="${cat === c.key}">${ic(c.icon, 18)}<span>${c.name}</span></button>`)}</div></div>
      <label class="field"><span>${t("Qısa mövzu")}</span><input class="input" id="tk-subject" maxlength="140" required placeholder="${t("Məsələn: Testin nəticəsi görünmür")}"></label>
      <label class="field"><span>${t("Təsvir")}</span><textarea class="input" id="tk-body" rows="5" maxlength="4000" required placeholder="${t("Nə baş verdi, hansı addımları atdınız və nə gözləyirdiniz?")}"></textarea></label>
      <div class="form-grid">
        <div class="field"><span>${t("Prioritet")} ${infoTip(t("Təcili — işinizi tamamilə dayandıran problem (məsələn, imtahan zamanı). Yüksək — vacib funksiya işləmir. Normal — digər hallar."))}</span>
          <div class="seg" role="radiogroup">${m.priorities.map((x) => html`<button type="button" class="${x.key === "normal" ? "active" : ""}" data-prio="${x.key}" role="radio" aria-checked="${x.key === "normal"}">${x.name}</button>`)}</div></div>
        <div class="field"><span>${t("Əlavə fayl")} <span class="muted">(${t("istəyə görə")})</span></span>
          <label class="file-pick"><input type="file" id="tk-file" accept=".pdf,.png,.jpg,.jpeg" hidden>${ic("clip", 15)} <span id="tk-fname">${t("Ekran şəkli və ya PDF seçin")}</span></label></div></div>
      ${from ? html`<div class="tiny muted">${ic("pin", 12)} ${t("Səhifə")}: <code>${from}</code> ${infoTip(t("Problemi daha tez tapmaq üçün hansı səhifədən yazdığınız sorğuya əlavə olunur."))}</div>` : ""}
      <div class="row between wrap"><span class="tiny muted">${ic("shield", 12)} ${t("Parol və ya FİN kimi məxfi məlumatları yazmayın.")}</span>
        <button class="btn btn-primary" type="submit">${ic("send", 15)} ${t("Sorğunu göndər")}</button></div></div></form>`);
    const f = $("#tk-form", el);
    on(f, "click", "[data-cat]", (e, b) => { cat = b.dataset.cat; $$("[data-cat]", f).forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", String(x === b)); }); });
    on(f, "click", "[data-prio]", (e, b) => { $$("[data-prio]", f).forEach((x) => { x.classList.toggle("active", x === b); x.setAttribute("aria-checked", String(x === b)); }); });
    $("#tk-file", f).addEventListener("change", (e) => { file = e.target.files[0] || null; $("#tk-fname", f).textContent = file ? `${file.name} · ${fmtSize(file.size)}` : t("Ekran şəkli və ya PDF seçin"); });
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = f.querySelector("[type=submit]");
      if (!cat) { toast(t("Mövzunun kateqoriyasını seçin"), "err"); return; }
      btn.disabled = true;
      try {
        let file_id = null;
        if (file) { const up = await api.post("/api/files", { filename: file.name, content_b64: await fileToB64(file), accept: "doc" }); file_id = up.id; }
        const r = await api.post("/api/support/tickets", { category: cat, priority: f.querySelector("[data-prio].active").dataset.prio,
          subject: $("#tk-subject", f).value, body: $("#tk-body", f).value, page: from, file_id });
        mount(main, html`<div class="card success-card"><div class="card-b center stack">
          <div class="success-ic">${ic("check", 30)}</div><h3>${t("Sorğunuz qəbul olundu")}</h3>
          <p class="muted" style="margin:0">${t("Sorğu № {id}. Cavab hazır olduqda bildiriş alacaqsınız.", { id: r.id })}</p>
          <div class="row wrap" style="justify-content:center"><button class="btn btn-primary" data-go="/support/${r.id}">${t("Sorğuya bax")}</button><button class="btn" data-go="/support?tab=mine">${t("Bütün sorğularım")}</button></div></div></div>`);
        refreshBadges();
      } catch (err) { toast(err.message, "err"); btn.disabled = false; }
    });
  } else if (tab === "mine") {
    const list = await api.get("/api/support/tickets");
    mount(main, html`<div class="card"><div class="card-h"><h3>${ic("ticket", 17)} ${t("Sorğularım")}</h3><span class="muted small">${t("{n} sorğu", { n: list.length })}</span></div>
      <div class="card-b list">${list.length ? list.map((x) => ticketRow(m, x, "/support"))
        : empty("ticket", t("Hələ sorğunuz yoxdur"), t("Problemlə qarşılaşsanız, dəstək xidmətinə yazın."), { label: t("Yeni sorğu"), go: "/support?tab=new", icon: "plus" })}</div></div>`);
  } else if (tab === "feedback") {
    mount(main, html`<div class="card"><div class="card-h"><h3>${ic("smile", 17)} ${t("Rəy və təkliflər")}</h3></div><div class="card-b stack">
      <p class="muted" style="margin:0">${t("Rəyiniz platformanı inkişaf etdirməyə kömək edir. Bir dəqiqədən az vaxt aparır.")}</p>
      <div class="emoji-scale big" role="radiogroup" aria-label="${t("Qiymət")}">${EMOJI.map((e, i) => html`<button type="button" role="radio" aria-checked="false" data-quick="${i + 1}"><span>${e}</span><small>${m.score_labels[i]}</small></button>`)}</div>
      <div class="tiny muted">${t("Qiyməti seçdikdən sonra şərh əlavə edə bilərsiniz.")}</div></div></div>`);
    on(main, "click", "[data-quick]", () => feedbackModal());
  } else {
    const g = await api.get("/api/guide");
    mount(main, html`<div class="stack">${g.faq.map((f) => html`<details class="faq"><summary>${f.q}</summary><p>${f.a}</p></details>`)}
      <div class="notice info">${ic("help", 16)}<div>${t("Cavab tapmadınız?")} <a href="#/support?tab=new">${t("Dəstək xidmətinə yazın")}</a>.</div></div></div>`);
  }
});

// ---------------------------------------------------------------- ticket thread (user and desk)
async function ticketPage(el, id, staffView) {
  const m = await meta();
  let tk;
  const draw = () => {
    const base = staffView ? "/staff/support" : "/support";
    mount(el, html`${pageHead(tk.subject, html`№ ${tk.id} · ${name(m.categories, tk.category)} · ${fmtDateTime(tk.created_at)}`,
        html`${prioBadge(m, tk.priority)} ${sBadge(m, tk.status)}`,
        [[t("Əsas"), HOME[S.user.role]], [staffView ? t("Dəstək sorğuları") : t("Dəstək"), staffView ? "/staff/support" : "/support?tab=mine"], [`№ ${tk.id}`]])}
      <div class="grid g-12">
        <div class="card"><div class="card-b">
          <div class="thread">
            <div class="msg me-first"><div class="row" style="gap:8px">${avatar(tk.user, tk.user_color)}<b class="small">${tk.user}</b><span class="tiny muted">${fmtDateTime(tk.created_at)}</span></div>
              <div class="msg-body">${tk.body}</div></div>
            ${tk.thread.map((x) => html`<div class="msg ${x.internal ? "internal" : ""} ${x.author_role === "office" || x.author_role === "admin" ? "staff" : ""}">
              <div class="row" style="gap:8px">${avatar(x.author, x.color)}<b class="small">${x.author}</b>${x.internal ? html`<span class="badge b-amber">${t("Daxili qeyd")}</span>` : ""}<span class="tiny muted">${fmtDateTime(x.created_at)}</span></div>
              ${x.text ? html`<div class="msg-body">${x.text}</div>` : ""}
              ${x.file_id ? html`<button class="attach" data-file="${x.file_id}" data-fname="${x.filename}">${ic("clip", 14)} ${x.filename} <span class="tiny muted">${fmtSize(x.size || 0)}</span></button>` : ""}</div>`)}
          </div>
          ${tk.can_reply ? html`<form class="reply-box" id="reply"><textarea class="input" id="reply-text" rows="3" maxlength="4000" placeholder="${staffView ? t("İstifadəçiyə cavab yazın…") : t("Mesajınızı yazın…")}" aria-label="${t("Mesaj")}"></textarea>
            <div class="row between wrap">${staffView ? html`<div class="row wrap"><label class="check small"><input type="checkbox" id="internal"> ${t("Daxili qeyd")} ${infoTip(t("Daxili qeydi yalnız dəstək komandası görür."))}</label>
                <select class="input input-sm" id="reply-status" aria-label="${t("Cavabdan sonra status")}"><option value="">${t("Status dəyişməsin")}</option><option value="waiting">${name(m.statuses, "waiting")}</option><option value="resolved">${name(m.statuses, "resolved")}</option></select></div>` : html`<span></span>`}
              <button class="btn btn-primary" type="submit">${ic("send", 15)} ${t("Göndər")}</button></div></form>`
            : html`<div class="notice info mt">${ic("info", 16)}<div>${t("Sorğu bağlanıb.")} ${tk.can_reopen ? html`<button class="btn btn-sm" id="reopen">${t("Yenidən aç")}</button>` : ""}</div></div>`}
          ${tk.can_rate ? html`<div class="rate-box"><b>${t("Problem həll olundumu? Xidməti qiymətləndirin:")}</b><div class="stars" role="radiogroup">${[1, 2, 3, 4, 5].map((n) => html`<button type="button" data-rate="${n}" aria-label="${n}">${ic("star", 22)}</button>`)}</div></div>` : ""}
          ${tk.rating ? html`<div class="tiny muted mt">${t("Xidmət qiyməti")}: ${"★".repeat(tk.rating)}${"☆".repeat(5 - tk.rating)}</div>` : ""}
        </div></div>
        <div class="stack">
          <div class="card"><div class="card-h"><h3>${ic("info", 17)} ${t("Məlumat")}</h3></div><div class="card-b"><div class="review-grid">
            <div>${t("Status")}</div><div>${sBadge(m, tk.status)}</div><div>${t("Prioritet")}</div><div>${prioBadge(m, tk.priority)}</div>
            <div>${t("Kateqoriya")}</div><div>${name(m.categories, tk.category)}</div><div>${t("Məsul şəxs")}</div><div>${tk.assignee || "—"}</div>
            <div>${t("Cavab müddəti")}</div><div>${fmtDateTime(tk.due_at)}${tk.overdue ? html` <span class="badge b-red">${t("keçib")}</span>` : ""}</div>
            ${tk.page ? html`<div>${t("Səhifə")}</div><div><a href="#${tk.page}">${tk.page}</a></div>` : ""}</div></div></div>
          ${staffView && tk.can_manage ? html`<div class="card"><div class="card-h"><h3>${ic("sliders", 17)} ${t("İdarəetmə")}</h3></div><div class="card-b stack">
            ${tk.assignee_id !== S.user.id ? html`<button class="btn btn-sm" data-st-assign>${ic("user", 15)} ${t("Özümə götür")}</button>` : ""}
            <label class="field"><span>${t("Status")}</span><select class="input" id="st-status">${m.statuses.map((x) => html`<option value="${x.key}" ${x.key === tk.status ? "selected" : ""}>${x.name}</option>`)}</select></label>
            <label class="field"><span>${t("Prioritet")}</span><select class="input" id="st-prio">${m.priorities.map((x) => html`<option value="${x.key}" ${x.key === tk.priority ? "selected" : ""}>${x.name}</option>`)}</select></label>
            <button class="btn btn-primary btn-sm" id="st-save">${ic("check", 15)} ${t("Yadda saxla")}</button></div></div>` : ""}
          ${!staffView ? html`<div class="notice info">${ic("clock", 16)}<div>${t("Cavab hazır olduqda bildiriş alacaqsınız.")}</div></div>` : ""}
        </div></div>`);
    const th = $(".thread", el); if (th) th.scrollTop = th.scrollHeight;
  };
  tk = await api.get(`/api/support/tickets/${id}`);
  draw();
  on(el, "submit", "#reply", async (e) => {
    e.preventDefault();
    const text = $("#reply-text", el).value.trim();
    if (!text) return;
    const b = e.target.querySelector("[type=submit]"); b.disabled = true;
    try {
      tk = await api.post(`/api/support/tickets/${id}/messages`, { text, internal: !!$("#internal", el)?.checked, status: $("#reply-status", el)?.value || undefined });
      draw(); refreshBadges(); toast(t("Mesaj göndərildi"), "ok");
    } catch (err) { toast(err.message, "err"); b.disabled = false; }
  });
  on(el, "click", "[data-rate]", async (e, b) => { tk = await api.post(`/api/support/tickets/${id}/rate`, { rating: +b.dataset.rate }); draw(); toast(t("Təşəkkür edirik!"), "ok"); });
  on(el, "click", "#reopen", async () => { tk = await api.post(`/api/support/tickets/${id}/reopen`); draw(); toast(t("Sorğu yenidən açıldı"), "ok"); });
  on(el, "click", "[data-st-assign]", async () => { tk = await api.post(`/api/support/tickets/${id}/status`, { assign: "me" }); draw(); });
  on(el, "click", "#st-save", async () => {
    tk = await api.post(`/api/support/tickets/${id}/status`, { status: $("#st-status", el).value, priority: $("#st-prio", el).value });
    draw(); refreshBadges(); toast(t("Dəyişikliklər yadda saxlanıldı"), "ok");
  });
  on(el, "click", "[data-file]", (e, b) => openFile(+b.dataset.file, b.dataset.fname));
}
route("/support/:id", (el, p) => ticketPage(el, p.id, false));
route("/staff/support/:id", (el, p) => { if (!DESK.includes(S.user.role)) return go("/support/" + p.id); return ticketPage(el, p.id, true); });

// ---------------------------------------------------------------- desk queue
route("/staff/support", async (el, p, q) => {
  if (!DESK.includes(S.user.role)) return go("/support");
  const m = await meta();
  const status = q.status || "open";
  const [sum, list] = await Promise.all([api.get("/api/support/summary"),
    api.get(`/api/support/tickets?scope=all&status=${encodeURIComponent(status)}${q.category ? "&category=" + encodeURIComponent(q.category) : ""}${q.mine ? "&mine=1" : ""}${q.q ? "&q=" + encodeURIComponent(q.q) : ""}`)]);
  const qs = (patch) => "/staff/support?" + new URLSearchParams(Object.entries({ status, category: q.category || "", mine: q.mine || "", q: q.q || "", ...patch }).filter(([, v]) => v)).toString();
  mount(el, html`${pageHead(t("Dəstək sorğuları"), t("İstifadəçi sorğularının vahid növbəsi."), html`<button class="btn" data-go="/staff/feedback">${ic("smile", 15)} ${t("Rəylər")}</button>`,
      [[t("Əsas"), HOME[S.user.role]], [t("Dəstək sorğuları")]], { info: t("Sorğular prioritet və yaranma vaxtına görə sıralanır. İlk cavab müddəti: təcili — 4 saat, yüksək — 8 saat, normal — 24 saat, aşağı — 72 saat.") })}
    <div class="grid g-4" id="sp-stats">
      <div class="stat"><span class="stat-ic ic-blue">${ic("inbox", 19)}</span><div><div class="v">${cnt(sum.open)}</div><div class="l">${t("Yeni")}</div></div></div>
      <div class="stat"><span class="stat-ic ic-violet">${ic("refresh", 19)}</span><div><div class="v">${cnt(sum.in_progress + sum.waiting)}</div><div class="l">${t("İcrada və cavab gözləyən")}</div></div></div>
      <div class="stat"><span class="stat-ic ${sum.overdue ? "ic-red" : "ic-green"}">${ic("alert", 19)}</span><div><div class="v">${cnt(sum.overdue)}</div><div class="l">${t("Müddəti keçib")}</div></div></div>
      <div class="stat"><span class="stat-ic ic-amber">${ic("clock", 19)}</span><div><div class="v">${sum.avg_first_response_h == null ? "—" : cnt(sum.avg_first_response_h, { dec: 1, suffix: " " + t("saat") })}</div><div class="l">${t("Orta ilk cavab")}</div></div></div>
    </div>
    <div class="card mt"><div class="card-h wrap">
      <div class="seg" role="tablist">${[["open", t("Açıq")], ["done", t("Bağlı")], ["all", t("Hamısı")]].map(([k, l]) => html`<button class="${status === k ? "active" : ""}" data-go="${qs({ status: k })}">${l}</button>`)}</div>
      <div class="row wrap"><select class="input input-sm" id="f-cat" aria-label="${t("Kateqoriya")}"><option value="">${t("Bütün kateqoriyalar")}</option>${m.categories.map((c) => html`<option value="${c.key}" ${q.category === c.key ? "selected" : ""}>${c.name}</option>`)}</select>
        <label class="check small"><input type="checkbox" id="f-mine" ${q.mine ? "checked" : ""}> ${t("Mənə təyin olunanlar")}</label>
        <input class="input input-sm" id="f-q" placeholder="${t("Axtarış: mövzu, ad, №")}" value="${q.q || ""}" aria-label="${t("Axtarış")}"></div></div>
      <div class="card-b list" id="queue">${list.length ? list.map((x) => html`<a class="list-item click ticket-row" href="#/staff/support/${x.id}">
          <span class="prio-dot p-${x.priority}" title="${name(m.priorities, x.priority)}"></span>${avatar(x.user, x.user_color)}
          <div class="grow"><div class="row wrap" style="gap:6px"><b>${x.subject}</b>${x.overdue ? html`<span class="badge b-red">${t("Müddəti keçib")}</span>` : ""}</div>
            <div class="small muted">№ ${x.id} · ${x.user} · ${name(m.categories, x.category)} · ${ago(x.created_at)}${x.assignee ? html` · ${ic("user", 12)} ${x.assignee}` : ""}</div></div>
          <div class="ticket-meta">${prioBadge(m, x.priority)}${sBadge(m, x.status)}</div></a>`)
        : empty("inbox", t("Bu filtrə uyğun sorğu yoxdur"), t("Filtrləri dəyişin və ya bütün sorğulara baxın."), { label: t("Filtrləri sıfırla"), go: "/staff/support", cls: "btn" })}</div></div>`);
  $("#f-cat", el).addEventListener("change", (e) => go(qs({ category: e.target.value })));
  $("#f-mine", el).addEventListener("change", (e) => go(qs({ mine: e.target.checked ? "1" : "" })));
  let tmr = null;
  $("#f-q", el).addEventListener("input", (e) => { clearTimeout(tmr); tmr = setTimeout(() => go(qs({ q: e.target.value.trim() })), 450); });
});

// ---------------------------------------------------------------- feedback analytics (leadership, desk)
export async function feedbackSummaryCard(link = true) {
  try {
    const f = await api.get("/api/feedback/summary");
    return html`<div class="card"><div class="card-h"><h3>${ic("smile", 17)} ${t("İstifadəçi məmnuniyyəti")}</h3>${link ? html`<a class="small" href="#/staff/feedback">${t("Ətraflı")} ${ic("arrow", 13)}</a>` : ""}</div>
      <div class="card-b"><div class="row wrap" style="gap:22px"><div><div class="big-num">${cnt(f.avg || 0, { dec: 1 })}<span class="muted small"> / 5</span></div><div class="tiny muted">${t("{n} rəy", { n: f.count })}</div></div>
        <div><div class="big-num">${f.nps == null ? "—" : cnt(f.nps, { prefix: f.nps > 0 ? "+" : "" })}</div><div class="tiny muted">NPS</div></div>
        <div class="grow">${f.distribution.slice().reverse().map((n, i) => html`<div class="dist-row"><span>${5 - i}★</span><div class="progress sm"><span style="width:${f.count ? (100 * n) / f.count : 0}%"></span></div><span class="tiny muted">${n}</span></div>`)}</div></div></div></div>`;
  } catch { return ""; }
}

route("/staff/feedback", async (el) => {
  if (!["office", "admin", "leader"].includes(S.user.role)) return go("/support?tab=feedback");
  const [f, s] = await Promise.all([api.get("/api/feedback/summary"), api.get("/api/support/summary")]);
  const weeks = f.weekly.map((w, i) => (i === f.weekly.length - 1 ? t("bu həftə") : t("{n} hft əvvəl", { n: f.weekly.length - 1 - i })));
  mount(el, html`${pageHead(t("Rəylər və məmnuniyyət"), t("İstifadəçi rəyləri, NPS və dəstək keyfiyyəti."), html`<button class="btn" id="csv">${ic("download", 15)} CSV</button>`,
      [[t("Əsas"), HOME[S.user.role]], [t("Rəylər və məmnuniyyət")]], { info: t("Məlumatlar demo üçün sintetikdir. NPS = tövsiyə edənlərin (9–10) faizi çıxılsın tənqid edənlərin (0–6) faizi.") })}
    <div class="grid g-4">
      <div class="stat"><span class="stat-ic ic-amber">${ic("star", 19)}</span><div><div class="v">${cnt(f.avg || 0, { dec: 2 })}</div><div class="l">${t("Orta qiymət (1–5)")}</div></div></div>
      <div class="stat"><span class="stat-ic ic-blue">${ic("users", 19)}</span><div><div class="v">${cnt(f.count)}</div><div class="l">${t("Rəylərin sayı")}</div></div></div>
      <div class="stat"><span class="stat-ic ic-green">${ic("trend", 19)}</span><div><div class="v">${f.nps == null ? "—" : cnt(f.nps, { prefix: f.nps > 0 ? "+" : "" })}</div><div class="l">NPS · ${t("{n} cavab", { n: f.nps_responses })}</div></div></div>
      <div class="stat"><span class="stat-ic ic-violet">${ic("ticket", 19)}</span><div><div class="v">${s.csat == null ? "—" : cnt(s.csat, { dec: 1 })}</div><div class="l">${t("Dəstək xidmətinin qiyməti")}</div></div></div>
    </div>
    <div class="grid g-2 mt">
      <div class="card"><div class="card-h"><h3>${ic("trend", 17)} ${t("Həftəlik orta qiymət")}</h3></div><div class="card-b">${lineChart({ labels: weeks, series: [{ name: t("Orta qiymət"), color: "#2b5aa8", values: f.weekly.map((w) => w.avg || 0) }], max: 5, height: 220 })}</div></div>
      <div class="card"><div class="card-h"><h3>${ic("chart", 17)} ${t("Qiymətlərin bölgüsü")}</h3></div><div class="card-b">${barChart({ labels: f.labels, values: f.distribution, colors: ["#d64045", "#ee7c7e", "#c27803", "#5a9bd3", "#0e9f6e"], height: 220 })}</div></div>
    </div>
    <div class="grid g-12 mt">
      <div class="card"><div class="card-h"><h3>${ic("message", 17)} ${t("Son şərhlər")}</h3></div><div class="card-b list">${f.recent.length ? f.recent.map((r) => html`<div class="list-item"><span class="emoji-sm" aria-hidden="true">${EMOJI[r.score - 1]}</span>
        <div class="grow"><div class="small">${r.comment}</div><div class="tiny muted">${r.area_name} · ${ago(r.created_at)}</div></div></div>`) : empty("message", t("Şərh yoxdur"))}</div></div>
      <div class="card"><div class="card-h"><h3>${ic("layers", 17)} ${t("Bölmələr üzrə")}</h3></div><div class="card-b list">${f.by_area.map((a) => html`<div class="list-item"><div class="grow"><b class="small">${a.name}</b>
        <div class="progress sm mt-sm"><span style="width:${(a.avg / 5) * 100}%"></span></div></div><span class="small bold">${num(a.avg, 1)}</span><span class="tiny muted">(${a.n})</span></div>`)}</div></div>
    </div>`);
  on(el, "click", "#csv", () => {
    const rows = [["area", "score", "comment", "created_at"], ...f.recent.map((r) => [r.area, r.score, (r.comment || "").replace(/"/g, '""'), r.created_at])];
    const csv = rows.map((r) => r.map((x) => `"${x}"`).join(",")).join("\n");
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob(["\ufeff" + csv], { type: "text/csv" })); a.download = "zeka-feedback.csv"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  });
});

// ---------------------------------------------------------------- page guides
registerTour("support", { route: "/support", title: t("Dəstək xidməti"), group: t("Kömək"), icon: "ticket", steps: [
  { sel: ".tabs", title: t("Bölmələr"), text: t("Yeni sorğu yaradın, əvvəlki sorğularınıza baxın, rəy bildirin və ya tez-tez verilən suallara baxın.") },
  { sel: ".cat-grid", title: t("Kateqoriya"), text: t("Mövzunu seçin — sorğu birbaşa uyğun mütəxəssisə çatır.") },
  { sel: "#tk-body", title: t("Təsvir"), text: t("Nə baş verdiyini və hansı addımları atdığınızı yazın. Ekran şəkli əlavə etmək problemi tez həll etməyə kömək edir.") },
  { sel: "#sp-side", title: t("Sistemin vəziyyəti"), text: t("Problem ümumidirsə, burada görünəcək. Universitetin rəsmi əlaqə məlumatları da buradadır.") },
] });
registerTour("staff.support", { route: "/staff/support", roles: ["office", "admin"], title: t("Dəstək sorğuları"), group: t("Dəstək"), icon: "inbox", steps: [
  { sel: "#sp-stats", title: t("Göstəricilər"), text: t("Yeni, icrada olan və müddəti keçmiş sorğular, həmçinin orta ilk cavab müddəti.") },
  { sel: ".card-h .seg", title: t("Filtrlər"), text: t("Açıq və bağlı sorğular, kateqoriya və sizə təyin olunanlar üzrə süzgəc.") },
  { sel: "#queue", title: t("Növbə"), text: t("Sorğunu açın, cavab yazın, statusu dəyişin. Daxili qeydləri istifadəçi görmür.") },
] });
registerTour("staff.feedback", { route: "/staff/feedback", roles: ["office", "admin", "leader"], title: t("Rəylər və məmnuniyyət"), group: t("Analitika"), icon: "smile", steps: [
  { sel: ".grid.g-4", title: t("Əsas göstəricilər"), text: t("Orta qiymət, rəylərin sayı, NPS və dəstək xidmətinin qiyməti.") },
  { sel: ".chart", title: t("Dinamika"), text: t("Həftəlik orta qiymət — dəyişikliklərin təsirini izləyin.") },
  { sel: "#csv", title: t("İxrac"), text: t("Şərhləri CSV formatında yükləyib hesabatlarda istifadə edin.") },
] });
