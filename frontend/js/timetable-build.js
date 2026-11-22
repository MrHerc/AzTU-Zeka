// The academic office's timetable builder (Task 48, slice 3): readiness, the settings and the term's plan, runs in the
// job runner (progress polled every 5 s, cancel), versions with their scorecards and a comparison, and a version's
// editor: grids by group, teacher or room; a meeting moved by drag or by keyboard (Enter, arrows, Enter) with the live
// clash check of every slot (a blocked slot says why, in text); locks; unplaced meetings with reasons; the check run;
// and the publication (shown only to an unscoped academic office: the server refuses everyone else anyway).
import { api, html, mount, on, ic, toast, modal, route, pageHead, loading, failed, empty, t, S, isoDay, fmtDate, fmtDateTime, progress, $, $$ } from "./core.js";
import { HOME } from "./shell.js";
import { DAYS, KIND, PAIR, SHIFT, CONFIRM, pickTerm, termSelect, tabs, readinessTable } from "./timetable-prep.js";

const POLL_MS = 5000;
const ROOT = "/admin/timetable/build";
const STATUS = () => ({ draft: [t("Layihə"), "b-blue"], review: [t("Rəydə"), "b-violet"], published: [t("Dərc olunub"), "b-green"],
  superseded: [t("Köhnəlib"), "b-gray"], discarded: [t("Atılıb"), "b-gray"] });
const RUN_STATUS = () => ({ queued: t("Növbədədir"), running: t("Hesablanır"), done: t("Bitdi"), failed: t("Alınmadı"), cancelled: t("Dayandırıldı") });
const RUN_KIND = () => ({ precheck: t("İlkin yoxlama"), solve: t("Cədvəlin qurulması"), check: t("Tam yoxlama"), publish: t("Dərc") });
const PHASE = () => ({ snapshot: t("məlumat oxunur"), construct: t("ilk yerləşdirmə"), improve: t("yaxşılaşdırma"), done: t("bitdi"),
  check: t("yoxlama"), rows: t("cədvəl sətirləri"), drop: t("köhnə dərslərin silinməsi"), lessons: t("dərslərin yaradılması"), notify: t("bildirişlər"), failed: t("alınmadı") });
const COMP = () => ({ group_window: t("Qrupların boş cütləri"), teacher_window: t("Müəllimlərin boş cütləri"), same_day_course: t("Bir gündə eyni fənn"),
  undesired: t("Arzuolunmaz vaxtlar"), saturday: t("Şənbə cütləri"), late_pair: t("Gec cütlər"), room_waste_10: t("Boş qalan yerlər (hər 10 yer)"),
  foreign_building: t("Qrupun binasından kənar otaqlar"), hours_miss: t("Saatların Forma №3-dən fərqi"), stability_time: t("Vaxtı dəyişən dərslər"),
  stability_weeks: t("Həftələri dəyişən dərslər"), stability_room: t("Otağı dəyişən dərslər"), move_repair: t("Bərpada köçürülən dərslər") });
const badgeOf = (map, k) => { const [l, c] = map()[k] || [k, "b-gray"]; return html`<span class="badge ${c}">${l}</span>`; };
const weeksLabel = (w) => (w === "all" ? "" : w === "odd" ? t("tək həftələr") : w === "even" ? t("cüt həftələr") : t("həftələr {w}", { w }));
const listOf = (items) => html`<ul class="tt-reasons">${items.map((x) => html`<li>${ic("alert", 13)} ${x.title || x.code}${x.slots ? html` <span class="muted">· ${t("{n} vaxtda", { n: x.slots })}</span>` : ""}</li>`)}</ul>`;
const refusal = (err, title) => {
  const d = err.data || {};
  const items = d.lines || d.gate || d.reasons;
  if (!items || !items.length) { toast(err.message, "err"); return; }
  modal({ title, body: html`<p class="small">${err.message}</p>${listOf(items)}` });
};

/** The earliest date a publication may take effect: today + notice days, moved to the next Monday, inside the term. */
const firstDay = (term, notice) => {
  const d = new Date(); d.setDate(d.getDate() + notice);
  while (d.getDay() !== 1) d.setDate(d.getDate() + 1);
  const s = isoDay(d);
  return s < term.teaching_start ? term.teaching_start : s;
};

/** A run's card, polled every 5 s while it is queued or running; onEnd(run) once it ends. */
function watchRun(host, id, onEnd) {
  let stopped = false;
  const draw = (r) => {
    const pr = r.progress || {};
    const pct = r.kind === "publish" ? ["check", "rows", "drop", "lessons", "notify", "done"].indexOf(pr.step || "check") * 20
      : r.iter_budget ? Math.min(100, Math.round(100 * (r.iterations || pr.iterations || 0) / r.iter_budget)) : 0;
    mount(host, html`<div class="card tt-run" data-run="${r.id}" data-status="${r.status}"><div class="card-h wrap"><h3>${ic("activity", 17)} ${RUN_KIND()[r.kind] || r.kind} #${r.id}</h3>
      <span class="badge ${r.status === "done" ? "b-green" : r.status === "failed" ? "b-red" : r.status === "cancelled" ? "b-gray" : "b-blue"}">${RUN_STATUS()[r.status] || r.status}</span>
      ${["queued", "running"].includes(r.status) && r.kind !== "publish" ? html`<button class="btn btn-ghost btn-sm" data-cancel-run="${r.id}">${t("Dayandır")}</button>` : ""}</div>
      <div class="card-b stack">${progress(r.status === "done" ? 100 : pct, "", t("Gedişat"))}
        <p class="small" style="margin:0" aria-live="polite">${t("Mərhələ: {p}", { p: PHASE()[pr.step || pr.phase] || pr.step || pr.phase || "—" })}
          ${pr.iterations || r.iterations ? " · " + t("{n} addım", { n: pr.iterations || r.iterations }) : ""}
          ${pr.meetings ? " · " + t("{n} dərs", { n: pr.meetings }) : ""}${pr.unplaced != null ? " · " + t("yerləşdirilməyən: {n}", { n: pr.unplaced }) : ""}
          ${pr.counts && pr.counts.notified != null ? " · " + t("bildiriş: {n}", { n: pr.counts.notified }) : ""}</p>
        ${r.status === "queued" ? html`<p class="small muted" style="margin:0">${t("Hesablama fon işində gedir: səhifəni bağlaya bilərsiniz, hazır olanda bildiriş gələcək.")}</p>` : ""}
        ${r.error && r.status === "failed" ? html`<p class="small" style="margin:0">${t("Səbəb")}: ${r.error}</p>` : ""}
        ${r.report && r.report.excluded && r.report.excluded.length ? html`<p class="small" style="margin:0">${t("Hesablamaya daxil edilməyən vahidlər: {n}", { n: r.report.excluded.length })}</p>` : ""}</div></div>`);
  };
  const poll = async () => {
    if (stopped || !document.body.contains(host)) return;
    let r;
    try { r = await api.get(`/api/timetable/runs/${id}`); } catch (err) { if ([401, 403, 404].includes(err.status)) return; setTimeout(poll, POLL_MS); return; }
    if (!document.body.contains(host)) return;
    draw(r);
    if (["queued", "running"].includes(r.status)) setTimeout(poll, POLL_MS); else { stopped = true; onEnd && onEnd(r); }
  };
  on(host, "click", "[data-cancel-run]", async (e, b) => {
    b.disabled = true;
    try { await api.post(`/api/timetable/runs/${b.dataset.cancelRun}/cancel`); toast(t("Dayandırılır"), "ok"); } catch (err) { toast(err.message, "err"); }
  });
  poll();
}

const scoreTable = (cards) => html`<div class="table-wrap"><table class="table tt-score"><thead><tr><th>${t("Göstərici")}</th>${cards.map((c) => html`<th>${c.label}</th>`)}</tr></thead><tbody>
  <tr><th scope="row">${t("Qaydaların pozuntusu")}</th>${cards.map((c) => html`<td>${c.score.hard ?? "—"}</td>`)}</tr>
  <tr><th scope="row">${t("Yerləşdirilən / yerləşdirilməyən")}</th>${cards.map((c) => html`<td>${c.score.placed ?? "—"} / ${c.score.unplaced ?? "—"}</td>`)}</tr>
  <tr><th scope="row">${t("Əhatə (‰)")}</th>${cards.map((c) => html`<td>${c.score.coverage ?? "—"}</td>`)}</tr>
  <tr><th scope="row">${t("Yumşaq qaydaların cəmi (az olsa yaxşıdır)")}</th>${cards.map((c) => html`<td><b>${c.score.soft ?? "—"}</b></td>`)}</tr>
  ${Object.keys(COMP()).filter((k) => cards.some((c) => c.score.components && c.score.components[k] && c.score.components[k].value)).map((k) => html`<tr><th scope="row">${COMP()[k]}</th>
    ${cards.map((c) => { const x = (c.score.components || {})[k] || { value: 0, cost: 0 }; return html`<td>${x.value} <span class="tiny muted">(${t("çəki ilə")} ${x.cost})</span></td>`; })}</tr>`)}
</tbody></table></div>`;

// ---------------------------------------------------------------- the start page: readiness, settings and plan, versions
route(ROOT, async (el, p, q) => {
  mount(el, loading());
  let terms, term, tab = q.tab || "ready", start;
  try { ({ terms, term } = await pickTerm(q)); if (term) start = await api.get(`/api/timetable/build/${term.id}`); }
  catch (err) { return mount(el, failed(err.message)); }
  const crumbs = [[t("Əsas"), HOME[S.user.role]], [t("Cədvəl qurucusu")]];
  const head = () => html`${pageHead(t("Cədvəl qurucusu"), t("Semestrin dərs cədvəli: hazırlıq, hesablama, layihələrin redaktəsi və dərc."),
    terms.length > 1 ? termSelect(terms, term) : "", crumbs)}`;
  if (!term) return mount(el, html`${head()}${empty("calendar", t("Semestr yoxdur"), t("Əvvəlcə «Struktur və reyestr» bölməsində semestr yaradın."))}`);
  const B = `/api/timetable/build/${term.id}`;
  let checked = new Set();

  const summary = () => html`<div class="grid tt-summary">
    <div class="card card-b"><div class="tiny muted">${t("Semestr")}</div><b>${start.term.name}</b><div class="small muted">${fmtDate(start.term.teaching_start)} – ${fmtDate(start.term.teaching_end)} · ${t("{n} həftə", { n: start.weeks })}</div></div>
    <div class="card card-b"><div class="tiny muted">${t("Hesablama")}</div><b>${start.run_blocked ? t("Dayandırılıb: hazırlıq siyahısına baxın") : t("Başlamaq olar")}</b>
      <div class="small muted">${t("Xəbərdarlıq: {n}", { n: start.warnings })}</div></div>
    <div class="card card-b"><div class="tiny muted">${t("Dərc")}</div><b>${start.published_id ? t("Dərc olunmuş versiya: #{id}", { id: start.published_id }) : t("Hələ dərc olunmayıb")}</b>
      <div class="small muted">${start.publish_blocked ? t("Dərc üçün təsdiq gözləyən bəndlər var") : t("Dərc qapısı açıqdır")}</div></div>
    <div class="card card-b"><div class="tiny muted">${t("Son tarixlər")}</div><div class="small">${t("Tələblər")}: ${fmtDate(start.dues.needs)} · ${t("Məşğulluq")}: ${fmtDate(start.dues.availability)}</div>
      <div class="small">${t("Dərc")}: ${fmtDate(start.dues.publish)}</div></div></div>`;

  const draw = async () => {
    mount(el, html`${head()}${summary()}${tabs([["ready", t("Hazırlıq")], ["settings", t("Ayarlar və plan")], ["versions", t("Hesablama və layihələr")]], tab)}<div id="tb-body">${loading()}</div>`);
    const body = $("#tb-body", el);
    try {
      if (tab === "ready") {
        const r = await api.get(`${B}/readiness`);
        mount(body, html`<div class="card"><div class="card-h"><h3>${ic("check", 17)} ${t("Hazırlıq siyahısı")}</h3></div>${readinessTable(r)}</div>`);
      } else if (tab === "settings") {
        const s = await api.get("/api/timetable/settings");
        settingsForm(body, s);
      } else {
        const vs = await api.get(`${B}/versions`);
        mount(body, html`${start.manages ? html`<div class="card"><div class="card-h"><h3>${ic("wand", 17)} ${t("Yeni hesablama")}</h3></div><div class="card-b row wrap tt-runform">
            <div class="field"><label class="label" for="rn-kind">${t("Növ")}</label><select class="input" id="rn-kind"><option value="solve">${RUN_KIND().solve}</option><option value="precheck">${RUN_KIND().precheck}</option></select></div>
            <div class="field grow"><label class="label" for="rn-name">${t("Layihənin adı")}</label><input class="input" id="rn-name" maxlength="100" placeholder="${t("məs.: ilk variant")}"></div>
            <div class="field"><label class="label" for="rn-budget">${t("Addım sayı")}</label><input class="input" id="rn-budget" type="number" min="1" value="20000"></div>
            <div class="field"><label class="label" for="rn-base">${t("Kilidlər bu layihədən")}</label><select class="input" id="rn-base"><option value="">—</option>${vs.map((v) => html`<option value="${v.id}">#${v.id} ${v.name || ""}</option>`)}</select></div>
            <button class="btn btn-primary" id="rn-start" ${start.run_blocked ? "disabled" : ""}>${ic("play", 15)} ${t("Başlat")}</button></div></div>` : ""}
          <div id="tb-run" class="mt"></div>
          <div id="tb-versions">${versionsCard(vs)}</div>`);
        if (start.run) watchRun($("#tb-run", el), start.run.id, ended);
      }
    } catch (err) { mount(body, failed(err.message)); }
  };
  const versionsCard = (vs) => html`<div class="card mt"><div class="card-h wrap"><h3>${ic("layers", 17)} ${t("Layihələr")}</h3><button class="btn btn-sm" id="tb-compare" disabled>${t("Seçilən ikisini müqayisə et")}</button></div>
          ${vs.length ? html`<div class="table-wrap"><table class="table"><thead><tr><th><span class="sr-only">${t("Seç")}</span></th><th>#</th><th>${t("Ad")}</th><th>${t("Vəziyyət")}</th><th>${t("Yaradılıb")}</th>
            <th>${t("Yerləşdirilməyən")}</th><th>${t("Pozuntu")}</th><th>${t("Yoxlama")}</th><th></th></tr></thead><tbody>${vs.map((v) => html`<tr>
              <td><input type="checkbox" data-pick="${v.id}" aria-label="${t("Müqayisə üçün seç")}: #${v.id}" ${checked.has(v.id) ? "checked" : ""}></td><td>${v.id}</td><td>${v.name || "—"}</td><td>${badgeOf(STATUS, v.status)}</td>
              <td class="nowrap">${fmtDateTime(v.created_at)}</td><td>${v.unplaced}</td><td>${v.violations ?? "—"}</td>
              <td>${v.checked_rev === v.rev ? html`<span class="badge b-green">${t("Yoxlanılıb")}</span>` : html`<span class="badge b-amber">${t("Yoxlanılmayıb")}</span>`}</td>
              <td><a class="btn btn-ghost btn-sm" href="#${ROOT}/version/${v.id}">${t("Aç")}</a></td></tr>`)}</tbody></table></div>`
            : html`<div class="card-b">${empty("layers", t("Hələ layihə yoxdur"), t("Hazırlıq tamam olanda hesablamanı başladın."))}</div>`}</div>`;
  // a run's end refreshes the list of drafts only: its card stays, with its final state
  const ended = async () => {
    try { start = await api.get(B); const box = $("#tb-versions", el); if (box) mount(box, versionsCard(await api.get(`${B}/versions`))); }
    catch { /* the page keeps its last state */ }
  };

  const settingsForm = (body, s) => {
    const v = s.timetable, conf = new Set(v.confirmed), tconf = new Set(start.term_confirmed);
    const times = s.lesson_times.length ? s.lesson_times : s.defaults;
    const num = (k, l, min, max) => html`<div class="field"><label class="label" for="st-${k}">${l}</label><input class="input" id="st-${k}" type="number" min="${min}" max="${max}" value="${v[k] ?? ""}"></div>`;
    mount(body, html`<div class="card"><div class="card-h"><h3>${ic("check", 17)} ${t("Təsdiqlənən ayarlar")}</h3><button class="btn btn-sm btn-primary" id="st-save">${t("Saxla")}</button></div>
      <div class="card-b stack"><p class="small muted" style="margin:0">${t("Hər ayar təsdiqlənənədək standart sayılır. Dərs tarixləri, zəng cədvəli və saatların bölgü qaydası təsdiqlənmədən cədvəl dərc olunmur.")}</p>
        <p class="small" style="margin:0">${t("Zəng cədvəli")}: ${times.map((x, i) => `${i + 1}) ${x.join("–")}`).join(" · ")}${s.lesson_times.length ? "" : html` <span class="badge b-amber">${t("standart")}</span>`}</p>
        <div class="row wrap tt-confirm">${Object.keys(CONFIRM()).filter((k) => !["practice", "reserved_weeks", "online"].includes(k)).map((k) =>
          html`<label class="row small"><input type="checkbox" name="conf" value="${k}" ${conf.has(k) ? "checked" : ""}> ${CONFIRM()[k]}${v.publish_requires.includes(k) ? html` <span class="badge b-red">${t("dərc üçün vacib")}</span>` : ""}</label>`)}</div>
        <h4 style="margin:0">${t("Növbələr (cütlərin nömrələri vergüllə)")}</h4>
        <div class="row wrap">${["morning", "afternoon", "evening"].map((k) => html`<div class="field"><label class="label" for="sh-${k}">${SHIFT()[k]}</label>
          <input class="input" id="sh-${k}" value="${(v.shifts[k] || []).join(", ")}" placeholder="${t("boş: növbə yoxdur")}"></div>`)}</div>
        <h4 style="margin:0">${t("Hədlər")}</h4>
        <div class="row wrap">${num("max_pairs_day_group", t("Qrupun gündə ən çox cütü"), 1, 8)}${num("max_pairs_day_teacher", t("Müəllimin gündə ən çox cütü"), 1, 8)}
          ${num("max_week_hours_group", t("Qrupun həftəlik auditoriya saatı"), 1, 30)}${num("availability_cap_pct", t("Məşğul xanaların həddi (%)"), 0, 100)}
          ${num("notice_days", t("Dəyişiklikdən əvvəl bildiriş (gün)"), 0, 60)}${num("hours_tolerance", t("Saat fərqinin yol verilən həddi"), 0, 20)}</div>
        <label class="row small"><input type="checkbox" id="st-review" ${v.review_required ? "checked" : ""}> ${t("Dərcdən əvvəl rəy tələb olunur")}</label></div></div>
      <div class="card mt"><div class="card-h"><h3>${ic("calendar", 17)} ${t("Semestrin planı")}</h3><button class="btn btn-sm btn-primary" id="pl-save">${t("Saxla")}</button></div>
        <div class="card-b stack"><div class="row wrap">${[["needs_due", t("Tələblərin son tarixi"), start.dues.needs], ["groups_due", t("Qrup növbələrinin son tarixi"), start.dues.groups],
          ["availability_due", t("Məşğulluq vaxtlarının son tarixi"), start.dues.availability], ["review_due", t("Rəyin son tarixi"), start.dues.review], ["publish_target", t("Dərcin hədəf tarixi"), start.dues.publish]].map(([k, l, d]) =>
          html`<div class="field"><label class="label" for="pl-${k}">${l}</label><input class="input" id="pl-${k}" type="date" value="${d || ""}"></div>`)}</div>
          <div class="row wrap">${["practice", "reserved_weeks", "fixed_slots", "online"].map((k) => html`<label class="row small"><input type="checkbox" name="tconf" value="${k}" ${tconf.has(k) ? "checked" : ""}> ${CONFIRM()[k]}</label>`)}</div></div></div>`);
    on(body, "click", "#st-save", async (e, b) => {
      const shifts = {};
      for (const k of ["morning", "afternoon", "evening"]) {
        const ps = $(`#sh-${k}`, body).value.split(/[\s,;]+/).filter(Boolean).map(Number);
        if (ps.length) shifts[k] = ps;
      }
      const nums = Object.fromEntries(["max_pairs_day_group", "max_pairs_day_teacher", "max_week_hours_group", "availability_cap_pct", "notice_days", "hours_tolerance"]
        .map((k) => [k, Number($(`#st-${k}`, body).value)]));
      b.disabled = true;
      try {
        await api.put("/api/timetable/settings", { value: { ...v, ...nums, shifts, review_required: $("#st-review", body).checked,
          confirmed: $$("[name=conf]:checked", body).map((x) => x.value) } });
        toast(t("Saxlanıldı"), "ok"); start = await api.get(B); draw();
      } catch (err) { toast(err.message, "err"); b.disabled = false; }
    });
    on(body, "click", "#pl-save", async (e, b) => {
      b.disabled = true;
      try {
        await api.put(`${B}/plan`, { ...Object.fromEntries(["needs_due", "groups_due", "availability_due", "review_due", "publish_target"].map((k) => [k, $(`#pl-${k}`, body).value || null])),
          confirmed: $$("[name=tconf]:checked", body).map((x) => x.value) });
        toast(t("Saxlanıldı"), "ok"); start = await api.get(B); draw();
      } catch (err) { toast(err.message, "err"); b.disabled = false; }
    });
  };

  on(el, "click", "[data-tab]", (e, b) => { tab = b.dataset.tab; draw(); });
  on(el, "change", ".tt-term", (e, s) => { location.hash = `#${ROOT}?term=${s.value}`; });
  on(el, "change", "[data-pick]", (e, c) => {
    const id = Number(c.dataset.pick);
    if (c.checked) checked.add(id); else checked.delete(id);
    $("#tb-compare", el).disabled = checked.size !== 2;
  });
  on(el, "click", "#tb-compare", async () => {
    const ids = [...checked].sort((a, b) => a - b);
    try {
      const cards = await Promise.all(ids.map((id) => api.get(`/api/timetable/versions/${id}/scorecard`)));
      modal({ title: t("Layihələrin müqayisəsi"), size: "lg", body: html`${cards.some((c) => c.stale) ? html`<p class="small"><span class="badge b-amber">${t("Yoxlanılmayıb")}</span>
        ${t("Əl ilə dəyişiklikdən sonra göstəricilər «Yoxla» ilə yenilənir.")}</p>` : ""}${scoreTable(cards.map((c) => ({ label: `#${c.version.id} ${c.version.name || ""}`, score: c.score || {} })))}` });
    } catch (err) { toast(err.message, "err"); }
  });
  on(el, "click", "#rn-start", async (e, b) => {
    b.disabled = true;
    const base = $("#rn-base", el).value;
    try {
      const r = await api.post(`${B}/runs`, { kind: $("#rn-kind", el).value, name: $("#rn-name", el).value || null, budget: Number($("#rn-budget", el).value) || undefined,
        ...(base ? { base_version_id: Number(base) } : {}) });
      toast(t("Hesablama növbəyə qoyuldu"), "ok");
      watchRun($("#tb-run", el), r.id, ended);
    } catch (err) { if (err.status === 409) refusal(err, t("Hesablama başlamadı")); else toast(err.message, "err"); }
    finally { b.disabled = false; }
  });
  draw();
});

// ---------------------------------------------------------------- a version: scorecard, unplaced, grids and the editor
route(`${ROOT}/version/:id`, async (el, p, q) => {
  const vid = Number(p.id);
  mount(el, loading());
  let card, unplaced, start, groups, board, rooms;
  try {
    card = await api.get(`/api/timetable/versions/${vid}/scorecard`);
    const tid = card.version.term_id;
    [unplaced, start, groups, board, rooms] = await Promise.all([api.get(`/api/timetable/versions/${vid}/unplaced`), api.get(`/api/timetable/build/${tid}`),
      api.get(`/api/timetable/build/${tid}/groups`), api.get(`/api/timetable/build/${tid}/teachers`), api.all("/api/directory/rooms?active=1")]);
  } catch (err) { return mount(el, failed(err.message)); }
  const v = () => card.version;
  const editable = () => start.manages && ["draft", "review"].includes(v().status);
  const lists = { group: groups.map((g) => [g.id, g.name]), teacher: board.items.map((x) => [x.id, x.full_name]), room: rooms.map((r) => [r.id, r.code]) };
  let by = ["group", "teacher", "room"].includes(q.by) ? q.by : "group", pick = Number(q.id) || (lists[by][0] || [])[0] || null;
  let items = [], rev = v().rev, sel = null, opts = null, cursor = null, times = [], days = [1, 2, 3, 4, 5, 6];
  const roomCode = Object.fromEntries(rooms.map((r) => [r.id, r.code]));

  const head = () => html`${pageHead(t("Layihə #{id}", { id: vid }) + (v().name ? ` · ${v().name}` : ""), t("Dərsi sürüşdürün və ya seçib Enter, oxlar, Enter ilə köçürün: hər vaxtın mümkün olub-olmadığı dərhal yoxlanır."),
    html`${badgeOf(STATUS, v().status)}${editable() ? html`<button class="btn btn-sm" id="vr-check">${ic("check", 15)} ${t("Yoxla")}</button>` : ""}
      <button class="btn btn-sm" id="vr-print">${ic("printer", 15)} ${t("Çap et")}</button>
      ${start.can_publish && editable() ? html`<button class="btn btn-sm btn-primary" id="vr-publish">${ic("upload", 15)} ${t("Dərc et")}</button>` : ""}`,
    [[t("Əsas"), HOME[S.user.role]], [t("Cədvəl qurucusu"), `${ROOT}?tab=versions&term=${v().term_id}`], [t("Layihə #{id}", { id: vid })]])}`;

  const scoreCard = () => html`<div class="card"><div class="card-h wrap"><h3>${ic("chart", 17)} ${t("Göstəricilər")}</h3>
    ${card.stale ? html`<span class="badge b-amber">${t("Yoxlanılmayıb")}</span><span class="small muted">${t("Əl ilə dəyişiklikdən sonra göstəricilər «Yoxla» ilə yenilənir.")}</span>`
      : html`<span class="badge b-green">${t("Yoxlanılıb")}</span>`}</div>${scoreTable([{ label: t("Bu layihə"), score: card.score || {} }])}</div>`;
  const unplacedCard = () => html`<div class="card"><div class="card-h"><h3>${ic("alert", 17)} ${t("Yerləşdirilməyən dərslər")}</h3><span class="badge ${unplaced.length ? "b-amber" : "b-green"}">${unplaced.length}</span></div>
    ${unplaced.length ? html`<div class="list card-b">${unplaced.map((x) => html`<div class="list-item tt-unplaced"><div class="grow"><b class="small">${x.course} · ${KIND()[x.kind] || x.kind}${x.subgroup ? " · " + x.subgroup : ""}</b>
      ${listOf(x.reasons.slice(0, 4))}</div></div>`)}</div>` : html`<div class="card-b"><p class="muted small" style="margin:0">${t("Bütün dərslər yerləşdirilib.")}</p></div>`}</div>`;

  const option = (wd, pr) => (opts ? opts.find((o) => o.weekday === wd && o.period === pr) : null);
  const cellText = (o) => (!o ? "" : o.current ? t("indiki vaxt") : o.reasons.length ? o.reasons.map((r) => r.title).join("; ") : t("mümkündür") + (o.room_id ? ` · ${roomCode[o.room_id] || "#" + o.room_id}` : ""));
  const itemLine = (x) => (by === "group" ? [x.teacher, x.room] : by === "teacher" ? [x.groups.join(", "), x.room] : [x.groups.join(", "), x.teacher]).filter(Boolean).join(" · ");
  const gridHtml = () => {
    const periods = Math.max(times.length, ...items.map((x) => x.period + x.duration - 1));
    return html`<div class="table-wrap tt-gridwrap ${opts ? "moving" : ""}" tabindex="0" role="region" aria-label="${t("Həftəlik cədvəl")}"><table class="table tt-grid"><thead><tr><th>${t("Cüt")}</th>${days.map((d) => html`<th>${DAYS()[d]}</th>`)}</tr></thead><tbody>
      ${Array.from({ length: periods }, (_, i) => i + 1).map((pr) => html`<tr><th scope="row" class="nowrap">${PAIR(pr)}<div class="tiny muted">${(times[pr - 1] || []).join("–")}</div></th>
        ${days.map((d) => { const o = option(d, pr), here = items.filter((x) => x.weekday === d && x.period <= pr && pr < x.period + x.duration);
          const cls = o ? (o.current ? "cur" : o.reasons.length ? "no" : "ok") : "";
          return html`<td class="tt-slot ${cls} ${cursor && cursor[0] === d && cursor[1] === pr ? "cursor" : ""}" data-slot="${d}:${pr}" ${opts ? html`tabindex="-1" aria-label="${DAYS()[d]}, ${PAIR(pr)}: ${cellText(o)}"` : ""}>
            ${here.map((x) => html`<div class="tt-item ${x.locked ? "locked" : ""} ${sel && sel.id === x.id ? "sel" : ""}" ${editable() && !x.locked ? html`draggable="true"` : ""} data-item="${x.id}">
              <button class="tt-item-b" data-pickitem="${x.id}" aria-label="${x.course}, ${KIND()[x.kind] || x.kind}, ${DAYS()[d]} ${PAIR(x.period)}${x.locked ? ", " + t("kilidli") : ""}">
                <b>${x.course}</b><span class="tiny">${KIND()[x.kind] || x.kind}${x.subgroup ? " · " + x.subgroup : ""}${weeksLabel(x.weeks) ? " · " + weeksLabel(x.weeks) : ""}</span>
                <span class="tiny muted">${itemLine(x)}</span>${x.origin === "manual" ? html`<span class="tiny muted">${ic("edit", 11)} ${t("əl ilə")}</span>` : ""}</button>
              ${editable() ? html`<button class="btn-icon tt-lock" data-lock="${x.id}" aria-pressed="${!!x.locked}" aria-label="${x.locked ? t("Kilidi aç") : t("Kilidlə")}" title="${x.locked ? t("Kilidi aç") : t("Kilidlə")}">${ic("lock", 13)}</button>`
                : x.locked ? html`<span class="tt-lock">${ic("lock", 13)}</span>` : ""}</div>`)}
            ${o && !o.current ? html`<span class="tt-why">${o.reasons.length ? html`${ic("x", 11)} ${o.reasons.map((r) => r.title).join("; ")}` : html`${ic("check", 11)} ${t("mümkündür")}`}</span>` : ""}</td>`; })}</tr>`)}
    </tbody></table></div>`;
  };

  const drawGrid = () => {
    const host = $("#vr-grid", el);
    if (!host) return;
    mount(host, html`<div class="card-h wrap"><div class="seg" role="tablist">${[["group", t("Qrup")], ["teacher", t("Müəllim")], ["room", t("Otaq")]].map(([k, l]) =>
        html`<button role="tab" aria-selected="${by === k}" class="${by === k ? "active" : ""}" data-by="${k}">${l}</button>`)}</div>
      <select class="input input-sm" id="vr-pick" aria-label="${t("Seçim")}">${lists[by].map(([id, n]) => html`<option value="${id}" ${id === pick ? "selected" : ""}>${n}</option>`)}</select>
      ${editable() && items.length ? html`<button class="btn btn-ghost btn-sm" id="vr-lockall">${ic("lock", 14)} ${t("Hamısını kilidlə")}</button>` : ""}
</div><p class="small muted tt-status" id="vr-status" role="status" aria-live="polite">${sel ? (opts ? t("«{c}» seçilib: yeni vaxtı seçin (Esc: ləğv)", { c: sel.course }) : t("Mümkün vaxtlar yoxlanılır…")) : ""}
        ${cursor && opts ? " " + DAYS()[cursor[0]] + ", " + PAIR(cursor[1]) + ": " + cellText(option(...cursor)) : ""}</p>
      ${pick ? (items.length ? gridHtml() : html`<div class="card-b">${gridHtml()}<p class="muted small">${t("Bu seçimdə dərs yoxdur")}</p></div>`) : html`<div class="card-b">${empty("calendar", t("Seçim yoxdur"))}</div>`}`);
    if (cursor && opts) host.querySelector(`[data-slot="${cursor[0]}:${cursor[1]}"]`)?.focus();
  };
  const loadGrid = async () => {
    if (!pick) { items = []; return drawGrid(); }
    const r = await api.get(`/api/timetable/versions/${vid}/grid?${by}_id=${pick}`);
    items = r.items; rev = r.version.rev; card.version = { ...card.version, ...r.version }; times = r.times; days = r.days;
    drawGrid();
  };
  const draw = () => {
    mount(el, html`<div id="vr-head">${head()}${v().status === "published" ? "" : html`<div class="tt-draftmark" aria-hidden="true">${t("LAYİHƏ")}</div>`}</div>
      <div class="grid tt-vgrid"><div class="card tt-gridcard" id="vr-grid"></div><div class="stack">${scoreCard()}${unplacedCard()}</div></div>
      <div id="vr-run" class="mt"></div>`);
    loadGrid().catch((err) => mount($("#vr-grid", el), failed(err.message)));
  };

  const cancelMove = () => { sel = null; opts = null; cursor = null; drawGrid(); };
  const choose = async (id, keyboard) => {
    const x = items.find((i) => i.id === id);
    if (!x || !editable()) return;
    if (x.locked) { toast(t("Yerləşdirmə kilidlidir"), "err"); return; }
    sel = x; opts = null; cursor = keyboard ? [x.weekday, x.period] : null; drawGrid();
    try {
      const r = await api.get(`/api/timetable/versions/${vid}/placements/${id}/options`);
      if (!sel || sel.id !== id) return;
      opts = r.options; rev = r.rev; drawGrid();
    } catch (err) { toast(err.message, "err"); cancelMove(); }
  };
  const moveTo = async (wd, pr) => {
    if (!sel || !opts) return;
    const o = option(wd, pr);
    if (!o || o.current) return cancelMove();
    if (o.reasons.length) { toast(o.reasons.map((r) => r.title).join("; "), "err"); return; }
    try {
      const r = await api.post(`/api/timetable/versions/${vid}/placements/${sel.id}/move`, { weekday: wd, period: pr, room_id: o.room_id, rev });
      rev = r.rev; card.stale = true; toast(t("Dərs köçürüldü"), "ok");
      sel = null; opts = null; cursor = null; await loadGrid();
      $(`[data-pickitem="${r.placement.id}"]`, el)?.focus();
      refreshScore();
    } catch (err) { if (err.status === 409) refusal(err, t("Dərs köçürülmədi")); else toast(err.message, "err"); cancelMove(); }
  };
  const refreshScore = async () => {
    try {
      [card, unplaced] = await Promise.all([api.get(`/api/timetable/versions/${vid}/scorecard`), api.get(`/api/timetable/versions/${vid}/unplaced`)]);
      const side = $(".tt-vgrid > .stack", el); if (side) mount(side, html`${scoreCard()}${unplacedCard()}`);
    } catch { /* the grid stays usable */ }
  };
  const setLock = async (ids, locked) => {
    try { const r = await api.post(`/api/timetable/versions/${vid}/lock`, { ids, locked, rev }); rev = r.rev; await loadGrid(); }
    catch (err) { toast(err.message, "err"); }
  };

  on(el, "click", "[data-by]", (e, b) => { by = b.dataset.by; pick = (lists[by][0] || [])[0] || null; sel = opts = cursor = null; loadGrid(); });
  on(el, "change", "#vr-pick", (e, s) => { pick = Number(s.value); sel = opts = cursor = null; loadGrid(); });
  on(el, "click", "[data-pickitem]", (e, b) => {
    const id = Number(b.dataset.pickitem);
    if (sel && opts) { const td = b.closest("[data-slot]"); const [d, pr] = td.dataset.slot.split(":").map(Number); if (sel.id === id) return cancelMove(); return moveTo(d, pr); }
    choose(id, e.detail === 0);                        // detail 0: Enter or Space on the button, not a pointer click
  });
  on(el, "click", "[data-slot]", (e, td) => { if (e.target.closest("[data-pickitem], [data-lock]")) return; if (sel && opts) { const [d, pr] = td.dataset.slot.split(":").map(Number); moveTo(d, pr); } });
  on(el, "click", "[data-lock]", (e, b) => { const x = items.find((i) => i.id === Number(b.dataset.lock)); if (x) setLock([x.id], !x.locked); });
  on(el, "click", "#vr-lockall", () => setLock(items.map((x) => x.id), true));
  on(el, "dragstart", "[data-item]", (e, d) => { e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", d.dataset.item); choose(Number(d.dataset.item), false); });
  on(el, "dragover", "[data-slot]", (e, td) => { const [d, pr] = td.dataset.slot.split(":").map(Number); const o = option(d, pr); if (o && !o.reasons.length) e.preventDefault(); });
  on(el, "drop", "[data-slot]", (e, td) => { e.preventDefault(); const [d, pr] = td.dataset.slot.split(":").map(Number); moveTo(d, pr); });
  el.addEventListener("keydown", (e) => {
    if (!sel) return;
    if (e.key === "Escape") { e.preventDefault(); cancelMove(); $(`[data-pickitem="${sel ? sel.id : ""}"]`, el)?.focus(); return; }
    if (!opts || !cursor) return;
    const periods = Math.max(...opts.map((o) => o.period));
    const di = days.indexOf(cursor[0]);
    const step = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (step) {
      e.preventDefault();
      cursor = [days[Math.max(0, Math.min(days.length - 1, di + step[0]))], Math.max(1, Math.min(periods, cursor[1] + step[1]))];
      drawGrid();
    } else if (e.key === "Enter") { e.preventDefault(); moveTo(...cursor); }
  });
  on(el, "click", "#vr-print", () => window.print());
  on(el, "click", "#vr-check", async (e, b) => {
    b.disabled = true;
    try {
      const r = await api.post(`/api/timetable/build/${v().term_id}/runs`, { kind: "check", version_id: vid });
      toast(t("Yoxlama növbəyə qoyuldu"), "ok");
      watchRun($("#vr-run", el), r.id, () => { refreshScore(); b.disabled = false; });
    } catch (err) { toast(err.message, "err"); b.disabled = false; }
  });
  on(el, "click", "#vr-publish", () => {
    const first = firstDay(start.term, start.notice_days);
    modal({ title: t("Cədvəli dərc et"), size: "lg", body: html`<div class="stack">
        <p class="small" style="margin:0">${t("Dərc olunanda cədvəl sətirləri və qüvvəyə minmə tarixindən dərslər yaradılır, tələbə və müəllimlərə bildiriş gedir. Keçmiş və davamiyyəti yazılmış dərslər dəyişmir.")}</p>
        ${card.stale ? html`<p class="small" style="margin:0"><span class="badge b-amber">${t("Yoxlanılmayıb")}</span> ${t("Əvvəlcə «Yoxla» düyməsi ilə tam yoxlamanı keçirin.")}</p>` : ""}
        <div class="row wrap"><div class="field"><label class="label" for="pb-from">${t("Qüvvəyə minmə tarixi")}</label><input class="input" id="pb-from" type="date" value="${first}" min="${first}" max="${start.term.teaching_end}"></div>
          <div class="field"><label class="label" for="pb-count">${t("Yerləşdirilməyən dərslərin sayını yazın")}</label><input class="input" id="pb-count" type="number" min="0" inputmode="numeric"></div></div>
        <div class="field"><label class="label" for="pb-reason">${t("Rəy mərhələsi olmadan dərcin səbəbi (ən azı 10 simvol)")}</label><textarea class="input" id="pb-reason" rows="2" maxlength="500"></textarea></div>
        <div id="pb-gate" aria-live="polite"></div></div>`,
    actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Dərc et"), cls: "btn-primary", onClick: async (w) => {
      const count = w.querySelector("#pb-count").value;
      try {
        const r = await api.post(`/api/timetable/versions/${vid}/publish`, { effective_from: w.querySelector("#pb-from").value,
          accept_unplaced: count === "" ? null : Number(count), override_reason: w.querySelector("#pb-reason").value });
        toast(t("Dərc növbəyə qoyuldu"), "ok");
        watchRun($("#vr-run", el), r.id, async (run) => {           // the run's card stays; the head and the grid follow the new status
          if (run.status !== "done") return;
          card = await api.get(`/api/timetable/versions/${vid}/scorecard`);
          mount($("#vr-head", el), head()); loadGrid();
        });
      } catch (err) {
        const g = (err.data && err.data.gate) || [];
        mount(w.querySelector("#pb-gate"), g.length ? html`<p class="small" style="margin:0"><b>${err.message}</b></p>${listOf(g)}` : html`<p class="small">${err.message}</p>`);
        return false;
      }
    } }] });
  });
  draw();
});

