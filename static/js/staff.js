import { api, html, raw, mount, on, ic, toast, modal, route, go, S, pageHead, fmtDate, fmtDateTime, isoDay, ring, progress, loading, failed, empty,
  infoTip, confirmBox, sparkline, lineChart, barChart, cnt, num, t, LANG, $, $$, esc, registerTour, currentPath } from "./core.js";
import { stat } from "./student.js";
import { HOME } from "./shell.js";
import { feedbackSummaryCard } from "./support.js";
import { achievementsTeaser } from "./achievements.js";

const COL = { wau: "#2b5aa8", teachers: "#1a2355", prep: "#0e9f6e", doc: "#0e8aa8", cite: "#5a9bd3", sat: "#c27803", academy: "#ee7c7e", gain: "#0e9f6e" };
// Pull the leading number out of a server-formatted KPI value ("64%", "−41%", "4,4 / 5", "5,4 saat") so it can count up; keep the rest as suffix.
function kpiNumber(value) {
  const s = String(value);
  const m = s.match(/^([+\-−]?\d+(?:[.,]\d+)?)(.*)$/);
  if (!m) return null;
  const sign = m[1][0] === "−" || m[1][0] === "-" ? -1 : 1;
  const n = sign * parseFloat(m[1].replace("−", "").replace(",", ".").replace(/^[+\-]/, ""));
  if (!isFinite(n)) return null;
  const dec = (m[1].split(/[.,]/)[1] || "").length;
  const prefix = m[1][0] === "+" ? "+" : m[1][0] === "−" || m[1][0] === "-" ? "−" : "";
  return { n, dec, prefix, suffix: m[2] };
}
function kpiValue(value) {
  const k = kpiNumber(value);
  // The sign is rendered by the prefix ("−41%"), so the animated number itself must be unsigned — otherwise "−-41%".
  return k ? cnt(Math.abs(k.n), { dec: k.dec, prefix: k.prefix, suffix: k.suffix }) : html`${value}`;
}

// ---------------------------------------------------------------- leadership dashboard
route("/leader", async (el) => {
  mount(el, loading());
  let a;
  try { a = await api.get("/api/analytics"); } catch (err) { mount(el, failed(err.message)); return; }
  mount(el, html`
    ${pageHead(t("Pilot idarə paneli"), t("{faculty} · {courses} fənn · {students} tələbə · {teachers} müəllim",
        { faculty: S.app.faculty.name, courses: 6, students: a.totals.students, teachers: a.totals.teachers }),
      html`<span class="demo-banner">${t("Pilot ssenarisi")}</span><button class="btn" id="print">${ic("printer", 15)} ${t("Hesabatı çap et")}</button>`,
      [[t("Rəhbərlik"), "/leader"], [t("Pilot idarə paneli")]],
      { info: t("Göstəricilər pilot məqsədilə sintetik məlumatlar əsasında hazırlanıb. Hədəflər universitetin rəqəmsallaşma proqramına uyğundur.") })}
    <div class="grid g-4" id="kpis">${a.kpis.map((k) => html`<div class="card kpi"><div class="kpi-top"><span class="kpi-l">${k.label}</span>
      <span class="badge ${k.ok ? "b-green" : "b-amber"}">${k.ok ? t("Hədəfdə") : t("İcrada")}</span></div>
      <div class="row between"><span class="kpi-v">${kpiValue(k.value)}</span>${sparkline(k.series, COL[k.key], 96, 34)}</div>
      <span class="kpi-t">${t("Hədəf")}: ${k.target}</span></div>`)}</div>

    <div class="grid g-12 mt">
      <div class="card"><div class="card-h"><h3>${ic("users", 17)} ${t("Həftəlik aktiv istifadəçilər")}</h3>
        <div class="row small"><span class="dot" style="background:#2b5aa8;box-shadow:none"></span>${t("Tələbələr")}
          <span class="dot" style="background:#1a2355;box-shadow:none;margin-left:8px"></span>${t("Müəllimlər")}</div></div>
        <div class="card-b">${lineChart({ labels: a.labels, series: [{ name: t("Tələbələr"), values: a.wau_students, color: "#2b5aa8" }, { name: t("Müəllimlər"), values: a.wau_teachers, color: "#1a2355" }],
          suffix: "%", target: { value: 60, label: t("Hədəf 60%") }, max: 100, label: t("Həftəlik aktiv istifadəçilər, %") })}</div></div>
      <div class="card"><div class="card-h"><h3>${ic("sparkles", 17)} ${t("AI keyfiyyəti")}</h3>${infoTip(t("Mənbəli cavablar — AI-ın fənn materialına istinad etdiyi cavabların payı. Faydalı rəylər — tələbələrin müsbət qiymətləndirdiyi cavablar."))}</div>
        <div class="card-b">
          <div class="row" style="justify-content:space-around">${ring(a.ai.cited_rate, 112, "#2b5aa8", num(a.ai.cited_rate, 1) + "%")}${ring(a.ai.positive_rate || 0, 112, "#0e9f6e", a.ai.positive_rate == null ? "—" : a.ai.positive_rate + "%")}</div>
          <div class="row small muted" style="justify-content:space-around;margin-top:6px"><span>${t("Mənbəli cavablar")}</span><span>${t("Faydalı rəylər")}</span></div><div class="divider"></div>
          <div class="row between small"><span class="muted">${t("AI xərci (aktiv tələbə / ay)")}</span><b>${cnt(a.ai.cost_per_student, { dec: 2, prefix: "$" })}</b></div>
          <div class="row between small mt-sm"><span class="muted">${t("AI cavabları (cəmi)")}</span><b>${cnt(a.ai.messages)}</b></div>
          <div class="row between small mt-sm"><span class="muted">${t("Təsdiqlənmiş sual bankı")}</span><b>${cnt(a.totals.questions_bank)}</b></div></div></div></div>

    <div class="grid g-4 mt">
      ${stat("grid", "ic-blue", cnt(a.totals.requests), t("Onlayn müraciət"), "/office")}
      ${stat("qr", "ic-green", cnt(a.totals.documents), t("QR kodlu sənəd"), "/office/registry")}
      ${stat("calcheck", "ic-coral", html`${num(a.attendance.rate, 1)}%`, t("Davamiyyət · {n} üzrlü qayıb", { n: a.attendance.excused }))}
      ${stat("cap", "ic-violet", cnt(a.totals.academy_hours, { suffix: " " + t("saat") }), t("Müəllim təlimi · {n} sertifikat", { n: a.totals.certificates }))}</div>

    <div class="grid g-2 mt">
      <div class="card"><div class="card-h"><h3>${ic("message", 17)} ${t("Tutor sualları (həftəlik)")}</h3></div><div class="card-b">${barChart({ labels: a.labels, values: a.tutor_questions, color: "#2b5aa8", label: t("Tutor sualları, həftəlik") })}</div></div>
      <div class="card"><div class="card-h"><h3>${ic("file", 17)} ${t("Arayışın hazırlanma müddəti, saat")}</h3></div><div class="card-b">${lineChart({ labels: a.labels, series: [{ name: t("Saat"), values: a.request_hours, color: "#0e8aa8" }], target: { value: 24, label: t("İcra müddəti 24 saat") }, label: t("Arayışın hazırlanma müddəti, saat") })}</div></div></div>

    <div class="grid g-2 mt">
      <div class="card"><div class="card-h"><h3>${ic("grid", 17)} ${t("E-xidmətlər üzrə müraciətlər")}</h3></div><div class="card-b">${a.requests_by_type.length ? a.requests_by_type.map((r) => html`<div class="bar-row"><span class="ellipsis small" title="${r.name}">${r.name}</span>
        ${progress((100 * r.n) / Math.max(1, a.requests_by_type[0].n))}<b class="right small">${cnt(r.n)}</b></div>`) : empty("grid", t("Hələ müraciət yoxdur"))}</div></div>
      <div class="card"><div class="card-h"><h3>${ic("news", 17)} ${t("Ən çox oxunan xəbərlər")}</h3><a class="small" href="#/staff/news">${t("İdarə et")} ${ic("arrow", 13)}</a></div>
        <div class="card-b list">${a.news.length ? a.news.map((n) => html`<a class="list-item click" href="#/news/${n.id}"><div class="grow"><b class="small">${n.title}</b></div>
          <span class="badge b-gray">${ic("eye", 11)} ${cnt(n.reads)}</span>${n.rsvp ? html`<span class="badge b-coral">${t("{n} qeydiyyat", { n: n.rsvp })}</span>` : ""}</a>`) : empty("news", t("Hələ xəbər dərc edilməyib"), "", { label: t("Xəbər dərc et"), go: "/staff/news?new=1", icon: "megaphone" })}</div></div></div>

    <div class="grid g-12 mt">
      <div class="card"><div class="card-h"><h3>${ic("book", 17)} ${t("Fənlər üzrə")}</h3></div><div class="table-wrap"><table class="table"><thead><tr><th>${t("Fənn")}</th><th>${t("Tutor sualları")}</th><th>${t("Test orta balı")}</th><th>${t("Davamiyyət")}</th><th>${t("Faydalı cavab")}</th><th>${t("Mənbəsiz")}</th></tr></thead><tbody>
        ${a.courses.map((c) => html`<tr><td><div class="row"><span class="dot" style="background:${c.color};box-shadow:none"></span><b class="small">${c.name}</b></div></td><td>${num(c.questions)}</td>
          <td><div class="row" style="min-width:120px">${progress(c.quiz_avg || 0)}<b class="small">${c.quiz_avg == null ? "—" : c.quiz_avg + "%"}</b></div></td>
          <td>${c.attendance == null ? "—" : c.attendance + "%"}</td><td>${c.positive_rate == null ? "—" : c.positive_rate + "%"}</td>
          <td>${c.no_source_rate > 5 ? html`<span class="badge b-amber">${num(c.no_source_rate, 1)}%</span>` : html`${num(c.no_source_rate, 1)}%`}</td></tr>`)}</tbody></table></div></div>
      <div class="card" id="insights"><div class="card-h"><h3>${ic("bell", 17)} ${t("Diqqət tələb edənlər")}</h3></div><div class="card-b stack">
        ${a.insights.length ? a.insights.map((i) => html`<div class="notice ${i.level === "good" ? "ok" : "warn"}">${ic(i.level === "good" ? "trend" : "alert", 16)}<div>${i.text}</div></div>`) : empty("check", t("Diqqət tələb edən məsələ yoxdur"))}</div></div></div>

    <div class="grid g-2 mt" id="leader-extra"></div>`);
  $("#print", el).addEventListener("click", () => window.print());
  // Async cross-module cards (feedback summary + achievements teaser)
  Promise.all([feedbackSummaryCard(true), achievementsTeaser(3)]).then(([fb, ach]) => {
    const box = $("#leader-extra", el);
    if (box) mount(box, html`${fb}${ach}`);
  });
});

// ---------------------------------------------------------------- platform settings (admin)
route("/admin", async (el) => {
  mount(el, loading());
  let s;
  try { s = await api.get("/api/admin/status"); } catch (err) { mount(el, failed(err.message)); return; }
  const NAMES = { users: t("istifadəçi"), courses: t("fənn"), materials: t("material"), chunks: t("mətn bölməsi"), questions: t("sual"), messages: t("mesaj"),
    requests: t("müraciət"), files: t("fayl"), documents: t("sənəd"), news: t("xəbər"), notifications: t("bildiriş"), lessons: t("dərs") };
  mount(el, html`${pageHead(t("Platforma idarəetməsi"), t("AI provayderi, limitlər, məxfilik və demo məlumatları."), "", [[t("Platforma"), "/admin"], [t("İdarəetmə")]],
      { info: t("Bu parametrlər bütün istifadəçilərə təsir edir. Dəyişiklik etməzdən əvvəl pilot komandası ilə razılaşdırın.") })}
    <div class="grid g-2">
      <div class="card"><div class="card-h"><h3>${ic("cpu", 17)} ${t("AI provayderi")}</h3>${s.llm.configured ? html`<span class="badge b-green">${t("LLM qoşulub")}</span>` : html`<span class="badge b-navy">${t("Demo rejimi")}</span>`}</div><div class="card-b">
        <div class="review-grid">${[[t("Rejim"), s.engine.label], [t("Provayder"), s.llm.provider], [t("Model"), s.llm.model], [t("Ünvan (endpoint)"), s.llm.base_url]].map(([k, v]) => html`<div>${k}</div><div class="small">${v}</div>`)}</div>
        <div class="notice info mt">${ic("info", 16)}<div>${t("Real modeli qoşmaq üçün layihə qovluğunda config.example.json faylını config.json adı ilə kopyalayın, API açarını yazın və serveri yenidən başladın. Model əlçatan olmadıqda sistem avtomatik demo rejimə keçir.")}</div></div>
        <button class="btn mt" id="test">${ic("bolt", 15)} ${t("Bağlantını yoxla")}</button></div></div>
      <div class="card"><div class="card-h"><h3>${ic("shield", 17)} ${t("Limitlər və məxfilik")}</h3></div><form class="card-b stack" id="settings-form" novalidate>
        <label class="field"><span>${t("Tələbə üçün gündəlik sual limiti")} ${infoTip(t("Bir tələbənin AI tutora və kampus köməkçisinə gün ərzində verə biləcəyi sualların sayı. 5 ilə 500 arasında."))}</span><input class="input" id="dl" type="number" min="5" max="500" value="${s.limits.daily_messages}"></label>
        <label class="row switch-row"><span class="switch"><input type="checkbox" id="pii" ${s.limits.pii_masking ? "checked" : ""}><span></span></span><div><b class="small">${t("Şəxsi məlumatların maskalanması")}</b><div class="tiny muted">${t("FİN, telefon, e-poçt və kart nömrəsi AI-a göndərilmir")}</div></div></label>
        <label class="field"><span>${t("Söhbətlərin saxlanma müddəti (gün)")} ${infoTip(t("Bu müddətdən sonra AI söhbətləri avtomatik silinir. Minimum 30 gün."))}</span><input class="input" id="rd" type="number" min="30" max="3650" value="${s.limits.retention_days}"></label>
        <button class="btn btn-primary" type="submit" style="align-self:flex-start">${ic("check", 15)} ${t("Yadda saxla")}</button></form></div></div>

    <div class="grid g-2 mt">
      <div class="card"><div class="card-h"><h3>${ic("layers", 17)} ${t("Məlumatlar")}</h3></div><div class="card-b"><div class="grid g-4">${Object.entries(s.counts).map(([k, v]) => html`<div><div class="stat-v" style="font-size:20px">${cnt(v)}</div><div class="stat-l">${NAMES[k] || k}</div></div>`)}</div>
        <div class="tiny muted mt">${t("Verilənlər bazası")}: <code>${s.db_path}</code> · ${t("fayllar")}: <code>${s.uploads}</code></div></div></div>
      <div class="card"><div class="card-h"><h3>${ic("refresh", 17)} ${t("Demo məlumatları")}</h3></div><div class="card-b stack"><p class="small muted" style="margin:0">${t("Bütün dəyişikliklər (müraciətlər, fayllar, xəbərlər, testlər, söhbətlər) silinəcək və ilkin demo məlumatları yenidən yaradılacaq. Bu əməliyyat geri qaytarılmır.")}</p>
        <button class="btn btn-danger" id="reset" style="align-self:flex-start">${ic("refresh", 15)} ${t("Demo məlumatlarını sıfırla")}</button></div></div></div>`);
  $("#test", el).addEventListener("click", async (e) => {
    const b = e.currentTarget; b.disabled = true;
    try { const r = await api.post("/api/admin/test-llm"); toast(r.message, r.ok ? "ok" : "err"); } catch (err) { toast(err.message, "err"); } finally { b.disabled = false; }
  });
  $("#settings-form", el).addEventListener("submit", async (e) => {
    e.preventDefault();
    const b = e.target.querySelector("[type=submit]"); b.disabled = true;
    try { await api.put("/api/admin/settings", { daily_messages: +$("#dl", el).value, pii_masking: $("#pii", el).checked, retention_days: +$("#rd", el).value });
      toast(t("Tənzimləmələr yadda saxlanıldı"), "ok"); } catch (err) { toast(err.message, "err"); } finally { b.disabled = false; }
  });
  $("#reset", el).addEventListener("click", async () => {
    if (!(await confirmBox(t("Demo məlumatlarını sıfırlamaq?"), t("Bütün demo dəyişiklikləri silinəcək və ilkin vəziyyət bərpa olunacaq. Bu əməliyyat geri qaytarılmır."), t("Sıfırla"), true))) return;
    try { await api.post("/api/admin/reset"); sessionStorage.removeItem("zeka-sid"); toast(t("Demo məlumatları sıfırlandı"), "ok"); setTimeout(() => location.reload(), 700); }
    catch (err) { toast(err.message, "err"); }
  });
});

// ---------------------------------------------------------------- audit log (admin + leader)
// Server returns raw rows {ts, full_name, action, entity, detail}; UI chrome is translated and action codes mapped to readable labels.
const ACTIONS = {
  login: [t("Giriş"), "b-gray"], consent: [t("Razılıq verildi"), "b-gray"], request_create: [t("Müraciət yaradıldı"), "b-blue"],
  document_issue: [t("Sənəd verildi"), "b-green"], request_complete: [t("Müraciət tamamlandı"), "b-green"], document_revoke: [t("Sənəd ləğv edildi"), "b-red"],
  file_view: [t("Fayla baxış"), "b-amber"], file_preview: [t("Fayl önizləməsi"), "b-amber"], news_publish: [t("Xəbər dərc edildi"), "b-green"],
  news_update: [t("Xəbər yeniləndi"), "b-blue"], news_delete: [t("Xəbər silindi"), "b-red"], quiz_submit: [t("Test göndərildi"), "b-blue"],
  quiz_publish: [t("Test dərc edildi"), "b-green"], ai_generate: [t("AI sual generasiyası"), "b-violet"], material_upload: [t("Material yükləndi"), "b-blue"],
  material_delete: [t("Material silindi"), "b-red"], tutor_settings: [t("Tutor tənzimləmələri"), "b-navy"], settings_update: [t("Tənzimləmələr dəyişdirildi"), "b-navy"],
  certificate_issue: [t("Sertifikat verildi"), "b-green"], syllabus_generate: [t("Sillabus hazırlandı"), "b-violet"], forward_question: [t("Sual müəllimə göndərildi"), "b-blue"],
  support_create: [t("Dəstək sorğusu yaradıldı"), "b-blue"], support_update: [t("Dəstək sorğusu yeniləndi"), "b-navy"], feedback: [t("Rəy bildirildi"), "b-gray"],
  seed: [t("Demo məlumatları yaradıldı"), "b-gray"],
};
const actionLabel = (code) => (ACTIONS[code] || [code, "b-gray"]);

route("/admin/audit", async (el, p, q) => {
  mount(el, loading());
  let rows;
  try { rows = await api.get("/api/admin/audit"); } catch (err) { mount(el, failed(err.message)); return; }
  const back = S.user.role === "admin" ? ["/admin", t("İdarəetmə")] : ["/leader", t("Pilot idarə paneli")];
  // Build filter option lists from the data itself.
  const presentActions = [...new Set(rows.map((r) => r.action))].sort((x, y) => actionLabel(x)[0].localeCompare(actionLabel(y)[0], "az"));
  const presentUsers = [...new Set(rows.map((r) => r.full_name || ""))].filter(Boolean).sort((x, y) => x.localeCompare(y, "az"));
  mount(el, html`${pageHead(t("Audit jurnalı"), t("Mühüm əməliyyatlar qeydə alınır: giriş, müraciət, sənəd, fayla baxış və tənzimləmələr."), "",
      [[back[1], back[0]], [t("Audit jurnalı")]], { info: t("Son 200 qeyd göstərilir. Jurnal yalnız oxunur: qeydləri dəyişmək və ya silmək mümkün deyil. Vaxtlar yerli saatla göstərilir.") })}
    <div class="card"><div class="card-h wrap">
      <div class="row wrap">
        <select class="input input-sm" id="f-action" aria-label="${t("Əməliyyat")}"><option value="">${t("Bütün əməliyyatlar")}</option>${presentActions.map((aC) => html`<option value="${aC}">${actionLabel(aC)[0]}</option>`)}</select>
        <select class="input input-sm" id="f-user" aria-label="${t("İstifadəçi")}"><option value="">${t("Bütün istifadəçilər")}</option>${presentUsers.map((n) => html`<option value="${esc(n)}">${n}</option>`)}</select>
        <input class="input input-sm" id="f-date" type="date" aria-label="${t("Tarix")}">
      </div>
      <div class="row wrap"><span class="small muted" id="f-count"></span><button class="btn btn-ghost btn-sm" id="f-clear">${ic("x", 14)} ${t("Filtrləri sıfırla")}</button></div></div>
      <div id="audit-body"></div></div>`);
  const bodyEl = $("#audit-body", el);
  const draw = () => {
    const fa = $("#f-action", el).value, fu = $("#f-user", el).value, fd = $("#f-date", el).value;
    const filtered = rows.filter((r) => (!fa || r.action === fa) && (!fu || (r.full_name || "") === fu) && (!fd || isoDay(new Date(r.ts)) === fd));
    $("#f-count", el).textContent = t("{n} qeyd", { n: filtered.length });
    if (!filtered.length) {
      mount(bodyEl, html`<div class="card-b">${empty("search", t("Bu filtrlərə uyğun qeyd yoxdur"), t("Filtrləri dəyişin və ya sıfırlayın."), { label: t("Filtrləri sıfırla"), id: "empty-clear", cls: "btn", icon: "x" })}</div>`);
      return;
    }
    mount(bodyEl, html`<div class="table-wrap"><table class="table"><thead><tr><th>${t("Vaxt")}</th><th>${t("İstifadəçi")}</th><th>${t("Əməliyyat")}</th><th>${t("Obyekt")}</th><th>${t("Təfərrüat")}</th></tr></thead><tbody>
      ${filtered.map((r) => { const [label, cls] = actionLabel(r.action); return html`<tr><td class="small nowrap">${fmtDateTime(r.ts)}</td><td>${r.full_name || t("Sistem")}</td>
        <td><span class="badge ${cls}">${label}</span></td><td class="small">${r.entity || "—"}</td><td class="small muted">${r.detail || "—"}</td></tr>`; })}</tbody></table></div>`);
  };
  draw();
  const resetFilters = () => { $("#f-action", el).value = ""; $("#f-user", el).value = ""; $("#f-date", el).value = ""; draw(); };
  $("#f-action", el).addEventListener("change", draw);
  $("#f-user", el).addEventListener("change", draw);
  $("#f-date", el).addEventListener("change", draw);
  $("#f-clear", el).addEventListener("click", resetFilters);
  on(el, "click", "#empty-clear", resetFilters);
});

// ---------------------------------------------------------------- page guides
registerTour("leader", { route: "/leader", roles: ["leader"], title: t("Pilot idarə paneli"), group: t("Rəhbərlik"), icon: "chart", steps: [
  { sel: "#kpis", title: t("Əsas göstəricilər"), text: t("Pilotun hədəfləri: aktivlik, keyfiyyət, icra müddəti və məmnuniyyət. Hər kartda cari dəyər və hədəf göstərilir.") },
  { sel: ".grid.g-12 .card", title: t("Dinamika"), text: t("Həftəlik aktivlik və AI keyfiyyəti — tendensiyaları izləyin.") },
  { sel: "#insights", title: t("Diqqət tələb edənlər"), text: t("Sistem avtomatik olaraq diqqət tələb edən məsələləri qeyd edir — məsələn, materialı çatışmayan fənlər.") },
  { sel: "#leader-extra", title: t("Rəy və nailiyyətlər"), text: t("İstifadəçi məmnuniyyəti və universitetin son nailiyyətləri bir baxışda.") },
] });
registerTour("admin", { route: "/admin", roles: ["admin"], title: t("Platforma idarəetməsi"), group: t("Platforma"), icon: "sliders", steps: [
  { sel: ".card", title: t("AI provayderi"), text: t("Cari AI rejimi və provayder. Real modeli config.json ilə qoşmaq olar.") },
  { sel: "#settings-form", title: t("Limitlər və məxfilik"), text: t("Gündəlik sual limiti, şəxsi məlumatların maskalanması və söhbətlərin saxlanma müddəti.") },
  { sel: "#reset", title: t("Demo sıfırlama"), text: t("Pilot nümayişindən əvvəl məlumatları ilkin vəziyyətə qaytarın.") },
] });
registerTour("admin.audit", { route: "/admin/audit", roles: ["admin", "leader"], title: t("Audit jurnalı"), group: t("Nəzarət"), icon: "list", steps: [
  { sel: ".card-h", title: t("Filtrlər"), text: t("Əməliyyat, istifadəçi və tarix üzrə qeydləri süzün.") },
  { sel: "#audit-body", title: t("Qeydlər"), text: t("Hər sətir bir əməliyyatdır: vaxt, kim, nə etdi və hansı obyekt üzərində.") },
] });
