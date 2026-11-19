// The university's structure and register (Task 15): faculties, departments, specialties, groups, terms; people,
// courses, teaching units, enrolments and students' status orders. Lists are paged and searched on the server;
// rows are deactivated, never deleted; an enrolment is ended, a status order is only added.
import { api, html, mount, on, ic, toast, modal, route, pageHead, loading, failed, $, $$, t, S } from "./core.js";
import { HOME, ROLE_LABEL } from "./shell.js";

const DEGREES = () => [["bachelor", t("Bakalavriat")], ["master", t("Magistratura")], ["phd", t("Doktorantura")]];
const UNIT_KINDS = () => [["lecture", t("Mühazirə")], ["seminar", t("Məşğələ")], ["lab", t("Laboratoriya")]];
const STATUS_KINDS = () => [["admission", t("Qəbul")], ["group_change", t("Qrup dəyişikliyi")], ["transfer_in", t("Köçürülmə (gəliş)")],
  ["transfer_out", t("Köçürülmə (gediş)")], ["academic_leave", t("Akademik məzuniyyət")], ["expulsion", t("Xaric olunma")],
  ["reinstatement", t("Bərpa")], ["graduation", t("Məzun olma")]];
const STATUS = () => ({ active: t("Təhsil alır"), on_leave: t("Akademik məzuniyyətdə"), expelled: t("Xaric olunub"),
  transferred: t("Köçürülüb"), graduated: t("Məzun olub") });
const ROOM_KINDS = () => [["lecture_hall", t("Mühazirə zalı")], ["classroom", t("Auditoriya")], ["lab", t("Laboratoriya")],
  ["computer_lab", t("Kompüter laboratoriyası")], ["office", t("Otaq")], ["other", t("Digər")]];
const FLAG = () => [["0", t("Xeyr")], ["1", t("Bəli")]];
const MANAGERS = ["admin", "academic_office"];
const ENT = () => ({
  faculties: { title: t("Fakültələr"), cols: [["code", t("Kod")], ["name", t("Ad")]],
    fields: [["code", t("Kod"), "text"], ["name", t("Ad"), "text"]] },
  departments: { title: t("Kafedralar"), cols: [["code", t("Kod")], ["name", t("Ad")], ["faculty_id", t("Fakültə"), "faculties"]],
    fields: [["faculty_id", t("Fakültə"), "ref:faculties"], ["code", t("Kod"), "text"], ["name", t("Ad"), "text"]] },
  specialties: { title: t("İxtisaslar"), cols: [["code", t("Kod")], ["name", t("Ad")], ["faculty_id", t("Fakültə"), "faculties"], ["degree", t("Dərəcə"), "degree"]],
    fields: [["faculty_id", t("Fakültə"), "ref:faculties"], ["department_id", t("Kafedra"), "ref?:departments"], ["code", t("Kod"), "text"],
      ["name", t("Ad"), "text"], ["degree", t("Dərəcə"), "degree"]] },
  groups: { title: t("Qruplar"), cols: [["name", t("Qrup")], ["year", t("Qəbul ili")], ["faculty_id", t("Fakültə"), "faculties"], ["specialty_id", t("İxtisas"), "specialties"]],
    fields: [["name", t("Qrup"), "text"], ["year", t("Qəbul ili"), "number"], ["faculty_id", t("Fakültə"), "ref:faculties"], ["specialty_id", t("İxtisas"), "ref?:specialties"]] },
  terms: { title: t("Semestrlər"), cols: [["code", t("Kod")], ["name", t("Ad")], ["teaching_start", t("Tədris"), "period:teaching"], ["exam_start", t("İmtahan sessiyası"), "period:exam"]],
    fields: [["code", t("Kod"), "text"], ["name", t("Ad"), "text"], ["teaching_start", t("Tədrisin başlanğıcı"), "date"], ["teaching_end", t("Tədrisin sonu"), "date"],
      ["exam_start", t("Sessiyanın başlanğıcı"), "date"], ["exam_end", t("Sessiyanın sonu"), "date"]] },
  users: { title: t("İstifadəçilər"), readers: MANAGERS, managers: ["admin"], search: t("Ad, istifadəçi adı, bilet nömrəsi və ya e-poçt"),
    cols: [["full_name", t("Ad, soyad")], ["username", t("İstifadəçi adı")], ["role", t("Rol"), "role"], ["group_id", t("Qrup"), "groups"], ["student_no", t("Bilet №")]],
    fields: [["username", t("İstifadəçi adı"), "text"], ["full_name", t("Ad, soyad"), "text"], ["role", t("Rol"), "role"], ["group_id", t("Qrup"), "ref?:groups"],
      ["student_no", t("Tələbə bileti №"), "text?"], ["email", t("E-poçt"), "text?"], ["department_id", t("Kafedra"), "ref?:departments"]] },
  courses: { title: t("Fənlər"), cols: [["code", t("Kod")], ["name", t("Ad")], ["teacher_id", t("Rəhbər müəllim"), "teachers"], ["credits", t("Kredit")], ["term_id", t("Semestr"), "terms"]],
    fields: [["code", t("Kod"), "text"], ["name", t("Ad"), "text"], ["teacher_id", t("Rəhbər müəllim"), "ref?:teachers"], ["credits", t("Kredit"), "number"],
      ["department_id", t("Kafedra"), "ref?:departments"], ["term_id", t("Semestr"), "ref?:terms"]] },
  units: { title: t("Tədris vahidləri"), cols: [["course_id", t("Fənn"), "courses"], ["kind", t("Növ"), "unit_kind"], ["teacher_id", t("Müəllim"), "teachers"], ["subgroup", t("Yarımqrup")]],
    fields: [["course_id", t("Fənn"), "ref:courses"], ["kind", t("Növ"), "unit_kind"], ["teacher_id", t("Müəllim"), "ref?:teachers"], ["subgroup", t("Yarımqrup"), "number"]] },
  buildings: { title: t("Korpuslar"), cols: [["code", t("Kod")], ["name", t("Ad")], ["address", t("Ünvan")]],
    fields: [["code", t("Kod"), "text"], ["name", t("Ad"), "text"], ["address", t("Ünvan"), "text?"]] },
  rooms: { title: t("Otaqlar"), search: t("Kod, nömrə və ya ad"),
    cols: [["code", t("Kod")], ["building_id", t("Korpus"), "buildings"], ["number", t("Nömrə")], ["name", t("Ad")], ["kind", t("Növ"), "room_kind"], ["capacity", t("Tutum")]],
    fields: [["building_id", t("Korpus"), "ref:buildings"], ["code", t("Kod (QR ünvanı)"), "text"], ["number", t("Nömrə (qapıda)"), "text"],
      ["name", t("Ad"), "text?"], ["floor", t("Mərtəbə"), "number"], ["kind", t("Növ"), "room_kind"], ["capacity", t("Tutum"), "number"],
      ["accessible", t("Əlil arabası ilə əlçatan"), "flag"]] },
});
// shortcut: a reference list holds its first page (50 rows); a search picker replaces it once Task 16 imports real data
const REF_URL = { teachers: "/api/directory/users?active=1&role=teacher" };
const label = (o) => (o ? o.name || o.full_name || o.code : "");
const optionsOf = (pairs, v) => pairs.map(([k, l]) => html`<option value="${k}" ${k === v ? "selected" : ""}>${l}</option>`);

route("/admin/directory", async (el, p, q) => {
  const ent = ENT();
  const role = S.user.role;
  const tabs = Object.entries(ent).filter(([, v]) => !v.readers || v.readers.includes(role));
  const canManage = (k) => (ent[k].managers || MANAGERS).includes(role);
  let tab = tabs.some(([k]) => k === q.tab) ? q.tab : "faculties", page = 1, query = "", refs = {}, items = [], timer = null;
  const refNames = (e) => [...new Set(e.fields.filter(([, , k]) => k.startsWith("ref")).map(([, , k]) => k.split(":")[1]))];
  const loadRefs = async (e) => {
    for (const n of refNames(e)) {
      if (refs[n]) continue;
      try { refs[n] = Object.fromEntries((await api.get(REF_URL[n] || `/api/directory/${n}?active=1`)).items.map((x) => [x.id, x])); }
      catch (err) {
        if (err.status !== 403) toast(err.message, "err");   // a list this role may not read: names show as #id
        refs[n] = {};
      }
    }
  };
  const cell = (x, [k, , kind]) => {
    if (kind === "degree") return (DEGREES().find(([v]) => v === x[k]) || [, x[k]])[1];
    if (kind === "unit_kind") return (UNIT_KINDS().find(([v]) => v === x[k]) || [, x[k]])[1];
    if (kind === "room_kind") return (ROOM_KINDS().find(([v]) => v === x[k]) || [, x[k]])[1];
    if (kind === "role") return ROLE_LABEL[x[k]] || x[k];
    if (kind === "period:teaching") return `${x.teaching_start} — ${x.teaching_end}`;
    if (kind === "period:exam") return `${x.exam_start} — ${x.exam_end}`;
    if (kind && refs[kind]) return x[k] ? (refs[kind][x[k]] ? label(refs[kind][x[k]]) : `#${x[k]}`) : "—";
    return x[k] ?? "—";
  };
  const extra = (x) => html`${tab === "courses" ? html`<button class="btn btn-ghost btn-sm" data-enr="${x.id}">${t("Tələbələr")}</button>` : ""}
    ${tab === "units" && canManage(tab) ? html`<button class="btn btn-ghost btn-sm" data-groups="${x.id}">${t("Qruplar")}</button>` : ""}
    ${tab === "users" && x.role === "student" ? html`<button class="btn btn-ghost btn-sm" data-status="${x.id}">${t("Status")}</button>` : ""}
    ${tab === "buildings" && canManage(tab) ? html`<a class="btn btn-ghost btn-sm" href="/api/facilities/buildings/${x.id}/qr" target="_blank" rel="noopener">${t("QR vərəqi")}</a>` : ""}
    ${tab === "rooms" ? html`<a class="btn btn-ghost btn-sm" href="/r/${encodeURIComponent(x.code)}" target="_blank" rel="noopener">${t("Səhifə")}</a>` : ""}`;
  const draw = async () => {
    const e = ent[tab];
    const can = canManage(tab);
    let r;
    try { await loadRefs(e); r = await api.get(`/api/directory/${tab}?page=${page}&q=${encodeURIComponent(query)}`); }
    catch (err) { mount(el, failed(err.message)); return; }
    items = r.items;
    mount(el, html`${pageHead(t("Struktur və reyestr"), t("Struktur, semestrlər, istifadəçilər, fənlər və qeydiyyat. Sətirlər silinmir, deaktiv edilir."), "",
        [[t("Əsas"), HOME[role]], [t("Struktur və reyestr")]])}
      <div class="seg mb wrap" role="tablist">${tabs.map(([k, v]) => html`<button role="tab" aria-selected="${k === tab}" class="${k === tab ? "active" : ""}" data-tab="${k}">${v.title}</button>`)}</div>
      <div class="card"><div class="card-h wrap"><input class="input input-sm" id="dir-q" type="search" placeholder="${e.search || t("Kod və ya ad üzrə axtar")}" aria-label="${t("Axtar")}" value="${query}" style="max-width:320px">
        ${can ? html`<button class="btn btn-primary btn-sm" id="dir-new">${ic("plus", 15)} ${t("Yeni")}</button>` : ""}
        ${can && tab === "rooms" ? html`<button class="btn btn-sm" id="dir-link-rooms">${t("Cədvəli otaqlara bağla")}</button>` : ""}</div>
      <div class="table-wrap"><table class="table"><thead><tr>${e.cols.map((c) => html`<th>${c[1]}</th>`)}<th>${t("Vəziyyət")}</th><th></th></tr></thead><tbody>
        ${items.map((x) => html`<tr><td>${cell(x, e.cols[0])}</td>${e.cols.slice(1).map((c) => html`<td>${cell(x, c)}</td>`)}
          <td>${x.active ? html`<span class="badge b-green">${t("Aktiv")}</span>` : html`<span class="badge b-gray">${t("Deaktiv")}</span>`}</td>
          <td class="nowrap">${can ? html`<button class="btn btn-ghost btn-sm" data-edit="${x.id}">${t("Düzəlt")}</button><button class="btn btn-ghost btn-sm" data-toggle="${x.id}">${x.active ? t("Deaktiv et") : t("Aktiv et")}</button>` : ""}${extra(x)}</td></tr>`)}
      </tbody></table></div>
      ${items.length ? "" : html`<div class="card-b"><p class="muted" style="margin:0">${t("Heç nə tapılmadı")}</p></div>`}
      <div class="card-b row between"><span class="small muted">${t("Cəmi: {n}", { n: r.total })}</span>
        <div class="row"><button class="btn btn-sm" data-page="${page - 1}" aria-label="${t("Əvvəlki səhifə")}">←</button>
          <span class="small">${page} / ${r.pages}</span><button class="btn btn-sm" data-page="${page + 1}" aria-label="${t("Növbəti səhifə")}">→</button></div></div></div>`);
    $("[data-page='" + (page - 1) + "']", el).disabled = page <= 1;
    $("[data-page='" + (page + 1) + "']", el).disabled = page >= r.pages;
  };
  const input = ([k, lbl, kind], x) => {
    const v = x ? x[k] ?? "" : "";
    const wrap = (inner) => html`<div class="field"><label class="label" for="f-${k}">${lbl}</label>${inner}</div>`;
    if (kind.startsWith("ref")) {
      const target = refs[kind.split(":")[1]] || {};
      return wrap(html`<select class="input" id="f-${k}" name="${k}">${kind.startsWith("ref?") || !v ? html`<option value="">—</option>` : ""}
        ${Object.values(target).map((o) => html`<option value="${o.id}" ${o.id === v ? "selected" : ""}>${label(o)}</option>`)}</select>`);
    }
    if (kind === "degree") return wrap(html`<select class="input" id="f-${k}" name="${k}">${optionsOf(DEGREES(), v || "bachelor")}</select>`);
    if (kind === "unit_kind") return wrap(html`<select class="input" id="f-${k}" name="${k}">${optionsOf(UNIT_KINDS(), v || "lecture")}</select>`);
    if (kind === "room_kind") return wrap(html`<select class="input" id="f-${k}" name="${k}">${optionsOf(ROOM_KINDS(), v || "classroom")}</select>`);
    if (kind === "flag") return wrap(html`<select class="input" id="f-${k}" name="${k}">${optionsOf(FLAG(), String(v || 0))}</select>`);
    if (kind === "role") return wrap(html`<select class="input" id="f-${k}" name="${k}">${optionsOf(Object.entries(ROLE_LABEL), v || "student")}</select>`);
    const type = kind === "number" ? "number" : kind === "date" ? "date" : "text";
    return wrap(html`<input class="input" id="f-${k}" name="${k}" type="${type}" value="${v}">`);
  };
  const form = (x) => {
    const e = ent[tab];
    modal({ title: x ? t("Düzəlt") : t("Yeni"), body: html`<div class="stack">${e.fields.map((f) => input(f, x))}</div>`,
      actions: [{ label: t("Saxla"), cls: "btn-primary", onClick: async (w) => {
        const body = {};
        for (const [k, , kind] of e.fields) {
          const v = w.querySelector(`[name="${k}"]`).value;
          body[k] = kind.startsWith("ref") || kind === "number" || kind === "flag" ? (v === "" ? null : Number(v)) : kind === "text?" && v === "" ? null : v;
        }
        try {
          if (x) await api.put(`/api/directory/${tab}/${x.id}`, body); else await api.post(`/api/directory/${tab}`, body);
          toast(t("Saxlanıldı"), "ok"); refs = {}; draw();
        } catch (err) { toast(err.message, "err"); return false; }
      } }] });
  };

  // ---- enrolments of a course
  const enrolments = async (course) => {
    const path = `/api/directory/courses/${course.id}/enrollments`;
    const can = MANAGERS.includes(role);
    const m = modal({ title: t("{x}: qeydiyyat", { x: course.name }), size: "lg", body: html`<div id="enr-box">${loading()}</div>` });
    const box = $("#enr-box", m.el);
    const show = async (list) => {
      list = list || await api.get(path);
      mount(box, html`<div class="table-wrap"><table class="table"><thead><tr><th>${t("Tələbə")}</th><th>${t("Bilet №")}</th><th>${t("Qrup")}</th>
          <th>${t("Yarımqrup")}</th><th>${t("Başlanğıc")}</th><th>${t("Bitmə")}</th><th></th></tr></thead><tbody>
        ${list.map((x) => html`<tr><td>${x.full_name}</td><td>${x.student_no || "—"}</td><td>${x.group_name || "—"}</td><td>${x.subgroup || "—"}</td>
          <td>${x.begin_date || "—"}</td><td>${x.end_date || "—"}</td>
          <td>${can && !x.end_date ? html`<button class="btn btn-ghost btn-sm" data-end="${x.user_id}">${t("Bitir")}</button>` : ""}</td></tr>`)}</tbody></table></div>
        ${list.length ? "" : html`<p class="muted">${t("Qeydiyyatda tələbə yoxdur")}</p>`}
        ${can ? html`<div class="stack mt"><b>${t("Tələbə əlavə et")}</b>
          <input class="input" id="enr-q" type="search" placeholder="${t("Ad, istifadəçi adı və ya bilet nömrəsi")}" aria-label="${t("Tələbə axtar")}">
          <select class="input" id="enr-user" aria-label="${t("Tələbə")}"><option value="">—</option></select>
          <div class="row wrap"><label class="small">${t("Yarımqrup")} <input class="input input-sm" id="enr-sub" type="number" min="1" max="9" style="width:80px"></label>
            <label class="small">${t("Başlanğıc")} <input class="input input-sm" id="enr-begin" type="date"></label>
            <button class="btn btn-primary btn-sm" id="enr-add">${t("Əlavə et")}</button></div></div>` : ""}`);
    };
    on(m.el, "input", "#enr-q", (ev, i) => { clearTimeout(timer); timer = setTimeout(async () => {
      const found = (await api.get(`/api/directory/users?role=student&active=1&q=${encodeURIComponent(i.value)}`)).items;
      mount($("#enr-user", m.el), html`<option value="">—</option>${found.map((u) => html`<option value="${u.id}">${u.full_name} · ${u.student_no || u.username}</option>`)}`);
    }, 300); });
    on(m.el, "click", "#enr-add", async () => {
      const uid = Number($("#enr-user", m.el).value);
      if (!uid) { toast(t("Tələbəni seçin"), "err"); return; }
      const sub = $("#enr-sub", m.el).value;
      try { await show(await api.post(path, { user_id: uid, subgroup: sub ? Number(sub) : null, begin_date: $("#enr-begin", m.el).value || null })); toast(t("Saxlanıldı"), "ok"); }
      catch (err) { toast(err.message, "err"); }
    });
    on(m.el, "click", "[data-end]", (ev, b) => modal({ title: t("Qeydiyyatı bitir"), size: "sm",
      body: html`<div class="field"><label class="label" for="enr-end">${t("Bitmə tarixi")}</label><input class="input" id="enr-end" type="date"></div>
        <p class="small muted" style="margin:0">${t("Bu tarixdən dərs siyahılarında görünmür; əvvəlki davamiyyət və ballar qalır.")}</p>`,
      actions: [{ label: t("Bitir"), cls: "btn-primary", onClick: async (w) => {
        try { await show(await api.post(`${path}/${b.dataset.end}/end`, { end_date: w.querySelector("#enr-end").value })); }
        catch (err) { toast(err.message, "err"); return false; }
      } }] }));
    try { await show(); } catch (err) { mount(box, failed(err.message)); }
  };

  // ---- status orders of a student
  const statusOf = async (u) => {
    const path = `/api/directory/students/${u.id}/status`;
    const enter = role === "academic_office";
    const kinds = Object.fromEntries(STATUS_KINDS());
    const m = modal({ title: t("{x}: status əmrləri", { x: u.full_name }), size: "lg", body: html`<div id="st-box">${loading()}</div>` });
    const box = $("#st-box", m.el);
    await loadRefs({ fields: [["", "", "ref:groups"]] });
    const show = (s) => mount(box, html`<p>${t("Hazırkı status")}: <b>${STATUS()[s.status] || s.status}</b></p>
      ${MANAGERS.includes(role) ? html`<div class="row wrap mb"><button class="btn btn-sm" id="st-reconcile">${t("Əvvəlki semestrlər uzlaşdırılıb")}</button>
        <span class="small muted">${t("Köhnə sistemdən gələn qiymətlər yoxlanandan sonra transkript verilir.")}</span></div>` : ""}
      <div class="table-wrap"><table class="table"><thead><tr><th>${t("Əmr")}</th><th>${t("Nömrə")}</th><th>${t("Əmrin tarixi")}</th>
        <th>${t("Qüvvəyə minir")}</th><th>${t("Qeyd")}</th></tr></thead><tbody>
      ${s.events.map((x) => html`<tr><td>${kinds[x.kind] || x.kind}</td><td>${x.order_no}</td><td>${x.order_date}</td><td>${x.effective_date}</td>
        <td class="small">${x.note || "—"}</td></tr>`)}</tbody></table></div>
      ${s.events.length ? "" : html`<p class="muted">${t("Əmr yoxdur")}</p>`}
      ${enter ? html`<div class="stack mt"><b>${t("Yeni əmr")}</b>
        <select class="input" id="st-kind" aria-label="${t("Əmrin növü")}">${optionsOf(STATUS_KINDS(), "academic_leave")}</select>
        <div class="row wrap"><input class="input" id="st-no" placeholder="${t("Əmrin nömrəsi")}" aria-label="${t("Əmrin nömrəsi")}" style="max-width:180px">
          <label class="small">${t("Əmrin tarixi")} <input class="input input-sm" id="st-date" type="date"></label>
          <label class="small">${t("Qüvvəyə minir")} <input class="input input-sm" id="st-eff" type="date"></label></div>
        <select class="input" id="st-group" aria-label="${t("Yeni qrup")}"><option value="">${t("Yeni qrup (qrup dəyişikliyi və gəliş üçün)")}</option>
          ${Object.values(refs.groups || {}).map((g) => html`<option value="${g.id}">${g.name}</option>`)}</select>
        <input class="input" id="st-note" placeholder="${t("Qeyd (düzəliş əmridirsə, səbəbini yazın)")}" aria-label="${t("Qeyd")}">
        <p class="small muted" style="margin:0">${t("Əmrlər dəyişdirilmir və silinmir: səhv əmr yeni əmrlə düzəldilir.")}</p>
        <button class="btn btn-primary btn-sm" id="st-add" style="align-self:flex-start">${t("Əmri yaz")}</button></div>` : ""}`);
    on(m.el, "click", "#st-reconcile", async () => {
      try { await api.post(`/api/journal/students/${u.id}/reconcile`); toast(t("Qeyd olundu: transkript verilə bilər"), "ok"); }
      catch (err) { toast(err.message, "err"); }
    });
    on(m.el, "click", "#st-add", async () => {
      const g = $("#st-group", m.el).value;
      try {
        show(await api.post(path, { kind: $("#st-kind", m.el).value, order_no: $("#st-no", m.el).value, order_date: $("#st-date", m.el).value,
          effective_date: $("#st-eff", m.el).value, to_group_id: g ? Number(g) : null, note: $("#st-note", m.el).value }));
        toast(t("Əmr yazıldı"), "ok");
      } catch (err) { toast(err.message, "err"); }
    });
    try { show(await api.get(path)); } catch (err) { mount(box, failed(err.message)); }
  };

  // ---- groups of a teaching unit
  const unitGroups = async (unit) => {
    await loadRefs({ fields: [["", "", "ref:groups"]] });
    const have = new Set((await api.get(`/api/directory/units/${unit.id}/groups`)).group_ids);
    modal({ title: t("Tədris vahidinin qrupları"), body: html`<div class="stack">${Object.values(refs.groups || {}).map((g) =>
        html`<label class="check"><input type="checkbox" value="${g.id}" ${have.has(g.id) ? "checked" : ""}> ${g.name}</label>`)}</div>`,
      actions: [{ label: t("Saxla"), cls: "btn-primary", onClick: async (w) => {
        try { await api.put(`/api/directory/units/${unit.id}/groups`, { group_ids: $$("input:checked", w).map((i) => Number(i.value)) }); toast(t("Saxlanıldı"), "ok"); }
        catch (err) { toast(err.message, "err"); return false; }
      } }] });
  };

  const find = (b, key) => items.find((x) => x.id === Number(b.dataset[key]));
  on(el, "click", "[data-tab]", (ev, b) => { tab = b.dataset.tab; page = 1; query = ""; draw(); });
  on(el, "click", "[data-page]", (ev, b) => { page = Number(b.dataset.page); draw(); });
  on(el, "input", "#dir-q", (ev, i) => { clearTimeout(timer); timer = setTimeout(() => { query = i.value; page = 1; draw().then(() => { const n = $("#dir-q", el); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }); }, 300); });
  on(el, "click", "#dir-new", () => form(null));
  on(el, "click", "#dir-link-rooms", async () => {
    let r;
    try { r = await api.post("/api/facilities/link-rooms"); } catch (err) { toast(err.message, "err"); return; }
    modal({ title: t("Cədvəl və otaqlar"), size: "lg", body: html`<p>${t("Otağa bağlanan cədvəl sətri: {n}", { n: r.linked })}</p>
      ${r.unmatched.length ? html`<p class="small muted">${t("Bu yazılar heç bir otağa (və ya birdən çox otağa) uyğun gəlmir. Otağı əlavə edin və ya cədvəldə düzəldin:")}</p>
        <div class="table-wrap"><table class="table"><thead><tr><th>${t("Cədvəldəki yazı")}</th><th>${t("Sətir")}</th></tr></thead><tbody>
        ${r.unmatched.map((x) => html`<tr><td>${x.room}</td><td>${x.rows}</td></tr>`)}</tbody></table></div>`
        : html`<p class="muted">${t("Bütün cədvəl sətirləri otağa bağlandı")}</p>`}` });
  });
  on(el, "click", "[data-edit]", (ev, b) => form(find(b, "edit")));
  on(el, "click", "[data-enr]", (ev, b) => enrolments(find(b, "enr")));
  on(el, "click", "[data-status]", (ev, b) => statusOf(find(b, "status")));
  on(el, "click", "[data-groups]", (ev, b) => unitGroups(find(b, "groups")));
  on(el, "click", "[data-toggle]", async (ev, b) => {
    const x = find(b, "toggle");
    try { await api.post(`/api/directory/${tab}/${x.id}/${x.active ? "deactivate" : "activate"}`); refs = {}; draw(); }
    catch (err) { toast(err.message, "err"); }
  });
  mount(el, loading());
  draw();
});
