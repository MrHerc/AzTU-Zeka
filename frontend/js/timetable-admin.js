// Timetable management (Task 19): weekly rows of teaching units, checked for clashes of rooms, teachers and groups;
// making the term's lessons from them; a day's lessons, which can be cancelled or moved (the students are told).
import { api, html, mount, on, ic, toast, modal, route, pageHead, loading, failed, t, S } from "./core.js";
import { HOME } from "./shell.js";

const DAYS = () => ["", t("Bazar ertəsi"), t("Çərşənbə axşamı"), t("Çərşənbə"), t("Cümə axşamı"), t("Cümə"), t("Şənbə"), t("Bazar")];
const WEEKS = () => [["all", t("Hər həftə")], ["odd", t("Tək həftələr")], ["even", t("Cüt həftələr")]];
const UNIT_KIND = () => ({ lecture: t("Mühazirə"), seminar: t("Məşğələ"), lab: t("Laboratoriya") });
const WHAT = () => ({ room: t("otaq məşğuldur"), teacher: t("müəllim məşğuldur"), group: t("qrup məşğuldur") });
const MANAGERS = ["admin", "academic_office"];
const opts = (pairs, v) => pairs.map(([k, l]) => html`<option value="${k}" ${String(k) === String(v) ? "selected" : ""}>${l}</option>`);

const clashList = (err) => {
  const list = (err.data && err.data.conflicts) || [];
  if (!list.length) { toast(err.message, "err"); return; }
  modal({ title: t("Cədvəldə toqquşma var"), size: "lg", body: html`<p class="small muted">${t("Sətir saxlanmadı. Bu dərslərlə eyni vaxtdadır:")}</p>
    <div class="table-wrap"><table class="table"><thead><tr><th>${t("Səbəb")}</th><th>${t("Fənn")}</th><th>${t("Vaxt")}</th><th>${t("Otaq")}</th><th>${t("Müəllim")}</th></tr></thead><tbody>
    ${list.map((x) => html`<tr><td>${WHAT()[x.what] || x.what}${x.groups && x.groups.length ? html` (${x.groups.join(", ")})` : ""}</td>
      <td>${x.course} · ${x.kind || ""}</td><td>${x.day ? x.day + " " : ""}${x.start}–${x.end}</td><td>${x.room || "—"}</td><td>${x.teacher || "—"}</td></tr>`)}
    </tbody></table></div>` });
};

route("/admin/timetable", async (el, p, q) => {
  const role = S.user.role;
  const can = MANAGERS.includes(role);
  let view = q.view === "lessons" ? "lessons" : "rows", group = q.group || "", day = new Date().toLocaleDateString("sv-SE");      // YYYY-MM-DD of the local day
  let groups = [], courses = [], terms = [], rowsNow = [], lessonsNow = [], term = "";
  try {
    [groups, courses, terms] = await Promise.all(["groups", "courses", "terms"].map((n) => api.all(`/api/directory/${n}?active=1`)));
  } catch (err) { mount(el, failed(err.message)); return; }

  const head = () => html`${pageHead(t("Dərs cədvəli"), t("Tədris vahidlərinin həftəlik cədvəli. Saxlananda otaq, müəllim və qrup toqquşması yoxlanır."), "",
      [[t("Əsas"), HOME[role]], [t("Dərs cədvəli")]])}
    <div class="seg mb" role="tablist"><button role="tab" aria-selected="${view === "rows"}" class="${view === "rows" ? "active" : ""}" data-view="rows">${t("Həftəlik cədvəl")}</button>
      <button role="tab" aria-selected="${view === "lessons"}" class="${view === "lessons" ? "active" : ""}" data-view="lessons">${t("Günün dərsləri")}</button></div>`;
  const groupPick = () => html`<select class="input input-sm" id="tt-group" aria-label="${t("Qrup")}" style="max-width:200px"><option value="">${t("Bütün qruplar")}</option>${opts(groups.map((g) => [g.id, g.name]), group)}</select>`;

  const drawRows = async () => {
    let r;
    try { r = await api.get(`/api/timetable?${term ? "term_id=" + term + "&" : ""}${group ? "group_id=" + group : ""}`); }
    catch (err) { mount(el, failed(err.message)); return; }
    term = term || (r.term ? String(r.term.id) : "");
    rowsNow = r.rows;
    mount(el, html`${head()}
      <div class="card"><div class="card-h wrap">
        <select class="input input-sm" id="tt-term" aria-label="${t("Semestr")}" style="max-width:240px">${opts(terms.map((x) => [x.id, x.name]), term)}</select>${groupPick()}
        ${can ? html`<button class="btn btn-primary btn-sm" id="tt-new">${ic("plus", 15)} ${t("Yeni sətir")}</button>
          <button class="btn btn-sm" id="tt-make">${ic("calendar", 15)} ${t("Dərsləri yarat")}</button>` : ""}</div>
      <div class="table-wrap"><table class="table"><thead><tr><th>${t("Gün")}</th><th>${t("Vaxt")}</th><th>${t("Fənn")}</th><th>${t("Növ")}</th><th>${t("Qruplar")}</th>
        <th>${t("Müəllim")}</th><th>${t("Otaq")}</th><th>${t("Həftələr")}</th><th>${t("Saat")}</th><th></th></tr></thead><tbody>
        ${r.rows.map((x) => html`<tr><td>${DAYS()[x.weekday]}</td><td class="nowrap">${x.start}–${x.end}</td><td>${x.course}</td><td>${x.kind || "—"}</td>
          <td>${x.groups.length ? x.groups.join(", ") : "—"}${x.subgroup ? html` · ${t("Yarımqrup {n}", { n: x.subgroup })}` : ""}</td><td>${x.teacher || "—"}</td>
          <td>${x.room || "—"}${x.room && !x.room_id ? html` <span class="badge b-amber" title="${t("Otağa bağlanmayıb")}">?</span>` : ""}</td>
          <td>${(WEEKS().find(([k]) => k === x.weeks) || [, x.weeks])[1]}</td><td>${x.academic_hours ?? "—"}</td>
          <td class="nowrap">${can && x.unit_id ? html`<button class="btn btn-ghost btn-sm" data-edit="${x.id}">${t("Düzəlt")}</button>
            <button class="btn btn-ghost btn-sm" data-off="${x.id}">${t("Çıxar")}</button>` : ""}</td></tr>`)}
      </tbody></table></div>
      ${r.rows.length ? "" : html`<div class="card-b"><p class="muted" style="margin:0">${t("Bu seçimdə cədvəl sətri yoxdur")}</p></div>`}
      ${r.more ? html`<div class="card-b"><p class="muted" style="margin:0">${t("Siyahı ilk {n} sətirlə qısaldılıb: qrup seçin.", { n: r.rows.length })}</p></div>` : ""}</div>`);
  };

  const rowForm = (x) => {
    const m = modal({ title: x ? t("Cədvəl sətri") : t("Yeni sətir"), body: html`<div class="stack">
      ${x ? html`<p class="small muted" style="margin:0">${x.course} · ${x.kind}</p>` : html`
        <div class="field"><label class="label" for="tt-course">${t("Fənn")}</label><select class="input" id="tt-course"><option value="">—</option>${opts(courses.map((c) => [c.id, `${c.code} · ${c.name}`]), "")}</select></div>
        <div class="field"><label class="label" for="tt-unit">${t("Tədris vahidi")}</label><select class="input" id="tt-unit"><option value="">—</option></select></div>`}
      <div class="row wrap"><div class="field"><label class="label" for="tt-day">${t("Gün")}</label><select class="input" id="tt-day">${opts(DAYS().slice(1).map((d, i) => [i + 1, d]), x ? x.weekday : 1)}</select></div>
        <div class="field"><label class="label" for="tt-start">${t("Başlanğıc")}</label><input class="input" id="tt-start" type="time" value="${x ? x.start : "09:00"}"></div>
        <div class="field"><label class="label" for="tt-end">${t("Son")}</label><input class="input" id="tt-end" type="time" value="${x ? x.end : "10:20"}"></div></div>
      <div class="row wrap"><div class="field"><label class="label" for="tt-room">${t("Otaq")}</label><input class="input" id="tt-room" value="${x ? x.room || "" : ""}" placeholder="EK-220"></div>
        <div class="field"><label class="label" for="tt-weeks">${t("Həftələr")}</label><select class="input" id="tt-weeks">${opts(WEEKS(), x ? x.weeks : "all")}</select></div>
        <div class="field"><label class="label" for="tt-hours">${t("Akademik saat")}</label><input class="input" id="tt-hours" type="number" min="1" max="8" value="${x ? x.academic_hours || 2 : 2}"></div></div>
      <p class="small muted" style="margin:0">${t("Növ və müəllim tədris vahidindən gəlir. Gələcək dərslər yeni vaxta keçir; tələbələrə bildiriş gedir.")}</p></div>`,
    actions: [{ label: t("Saxla"), cls: "btn-primary", onClick: async (w) => {
      const body = { weekday: Number(w.querySelector("#tt-day").value), start: w.querySelector("#tt-start").value, end: w.querySelector("#tt-end").value,
        room: w.querySelector("#tt-room").value || null, weeks: w.querySelector("#tt-weeks").value, academic_hours: Number(w.querySelector("#tt-hours").value) };
      try {
        if (x) await api.put(`/api/timetable/${x.id}`, body);
        else await api.post("/api/timetable", { ...body, unit_id: Number(w.querySelector("#tt-unit").value) || null });
        toast(t("Saxlanıldı"), "ok"); drawRows();
      } catch (err) { if (err.status === 409) clashList(err); else toast(err.message, "err"); return false; }
    } }] });
    if (!x) on(m.el, "change", "#tt-course", async (ev, s) => {
      const box = m.el.querySelector("#tt-unit");
      if (!s.value) { mount(box, html`<option value="">—</option>`); return; }
      try {
        const units = (await api.get(`/api/directory/units?course_id=${s.value}&active=1`)).items;
        mount(box, html`${opts(units.map((u) => [u.id, `${UNIT_KIND()[u.kind] || u.kind}${u.subgroup ? " · " + t("Yarımqrup {n}", { n: u.subgroup }) : ""} (#${u.id})`]), "")}`);
      } catch (err) { toast(err.message, "err"); }
    });
  };

  const drawLessons = async () => {
    let list;
    try { list = await api.get(`/api/lessons?day=${day}${group ? "&group_id=" + group : ""}`); }
    catch (err) { mount(el, failed(err.message)); return; }
    lessonsNow = list;
    mount(el, html`${head()}
      <div class="card"><div class="card-h wrap"><input class="input input-sm" id="ls-day" type="date" value="${day}" aria-label="${t("Tarix")}" style="max-width:180px">${groupPick()}</div>
      <div class="table-wrap"><table class="table"><thead><tr><th>${t("Vaxt")}</th><th>${t("Fənn")}</th><th>${t("Növ")}</th><th>${t("Müəllim")}</th><th>${t("Otaq")}</th><th>${t("Vəziyyət")}</th><th></th></tr></thead><tbody>
      ${list.map((x) => html`<tr><td class="nowrap">${x.start}–${x.end}</td><td>${x.course}</td><td>${x.kind || "—"}</td><td>${x.teacher || "—"}</td><td>${x.room || "—"}</td>
        <td>${x.status === "cancelled" ? html`<span class="badge b-red">${t("Ləğv edilib")}</span>` : html`<span class="badge b-green">${t("Planlaşdırılıb")}</span>`}
          ${x.note ? html`<div class="small muted">${x.note}</div>` : ""}</td>
        <td class="nowrap">${can && x.status !== "cancelled" ? html`<button class="btn btn-ghost btn-sm" data-move="${x.id}">${t("Köçür")}</button>
          <button class="btn btn-ghost btn-sm" data-cancel="${x.id}">${t("Ləğv et")}</button>` : ""}</td></tr>`)}</tbody></table></div>
      ${list.length ? "" : html`<div class="card-b"><p class="muted" style="margin:0">${t("Bu gün dərs yoxdur")}</p></div>`}</div>`);
  };
  const draw = () => (view === "rows" ? drawRows() : drawLessons());

  on(el, "click", "[data-view]", (e, b) => { view = b.dataset.view; draw(); });
  on(el, "change", "#tt-term", (e, s) => { term = s.value; drawRows(); });
  on(el, "change", "#tt-group", (e, s) => { group = s.value; draw(); });
  on(el, "change", "#ls-day", (e, s) => { day = s.value; drawLessons(); });
  on(el, "click", "#tt-new", () => rowForm(null));
  on(el, "click", "[data-edit]", (e, b) => rowForm(rowsNow.find((x) => x.id === Number(b.dataset.edit))));
  on(el, "click", "[data-off]", (e, b) => modal({ title: t("Sətri cədvəldən çıxar"), size: "sm",
    body: html`<p style="margin:0">${t("Bu sətrin gələcək dərsləri silinir, keçmiş dərslər və davamiyyət qalır. Tələbələrə bildiriş gedir.")}</p>`,
    actions: [{ label: t("Çıxar"), cls: "btn-danger", onClick: async () => {
      try { await api.post(`/api/timetable/${b.dataset.off}/deactivate`); toast(t("Saxlanıldı"), "ok"); drawRows(); }
      catch (err) { toast(err.message, "err"); return false; }
    } }] }));
  on(el, "click", "#tt-make", async (e, b) => {
    b.classList.add("loading");
    try {
      const r = await api.post("/api/timetable/generate", { term_id: Number(term) || null });
      toast(t("{n} yeni dərs yaradıldı ({a} – {b})", { n: r.created, a: r.term.teaching_start, b: r.term.teaching_end }), "ok");
    } catch (err) { toast(err.message, "err"); } finally { b.classList.remove("loading"); }
  });
  on(el, "click", "[data-cancel]", (e, b) => modal({ title: t("Dərsi ləğv et"), size: "sm",
    body: html`<div class="field"><label class="label" for="ls-why">${t("Səbəb (tələbələr görür)")}</label><input class="input" id="ls-why" maxlength="300"></div>`,
    actions: [{ label: t("Ləğv et"), cls: "btn-danger", onClick: async (w) => {
      try { await api.post(`/api/lessons/${b.dataset.cancel}/cancel`, { reason: w.querySelector("#ls-why").value }); toast(t("Dərs ləğv edildi"), "ok"); drawLessons(); }
      catch (err) { toast(err.message, "err"); return false; }
    } }] }));
  on(el, "click", "[data-move]", (e, b) => {
    const x = lessonsNow.find((l) => l.id === Number(b.dataset.move));
    modal({ title: t("Dərsi köçür"), body: html`<div class="stack"><div class="row wrap">
        <div class="field"><label class="label" for="mv-day">${t("Tarix")}</label><input class="input" id="mv-day" type="date" value="${x.day}"></div>
        <div class="field"><label class="label" for="mv-start">${t("Başlanğıc")}</label><input class="input" id="mv-start" type="time" value="${x.start}"></div>
        <div class="field"><label class="label" for="mv-end">${t("Son")}</label><input class="input" id="mv-end" type="time" value="${x.end}"></div></div>
        <div class="field"><label class="label" for="mv-room">${t("Otaq")}</label><input class="input" id="mv-room" value="${x.room || ""}"></div></div>`,
      actions: [{ label: t("Köçür"), cls: "btn-primary", onClick: async (w) => {
        try {
          await api.post(`/api/lessons/${x.id}/move`, { day: w.querySelector("#mv-day").value, start: w.querySelector("#mv-start").value,
            end: w.querySelector("#mv-end").value, room: w.querySelector("#mv-room").value || null });
          toast(t("Dərs köçürüldü"), "ok"); drawLessons();
        } catch (err) { if (err.status === 409) clashList(err); else toast(err.message, "err"); return false; }
      } }] });
  });
  mount(el, loading());
  draw();
});
