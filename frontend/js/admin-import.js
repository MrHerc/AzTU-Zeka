// Bulk import (Task 16): a CSV or XLSX file of one kind from one source system is checked first (dry run), then
// imported all or nothing. Conflicts (rows changed in Zəka since the last import) are listed, not overwritten.
// Activation codes for a faculty's students are made here once and handed to the dean's office as CSV.
import { api, html, mount, on, ic, toast, route, pageHead, loading, failed, $, t, S } from "./core.js";
import { HOME } from "./shell.js";

const KINDS = () => [["users", t("İstifadəçilər")], ["orgs", t("Fakültə və kafedralar")], ["terms", t("Semestrlər")],
  ["courses", t("Fənlər")], ["classes", t("Tədris vahidləri")], ["enrollments", t("Qeydiyyat")], ["timetable", t("Dərs cədvəli")],
  ["rooms", t("Otaqlar")], ["teaching-load", t("Forma №3: kafedranın akademik yükü")]];

const readFile = (f) => new Promise((ok, bad) => {
  const r = new FileReader();
  r.onload = () => ok(String(r.result).split(",", 2)[1] || "");
  r.onerror = () => bad(new Error(t("Fayl oxunmadı")));
  r.readAsDataURL(f);
});

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
      ${r.conflicts.length ? html`<div class="notice info">${ic("info", 16)}<div>${t("Bu sətirlər Zəka-da dəyişdirilib və mənbənin dəyəri yazılmayıb. Mənbəni üstün tutmaq üçün işarəni qoyub yenidən idxal edin.")}</div></div>
        <div class="table-wrap"><table class="table"><thead><tr><th>${t("Sətir")}</th><th>${t("Sahələr")}</th><th>${t("Səbəb")}</th></tr></thead><tbody>
          ${r.conflicts.slice(0, 500).map((x) => html`<tr><td>${x.row}</td><td>${(x.fields || []).join(", ") || "—"}</td><td>${x.reason}</td></tr>`)}</tbody></table></div>` : ""}
    </div></div>`;
}

route("/admin/import", async (el) => {
  let faculties = [];
  try { faculties = (await api.get("/api/directory/faculties?active=1")).items; } catch (err) { mount(el, failed(err.message)); return; }
  let checked = null;
  mount(el, html`${pageHead(t("Kütləvi idxal"), t("Köhnə sistemlərdən CSV və ya XLSX faylı: əvvəl yoxlanır, sonra ya tam idxal olunur, ya heç nə."), "",
      [[t("Əsas"), HOME[S.user.role]], [t("Kütləvi idxal")]])}
    <div class="grid g-2">
      <div class="card"><div class="card-h"><h3>${ic("upload", 17)} ${t("Fayl")}</h3></div><div class="card-b stack">
        <div class="field"><label class="label" for="imp-kind">${t("Nə idxal olunur")}</label>
          <select class="input" id="imp-kind">${KINDS().map(([k, l]) => html`<option value="${k}">${l}</option>`)}</select></div>
        <div class="field"><label class="label" for="imp-source">${t("Mənbə sistem")}</label>
          <input class="input" id="imp-source" placeholder="${t("məs. kohne-sis")}" autocomplete="off" spellcheck="false"></div>
        <div class="field"><label class="label" for="imp-file">${t("CSV və ya XLSX faylı (ekrandan ən çox 20 000 sətir)")}</label>
          <input class="input" id="imp-file" type="file" accept=".csv,.xlsx,text/csv"></div>
        <label class="check"><input type="checkbox" id="imp-prefer"> ${t("Konfliktdə mənbəni üstün tut (dəyişiklik audit jurnalına yazılır)")}</label>
        <div class="row wrap"><button class="btn" id="imp-check">${ic("eye", 15)} ${t("Yoxla")}</button>
          <button class="btn btn-primary" id="imp-run" disabled>${ic("upload", 15)} ${t("İdxal et")}</button></div>
        <p class="small muted" style="margin:0">${t("Sütun adları OneRoster 1.2 və ya Azərbaycanca başlıqlardır. Böyük faylı serverdə manage.py import ilə idxal edin.")}</p>
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
      dry_run: dry, prefer_source: $("#imp-prefer", el).checked };
  };
  const reset = () => { checked = null; $("#imp-run", el).disabled = true; };
  on(el, "change", "#imp-kind, #imp-source, #imp-file, #imp-prefer", reset);
  on(el, "click", "#imp-check", async (e, b) => {
    b.classList.add("loading"); mount(box, loading());
    try { const r = await api.post("/api/admin/import", await body(true)); mount(box, report(r)); checked = r; $("#imp-run", el).disabled = !!r.error_count; }
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
