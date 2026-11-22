// The timetable builder's preparation pages (Task 48, slice 3): a teacher's availability grid (/teacher/availability),
// the department head's view of the department (/dept/timetable: readiness, unit needs, the teachers' board) and the
// dean's office's group shifts (/office/timetable). The academic office's builder is timetable-build.js.
// A level is shown as text, never by colour alone; grids are real tables.
import { api, html, mount, on, ic, toast, modal, route, pageHead, loading, failed, empty, t, S, isoDay, fmtDate, fmtDateTime, $, $$ } from "./core.js";
import { HOME } from "./shell.js";

export const DAYS = () => ["", t("Bazar ertəsi"), t("Çərşənbə axşamı"), t("Çərşənbə"), t("Cümə axşamı"), t("Cümə"), t("Şənbə"), t("Bazar")];
export const KIND = () => ({ lecture: t("Mühazirə"), seminar: t("Məşğələ"), lab: t("Laboratoriya") });
const PAIRS = () => [t("1-ci cüt"), t("2-ci cüt"), t("3-cü cüt"), t("4-cü cüt"), t("5-ci cüt"), t("6-cı cüt"), t("7-ci cüt"), t("8-ci cüt")];
export const PAIR = (n) => PAIRS()[n - 1] || t("Cüt {n}", { n });
const LEVELS = ["", "unavailable", "undesired", "preferred"];
const LEVEL = () => ({ "": t("Boş"), unavailable: t("Məşğulam"), undesired: t("Arzuolunmaz"), preferred: t("Üstünlük verirəm") });
const LEVEL_SHORT = () => ({ "": "—", unavailable: t("Məşğul"), undesired: t("Arzuolunmaz"), preferred: t("Üstünlük") });
export const SHIFT = () => ({ morning: t("Səhər növbəsi"), afternoon: t("Günorta növbəsi"), evening: t("Axşam növbəsi") });
const ROOM_KINDS = () => [["lecture_hall", t("Mühazirə zalı")], ["classroom", t("Auditoriya")], ["lab", t("Laboratoriya")], ["computer_lab", t("Kompüter laboratoriyası")]];
export const CONFIRM = () => ({ term_dates: t("Semestrin dərs tarixləri"), lesson_times: t("Zəng cədvəli"), pattern: t("Saatların həftələrə bölgü qaydası"),
  shifts: t("Növbələr"), rooms: t("Otaqlar və tutumları"), limits: t("Günlük və həftəlik hədlər"), travel: t("Binalar arası keçid vaxtı"),
  fixed_slots: t("Universitet üzrə sabit vaxtlar"), weights: t("Yumşaq qaydaların çəkiləri"), availability_cap: t("Məşğulluq həddi"),
  review: t("Rəy mərhələsi"), approver: t("Təsdiq edən şəxs"), practice: t("Təcrübə həftələri"), reserved_weeks: t("Ehtiyat həftələr"), online: t("Onlayn dərslər") });
/** A week set as people read it: nothing for all weeks, "odd"/"even" and ranges in words. */
export const weeksLabel = (w) => (!w || w === "all" ? "" : w === "odd" ? t("tək həftələr") : w === "even" ? t("cüt həftələr") : t("həftələr {w}", { w }));
const WEEK_SETS = () => [["all", t("Bütün həftələr")], ["odd", t("Tək həftələr")], ["even", t("Cüt həftələr")], ["range", t("Seçilmiş həftələr…")]];
// a unit's pattern is typed: the words of the page's language for odd and even weeks, the API's tokens on the wire
const WEEK_WORD = () => ({ [t("tək").toLowerCase()]: "odd", [t("cüt").toLowerCase()]: "even", tək: "odd", cüt: "even" });
const patternIn = (x) => WEEK_WORD()[x.toLowerCase()] || x;
const patternOut = (x) => (x === "odd" ? t("tək") : x === "even" ? t("cüt") : x);
const LINE_LEVEL = () => ({ block: [t("Dayandırır"), "b-red", "alert"], warn: [t("Diqqət"), "b-amber", "info"], ok: [t("Hazırdır"), "b-green", "check"], info: [t("Məlumat"), "b-blue", "info"] });

/** The term the builder works on: ?term=, else the earliest that has not begun, else the latest begun. */
export async function pickTerm(q) {
  const terms = await api.all("/api/directory/terms?active=1");                 // newest first
  const today = isoDay(new Date());
  const wanted = terms.find((x) => String(x.id) === String(q.term));
  const next = terms.filter((x) => x.teaching_start > today).at(-1);
  return { terms, term: (wanted || next || terms.find((x) => x.teaching_start <= today) || terms[0] || null) };
}
export const termSelect = (terms, term) => html`<select class="input input-sm tt-term" aria-label="${t("Semestr")}">${terms.map((x) =>
  html`<option value="${x.id}" ${term && x.id === term.id ? "selected" : ""}>${x.name}</option>`)}</select>`;
export const tabs = (list, cur) => html`<div class="seg mb" role="tablist">${list.map(([k, l]) =>
  html`<button role="tab" aria-selected="${k === cur}" class="${k === cur ? "active" : ""}" data-tab="${k}">${l}</button>`)}</div>`;

/** The readiness checklist: level as text, what it stops, counts, samples (ids) and the page that fixes it. */
export const readinessTable = (r) => html`<div class="table-wrap"><table class="table tt-ready"><thead><tr><th>${t("Vəziyyət")}</th><th>${t("Bənd")}</th>
  <th>${t("Say")}</th><th>${t("Nə dayanır")}</th><th>${t("Nümunələr")}</th><th></th></tr></thead><tbody>
  ${r.lines.map((x) => { const [l, c, i] = LINE_LEVEL()[x.level] || [x.level, "b-gray", "info"];
    return html`<tr data-line="${x.code}"><td><span class="badge ${c}">${ic(i, 13)} ${l}</span></td><td>${x.title}</td>
      <td class="nowrap">${x.code === "term_dates" ? t("{n} həftə, gözlənilən {m}", { n: x.found, m: x.of }) : x.of ? `${x.found} / ${x.of}` : x.found || "—"}</td>
      <td>${x.blocks.length ? x.blocks.map((b) => html`<span class="badge b-red">${b === "run" ? t("hesablama") : t("dərc")}</span> `) : "—"}</td>
      <td class="small">${x.samples.length ? x.samples.map((s, i) => (typeof s === "string" ? CONFIRM()[s] || s : x.code === "lesson_times" ? PAIR(s) : (x.labels || [])[i] || `#${s}`)).join(", ") : "—"}</td>
      <td>${x.fix && x.level !== "ok" && x.fix !== location.hash.slice(1).split("?")[0] ? html`<a class="btn btn-ghost btn-sm" href="#${x.fix}">${t("Düzəlt")}</a>` : ""}</td></tr>`; })}
  </tbody></table></div>`;

// ---------------------------------------------------------------- availability grid (a teacher's own, or a head's for a teacher)
function availabilityEditor(host, termId, uid, { onSaved } = {}) {
  let data, cells, sel = null;
  const mine = uid === S.user.id;
  const key = (wd, p) => `${wd}:${p}`;
  const meter = () => {
    const total = data.days.length * data.periods;
    const un = [...cells.values()].filter((c) => c.level === "unavailable").length;
    const needed = data.feedback.needed_cells;
    const over = Math.max(0, un - Math.floor(total * data.cap_pct / 100), needed - (total - un));
    return { total, un, over, free: total - un };
  };
  const draw = () => {
    const m = meter(), st = data.status, ro = !data.editable;
    mount(host, html`<div class="card"><div class="card-h wrap"><h3>${ic("calendar", 17)} ${mine ? t("Həftəlik məşğulluq") : data.teacher.full_name}</h3>
      <span class="badge ${st.confirmed_at ? "b-green" : "b-amber"}">${st.confirmed_at ? t("Təsdiqlənib: {d}", { d: fmtDateTime(st.confirmed_at) }) : t("Təsdiqlənməyib")}</span>
      ${st.pending ? html`<span class="badge b-violet">${t("Kafedra müdirinin qərarını gözləyir")}</span>` : ""}</div>
      <div class="card-b stack">
        <p class="small muted" style="margin:0">${t("Xananı basdıqca vəziyyəti dəyişir: boş → məşğulam → arzuolunmaz → üstünlük verirəm. «Məşğulam» xanasına dərs qoyulmur; digərləri yalnız nəzərə alınır.")}</p>
        <p class="small" style="margin:0" aria-live="polite" id="av-meter"><b>${t("Həftədə {n} cüt dərsiniz var.", { n: data.feedback.weekly_pairs })} ${t("Boş qalan xana: {n}.", { n: m.free })}</b>
          ${t("Məşğul xanalar: {u} / {t} (hədd {p}%).", { u: m.un, t: m.total, p: data.cap_pct })}
          ${m.over ? html` <span class="badge b-amber">${mine ? t("Hədd {n} xana aşılıb: cədvəl kafedra müdirinin təsdiqinə gedəcək", { n: m.over }) : t("Hədd {n} xana aşılıb", { n: m.over })}</span>` : ""}</p>
        <p class="small muted" style="margin:0">${t("Son tarix: {d}", { d: fmtDate(data.due) })}${st.reopened_until ? " · " + t("Müddət {d} tarixinədək uzadılıb", { d: fmtDate(st.reopened_until) }) : ""}
          ${ro ? html` · <b>${t("Son tarix keçib: dəyişiklik üçün kafedra müdirinə müraciət edin")}</b>` : ""}</p>
        <div class="table-wrap" tabindex="0" role="region" aria-label="${t("Həftəlik məşğulluq")}"><table class="table tt-avail"><thead><tr><th>${t("Cüt")}</th>${data.days.map((d) => html`<th>${DAYS()[d]}</th>`)}</tr></thead><tbody>
          ${Array.from({ length: data.periods }, (_, i) => i + 1).map((p) => html`<tr><th scope="row" class="nowrap">${PAIR(p)}<div class="tiny muted">${(data.times[p - 1] || []).join("–")}</div></th>
            ${data.days.map((d) => { const c = cells.get(key(d, p)) || { level: "" };
              return html`<td><button class="tt-cell lv-${c.level || "free"} ${sel === key(d, p) ? "sel" : ""}" data-cell="${key(d, p)}" ${ro ? "disabled" : ""}
                aria-label="${DAYS()[d]}, ${PAIR(p)}: ${LEVEL()[c.level]}${weeksLabel(c.weeks) ? " · " + weeksLabel(c.weeks) : ""}">${LEVEL_SHORT()[c.level]}${weeksLabel(c.weeks) ? html`<span class="tiny"> · ${weeksLabel(c.weeks)}</span>` : ""}${c.note ? html` ${ic("message", 11)}` : ""}</button></td>`; })}</tr>`)}
        </tbody></table></div>
        ${sel && cells.get(sel) && !ro ? html`<div class="row wrap tt-cell-more"><span class="small"><b>${DAYS()[sel.split(":")[0]]}, ${PAIR(sel.split(":")[1])}</b></span>
          ${(() => { const c = cells.get(sel), kind = c.range || !["all", "odd", "even", undefined, ""].includes(c.weeks) ? "range" : c.weeks || "all";
            return html`<div class="field"><label class="label" for="av-weeks">${t("Həftələr")}</label><select class="input input-sm" id="av-weeks">${WEEK_SETS().map(([k, l]) =>
              html`<option value="${k}" ${k === kind ? "selected" : ""}>${l}</option>`)}</select></div>
            ${kind === "range" ? html`<div class="field"><label class="label" for="av-range">${t("Həftələrin nömrələri (məs.: 1-8, 10)")}</label>
              <input class="input input-sm" id="av-range" value="${["all", "odd", "even"].includes(c.weeks) ? "" : c.weeks || ""}"></div>` : ""}`; })()}
          <div class="field grow"><label class="label" for="av-note">${t("Qeyd (yalnız kafedra görür)")}</label><input class="input input-sm" id="av-note" maxlength="200" value="${cells.get(sel).note || ""}"></div></div>` : ""}
        ${ro ? "" : html`<div class="row wrap"><button class="btn btn-primary" id="av-save">${ic("check", 15)} ${mine && m.over ? t("Kafedra müdirinə göndər") : t("Saxla")}</button>
          <button class="btn" id="av-confirm">${t("Təsdiq edirəm: cədvəlim tamdır")}</button>
          <button class="btn btn-ghost" id="av-clear">${t("Hamısını təmizlə")}</button></div>`}
      </div></div>`);
  };
  const body = () => ({ cells: [...cells.entries()].map(([k, c]) => ({ weekday: Number(k.split(":")[0]), period: Number(k.split(":")[1]), level: c.level,
    weeks: c.weeks || "all", note: c.note || null })) });
  const save = async () => {
    const r = await api.put(`/api/timetable/build/${termId}/teachers/${uid}/availability`, body());
    toast(r.status === "pending" ? t("Hədd aşıldığı üçün cədvəl kafedra müdirinə göndərildi") : t("Saxlanıldı"), "ok");
    return r;
  };
  const load = async () => {
    data = await api.get(`/api/timetable/build/${termId}/teachers/${uid}/availability`);
    cells = new Map(data.cells.map((c) => [key(c.weekday, c.period), c]));
    draw();
  };
  on(host, "click", "[data-cell]", (e, b) => {
    const k = b.dataset.cell, c = cells.get(k) || { level: "" };
    const next = LEVELS[(LEVELS.indexOf(c.level) + 1) % LEVELS.length];
    if (next) cells.set(k, { ...c, level: next }); else cells.delete(k);
    sel = next ? k : null;
    draw();
    host.querySelector(`[data-cell="${k}"]`)?.focus();
  });
  on(host, "change", "#av-weeks", (e, i) => { const c = cells.get(sel); if (c) { c.range = i.value === "range"; if (!c.range) c.weeks = i.value; } draw(); });
  on(host, "change", "#av-range", (e, i) => { const c = cells.get(sel); if (c) c.weeks = i.value.replace(/\s+/g, "") || "all"; draw(); });
  on(host, "change", "#av-note", (e, i) => { const c = cells.get(sel); if (c) c.note = i.value; });
  on(host, "click", "#av-clear", () => { cells.clear(); sel = null; draw(); });
  on(host, "click", "#av-save", async (e, b) => {
    b.disabled = true;
    try { await save(); await load(); onSaved && onSaved(); } catch (err) { toast(err.message, "err"); b.disabled = false; }
  });
  on(host, "click", "#av-confirm", async (e, b) => {
    b.disabled = true;
    try {
      const r = await save();
      if (r.status === "pending") { await load(); return; }
      await api.post(`/api/timetable/build/${termId}/teachers/${uid}/availability/confirm`);
      toast(t("Məşğulluq cədvəliniz təsdiqləndi"), "ok"); await load(); onSaved && onSaved();
    } catch (err) { toast(err.message, "err"); b.disabled = false; }
  });
  return load();
}

route("/teacher/availability", async (el, p, q) => {
  mount(el, loading());
  let terms, term;
  try { ({ terms, term } = await pickTerm(q)); } catch (err) { return mount(el, failed(err.message)); }
  const head = pageHead(t("Məşğulluq vaxtlarım"), t("Dərs deyə bilmədiyiniz vaxtları qeyd edin: cədvəl qurulanda bu vaxtlara dərs qoyulmur."),
    terms.length > 1 ? termSelect(terms, term) : "", [[t("Əsas"), HOME[S.user.role]], [t("Məşğulluq vaxtlarım")]]);
  if (!term) return mount(el, html`${head}${empty("calendar", t("Semestr yoxdur"), t("Tədris şöbəsi semestri yaradanda burada görünür."))}`);
  mount(el, html`${head}<div id="av-host">${loading()}</div>`);
  on(el, "change", ".tt-term", (e, s) => { location.hash = `#/teacher/availability?term=${s.value}`; });
  try { await availabilityEditor($("#av-host", el), term.id, S.user.id); } catch (err) { mount($("#av-host", el), failed(err.message)); }
});

// ---------------------------------------------------------------- department head: readiness, unit needs, teachers
const needsForm = (u, rooms, after, groupNames = "") => {
  const n = u.needs || {};
  modal({ title: t("Vahidin tələbləri"), size: "lg", body: html`<div class="stack">
      <p class="small muted" style="margin:0">${u.course} · ${KIND()[u.kind] || u.kind}${groupNames ? " · " + groupNames : ""}${u.subgroup ? " · " + t("Yarımqrup {n}", { n: u.subgroup }) : ""} · ${t("{h} saat", { h: u.hours ?? "—" })}</p>
      <fieldset class="field"><legend class="label">${t("Otaq növü (boşdursa: vahidin növünə görə)")}</legend><div class="row wrap">${ROOM_KINDS().map(([k, l]) =>
        html`<label class="row small"><input type="checkbox" name="kind" value="${k}" ${(n.room_kinds || []).includes(k) ? "checked" : ""}> ${l}</label>`)}</div></fieldset>
      <div class="field"><label class="label" for="nd-rooms">${t("Yalnız bu otaqlar")}</label><select class="input" id="nd-rooms" multiple size="4">${rooms.map((r) =>
        html`<option value="${r.id}" ${(n.room_ids || []).includes(r.id) ? "selected" : ""}>${r.code}${r.capacity ? ` · ${r.capacity}` : ""}</option>`)}</select></div>
      <div class="row wrap"><div class="field"><label class="label" for="nd-need">${t("Yer sayı")}</label><input class="input" id="nd-need" type="number" min="1" max="2000" value="${n.need ?? ""}" placeholder="${u.students ?? ""}"></div>
        <div class="field grow"><label class="label" for="nd-reason">${t("Yer sayını dəyişməyin səbəbi")}</label><input class="input" id="nd-reason" maxlength="300" value="${n.need_reason || ""}"></div></div>
      <div class="row wrap"><div class="field"><label class="label" for="nd-dur">${t("Bir dərsdə cüt sayı")}</label><input class="input" id="nd-dur" type="number" min="1" max="4" value="${n.duration || 1}"></div>
        <div class="field"><label class="label" for="nd-mode">${t("Forma")}</label><select class="input" id="nd-mode"><option value="in_person">${t("Əyani")}</option>
          <option value="online" ${n.mode === "online" ? "selected" : ""}>${t("Onlayn")}</option></select></div>
        <div class="field grow"><label class="label" for="nd-pattern">${t("Hər dərsin həftələri, nöqtəli vergüllə (məs.: tək; cüt və ya 1-8; 9-15)")}</label><input class="input" id="nd-pattern" value="${(n.pattern || []).map(patternOut).join("; ")}" placeholder="${t("boşdursa: ümumi qayda")}"></div></div>
    </div>`,
  actions: [{ label: t("Saxla"), cls: "btn-primary", onClick: async (w) => {
    const need = w.querySelector("#nd-need").value, pat = w.querySelector("#nd-pattern").value.split(";").map((x) => patternIn(x.trim())).filter(Boolean);
    const kinds = $$("[name=kind]:checked", w).map((x) => x.value), ids = [...w.querySelector("#nd-rooms").selectedOptions].map((o) => Number(o.value));
    try {
      await api.put(`/api/timetable/units/${u.id}/needs`, { room_kinds: kinds.length ? kinds : null, room_ids: ids.length ? ids : null,
        need: need ? Number(need) : null, need_reason: w.querySelector("#nd-reason").value || null, duration: Number(w.querySelector("#nd-dur").value) || 1,
        mode: w.querySelector("#nd-mode").value, pattern: pat.length ? pat : null, split: n.split || null });
      toast(t("Saxlanıldı"), "ok"); after();
    } catch (err) { toast(err.message, "err"); return false; }
  } }] });
};

route("/dept/timetable", async (el, p, q) => {
  mount(el, loading());
  let terms, term, tab = q.tab || "ready";
  try { ({ terms, term } = await pickTerm(q)); } catch (err) { return mount(el, failed(err.message)); }
  const crumbs = [[t("Əsas"), HOME[S.user.role]], [t("Kafedra cədvəli")]];
  const head = () => html`${pageHead(t("Kafedra cədvəli"), t("Semestr cədvəli üçün kafedranın hazırlığı: vahidlərin tələbləri və müəllimlərin məşğulluq vaxtları."),
    terms.length > 1 ? termSelect(terms, term) : "", crumbs)}${tabs([["ready", t("Hazırlıq")], ["units", t("Tələblər")], ["teachers", t("Müəllimlər")]], tab)}`;
  if (!term) return mount(el, html`${head()}${empty("calendar", t("Semestr yoxdur"), t("Tədris şöbəsi semestri yaradanda burada görünür."))}`);
  const B = `/api/timetable/build/${term.id}`;
  let offset = 0, board = null, rooms = null, unitsNow = [], open = null, gnames = {};

  const draw = async () => {
    mount(el, html`${head()}<div id="dp-body">${loading()}</div>`);
    const body = $("#dp-body", el);
    try {
      if (tab === "ready") {
        const r = await api.get(`${B}/readiness`);
        mount(body, html`<div class="card"><div class="card-h"><h3>${ic("check", 17)} ${t("Hazırlıq siyahısı")}</h3></div>${readinessTable(r)}</div>`);
      } else if (tab === "units") {
        const [r, b, gs] = await Promise.all([api.get(`${B}/units?offset=${offset}`), board || api.get(`${B}/teachers`), api.get(`${B}/groups`)]);
        gnames = Object.fromEntries(gs.map((g) => [g.id, g.name]));
        board = b; rooms = rooms || await api.all("/api/directory/rooms?active=1").catch(() => []);
        unitsNow = r.items;
        const names = Object.fromEntries(b.items.map((x) => [x.id, x.full_name]));
        mount(body, html`<div class="card"><div class="card-h"><h3>${ic("layers", 17)} ${t("Tədris vahidləri")}</h3><span class="muted small">${t("{n} vahid", { n: r.total })}</span></div>
          ${r.items.length ? html`<div class="table-wrap"><table class="table"><thead><tr><th>${t("Fənn")}</th><th>${t("Qrup")}</th><th>${t("Növ")}</th><th>${t("Müəllim")}</th><th>${t("Saat")}</th>
            <th>${t("Tələblər")}</th><th></th></tr></thead><tbody>${r.items.map((u) => html`<tr><td>${u.course}</td><td>${groupsOf(u) || "—"}</td><td>${KIND()[u.kind] || u.kind}${u.subgroup ? " · " + u.subgroup : ""}</td>
            <td>${u.teacher_id ? names[u.teacher_id] || `#${u.teacher_id}` : html`<span class="badge b-amber">${t("Vakansiya")}</span>`}</td><td>${u.hours ?? "—"}</td>
            <td class="small">${u.needs ? [u.needs.need ? t("{n} yer", { n: u.needs.need }) : "", u.needs.duration > 1 ? t("{n} cüt", { n: u.needs.duration }) : "",
              u.needs.mode === "online" ? t("Onlayn") : "", (u.needs.pattern || []).map(patternOut).join(", ")].filter(Boolean).join(" · ") || t("standart") : t("standart")}</td>
            <td><button class="btn btn-ghost btn-sm" data-needs="${u.id}">${t("Dəyiş")}</button></td></tr>`)}</tbody></table></div>
            ${r.total > 100 ? html`<div class="card-b row"><button class="btn btn-sm" data-page="-1" ${offset ? "" : "disabled"}>${t("Əvvəlki")}</button>
              <button class="btn btn-sm" data-page="1" ${offset + 100 < r.total ? "" : "disabled"}>${t("Növbəti")}</button></div>` : ""}`
            : html`<div class="card-b">${empty("layers", t("Bu semestrdə kafedranın vahidi yoxdur"), t("Forma №3 idxal olunanda burada görünür."))}</div>`}</div>`);
      } else {
        board = await api.get(`${B}/teachers`);
        mount(body, html`<div class="card"><div class="card-h"><h3>${ic("users", 17)} ${t("Müəllimlərin məşğulluq vaxtları")}</h3><span class="muted small">${t("Son tarix: {d}", { d: fmtDate(board.due) })}</span></div>
          ${board.items.length ? html`<div class="table-wrap"><table class="table"><thead><tr><th>${t("Müəllim")}</th><th>${t("Vahid")}</th><th>${t("Xana")}</th><th>${t("Vəziyyət")}</th><th></th></tr></thead><tbody>
            ${board.items.map((x) => html`<tr><td>${x.full_name}</td><td>${x.units}</td><td>${x.cells}</td>
              <td>${x.pending ? html`<span class="badge b-violet">${t("Qərar gözləyir")}</span>` : x.confirmed_at ? html`<span class="badge b-green">${t("Təsdiqlənib")}</span>`
                : html`<span class="badge ${x.late ? "b-red" : "b-amber"}">${x.late ? t("Gecikir") : t("Təsdiqlənməyib")}</span>`}
                ${x.over_cap_cells ? html` <span class="badge b-gray">${t("Hədd {n} xana aşılıb", { n: x.over_cap_cells })}</span>` : ""}</td>
              <td class="nowrap">${x.pending ? html`<button class="btn btn-sm btn-primary" data-decide="${x.id}">${t("Bax və qərar ver")}</button>` : ""}
                ${x.id !== S.user.id ? html`<button class="btn btn-ghost btn-sm" data-grid="${x.id}">${t("Cədvəlini aç")}</button>
                  <button class="btn btn-ghost btn-sm" data-reopen="${x.id}">${t("Müddəti uzat")}</button>` : ""}</td></tr>`)}</tbody></table></div>`
            : html`<div class="card-b">${empty("users", t("Müəllim yoxdur"), t("Kafedranın bu semestrdə vahidi olan müəllimləri burada görünür."))}</div>`}</div>
          <div id="dp-grid" class="mt"></div>`);
        if (open) await availabilityEditor($("#dp-grid", el), term.id, open, { onSaved: () => {} });
      }
    } catch (err) { mount(body, failed(err.message)); }
  };
  on(el, "click", "[data-tab]", (e, b) => { tab = b.dataset.tab; open = null; draw(); });
  on(el, "change", ".tt-term", (e, s) => { location.hash = `#/dept/timetable?term=${s.value}`; });
  on(el, "click", "[data-page]", (e, b) => { offset = Math.max(0, offset + Number(b.dataset.page) * 100); draw(); });
  const groupsOf = (u) => (u.groups || []).map((g) => gnames[g] || `#${g}`).join(", ");
  on(el, "click", "[data-needs]", (e, b) => { const u = unitsNow.find((x) => x.id === Number(b.dataset.needs)); needsForm(u, rooms || [], draw, groupsOf(u)); });
  on(el, "click", "[data-grid]", (e, b) => { open = Number(b.dataset.grid); draw(); });
  on(el, "click", "[data-decide]", async (e, b) => {
    const uid = Number(b.dataset.decide);
    let a;
    try { a = await api.get(`${B}/teachers/${uid}/availability`); } catch (err) { return toast(err.message, "err"); }
    const pend = new Map((a.status.pending || []).map((c) => [`${c.weekday}:${c.period}`, c]));
    const decide = async (approve) => {
      try { await api.post(`${B}/teachers/${uid}/availability/decide`, { approve }); toast(approve ? t("Təsdiqləndi") : t("Qəbul edilmədi"), "ok"); draw(); }
      catch (err) { toast(err.message, "err"); return false; }
    };
    modal({ title: t("Gözləyən məşğulluq cədvəli: {name}", { name: a.teacher.full_name }), size: "lg", body: html`<p class="small">${t("Müəllim həddən çox xananı məşğul qeyd edib. Təsdiq etsəniz, cədvəl qüvvəyə minir.")}</p>
      <div class="table-wrap"><table class="table tt-avail"><thead><tr><th>${t("Cüt")}</th>${a.days.map((d) => html`<th>${DAYS()[d]}</th>`)}</tr></thead><tbody>
      ${Array.from({ length: a.periods }, (_, i) => i + 1).map((p) => html`<tr><th scope="row">${PAIR(p)}</th>${a.days.map((d) => { const c = pend.get(`${d}:${p}`);
        return html`<td><span class="tt-cell lv-${c ? c.level : "free"}">${LEVEL_SHORT()[c ? c.level : ""]}${c && weeksLabel(c.weeks) ? html`<span class="tiny"> · ${weeksLabel(c.weeks)}</span>` : ""}</span>
          ${c && c.note ? html`<div class="tiny">${ic("message", 11)} ${c.note}</div>` : ""}</td>`; })}</tr>`)}</tbody></table></div>`,
    actions: [{ label: t("İmtina et"), cls: "btn-danger", onClick: () => decide(false) }, { label: t("Təsdiq et"), cls: "btn-primary", onClick: () => decide(true) }] });
  });
  on(el, "click", "[data-reopen]", (e, b) => modal({ title: t("Müddəti uzat"), size: "sm", body: html`<div class="field"><label class="label" for="ro-until">${t("Yeni son tarix")}</label>
      <input class="input" id="ro-until" type="date" min="${isoDay(new Date())}" max="${term.teaching_end}"></div>`,
    actions: [{ label: t("Uzat"), cls: "btn-primary", onClick: async (w) => {
      try { await api.post(`${B}/teachers/${b.dataset.reopen}/availability/reopen`, { until: w.querySelector("#ro-until").value }); toast(t("Saxlanıldı"), "ok"); draw(); }
      catch (err) { toast(err.message, "err"); return false; }
    } }] }));
  draw();
});

// ---------------------------------------------------------------- dean's office: the groups' shifts
route("/office/timetable", async (el, p, q) => {
  mount(el, loading());
  let terms, term, groups, st;
  try {
    ({ terms, term } = await pickTerm(q));
    if (term) [groups, st] = await Promise.all([api.get(`/api/timetable/build/${term.id}/groups`), api.get("/api/timetable/settings")]);
  } catch (err) { return mount(el, failed(err.message)); }
  const head = pageHead(t("Fakültə cədvəli"), t("Qrupların növbəsi: cədvəl qurulanda qrupun dərsləri yalnız öz növbəsinin cütlərinə qoyulur."),
    terms.length > 1 ? termSelect(terms, term) : "", [[t("Əsas"), HOME[S.user.role]], [t("Fakültə cədvəli")]]);
  if (!term) return mount(el, html`${head}${empty("calendar", t("Semestr yoxdur"), t("Tədris şöbəsi semestri yaradanda burada görünür."))}`);
  const shifts = Object.keys(st.timetable.shifts);
  const label = (k) => `${SHIFT()[k] || k} (${st.timetable.shifts[k].join(", ")})`;
  mount(el, html`${head}<div class="card"><div class="card-h wrap"><h3>${ic("users", 17)} ${t("Qrupların növbəsi")}</h3>
      ${groups.length ? html`<div class="row wrap"><label class="small" for="og-all">${t("Hamısına")}</label><select class="input input-sm" id="og-all"><option value="">—</option>${shifts.map((k) => html`<option value="${k}">${label(k)}</option>`)}</select>
      <button class="btn btn-primary btn-sm" id="og-save">${ic("check", 15)} ${t("Saxla")}</button></div>` : ""}</div>
    ${groups.length ? html`<div class="table-wrap"><table class="table"><thead><tr><th>${t("Qrup")}</th><th>${t("Qrupun növbəsi")}</th></tr></thead><tbody>
      ${groups.map((g) => html`<tr><td>${g.name}</td><td><select class="input input-sm" data-group="${g.id}" aria-label="${t("Qrupun növbəsi")}: ${g.name}">
        <option value="">${t("Göstərilməyib")}</option>${shifts.map((k) => html`<option value="${k}" ${g.shift === k ? "selected" : ""}>${label(k)}</option>`)}</select></td></tr>`)}</tbody></table></div>`
      : html`<div class="card-b">${empty("users", t("Qrup yoxdur"), t("Fakültənin bu semestrdə dərsi olan qrupları burada görünür."))}</div>`}</div>`);
  on(el, "change", ".tt-term", (e, s) => { location.hash = `#/office/timetable?term=${s.value}`; });
  on(el, "change", "#og-all", (e, s) => { if (s.value) $$("[data-group]", el).forEach((x) => { x.value = s.value; }); });
  on(el, "click", "#og-save", async (e, b) => {
    b.disabled = true;
    try {
      const items = $$("[data-group]", el).map((x) => ({ group_id: Number(x.dataset.group), shift: x.value || null,
        home_building_id: (groups.find((g) => g.id === Number(x.dataset.group)) || {}).home_building_id ?? null }));
      for (let i = 0; i < items.length; i += 500) await api.put(`/api/timetable/build/${term.id}/groups`, { items: items.slice(i, i + 500) });
      toast(t("Saxlanıldı"), "ok");
    } catch (err) { toast(err.message, "err"); } finally { b.disabled = false; }
  });
});
