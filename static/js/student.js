import { api, html, raw, mount, on, md, ic, toast, modal, route, go, S, pageHead, badge, fmtDate, fmtDateTime, fmtDayLong, ago, ring, progress, loading, empty,
  failed, infoTip, greeting, QTYPE, cover, datebox, cnt, num, registerTour, openFile, openSyllabus, t, $, $$, esc, isoDay } from "./core.js";
import { chatView } from "./chat.js";
import { achievementsTeaser } from "./achievements.js";

const LET = "ABCD";
// Lesson kind codes map to a tone; labels come localized from the server.
const KIND_TONE = { lecture: "b-navy", seminar: "b-blue", lab: "b-teal", Mühazirə: "b-navy", Məşğələ: "b-blue", Laboratoriya: "b-teal" };
const kindTone = (k) => KIND_TONE[k] || "b-gray";

// ---------------------------------------------------------------- shared exports (other modules import these)
export function stat(icn, cls, v, label, go_) {
  return html`<div class="card stat slide-up ${go_ ? "hover" : ""}" ${go_ ? raw(`data-go="${go_}"`) : ""}><span class="stat-ic ${cls}">${ic(icn, 21)}</span>
    <div><div class="stat-v">${v}</div><div class="stat-l">${label}</div></div></div>`;
}
const crumbsS = (...c) => [[t("Əsas"), "/student"], ...c];

export function lessonRow(x) {
  return html`<div class="lesson ${x.state || ""}"><div class="lt">${x.start}<span>${x.end}</span></div><div class="lbar" style="background:${x.color}"></div>
    <div class="grow"><div class="row wrap"><b>${x.course}</b><span class="badge ${kindTone(x.kind)}">${x.kind}</span>${x.state === "now" ? html`<span class="badge b-coral">${t("indi")}</span>` : ""}</div>
    <div class="small muted">${ic("pin", 12)} ${x.room}${x.teacher ? " · " + x.teacher : ""}</div></div></div>`;
}

// ---------------------------------------------------------------- dashboard
route("/student", async (el) => {
  mount(el, loading());
  let d;
  try { d = await api.get("/api/student/home"); } catch (e) { return mount(el, failed(e.message)); }
  const first = d.user.full_name.split(" ")[0];
  mount(el, html`
    <div class="hero slide-up" data-tour="hero">
      <div class="row between wrap"><div><div class="small" style="opacity:.8">${fmtDayLong(new Date())} · ${S.app.semester}</div>
        <h2 class="mt-sm">${greeting()}, ${first}</h2>
        <p>${t("Sualınızı AI tutora verin — cavablar fənn materiallarına əsaslanır.")}</p></div></div>
      <form class="row mt wrap" id="quick" style="max-width:780px">
        <select class="select" id="qc" style="max-width:260px" aria-label="${t("Fənn")}">${d.courses.map((c) => html`<option value="${c.id}">${c.name}</option>`)}</select>
        <input class="input grow" id="qq" placeholder="${t("Məsələn: Paralel birləşmədə müqavimət necə hesablanır?")}" maxlength="500" aria-label="${t("Sual")}" style="min-width:220px">
        <button class="btn btn-accent">${ic("sparkles", 16)} ${t("Soruş")}</button>
      </form>
    </div>
    ${d.unexcused ? html`<div class="notice coral mt" data-tour="unexcused">${ic("calcheck", 18)}<div class="grow"><b>${t("{n} üzrsüz qayıbınız var.", { n: d.unexcused })}</b>
      ${t("Təsdiqedici sənəd varsa, onu yükləyin — dekanlıq təsdiqlədikdə qayıb üzrlü sayılır.")}</div>
      <button class="btn btn-accent btn-sm" data-go="/student/attendance">${t("Davamiyyətə bax")}</button></div>` : ""}
    <div class="tile-grid mt" data-tour="quick-tiles">
      ${[["file", t("Arayış sifariş et"), t("Təyinata uyğun, QR kodlu"), "/student/services?new=enrollment_certificate", "ic-blue"],
         ["heart", t("Qayıbı üzrlü et"), t("Təsdiqedici sənədi yükləyin"), "/student/services?new=absence_excuse", "ic-coral"],
         ["calcheck", t("Dərslərdən icazə"), t("Olimpiada, yarış, konfrans"), "/student/services?new=leave_permission", "ic-green"],
         ["grid", t("Bütün e-xidmətlər"), t("Onlayn xidmətlərin tam siyahısı"), "/student/services", "ic-navy"]].map(([i, tt, s, g, c]) =>
        html`<button class="tile" data-go="${g}"><span class="stat-ic ${c}" style="width:38px;height:38px">${ic(i, 18)}</span><div><b>${tt}</b><br><span>${s}</span></div></button>`)}
    </div>
    <div class="grid g-12 mt">
      <div class="stack">
        <div class="card" id="today-card"><div class="card-h"><h3>${ic("calendar", 17)} ${t("Bu gün")}</h3><a class="small" href="#/student/schedule">${t("Həftəlik cədvəl")} ${ic("arrow", 13)}</a></div>
          <div class="card-b today-line">${d.today.length ? d.today.map(lessonRow)
            : empty("calendar", t("Bu gün dərs yoxdur"), t("Həftənin digər günlərinə dərs cədvəlindən baxın."), { label: t("Dərs cədvəli"), go: "/student/schedule", icon: "calendar", cls: "btn" })}</div></div>
        <div class="card" data-tour="courses"><div class="card-h"><h3>${ic("book", 17)} ${t("Fənlərim")}</h3><a class="small" href="#/student/courses">${t("Hamısı")} ${ic("arrow", 13)}</a></div>
          <div class="card-b">${d.courses.length ? html`<div class="grid g-3">${d.courses.map((c) => courseMiniCard(c))}</div>`
            : empty("book", t("Bu semestr üçün fənn yoxdur"), t("Qeydiyyat tamamlandıqda fənləriniz burada görünəcək."))}</div></div>
        <div class="card"><div class="card-h"><h3>${ic("news", 17)} ${t("Xəbərlər və elanlar")}</h3><a class="small" href="#/news">${t("Bütün xəbərlər")} ${ic("arrow", 13)}</a></div>
          <div class="card-b">${d.news.length ? html`<div class="grid g-2">${d.news.map((n) => html`<a class="news-card news-row" href="#/news/${n.id}">
            ${raw(cover(JSON.parse(n.cover || "{}"), 26, "news-cover").__html)}
            <div class="news-body"><div class="row wrap">${n.pinned ? html`<span class="badge b-coral">${ic("pin", 11)} ${t("Sabitlənib")}</span>` : ""}<span class="badge b-gray">${(S.app.news_kinds || {})[n.kind] || n.kind}</span></div>
            <b>${n.title}</b><span class="tiny muted">${ago(n.published_at)}</span></div></a>`)}</div>`
            : empty("news", t("Hələ xəbər yoxdur"))}</div></div>
      </div>
      <div class="stack">
        <div class="grid g-2">${stat("message", "ic-blue", cnt(d.stats.tutor_week), t("Tutora sual (həftə)"), "/student/tutor")}
          ${stat("target", "ic-green", d.stats.avg_score != null ? cnt(d.stats.avg_score, { suffix: "%" }) : "—", t("Orta test nəticəsi"), "/student/quizzes")}</div>
        <div class="card brand-border" data-tour="ai-tip"><div class="card-h"><h3>${ic("sparkles", 17)} ${t("AI tövsiyəsi")}</h3></div><div class="card-b">
          ${d.weak_topics.length ? html`<p class="small muted" style="margin:0 0 6px">${t("Son testlərə əsasən bu mövzuları təkrarlamaq faydalı olar:")}</p>
            ${d.weak_topics.map((w) => html`<div class="list-item"><span class="stat-ic ic-amber" style="width:34px;height:34px">${ic("target", 16)}</span>
              <div class="grow"><b class="small">${w.topic}</b><div class="tiny muted">${t("{n} səhv cavab", { n: w.n })}</div></div>
              <button class="btn btn-sm" data-go="/student/tutor/${w.course_id}?q=${encodeURIComponent(w.topic + " mövzusunu izah et")}&mode=explain">${t("Təkrarla")}</button></div>`)}`
            : empty("sparkles", t("Hələ tövsiyə yoxdur"), t("Bir məşq testi həll edin — nəticəyə görə fərdi tövsiyə hazırlanacaq."), { label: t("Testlərə bax"), go: "/student/quizzes", icon: "quiz", cls: "btn-sm" })}</div></div>
        <div class="card"><div class="card-h"><h3>${ic("quiz", 17)} ${t("Gözləyən testlər")}</h3><a class="small" href="#/student/quizzes">${t("Hamısı")} ${ic("arrow", 13)}</a></div>
          <div class="card-b list">${d.quizzes.length ? d.quizzes.map((q) => html`<div class="list-item click" data-go="/student/quiz/${q.id}">
            <span class="course-ic sm" style="background:${q.color}">${ic("quiz", 16)}</span>
            <div class="grow"><b class="small">${q.title}</b><div class="tiny muted">${q.course} · ${t("{n} sual", { n: q.questions })} · ${t("{n} dəq", { n: q.time_limit })}</div></div>
            <span class="badge ${q.kind === "graded" ? "b-coral" : "b-blue"}">${q.kind === "graded" ? t("Qiymətli") : t("Məşq")}</span></div>`)
            : empty("check", t("Gözləyən test yoxdur"), t("Yeni test təyin olunduqda burada görünəcək."))}</div></div>
        <div class="card"><div class="card-h"><h3>${ic("inbox", 17)} ${t("Müraciətlərim")}</h3><a class="small" href="#/student/requests">${t("Hamısı")} ${ic("arrow", 13)}</a></div>
          <div class="card-b list">${d.requests.length ? d.requests.map((r) => html`<div class="list-item click" data-go="/student/requests/${r.id}">
            <span class="stat-ic ic-blue" style="width:34px;height:34px">${ic(r.icon, 16)}</span><div class="grow"><b class="small ellipsis" style="display:block">${r.type_name}</b>
            <div class="tiny muted">${t("№ {id}", { id: r.id })} · ${ago(r.created_at)}</div></div>${badge(r.status)}</div>`)
            : empty("inbox", t("Hələ müraciətiniz yoxdur"), t("E-xidmətlər bölməsindən arayış, icazə və digər müraciətləri göndərə bilərsiniz."), { label: t("E-xidmətlər"), go: "/student/services", icon: "grid", cls: "btn-sm" })}</div></div>
        <div id="ach-teaser"></div>
        <div class="card pad"><div class="row"><span class="stat-ic ic-navy">${ic("help", 20)}</span><div class="grow"><b>${t("Kampus köməkçisi")}</b>
          <div class="small muted">${t("Qaydalar, arayışlar, təqaüd — 7/24")}</div></div><button class="btn btn-sm" data-go="/student/campus">${t("Aç")}</button></div></div>
      </div>
    </div>`);
  $("#quick", el).addEventListener("submit", (e) => {
    e.preventDefault();
    const q = $("#qq", el).value.trim();
    go(`/student/tutor/${$("#qc", el).value}${q ? "?q=" + encodeURIComponent(q) : ""}`);
  });
  achievementsTeaser(3).then((h) => { const box = $("#ach-teaser", el); if (box && h) mount(box, h); else if (box) box.remove(); });
});

function courseMiniCard(c) {
  return html`<div class="card hover course-mini" data-go="/student/course/${c.id}"><div class="course-strip" style="background:${c.color}"></div>
    <div class="course-mini-b"><div class="row"><span class="course-ic" style="background:${c.color}">${c.code.split("-")[0]}</span>
      <div class="grow"><b class="course-mini-t">${c.name}</b><span class="tiny muted">${c.teacher}</span></div></div>
      <div class="row between mt small"><span class="muted">${t("Davamiyyət")}</span><b style="color:${c.attendance.rate < 80 ? "var(--red)" : "inherit"}">${num(c.attendance.rate)}%</b></div>
      ${progress(c.attendance.rate, c.attendance.rate < 80 ? "coral" : "green")}
      <div class="row between mt-sm small"><span class="muted">${t("Test irəliləyişi")}</span><b>${num(c.progress)}%</b></div>${progress(c.progress)}</div></div>`;
}

// ---------------------------------------------------------------- courses
route("/student/courses", async (el) => {
  mount(el, loading());
  let cs;
  try { cs = await api.get("/api/courses"); } catch (e) { return mount(el, failed(e.message)); }
  const credits = cs.reduce((a, c) => a + c.credits, 0);
  mount(el, html`${pageHead(t("Fənlərim"), t("{sem} · {c} fənn · {k} kredit", { sem: S.app.semester, c: cs.length, k: credits }), "", crumbsS([t("Fənlərim")]),
      { info: t("Fənn kartından materiallara, testlərə, davamiyyətə və AI tutora keçə bilərsiniz. Fənn materialları tədris dilində təqdim olunur.") })}
    ${cs.length ? html`<div class="grid g-3" data-tour="course-grid">${cs.map((c) => html`<div class="card hover slide-up course-full" data-go="/student/course/${c.id}">
      <div class="course-strip" style="background:${c.color}"></div><div class="card-b">
        <div class="row"><span class="course-ic" style="background:${c.color}">${c.code.split("-")[0]}</span><div class="grow"><b class="course-full-t">${c.name}</b>
          <span class="small muted">${c.teacher} · ${t("{n} kredit", { n: c.credits })}</span></div></div>
        ${c.next ? html`<div class="notice info mt tight">${ic("clock", 14)}<div class="small">${t("Növbəti dərs")}: <b>${c.next.weekday}, ${c.next.start}</b> · ${c.next.room}</div></div>` : ""}
        <div class="grid g-2 mt"><div><div class="tiny muted">${t("Davamiyyət")}</div><b>${num(c.attendance.rate)}%</b> ${c.attendance.absent ? html`<span class="badge b-red">${t("{n} qayıb", { n: c.attendance.absent })}</span>` : ""}</div>
          <div><div class="tiny muted">${t("Materiallar")}</div><b>${num(c.materials)}</b></div></div>
        <div class="row mt wrap"><button class="btn btn-sm btn-ai grow" data-go="/student/tutor/${c.id}">${ic("sparkles", 14)} ${t("AI tutor")}</button>
          <button class="btn btn-sm grow" data-go="/student/course/${c.id}">${t("Fənn səhifəsi")}</button></div></div></div>`)}</div>`
      : empty("book", t("Bu semestr üçün fənn yoxdur"), t("Qeydiyyat tamamlandıqda fənləriniz burada görünəcək."))}`);
});

route("/student/course/:id", async (el, p) => {
  mount(el, loading());
  let c;
  try { c = await api.get(`/api/courses/${p.id}`); } catch (e) { return mount(el, failed(e.message)); }
  const a = c.attendance;
  mount(el, html`
    ${pageHead(c.name, t("{code} · {k} kredit · {teacher}", { code: c.code, k: c.credits, teacher: `${c.teacher}, ${c.teacher_title}` }),
      html`${c.syllabus_id ? html`<button class="btn" data-syl="${c.syllabus_id}">${ic("layers", 15)} ${t("Sillabus")}</button>` : ""}<button class="btn btn-ai" data-go="/student/tutor/${c.id}">${ic("sparkles", 16)} ${t("AI tutora soruş")}</button>`,
      crumbsS([t("Fənlərim"), "/student/courses"], [c.name]), { info: t("Materiallar və test sualları fənnin tədris dilində təqdim olunur.") })}
    <div class="grid g-12">
      <div class="stack">
        <div class="card" data-tour="materials"><div class="card-h"><h3>${ic("layers", 17)} ${t("Mühazirə materialları")}</h3><span class="small muted">${t("{n} material", { n: c.materials_list.length })}</span></div>
          <div class="card-b list">${c.materials_list.length ? c.materials_list.map((m) => html`<div class="list-item click" data-mat="${m.id}"><span class="stat-ic ic-blue" style="width:36px;height:36px">${ic("file", 17)}</span>
            <div class="grow"><b class="small">${m.title}</b><div class="tiny muted">${t("{n} bölmə", { n: m.chunk_count })} · ${t("{n} anlayış", { n: m.term_count })} · ${fmtDate(m.created_at)}</div></div>
            <button class="btn btn-sm">${ic("eye", 14)} ${t("Oxu")}</button></div>`)
            : empty("file", t("Hələ material yoxdur"), t("Müəllim material yüklədikcə burada görünəcək."))}</div></div>
        <div class="card"><div class="card-h"><h3>${ic("quiz", 17)} ${t("Testlər")}</h3></div><div class="card-b list">
          ${c.quizzes.length ? c.quizzes.map((q) => html`<div class="list-item"><span class="course-ic sm" style="background:${c.color}">${ic("quiz", 15)}</span>
            <div class="grow"><b class="small">${q.title}</b><div class="tiny muted">${t("{n} sual", { n: q.questions })} · ${t("{n} dəq", { n: q.time_limit })} · ${t("cəhd {u}/{a}", { u: q.used, a: q.attempts })}</div></div>
            ${q.best != null ? html`<span class="badge b-green">${num(q.best)}%</span>` : ""}
            ${q.can_start ? html`<button class="btn btn-sm btn-primary" data-go="/student/quiz/${q.id}">${t("Başla")}</button>`
              : q.last_attempt ? html`<button class="btn btn-sm" data-go="/student/attempt/${q.last_attempt}">${t("Nəticə")}</button>` : html`<span class="badge b-gray">${t("Cəhd limiti bitib")}</span>`}</div>`)
            : empty("quiz", t("Hələ test yoxdur"), t("Müəllim test təyin etdikdə burada görünəcək."))}</div></div>
      </div>
      <div class="stack">
        <div class="card" data-tour="attendance-card"><div class="card-h"><h3>${ic("calcheck", 17)} ${t("Davamiyyət")}</h3><a class="small" href="#/student/attendance">${t("Ətraflı")} ${ic("arrow", 13)}</a></div><div class="card-b">
          <div class="row">${ring(a.rate, 74, a.rate < 80 ? "var(--red)" : "var(--green)")}<div class="grow small"><div>${t("Keçirilib")}: <b>${num(a.total)}</b> ${t("dərs")}</div>
            <div>${t("Qayıb")}: <b style="color:var(--red)">${num(a.absent)}</b> · ${t("Üzrlü")}: <b>${num(a.excused)}</b> · ${t("Gecikmə")}: <b>${num(a.late)}</b></div>
            <div class="muted">${t("İcazə verilən həd: {n} dərs (25%)", { n: a.limit })}</div></div></div></div></div>
        <div class="card"><div class="card-h"><h3>${ic("calendar", 17)} ${t("Dərs cədvəli")}</h3></div><div class="card-b list">${c.schedule.length ? c.schedule.map((x) => html`<div class="list-item">
          <div class="grow"><b class="small">${x.weekday_name}</b> <span class="small muted">${x.start}–${x.end}</span><div class="tiny muted">${x.room}</div></div><span class="badge ${kindTone(x.kind)}">${x.kind}</span></div>`)
          : empty("calendar", t("Cədvəl məlumatı yoxdur"))}</div></div>
        ${c.tools.length ? html`<div class="card"><div class="card-h"><h3>${ic("cpu", 17)} ${t("Müəllimin tövsiyə etdiyi həllər")}</h3></div><div class="card-b list">${c.tools.map((tool) => html`<div class="list-item">
          <span class="tool"><span class="tl">${tool.name.slice(0, 2)}</span></span><div class="grow"><b class="small">${tool.name}</b><div class="tiny muted">${tool.type} · ${tool.pricing}</div></div>
          ${tool.url ? html`<a class="btn btn-sm" href="${tool.url}" target="_blank" rel="noopener noreferrer">${ic("external", 13)} ${t("Aç")}</a>` : ""}</div>`)}</div></div>` : ""}
      </div></div>`);
  on(el, "click", "[data-syl]", (e, b) => openSyllabus(+b.dataset.syl, c.name));
  on(el, "click", "[data-mat]", async (e, b) => {
    let m;
    try { m = await api.get(`/api/materials/${b.dataset.mat}`); } catch (err) { return toast(err.message, "err"); }
    modal({ title: m.title, size: "lg", body: html`${m.glossary.length ? html`<div class="label mb-sm">${t("Əsas anlayışlar")}</div><div class="chips mb">${m.glossary.map((g) => html`<span class="badge b-navy" title="${g.definition}">${g.term}</span>`)}</div>` : ""}
      <div class="stack">${m.chunks.map((ch) => html`<div class="card pad"><b>${ch.heading}</b><div class="mt-sm">${md(ch.text)}</div></div>`)}</div>`,
      actions: [{ label: t("Bağla") }, { html: `${ic("sparkles", 15).__html} ${esc(t("Bu mövzunu tutorla öyrən"))}`, cls: "btn-ai", onClick: () => go(`/student/tutor/${c.id}?q=${encodeURIComponent(m.title.split(". ").pop() + " mövzusunu izah et")}&mode=explain`) }] });
  });
});

// ---------------------------------------------------------------- tutor & campus
route("/student/tutor/:cid?", async (el, p, q) => {
  mount(el, loading());
  let courses;
  try { courses = await api.get("/api/courses"); } catch (e) { return mount(el, failed(e.message)); }
  if (!courses.length) return mount(el, html`${pageHead(t("AI tutor"), "", "", crumbsS([t("AI tutor")]))}${empty("sparkles", t("Fənn tapılmadı"), t("AI tutor üçün ən azı bir fənnə qeydiyyat lazımdır."))}`);
  const course = courses.find((c) => c.id === +(p.cid || courses[0].id)) || courses[0];
  mount(el, html`${pageHead(t("AI tutor"), t("Cavablar müəllimin yüklədiyi fənn materiallarına əsaslanır və mənbə göstərir."), "", crumbsS([t("AI tutor")]),
      { info: t("Sokratik rejimdə tutor hazır cavab vermir, düşünməyə yönəldir. İzah və Məşq rejimləri də mövcuddur. Fənn materialları tədris dilində təqdim olunur.") })}
    <div class="chips mb" data-tour="tutor-courses">${courses.map((c) => html`<button class="chip ${c.id === course.id ? "on" : ""}" data-go="/student/tutor/${c.id}"><span class="dot" style="background:${c.color};box-shadow:none"></span>${c.name}</button>`)}</div>
    <div id="chat" data-tour="tutor-chat"></div>`);
  await chatView($("#chat", el), {
    kind: "tutor", base: `/api/tutor/${course.id}`, modes: course.modes, mode: q.mode && course.modes.includes(q.mode) ? q.mode : course.modes[0],
    suggestions: course.suggestions, locked: !!course.tutor_locked, canForward: true, prefill: q.q || "", title: t("{course} üzrə AI tutor", { course: course.name }),
    text: t("Salam! Sualınızı yazın — {teacher} müəllimin materiallarına əsaslanaraq cavab verəcəyəm. Sokratik rejimdə hazır cavab yox, düşünməyə kömək edən ipuçları veririəm.", { teacher: course.teacher }),
  });
});

route("/student/campus", async (el) => {
  mount(el, html`${pageHead(t("Kampus köməkçisi"), t("Universitet qaydaları, arayışlar və prosedurlar barədə suallara 7/24 cavab."),
      html`<span class="demo-banner">${t("Bilik bazası: nümunə qaydalar (pilot)")}</span>`, crumbsS([t("Kampus köməkçisi")]),
      { info: t("Köməkçi ümumi qaydalar üzrə məlumat verir. Lazım gəldikdə müraciəti elə bu söhbətdən yarada bilərsiniz.") })}<div id="chat" data-tour="campus-chat"></div>`);
  await chatView($("#chat", el), {
    kind: "campus", suggestions: [t("Xəstə olmuşam, qayıbı necə üzrlü edim?"), t("Arayışı necə ala bilərəm?"), t("Qiymətləndirmə sistemi necədir?"), t("Yataqxanaya necə müraciət edim?"), t("İmtahanı başqa vaxta keçirmək olar?")],
    title: t("AzTU kampus köməkçisi"), text: t("Arayış, qayıb, akademik məzuniyyət, qiymətləndirmə, təqaüd və digər mövzularda soruşa bilərsiniz. Lazım olduqda müraciəti elə buradan yaradacağıq."),
  });
});

// ---------------------------------------------------------------- quizzes
route("/student/quizzes", async (el) => {
  mount(el, loading());
  let qs;
  try { qs = await api.get("/api/quizzes"); } catch (e) { return mount(el, failed(e.message)); }
  mount(el, html`${pageHead(t("Testlər"), t("Məşq testləri dərhal izahla yoxlanılır; qiymətli testlərin nəticəsi müəllimə ötürülür."), "", crumbsS([t("Testlər")]),
      { info: t("Qiymətli test semestr qiymətinə təsir edir və cəhd sayı məhduddur. Məşq testini istədiyiniz qədər həll edə bilərsiniz.") })}
    ${qs.length ? html`<div class="grid g-3" data-tour="quiz-grid">${qs.map((q) => html`<div class="card slide-up quiz-card"><div class="course-strip" style="background:${q.color}"></div><div class="card-b">
      <div class="row between"><span class="badge ${q.kind === "graded" ? "b-coral" : "b-blue"}">${q.kind === "graded" ? t("Qiymətli") : t("Məşq")}</span>${q.best != null ? html`<span class="badge b-green">${t("Ən yaxşı: {n}%", { n: q.best })}</span>` : ""}</div>
      <h3 class="quiz-title">${q.title}</h3><div class="small muted">${q.course}</div>
      <div class="row wrap small muted mt quiz-meta">${ic("list", 14)} ${t("{n} sual", { n: q.questions })} <span>·</span> ${ic("clock", 14)} ${t("{n} dəq", { n: q.time_limit })} <span>·</span> ${t("cəhd {u}/{a}", { u: q.used, a: q.attempts })}</div>
      <div class="row mt wrap">${q.can_start ? html`<button class="btn btn-primary grow" data-go="/student/quiz/${q.id}">${ic("play", 14)} ${q.used ? t("Yenidən həll et") : t("Başla")}</button>`
        : html`<button class="btn grow" disabled>${t("Cəhd limiti bitib")}</button>`}
        ${q.last_attempt ? html`<button class="btn" data-go="/student/attempt/${q.last_attempt}">${t("Nəticə")}</button>` : ""}</div></div></div>`)}</div>`
      : empty("quiz", t("Hələ test yoxdur"), t("Müəllim test təyin etdikdə burada görünəcək. Bu arada materialları AI tutorla təkrarlaya bilərsiniz."), { label: t("Fənlərim"), go: "/student/courses", icon: "book", cls: "btn" })}`);
});

route("/student/quiz/:id", async (el, p) => {
  mount(el, loading(t("Test hazırlanır…")));
  let d;
  try { d = await api.post(`/api/quizzes/${p.id}/start`); } catch (e) { toast(e.message, "err"); return go("/student/quizzes"); }
  const answers = {};
  let cur = 0, timer = null, done = false;
  const deadline = new Date(d.deadline).getTime();
  const draw = () => {
    const q = d.questions[cur];
    mount(el, html`<div class="quiz-player">
      <div class="q-head"><div><div class="small muted">${d.quiz.course}</div><h2 class="q-title">${d.quiz.title}</h2></div>
        <div class="row"><span class="timer" id="timer" aria-live="polite" aria-label="${t("Qalan vaxt")}">--:--</span><button class="btn btn-primary" id="finish">${ic("check", 15)} ${t("Bitir")}</button></div></div>
      <div class="row between mb"><div class="q-dots">${d.questions.map((x, i) => html`<button class="q-dot ${i === cur ? "cur" : ""} ${answers[x.id] !== undefined ? "ans" : ""}" data-i="${i}" aria-label="${t("Sual {n}", { n: i + 1 })}">${i + 1}</button>`)}</div>
        <span class="small muted">${t("{a}/{b} cavablandırılıb", { a: Object.keys(answers).length, b: d.questions.length })}</span></div>
      ${progress(((cur + 1) / d.questions.length) * 100)}
      <div class="card q-card mt slide-up">
        <div class="row wrap mb"><span class="badge b-gray">${t("Sual {n}", { n: cur + 1 })}</span><span class="badge b-navy">${QTYPE[q.qtype]}</span>${q.bloom ? html`<span class="badge b-gray">${q.bloom}</span>` : ""}</div>
        <div class="q-text">${md(q.text)}</div>
        ${q.qtype === "mcq" ? html`<div class="opts">${q.options.map((o, i) => html`<button class="opt ${answers[q.id] === i ? "sel" : ""}" data-opt="${i}"><span class="l">${LET[i]}</span><span>${o}</span></button>`)}</div>`
          : q.qtype === "tf" ? html`<div class="opts">${[[true, t("Doğru")], [false, t("Yanlış")]].map(([v, l], i) => html`<button class="opt ${answers[q.id] === v ? "sel" : ""}" data-tf="${v}"><span class="l">${LET[i]}</span><span>${l}</span></button>`)}</div>`
          : html`<div class="row"><input class="input numans" id="numans" inputmode="decimal" placeholder="${t("Cavab")}" value="${answers[q.id] ?? ""}" aria-label="${t("Cavab")}">${q.unit ? html`<span class="badge b-gray">${q.unit}</span>` : ""}</div><div class="small muted mt-sm">${t("Onluq kəsr üçün vergül və ya nöqtə istifadə edə bilərsiniz.")}</div>`}
        <div class="row between mt"><button class="btn" id="prev" ${cur === 0 ? "disabled" : ""}>${ic("back", 15)} ${t("Əvvəlki")}</button>
          ${cur < d.questions.length - 1 ? html`<button class="btn btn-primary" id="next">${t("Növbəti")} ${ic("chevron", 15)}</button>` : html`<button class="btn btn-success" id="finish2">${ic("check", 15)} ${t("Testi bitir")}</button>`}</div>
      </div></div>`);
    tick();
  };
  const tick = () => {
    const left = Math.max(0, Math.floor((deadline - Date.now()) / 1000));
    const tm = $("#timer", el);
    if (tm) { tm.textContent = `${String(Math.floor(left / 60)).padStart(2, "0")}:${String(left % 60).padStart(2, "0")}`; tm.classList.toggle("low", left < 60); }
    if (left <= 0 && !done) submit(true);
  };
  timer = setInterval(() => { if (!document.body.contains(el) || !location.hash.includes(`/student/quiz/${p.id}`)) return clearInterval(timer); tick(); }, 1000);
  const saveNum = () => { const n = $("#numans", el); if (n) { const v = n.value.trim(); if (v) answers[d.questions[cur].id] = v; else delete answers[d.questions[cur].id]; } };
  const submit = async (auto = false) => {
    if (done) return;
    saveNum();
    const missing = d.questions.length - Object.keys(answers).length;
    const doIt = async () => { done = true; clearInterval(timer); mount(el, loading(t("Cavablar yoxlanılır…"))); try { const r = await api.post(`/api/attempts/${d.attempt_id}/submit`, { answers }); go(`/student/attempt/${r.id}`); } catch (err) { toast(err.message, "err"); go("/student/quizzes"); } };
    if (auto) { toast(t("Vaxt bitdi — cavablar avtomatik göndərildi")); return doIt(); }
    modal({ title: t("Testi bitirmək?"), size: "sm", body: html`<p>${missing ? t("{n} sual cavabsız qalıb. Cavabları göndərmək istəyirsiniz?", { n: missing }) : t("Bütün suallar cavablandırılıb. Cavabları göndərmək istəyirsiniz?")}</p>`,
      actions: [{ label: t("Davam et") }, { label: t("Göndər"), cls: "btn-primary", onClick: doIt }] });
  };
  on(el, "click", "[data-opt]", (e, b) => { answers[d.questions[cur].id] = +b.dataset.opt; draw(); });
  on(el, "click", "[data-tf]", (e, b) => { answers[d.questions[cur].id] = b.dataset.tf === "true"; draw(); });
  on(el, "click", "[data-i]", (e, b) => { saveNum(); cur = +b.dataset.i; draw(); });
  on(el, "click", "#prev", () => { saveNum(); cur = Math.max(0, cur - 1); draw(); });
  on(el, "click", "#next", () => { saveNum(); cur = Math.min(d.questions.length - 1, cur + 1); draw(); });
  on(el, "click", "#finish, #finish2", () => submit());
  draw();
});

route("/student/attempt/:id", async (el, p) => {
  mount(el, loading());
  let r;
  try { r = await api.get(`/api/attempts/${p.id}`); } catch (e) { return mount(el, failed(e.message)); }
  const color = r.percent >= 81 ? "#0e9f6e" : r.percent >= 51 ? "#2b5aa8" : "#d64045";
  const verdict = r.percent >= 81 ? t("Əla nəticə.") : r.percent >= 51 ? t("Yaxşıdır — səhv etdiyiniz mövzuları tutorla təkrarlayın.") : t("Narahat olmayın — izahlara baxın və tutorla məşq edin.");
  mount(el, html`${pageHead(r.quiz.title, t("{course} · {dt}", { course: r.quiz.course, dt: fmtDateTime(r.finished_at) }), html`<button class="btn" data-go="/student/quizzes">${ic("back", 15)} ${t("Testlər")}</button>`,
      crumbsS([t("Testlər"), "/student/quizzes"], [t("Nəticə")]))}
    <div class="grid g-21">
      <div class="card pad center slide-up result-card" data-tour="result-score">${ring(r.percent, 150, color, null, 12)}<h3 class="mt">${t("{s} / {m} düzgün cavab", { s: r.score, m: r.max_score })}</h3>
        <p class="muted small">${verdict}</p>
        <button class="btn btn-ai btn-block" data-go="/student/tutor/${r.quiz.course_id}?mode=practice">${ic("sparkles", 15)} ${t("Tutorla məşq et")}</button></div>
      <div class="stack" data-tour="result-details">${r.details.map((dt, i) => html`<div class="review ${dt.correct ? "ok" : "no"} slide-up">
        <div class="row between"><b>${t("{n}. sual", { n: i + 1 })} · ${dt.correct ? t("Düzgün") : t("Səhv")}</b>${dt.topic ? html`<span class="badge b-gray">${dt.topic}</span>` : ""}</div>
        <div class="mt-sm">${md(dt.text)}</div>
        <div class="small mt-sm"><span class="muted">${t("Sizin cavabınız")}:</span> <b>${dt.qtype === "mcq" && /^[A-D]$/.test(dt.given) ? dt.given + ") " + (dt.options[LET.indexOf(dt.given)] || "") : dt.given}</b>
          ${dt.correct ? "" : html` · <span class="muted">${t("Düzgün cavab")}:</span> <b style="color:var(--green)">${dt.answer}</b>`}</div>
        <div class="notice ai mt-sm">${ic("sparkles", 15)}<div>${md(dt.explanation)}${dt.source ? html`<div class="tiny muted mt-sm">${ic("book", 12)} ${t("Mənbə")}: ${dt.source.material} · ${dt.source.heading}</div>` : ""}</div></div>
        ${dt.correct ? "" : html`<button class="btn btn-sm mt-sm" data-go="/student/tutor/${r.quiz.course_id}?mode=explain&q=${encodeURIComponent((dt.topic || "") + " mövzusunu izah et")}">${ic("sparkles", 14)} ${t("Bu mövzunu tutorla təkrarla")}</button>`}
      </div>`)}</div></div>`);
});

// ---------------------------------------------------------------- schedule (shared with /teacher/schedule)
export async function schedulePage(el, role) {
  mount(el, loading());
  let s;
  try { s = await api.get("/api/schedule"); } catch (e) { return mount(el, failed(e.message)); }
  const home = role === "teacher" ? "/teacher" : "/student";
  mount(el, html`${pageHead(t("Dərs cədvəli"), t("{sem} · bu həftə", { sem: S.app.semester }), html`<span class="badge b-gray">${ic("clock", 12)} ${t("İndi")}: ${s.now}</span>`, [[t("Əsas"), home], [t("Dərs cədvəli")]],
      { info: t("Həftəlik cədvəl elektron sistemdən götürülür. Qeydiyyatdan keçdiyiniz tədbirlər aşağıda göstərilir.") })}
    <div class="table-wrap"><div class="week" data-tour="week-grid">${s.days.map((d) => html`<div class="wday ${d.today ? "today" : ""}"><div class="wday-h"><span>${d.name}</span><span>${fmtDate(d.date).slice(0, 5)}</span></div>
      ${d.items.length ? d.items.map((x) => html`<div class="wslot" style="border-left-color:${x.color}"><span class="tiny muted">${x.start}–${x.end}</span><b>${x.course}</b>
        <span class="badge ${kindTone(x.kind)}">${x.kind}</span><div class="tiny muted mt-sm">${x.room}</div></div>`) : html`<div class="empty small wday-empty">${t("Dərs yoxdur")}</div>`}</div>`)}</div></div>
    <div class="grid g-2 mt">
      <div class="card" data-tour="my-events"><div class="card-h"><h3>${ic("calendar", 17)} ${t("Qeydiyyatdan keçdiyim tədbirlər")}</h3><a class="small" href="#/news">${t("Tədbirlər")} ${ic("arrow", 13)}</a></div><div class="card-b list">
        ${s.events.length ? s.events.map((ev) => html`<div class="list-item click" data-go="/news/${ev.id}">${datebox(ev.event_start)}<div class="grow"><b class="small">${ev.title}</b>
          <div class="tiny muted">${fmtDateTime(ev.event_start).slice(11)} · ${ev.location}</div></div>${ic("chevron", 14)}</div>`)
          : empty("calendar", t("Qeydiyyatınız yoxdur"), t("Xəbərlər bölməsində tədbirlərə qeydiyyatdan keçə bilərsiniz."), { label: t("Tədbirlərə bax"), go: "/news", icon: "news", cls: "btn-sm" })}</div></div>
      <div class="card"><div class="card-h"><h3>${ic("info", 17)} ${t("Dərs saatları")}</h3></div><div class="card-b list">
        ${[[t("1-ci cüt"), "09:00 – 10:20"], [t("2-ci cüt"), "10:30 – 11:50"], [t("3-cü cüt"), "12:00 – 13:20"], [t("Fasilə"), "13:20 – 13:50"], [t("4-cü cüt"), "13:50 – 15:10"], [t("5-ci cüt"), "15:20 – 16:40"]].map(([a, b]) =>
          html`<div class="list-item"><b class="small grow">${a}</b><span class="small muted">${b}</span></div>`)}</div></div></div>`);
}
route("/student/schedule", (el) => schedulePage(el, "student"));

// ---------------------------------------------------------------- attendance
route("/student/attendance", async (el) => {
  mount(el, loading());
  let a;
  try { a = await api.get("/api/attendance"); } catch (e) { return mount(el, failed(e.message)); }
  const abs = a.records.filter((r) => r.status === "absent");
  const days = [...new Set(abs.map((r) => r.day))].sort();
  mount(el, html`${pageHead(t("Davamiyyət"), t("Cari semestr üzrə iştirakınız. Üzrlü səbəb varsa, təsdiqedici sənədi yükləyin."),
      abs.length ? html`<button class="btn btn-accent" id="excuse-all">${ic("heart", 16)} ${t("Qayıbları üzrlü et ({n})", { n: abs.length })}</button>` : "", crumbsS([t("Davamiyyət")]),
      { info: t("Tibbi sənədləri yalnız dekanlıq görür; müəllim yalnız qayıbın “üzrlü” olduğunu görür. Buraxılmış dərslər ümumi saatların 25%-ni keçərsə, imtahana buraxılmaya bilərsiniz.") })}
    <div class="grid g-3" data-tour="att-courses">${a.courses.map((c) => html`<div class="card pad slide-up"><div class="row"><span class="course-ic sm2" style="background:${c.color}">${c.code.split("-")[0]}</span>
      <b class="small grow">${c.name}</b><b style="color:${c.rate < 80 ? "var(--red)" : "var(--green)"}">${num(c.rate)}%</b></div>
      <div class="row wrap mt small"><span class="badge b-green">${t("{n} iştirak", { n: c.present })}</span><span class="badge b-red">${t("{n} qayıb", { n: c.absent })}</span><span class="badge b-blue">${t("{n} üzrlü", { n: c.excused })}</span><span class="badge b-amber">${t("{n} gecikmə", { n: c.late })}</span></div>
      <div class="row between tiny muted mt">${t("Limitdən istifadə: {a} / {b} dərs", { a: c.absent, b: c.limit })}<span>${t("{n} dərs keçirilib", { n: c.total })}</span></div>${progress((100 * c.absent) / Math.max(1, c.limit), "coral")}</div>`)}</div>
    <div class="card mt" data-tour="att-log"><div class="card-h"><h3>${ic("list", 17)} ${t("Qayıblar və gecikmələr")}</h3></div>
      <div class="table-wrap"><table class="table"><thead><tr><th>${t("Tarix")}</th><th>${t("Fənn")}</th><th>${t("Dərs")}</th><th>${t("Status")}</th><th></th></tr></thead><tbody>
      ${a.records.length ? a.records.map((r) => html`<tr><td class="nowrap"><b>${fmtDate(r.day)}</b> <span class="tiny muted">${r.start}</span></td>
        <td><span class="dot" style="background:${r.color};box-shadow:none"></span> ${r.course}</td><td class="small">${r.kind} · <span class="muted">${r.topic}</span></td><td>${badge(r.status)}</td>
        <td class="right">${r.status === "absent" ? (r.pending_request ? html`<button class="btn btn-sm" data-go="/student/requests/${r.pending_request}">${ic("clock", 13)} ${t("Baxılır")}</button>`
          : html`<button class="btn btn-sm" data-excuse="${r.day}">${ic("heart", 13)} ${t("Üzrlü et")}</button>`) : r.status === "excused" ? html`<span class="tiny muted">${t("Dekanlıq təsdiqləyib")}</span>` : ""}</td></tr>`)
        : html`<tr><td colspan="5">${empty("check", t("Qayıb yoxdur"), t("Davamiyyətiniz qüsursuzdur."))}</td></tr>`}</tbody></table></div></div>`);
  const openWizard = (from, to) => go(`/student/services?new=absence_excuse&from=${from}&to=${to}`);
  on(el, "click", "#excuse-all", () => openWizard(days[0], days[days.length - 1]));
  on(el, "click", "[data-excuse]", (e, b) => openWizard(b.dataset.excuse, b.dataset.excuse));
});

// ---------------------------------------------------------------- grades
route("/student/grades", async (el) => {
  mount(el, loading());
  let g;
  try { g = await api.get("/api/grades"); } catch (e) { return mount(el, failed(e.message)); }
  const hasCur = g.courses.length && g.courses[0].items;
  mount(el, html`${pageHead(t("Qiymətlərim"), t("Cari semestrin balları və keçmiş semestrlər."),
      html`<button class="btn" data-go="/student/services?new=transcript">${ic("file", 15)} ${t("Transkript sifariş et")}</button>`, crumbsS([t("Qiymətlərim")]),
      { info: t("100 ballıq sistem: 50 bal semestr, 50 bal imtahan. Balların hesablanması qaydası ilə “Qiymətləndirmə” sənədində tanış ola bilərsiniz. Ballar demo üçün sintetikdir.") })}
    <div class="grid g-3 mb" data-tour="grades-summary">${stat("target", "ic-navy", g.average != null ? num(g.average) : "—", t("Orta çəkili bal (keçmiş semestrlər)"))}
      ${stat("award", "ic-green", cnt(g.credits), t("Toplanmış kredit (AKTS)"))}${stat("book", "ic-blue", cnt(g.courses.length), t("Cari semestrdə fənn"))}</div>
    ${hasCur ? html`<div class="card" data-tour="grades-table"><div class="card-h"><h3>${ic("list", 17)} ${S.app.semester}</h3><span class="small muted">${t("“—” — hələ keçirilməyib")}</span></div>
      <div class="table-wrap"><table class="table"><thead><tr><th>${t("Fənn")}</th>${g.courses[0].items.map((i) => html`<th class="center">${i.name}<br><span class="tiny">${t("maks. {n}", { n: i.max })}</span></th>`)}<th class="center">${t("Semestr (50)")}</th></tr></thead>
      <tbody>${g.courses.map((c) => html`<tr><td><div class="row"><span class="dot" style="background:${c.color};box-shadow:none"></span><b class="small">${c.name}</b></div></td>
        ${c.items.map((i) => html`<td class="center">${i.score != null ? html`<b>${num(i.score)}</b>` : html`<span class="faint">—</span>`}</td>`)}
        <td class="center"><b>${num(c.semester)}</b></td></tr>`)}</tbody></table></div></div>`
      : empty("target", t("Cari semestr üçün qiymət yoxdur"), t("Qiymətlər daxil olduqca burada görünəcək."))}
    ${g.past.length ? html`<div class="grid g-2 mt">${g.past.map((s) => html`<div class="card"><div class="card-h"><h3>${ic("award", 17)} ${s.name}</h3></div><div class="table-wrap"><table class="table">
      <thead><tr><th>${t("Fənn")}</th><th>${t("Kredit")}</th><th>${t("Bal")}</th><th>${t("Qiymət")}</th></tr></thead><tbody>${s.courses.map((r) => html`<tr><td class="small">${r.name}</td><td>${num(r.credits)}</td><td><b>${num(r.score)}</b></td>
      <td><span class="badge ${r.letter === "A" ? "b-green" : r.letter === "B" ? "b-blue" : r.letter === "C" ? "b-navy" : "b-amber"}">${r.letter}</span></td></tr>`)}</tbody></table></div></div>`)}</div>` : ""}`);
});

export { isoDay };

// ---------------------------------------------------------------- page guides
registerTour("student.home", { route: "/student", roles: ["student"], title: t("Əsas səhifə"), group: t("Əsas"), icon: "home", go: "/student", steps: [
  { sel: "[data-tour=hero]", title: t("Sürətli sual"), text: t("Fənni seçin, sualınızı yazın və birbaşa AI tutora keçin.") },
  { sel: "[data-tour=quick-tiles]", title: t("Sürətli xidmətlər"), text: t("Ən çox istifadə olunan e-xidmətlər: arayış, qayıbın üzrlü edilməsi, icazə.") },
  { sel: "#today-card", title: t("Bu gün"), text: t("Bugünkü dərsləriniz. Həftəlik cədvələ bir toxunuşla keçin.") },
  { sel: "[data-tour=ai-tip]", title: t("AI tövsiyəsi"), text: t("Test nəticələrinizə əsasən təkrarlamalı mövzular burada görünür.") },
] });
registerTour("student.courses", { route: "/student/courses", roles: ["student"], title: t("Fənlərim"), group: t("Təhsil"), icon: "book", go: "/student/courses", steps: [
  { sel: "[data-tour=course-grid]", title: t("Fənlər"), text: t("Hər kartda müəllim, davamiyyət və material sayı göstərilir. Karta toxunub fənn səhifəsini açın.") },
] });
registerTour("student.course", { route: "/student/course/:id", roles: ["student"], title: t("Fənn səhifəsi"), group: t("Təhsil"), icon: "book", go: "/student/course/1", steps: [
  { sel: "[data-tour=materials]", title: t("Materiallar"), text: t("Mühazirə materiallarını portal daxilində oxuyun; əsas anlayışlar da burada verilir.") },
  { sel: "[data-tour=attendance-card]", title: t("Davamiyyət"), text: t("Fənn üzrə iştirakınız və icazə verilən qayıb həddi.") },
] });
registerTour("student.tutor", { route: "/student/tutor/:cid?", roles: ["student"], title: t("AI tutor"), group: t("Təhsil"), icon: "sparkles", go: "/student/tutor/1", steps: [
  { sel: "[data-tour=tutor-courses]", title: t("Fənn seçimi"), text: t("Tutor seçdiyiniz fənnin materiallarına əsaslanır. Fənni buradan dəyişin.") },
  { sel: "[data-tour=chat-modes]", title: t("Rejimlər"), text: t("Sokratik rejim addım-addım düşündürür, İzah rejimi mövzunu qısa izah edir, Məşq rejimi sual verib cavabınızı yoxlayır.") },
  { sel: "[data-tour=chat-input]", title: t("Sual"), text: t("Sualınızı yazın və göndərin. Cavabdakı [1], [2] işarələri mənbəyə keçiddir.") },
  { sel: "[data-tour=chat-sources]", title: t("Mənbələr"), text: t("Cavabın əsaslandığı material hissəsini buradan oxuyun.") },
  { sel: "[data-tour=chat-usage]", title: t("Gündəlik limit"), text: t("Bu gün verə biləcəyiniz sualların sayı.") },
] });
registerTour("student.campus", { route: "/student/campus", roles: ["student"], title: t("Kampus köməkçisi"), group: t("Xidmətlər"), icon: "help", go: "/student/campus", steps: [
  { sel: "[data-tour=campus-chat]", title: t("Köməkçi"), text: t("Qaydalar, arayışlar və prosedurlar barədə soruşun; lazım olduqda müraciəti elə buradan yaradın.") },
  { sel: "[data-tour=chat-suggestions]", title: t("Nümunə suallar"), text: t("Tez-tez verilən suallardan birini seçərək başlayın.") },
  { sel: "[data-tour=chat-input]", title: t("Sual"), text: t("Sualınızı sərbəst yazın. Cavab universitetin qaydalarına əsaslanır və mənbəsi göstərilir.") },
] });
registerTour("student.quizzes", { route: "/student/quizzes", roles: ["student"], title: t("Testlər"), group: t("Təhsil"), icon: "quiz", go: "/student/quizzes", steps: [
  { sel: "[data-tour=quiz-grid]", title: t("Testlər"), text: t("Qiymətli və məşq testləri. Hər kartda sual sayı, vaxt və cəhd limiti göstərilir.") },
] });
registerTour("student.quiz", { route: "/student/quiz/:id", roles: ["student"], title: t("Test həlli"), group: t("Təhsil"), icon: "quiz", steps: [
  { sel: ".q-dots", title: t("Suallar"), text: t("Suallar arasında keçin; cavablandırılmışlar işarələnir.") },
  { sel: "#timer", title: t("Vaxt"), text: t("Qalan vaxt. Vaxt bitdikdə cavablar avtomatik göndərilir.") },
  { sel: ".opts, .numans", title: t("Cavab"), text: t("Variantı seçin və ya cavabı yazın. Bitirmədən əvvəl cavabsız sualları yoxlayın.") },
] });
registerTour("student.attempt", { route: "/student/attempt/:id", roles: ["student"], title: t("Test nəticəsi"), group: t("Təhsil"), icon: "target", steps: [
  { sel: "[data-tour=result-score]", title: t("Nəticə"), text: t("Ümumi balınız. Zəif mövzuları birbaşa tutorla təkrarlayın.") },
  { sel: "[data-tour=result-details]", title: t("İzahlar"), text: t("Hər sualın düzgün cavabı və mənbə ilə izahı.") },
] });
registerTour("student.schedule", { route: "/student/schedule", roles: ["student"], title: t("Dərs cədvəli"), group: t("Əsas"), icon: "calendar", go: "/student/schedule", steps: [
  { sel: "[data-tour=week-grid]", title: t("Həftəlik cədvəl"), text: t("Bütün həftənin dərsləri. Bugünkü gün vurğulanır.") },
  { sel: "[data-tour=my-events]", title: t("Tədbirlər"), text: t("Qeydiyyatdan keçdiyiniz universitet tədbirləri.") },
] });
registerTour("teacher.schedule", { route: "/teacher/schedule", roles: ["teacher"], title: t("Dərs cədvəli"), group: t("Əsas"), icon: "calendar", go: "/teacher/schedule", steps: [
  { sel: "[data-tour=week-grid]", title: t("Həftəlik cədvəl"), text: t("Dərslərinizin həftəlik cədvəli. Bugünkü gün vurğulanır.") },
  { sel: "[data-tour=my-events]", title: t("Tədbirlər"), text: t("Qeydiyyatdan keçdiyiniz universitet tədbirləri.") },
] });
registerTour("student.attendance", { route: "/student/attendance", roles: ["student"], title: t("Davamiyyət"), group: t("Təhsil"), icon: "calcheck", go: "/student/attendance", steps: [
  { sel: "[data-tour=att-courses]", title: t("Fənlər üzrə"), text: t("Hər fənn üzrə iştirak faizi və qayıb həddindən istifadə.") },
  { sel: "[data-tour=att-log]", title: t("Jurnal"), text: t("Qayıbları buradan üzrlü edin — e-xidmət müraciəti avtomatik hazırlanır.") },
] });
registerTour("student.grades", { route: "/student/grades", roles: ["student"], title: t("Qiymətlərim"), group: t("Təhsil"), icon: "target", go: "/student/grades", steps: [
  { sel: "[data-tour=grades-summary]", title: t("Xülasə"), text: t("Orta bal, toplanmış kreditlər və cari semestrdəki fənn sayı.") },
  { sel: "[data-tour=grades-table]", title: t("Cari semestr"), text: t("Fənlər üzrə semestr balları. Transkripti e-xidmətdən sifariş edin.") },
] });
