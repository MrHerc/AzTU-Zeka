import { api, html, raw, mount, on, md, ic, toast, modal, confirmBox, route, go, S, pageHead, badge, fmtDate, fmtDateTime, ago, ring, progress, loading, skelLines, empty,
  failed, infoTip, greeting, QTYPE, cnt, num, sparkline, barChart, fileToB64, fmtSize, sleep, fmtDayLong, registerTour, refCard, refList, t, esc, $, $$ } from "./core.js";
import { chatView } from "./chat.js";
import { stat, lessonRow, schedulePage } from "./student.js";
import { achievementsTeaser } from "./achievements.js";
import { refreshBadges } from "./shell.js";

const LET = "ABCD";
const crumbsT = (...c) => [[t("Əsas"), "/teacher"], ...c];
// Accepted upload formats (shared between the upload card and its info tip).
const FORMATS = ".docx,.pptx,.txt,.md";
const MAX_MB = 20;

// ---------------------------------------------------------------- dashboard
route("/teacher", async (el) => {
  mount(el, loading());
  let d;
  try { d = await api.get("/api/teacher/home"); } catch (e) { return mount(el, failed(e.message)); }
  const first = d.user.full_name.split(" ")[0];
  const main = d.courses[0];
  const ins = main ? main.insights : null;
  const pct = Math.round((100 * d.academy.done) / Math.max(1, d.academy.total));
  mount(el, html`
    <div class="hero slide-up" data-tour="hero"><div class="row between wrap"><div><div class="small" style="opacity:.8">${fmtDayLong(new Date())} · ${S.app.semester}</div>
      <h2 class="mt-sm">${t("{greet}, {name} müəllim", { greet: greeting(), name: first })}</h2><p>${d.user.title}</p></div>
      <div class="row wrap"><button class="btn btn-accent" data-go="/teacher/studio">${ic("wand", 16)} ${t("Test yarat")}</button>
        <button class="btn btn-hero-ghost" data-go="/teacher/syllabus">${ic("layers", 16)} ${t("Sillabus")}</button></div></div></div>

    <div class="grid g-4 mt" data-tour="stats">
      ${stat("message", "ic-blue", ins ? cnt(ins.this_week) : "—", t("Tutora sual (bu həftə)"))}
      ${stat("shield", "ic-green", ins ? cnt(ins.cited_rate, { suffix: "%", dec: 1 }) : "—", t("Mənbəyə istinadlı cavablar"))}
      ${stat("inbox", "ic-amber", cnt(d.open_questions), t("Cavab gözləyən tələbə sualı"), "/teacher/questions")}
      ${stat("cap", "ic-navy", cnt(pct, { suffix: "%" }), t("AI Akademiya gedişatı"), "/teacher/academy")}
    </div>

    <div class="grid g-12 mt">
      <div class="stack">
        <div class="card" id="insights-card" data-tour="insights"><div class="card-h"><h3>${ic("sparkles", 17)} ${main ? t("Tutor müşahidələri · {course}", { course: main.name }) : t("Tutor müşahidələri")}
            ${infoTip(t("Müşahidələr yalnız materiallardakı boşluqları göstərir; tələbələrin tutorla şəxsi söhbətləri sizə açılmır."))}</h3>
          ${main ? html`<a class="small" href="#/teacher/course/${main.id}?tab=insights">${t("Ətraflı")} ${ic("arrow", 13)}</a>` : ""}</div>
          <div class="card-b">${ins ? html`<div class="grid g-2">
            <div><div class="label mb-sm">${t("Ən çox soruşulan mövzular")}</div>
              ${ins.top_topics.length ? ins.top_topics.map((x) => html`<div class="bar-row"><span class="ellipsis small" title="${x.topic}">${x.topic}</span>${progress((x.n / ins.top_topics[0].n) * 100)}<b class="right small">${num(x.n)}</b></div>`)
                : empty("message", t("Hələ sual yoxdur"), t("Tələbələr tutora sual verdikcə mövzular burada toplanacaq."))}</div>
            <div><div class="label mb-sm">${t("Həftəlik suallar")}</div>${sparkline(ins.weekly, "#2b5aa8", 260, 70)}
              <div class="row wrap mt"><span class="badge b-green">${t("{n}% faydalı", { n: ins.positive_rate ?? "—" })}</span><span class="badge b-amber">${t("Mənbəsiz: {n}%", { n: num(ins.no_source_rate, 1) })}</span></div>
              ${ins.gaps.length ? html`<div class="notice warn mt">${ic("alert", 16)}<div><b>${t("Materiallarda cavabı olmayan suallar")}</b>
                <div class="mt-sm">${ins.gaps.slice(0, 3).map((g) => html`<div class="small">${t("“{q}”", { q: g })}</div>`)}</div>
                <a class="small" href="#/teacher/course/${main.id}?tab=materials">${t("Material əlavə et")} ${ic("arrow", 13)}</a></div></div>` : ""}</div></div>`
            : empty("sparkles", t("Hələ müşahidə yoxdur"), t("Fənninizə material yükləyin və tutoru aktiv edin — tələbə sualları toplandıqca təhlil burada görünəcək."),
                main ? { label: t("Material yüklə"), go: `/teacher/course/${main.id}?tab=materials`, icon: "upload", cls: "btn" } : { label: t("Fənlərim"), go: "/teacher/courses", icon: "book", cls: "btn" })}</div></div>

        <div class="card" data-tour="courses"><div class="card-h"><h3>${ic("book", 17)} ${t("Fənlərim")}</h3><a class="small" href="#/teacher/courses">${t("İdarə et")} ${ic("arrow", 13)}</a></div>
          <div class="card-b">${d.courses.length ? html`<div class="table-wrap"><table class="table">
            <thead><tr><th>${t("Fənn")}</th><th>${t("Tələbə")}</th><th>${t("Material")}</th><th>${t("Tutor")}</th><th>${t("Bu həftə")}</th><th></th></tr></thead><tbody>
            ${d.courses.map((c) => html`<tr><td><div class="row"><span class="course-ic sm" style="background:${c.color}">${c.code.split("-")[0]}</span>
              <div><b class="small">${c.name}</b><div class="tiny muted">${c.code} · ${t("{n} kredit", { n: c.credits })}</div></div></div></td>
              <td>${num(c.students)}</td><td>${num(c.materials)}</td>
              <td>${c.tutor_locked ? html`<span class="badge b-amber">${ic("lock", 11)} ${t("Bağlı")}</span>` : html`<span class="badge b-green">${t("Aktiv")}</span>`}</td>
              <td>${t("{n} sual", { n: c.insights.this_week })}</td><td class="right"><button class="btn btn-sm" data-go="/teacher/course/${c.id}">${t("İdarə et")}</button></td></tr>`)}</tbody></table></div>`
            : empty("book", t("Bu semestr üçün fənn yoxdur"), t("Fənlər təyin olunduqda burada görünəcək."))}</div></div>
      </div>

      <div class="stack">
        <div class="card" id="today-card"><div class="card-h"><h3>${ic("calendar", 17)} ${t("Bu gün")}</h3><a class="small" href="#/teacher/schedule">${t("Həftəlik cədvəl")} ${ic("arrow", 13)}</a></div>
          <div class="card-b today-line">${d.today.length ? d.today.map((x) => lessonRow({ ...x, state: x.end < new Date().toTimeString().slice(0, 5) ? "done" : "" }))
            : empty("calendar", t("Bu gün dərs yoxdur"), t("Həftənin digər günlərinə dərs cədvəlindən baxın."), { label: t("Dərs cədvəli"), go: "/teacher/schedule", icon: "calendar", cls: "btn" })}</div></div>

        <div class="card" data-tour="questions"><div class="card-h"><h3>${ic("inbox", 17)} ${t("Tələbə sualları")}</h3><a class="small" href="#/teacher/questions">${t("Hamısı")} ${ic("arrow", 13)}</a></div>
          <div class="card-b list">${d.questions.length ? d.questions.map((q) => html`<div class="list-item top click" data-go="/teacher/questions">
            <span class="avatar sm" style="background:${q.anonymous ? "#9aa3b8" : "#2b5aa8"}">${q.anonymous ? "?" : q.student.split(" ").map((x) => x[0]).join("")}</span>
            <div class="grow"><div class="row between"><b class="small">${q.student}</b><span class="tiny muted">${ago(q.created_at)}</span></div>
            <div class="small">${q.question.slice(0, 110)}${q.question.length > 110 ? "…" : ""}</div></div></div>`)
            : empty("check", t("Cavab gözləyən sual yoxdur"), t("Tələbələr tutordan sizə sual yönləndirdikdə burada görünəcək."))}</div></div>

        ${d.excused.length ? html`<div class="card"><div class="card-h"><h3>${ic("calcheck", 17)} ${t("Üzrlü qayıblar")}</h3></div><div class="card-b list">
          ${d.excused.map((x) => html`<div class="list-item"><div class="grow"><b class="small">${x.student}</b><div class="tiny muted">${fmtDate(x.day)} · ${x.course}</div></div>${badge("excused")}</div>`)}
          <div class="tiny muted mt-sm">${t("Dekanlıq tərəfindən təsdiqlənib. Səbəb və sənədlər məxfidir.")}</div></div></div>` : ""}

        <div class="card brand-border" data-tour="academy"><div class="card-b"><div class="row">${ring(pct, 76)}<div class="grow"><b>${t("AI Akademiya")}</b>
          <div class="small muted">${t("{done}/{total} modul · {h} saat peşəkar inkişaf", { done: d.academy.done, total: d.academy.total, h: num(d.academy.hours, 1) })}</div>
          <button class="btn btn-sm btn-ai mt-sm" data-go="/teacher/academy">${t("Davam et")}</button></div></div></div></div>

        <div id="ach-teaser"></div>

        ${d.drafts ? html`<div class="notice ai">${ic("wand", 16)}<div><b>${t("{n} AI qaralama sual", { n: d.drafts })}</b> ${t("təsdiqinizi gözləyir.")}
          <a href="#/teacher/studio?tab=bank">${t("Yoxla")} ${ic("arrow", 13)}</a></div></div>` : ""}
      </div></div>`);
  achievementsTeaser(3).then((h) => { const box = $("#ach-teaser", el); if (box && h) mount(box, h); else if (box) box.remove(); });
});

route("/teacher/schedule", (el) => schedulePage(el, "teacher"));

// ---------------------------------------------------------------- courses
route("/teacher/courses", async (el) => {
  mount(el, loading());
  let cs;
  try { cs = await api.get("/api/courses"); } catch (e) { return mount(el, failed(e.message)); }
  mount(el, html`${pageHead(t("Fənlərim"), t("{sem} · {n} fənn", { sem: S.app.semester, n: cs.length }), "", crumbsT([t("Fənlərim")]),
      { info: t("Fənn kartından materiallara, tutor rejimlərinə, davamiyyətə, analitikaya və test studiyasına keçə bilərsiniz.") })}
    ${cs.length ? html`<div class="grid g-3" data-tour="course-grid">${cs.map((c) => html`<div class="card hover slide-up course-full" data-go="/teacher/course/${c.id}">
      <div class="course-strip" style="background:${c.color}"></div><div class="card-b">
      <div class="row"><span class="course-ic" style="background:${c.color}">${c.code.split("-")[0]}</span>
        <div class="grow"><b class="course-full-t">${c.name}</b><span class="small muted">${c.code} · ${t("{n} tələbə", { n: c.students })}</span></div></div>
      <div class="row wrap mt small"><span class="badge b-blue">${t("{n} material", { n: c.materials })}</span>
        ${c.tutor_locked ? html`<span class="badge b-amber">${ic("lock", 11)} ${t("Tutor bağlı")}</span>` : html`<span class="badge b-green">${t("Tutor aktiv")}</span>`}</div>
      <div class="row mt wrap"><button class="btn btn-sm grow" data-go="/teacher/course/${c.id}">${t("Fənni idarə et")}</button>
        <button class="btn btn-sm btn-ai grow" data-go="/teacher/studio?course=${c.id}">${ic("wand", 14)} ${t("Test yarat")}</button></div></div></div>`)}</div>`
      : empty("book", t("Bu semestr üçün fənn yoxdur"), t("Sizə fənn təyin olunduqda burada görünəcək."))}`);
});

// ---------------------------------------------------------------- course detail (tabbed)
route("/teacher/course/:id", async (el, p, q) => {
  mount(el, loading());
  let c, all;
  try { [c, all] = await Promise.all([api.get(`/api/courses/${p.id}`), api.get("/api/courses")]); }
  catch (e) { return mount(el, html`${pageHead(t("Fənn"), "", "", crumbsT([t("Fənlərim"), "/teacher/courses"]))}
    ${e.status === 404 ? empty("alert", t("Fənn tapılmadı"), t("Bu fənn mövcud deyil və ya ünvan dəyişib."), { label: t("Fənlərim"), go: "/teacher/courses", icon: "book" }) : failed(e.message)}`); }
  const tab = q.tab || "materials";
  const TABS = [["materials", t("Materiallar"), "file"], ["tutor", t("Tutor rejimləri"), "sliders"], ["attendance", t("Davamiyyət"), "calcheck"],
    ["insights", t("Analitika"), "chart"], ["tools", t("Texnoloji həllər"), "cpu"], ["test", t("Tutoru sına"), "sparkles"]];
  mount(el, html`${pageHead(c.name, t("{code} · {n} tələbə · {k} kredit", { code: c.code, n: c.students, k: c.credits }),
      html`<label class="sr-only" for="cs">${t("Fənn")}</label><select class="select" id="cs" style="width:auto" aria-label="${t("Fənn")}">${all.map((x) => html`<option value="${x.id}" ${x.id === c.id ? "selected" : ""}>${x.name}</option>`)}</select>`,
      crumbsT([t("Fənlərim"), "/teacher/courses"], [c.name]), { info: t("Materiallar və test sualları fənnin tədris dilində təqdim olunur.") })}
    <div class="table-wrap"><div class="tabs" role="tablist" data-tour="tabs">${TABS.map(([k, l, i]) => html`<button class="tab ${tab === k ? "active" : ""}" role="tab" aria-selected="${tab === k}" data-go="/teacher/course/${c.id}?tab=${k}">${ic(i, 15)} ${l}</button>`)}</div></div>
    <div id="tab"></div>`);
  $("#cs", el).addEventListener("change", (e) => go(`/teacher/course/${e.target.value}?tab=${tab}`));
  const tgt = $("#tab", el);
  if (tab === "materials") materialsTab(tgt, c);
  else if (tab === "tutor") tutorTab(tgt, c);
  else if (tab === "attendance") attendanceTab(tgt, c);
  else if (tab === "insights") insightsTab(tgt, c);
  else if (tab === "tools") toolsTab(tgt, c);
  else testTab(tgt, c);
});

function materialsTab(tgt, c) {
  mount(tgt, html`<div class="grid g-12">
    <div class="card" data-tour="mat-list"><div class="card-h"><h3>${ic("layers", 17)} ${t("Fənn materialları")}</h3><span class="small muted">${t("{n} material", { n: c.materials_list.length })}</span></div>
      ${c.materials_list.length ? html`<div class="table-wrap"><table class="table"><thead><tr><th>${t("Material")}</th><th>${t("Bölmə")}</th><th>${t("Anlayış")}</th><th>${t("Yüklənib")}</th><th></th></tr></thead><tbody>
      ${c.materials_list.map((m) => html`<tr class="click" data-view="${m.id}"><td><div class="row"><span class="stat-ic ic-blue" style="width:34px;height:34px">${ic("file", 16)}</span>
        <div><b class="small">${m.title}</b><div class="tiny muted">${m.filename} · ${t("{n}K simvol", { n: num(Math.round(m.chars / 100) / 10, 1) })}${m.refs ? html` · ${t("{n} əlavə mənbə", { n: m.refs })}` : ""}</div></div></div></td>
        <td>${num(m.chunk_count)}</td><td>${num(m.term_count)}</td><td class="small">${fmtDate(m.created_at)}</td>
        <td class="right nowrap"><button class="btn btn-sm" data-view="${m.id}">${ic("eye", 14)} ${t("Oxu")}</button>
          <button class="btn btn-sm btn-danger btn-icon" data-del="${m.id}" aria-label="${t("Sil")}">${ic("trash", 14)}</button></td></tr>`)}</tbody></table></div>`
        : html`<div class="card-b">${empty("file", t("Hələ material yoxdur"), t("Mühazirə və ya təqdimat faylı yükləyin — tutor və test studiyası məhz bu materiallara əsaslanır."))}</div>`}</div>

    <div class="stack"><div class="card" data-tour="upload"><div class="card-h"><h3>${ic("upload", 17)} ${t("Yeni material")}
        ${infoTip(t("Dəstəklənən formatlar: Word (DOCX), PowerPoint (PPTX), mətn (TXT) və Markdown (MD). Maksimum ölçü {mb} MB. PDF dəstəyi pilot mərhələsində əlavə olunacaq.", { mb: MAX_MB }))}</h3></div>
      <div class="card-b">
        <label class="dropzone" id="dz"><input type="file" id="file" accept="${FORMATS}" hidden><div style="color:var(--blue-700)">${ic("upload", 30)}</div>
          <b>${t("Faylı bura atın və ya seçin")}</b><div class="small muted mt-sm">${t("DOCX, PPTX, TXT, MD · maksimum {mb} MB", { mb: MAX_MB })}</div></label>
        <div id="proc" class="mt" aria-live="polite"></div></div></div>
      <div class="notice ai">${ic("sparkles", 16)}<div><b>${t("Məsləhət")}:</b> ${t("Əsas anlayışları “Termin — tərif” formatında yazın — AI onlardan həm tutorda, həm də test generasiyasında istifadə edir.")}</div></div>
      ${refCard(c.references, c.references_checked, { note: t("Tələbələr bu siyahını fənn səhifəsində görür.") })}</div></div>`);

  const proc = $("#proc", tgt), file = $("#file", tgt), dz = $("#dz", tgt);
  const STEPS = [t("Fayl yüklənir"), t("Mətn çıxarılır"), t("Bölmələrə ayrılır"), t("Anlayışlar çıxarılır"), t("Axtarış indeksi qurulur")];
  async function upload(f) {
    const ext = "." + (f.name.split(".").pop() || "").toLowerCase();
    if (!FORMATS.split(",").includes(ext)) return toast(t("Format dəstəklənmir. DOCX, PPTX, TXT və ya MD faylı seçin."), "err");
    if (f.size > MAX_MB * 1024 * 1024) return toast(t("Fayl çox böyükdür ({size}). Maksimum {mb} MB.", { size: fmtSize(f.size), mb: MAX_MB }), "err");
    const draw = (k, extra = "") => mount(proc, html`<div class="steps">${STEPS.map((s, i) => html`<div class="step ${i < k ? "ok" : i === k ? "run" : ""}"><span class="si">${i < k ? raw(ic("check", 12).__html) : ""}</span>${s}</div>`)}</div>${raw(extra)}`);
    draw(0);
    try {
      const request = api.post(`/api/courses/${c.id}/materials`, { filename: f.name, content_b64: await fileToB64(f) });
      for (let k = 1; k < STEPS.length; k++) { await sleep(420); draw(k); }
      const r = await request;
      draw(STEPS.length, html`<div class="notice ok mt">${ic("check", 16)}<div><b>${r.title}</b> ${t("hazırdır: {c} bölmə, {g} anlayış.", { c: r.chunks, g: r.terms })}
        ${r.glossary.length ? html`<div class="chips mt-sm">${r.glossary.slice(0, 8).map((g) => html`<span class="badge b-navy">${g}</span>`)}</div>` : ""}
        <div class="row mt-sm"><button class="btn btn-sm btn-ai" data-go="/teacher/studio?course=${c.id}&material=${r.id}">${ic("wand", 14)} ${t("Bu materialdan test yarat")}</button></div></div></div>`.__html);
      toast(t("Material emal olundu və tutora əlavə edildi"), "ok");
      const fresh = await api.get(`/api/courses/${c.id}`);
      c.materials_list = fresh.materials_list;
      const keep = proc.innerHTML; materialsTab(tgt, c); $("#proc", tgt).innerHTML = keep;
    } catch (e) { mount(proc, html`<div class="notice warn">${ic("alert", 16)}<div>${e.message}</div></div>`); }
  }
  file.addEventListener("change", () => file.files[0] && upload(file.files[0]));
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("drag"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
  dz.addEventListener("drop", (e) => { e.preventDefault(); dz.classList.remove("drag"); e.dataTransfer.files[0] && upload(e.dataTransfer.files[0]); });
  on(tgt, "click", "[data-view]", async (e, b) => {
    let m;
    try { m = await api.get(`/api/materials/${b.dataset.view}`); } catch (err) { return toast(err.message, "err"); }
    modal({ title: m.title, size: "lg", body: html`${m.glossary.length ? html`<div class="label mb-sm">${t("Çıxarılmış anlayışlar ({n})", { n: m.glossary.length })}</div>
        <div class="chips mb">${m.glossary.map((g) => html`<span class="badge b-navy" title="${g.definition}">${g.term}</span>`)}</div>` : ""}
      <div class="label mb-sm">${t("Bölmələr ({n}) — tutor bu hissələrə istinad edir", { n: m.chunks.length })}</div>
      <div class="stack">${m.chunks.map((ch) => html`<div class="card pad"><b>${t("{n}.", { n: ch.seq + 1 })} ${ch.heading}</b><div class="mt-sm small">${md(ch.text)}</div></div>`)}</div>
      ${m.references && m.references.length ? html`<div class="label mt mb-sm">${t("Mövzu üzrə əlavə oxu")}</div>${refList(m.references)}` : ""}` });
  });
  on(tgt, "click", "[data-del]", (e, b) => { e.stopPropagation(); modal({ title: t("Materialı silmək?"), size: "sm", body: html`<p>${t("Material və onun bölmələri tutorun bilik bazasından silinəcək. Bu əməliyyat geri qaytarılmır.")}</p>`,
    actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Sil"), cls: "btn-danger", onClick: async () => { await api.del(`/api/materials/${b.dataset.del}`); toast(t("Material silindi"), "ok"); go(`/teacher/course/${c.id}?tab=materials`); } }] }); });
}

function tutorTab(tgt, c) {
  const MODES = [["socratic", t("Sokratik"), t("Hazır cavab vermir; addım-addım ipucu və suallarla düşündürür. Ev tapşırıqları üçün tövsiyə olunur.")],
    ["explain", t("İzah"), t("Mövzunu qısa izah edir, mənbə göstərir və özünüyoxlama sualı verir.")],
    ["practice", t("Məşq"), t("Sual bankından sual verir və cavabı dərhal yoxlayır.")]];
  mount(tgt, html`<div class="grid g-12"><div class="card" data-tour="modes"><div class="card-b stack">
      <div class="label">${t("Aktiv rejimlər")}</div>
      ${MODES.map(([k, l, dsc]) => html`<label class="row card pad switch-row"><span class="switch"><input type="checkbox" data-mode="${k}" ${c.modes.includes(k) ? "checked" : ""}><span></span></span>
        <div class="grow"><b>${l}</b>${k === "socratic" ? html` <span class="badge b-navy">${t("Tövsiyə olunur")}</span>` : ""}<div class="small muted">${dsc}</div></div></label>`)}
      <div class="field"><label class="label" for="rules">${t("Fənnə xas qaydalar")}</label>
        <textarea class="textarea" id="rules" placeholder="${t("Məsələn: Vahidləri həmişə SI sistemində göstər.")}">${c.tutor_rules}</textarea>
        <span class="hint">${t("LLM qoşulduqda tutor bu qaydalara əməl edir.")}</span></div>
      <label class="row card pad switch-row"><span class="switch"><input type="checkbox" id="lock" ${c.tutor_locked ? "checked" : ""}><span></span></span>
        <div class="grow"><b>${t("Tutoru müvəqqəti bağla")}</b><div class="small muted">${t("Məsələn, auditoriyada test və ya imtahan zamanı.")}</div></div></label>
      <div class="row"><button class="btn btn-primary" id="save">${ic("check", 15)} ${t("Yadda saxla")}</button></div></div></div>
    <div class="stack"><div class="notice ai">${ic("shield", 16)}<div><b>${t("Qoruyucu qaydalar həmişə aktivdir:")}</b>
      <div class="small mt-sm">${[t("cavablar yalnız fənn materiallarına əsaslanır"), t("mənbəsiz fakt uydurulmur"), t("şəxsi məlumatlar maskalanır"), t("gündəlik limit: 50 sual")].map((x) => html`<div>· ${x}</div>`)}</div></div></div>
      <div class="notice info">${ic("info", 16)}<div>${t("Məhdudiyyətsiz söhbət botu öyrənməyə zərər verə bilər; Sokratik və materiala bağlı tutor isə nəticəni əhəmiyyətli dərəcədə yaxşılaşdırır.")}</div></div></div></div>`);
  $("#save", tgt).addEventListener("click", async () => {
    const modes = $$("[data-mode]", tgt).filter((x) => x.checked).map((x) => x.dataset.mode);
    if (!modes.length) return toast(t("Ən azı bir rejim seçin"), "err");
    try { await api.put(`/api/courses/${c.id}/tutor`, { modes, rules: $("#rules", tgt).value, locked: $("#lock", tgt).checked }); toast(t("Tənzimləmələr yadda saxlanıldı"), "ok"); }
    catch (e) { toast(e.message, "err"); }
  });
}

async function attendanceTab(tgt, c) {
  mount(tgt, skelLines(6));
  let a;
  try { a = await api.get(`/api/courses/${c.id}/attendance`); } catch (e) { return mount(tgt, failed(e.message)); }
  mount(tgt, html`<div class="grid g-12"><div class="card"><div class="card-h"><h3>${ic("calcheck", 17)} ${t("Son dərslər")}</h3><span class="small muted">${t("{n} tələbə", { n: c.students })}</span></div>
      ${a.lessons.length ? html`<div class="table-wrap"><table class="table"><thead><tr><th>${t("Tarix")}</th><th>${t("Dərs")}</th><th>${t("İştirak")}</th><th>${t("Qayıb")}</th><th>${t("Üzrlü")}</th><th>${t("Gecikmə")}</th><th>${t("Faiz")}</th></tr></thead><tbody>
      ${a.lessons.map((l) => { const tot = l.present + l.late + l.absent + l.excused; const p_ = Math.round((100 * (l.present + l.late)) / Math.max(1, tot));
        return html`<tr><td class="nowrap"><b>${fmtDate(l.day)}</b> <span class="tiny muted">${l.start}</span></td><td class="small">${l.kind} · <span class="muted">${l.topic}</span></td>
          <td>${num(l.present)}</td><td><span class="att-cell absent">${num(l.absent)}</span></td><td><span class="att-cell excused">${num(l.excused)}</span></td><td><span class="att-cell late">${num(l.late)}</span></td>
          <td style="min-width:110px"><div class="row">${progress(p_, p_ < 85 ? "coral" : "green")}<b class="small">${num(p_)}%</b></div></td></tr>`; })}</tbody></table></div>`
        : html`<div class="card-b">${empty("calcheck", t("Hələ dərs qeydə alınmayıb"), t("Dərslər keçirildikcə davamiyyət burada görünəcək."))}</div>`}</div>
    <div class="stack"><div class="card"><div class="card-h"><h3>${ic("heart", 17)} ${t("Üzrlü hesab edilənlər")}</h3></div><div class="card-b list">
      ${a.excused.length ? a.excused.map((x) => html`<div class="list-item"><div class="grow"><b class="small">${x.student}</b><div class="tiny muted">${fmtDate(x.day)} · ${x.kind}</div></div>${badge("excused")}</div>`)
        : empty("check", t("Üzrlü qayıb yoxdur"), t("Dekanlıq qayıbı üzrlü etdikdə burada görünəcək."))}</div></div>
      <div class="notice info">${ic("shield", 16)}<div>${t("Qayıbın səbəbi və təsdiqedici sənədlər (məsələn, həkim arayışı) məxfidir və yalnız dekanlıqda saxlanılır. Siz yalnız statusu görürsünüz.")}</div></div></div></div>`);
}

function insightsTab(tgt, c) {
  const i = c.insights;
  mount(tgt, html`<div class="grid g-4" data-tour="ins-stats">${stat("message", "ic-blue", cnt(i.questions_total), t("Sual (8 həftə)"))}
      ${stat("up", "ic-green", i.positive_rate != null ? cnt(i.positive_rate, { suffix: "%" }) : "—", t("Faydalı cavab"))}
      ${stat("shield", "ic-navy", cnt(i.cited_rate, { suffix: "%", dec: 1 }), t("Mənbəli cavab"))}
      ${stat("alert", "ic-amber", cnt(i.no_source_rate, { suffix: "%", dec: 1 }), t("Materialda tapılmayan"))}</div>
    <div class="grid g-2 mt"><div class="card"><div class="card-h"><h3>${t("Həftəlik sual sayı")}</h3></div><div class="card-b">
        ${i.weekly.some((x) => x) ? barChart({ labels: i.weekly.map((_, k) => t("{n}-h", { n: k + 1 })), values: i.weekly, color: "#2b5aa8", label: t("Həftələr üzrə sual sayı") })
          : empty("chart", t("Hələ məlumat yoxdur"), t("Tələbə sualları toplandıqca qrafik burada görünəcək."))}</div></div>
      <div class="card"><div class="card-h"><h3>${t("Mövzular üzrə suallar")}</h3></div><div class="card-b">
        ${i.top_topics.length ? i.top_topics.map((x) => html`<div class="bar-row"><span class="ellipsis small" title="${x.topic}">${x.topic}</span>${progress((x.n / i.top_topics[0].n) * 100)}<b class="right small">${num(x.n)}</b></div>`)
          : empty("message", t("Mövzu yoxdur"), t("Suallar toplandıqca ən çox soruşulan mövzular burada sıralanacaq."))}</div></div></div>
    <div class="card mt"><div class="card-h"><h3>${ic("alert", 17)} ${t("Materiallarda cavabı tapılmayan suallar")}</h3></div><div class="card-b">
      ${i.gaps.length ? html`<div class="list">${i.gaps.map((g) => html`<div class="list-item"><span class="stat-ic ic-amber" style="width:32px;height:32px">${ic("help", 15)}</span><div class="grow">${g}</div>
        <button class="btn btn-sm" data-go="/teacher/course/${c.id}?tab=materials">${t("Material əlavə et")}</button></div>`)}</div>`
        : empty("check", t("Boşluq yoxdur"), t("Soruşulan sualların hamısının cavabı yüklədiyiniz materiallarda var."))}
      <div class="tiny muted mt">${t("Bu siyahı materiallardakı boşluqları göstərir — tələbələrin şəxsi söhbətləri müəllimə göstərilmir.")}</div></div></div>`);
}

function toolsTab(tgt, c) {
  mount(tgt, html`<div class="row between wrap mb"><div class="small muted">${t("Tələbələr bu alətləri fənn səhifəsində görür.")}</div>
      <button class="btn btn-primary" data-go="/teacher/tools">${ic("cpu", 15)} ${t("Kataloqdan əlavə et")}</button></div>
    ${c.tools.length ? html`<div class="grid g-3">${c.tools.map((x) => html`<div class="tool"><div class="row"><span class="tl">${x.name.slice(0, 2)}</span>
      <div class="grow"><b>${x.name}</b><div class="tiny muted">${x.type} · ${x.pricing}</div></div></div><div class="small muted">${x.summary}</div>
      <div class="row wrap" style="margin-top:auto">${x.url ? html`<a class="btn btn-sm" href="${x.url}" target="_blank" rel="noopener noreferrer">${ic("external", 13)} ${t("Aç")}</a>` : ""}
      <button class="btn btn-sm btn-danger" data-rm="${x.key}">${ic("x", 13)} ${t("Fəndən çıxar")}</button></div></div>`)}</div>`
      : html`<div class="card">${empty("cpu", t("Alət əlavə edilməyib"), t("Texnoloji həllər kataloqundan fənninizə uyğun simulyasiya və ya laboratoriya aləti seçin."), { label: t("Kataloqa bax"), go: "/teacher/tools", icon: "cpu", cls: "btn" })}</div>`}`);
  on(tgt, "click", "[data-rm]", async (e, b) => { try { await api.post(`/api/courses/${c.id}/tools`, { tool_key: b.dataset.rm }); toast(t("Alət fəndən çıxarıldı"), "ok"); go(`/teacher/course/${c.id}?tab=tools`); } catch (err) { toast(err.message, "err"); } });
}

function testTab(tgt, c) {
  mount(tgt, html`<div class="notice info mb">${ic("info", 16)}<div>${t("Tutoru tələbə kimi sınayın: cavablar bu fənnin materiallarına və sizin qaydalarınıza əsaslanır.")}</div></div><div id="chat" data-tour="try-chat"></div>`);
  chatView($("#chat", tgt), { kind: "tutor", base: `/api/tutor/${c.id}`, modes: c.modes, suggestions: c.suggestions, canForward: false,
    title: t("Tutoru sınayın"), text: t("Tələbələrin verə biləcəyi bir sual yazın və cavabın keyfiyyətini yoxlayın.") });
}

// ---------------------------------------------------------------- Test studiyası
route("/teacher/studio", async (el, p, q) => {
  mount(el, loading());
  let courses;
  try { courses = await api.get("/api/courses"); } catch (e) { return mount(el, failed(e.message)); }
  if (!courses.length) return mount(el, html`${pageHead(t("Test studiyası"), "", "", crumbsT([t("Test studiyası")]))}
    ${empty("wand", t("Fənn tapılmadı"), t("Test yaratmaq üçün sizə təyin olunmuş fənn lazımdır."), { label: t("Fənlərim"), go: "/teacher/courses", icon: "book" })}`);
  const course = courses.find((x) => x.id === +q.course) || courses[0];
  let detail;
  try { detail = await api.get(`/api/courses/${course.id}`); } catch (e) { return mount(el, failed(e.message)); }
  const tab = q.tab || "generate";
  const TABS = [["generate", t("AI ilə yarat"), "wand"], ["bank", t("Sual bankı"), "layers"], ["quizzes", t("Testlər və nəticələr"), "chart"]];
  mount(el, html`${pageHead(t("Test studiyası"), t("AI materialdan sual yaradır, siz yoxlayıb təsdiqləyirsiniz."),
      html`<label class="sr-only" for="cs">${t("Fənn")}</label><select class="select" id="cs" style="width:auto" aria-label="${t("Fənn")}">${courses.map((x) => html`<option value="${x.id}" ${x.id === course.id ? "selected" : ""}>${x.name}</option>`)}</select>`,
      crumbsT([t("Test studiyası")]), { info: t("İş axını: AI ilə sual yaradın → yoxlayın → təsdiqləyin → testə yığın → nəticələrə baxın. Heç bir sual təsdiqinizdən əvvəl tələbəyə getmir.") })}
    <div class="table-wrap"><div class="tabs" role="tablist" data-tour="studio-tabs">${TABS.map(([k, l, i]) => html`<button class="tab ${tab === k ? "active" : ""}" role="tab" aria-selected="${tab === k}" data-go="/teacher/studio?course=${course.id}&tab=${k}">${ic(i, 15)} ${l}</button>`)}</div></div>
    <div id="tab"></div>`);
  $("#cs", el).addEventListener("change", (e) => go(`/teacher/studio?course=${e.target.value}&tab=${tab}`));
  const tgt = $("#tab", el);
  if (tab === "generate") genTab(tgt, course, detail, q);
  else if (tab === "bank") bankTab(tgt, course);
  else quizzesTab(tgt, course);
});

function genTab(tgt, course, detail, q) {
  mount(tgt, html`<div class="grid g-21"><div class="card brand-border" data-tour="gen-form" style="align-self:start"><div class="card-b stack">
      <div class="field"><label class="label" for="mat">${t("Material")}</label><select class="select" id="mat"><option value="">${t("Bütün materiallar")}</option>
        ${detail.materials_list.map((m) => html`<option value="${m.id}" ${+q.material === m.id ? "selected" : ""}>${m.title}</option>`)}</select></div>
      <div class="field"><span class="label">${t("Sual növləri")}</span><div class="chips">${[["mcq", t("Çoxseçimli")], ["tf", t("Doğru / Yanlış")], ["numeric", t("Hesablama")]].map(([k, l]) => html`<button class="chip on" data-type="${k}" aria-pressed="true">${l}</button>`)}</div></div>
      <div class="field"><label class="label" for="cnt">${t("Sual sayı")}</label><select class="select" id="cnt">${[3, 5, 6, 8, 10].map((n) => html`<option ${n === 6 ? "selected" : ""}>${n}</option>`)}</select></div>
      <button class="btn btn-ai btn-block" id="gen">${ic("sparkles", 16)} ${t("AI ilə sual yarat")}</button>
      <div class="small muted">${ic("cpu", 12)} ${S.app.engine.label}. ${t("Hesablama sualları hər dəfə fərqli rəqəmlərlə (parametrik) yaradılır.")}</div></div></div>
    <div id="out">${empty("wand", t("Suallar burada görünəcək"), t("Material və parametrləri seçib “AI ilə sual yarat” düyməsini basın."))}</div></div>`);
  on(tgt, "click", "[data-type]", (e, b) => { const onx = !b.classList.contains("on"); b.classList.toggle("on", onx); b.setAttribute("aria-pressed", String(onx)); });
  const out = $("#out", tgt);
  $("#gen", tgt).addEventListener("click", async () => {
    const types = $$("[data-type].on", tgt).map((b) => b.dataset.type);
    if (!types.length) return toast(t("Ən azı bir sual növü seçin"), "err");
    const msgs = [t("Material təhlil olunur…"), t("Əsas anlayışlar çıxarılır…"), t("Suallar və yanlış variantlar yaradılır…"), t("Mənbə uyğunluğu yoxlanılır…")];
    mount(out, html`<div class="card pad"><div class="row"><span class="spinner" style="color:var(--blue-700)"></span><b id="gm">${msgs[0]}</b></div><div class="mt">${skelLines(4)}</div></div>`);
    let k = 0;
    const iv = setInterval(() => { const g = $("#gm", out); if (g) g.textContent = msgs[++k % msgs.length]; }, 500);
    try {
      const [r] = await Promise.all([api.post("/api/studio/generate", { course_id: course.id, material_id: $("#mat", tgt).value || null, count: +$("#cnt", tgt).value, types }), sleep(1600)]);
      clearInterval(iv);
      renderDrafts(out, r.questions, course);
      toast(t("{n} sual qaralama kimi yaradıldı", { n: r.questions.length }), "ok");
    } catch (e) { clearInterval(iv); mount(out, html`<div class="notice warn">${ic("alert", 16)}<div>${e.message}</div></div>`); }
  });
}

function qCard(qq, actions = true) {
  return html`<div class="card qcard slide-up" data-q="${qq.id}">
    <div class="row between wrap"><div class="row wrap"><span class="badge b-navy">${QTYPE[qq.qtype]}</span><span class="badge b-gray">${qq.bloom}</span><span class="badge b-gray">${qq.difficulty}</span>
      ${qq.origin === "ai" ? html`<span class="badge b-blue">${ic("sparkles", 11)} ${t("AI")}</span>` : ""}${badge(qq.status)}</div>
      ${(qq.flags || []).includes("similar") ? html`<span class="badge b-amber">${ic("alert", 11)} ${t("Bankda oxşar sual var")}</span>`
        : (qq.flags || []).includes("source_ok") ? html`<span class="badge b-green">${ic("check", 11)} ${t("Mənbədə təsdiqlənib")}</span>` : ""}</div>
    <div class="mt-sm qcard-text">${md(qq.text)}</div>
    ${qq.qtype === "mcq" ? html`<div class="opts-mini">${qq.options.map((o, i) => html`<div class="om ${i === qq.answer ? "ok" : ""}">${LET[i]}) ${o}</div>`)}</div>`
      : html`<div class="opts-mini"><div class="om ok">${t("Cavab")}: ${qq.qtype === "tf" ? (qq.answer ? t("Doğru") : t("Yanlış")) : `${qq.answer}${qq.unit ? " " + qq.unit : ""}`}</div></div>`}
    <div class="small muted">${md(qq.explanation)}</div>${qq.source ? html`<div class="tiny muted mt-sm">${ic("book", 11)} ${qq.source.material} · ${qq.source.heading}</div>` : ""}
    ${actions ? html`<div class="row mt wrap">${qq.status === "draft" ? html`<button class="btn btn-sm btn-success" data-approve="${qq.id}">${ic("check", 14)} ${t("Təsdiqlə")}</button>` : ""}
      <button class="btn btn-sm" data-edit="${qq.id}">${ic("edit", 14)} ${t("Redaktə et")}</button>
      <button class="btn btn-sm btn-danger btn-icon" data-delq="${qq.id}" aria-label="${t("Sil")}">${ic("trash", 14)}</button></div>` : ""}</div>`;
}

function bindQActions(root, list, rerender) {
  on(root, "click", "[data-approve]", async (e, b) => { try { const nq = await api.put(`/api/questions/${b.dataset.approve}`, { status: "approved" }); Object.assign(list.find((x) => x.id === nq.id), nq); rerender(); toast(t("Sual təsdiqləndi və banka əlavə olundu"), "ok"); } catch (err) { toast(err.message, "err"); } });
  on(root, "click", "[data-delq]", async (e, b) => { try { await api.del(`/api/questions/${b.dataset.delq}`); list.splice(list.findIndex((x) => x.id === +b.dataset.delq), 1); rerender(); toast(t("Sual silindi"), "ok"); } catch (err) { toast(err.message, "err"); } });
  on(root, "click", "[data-edit]", (e, b) => {
    const qq = list.find((x) => x.id === +b.dataset.edit);
    modal({ title: t("Sualı redaktə et"), size: "lg", body: html`<div class="stack"><div class="field"><label class="label" for="et">${t("Sual mətni")}</label><textarea class="textarea" id="et">${qq.text}</textarea></div>
        ${qq.qtype === "mcq" ? html`<div class="field"><span class="label">${t("Variantlar (düzgün cavabı seçin)")}</span>${qq.options.map((o, i) => html`<div class="row"><input type="radio" name="ans" value="${i}" ${i === qq.answer ? "checked" : ""} aria-label="${t("Düzgün cavab {l}", { l: LET[i] })}"><input class="input" data-opt="${i}" value="${esc(o)}"></div>`)}</div>`
        : qq.qtype === "tf" ? html`<div class="field"><label class="label" for="etf">${t("Düzgün cavab")}</label><select class="select" id="etf"><option value="1" ${qq.answer ? "selected" : ""}>${t("Doğru")}</option><option value="0" ${qq.answer ? "" : "selected"}>${t("Yanlış")}</option></select></div>`
        : html`<div class="field"><label class="label" for="enum">${t("Düzgün cavab (ədəd)")}</label><input class="input" id="enum" value="${esc(String(qq.answer))}"></div>`}
        <div class="field"><label class="label" for="ee">${t("İzah")}</label><textarea class="textarea" id="ee">${qq.explanation}</textarea></div></div>`,
      actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Yadda saxla və təsdiqlə"), cls: "btn-primary", onClick: async (w) => {
        const body = { text: w.querySelector("#et").value, explanation: w.querySelector("#ee").value, status: "approved" };
        if (qq.qtype === "mcq") { body.options = [...w.querySelectorAll("[data-opt]")].map((x) => x.value); body.answer = +(w.querySelector("[name=ans]:checked") || { value: 0 }).value; }
        else if (qq.qtype === "tf") body.answer = w.querySelector("#etf").value === "1";
        else body.answer = parseFloat(String(w.querySelector("#enum").value).replace(",", "."));
        Object.assign(qq, await api.put(`/api/questions/${qq.id}`, body)); rerender(); toast(t("Yadda saxlanıldı"), "ok");
      } }] });
  });
}

function renderDrafts(out, list, course) {
  const rerender = () => {
    if (!list.length) return mount(out, empty("wand", t("Sual yaradılmadı"), t("Parametrləri dəyişib yenidən cəhd edin.")));
    mount(out, html`<div class="row between mb wrap"><b>${t("{n} sual · {a} təsdiqlənib", { n: list.length, a: list.filter((x) => x.status === "approved").length })}</b>
      <div class="row wrap"><button class="btn btn-sm" id="all">${ic("check", 14)} ${t("Hamısını təsdiqlə")}</button>
      <button class="btn btn-sm btn-primary" id="mk" ${list.some((x) => x.status === "approved") ? "" : "disabled"}>${ic("plus", 14)} ${t("Təsdiqlənənlərdən test yarat")}</button></div></div>
    <div class="stack">${list.map((x) => qCard(x))}</div>`);
  };
  rerender();
  bindQActions(out, list, rerender);
  on(out, "click", "#all", async () => { try { for (const x of list.filter((y) => y.status === "draft")) Object.assign(x, await api.put(`/api/questions/${x.id}`, { status: "approved" })); rerender(); toast(t("Bütün suallar təsdiqləndi"), "ok"); } catch (err) { toast(err.message, "err"); } });
  on(out, "click", "#mk", () => createQuizModal(course, list.filter((x) => x.status === "approved").map((x) => x.id)));
}

function createQuizModal(course, ids) {
  modal({ title: t("Test yarat və dərc et"), body: html`<div class="stack"><div class="field"><label class="label" for="qt">${t("Ad")}</label><input class="input" id="qt" value="${esc(t("Məşq: {course}", { course: course.name }))}"></div>
      <div class="grid g-3"><div class="field"><label class="label" for="qk">${t("Növ")}</label><select class="select" id="qk"><option value="practice">${t("Məşq")}</option><option value="graded">${t("Qiymətli")}</option></select></div>
        <div class="field"><label class="label" for="ql">${t("Vaxt (dəq)")}</label><input class="input" id="ql" type="number" value="${Math.max(5, ids.length * 2)}" min="1"></div>
        <div class="field"><label class="label" for="qa">${t("Cəhd sayı")}</label><input class="input" id="qa" type="number" value="3" min="1"></div></div>
      <div class="notice info">${ic("bell", 16)}<div>${t("{n} təsdiqlənmiş sual daxil ediləcək. Dərc olunan kimi fənnin bütün tələbələrinə bildiriş gedəcək.", { n: ids.length })}</div></div></div>`,
    actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Dərc et"), cls: "btn-primary", onClick: async (w) => {
      await api.post("/api/quizzes", { course_id: course.id, title: w.querySelector("#qt").value, kind: w.querySelector("#qk").value, time_limit: +w.querySelector("#ql").value, attempts: +w.querySelector("#qa").value, question_ids: ids });
      toast(t("Test dərc olundu — tələbələrə bildiriş göndərildi"), "ok"); go(`/teacher/studio?course=${course.id}&tab=quizzes`);
    } }] });
}

async function bankTab(tgt, course) {
  mount(tgt, skelLines(6));
  let list;
  try { list = await api.get(`/api/questions?course_id=${course.id}`); } catch (e) { return mount(tgt, failed(e.message)); }
  let filter = "all";
  const sel = new Set();
  const rerender = () => {
    const shown = list.filter((x) => filter === "all" || x.status === filter);
    mount(tgt, html`<div class="row between wrap mb"><div class="seg" role="tablist">${[["all", t("Hamısı")], ["draft", t("Qaralama")], ["approved", t("Təsdiqlənib")]].map(([k, l]) =>
      html`<button data-f="${k}" class="${filter === k ? "active" : ""}" role="tab" aria-selected="${filter === k}">${l} (${k === "all" ? list.length : list.filter((x) => x.status === k).length})</button>`)}</div>
      <button class="btn btn-primary" id="mk" ${sel.size ? "" : "disabled"}>${ic("plus", 15)} ${t("Seçilənlərdən test ({n})", { n: sel.size })}</button></div>
      ${shown.length ? html`<div class="grid g-2">${shown.map((x) => html`<div class="qwrap">${x.status === "approved" ? html`<label class="check qwrap-check"><input type="checkbox" data-sel="${x.id}" ${sel.has(x.id) ? "checked" : ""} aria-label="${t("Seç")}"></label>` : ""}${qCard(x)}</div>`)}</div>`
        : filter === "draft" ? empty("wand", t("Qaralama sual yoxdur"), t("“AI ilə yarat” bölməsində material seçib yeni suallar hazırlayın."), { label: t("AI ilə yarat"), go: `/teacher/studio?course=${course.id}&tab=generate`, icon: "wand", cls: "btn" })
        : filter === "approved" ? empty("check", t("Təsdiqlənmiş sual yoxdur"), t("Qaralama sualları yoxlayıb təsdiqlədikcə burada toplanacaq."))
        : empty("layers", t("Sual bankı boşdur"), t("“AI ilə yarat” bölməsindən materiallarınızdan ilk sualları hazırlayın."), { label: t("AI ilə yarat"), go: `/teacher/studio?course=${course.id}&tab=generate`, icon: "wand", cls: "btn" })}`);
  };
  rerender();
  bindQActions(tgt, list, rerender);
  on(tgt, "click", "[data-f]", (e, b) => { filter = b.dataset.f; rerender(); });
  on(tgt, "change", "[data-sel]", (e, b) => { b.checked ? sel.add(+b.dataset.sel) : sel.delete(+b.dataset.sel); const m = $("#mk", tgt); m.disabled = !sel.size; m.innerHTML = `${ic("plus", 15).__html} ${esc(t("Seçilənlərdən test ({n})", { n: sel.size }))}`; });
  on(tgt, "click", "#mk", () => { if (sel.size) createQuizModal(course, [...sel]); });
}

async function quizzesTab(tgt, course) {
  mount(tgt, skelLines(5));
  let qs;
  try { qs = (await api.get("/api/teacher/quizzes")).filter((x) => x.course_id === course.id); } catch (e) { return mount(tgt, failed(e.message)); }
  mount(tgt, qs.length ? html`<div class="card"><div class="table-wrap"><table class="table"><thead><tr><th>${t("Test")}</th><th>${t("Növ")}</th><th>${t("Sual")}</th><th>${t("Cəhd")}</th><th>${t("Orta nəticə")}</th><th></th></tr></thead><tbody>
    ${qs.map((x) => html`<tr><td><b>${x.title}</b><div class="tiny muted">${fmtDate(x.created_at)}</div></td><td><span class="badge ${x.kind === "graded" ? "b-coral" : "b-blue"}">${x.kind === "graded" ? t("Qiymətli") : t("Məşq")}</span></td>
      <td>${num(x.questions)}</td><td>${num(x.attempts_count)}</td><td>${x.avg != null ? html`<div class="row" style="min-width:140px">${progress(x.avg)}<b>${num(x.avg)}%</b></div>` : "—"}</td>
      <td class="right"><button class="btn btn-sm" data-res="${x.id}">${ic("chart", 14)} ${t("Nəticələr")}</button></td></tr>`)}</tbody></table></div></div>`
    : empty("quiz", t("Hələ test yoxdur"), t("Təsdiqlənmiş suallardan test yığıb dərc edin — nəticələr və statistika burada görünəcək."), { label: t("Sual bankı"), go: `/teacher/studio?course=${course.id}&tab=bank`, icon: "layers", cls: "btn" }));
  on(tgt, "click", "[data-res]", async (e, b) => {
    let r;
    try { r = await api.get(`/api/quizzes/${b.dataset.res}/results`); } catch (err) { return toast(err.message, "err"); }
    modal({ title: r.quiz.title, size: "lg", body: html`<div class="grid g-3 mb">${stat("users", "ic-blue", cnt(r.attempts), t("Cəhd"))}${stat("target", "ic-green", r.avg != null ? cnt(r.avg, { suffix: "%" }) : "—", t("Orta nəticə"))}${stat("quiz", "ic-navy", cnt(r.questions.length), t("Sual"))}</div>
      ${r.attempts ? html`<div class="label mb-sm">${t("Balların paylanması")}</div>${barChart({ labels: r.labels, values: r.buckets, colors: ["#d64045", "#e8823a", "#e0b43a", "#5a9bd3", "#2b5aa8", "#0e9f6e"], height: 190, label: t("Bal aralıqları üzrə tələbə sayı") })}
      <div class="label mb-sm mt">${t("Suallar üzrə düzgün cavab faizi")}</div><div class="stack sm">${r.questions.map((x, i) => html`<div class="bar-row qstat"><span class="ellipsis small" title="${esc(x.text)}">${t("{n}.", { n: i + 1 })} ${x.text.replace(/```[\s\S]*?```/g, "").slice(0, 90)}</span>${progress(x.correct_rate || 0)}<b class="right">${x.correct_rate != null ? num(x.correct_rate) + "%" : "—"}</b></div>`)}</div>
      <div class="notice info mt">${ic("info", 16)}<div>${t("90%-dən yuxarı sual çox asan ola bilər; 30%-dən aşağı çətin və ya qeyri-dəqiqdir. Ətraflı məlumat AI Akademiyada.")}</div></div>`
        : empty("users", t("Hələ cəhd yoxdur"), t("Tələbələr testi həll etdikdə nəticə statistikası burada görünəcək."))}` });
  });
}

// ---------------------------------------------------------------- tələbə sualları (inbox)
route("/teacher/questions", async (el) => {
  mount(el, loading());
  let qs;
  try { qs = await api.get("/api/teacher/questions"); } catch (e) { return mount(el, failed(e.message)); }
  let filter = "all";
  const render = () => {
    const shown = qs.filter((x) => filter === "all" || x.status === filter);
    const openN = qs.filter((x) => x.status === "open").length;
    mount(el, html`${pageHead(t("Tələbə sualları"), t("AI tutordan sizə yönləndirilmiş suallar. Tələbə anonimlik seçə bilər; cavabınız bildiriş kimi çatdırılır."), "", crumbsT([t("Tələbə sualları")]),
        { info: t("Yalnız tələbənin müəllimə yönləndirdiyi suallar sizə gəlir — tutorla adi söhbətlər məxfidir.") })}
      <div class="row between wrap mb" data-tour="filters"><div class="seg" role="tablist">${[["all", t("Hamısı"), qs.length], ["open", t("Cavab gözləyən"), openN], ["answered", t("Cavablandırılıb"), qs.length - openN]].map(([k, l, n]) =>
        html`<button data-f="${k}" class="${filter === k ? "active" : ""}" role="tab" aria-selected="${filter === k}">${l} (${n})</button>`)}</div></div>
      <div class="stack" data-tour="q-list">${shown.length ? shown.map((q) => html`<div class="card pad slide-up"><div class="row between wrap"><div class="row"><span class="avatar" style="background:${q.anonymous ? "#9aa3b8" : "#2b5aa8"}">${q.anonymous ? "?" : q.student.split(" ").map((x) => x[0]).join("")}</span>
        <div><b>${q.student}</b><div class="small muted">${q.course} · ${ago(q.created_at)}</div></div></div>${badge(q.status)}</div>
        <p class="q-body">${q.question}</p>${q.context ? html`<div class="small muted">${ic("sparkles", 12)} ${q.context.slice(0, 160)}</div>` : ""}
        ${q.status === "answered" ? html`<div class="notice ok mt">${ic("check", 16)}<div><b>${t("Cavabınız")}:</b> ${q.answer}</div></div>`
          : html`<div class="row mt top"><button class="btn btn-primary" data-reply="${q.id}">${ic("send", 15)} ${t("Cavabla")}</button></div>`}</div>`)
        : filter === "open" ? empty("check", t("Cavab gözləyən sual yoxdur"), t("Bütün suallar cavablandırılıb."))
        : filter === "answered" ? empty("message", t("Cavablandırılmış sual yoxdur"), t("Cavabladığınız suallar burada arxivlənir."))
        : empty("inbox", t("Hələ sual yoxdur"), t("Tələbələr tutordan sizə sual yönləndirdikdə burada görünəcək."))}</div>`);
  };
  render();
  on(el, "click", "[data-f]", (e, b) => { filter = b.dataset.f; render(); });
  on(el, "click", "[data-reply]", (e, b) => {
    const q = qs.find((x) => x.id === +b.dataset.reply);
    modal({ title: t("Sualı cavablandır"), size: "lg", body: html`<div class="row mb"><span class="avatar" style="background:${q.anonymous ? "#9aa3b8" : "#2b5aa8"}">${q.anonymous ? "?" : q.student.split(" ").map((x) => x[0]).join("")}</span>
        <div><b>${q.student}</b><div class="small muted">${q.course} · ${ago(q.created_at)}</div></div></div>
      <div class="notice info mb">${ic("help", 15)}<div>${q.question}</div></div>
      <div class="field"><label class="label" for="ans">${t("Cavabınız")}</label><textarea class="textarea" id="ans" style="min-height:120px" placeholder="${t("Cavabınızı yazın…")}"></textarea></div>`,
      actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Göndər"), cls: "btn-primary", onClick: async (w) => {
        const v = w.querySelector("#ans").value.trim();
        if (!v) { toast(t("Cavab boş ola bilməz"), "err"); return false; }
        await api.post(`/api/teacher/questions/${q.id}/answer`, { answer: v });
        q.status = "answered"; q.answer = v; toast(t("Cavab tələbəyə göndərildi"), "ok"); refreshBadges(); render();
      } }] });
  });
});

// ---------------------------------------------------------------- page guides
registerTour("teacher.home", { route: "/teacher", roles: ["teacher"], title: t("Əsas səhifə"), group: t("Əsas"), icon: "home", go: "/teacher", steps: [
  { sel: "[data-tour=hero]", title: t("Sürətli başlanğıc"), text: t("Bir toxunuşla test studiyasını və ya sillabus köməkçisini açın.") },
  { sel: "[data-tour=stats]", title: t("Göstəricilər"), text: t("Tutor fəallığı, mənbəli cavablar və cavab gözləyən tələbə sualları.") },
  { sel: "#insights-card", title: t("Tutor müşahidələri"), text: t("Ən çox soruşulan mövzular və materiallardakı boşluqlar. Şəxsi söhbətlər göstərilmir.") },
  { sel: "[data-tour=courses]", title: t("Fənlərim"), text: t("Hər fənni idarə edin: material, tutor rejimləri, davamiyyət və analitika.") },
] });
registerTour("teacher.courses", { route: "/teacher/courses", roles: ["teacher"], title: t("Fənlərim"), group: t("Tədris"), icon: "book", go: "/teacher/courses", steps: [
  { sel: "[data-tour=course-grid]", title: t("Fənlər"), text: t("Hər kartda tələbə sayı, material və tutor statusu göstərilir. Karta toxunub fənni idarə edin.") },
] });
registerTour("teacher.course", { route: "/teacher/course/:id", roles: ["teacher"], title: t("Fənn səhifəsi"), group: t("Tədris"), icon: "book", go: "/teacher/course/1", steps: [
  { sel: "[data-tour=tabs]", title: t("Bölmələr"), text: t("Material, tutor rejimləri, davamiyyət, analitika, texnoloji həllər və tutoru sınama.") },
  { sel: "[data-tour=mat-list]", title: t("Materiallar"), text: t("Tutor və test studiyası məhz bu materiallara əsaslanır.") },
  { sel: "[data-tour=upload]", title: t("Material yüklə"), text: t("Dəstəklənən formatlarda fayl yükləyin; AI onu bölmələrə ayırıb anlayışları çıxarır.") },
  { sel: "[data-tour=refs]", title: t("Tövsiyə olunan mənbələr"), text: t("Fənn üçün yoxlanılmış açıq dərsliklər və kurslar. Tələbələr eyni siyahını görür.") },
] });
registerTour("teacher.studio", { route: "/teacher/studio", roles: ["teacher"], title: t("Test studiyası"), group: t("Tədris"), icon: "wand", go: "/teacher/studio", steps: [
  { sel: "[data-tour=studio-tabs]", title: t("İş axını"), text: t("AI ilə yarat → sual bankı → testlər və nəticələr.") },
  { sel: "[data-tour=gen-form]", title: t("AI ilə yarat"), text: t("Materialı və parametrləri seçin — AI qaralama suallar hazırlayır.") },
] });
registerTour("teacher.questions", { route: "/teacher/questions", roles: ["teacher"], title: t("Tələbə sualları"), group: t("Tədris"), icon: "inbox", go: "/teacher/questions", steps: [
  { sel: "[data-tour=filters]", title: t("Filtrlər"), text: t("Sualları cavab gözləyən və cavablandırılmış kimi süzün.") },
  { sel: "[data-tour=q-list]", title: t("Cavablandırma"), text: t("“Cavabla” düyməsi ilə cavabınızı yazın; tələbəyə bildiriş kimi çatır.") },
] });
