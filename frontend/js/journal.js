// The attendance journal (Task 20): a teacher marks a lesson's list (everyone present by default, exceptions marked);
// after the edit window a department head corrects with a reason; each student's share of missed hours per course.
import { api, html, mount, on, ic, toast, modal, route, pageHead, loading, failed, go, $, $$, t, S } from "./core.js";
import { HOME } from "./shell.js";

const MARK = () => ({ present: t("İştirak edir"), absent: t("Qayıb"), late: t("Gecikmə"), excused: t("Üzrlü") });
const STAND = () => ({ normal: [t("Normal"), "b-green"], warning: [t("Həddə yaxındır"), "b-amber"],
  not_admitted: [t("İmtahana buraxılmır"), "b-red"], incomplete: [t("Məlumat natamam"), "b-gray"] });
const CORRECTORS = ["dept_head", "admin"];
const crumbs = (x) => [[t("Əsas"), HOME[S.user.role]], [t("Elektron jurnal"), "/journal"], ...(x ? [[x]] : [])];
const standBadge = (s) => { const [l, c] = STAND()[s] || [s, "b-gray"]; return html`<span class="badge ${c}">${l}</span>`; };

route("/journal", async (el, p, q) => {
  const role = S.user.role;
  let view = q.view === "standing" || ["office", "academic_office", "leader"].includes(role) ? "standing" : "lessons";
  let course = q.course || "", courses = [];
  try {
    courses = role === "teacher" ? await api.get("/api/courses") : (await api.get("/api/directory/courses?active=1")).items;
  } catch (err) { mount(el, failed(err.message)); return; }
  const head = () => html`${pageHead(t("Elektron jurnal"), t("Dərsin davamiyyəti, buraxılmış saatlar və imtahana buraxılış."), "", crumbs())}
    <div class="seg mb" role="tablist">
      <button role="tab" aria-selected="${view === "lessons"}" class="${view === "lessons" ? "active" : ""}" data-view="lessons">${t("Dərslərim")}</button>
      <button role="tab" aria-selected="${view === "standing"}" class="${view === "standing" ? "active" : ""}" data-view="standing">${t("Fənn üzrə vəziyyət")}</button></div>`;

  const drawLessons = async () => {
    let list;
    try { list = await api.get("/api/journal/lessons"); } catch (err) { mount(el, failed(err.message)); return; }
    mount(el, html`${head()}<div class="card"><div class="card-h"><h3>${ic("calendar", 17)} ${t("Son iki həftənin dərsləri")}</h3></div>
      <div class="table-wrap"><table class="table"><thead><tr><th>${t("Tarix")}</th><th>${t("Vaxt")}</th><th>${t("Fənn")}</th><th>${t("Növ")}</th><th>${t("Vəziyyət")}</th><th></th></tr></thead><tbody>
      ${list.map((x) => html`<tr><td class="nowrap">${x.day}</td><td class="nowrap">${x.start}–${x.end}</td><td>${x.course}</td><td>${x.kind || "—"}</td>
        <td>${x.status === "cancelled" ? html`<span class="badge b-red">${t("Ləğv edilib")}</span>` : x.marked ? html`<span class="badge b-green">${t("Qeyd olunub")}</span>`
          : html`<span class="badge b-amber">${t("Qeyd olunmayıb")}</span>`}</td>
        <td>${x.status !== "cancelled" ? html`<button class="btn btn-sm" data-go="/journal/lesson/${x.id}">${t("Aç")}</button>` : ""}</td></tr>`)}</tbody></table></div>
      ${list.length ? "" : html`<div class="card-b"><p class="muted" style="margin:0">${t("Son iki həftədə sizin dərsiniz yoxdur")}</p></div>`}</div>`);
  };

  const drawStanding = async () => {
    let list = [];
    if (course) { try { list = await api.get(`/api/journal/courses/${course}/standing`); } catch (err) { toast(err.message, "err"); } }
    mount(el, html`${head()}<div class="card"><div class="card-h wrap">
        <select class="input input-sm" id="j-course" aria-label="${t("Fənn")}" style="max-width:360px"><option value="">${t("Fənni seçin")}</option>
          ${courses.map((c) => html`<option value="${c.id}" ${String(c.id) === String(course) ? "selected" : ""}>${c.code} · ${c.name}</option>`)}</select></div>
      ${course ? html`<div class="table-wrap"><table class="table"><thead><tr><th>${t("Tələbə")}</th><th>${t("Qrup")}</th><th>${t("Plan saatı")}</th>
          <th>${t("Buraxılmış saat")}</th><th>${t("Faiz")}</th><th>${t("Vəziyyət")}</th><th></th></tr></thead><tbody>
        ${list.map((x) => html`<tr><td>${x.full_name} <span class="tiny muted">${x.student_no || ""}</span></td><td>${x.group || "—"}</td><td>${x.planned_hours}</td>
          <td>${x.missed_hours}${x.excused_hours ? html` <span class="tiny muted">(${t("üzrlü: {n}", { n: x.excused_hours })})</span>` : ""}</td>
          <td><b>${x.percent}%</b> <span class="tiny muted">/ ${x.limit_percent}%</span></td>
          <td>${standBadge(x.status)}${x.as_of ? html`<div class="tiny muted">${t("{d} tarixinədək idxal", { d: x.as_of })}</div>` : ""}</td>
          <td>${x.opening_id && CORRECTORS.includes(S.user.role) ? html`<button class="btn btn-ghost btn-sm" data-open="${x.opening_id}" data-u="${x.unexcused_hours}" data-e="${x.excused_hours}">${t("Qalığı düzəlt")}</button>` : ""}</td></tr>`)}
        </tbody></table></div>${list.length ? "" : html`<div class="card-b"><p class="muted" style="margin:0">${t("Bu fənndə tələbə yoxdur")}</p></div>`}`
        : html`<div class="card-b"><p class="muted" style="margin:0">${t("Tələbələrin buraxılmış saatlarını görmək üçün fənni seçin.")}</p></div>`}</div>`);
  };
  const draw = () => (view === "lessons" ? drawLessons() : drawStanding());
  on(el, "click", "[data-view]", (e, b) => { view = b.dataset.view; draw(); });
  on(el, "click", "[data-go]", (e, b) => go(b.dataset.go));
  on(el, "change", "#j-course", (e, s) => { course = s.value; drawStanding(); });
  on(el, "click", "[data-open]", (e, b) => modal({ title: t("Açılış qalığının düzəlişi"), size: "sm",
    body: html`<div class="stack"><div class="row wrap">
      <div class="field"><label class="label" for="o-u">${t("Üzrsüz qayıb saatı")}</label><input class="input" id="o-u" type="number" min="0" value="${b.dataset.u}"></div>
      <div class="field"><label class="label" for="o-e">${t("Üzrlü qayıb saatı")}</label><input class="input" id="o-e" type="number" min="0" value="${b.dataset.e}"></div></div>
      <div class="field"><label class="label" for="o-why">${t("Səbəb")}</label><input class="input" id="o-why" maxlength="300"></div></div>`,
    actions: [{ label: t("Saxla"), cls: "btn-primary", onClick: async (w) => {
      try {
        await api.put(`/api/journal/openings/${b.dataset.open}`, { unexcused_hours: Number(w.querySelector("#o-u").value),
          excused_hours: Number(w.querySelector("#o-e").value), reason: w.querySelector("#o-why").value });
        toast(t("Saxlanıldı"), "ok"); drawStanding();
      } catch (err) { toast(err.message, "err"); return false; }
    } }] }));
  mount(el, loading());
  draw();
});

route("/journal/lesson/:id", async (el, p) => {
  let v;
  const marks = new Map();
  const reset = () => { marks.clear(); for (const s of v.students) marks.set(s.id, s.status || "present"); };
  const draw = () => {
    const l = v.lesson;
    const lock = (s) => s.status === "excused" && s.request_id;
    mount(el, html`${pageHead(`${l.course} · ${l.kind || ""}`, `${l.day} · ${l.start}–${l.end}${l.room ? " · " + l.room : ""}${l.teacher ? " · " + l.teacher : ""}`, "",
        crumbs(l.day))}
      ${l.status === "cancelled" ? html`<div class="notice warn mb">${ic("alert", 16)}<div>${t("Dərs ləğv edilib")}${l.note ? ": " + l.note : ""}</div></div>` : ""}
      ${v.before_cutover ? html`<div class="notice warn mb">${ic("alert", 16)}<div>${t("Bu dərs kəsid tarixindən əvvəldir: davamiyyəti köhnə sistemdən idxal olunur.")}</div></div>` : ""}
      ${!v.can_mark && !v.before_cutover && l.status !== "cancelled" ? html`<div class="notice warn mb">${ic("alert", 16)}<div>${v.window_open ? t("Bu dərs hələ keçirilməyib.")
        : t("Düzəliş müddəti ({n} saat) bitib: dəyişikliyi kafedra müdiri səbəblə edir.", { n: v.edit_hours })}</div></div>` : ""}
      <div class="card"><div class="card-h wrap"><h3>${ic("users", 17)} ${t("Siyahı: {n} tələbə", { n: v.students.length })}</h3>
        ${v.can_mark ? html`<button class="btn btn-sm" id="all-present">${t("Hamısı iştirak edir")}</button>` : ""}
        ${v.can_substitute ? html`<button class="btn btn-sm btn-ghost" id="substitute">${t("Əvəzedici müəllim")}</button>` : ""}</div>
      <div class="table-wrap"><table class="table"><thead><tr><th>${t("Tələbə")}</th><th>${t("Qrup")}</th><th>${t("Davamiyyət")}</th></tr></thead><tbody>
        ${v.students.map((s) => html`<tr><td>${s.full_name} <span class="tiny muted">${s.student_no || ""}</span>${s.source === "legacy" ? html` <span class="badge b-gray">${t("idxal")}</span>` : ""}</td>
          <td>${s.group || "—"}${s.subgroup ? " · " + s.subgroup : ""}</td>
          <td>${lock(s) ? html`<span class="badge b-blue">${MARK().excused}</span>` : v.can_mark
            ? html`<div class="seg" role="radiogroup" aria-label="${s.full_name}">${["present", "absent", "late"].map((m) => html`<button type="button" role="radio"
                aria-checked="${marks.get(s.id) === m}" class="${marks.get(s.id) === m ? "active" : ""}" data-s="${s.id}" data-m="${m}">${MARK()[m]}</button>`)}</div>`
            : html`<span>${s.status ? MARK()[s.status] : "—"}</span>`}</td></tr>`)}</tbody></table></div>
      ${v.can_mark ? html`<div class="card-b stack">${v.needs_reason ? html`<div class="field"><label class="label" for="why">${t("Düzəlişin səbəbi")}</label>
          <input class="input" id="why" maxlength="300"></div>` : ""}
        <button class="btn btn-primary" id="save" style="align-self:flex-start">${t("Davamiyyəti saxla")}</button></div>` : ""}</div>`);
  };
  on(el, "click", "[data-m]", (e, b) => {
    marks.set(Number(b.dataset.s), b.dataset.m);
    $$(`[data-s="${b.dataset.s}"]`, el).forEach((x) => { const sel = x.dataset.m === b.dataset.m; x.classList.toggle("active", sel); x.setAttribute("aria-checked", sel); });
  });
  on(el, "click", "#all-present", () => { for (const k of marks.keys()) marks.set(k, "present"); draw(); });
  on(el, "click", "#save", async (e, b) => {
    const body = { marks: Object.fromEntries([...marks].filter(([, m]) => m !== "present")) };
    const why = $("#why", el);
    if (why) body.reason = why.value;
    b.classList.add("loading");
    try { v = await api.put(`/api/journal/lessons/${p.id}/attendance`, body); reset(); toast(t("Davamiyyət saxlanıldı"), "ok"); draw(); }
    catch (err) { toast(err.message, "err"); b.classList.remove("loading"); }
  });
  on(el, "click", "#substitute", async () => {
    let teachers = [];
    try { teachers = (await api.get("/api/directory/users?role=teacher&active=1")).items; } catch (err) { toast(err.message, "err"); return; }
    modal({ title: t("Əvəzedici müəllim"), size: "sm", body: html`<div class="stack">
        <div class="field"><label class="label" for="sub-t">${t("Müəllim")}</label><select class="input" id="sub-t">${teachers.map((x) => html`<option value="${x.id}">${x.full_name}</option>`)}</select></div>
        <div class="field"><label class="label" for="sub-why">${t("Səbəb")}</label><input class="input" id="sub-why" maxlength="300"></div></div>`,
      actions: [{ label: t("Saxla"), cls: "btn-primary", onClick: async (w) => {
        try { v = await api.post(`/api/journal/lessons/${p.id}/teacher`, { teacher_id: Number(w.querySelector("#sub-t").value), reason: w.querySelector("#sub-why").value });
          reset(); toast(t("Saxlanıldı"), "ok"); draw(); }
        catch (err) { toast(err.message, "err"); return false; }
      } }] });
  });
  mount(el, loading());
  try { v = await api.get(`/api/journal/lessons/${p.id}`); } catch (err) { mount(el, failed(err.message)); return; }
  reset();
  draw();
});
