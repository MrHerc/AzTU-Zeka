import { api, html, raw, mount, on, md, ic, toast, modal, route, go, S, pageHead, badge, fmtDate, fmtDateTime, ago, loading, skelLines, spinner, empty, failed,
  infoTip, avatar, fmtSize, fileToB64, openFile, openDoc, confirmBox, cnt, num, registerTour, t, $, $$, esc } from "./core.js";
import { stat } from "./student.js";
import { refreshBadges } from "./shell.js";

const STAFF = ["office", "admin", "leader"];
const DESK = ["office", "admin"];
let SVC = null;
async function services() { if (!SVC) SVC = await api.get("/api/services"); return SVC; }
const catOf = (key) => (SVC && SVC.categories.find((c) => c.key === key)) || {};
const fmtD = (s) => (s ? fmtDate(s) : "—");
const slaLabel = (h) => (h <= 24 ? t("1 iş günü") : t("{n} iş günü", { n: Math.round(h / 24) }));
const crumbsS = (...c) => [[t("Əsas"), "/student"], ...c];
const crumbsO = (...c) => [[t("Dekanlıq"), "/office"], ...c];

// ---------------------------------------------------------------- catalogue
route("/student/services", async (el, p, q) => {
  if (q.new) return go(`/student/apply/${q.new}${q.from ? `?from=${q.from}&to=${q.to || q.from}` : ""}`);
  mount(el, loading());
  let s;
  try { s = await services(); } catch (e) { return mount(el, failed(e.message)); }
  const draw = (f = "") => {
    const ff = f.trim().toLowerCase();
    const match = (x) => !ff || (x.name + " " + x.description).toLowerCase().includes(ff);
    const popular = s.types.filter((x) => x.popular);
    return html`${!ff && popular.length ? html`<div class="card brand-border mb" data-tour="svc-popular"><div class="card-h"><h3>${ic("star", 17)} ${t("Ən çox istifadə olunan")}</h3></div>
        <div class="card-b grid g-3">${popular.map((x) => svcCard(x))}</div></div>` : ""}
      ${s.categories.map((c) => { const ts = s.types.filter((x) => x.category === c.key && match(x)); return ts.length ? html`<section class="mb svc-sec">
        <div class="row mb-sm"><span class="stat-ic svc-cat-ic" style="--c:${c.color}">${ic(c.icon, 17)}</span><div><b>${c.name}</b><div class="tiny muted">${c.text}</div></div></div>
        <div class="grid g-3">${ts.map((x) => svcCard(x))}</div></section>` : ""; })}
      ${s.types.some(match) ? "" : empty("search", t("Uyğun xidmət tapılmadı"), t("Axtarışı dəyişin və ya sərbəst ərizə ilə müraciət edin."), { label: t("Sərbəst ərizə"), go: "/student/apply/free_application", icon: "edit", cls: "btn" })}`;
  };
  mount(el, html`${pageHead(t("E-xidmətlər"), t("Bütün müraciətlər onlayn — kağız ərizə və növbə olmadan."),
      html`<button class="btn" data-go="/student/requests">${ic("inbox", 15)} ${t("Müraciətlərim")}</button>`, crumbsS([t("E-xidmətlər")]),
      { info: t("Müraciətin statusunu “Müraciətlərim” bölməsində izləyin. Hazır sənədlər QR kod və doğrulama kodu ilə verilir.") })}
    <div class="row mb"><div class="search-field"><span class="sfi">${ic("search", 16)}</span>
      <input class="input" id="sf" placeholder="${t("Məsələn: arayış, qayıb, yataqxana")}" aria-label="${t("Xidmət axtarın")}"></div></div>
    <div id="cat">${draw()}</div>`);
  $("#sf", el).addEventListener("input", (e) => mount($("#cat", el), draw(e.target.value)));
});

function svcCard(x) {
  const c = catOf(x.category);
  return html`<button class="svc" data-go="/student/apply/${x.code}"><span class="si" style="--c:${c.color}">${ic(x.icon, 20)}</span>
    <b>${x.name}</b><span>${x.description}</span>
    <div class="row wrap tiny muted svc-meta">${ic("clock", 12)} ${slaLabel(x.sla_hours)}
      ${x.document ? html`<span class="badge b-green">${ic("qr", 11)} ${t("QR sənəd")}</span>` : ""}
      ${x.attachments && x.attachments.required ? html`<span class="badge b-amber">${ic("clip", 11)} ${t("sənəd tələb olunur")}</span>` : ""}</div></button>`;
}

// ---------------------------------------------------------------- apply wizard
route("/student/apply/:code", async (el, p, q) => {
  mount(el, loading());
  let s;
  try { s = await services(); } catch (e) { return mount(el, failed(e.message)); }
  const rt = s.types.find((x) => x.code === p.code);
  if (!rt) return mount(el, html`${pageHead(t("E-xidmətlər"), "", "", crumbsS([t("E-xidmətlər"), "/student/services"], [t("Xidmət")]))}
    ${empty("alert", t("Xidmət tapılmadı"), t("Bu xidmət mövcud deyil və ya adı dəyişib."), { label: t("Bütün xidmətlər"), go: "/student/services", icon: "grid", cls: "btn" })}`);
  let courses = [];
  if (rt.fields.some((f) => f.type === "course" || f.type === "courses")) {
    try { courses = await api.get("/api/courses"); } catch { courses = []; }
  }
  const c = catOf(rt.category);
  const data = {};
  rt.fields.forEach((f) => {
    if (f.type === "select") data[f.name] = f.options[0];
    if (f.type === "daterange") data[f.name] = q.from ? { from: q.from, to: q.to || q.from } : { from: "", to: "" };
    if (f.type === "courses" || f.type === "absences") data[f.name] = [];
  });
  const files = [];
  let step = 1, absences = [], absKey = "";
  const result = { id: null };
  // show_if values arrive localized from the server; compare value-to-value, never against a hard-coded label.
  const visible = (f) => !f.show_if || Object.entries(f.show_if).every(([k, v]) => data[k] === v);

  function fieldHtml(f) {
    if (!visible(f)) return "";
    const id = `f_${f.name}`, v = data[f.name];
    const req = f.required ? raw(' <span class="req" aria-hidden="true">*</span>') : "";
    const lab = html`<label class="label" for="${id}">${f.label}${req}</label>`;
    const hint = f.hint ? html`<span class="hint">${f.hint}</span>` : "";
    switch (f.type) {
      case "radio": return html`<div class="field full"><span class="label">${f.label}${req}</span>
        <div class="radio-cards" role="radiogroup" aria-label="${f.label}">${f.options.map((o) => html`<button type="button" class="radio-card ${v === o ? "on" : ""}" data-radio="${f.name}" data-val="${esc(o)}" role="radio" aria-checked="${v === o}"><span class="rd" aria-hidden="true"></span>${o}</button>`)}</div>${hint}</div>`;
      case "select": return html`<div class="field">${lab}<select class="select" id="${id}" data-f="${f.name}">${f.options.map((o) => html`<option ${o === v ? "selected" : ""}>${o}</option>`)}</select>${hint}</div>`;
      case "textarea": return html`<div class="field full">${lab}<textarea class="textarea" id="${id}" data-f="${f.name}" rows="4" placeholder="${f.placeholder || ""}">${v || ""}</textarea>${hint}</div>`;
      case "number": return html`<div class="field">${lab}<input class="input" type="number" id="${id}" data-f="${f.name}" value="${v || ""}" min="${f.min ?? ""}" max="${f.max ?? ""}">${hint}</div>`;
      case "date": return html`<div class="field">${lab}<input class="input" type="date" id="${id}" data-f="${f.name}" value="${v || ""}">${hint}</div>`;
      case "daterange": return html`<div class="field full"><span class="label">${f.label}${req}</span>
        <div class="row wrap daterange"><input class="input" type="date" data-range="${f.name}" data-part="from" value="${(v && v.from) || ""}" aria-label="${t("Başlanğıc tarix")}">
          <span class="muted" aria-hidden="true">—</span><input class="input" type="date" data-range="${f.name}" data-part="to" value="${(v && v.to) || ""}" aria-label="${t("Son tarix")}"></div>
        <span class="hint">${f.future ? t("Yalnız gələcək tarixlər seçilə bilər.") : t("Keçmiş tarixlər — buraxılmış dərslər üçün.")}</span></div>`;
      case "course": return html`<div class="field">${lab}<select class="select" id="${id}" data-f="${f.name}"><option value="">${t("— seçin —")}</option>${courses.map((co) => html`<option value="${co.id}" ${+v === co.id ? "selected" : ""}>${co.name}</option>`)}</select>${hint}</div>`;
      case "courses": return html`<div class="field full"><span class="label">${f.label}${req}</span>
        <div class="chips">${courses.length ? courses.map((co) => html`<button type="button" class="chip ${v.includes(co.id) ? "on" : ""}" data-multi="${f.name}" data-val="${co.id}" aria-pressed="${v.includes(co.id)}">${co.name}</button>`)
          : html`<span class="small muted">${t("Qeydiyyatda fənn yoxdur.")}</span>`}</div></div>`;
      case "absences": return html`<div class="field full"><span class="label">${f.label}${req}</span><div id="abs-box">${absBox(f)}</div></div>`;
      default: return html`<div class="field ${f.name === "org" || f.name === "purpose_other" ? "full" : ""}">${lab}<input class="input" id="${id}" data-f="${f.name}" value="${v || ""}" placeholder="${f.placeholder || ""}">${hint}</div>`;
    }
  }
  function absBox(f) {
    const per = data.period || {};
    if (!per.from || !per.to) return html`<div class="notice info">${ic("info", 16)}<div>${t("Əvvəlcə dövrü seçin — həmin dövrdəki qayıblarınız burada görünəcək.")}</div></div>`;
    if (!absences.length) return html`<div class="notice warn">${ic("alert", 16)}<div>${t("Seçilmiş dövrdə üzrlü edilməmiş qayıb tapılmadı.")}</div></div>`;
    return html`<div class="list abs-list">${absences.map((a) => html`<label class="list-item check abs-item"><input type="checkbox" data-abs="${a.lesson_id}" ${data[f.name].includes(a.lesson_id) ? "checked" : ""}>
      <span class="dot" style="background:${a.color};box-shadow:none"></span><div class="grow"><b class="small">${a.course}</b><div class="tiny muted">${fmtDate(a.day)} · ${a.start}–${a.end} · ${a.kind}</div></div>${badge("absent")}</label>`)}</div>
      <div class="tiny muted mt-sm">${t("{a} / {b} dərs seçilib", { a: data[f.name].length, b: absences.length })}</div>`;
  }
  async function loadAbsences() {
    const per = data.period || {};
    const key = `${per.from}|${per.to}`;
    if (!rt.fields.some((f) => f.type === "absences") || key === absKey) return;
    absKey = key;
    try { absences = per.from && per.to ? await api.get(`/api/me/absences?from=${per.from}&to=${per.to}`) : []; }
    catch { absences = []; }
    data.absences = absences.map((a) => a.lesson_id);
    const box = $("#abs-box", el);
    if (box) mount(box, absBox(rt.fields.find((f) => f.type === "absences")));
  }
  function filesHtml() {
    const a = rt.attachments;
    if (!a) return "";
    return html`<div class="field full"><span class="label">${a.label}${a.required ? raw(' <span class="req" aria-hidden="true">*</span>') : ""}</span>
      <label class="dropzone" id="dz"><input type="file" id="file" ${a.accept === "image" ? 'accept="image/png,image/jpeg"' : 'accept=".pdf,.jpg,.jpeg,.png,.docx"'} multiple hidden>
        <span class="dz-ic">${ic("upload", 26)}</span><b>${t("Faylı seçin və ya bura atın")}</b>
        <div class="tiny muted mt-sm">${a.accept === "image" ? t("JPG və ya PNG") : t("PDF, JPG, PNG və ya DOCX")} · ${t("maks. 10 MB")} · ${t("ən çox {n} fayl", { n: a.max })}</div></label>
      <div class="file-list">${files.map((f, i) => html`<div class="file-row"><span class="fi ${f.mime.startsWith("image/") ? "img" : ""}">${f.mime.startsWith("image/") ? "IMG" : f.mime.includes("pdf") ? "PDF" : "DOC"}</span>
        <div class="grow"><b class="small ellipsis" style="display:block">${f.filename}</b><span class="tiny muted">${fmtSize(f.size)} · ${t("yükləndi")}</span></div>
        <button type="button" class="btn btn-ghost btn-icon" data-rmfile="${i}" aria-label="${t("Faylı sil")}">${ic("x", 15)}</button></div>`)}</div></div>`;
  }
  const side = () => html`<div class="card svc-side" data-tour="apply-side"><div class="card-h"><h3>${ic("info", 17)} ${t("Xidmət haqqında")}</h3></div><div class="card-b stack">
    <div class="small">${rt.description}</div>
    ${rt.needs.length ? html`<div><div class="label mb-sm">${t("Lazım olanlar")}</div>${rt.needs.map((n) => html`<div class="small needs-row">${ic("check", 13)} ${n}</div>`)}</div>` : ""}
    <div><div class="label mb-sm">${t("Mərhələlər")}</div><div class="timeline">${rt.steps.map((s_) => html`<div class="tl-item wait"><span class="small">${s_}</span></div>`)}</div></div>
    <div class="notice ok">${ic("check", 16)}<div><b>${t("Nəticə")}:</b> ${rt.outcome}</div></div>
    <div class="row small muted">${ic("clock", 14)} ${t("İcra müddəti")}: <b>${slaLabel(rt.sla_hours)}</b></div>
    ${rt.privacy ? html`<div class="notice info">${ic("shield", 16)}<div>${rt.privacy}</div></div>` : ""}</div></div>`;

  function reviewHtml() {
    const rows_ = [];
    rt.fields.filter(visible).forEach((f) => {
      let v = data[f.name];
      if (v == null || v === "" || (Array.isArray(v) && !v.length)) return;
      if (f.type === "daterange") v = v.from ? `${fmtD(v.from)} – ${fmtD(v.to)}` : "";
      else if (f.type === "date") v = fmtD(v);
      else if (f.type === "course") v = (courses.find((co) => co.id === +v) || {}).name;
      else if (f.type === "courses") v = v.map((id) => (courses.find((co) => co.id === id) || {}).name).join(", ");
      else if (f.type === "absences") v = absences.filter((a) => v.includes(a.lesson_id)).map((a) => `${fmtDate(a.day)} ${a.start} · ${a.course}`).join("\n");
      if (v) rows_.push([f.label, v]);
    });
    if (rt.attachments) rows_.push([rt.attachments.label, files.map((f) => f.filename).join(", ") || "—"]);
    return html`<div class="review-grid">${rows_.map(([k, v]) => html`<div>${k}</div><div style="white-space:pre-line">${v}</div>`)}</div>
      <label class="check mt confirm-row"><input type="checkbox" id="confirm"> <span>${t("Göstərdiyim məlumatların düzgün olduğunu təsdiq edirəm.")}</span></label>`;
  }
  function draw() {
    const names = [t("Məlumatlar"), t("Yoxlama"), t("Göndərildi")];
    const stepper = html`<ol class="stepper" data-tour="apply-stepper" aria-label="${t("Müraciət mərhələləri")}">${names.map((n, i) => html`<li class="sp ${step === i + 1 ? "on" : step > i + 1 ? "done" : ""}" aria-current="${step === i + 1 ? "step" : "false"}">
      <span class="sn">${step > i + 1 ? raw(ic("check", 14).__html) : i + 1}</span><span class="sl">${n}</span></li>`)}</ol>`;
    mount(el, html`${pageHead(rt.name, c.name, "", crumbsS([t("E-xidmətlər"), "/student/services"], [rt.name]))}
      <div class="grid g-12"><div class="card"><div class="card-b">${stepper}
        ${step === 1 ? html`<form class="form-grid" id="w-form" novalidate>${rt.fields.map(fieldHtml)}${filesHtml()}</form>
          <div class="row between mt wrap"><button class="btn" data-go="/student/services">${ic("back", 15)} ${t("Xidmətlər")}</button><button class="btn btn-primary" id="to-review">${t("Davam et")} ${ic("chevron", 15)}</button></div>`
        : step === 2 ? html`<div class="small muted mb">${t("Göndərməzdən əvvəl məlumatları yoxlayın.")}</div>${reviewHtml()}
          <div class="row between mt wrap"><button class="btn" id="back1">${ic("back", 15)} ${t("Düzəliş et")}</button><button class="btn btn-accent" id="submit">${ic("send", 15)} ${t("Müraciəti göndər")}</button></div>`
        : html`<div class="success-card center"><div class="success-ic">${ic("check", 30)}</div>
            <h3>${t("Müraciətiniz göndərildi")}</h3>
            <p class="muted">${t("Müraciət № {id}. Təxmini icra müddəti: {sla}. Status dəyişdikdə bildiriş alacaqsınız.", { id: result.id, sla: slaLabel(rt.sla_hours) })}</p>
            <div class="success-steps">${(rt.steps || []).slice(0, 1).map((s_) => html`<div class="tiny muted">${ic("arrow", 12)} ${t("Növbəti addım")}: ${s_}</div>`)}</div>
            <div class="row wrap success-actions"><button class="btn btn-primary" data-go="/student/requests/${result.id}">${ic("eye", 15)} ${t("Müraciətə bax")}</button>
              <button class="btn" data-go="/student/services">${t("Yeni müraciət")}</button></div></div>`}
      </div></div>${side()}</div>`);
  }
  function validateLocal() {
    for (const f of rt.fields) {
      if (!f.required || !visible(f)) continue;
      const v = data[f.name];
      const emptyV = v == null || v === "" || (Array.isArray(v) && !v.length) || (f.type === "daterange" && (!v.from || !v.to));
      if (emptyV) {
        toast(t("“{label}” sahəsini doldurun.", { label: f.label }), "err");
        const n = el.querySelector(`[data-f="${f.name}"], [data-radio="${f.name}"], [data-range="${f.name}"]`); n && n.focus();
        return false;
      }
    }
    if (rt.attachments && rt.attachments.required && !files.length) { toast(t("“{label}” yüklənməlidir.", { label: rt.attachments.label }), "err"); return false; }
    return true;
  }
  on(el, "click", "[data-radio]", (e, b) => { data[b.dataset.radio] = b.dataset.val; draw(); });
  on(el, "click", "[data-multi]", (e, b) => { const arr = data[b.dataset.multi]; const v = +b.dataset.val; const i = arr.indexOf(v); i >= 0 ? arr.splice(i, 1) : arr.push(v); b.classList.toggle("on"); b.setAttribute("aria-pressed", String(i < 0)); });
  on(el, "change", "[data-f]", (e, n) => { data[n.dataset.f] = n.value; if (rt.fields.some((f) => f.show_if)) draw(); });
  on(el, "input", "[data-f]", (e, n) => { data[n.dataset.f] = n.value; });
  on(el, "change", "[data-range]", (e, n) => { data[n.dataset.range][n.dataset.part] = n.value; loadAbsences(); });
  on(el, "change", "[data-abs]", (e, n) => { const id = +n.dataset.abs; const arr = data.absences; const i = arr.indexOf(id); n.checked ? (i < 0 && arr.push(id)) : (i >= 0 && arr.splice(i, 1));
    const box = $("#abs-box", el); if (box) mount(box, absBox(rt.fields.find((f) => f.type === "absences"))); });
  on(el, "click", "[data-rmfile]", (e, b) => { files.splice(+b.dataset.rmfile, 1); draw(); });
  on(el, "click", "#to-review", () => { if (validateLocal()) { step = 2; draw(); window.scrollTo(0, 0); } });
  on(el, "click", "#back1", () => { step = 1; draw(); loadAbsences(); });
  on(el, "click", "#submit", async (e, b) => {
    if (!$("#confirm", el).checked) return toast(t("Məlumatların düzgünlüyünü təsdiq edin."), "err");
    b.disabled = true;
    try {
      const r = await api.post("/api/requests", { type_code: rt.code, data, files: files.map((f) => f.id) });
      result.id = r.id; step = 3; draw(); refreshBadges();
    } catch (err) { toast(err.message, "err"); b.disabled = false; }
  });
  async function upload(list) {
    for (const f of list) {
      if (files.length >= (rt.attachments.max || 3)) { toast(t("Ən çox {n} fayl əlavə etmək olar.", { n: rt.attachments.max }), "err"); break; }
      if (f.size > 10 * 1024 * 1024) { toast(t("{name}: fayl 10 MB-dan böyükdür.", { name: f.name }), "err"); continue; }
      try { const r = await api.post("/api/files", { filename: f.name, content_b64: await fileToB64(f), accept: rt.attachments.accept }); files.push(r); toast(t("{name} yükləndi.", { name: f.name }), "ok"); }
      catch (err) { toast(`${f.name}: ${err.message}`, "err"); }
    }
    draw();
  }
  el.addEventListener("change", (e) => { if (e.target.id === "file" && e.target.files.length) upload([...e.target.files]); });
  el.addEventListener("dragover", (e) => { const dz = e.target.closest("#dz"); if (dz) { e.preventDefault(); dz.classList.add("drag"); } });
  el.addEventListener("dragleave", (e) => { const dz = e.target.closest("#dz"); if (dz) dz.classList.remove("drag"); });
  el.addEventListener("drop", (e) => { const dz = e.target.closest("#dz"); if (dz) { e.preventDefault(); dz.classList.remove("drag"); upload([...e.dataTransfer.files]); } });
  draw();
  loadAbsences();
});

// ---------------------------------------------------------------- my requests
route("/student/requests", async (el, p, q) => {
  mount(el, loading());
  let rs;
  try { [rs] = await Promise.all([api.get("/api/requests"), services()]); } catch (e) { return mount(el, failed(e.message)); }
  const tab = q.tab || "active";
  const inTab = (r) => tab === "all" || (tab === "active" ? ["submitted", "in_progress", "returned"].includes(r.status) : ["ready", "rejected", "cancelled"].includes(r.status));
  const shown = rs.filter(inTab);
  mount(el, html`${pageHead(t("Müraciətlərim"), t("Statusu izləyin, dekanlıqla yazışın, hazır sənədləri yükləyin."),
      html`<button class="btn btn-primary" data-go="/student/services">${ic("plus", 16)} ${t("Yeni müraciət")}</button>`, crumbsS([t("Müraciətlərim")]),
      { info: t("Aktiv — baxılan müraciətlər; Bağlanmış — hazır, rədd və ya ləğv edilənlər.") })}
    <div class="seg mb" role="tablist" data-tour="req-tabs">${[["active", t("Aktiv")], ["done", t("Bağlanmış")], ["all", t("Hamısı")]].map(([k, l]) => html`<button class="${tab === k ? "active" : ""}" role="tab" aria-selected="${tab === k}" data-go="/student/requests?tab=${k}">${l}</button>`)}</div>
    ${shown.length ? html`<div class="stack" data-tour="req-list">${shown.map((r) => reqRow(r))}</div>`
      : html`<div class="card">${empty("inbox", tab === "active" ? t("Aktiv müraciət yoxdur") : t("Müraciət yoxdur"),
          t("E-xidmətlər bölməsindən arayış, icazə və digər müraciətləri göndərə bilərsiniz."), { label: t("E-xidmətlər"), go: "/student/services", icon: "grid", cls: "btn" })}</div>`}`);
});

function reqRow(r) {
  const col = catOf(r.category).color;
  const steps = (r.steps || []).map((s_, i) => {
    const on_ = r.status === "ready" || i < r.step;
    const cur = i === r.step && ["submitted", "in_progress"].includes(r.status);
    return `<span class="rprog ${on_ ? "done" : cur ? "cur" : ""}" title="${esc(s_)}"></span>`;
  }).join("");
  return html`<button class="card hover req-card" data-go="/student/requests/${r.id}"><div class="card-b row wrap">
    <span class="stat-ic svc-cat-ic" style="--c:${col}">${ic(r.icon, 20)}</span>
    <div class="grow req-main"><b>${r.type_name}</b><div class="small muted">${t("№ {id}", { id: r.id })} · ${fmtDateTime(r.created_at)}${r.summary ? " · " + r.summary : ""}</div>
      <div class="rprog-bar mt-sm">${raw(steps)}</div></div>
    <div class="row wrap req-badges">${r.files ? html`<span class="badge b-gray">${ic("clip", 11)} ${r.files}</span>` : ""}${r.messages ? html`<span class="badge b-gray">${ic("message", 11)} ${r.messages}</span>` : ""}
      ${["ready", "rejected", "cancelled"].includes(r.status) ? "" : r.overdue ? html`<span class="badge b-red">${t("gecikir")}</span>`
        : r.hours_left != null && r.status !== "returned" ? html`<span class="badge b-gray">${ic("clock", 11)} ${t("~{n} saat", { n: Math.max(1, Math.round(r.hours_left)) })}</span>` : ""}
      ${badge(r.status)}</div></div></button>`;
}

route("/student/requests/:id", (el, p) => requestDetailPage(el, +p.id));
route("/office/request/:id", (el, p) => requestDetailPage(el, +p.id));

const ACT = {
  submitted: [t("Göndərildi"), "done"], approved: [t("Mərhələ təsdiqləndi"), "done"], returned: [t("Düzəlişə qaytarıldı"), "bad"], rejected: [t("Rədd edildi"), "bad"],
  issued: [t("Tamamlandı"), "done"], resubmitted: [t("Yenidən göndərildi"), "done"], cancelled: [t("Ləğv edildi"), "bad"],
};

export async function requestDetailPage(el, id) {
  mount(el, loading());
  let r;
  try { await services(); r = await api.get(`/api/requests/${id}`); } catch (e) { return mount(el, failed(e.message)); }
  const staff = STAFF.includes(S.user.role), canAct = DESK.includes(S.user.role);
  const open = ["submitted", "in_progress", "returned"].includes(r.status);
  const back = staff ? [t("Müraciətlər"), "/office"] : [t("Müraciətlərim"), "/student/requests"];
  const last = r.step >= r.steps.length - 1;
  const actions = [];
  if (canAct && open && r.status !== "returned") {
    actions.push(html`<button class="btn btn-danger" id="a-reject">${ic("x", 15)} ${t("Rədd et")}</button>`, html`<button class="btn" id="a-return">${ic("back", 15)} ${t("Düzəlişə qaytar")}</button>`);
    actions.push(last ? html`<button class="btn btn-success" id="a-issue">${ic("check", 15)} ${r.has_document ? t("Sənədi hazırla və ver") : t("Təsdiqlə və tamamla")}</button>`
      : html`<button class="btn btn-primary" id="a-approve">${ic("check", 15)} ${t("Təsdiqlə")}</button>`);
  }
  if (!staff && r.status === "returned") actions.push(html`<button class="btn btn-primary" id="a-resubmit">${ic("edit", 15)} ${t("Düzəliş edib göndər")}</button>`);
  if (!staff && ["submitted", "returned"].includes(r.status)) actions.push(html`<button class="btn btn-ghost" id="a-cancel">${t("Ləğv et")}</button>`);
  mount(el, html`${pageHead(r.type_name, html`${t("№ {id}", { id: r.id })} · ${r.student}${r.group ? " · " + r.group : ""} · ${fmtDateTime(r.created_at)}`, html`${badge(r.status)}${actions}`,
      [staff ? [t("Dekanlıq"), "/office"] : [t("Əsas"), "/student"], back, [t("№ {id}", { id: r.id })]])}
    ${r.status === "returned" ? html`<div class="notice warn mb">${ic("alert", 16)}<div><b>${t("Düzəliş tələb olunur")}:</b> ${(r.events.filter((e) => e.action === "returned").pop() || {}).note || ""}</div></div>` : ""}
    ${r.overdue ? html`<div class="notice coral mb">${ic("clock", 16)}<div>${t("İcra müddəti {n} saat keçib.", { n: Math.abs(Math.round(r.hours_left)) })}</div></div>` : ""}
    <div class="grid g-12"><div class="stack">
      ${r.document ? html`<div class="card brand-border" data-tour="req-doc"><div class="card-b row wrap"><span class="stat-ic ic-green">${ic("qr", 22)}</span>
        <div class="grow"><b>${t("Sənəd hazırdır")}</b><div class="small muted">${r.document.reg_no} · ${t("doğrulama kodu")} <b class="mono">${r.document.verify_code}</b></div></div>
        <button class="btn btn-primary" data-doc="${r.document.id}">${ic("eye", 15)} ${t("Sənədə bax")}</button>
        <a class="btn" href="/verify/${r.document.verify_code}" target="_blank" rel="noopener">${ic("shield", 15)} ${t("Doğrula")}</a></div></div>` : ""}
      ${r.answer ? html`<div class="notice ok">${ic("check", 16)}<div><b>${t("Cavab")}:</b> ${r.answer}</div></div>` : ""}
      <div class="card"><div class="card-h"><h3>${ic("list", 17)} ${t("Müraciətin məlumatları")}</h3></div><div class="card-b">
        ${r.data_view.length ? html`<div class="review-grid">${r.data_view.map((d) => html`<div>${d.label}</div><div>${Array.isArray(d.value) ? raw(d.value.map((x) => `• ${esc(x)}`).join("<br>")) : d.value}</div>`)}</div>`
          : html`<div class="small muted">${t("Əlavə məlumat göstərilməyib.")}</div>`}</div></div>
      ${r.type.attachments ? html`<div class="card"><div class="card-h"><h3>${ic("clip", 17)} ${t("Əlavə edilmiş sənədlər")}</h3>${r.type.privacy ? html`<span class="badge b-blue">${ic("shield", 11)} ${t("məxfi")}</span>` : ""}</div><div class="card-b">
        ${r.attachments.length ? html`<div class="file-list" style="margin:0">${r.attachments.map((f) => html`<div class="file-row"><span class="fi ${f.mime.startsWith("image/") ? "img" : ""}">${f.mime.startsWith("image/") ? "IMG" : f.mime.includes("pdf") ? "PDF" : "DOC"}</span>
          <div class="grow"><b class="small ellipsis" style="display:block">${f.filename}</b><div class="tiny muted">${fmtSize(f.size)} · ${fmtDateTime(f.created_at)}</div></div>
          ${S.user.role !== "leader" ? html`<button class="btn btn-sm" data-file="${f.id}" data-fname="${esc(f.filename)}">${ic("eye", 14)} ${t("Bax")}</button>` : html`<span class="tiny muted">${t("yalnız dekanlıq")}</span>`}</div>`)}</div>`
          : html`<div class="small muted">${t("Fayl əlavə edilməyib.")}</div>`}
        ${r.type.privacy ? html`<div class="tiny muted mt-sm">${r.type.privacy} ${t("Hər baxış audit jurnalına yazılır.")}</div>` : ""}</div></div>` : ""}
      <div class="card"><div class="card-h"><h3>${ic("message", 17)} ${t("Yazışma")}</h3><span class="tiny muted">${staff ? t("Tələbə ilə") : t("Dekanlıq ilə")}</span></div><div class="card-b">
        <div class="thread req-thread">${r.thread.length ? r.thread.map((m) => html`<div class="tmsg ${m.author_id === S.user.id ? "me" : ""}"><div class="tm">${m.author} · ${ago(m.created_at)}</div>${m.text}</div>`)
          : html`<div class="small muted">${t("Hələ mesaj yoxdur. Sualınız varsa, buradan yazın.")}</div>`}</div>
        ${open || staff ? html`<form class="row mt reply-row" id="msg-form"><input class="input grow" id="msg" placeholder="${t("Mesaj yazın…")}" maxlength="2000" aria-label="${t("Mesaj")}"><button class="btn btn-primary" aria-label="${t("Göndər")}">${ic("send", 15)}</button></form>` : ""}</div></div>
    </div>
    <div class="stack">
      <div class="card" data-tour="req-timeline"><div class="card-h"><h3>${ic("timer", 17)} ${t("Mərhələlər")}</h3></div><div class="card-b"><div class="timeline">
        ${r.steps.map((s_, i) => { const done = r.status === "ready" || i < r.step; const cur = i === r.step && ["submitted", "in_progress"].includes(r.status);
          return html`<div class="tl-item ${done ? "done" : cur ? "" : "wait"}"><b class="small">${s_}</b><div class="tiny muted">${done ? t("tamamlanıb") : cur ? t("icrada") : ["rejected", "cancelled"].includes(r.status) ? t("dayandırılıb") : t("gözləyir")}</div></div>`; })}</div>
        ${open ? html`<div class="small muted mt">${ic("clock", 13)} ${t("Son icra tarixi")}: <b>${fmtDateTime(r.due_at)}</b></div>` : ""}</div></div>
      <div class="card"><div class="card-h"><h3>${ic("list", 17)} ${t("Gedişat")}</h3></div><div class="card-b"><div class="timeline">
        ${r.events.map((e) => { const [l, cl] = ACT[e.action] || [e.action, ""]; return html`<div class="tl-item ${cl}"><b class="small">${l}</b><div class="tiny muted">${fmtDateTime(e.created_at)}${e.actor ? " · " + e.actor : ""}</div>${e.note ? html`<div class="small">${e.note}</div>` : ""}</div>`; })}</div></div></div>
      ${staff ? html`<div class="card pad"><div class="row">${avatar(r.student, r.student_color, "lg")}<div><b>${r.student}</b><div class="small muted">${r.group || ""} · ${t("tələbə")}</div></div></div></div>` : ""}
    </div></div>`);
  const reload = () => { refreshBadges(); requestDetailPage(el, id); };
  on(el, "click", "[data-doc]", (e, b) => openDoc(+b.dataset.doc, r.type_name));
  on(el, "click", "[data-file]", (e, b) => openFile(+b.dataset.file, b.dataset.fname));
  on(el, "submit", "#msg-form", async (e) => { e.preventDefault(); const v = $("#msg", el).value.trim(); if (!v) return; try { await api.post(`/api/requests/${id}/messages`, { text: v }); reload(); } catch (err) { toast(err.message, "err"); } });
  const reason = (action, title, cls, okLabel) => modal({ title, size: "sm", body: html`<div class="field"><label class="label" for="rn">${t("Səbəb (tələbəyə göstəriləcək)")}</label><textarea class="textarea" id="rn" rows="4"></textarea></div>`,
    actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: okLabel, cls, onClick: async (w) => {
      const note = w.querySelector("#rn").value.trim();
      if (!note) { toast(t("Səbəbi qeyd edin."), "err"); return false; }
      await api.post(`/api/requests/${id}/action`, { action, note }); toast(t("Yadda saxlanıldı, tələbəyə bildiriş göndərildi."), "ok"); reload(); } }] });
  on(el, "click", "#a-reject", () => reason("reject", t("Müraciəti rədd et"), "btn-danger", t("Rədd et")));
  on(el, "click", "#a-return", () => reason("return", t("Düzəlişə qaytar"), "btn-primary", t("Qaytar")));
  on(el, "click", "#a-approve", async () => { try { await api.post(`/api/requests/${id}/action`, { action: "approve" }); toast(t("Növbəti mərhələyə keçdi."), "ok"); reload(); } catch (err) { toast(err.message, "err"); } });
  on(el, "click", "#a-issue", async () => {
    if (r.has_document) {
      const m = modal({ title: t("Sənədin önizləməsi"), size: "xl", cls: "viewer", body: html`<div class="notice ai mb">${ic("sparkles", 16)}<div>${t("Sənəd seçilmiş təyinat və dilə uyğun şablondan avtomatik yaradıldı. Təsdiqdən sonra reyestr nömrəsi, QR kod və bütövlük imzası əlavə olunacaq.")}</div></div>
        <div class="viewer-stage"><div class="viewer-load">${spinner(22)}</div><iframe class="viewer-frame doc-frame" id="pv" title="${esc(t("Sənədin önizləməsi"))}" hidden></iframe></div>
        <div class="tiny muted mt-sm">${t("Pilotda bu addımda ASAN İmza / SİMA ilə gücləndirilmiş elektron imza əlavə olunacaq.")}</div>`,
        actions: [{ label: t("Geri"), cls: "btn-ghost" }, { html: `${ic("shield", 15).__html} ${esc(t("Elektron təsdiqlə və ver"))}`, cls: "btn-success", onClick: async () => {
          const res = await api.post(`/api/requests/${id}/action`, { action: "issue" }); toast(t("Sənəd verildi: {reg}", { reg: res.document.reg_no }), "ok"); reload(); } }] });
      const fr = m.el.querySelector("#pv");
      try {
        const sid = sessionStorage.getItem("zeka-sid");
        const resp = await fetch(`/api/requests/${id}/preview`, { headers: sid ? { "X-Session": sid } : {}, credentials: "same-origin" });
        if (!resp.ok) throw new Error(t("Önizləmə yüklənmədi"));
        fr.srcdoc = await resp.text();
        fr.addEventListener("load", () => { fr.hidden = false; m.el.querySelector(".viewer-load")?.remove(); }, { once: true });
      } catch (err) { m.el.querySelector(".viewer-stage").innerHTML = failed(err.message).__html; }
    } else {
      modal({ title: t("Müraciəti tamamla"), body: html`<div class="field"><label class="label" for="ans">${t("Tələbəyə cavab")}</label><textarea class="textarea" id="ans" rows="4">${r.type.answer || t("Müraciətiniz təmin edildi.")}</textarea></div>
        ${r.type_code === "absence_excuse" ? html`<div class="notice info mt">${ic("calcheck", 16)}<div>${t("Təsdiqdən sonra seçilmiş qayıblar elektron jurnalda avtomatik “üzrlü” olacaq və fənn müəllimləri məlumatlandırılacaq (tibbi məlumat göndərilmir).")}</div></div>` : ""}`,
        actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Təsdiqlə və tamamla"), cls: "btn-success", onClick: async (w) => { await api.post(`/api/requests/${id}/action`, { action: "issue", note: w.querySelector("#ans").value }); toast(t("Müraciət tamamlandı."), "ok"); reload(); } }] });
    }
  });
  on(el, "click", "#a-cancel", async () => { if (await confirmBox(t("Müraciəti ləğv etmək?"), t("Müraciət geri götürüləcək. Bu əməliyyat geri qaytarılmır."), t("Ləğv et"), true)) {
    try { await api.post(`/api/requests/${id}/cancel`); toast(t("Müraciət ləğv edildi."), "ok"); reload(); } catch (err) { toast(err.message, "err"); } } });
  on(el, "click", "#a-resubmit", () => {
    const fields = r.type.fields.filter((f) => ["text", "textarea", "select", "number"].includes(f.type));
    modal({ title: t("Düzəliş et"), body: html`<div class="stack">${fields.map((f) => html`<div class="field"><label class="label" for="e_${f.name}">${f.label}</label>
      ${f.type === "select" ? html`<select class="select" id="e_${f.name}" data-e="${f.name}">${f.options.map((o) => html`<option ${o === r.data[f.name] ? "selected" : ""}>${o}</option>`)}</select>`
        : f.type === "textarea" ? html`<textarea class="textarea" id="e_${f.name}" data-e="${f.name}" rows="4">${r.data[f.name] || ""}</textarea>` : html`<input class="input" id="e_${f.name}" data-e="${f.name}" value="${r.data[f.name] || ""}">`}</div>`)}</div>`,
      actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Yenidən göndər"), cls: "btn-primary", onClick: async (w) => { const data = {}; w.querySelectorAll("[data-e]").forEach((x) => { data[x.dataset.e] = x.value; });
        await api.post(`/api/requests/${id}/resubmit`, { data }); toast(t("Yenidən göndərildi."), "ok"); reload(); } }] });
  });
}

// ---------------------------------------------------------------- office queue
route("/office", async (el, p, q) => {
  if (!STAFF.includes(S.user.role)) return go("/student/services");
  mount(el, loading());
  const status = q.status || "open";
  let sum, rs;
  try { [sum, rs] = await Promise.all([api.get("/api/office/summary"), api.get(`/api/requests?status=${status}${q.type ? "&type=" + q.type : ""}`), services()]); }
  catch (e) { return mount(el, failed(e.message)); }
  let cat = q.cat || "", term = "";
  const draw = () => {
    const shown = rs.filter((r) => (!cat || r.category === cat) && (!term || (r.student + " " + r.id + " " + r.type_name).toLowerCase().includes(term)));
    mount($("#queue-b", el), shown.length ? html`<div class="table-wrap"><table class="table office-table"><thead><tr><th>${t("Tələbə")}</th><th>${t("Müraciət")}</th><th>${t("Göndərilib")}</th><th>${t("İcra müddəti")}</th><th>${t("Status")}</th><th></th></tr></thead><tbody>
      ${shown.map((r) => html`<tr data-open="${r.id}"><td data-l="${t("Tələbə")}"><div class="row">${avatar(r.student, r.student_color)}<div><b>${r.student}</b><div class="tiny muted">${r.group || ""}</div></div></div></td>
        <td data-l="${t("Müraciət")}"><div class="row"><span class="stat-ic svc-cat-ic sm" style="--c:${catOf(r.category).color}">${ic(r.icon, 15)}</span><div><b class="small">${r.type_name}</b>
          <div class="tiny muted">${t("№ {id}", { id: r.id })}${r.summary ? " · " + r.summary : ""}${r.files ? " · " + r.files + " " + t("fayl") : ""}</div></div></div></td>
        <td class="small nowrap" data-l="${t("Göndərilib")}">${ago(r.created_at)}</td>
        <td class="sla-cell" data-l="${t("İcra müddəti")}">${r.hours_left != null && r.status !== "returned" ? html`<div class="small sla-txt ${r.overdue ? "over" : ""}">${r.overdue ? t("{n} saat gecikir", { n: Math.abs(Math.round(r.hours_left)) }) : t("{n} saat qalıb", { n: Math.round(r.hours_left) })}</div>
          ${raw(`<div class="progress mt-xs"><span style="width:${Math.min(100, Math.max(4, 100 - (r.hours_left / r.sla_hours) * 100))}%;background:${r.overdue ? "var(--red)" : r.hours_left < r.sla_hours / 3 ? "var(--amber)" : "var(--green)"}"></span></div>`)}`
          : html`<span class="tiny muted">${fmtDateTime(r.updated_at)}</span>`}</td>
        <td data-l="${t("Status")}">${badge(r.status)}</td><td class="right">${ic("chevron", 16)}</td></tr>`)}</tbody></table></div>`
      : empty("check", t("Bu bölmədə müraciət yoxdur"), t("Filtri dəyişin və ya digər statuslara baxın."), { label: t("Bütün müraciətlər"), go: "/office?status=all", cls: "btn" }));
  };
  mount(el, html`${pageHead(t("Müraciətlər"), t("Tələbə müraciətlərinin yoxlanması, təsdiqi və sənədlərin elektron verilməsi."), "", crumbsO([t("Müraciətlər")]),
      { info: t("Növbə prioritet və icra müddətinə görə sıralanır. Müraciəti açmaq üçün sətrə toxunun.") })}
    <div class="grid g-4" id="office-stats">${stat("inbox", "ic-blue", cnt(sum.new), t("Yeni müraciət"))}${stat("timer", "ic-violet", cnt(sum.in_progress), t("İcrada"))}
      ${stat("alert", sum.overdue ? "ic-red" : "ic-green", cnt(sum.overdue), t("Müddəti keçən"))}
      ${stat("check", "ic-green", cnt(sum.issued_week), sum.avg_hours != null ? t("Bu həftə tamamlanıb · orta {n} saat", { n: num(sum.avg_hours, 1) }) : t("Bu həftə tamamlanıb"))}</div>
    <div class="card mt" id="queue"><div class="card-h wrap"><div class="seg" role="tablist">${[["open", t("Açıq")], ["done", t("Bağlanmış")], ["all", t("Hamısı")]].map(([k, l]) =>
      html`<button class="${status === k ? "active" : ""}" role="tab" aria-selected="${status === k}" data-go="/office?status=${k}">${l}</button>`)}</div>
      <div class="search-field sm"><span class="sfi">${ic("search", 15)}</span><input class="input input-sm" id="qf" placeholder="${t("Tələbə, № və ya xidmət")}" aria-label="${t("Axtarış")}"></div></div>
      <div class="card-b queue-filters"><div class="chips"><button class="chip ${!cat ? "on" : ""}" data-cat="">${t("Hamısı")}</button>
        ${sum.categories.map((cc) => html`<button class="chip ${cat === cc.key ? "on" : ""}" data-cat="${cc.key}">${cc.name}${sum.by_category[cc.key] && status === "open" ? html` <span class="badge b-coral">${sum.by_category[cc.key]}</span>` : ""}</button>`)}</div></div>
      <div class="card-b queue-body" id="queue-b"></div></div>`);
  draw();
  on(el, "click", "[data-cat]", (e, b) => { cat = b.dataset.cat; $$("[data-cat]", el).forEach((x) => x.classList.toggle("on", x === b)); draw(); });
  $("#qf", el).addEventListener("input", (e) => { term = e.target.value.trim().toLowerCase(); draw(); });
  on(el, "click", "[data-open]", (e, tr) => go(`/office/request/${tr.dataset.open}`));
});

// ---------------------------------------------------------------- document registry
route("/office/registry", async (el, p, q) => {
  if (!STAFF.includes(S.user.role)) return go("/student/services");
  mount(el, loading());
  let docs;
  try { docs = await api.get(`/api/documents?q=${encodeURIComponent(q.q || "")}`); } catch (e) { return mount(el, failed(e.message)); }
  mount(el, html`${pageHead(t("Sənəd reyestri"), t("Verilmiş bütün sənədlər — QR kod və bütövlük imzası ilə onlayn doğrulanır."), "", crumbsO([t("Sənəd reyestri")]),
      { info: t("Sənədi reyestr nömrəsi, ad və ya növ üzrə axtarın. Doğrulama səhifəsi sənədin etibarlı olduğunu təsdiqləyir.") })}
    <div class="card" data-tour="reg-table"><div class="card-h wrap"><form class="search-field grow" id="sform"><span class="sfi">${ic("search", 16)}</span>
        <input class="input" id="sq" placeholder="${t("Reyestr nömrəsi, ad və ya sənəd növü")}" value="${esc(q.q || "")}" aria-label="${t("Axtarış")}"></form><span class="small muted">${t("{n} sənəd", { n: docs.length })}</span></div>
      <div class="card-b queue-body">${docs.length ? html`<div class="table-wrap"><table class="table reg-table"><thead><tr><th>${t("Reyestr №")}</th><th>${t("Sənəd")}</th><th>${t("Sahibi")}</th><th>${t("Verilib")}</th><th>${t("Status")}</th><th></th></tr></thead><tbody>
      ${docs.map((d) => html`<tr><td class="mono small" data-l="${t("Reyestr №")}">${d.reg_no}</td><td data-l="${t("Sənəd")}">${d.kind === "certificate" ? html`<span class="badge b-violet">${ic("award", 11)} ${t("Sertifikat")}</span> ` : ""}${d.title}</td>
        <td data-l="${t("Sahibi")}">${d.holder}</td><td class="small nowrap" data-l="${t("Verilib")}">${fmtDate(d.issued_at)}</td><td data-l="${t("Status")}">${badge(d.status)}${d.status === "revoked" && d.revoked_reason ? html`<div class="tiny muted">${d.revoked_reason}</div>` : ""}</td>
        <td class="right nowrap reg-actions"><button class="btn btn-sm" data-doc="${d.id}" data-title="${esc(d.title)}" title="${t("Sənədə bax")}">${ic("eye", 14)}</button>
          <a class="btn btn-sm" href="/verify/${d.verify_code}" target="_blank" rel="noopener" title="${t("Doğrulama səhifəsi")}">${ic("qr", 14)}</a>
          ${d.status === "valid" && DESK.includes(S.user.role) ? html`<button class="btn btn-sm btn-danger" data-revoke="${d.id}" title="${t("Ləğv et")}">${ic("x", 14)}</button>` : ""}</td></tr>`)}</tbody></table></div>`
        : empty("search", q.q ? t("Uyğun sənəd tapılmadı") : t("Reyestr boşdur"), q.q ? t("Axtarış sözünü dəyişin.") : t("Verilmiş sənədlər burada görünəcək."), q.q ? { label: t("Axtarışı sıfırla"), go: "/office/registry", cls: "btn" } : null)}</div></div>`);
  $("#sform", el).addEventListener("submit", (e) => { e.preventDefault(); go(`/office/registry?q=${encodeURIComponent($("#sq", el).value.trim())}`); });
  on(el, "click", "[data-doc]", (e, b) => openDoc(+b.dataset.doc, b.dataset.title));
  on(el, "click", "[data-revoke]", (e, b) => modal({ title: t("Sənədi ləğv et"), size: "sm", body: html`<p class="small">${t("Ləğv edilmiş sənəd doğrulama səhifəsində “etibarsız” göstəriləcək.")}</p>
      <div class="field"><label class="label" for="rr">${t("Səbəb")}</label><textarea class="textarea" id="rr" rows="3"></textarea></div>`,
    actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Sənədi ləğv et"), cls: "btn-danger", onClick: async (w) => {
      const reason = w.querySelector("#rr").value.trim();
      if (!reason) { toast(t("Ləğv səbəbini yazın."), "err"); return false; }
      await api.post(`/api/documents/${b.dataset.revoke}/revoke`, { reason }); toast(t("Sənəd ləğv edildi."), "ok"); go(location.hash.slice(1)); } }] }));
});

export { openDoc };

// ---------------------------------------------------------------- page guides
const GX = t("Xidmətlər"), GO = t("Dekanlıq");
registerTour("student.services", { route: "/student/services", roles: ["student"], title: t("E-xidmətlər"), group: GX, icon: "grid", go: "/student/services", steps: [
  { sel: "#sf", title: t("Axtarış"), text: t("Xidmətin adını yazın — nəticələr dərhal süzgəclənir.") },
  { sel: "[data-tour=svc-popular]", title: t("Populyar xidmətlər"), text: t("Ən çox istifadə olunan müraciətlər buradadır.") },
  { sel: ".svc-sec", title: t("Kateqoriyalar"), text: t("Xidmətlər bölmələrə ayrılıb. Karta toxunub müraciətə başlayın.") },
] });
registerTour("student.apply", { route: "/student/apply/:code", roles: ["student"], title: t("Müraciət sihirbazı"), group: GX, icon: "edit", go: "/student/apply/enrollment_certificate", steps: [
  { sel: "[data-tour=apply-stepper]", title: t("Mərhələlər"), text: t("Müraciət üç addımdan ibarətdir: məlumatlar, yoxlama və göndəriş.") },
  { sel: "#w-form", title: t("Məlumatlar"), text: t("Sahələri doldurun. Bəzi sahələr seçiminizə görə görünür.") },
  { sel: "[data-tour=apply-side]", title: t("Xidmət haqqında"), text: t("Lazım olanlar, mərhələlər və icra müddəti burada göstərilir.") },
] });
registerTour("student.requests", { route: "/student/requests", roles: ["student"], title: t("Müraciətlərim"), group: GX, icon: "inbox", go: "/student/requests", steps: [
  { sel: "[data-tour=req-tabs]", title: t("Süzgəc"), text: t("Aktiv, bağlanmış və bütün müraciətlər arasında keçin.") },
  { sel: "[data-tour=req-list]", title: t("Müraciətlər"), text: t("Hər kartda status və irəliləyiş göstərilir. Təfərrüat üçün karta toxunun.") },
] });
registerTour("student.request", { route: "/student/requests/:id", roles: ["student"], title: t("Müraciətin təfərrüatı"), group: GX, icon: "inbox", go: "/student/requests/34", steps: [
  { sel: "[data-tour=req-timeline]", title: t("Mərhələlər"), text: t("Müraciətin hansı mərhələdə olduğunu izləyin.") },
  { sel: ".req-thread", title: t("Yazışma"), text: t("Dekanlıqla birbaşa yazışın; sualınızı buradan verin.") },
  { sel: "[data-tour=req-doc]", title: t("Sənəd"), text: t("Hazır sənədi portal daxilində açın və ya doğrulayın.") },
] });
registerTour("office.queue", { route: "/office", roles: ["office", "leader", "admin"], title: t("Müraciətlər növbəsi"), group: GO, icon: "inbox", go: "/office", steps: [
  { sel: "#office-stats", title: t("Göstəricilər"), text: t("Yeni, icrada olan və müddəti keçmiş müraciətlər, həftəlik icra statistikası.") },
  { sel: ".queue-filters", title: t("Süzgəclər"), text: t("Status və kateqoriya üzrə süzün, tələbə və ya nömrə ilə axtarın.") },
  { sel: "#queue-b", title: t("Növbə"), text: t("Müraciəti açmaq üçün sətrə toxunun — orada təsdiq və sənəd əməliyyatları var.") },
] });
registerTour("office.request", { route: "/office/request/:id", roles: ["office", "leader", "admin"], title: t("Müraciətə baxış"), group: GO, icon: "inbox", go: "/office/request/3", steps: [
  { sel: ".page-head", title: t("Əməliyyatlar"), text: t("Təsdiq, düzəlişə qaytarma, rədd və sənədin verilməsi başlıqdadır.") },
  { sel: "[data-tour=req-timeline]", title: t("Mərhələlər"), text: t("Müraciətin gedişatını və son icra tarixini izləyin.") },
  { sel: ".req-thread", title: t("Yazışma"), text: t("Tələbə ilə yazışın və əlavə məlumat istəyin.") },
] });
registerTour("office.registry", { route: "/office/registry", roles: ["office", "leader", "admin"], title: t("Sənəd reyestri"), group: GO, icon: "qr", go: "/office/registry", steps: [
  { sel: "#sform", title: t("Axtarış"), text: t("Sənədi reyestr nömrəsi, ad və ya növ üzrə tapın.") },
  { sel: "[data-tour=reg-table]", title: t("Sənədlər"), text: t("Sənədi portal daxilində açın, doğrulayın və ya lazım gəldikdə ləğv edin.") },
] });
