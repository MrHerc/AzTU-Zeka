// Bulk import (Task 16): a CSV or XLSX file of one kind from one source system is checked first (dry run), then
// imported all or nothing. Conflicts (rows changed in Zəka since the last import) are listed, not overwritten.
// Activation codes for a faculty's students are made here once and handed to the dean's office as CSV.
import { api, html, mount, on, ic, toast, route, pageHead, loading, failed, num, $, $$, t, S } from "./core.js";
// hours of the form: the file keeps floats such as 44.3333; shown with at most two decimals in the interface language (L15)
const hrs = (x) => (x == null || x === "" ? "—" : num(Math.round(Number(x) * 100) / 100));
import { HOME } from "./shell.js";

const KINDS = () => [["users", t("İstifadəçilər")], ["orgs", t("Fakültə və kafedralar")], ["terms", t("Semestrlər")],
  ["courses", t("Fənlər")], ["classes", t("Tədris vahidləri")], ["enrollments", t("Fənlərə yazılış")], ["timetable", t("Dərs cədvəli")],
  ["rooms", t("Otaqlar")], ["attendance-opening", t("Davamiyyətin açılış qalığı")], ["grades", t("Ballar")], ["teaching-load", t("Forma №3: kafedranın akademik yükü")]];

const readFile = (f) => new Promise((ok, bad) => {
  const r = new FileReader();
  r.onload = () => ok(String(r.result).split(",", 2)[1] || "");
  r.onerror = () => bad(new Error(t("Fayl oxunmadı")));
  r.readAsDataURL(f);
});

// Forma №3 (Task 47): what the reader found, so the dean's office can correct the file before applying it.
const LOAD = () => ({ consultation: t("Məsləhətlər"), credit: t("Məqbul"), exam: t("İmtahan"), exam_prep: t("İmtahan suallarının hazırlanması"),
  course_project: t("Kurs layihəsi (işi)"), essay: t("Referat"), master_work: t("Magistrların işi"),
  master_supervision: t("Magistr dissertasiyasına rəhbərlik"), master_consulting: t("Magistr dissertasiyası üzrə məsləhət"),
  research: t("Tədqiqat işinin aparılması"), project_management: t("Layihələrin idarə olunması"), practice: t("Təcrübə"),
  phd_teaching: t("Aspirantlara dərs"), doctoral: t("Doktorantura"), state_exam: t("Dövlət attestasiya komissiyası"),
  graduation: t("Buraxılış işi"), class_visits: t("Müəllimlərin dərslərdə iştirakı"), other_load: t("Digər dərs yükü"),
  other_department: t("Digər kafedranın dərs yükü") });

// a post whose subject courses of two departments teach: the office chooses whose course its lessons go to (Task 48)
const depPick = (p) => p.departments ? html`<select class="input input-sm" data-post-dep="${p.ref}" aria-label="${t("Kafedra")}: ${p.ref}">
  ${p.department_id == null ? html`<option value="">—</option>` : ""}${p.departments.map((d) => html`<option value="${d.id}" ${d.id === p.department_id ? "selected" : ""}>${d.name}</option>`)}</select>` : "—";

function forma3(f) {
  const tile = (n, label, tone = "") => html`<div class="stat"><b class="${tone}">${n}</b><span class="small muted">${label}</span></div>`;
  const blocked = f.posts.filter((p) => p.status === "blocked");
  const status = (p) => p.status === "ok" ? html`<span class="badge b-green">${t("Tətbiq oluna bilər")}</span>`
    : p.status === "hidden" ? html`<span class="badge">${t("Gizli vərəq: idxal olunmur")}</span>` : html`<span class="badge b-red">${t("Bloklanıb")}</span>`;
  const checks = (p) => ["T1", "T2", "T3"].map((k) => html`<span class="badge ${p.controls[k] ? "b-green" : "b-red"}">${k} ${p.controls[k] ? "✓" : "✗"}</span> `);
  const who = (p) => p.vacancy ? t("Vakansiya") + (p.vacancy_area ? ` (${p.vacancy_area})` : "") : p.teacher || "—";
  const skipped = f.sheets.filter((x) => !x.imported);
  const labels = LOAD();
  return html`<div class="card mt"><div class="card-h"><h3>${ic("list", 17)} ${t("Forma №3: faylın oxunması üzrə hesabat")}</h3>
      <span class="badge ${blocked.length ? "b-red" : "b-green"}">${blocked.length ? t("{n} ştat və ya bölmə bloklanıb", { n: blocked.length }) : t("Bütün yoxlamalar keçdi")}</span></div>
    <div class="card-b stack">
      <p class="small muted" style="margin:0">${t("Tədris ili: {y} · quruluş: {l} · vərəq: {n}", { y: f.year || "—", l: f.layout || "—", n: f.sheets.length })}</p>
      <div class="row wrap">${tile(f.units.count, t("dərs"))}${tile(f.units.ready, t("tətbiq oluna bilən"), "ok")}${tile(f.units.count - f.units.ready - (f.units.refused || 0), t("bloklanmış"), blocked.length ? "warn" : "")}
        ${f.units.refused ? tile(f.units.refused, t("reyestrdə tapılmayan"), "warn") : ""}
        ${tile(f.units.joint, t("birləşmiş dərs"))}${tile(f.units.hourly, t("saat hesabı"))}${tile(f.units.vacancy, t("vakansiya"))}${tile(f.units.hidden, t("gizli vərəqdə"))}</div>
      ${f.excluded && f.excluded.posts.length ? html`<p class="small muted" style="margin:0">${t("Kafedranın cəminə daxil olmayan ştat və bölmələr: {p} — dərs: {u} ({h} saat), digər yük: {l} saat",
        { p: f.excluded.posts.join(", "), u: f.excluded.units, h: hrs(f.excluded.hours), l: hrs(f.excluded.load_hours) })}</p>` : ""}
      ${blocked.length ? html`<div class="notice warn">${ic("alert", 16)}<div>${t("Bloklanmış ştatın və ya bölmənin dərsləri tətbiq olunmur. Fayldakı xananı düzəldib yenidən yoxlayın.")}</div></div>` : ""}
      ${f.unclassified ? html`<div class="notice warn">${ic("alert", 16)}<div>${t("{n} xana heç bir qaydaya uyğun gəlmədi; onlar qeydlərdə göstərilib.", { n: f.unclassified })}</div></div>` : ""}
      <div class="table-wrap"><table class="table"><thead><tr><th>${t("Xana")}</th><th>${t("Müəllim")}</th><th>${t("Ödəniş")}</th><th>${t("Vəziyyət")}</th>
        <th>${t("Yoxlamalar")}</th><th>${t("Dərs")}</th><th>${t("Auditoriya saatı")}</th><th>${t("İllik cəm")}</th><th>${t("Kafedra")}</th></tr></thead><tbody>
        ${f.posts.map((p) => html`<tr><td>${p.ref}</td><td>${who(p)}</td><td>${p.pay === "hourly" ? t("Saat hesabı") : t("Ştat")}${p.fraction ? ` · ${p.fraction}` : ""}</td>
          <td>${status(p)}${p.year_conflict ? html` <span class="badge b-amber">${t("Tədris ili fərqlidir")}</span>` : ""}</td><td>${checks(p)}</td>
          <td>${p.units}</td><td>${hrs(p.hours)}</td><td>${hrs(p.year_total)}</td><td>${depPick(p)}</td></tr>`)}</tbody></table></div>
      ${f.posts.some((p) => p.departments) ? html`<p class="small muted" style="margin:0">${t("Ştatın fənnini bir neçə kafedra keçir: dərslərin hansı kafedranın fənninə yazılacağını seçin və faylı yenidən yoxlayın.")}</p>` : ""}
      ${f.controls.length ? html`<div class="table-wrap"><table class="table"><thead><tr><th>${t("Yoxlama qaydası")}</th><th>${t("Xana")}</th><th>${t("Gözlənilən")}</th><th>${t("Tapılan")}</th><th></th></tr></thead><tbody>
        ${f.controls.map((c) => html`<tr><td>${c.check}</td><td>${c.ref || t("Fayl")}</td><td>${hrs(c.expected)}</td><td>${hrs(c.found)}</td>
          <td><span class="badge ${c.ok ? "b-green" : "b-red"}">${c.ok ? "✓" : "✗"}</span></td></tr>`)}</tbody></table></div>` : ""}
      ${f.conflict_count ? html`<h4 style="margin:0">${t("Konfliktlər: {n} (bloklayan: {b})", { n: f.conflict_count, b: f.blocking_count })}</h4>
        <div class="table-wrap"><table class="table"><thead><tr><th>${t("Xana")}</th><th>${t("Növ")}</th><th>${t("Səbəb")}</th></tr></thead><tbody>
        ${f.conflicts.map((c) => html`<tr><td>${c.cell}</td><td><span class="badge ${c.blocking ? "b-red" : "b-amber"}">${c.blocking ? t("Bloklayır") : t("Xəbərdarlıq")}</span></td>
          <td>${c.message}</td></tr>`)}</tbody></table></div>` : ""}
      ${f.note_count ? html`<details><summary>${t("Qeydlər: {n}", { n: f.note_count })}</summary>
        <div class="table-wrap"><table class="table"><thead><tr><th>${t("Xana")}</th><th>${t("Qeyd")}</th></tr></thead><tbody>
        ${f.notes.map((n) => html`<tr><td>${n.cell}</td><td>${n.message}</td></tr>`)}</tbody></table></div></details>` : ""}
      <details><summary>${t("Dərsdən kənar yük: {h} saat", { h: hrs(f.load_hours) })}</summary>
        <div class="table-wrap"><table class="table"><thead><tr><th>${t("Yükün növü")}</th><th>${t("Sətir")}</th><th>${t("Saat")}</th></tr></thead><tbody>
        ${Object.entries(f.load).map(([k, v]) => html`<tr><td>${labels[k] || k}</td><td>${v.lines}</td><td>${hrs(v.hours)}</td></tr>`)}</tbody></table></div></details>
      ${skipped.length ? html`<details><summary>${t("İdxal olunmayan vərəqlər: {n}", { n: skipped.length })}</summary>
        <div class="table-wrap"><table class="table"><thead><tr><th>${t("Vərəq")}</th><th>${t("Səbəb")}</th><th>${t("Dərs")}</th></tr></thead><tbody>
        ${skipped.map((x) => html`<tr><td>#${x.index} ${x.name}</td><td>${x.reason}</td><td>${x.units}</td></tr>`)}</tbody></table></div></details>` : ""}
    </div></div>`;
}

function report(r) {
  const tile = (n, label, tone = "") => html`<div class="stat"><b class="${tone}">${n}</b><span class="small muted">${label}</span></div>`;
  return html`<div class="card mt"><div class="card-h"><h3>${ic("list", 17)} ${r.written ? t("İdxal olundu") : r.error_count ? t("Fayl idxal olunmadı") : t("Yoxlamanın nəticəsi")}</h3>
      <span class="badge ${r.error_count ? "b-red" : r.written ? "b-green" : "b-blue"}">${r.error_count ? t("{n} səhv sətir", { n: r.error_count }) : r.written ? t("Yazıldı") : t("Heç nə yazılmayıb")}</span></div>
    <div class="card-b stack"><div class="row wrap">${tile(r.rows, t("sətir"))}${tile(r.inserted, t("yeni"), "ok")}${tile(r.updated, t("dəyişən"))}
      ${tile(r.unchanged, t("dəyişməyən"))}${tile(r.conflicts.length, t("konflikt"), r.conflicts.length ? "warn" : "")}</div>
      ${r.written ? html`<p class="small muted" style="margin:0">${t("Yazma kilidi: {ms} ms · cəmi {s} s", { ms: r.lock_ms, s: r.seconds })}</p>` : ""}
      ${r.error_count ? html`<div class="notice warn">${ic("alert", 16)}<div>${t("Səhv sətirlər düzəldilməyincə fayldan heç nə yazılmır.")}</div></div>
        <div class="table-wrap"><table class="table"><thead><tr><th>${t("Sətir")}</th><th>${t("Səbəb")}</th></tr></thead><tbody>
          ${r.errors.map((e) => html`<tr><td>${e.row}</td><td>${e.reason}</td></tr>`)}</tbody></table></div>` : ""}
      ${r.conflicts.length ? html`<div class="notice info">${ic("info", 16)}<div>${t("Bu sətirlər Zəka platformasında dəyişdirilib və mənbənin dəyərləri yazılmayıb. Mənbəni üstün tutmaq üçün işarəni qoyub yenidən idxal edin.")}</div></div>
        <div class="table-wrap"><table class="table"><thead><tr><th>${t("Sətir")}</th><th>${t("Dəyişən sahələr")}</th><th>${t("Səbəb")}</th></tr></thead><tbody>
          ${r.conflicts.slice(0, 500).map((x) => html`<tr><td>${x.row}</td><td>${(x.fields || []).join(", ") || "—"}</td><td>${x.reason}</td></tr>`)}</tbody></table></div>` : ""}
      ${(r.warnings || []).length ? html`<div class="notice warn">${ic("alert", 16)}<div>${t("Bu sətirlər yazılır, amma yoxlanmalıdır.")}</div></div>
        <div class="table-wrap"><table class="table"><thead><tr><th>${t("Sətir")}</th><th>${t("Səbəb")}</th></tr></thead><tbody>
          ${r.warnings.slice(0, 500).map((x) => html`<tr><td>${x.row}</td><td>${x.reason}</td></tr>`)}</tbody></table></div>` : ""}
      ${(r.stale || []).length ? html`<div class="notice warn">${ic("alert", 16)}<div>${t("Əvvəlki idxalın bu dərsləri bu fayla görə tətbiq olunmur: {n}", { n: r.stale.length })}</div></div>
        <div class="table-wrap"><table class="table"><thead><tr><th>${t("Xana")}</th><th>${t("Ştat və ya bölmə")}</th><th>${t("Səbəb")}</th></tr></thead><tbody>
          ${r.stale.slice(0, 500).map((x) => html`<tr><td>${x.anchor}</td><td>${x.post_ref}</td><td>${x.reason}</td></tr>`)}</tbody></table></div>` : ""}
    </div></div>${r.forma3 ? forma3(r.forma3) : ""}`;
}

route("/admin/import", async (el) => {
  let faculties = [];
  try { faculties = (await api.get("/api/directory/faculties?active=1")).items; } catch (err) { mount(el, failed(err.message)); return; }
  let checked = null;
  mount(el, html`${pageHead(t("Kütləvi idxal"), t("Köhnə sistemlərdən CSV və ya XLSX faylı: əvvəlcə yoxlanılır, sonra ya tam idxal olunur, ya da ümumiyyətlə idxal olunmur."), "",
      [[t("Əsas"), HOME[S.user.role]], [t("Kütləvi idxal")]])}
    <div class="grid g-2">
      <div class="card"><div class="card-h"><h3>${ic("upload", 17)} ${t("Fayl")}</h3></div><div class="card-b stack">
        <div class="field"><label class="label" for="imp-kind">${t("Nə idxal olunur")}</label>
          <select class="input" id="imp-kind">${KINDS().map(([k, l]) => html`<option value="${k}">${l}</option>`)}</select></div>
        <div class="field"><label class="label" for="imp-source">${t("Mənbə sistemi")}</label>
          <input class="input" id="imp-source" placeholder="${t("məs. kohne-sis")}" autocomplete="off" spellcheck="false"></div>
        <div class="field"><label class="label" for="imp-file">${t("CSV və ya XLSX faylı (bu səhifədən ən çox 20 000 sətir)")}</label>
          <input class="input" id="imp-file" type="file" accept=".csv,.xlsx,text/csv"></div>
        <label class="check"><input type="checkbox" id="imp-prefer"> ${t("Konflikt olduqda mənbəni üstün tut (dəyişiklik audit jurnalına yazılır)")}</label>
        <div class="row wrap"><button class="btn" id="imp-check">${ic("eye", 15)} ${t("Faylı yoxla")}</button>
          <button class="btn btn-primary" id="imp-run" disabled>${ic("upload", 15)} ${t("İdxal et")}</button></div>
        <p class="small muted" style="margin:0">${t("Sütun adları OneRoster 1.2 və ya azərbaycanca başlıqlardır. Böyük faylı serverdə manage.py import ilə idxal edin.")}</p>
      </div></div>
      <div class="card"><div class="card-h"><h3>${ic("lock", 17)} ${t("Aktivləşdirmə kodları")}</h3></div><div class="card-b stack">
        <p class="small muted" style="margin:0">${t("Fakültənin hələ parol seçməmiş tələbələrinə birdəfəlik kod. Kodlar yalnız bir dəfə göstərilir; yenidən yaratmaq köhnə kodları ləğv edir.")}</p>
        <select class="input" id="ac-faculty" aria-label="${t("Fakültə")}">${faculties.map((f) => html`<option value="${f.id}">${f.name}</option>`)}</select>
        <button class="btn" id="ac-make" style="align-self:flex-start">${ic("download", 15)} ${t("Kodları yarat və yüklə")}</button>
      </div></div>
    </div>
    <div id="imp-report"></div>`);
  const box = $("#imp-report", el);
  const body = async (dry) => {
    const f = $("#imp-file", el).files[0];
    if (!f) throw new Error(t("Faylı seçin"));
    return { kind: $("#imp-kind", el).value, source: $("#imp-source", el).value.trim(), filename: f.name, content_b64: await readFile(f),
      dry_run: dry, prefer_source: $("#imp-prefer", el).checked,
      departments: Object.fromEntries($$("[data-post-dep]", box).filter((x) => x.value).map((x) => [x.dataset.postDep, Number(x.value)])) };
  };
  const reset = () => { checked = null; $("#imp-run", el).disabled = true; };
  on(el, "change", "#imp-kind, #imp-source, #imp-file, #imp-prefer, [data-post-dep]", reset);
  on(el, "click", "#imp-check", async (e, b) => {
    b.classList.add("loading");
    try {
      const req = await body(true);                    // the report's department choices are read before it is replaced
      mount(box, loading());
      const r = await api.post("/api/admin/import", req); mount(box, report(r)); checked = r; $("#imp-run", el).disabled = !!r.error_count;
    }
    catch (err) { mount(box, ""); toast(err.message, "err"); reset(); }
    finally { b.classList.remove("loading"); }
  });
  on(el, "click", "#imp-run", async (e, b) => {
    if (!checked) return;
    b.classList.add("loading");
    try {
      const r = await api.post("/api/admin/import", await body(false));
      mount(box, report(r)); reset();
      toast(r.written ? t("İdxal olundu") : t("Fayl idxal olunmadı"), r.written ? "ok" : "err");     // nothing written: say so
    }
    catch (err) { toast(err.message, "err"); }
    finally { b.classList.remove("loading"); }
  });
  on(el, "click", "#ac-make", async (e, b) => {
    b.classList.add("loading");
    try {
      const r = await api.post("/api/admin/activation-codes", { faculty_id: Number($("#ac-faculty", el).value) });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob(["﻿" + r.csv], { type: "text/csv;charset=utf-8" }));
      a.download = `aktivlesdirme-kodlari-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      toast(t("{n} kod yaradıldı", { n: r.count }), "ok");
    } catch (err) { toast(err.message, "err"); }
    finally { b.classList.remove("loading"); }
  });
});
