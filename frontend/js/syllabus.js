// The structured syllabus (Task 23): outcomes with a Bloom level, a weekly plan that names its outcomes, weighted
// assessment, rules, prerequisites, literature and the workload from Forma №3. Every save is a new version; the server
// checks the university's rules (weights, the exam's weight, the attendance limit) and says what is wrong.
import { api, html, mount, on, ic, toast, route, go, t, pageHead, fmtDate, loading, empty, failed, confirmBox, openSyllabus, registerTour, modal, S, LANG } from "./core.js";
import { HOME } from "./shell.js";

const BLOOM = () => [["remember", t("Xatırlama")], ["understand", t("Anlama")], ["apply", t("Tətbiq")], ["analyze", t("Təhlil")],
  ["evaluate", t("Qiymətləndirmə")], ["create", t("Yaratma")]];
const KIND = () => [["component", t("Cari qiymətləndirmə")], ["attendance", t("Davamiyyət")], ["exam", t("İmtahan")]];
const AI = () => [["allowed", t("İcazə verilir")], ["limited", t("Məhdud: izah və məşq üçün")], ["forbidden", t("Qadağandır")]];
const LIT = () => [["main", t("Əsas")], ["extra", t("Əlavə")]];
const WORK = () => [["lecture", t("Mühazirə")], ["seminar", t("Məşğələ")], ["lab", t("Laboratoriya")], ["independent", t("Sərbəst iş")]];
const STATUS = () => ({ draft: [t("Qaralama"), "b-gray"], submitted: [t("Təqdim olunub"), "b-blue"], approved: [t("Kafedra təsdiqləyib"), "b-amber"],
  published: [t("Dərc olunub"), "b-green"], returned: [t("Geri qaytarılıb"), "b-red"] });
const SECTION = () => ({ description: t("Fənnin təsviri"), outcomes: t("Təlim nəticələri"), plan: t("Həftəlik plan"), assessment: t("Qiymətləndirmə"),
  rules: t("Qaydalar"), prerequisites: t("Prerekvizitlər"), literature: t("Ədəbiyyat"), workload: t("İş yükü, saat") });
const CHANGE = () => ({ added: [t("əlavə olunub"), "b-green"], removed: [t("çıxarılıb"), "b-red"], changed: [t("dəyişib"), "b-amber"] });
const STEP = () => ({ submit: t("Təsdiqə göndər"), approve: t("Təsdiqlə"), publish: t("Dərc et"), return: t("Geri qaytar") });
const badge = (status) => { const [l, c] = STATUS()[status] || [status, "b-gray"]; return html`<span class="badge ${c}">${l}</span>`; };
const label = (list, k) => (list().find(([x]) => x === k) || [k, k])[1];

// What changed between two versions, section by section (Task 25).
function diffList(changes) {
  if (!changes.length) return html`<p class="small muted" style="margin:0">${t("Fərq yoxdur")}</p>`;
  return html`<div class="list">${changes.map((x) => html`<div class="list-item"><div class="grow"><b class="small">${SECTION()[x.section] || x.section}</b>
    ${x.key !== x.section ? html` <span class="tiny muted">${x.key}</span>` : ""}</div><span class="badge ${CHANGE()[x.change][1]}">${CHANGE()[x.change][0]}</span></div>`)}</div>`;
}

// Warnings for the author and the approver, never a refusal (as domain.checks on the server): the outcomes no week of the
// plan teaches, those no component assesses, and an outcome whose Bloom level differs from a Bloom tag on it.
function checksOf(d, tags) {
  const taught = new Set(d.plan.flatMap((p) => p.outcomes)), assessed = new Set(d.assessment.flatMap((a) => a.outcomes || []));
  return { untaught: d.outcomes.filter((o) => !taught.has(o.id)).map((o) => o.id), unassessed: d.outcomes.filter((o) => !assessed.has(o.id)).map((o) => o.id),
    bloom: d.outcomes.map((o) => ({ outcome: o.id, level: o.bloom, tags: (tags[o.id] || []).filter((x) => x.key === "bloom" && x.code !== o.bloom).map((x) => x.code) }))
      .filter((x) => x.tags.length) };
}
function checksNotice(c) {
  if (!c.untaught.length && !c.unassessed.length && !c.bloom.length) return "";
  return html`<div class="notice warn" data-checks>${ic("alert", 16)}<div class="stack sm">
    ${c.untaught.length ? html`<div>${t("Həftəlik planda tədris olunmayan nəticələr: {list}", { list: c.untaught.join(", ") })}</div>` : ""}
    ${c.unassessed.length ? html`<div>${t("Heç bir komponentdə qiymətləndirilməyən nəticələr: {list}", { list: c.unassessed.join(", ") })}</div>` : ""}
    ${c.bloom.map((b) => html`<div>${t("{id}: Bloom səviyyəsi «{level}», Bloom bəndi isə «{tag}»", { id: b.outcome, level: label(BLOOM, b.level), tag: b.tags.map((x) => label(BLOOM, x)).join(", ") })}</div>`)}
    <div class="tiny muted">${t("Bu, xəbərdarlıqdır: saxlamağa və təsdiqə mane olmur.")}</div></div></div>`;
}

// A version as the reviewers read it: everything the approver approves, with the outcomes' tags frozen at submission.
function readOnly(d, tags = {}) {
  const rules = d.rules || {};
  return html`<div class="stack">
    ${d.description ? html`<div><b class="small">${t("Fənnin təsviri")}</b><p class="small syl-pre" style="margin:4px 0 0">${d.description}</p></div>` : ""}
    <div><b class="small">${t("Təlim nəticələri")}</b><div class="table-wrap"><table class="table"><tbody>${d.outcomes.map((o) => html`<tr><td><b>${o.id}</b></td>
      <td>${o.text}${tagChips(tags[o.id] || [])}</td><td class="nowrap">${label(BLOOM, o.bloom)}</td></tr>`)}</tbody></table></div></div>
    <div><b class="small">${t("Həftəlik plan")}</b><div class="table-wrap"><table class="table"><thead><tr><th>${t("Həftə")}</th><th>${t("Mövzu")}</th><th>${t("Nəticələr")}</th><th>${t("Fəaliyyət")}</th></tr></thead>
      <tbody>${d.plan.map((p) => html`<tr><td>${p.week}</td><td>${p.topic}</td><td class="nowrap">${p.outcomes.join(", ")}</td><td>${p.activity}</td></tr>`)}</tbody></table></div></div>
    <div><b class="small">${t("Qiymətləndirmə")}</b><div class="table-wrap"><table class="table"><thead><tr><th>${t("Komponent")}</th><th>${t("Növ")}</th><th>${t("Çəki")}</th><th>${t("Nəticələr")}</th></tr></thead>
      <tbody>${d.assessment.map((a) => html`<tr><td>${a.name}</td><td>${label(KIND, a.kind)}</td><td>${a.weight}</td><td>${(a.outcomes || []).join(", ") || "—"}</td></tr>`)}</tbody></table></div></div>
    <div class="small">${t("Buraxılmış dərslərin həddi, %")}: <b>${rules.attendance_limit}</b> · ${t("Süni intellektdən istifadə")}: <b>${label(AI, rules.ai_policy)}</b></div>
    <div class="small"><b>${t("AI siyasətinin izahı")}</b>: <span class="syl-pre">${rules.ai_note || "—"}</span></div>
    <div class="small"><b>${t("Gecikmiş işlər")}</b>: <span class="syl-pre">${rules.late_policy || "—"}</span></div>
    <div class="small"><b>${t("Prerekvizitlər")}</b>: ${(d.prerequisites || []).join(", ") || "—"}</div>
    <div><b class="small">${t("Ədəbiyyat")}</b>${(d.literature || []).length ? html`<ul class="small" style="margin:4px 0 0">${d.literature.map((x) => html`<li>${x.title} <span class="badge b-gray">${label(LIT, x.kind)}</span></li>`)}</ul>` : html` <span class="small">—</span>`}</div>
    <div class="small">${t("İş yükü, saat")}: ${WORK().map(([k, l]) => html`${l} <b>${d.workload[k]}</b> `)}</div></div>`;
}

// Framework items of one outcome (Task 24): the server searches, a page at a time, within a framework, a kind and, for NICE,
// one work role's statements. One outcome may carry items of several frameworks; the key is the course and the outcome.
let FWS = null;
// A version imported from a file NIST did not publish under that version is marked as such (SEC-FW-3).
const fwName = (f) => `${f.title} · ${f.version}${f.verified ? "" : ` · ${t("yoxlanmamış nüsxə")}`}`;
const tagText = (x) => `${x.key ? `${x.key.toUpperCase()} ${x.version} · ` : ""}${x.code}`;
const tagChips = (list) => (list.length ? html`<div class="chips">${list.map((x) => html`<span class="badge b-navy" title="${x.title ? `${x.title}: ${x.text}` : x.text}">${tagText(x)}</span>`)}</div>` : "");

async function pickTags(cid, oid, current, done) {
  try { FWS = FWS || await api.get("/api/frameworks"); } catch (err) { toast(err.message, "err"); return; }
  const chosen = new Map(current.map((x) => [x.id, x]));
  let fw = FWS.find((f) => !f.builtin) || FWS[0], kind = "", role = "", q = "", page = 1, items = [], timer = null;
  modal({ title: t("{id} nəticəsinin çərçivə bəndləri", { id: oid }), size: "lg", body: html`<div class="stack sm">
      <div class="row wrap"><select class="select" id="fw-f" style="width:auto" aria-label="${t("Çərçivə")}">${FWS.map((f) => html`<option value="${f.id}" ${f.id === fw.id ? "selected" : ""}>${fwName(f)}</option>`)}</select>
        <select class="select" id="fw-k" style="width:auto" aria-label="${t("Növ")}"></select>
        <select class="select" id="fw-r" style="width:auto;max-width:260px" aria-label="${t("İş rolu")}"></select>
        <input class="input grow" id="fw-q" type="search" maxlength="100" placeholder="${t("Kod və ya mətn üzrə axtarış")}" aria-label="${t("Axtar")}"></div>
      <div class="tiny muted" id="fw-note"></div>
      <div class="list" id="fw-list" aria-live="polite"></div>
      <div class="row between"><button class="btn btn-sm" id="fw-prev">${t("Əvvəlki")}</button><span class="tiny muted" id="fw-page"></span><button class="btn btn-sm" id="fw-next">${t("Növbəti")}</button></div>
      <div><b class="small">${t("Seçilmiş bəndlər")}</b><div class="chips mt-sm" id="fw-chosen"></div></div></div>`,
    actions: [{ label: t("Bağla") }, { label: t("Yadda saxla"), cls: "btn-primary", onClick: async () => {
      done(await api.put(`/api/syllabi/${cid}/outcomes/${encodeURIComponent(oid)}/items`, { items: [...chosen.keys()] }));
      toast(t("Saxlanıldı"), "ok");
    } }],
    onMount: (w) => {
      const $ = (sel) => w.querySelector(sel);
      const drawChosen = () => mount($("#fw-chosen"), chosen.size ? html`${[...chosen.values()].map((x) => html`<button class="badge b-navy" data-unpick="${x.id}" aria-label="${t("Sil")}: ${tagText(x)}">${tagText(x)} ×</button>`)}`
        : html`<span class="tiny muted">${t("Hələ seçilməyib")}</span>`);
      const load = async () => {
        const p = new URLSearchParams({ page: String(page), size: "10" });
        if (q) p.set("q", q);
        if (kind) p.set("kind", kind);
        if (role) p.set("role", role);
        let r;
        try { r = await api.get(`/api/frameworks/${fw.id}/items?${p}`); } catch (err) { mount($("#fw-list"), html`<span class="small muted">${err.message}</span>`); return; }
        items = r.items;
        mount($("#fw-list"), items.length ? html`${items.map((x) => html`<label class="list-item"><input type="checkbox" data-pick="${x.id}" ${chosen.has(x.id) ? "checked" : ""}>
          <div class="grow"><b class="small">${x.code}</b> <span class="badge b-gray">${x.label}</span><div class="small">${x.title ? html`<b>${x.title}</b> ` : ""}${x.text}</div></div></label>`)}`
          : html`<span class="small muted">${t("Heç nə tapılmadı")}</span>`);
        $("#fw-prev").disabled = page <= 1;
        $("#fw-next").disabled = !r.more;
        $("#fw-page").textContent = t("Səhifə {n}", { n: page });
      };
      const setFw = async () => {
        kind = (fw.kinds.find((k) => k.mappable) || {}).kind || "";
        role = "";
        page = 1;
        q = "";                                           // a word searched in one framework finds nothing in another (D6)
        clearTimeout(timer);
        $("#fw-q").value = "";
        mount($("#fw-k"), html`${fw.kinds.filter((k) => k.mappable).map((k) => html`<option value="${k.kind}" ${k.kind === kind ? "selected" : ""}>${k.label}</option>`)}`);
        let roles = [];
        try { roles = fw.counts.work_role ? (await api.get(`/api/frameworks/${fw.id}/items?kind=work_role&size=100`)).items : []; } catch (err) { toast(err.message, "err"); }
        $("#fw-r").hidden = !roles.length;
        mount($("#fw-r"), html`<option value="">${t("Bütün iş rolları")}</option>${roles.map((r) => html`<option value="${r.code}">${r.code} · ${r.title}</option>`)}`);
        $("#fw-note").textContent = fw.note || "";
        await load();
      };
      on(w, "change", "#fw-f", (e, n) => { fw = FWS.find((f) => f.id === +n.value) || fw; setFw(); });
      on(w, "change", "#fw-k", (e, n) => { kind = n.value; page = 1; load(); });
      on(w, "change", "#fw-r", (e, n) => { role = n.value; page = 1; load(); });
      on(w, "input", "#fw-q", (e, n) => { clearTimeout(timer); timer = setTimeout(() => { q = n.value.trim(); page = 1; load(); }, 300); });
      on(w, "click", "#fw-prev", () => { page = Math.max(1, page - 1); load(); });
      on(w, "click", "#fw-next", () => { page += 1; load(); });
      on(w, "change", "[data-pick]", (e, n) => {
        const x = items.find((y) => y.id === +n.dataset.pick);
        if (n.checked && x) chosen.set(x.id, { ...x, key: fw.key, version: fw.version });
        else chosen.delete(+n.dataset.pick);
        drawChosen();
      });
      on(w, "click", "[data-unpick]", (e, b) => { chosen.delete(+b.dataset.unpick); drawChosen(); load(); });
      drawChosen();
      setFw();
    } });
}

const opts = (list, cur) => list.map(([k, l]) => html`<option value="${k}" ${k === cur ? "selected" : ""}>${l}</option>`);
const clone = (x) => JSON.parse(JSON.stringify(x));
// A code that still has framework items is never reused (BR-F2): a new outcome must not inherit another one's items.
const nextId = (outs, tags = {}) => `N${Math.max(0, ...[...outs.map((o) => o.id), ...Object.keys(tags)].map((id) => +id.slice(1) || 0)) + 1}`;

route("/teacher/syllabus", async (el, p, q) => {
  mount(el, loading());
  let cs;
  try { cs = await api.get("/api/courses"); } catch (err) { return mount(el, failed(err.message)); }
  const crumbs = [[t("Əsas"), "/teacher"], [t("Sillabus")]];
  if (!cs.length) return mount(el, html`${pageHead(t("Sillabus"), "", "", crumbs)}
    ${empty("layers", t("Fənn tapılmadı"), t("Sillabus hazırlamaq üçün sizə təyin olunmuş fənn lazımdır."), { label: t("Fənlərim"), go: "/teacher/courses", icon: "book" })}`);
  const co = cs.find((x) => x.id === +q.course) || cs[0];
  let st, s = null, dirty = false, tags = {};
  try {
    [st, tags] = await Promise.all([api.get(`/api/syllabi/${co.id}`), api.get(`/api/syllabi/${co.id}/frameworks`).then((r) => r.outcomes)]);
    s = st.latest ? clone(st.latest.data) : null;
  } catch (err) { return mount(el, failed(err.message)); }
  const sum = () => (s ? s.assessment.reduce((a, x) => a + (+x.weight || 0), 0) : 0);

  // the warnings follow the editor as it changes, without redrawing it
  const drawChecks = () => { const box = el.querySelector("#syl-checks"); if (box && s) mount(box, checksNotice(checksOf(s, tags))); };
  const draw = () => {
    const total = Math.round(sum() * 100) / 100, imported = st.imported || {};
    mount(el, html`${pageHead(t("Sillabus"), t("Strukturlaşdırılmış sillabus: hər saxlama yeni versiyadır, dərc olunmuş versiya dəyişmir."),
        html`<select class="select" id="cs" style="width:auto" aria-label="${t("Fənn")}">${cs.map((x) => html`<option value="${x.id}" ${x.id === co.id ? "selected" : ""}>${x.name}</option>`)}</select>
        ${st.can_edit ? html`<button class="btn btn-ai" id="gen">${ic("sparkles", 15)} ${s ? t("Yeni layihə") : t("Layihə hazırla")}</button>` : ""}`, crumbs)}
      ${!s ? html`<div class="card">${empty("layers", t("Sillabus hələ yoxdur"), st.can_edit ? t("«Layihə hazırla» materiallarınızdan və Forma №3-dən ilkin variant qurur.") : t("Fənnin müəllimi sillabusu hələ saxlamayıb."),
          st.can_edit ? { label: t("Layihə hazırla"), id: "gen-empty", icon: "sparkles" } : undefined)}</div>` : html`
      ${st.latest && st.latest.status === "returned" && st.steps.length ? html`<div class="notice warn mb">${ic("alert", 16)}<div>
        <b>${t("Geri qaytarılıb")}</b>: ${st.steps[st.steps.length - 1].note || ""} <span class="tiny muted">· ${st.steps[st.steps.length - 1].who || ""}</span>
        <div class="tiny muted">${t("Düzəldib yeni versiya kimi saxlayın və yenidən təsdiqə göndərin.")}</div></div></div>` : ""}
      <div class="row between mb wrap" data-tour="actions"><span class="small muted">${st.latest ? html`${t("Versiya {n} · {d}", { n: st.latest.version, d: fmtDate(st.latest.created_at) })} ${badge(st.latest.status)}` : t("Hələ saxlanılmayıb")}
          ${dirty ? html` · <span class="badge b-amber">${t("Yadda saxlanılmamış dəyişikliklər")}</span>` : ""}</span>
        <div class="row wrap">${!dirty && st.actions.includes("submit") ? html`<button class="btn btn-ai" id="submit">${ic("send", 15)} ${STEP().submit}</button>` : ""}
          <button class="btn" id="print">${ic("printer", 15)} ${t("Çap et")}</button>
          ${st.can_edit ? html`<button class="btn btn-primary" id="save">${ic("check", 15)} ${t("Yeni versiya kimi saxla")}</button>` : ""}</div></div>
      <div class="grid g-12"><div class="stack">
        <div class="card"><div class="card-h"><h3>${ic("book", 17)} ${t("Fənnin təsviri")}</h3></div><div class="card-b"><textarea class="textarea" data-f="description" maxlength="4000" aria-label="${t("Fənnin təsviri")}">${s.description}</textarea></div></div>
        <div class="card" data-tour="outcomes"><div class="card-h"><h3>${ic("target", 17)} ${t("Təlim nəticələri")}</h3><button class="btn btn-sm" id="add-o">${ic("plus", 13)} ${t("Əlavə et")}</button></div>
          <div class="card-b syl-rows">${s.outcomes.map((o, i) => html`<div class="syl-row">
            <div class="syl-row-h"><b>${o.id}</b><select class="select" data-o-bloom="${i}" aria-label="${t("Bloom səviyyəsi")}: ${o.id}">${opts(BLOOM(), o.bloom)}</select>
              <span class="grow"></span><button class="btn btn-ghost btn-icon" data-o-del="${i}" aria-label="${t("Sil")}: ${o.id}">${ic("x", 14)}</button></div>
            <textarea class="textarea syl-text" rows="2" data-o-text="${i}" aria-label="${t("Nəticə")}: ${o.id}">${o.text}</textarea>
            <div class="row wrap">${tagChips(tags[o.id] || [])}${st.latest && st.latest.data.outcomes.some((x) => x.id === o.id)
              ? html`<button class="btn btn-ghost btn-sm" data-o-tags="${o.id}">${ic("plus", 13)} ${t("Bəndlər")}</button>`
              : html`<span class="tiny muted">${t("Saxladıqdan sonra")}</span>`}</div></div>`)}
            <div id="syl-checks"></div>
            <div class="tiny muted">${t("Ölçülə bilən fellərdən istifadə edin: «izah edir», «hesablayır», «layihələndirir».")}</div></div></div>
        <div class="card"><div class="card-h"><h3>${ic("calendar", 17)} ${t("Həftəlik plan")}</h3><button class="btn btn-sm" id="add-w">${ic("plus", 13)} ${t("Həftə əlavə et")}</button></div>
          <div class="card-b syl-rows">${s.plan.map((w, i) => html`<div class="syl-row">
            <div class="syl-row-h"><label class="small" for="pw-${i}">${t("Həftə")}</label><input class="input" id="pw-${i}" type="number" min="1" max="30" style="width:70px" data-p-week="${i}" value="${w.week}">
              <span class="row wrap grow" role="group" aria-label="${t("Nəticələr")}">${s.outcomes.map((o) => html`<label class="small nowrap"><input type="checkbox" data-p-out="${i}" value="${o.id}" ${w.outcomes.includes(o.id) ? "checked" : ""}> ${o.id}</label>`)}</span>
              <button class="btn btn-ghost btn-icon" data-p-del="${i}" aria-label="${t("Sil")}: ${t("Həftə")} ${w.week}">${ic("x", 14)}</button></div>
            <textarea class="textarea syl-text" rows="2" data-p-topic="${i}" aria-label="${t("Mövzu")}: ${t("Həftə")} ${w.week}" placeholder="${t("Mövzu")}">${w.topic}</textarea>
            <textarea class="textarea syl-text" rows="2" data-p-act="${i}" aria-label="${t("Fəaliyyət")}: ${t("Həftə")} ${w.week}" placeholder="${t("Fəaliyyət")}">${w.activity}</textarea></div>`)}</div></div>
        <div class="card"><div class="card-h"><h3>${ic("chart", 17)} ${t("Qiymətləndirmə")}</h3><span class="badge ${total === 100 ? "b-green" : "b-red"}" id="asum">${t("Cəmi: {n}", { n: total })}</span></div>
          <div class="table-wrap"><table class="table"><thead><tr><th>${t("Komponent")}</th><th>${t("Növ")}</th><th>${t("Çəki")}</th><th>${t("Nəticələr")}</th><th></th></tr></thead><tbody>
          ${s.assessment.map((a, i) => html`<tr><td><input class="input" data-a-name="${i}" value="${a.name}" aria-label="${t("Komponent")}"></td>
            <td><select class="select" data-a-kind="${i}" aria-label="${t("Növ")}">${opts(KIND(), a.kind)}</select></td>
            <td><input class="input" type="number" min="0.5" max="100" step="0.5" style="width:76px" data-a-weight="${i}" value="${a.weight}" aria-label="${t("Çəki")}"></td>
            <td><span class="row wrap" role="group" aria-label="${t("Qiymətləndirdiyi nəticələr")}">${s.outcomes.map((o) => html`<label class="small nowrap"><input type="checkbox" data-a-out="${i}" value="${o.id}" ${(a.outcomes || []).includes(o.id) ? "checked" : ""}> ${o.id}</label>`)}</span></td>
            <td><button class="btn btn-ghost btn-icon" data-a-del="${i}" aria-label="${t("Sil")}">${ic("x", 14)}</button></td></tr>`)}</tbody></table></div>
          <div class="card-b stack sm"><button class="btn btn-sm" id="add-a">${ic("plus", 13)} ${t("Komponent əlavə et")}</button>
            <div class="tiny muted">${t("Çəkilərin cəmi 100 olmalıdır; imtahanın çəkisini universitet təyin edir.")}</div></div></div>
        <div class="card"><div class="card-h"><h3>${ic("shield", 17)} ${t("Qaydalar")}</h3></div><div class="card-b stack sm">
          <div class="field"><label class="label" for="r-lim">${t("Buraxılmış dərslərin həddi, %")}</label><input class="input" id="r-lim" type="number" min="1" max="${st.limit_percent}" step="0.5" data-r="attendance_limit" value="${s.rules.attendance_limit}">
            <div class="tiny muted">${t("Universitetin həddi {n}%: sillabus onu yalnız aşağı sala bilər.", { n: st.limit_percent })}</div></div>
          <div class="field"><label class="label" for="r-late">${t("Gecikmiş işlər")}</label><textarea class="textarea" id="r-late" data-r="late_policy" style="min-height:60px">${s.rules.late_policy}</textarea></div>
          <div class="field"><label class="label" for="r-ai">${t("Süni intellektdən istifadə")}</label><select class="select" id="r-ai" data-r="ai_policy">${opts(AI(), s.rules.ai_policy)}</select>
            <textarea class="textarea mt-sm" data-r="ai_note" style="min-height:50px" aria-label="${t("AI siyasətinin izahı")}">${s.rules.ai_note}</textarea></div></div></div>
      </div><div class="stack">
        <div class="card"><div class="card-h"><h3>${ic("clock", 17)} ${t("İş yükü, saat")}</h3></div><div class="card-b stack sm">
          ${WORK().map(([k, l]) => html`<div class="row between"><label class="small" for="w-${k}">${l}</label><span class="row">
            ${imported[k] != null ? html`<span class="tiny ${+imported[k] !== +s.workload[k] ? "badge b-amber" : "muted"}">${t("Forma №3: {n}", { n: imported[k] })}</span>` : ""}
            <input class="input" id="w-${k}" type="number" min="0" step="0.5" style="width:90px" data-w="${k}" value="${s.workload[k]}"></span></div>`)}
          ${Object.keys(imported).length ? html`<div class="tiny muted">${t("Forma №3-dən fərqlənən saatlar təsdiq zamanı kafedra müdirinə fərq kimi göstərilir.")}</div>` : html`<div class="tiny muted">${t("Bu fənn üçün Forma №3 idxal olunmayıb.")}</div>`}</div></div>
        <div class="card"><div class="card-h"><h3>${ic("list", 17)} ${t("Prerekvizitlər")}</h3></div><div class="card-b">
          <textarea class="textarea" data-pre style="min-height:60px" aria-label="${t("Prerekvizitlər")}" placeholder="${t("Hər sətirdə bir fənn")}">${s.prerequisites.join("\n")}</textarea></div></div>
        <div class="card"><div class="card-h"><h3>${ic("file", 17)} ${t("Ədəbiyyat")}</h3><button class="btn btn-sm" id="add-l">${ic("plus", 13)} ${t("Əlavə et")}</button></div><div class="card-b stack sm">
          ${s.literature.map((x, i) => html`<div class="row"><input class="input grow" data-l-title="${i}" value="${x.title}" aria-label="${t("Mənbə")}">
            <select class="select" data-l-kind="${i}" style="width:auto" aria-label="${t("Növ")}">${opts(LIT(), x.kind)}</select>
            <button class="btn btn-ghost btn-icon" data-l-del="${i}" aria-label="${t("Sil")}">${ic("x", 14)}</button></div>`)}</div></div>
        <div class="card"><div class="card-h"><h3>${ic("layers", 17)} ${t("Versiyalar")}</h3></div><div class="card-b list">
          ${st.versions.length ? st.versions.map((v) => html`<div class="list-item"><div class="grow"><b class="small">${t("Versiya {n}", { n: v.version })}</b>
            <div class="tiny muted">${fmtDate(v.created_at)}${v.author ? " · " + v.author : ""}</div></div>
            <span class="badge ${(STATUS()[v.status] || ["", "b-gray"])[1]}">${(STATUS()[v.status] || [v.status])[0]}</span>
            ${st.versions.find((x) => x.version === v.version - 1) ? html`<button class="btn btn-ghost btn-sm" data-diff="${v.id}" data-prev="${st.versions.find((x) => x.version === v.version - 1).id}">${t("Fərq")}</button>` : ""}
            ${st.can_edit ? html`<button class="btn btn-sm" data-from="${v.id}">${t("Bundan davam et")}</button>` : ""}</div>`) : html`<span class="small muted">${t("Hələ versiya yoxdur")}</span>`}</div></div>
      </div></div>`}`);
    drawChecks();
  };
  draw();

  el.addEventListener("input", (e) => {
    if (!s) return;
    const d = e.target.dataset, v = e.target.value;
    if (d.f) s[d.f] = v;
    else if (d.oText !== undefined) s.outcomes[+d.oText].text = v;
    else if (d.pWeek !== undefined) s.plan[+d.pWeek].week = +v;
    else if (d.pTopic !== undefined) s.plan[+d.pTopic].topic = v;
    else if (d.pAct !== undefined) s.plan[+d.pAct].activity = v;
    else if (d.aName !== undefined) s.assessment[+d.aName].name = v;
    else if (d.aWeight !== undefined) {
      s.assessment[+d.aWeight].weight = +v;
      const b = el.querySelector("#asum"), sm = Math.round(sum() * 100) / 100;
      if (b) { b.textContent = t("Cəmi: {n}", { n: sm }); b.className = `badge ${sm === 100 ? "b-green" : "b-red"}`; }
    } else if (d.r !== undefined && d.r !== "ai_policy") s.rules[d.r] = d.r === "attendance_limit" ? +v : v;
    else if (d.pre !== undefined) s.prerequisites = v.split("\n").map((x) => x.trim()).filter(Boolean);
    else if (d.lTitle !== undefined) s.literature[+d.lTitle].title = v;
    else if (d.w) s.workload[d.w] = +v;
    else return;
    dirty = true;
  });
  el.addEventListener("change", (e) => {
    if (!s) return;
    const d = e.target.dataset, v = e.target.value;
    if (d.oBloom !== undefined) s.outcomes[+d.oBloom].bloom = v;
    else if (d.aKind !== undefined) s.assessment[+d.aKind].kind = v;
    else if (d.lKind !== undefined) s.literature[+d.lKind].kind = v;
    else if (d.r === "ai_policy") s.rules.ai_policy = v;
    else if (d.pOut !== undefined) {
      const w = s.plan[+d.pOut];
      w.outcomes = e.target.checked ? [...new Set([...w.outcomes, v])] : w.outcomes.filter((x) => x !== v);
    } else if (d.aOut !== undefined) {
      const a = s.assessment[+d.aOut], cur = a.outcomes || [];
      a.outcomes = e.target.checked ? [...new Set([...cur, v])] : cur.filter((x) => x !== v);
    } else return;
    dirty = true;
    drawChecks();
  });
  const edit = (fn) => { fn(); dirty = true; draw(); };
  on(el, "click", "#add-o", () => edit(() => s.outcomes.push({ id: nextId(s.outcomes, tags), text: "", bloom: "apply" })));
  on(el, "click", "[data-o-del]", (e, b) => edit(() => {
    const [gone] = s.outcomes.splice(+b.dataset.oDel, 1);
    s.plan.forEach((w) => { w.outcomes = w.outcomes.filter((x) => x !== gone.id); });
    s.assessment.forEach((a) => { a.outcomes = (a.outcomes || []).filter((x) => x !== gone.id); });
  }));
  on(el, "click", "[data-o-tags]", (e, b) => pickTags(co.id, b.dataset.oTags, tags[b.dataset.oTags] || [], (r) => { tags = r.outcomes; draw(); }));
  on(el, "click", "#add-w", () => edit(() => s.plan.push({ week: Math.max(0, ...s.plan.map((w) => w.week)) + 1, topic: "", outcomes: [], activity: "" })));
  on(el, "click", "[data-p-del]", (e, b) => edit(() => s.plan.splice(+b.dataset.pDel, 1)));
  on(el, "click", "#add-a", () => edit(() => s.assessment.splice(Math.max(0, s.assessment.length - 1), 0, { name: "", kind: "component", weight: 5, outcomes: [] })));
  on(el, "click", "[data-a-del]", (e, b) => edit(() => s.assessment.splice(+b.dataset.aDel, 1)));
  on(el, "click", "#add-l", () => edit(() => s.literature.push({ title: "", kind: "main" })));
  on(el, "click", "[data-l-del]", (e, b) => edit(() => s.literature.splice(+b.dataset.lDel, 1)));
  on(el, "change", "#cs", async (e, n) => {
    if (dirty && !(await confirmBox(t("Yadda saxlanılmamış dəyişikliklər"), t("Dəyişikliklər saxlanılmayıb. Başqa fənnə keçsəniz, itəcək."), t("Davam et")))) { n.value = String(co.id); return; }
    go(`/teacher/syllabus?course=${n.value}`);
  });
  on(el, "click", "#gen, #gen-empty", async (e, b) => {
    if (s && !(await confirmBox(t("Yeni layihə"), t("Redaktordakı mətn materiallardan və Forma №3-dən qurulan yeni layihə ilə əvəz olunacaq. Saxlanmış versiyalar qalır."), t("Davam et"), true))) return;
    b.disabled = true;
    try { s = (await api.post(`/api/syllabi/${co.id}/draft`)).data; dirty = true; draw(); toast(t("Layihə hazırdır: nəticələri və planı yoxlayıb saxlayın"), "ok"); }
    catch (err) { toast(err.message, "err"); b.disabled = false; }
  });
  on(el, "click", "[data-from]", async (e, b) => {
    try { s = clone((await api.get(`/api/syllabi/${co.id}/versions/${b.dataset.from}`)).data); dirty = true; draw(); }
    catch (err) { toast(err.message, "err"); }
  });
  on(el, "click", "[data-diff]", async (e, b) => {
    try { modal({ title: t("Əvvəlki versiyadan fərq"), body: diffList(await api.get(`/api/syllabi/${co.id}/diff?a=${b.dataset.prev}&b=${b.dataset.diff}`)) }); }
    catch (err) { toast(err.message, "err"); }
  });
  on(el, "click", "#submit", async () => {
    if (!(await confirmBox(STEP().submit, t("Versiya {n} kafedra müdirinə göndəriləcək. Göndərilən versiya dəyişmir.", { n: st.latest.version }), STEP().submit))) return;
    try { st = await api.post(`/api/syllabi/${co.id}/versions/${st.latest.id}/submit`); toast(t("Təsdiqə göndərildi"), "ok"); draw(); }
    catch (err) { toast(err.message, "err"); }
  });
  const save = async () => {
    try {
      st = await api.put(`/api/syllabi/${co.id}`, { data: s, base: st.latest ? st.latest.version : 0 });
      s = clone(st.latest.data);
      dirty = false;
      toast(t("Versiya {n} saxlanıldı", { n: st.latest.version }), "ok");
      return true;
    } catch (err) { toast(err.message, "err"); return false; }
  };
  on(el, "click", "#save", async () => { if (await save()) draw(); });
  on(el, "click", "#print", async () => {
    if (dirty && st.can_edit && !(await save())) return;
    draw();
    openSyllabus(co.id, t("Sillabus: {name}", { name: co.name }));
  });
});

registerTour("teacher.syllabus", { route: "/teacher/syllabus", roles: ["teacher"], title: t("Sillabus"), group: t("Müəllim"), icon: "layers", steps: [
  { sel: '[data-tour="outcomes"]', title: t("Təlim nəticələri"), text: t("Hər nəticənin kodu və Bloom səviyyəsi var; həftəlik plan nəticələrə istinad edir.") },
  { sel: '[data-tour="actions"]', title: t("Versiyalar"), text: t("Hər saxlama yeni versiyadır. Çap görünüşü portalın daxilində açılır.") },
] });

// The coverage report of a programme (Task 24): per NICE work role, how many of its task, knowledge and skill statements
// an outcome of the programme's courses covers; a role's page lists the covering outcomes and the uncovered statements.
const STATEMENT_KINDS = ["task", "knowledge", "skill"];
route("/frameworks/coverage", async (el, p, qs) => {
  mount(el, loading());
  let progs, fws, rep = null;
  try { [progs, fws] = await Promise.all([api.get("/api/frameworks/programmes"), api.get("/api/frameworks")]); } catch (err) { return mount(el, failed(err.message)); }
  const crumbs = [[t("Əsas"), HOME[S.user.role] || "/"], [t("Çərçivə əhatəsi")]];
  const nice = fws.filter((f) => f.counts.work_role);
  const sid = +qs.programme || (progs[0] || {}).id, fid = +qs.framework || (nice[0] || {}).id;
  const head = (actions = "") => pageHead(t("Çərçivə əhatəsi"), t("İxtisasın fənlərindəki təlim nəticələri NICE iş rollarının bəyanatlarını nə qədər örtür."), actions, crumbs);
  if (!progs.length || !nice.length) {
    return mount(el, html`${head()}<div class="card">${empty("target", progs.length ? t("NICE çərçivəsi idxal olunmayıb") : t("Sizə aid ixtisas yoxdur"),
      progs.length ? t("Administrator faylı manage.py import-framework əmri ilə idxal edir.") : "")}</div>`);
  }
  try { rep = await api.get(`/api/frameworks/coverage?programme=${sid}&framework=${fid}${qs.role ? `&role=${encodeURIComponent(qs.role)}` : ""}`); }
  catch (err) { return mount(el, failed(err.message)); }
  const pct = (a, b) => (b ? Math.round((a * 100) / b) : 0);
  const to = (patch) => go(`/frameworks/coverage?${new URLSearchParams({ programme: sid, framework: fid, ...patch })}`);
  const role = rep.role;
  const bad = role ? role.statements.filter((x) => !x.covered_by.length) : [];
  mount(el, html`${head(html`<select class="select" id="cv-p" style="width:auto" aria-label="${t("İxtisas")}">${progs.map((x) => html`<option value="${x.id}" ${x.id === sid ? "selected" : ""}>${x.code} · ${x.name}</option>`)}</select>
      <select class="select" id="cv-f" style="width:auto" aria-label="${t("Çərçivə")}">${nice.map((f) => html`<option value="${f.id}" ${f.id === fid ? "selected" : ""}>${fwName(f)}</option>`)}</select>
      <a class="btn" href="/api/frameworks/coverage?programme=${sid}&framework=${fid}&format=csv&lang=${LANG}" download>${ic("download", 15)} CSV</a>`)}
    <p class="small muted">${t("Fənlər: {c}. Təlim nəticələri: {o}. Dərc olunmuş sillabus, yoxdursa son versiya oxunur.", { c: rep.courses, o: rep.outcomes })}</p>
    ${role ? html`<div class="card mb"><div class="card-h"><h3>${role.code} · ${role.title}</h3><button class="btn btn-sm" id="cv-close">${t("Bağla")}</button></div>
      <div class="card-b stack sm"><p class="small muted" style="margin:0">${role.text}</p>
        <b class="small">${t("Örtülən bəyanatlar")}</b>
        ${role.statements.filter((x) => x.covered_by.length).map((x) => html`<div class="list-item"><div class="grow"><b class="small">${x.code}</b> <span class="badge b-gray">${rep.labels[x.kind]}</span>
          <div class="small">${x.text}</div></div><div class="chips">${x.covered_by.map((b) => html`<span class="badge b-green" title="${b.name}: ${b.text}">${b.course} ${b.outcome}</span>`)}</div></div>`)}
        <b class="small">${t("Örtülməyən bəyanatlar: {n}", { n: bad.length })}</b>
        ${bad.map((x) => html`<div class="list-item"><div class="grow"><b class="small">${x.code}</b> <span class="badge b-gray">${rep.labels[x.kind]}</span><div class="small">${x.text}</div></div></div>`)}</div></div>` : ""}
    <div class="card"><div class="table-wrap"><table class="table"><thead><tr><th>${t("İş rolu")}</th><th>${t("Kateqoriya")}</th>
      ${STATEMENT_KINDS.map((k) => html`<th>${rep.labels[k]}</th>`)}<th>${t("Örtülür")}</th><th></th></tr></thead><tbody>
      ${rep.roles.map((r) => html`<tr><td><b class="small">${r.code}</b> · ${r.title}</td><td class="small muted">${r.category || ""}</td>
        ${STATEMENT_KINDS.map((k) => html`<td class="nowrap">${r.kinds[k].covered}/${r.kinds[k].total}</td>`)}
        <td><span class="badge ${r.covered ? "b-blue" : "b-gray"}">${pct(r.covered, r.total)}%</span></td>
        <td><button class="btn btn-sm" data-role="${r.code}">${t("Bax")}</button></td></tr>`)}</tbody></table></div></div>`);
  on(el, "change", "#cv-p", (e, n) => to({ programme: n.value }));
  on(el, "change", "#cv-f", (e, n) => to({ framework: n.value }));
  on(el, "click", "[data-role]", (e, b) => to({ role: b.dataset.role }));
  on(el, "click", "#cv-close", () => to({}));
});

// The approval queue (Task 25): a department head approves or returns submitted versions of the courses the grant
// covers, the academic office publishes or returns approved ones. Publication configures the course.
route("/syllabi", async (el) => {
  mount(el, loading());
  let list;
  try { list = await api.get("/api/syllabi/queue"); } catch (err) { return mount(el, failed(err.message)); }
  const crumbs = [[t("Əsas"), HOME[S.user.role] || "/"], [t("Sillabus təsdiqi")]];
  mount(el, html`${pageHead(t("Sillabus təsdiqi"), t("Təsdiq gözləyən versiyalar: fərqə baxın, təsdiqləyin və ya şərhlə geri qaytarın."), "", crumbs)}
    <div class="card">${list.length ? html`<div class="table-wrap"><table class="table"><thead><tr><th>${t("Fənn")}</th><th>${t("Versiya")}</th><th>${t("Müəllif")}</th>
      <th>${t("Status")}</th><th>${t("Forma №3")}</th><th>${t("Dəyişiklik")}</th><th></th></tr></thead><tbody>
      ${list.map((x) => html`<tr><td><b class="small">${x.code}</b> · ${x.name}</td><td>${x.version}</td><td>${x.author || "—"}</td><td>${badge(x.status)}</td>
        <td>${x.forma3.length ? html`<span class="badge b-amber">${t("{n} fərq", { n: x.forma3.length })}</span>` : html`<span class="tiny muted">—</span>`}</td>
        <td>${x.changes == null ? html`<span class="tiny muted">${t("ilk dərc")}</span>` : x.changes}
          ${x.returned_id ? html`<div class="tiny muted">${t("Geri qaytarılmış versiyadan fərq: {c}", { c: x.changes_returned })}</div>` : ""}</td>
        <td><button class="btn btn-sm" data-open="${x.id}">${t("Bax")}</button></td></tr>`)}</tbody></table></div>`
      : html`<div class="card-b">${empty("check", t("Təsdiq gözləyən sillabus yoxdur"), t("Müəllim versiyanı təqdim etdikdə burada görünür."))}</div>`}</div>`);
  on(el, "click", "[data-open]", async (e, b) => {
    const x = list.find((y) => y.id === Number(b.dataset.open));
    let v, diff = [], back = [];
    try {
      [v, diff, back] = await Promise.all([api.get(`/api/syllabi/${x.course_id}/versions/${x.id}`),
        x.published_id ? api.get(`/api/syllabi/${x.course_id}/diff?a=${x.published_id}&b=${x.id}`) : [],
        x.returned_id ? api.get(`/api/syllabi/${x.course_id}/diff?a=${x.returned_id}&b=${x.id}`) : []]);
    } catch (err) { toast(err.message, "err"); return; }
    const DONE = { approve: t("Sillabus təsdiqləndi"), return: t("Sillabus geri qaytarıldı"), publish: t("Sillabus dərc olundu") };
    const act = async (action, w, extra = {}) => {
      try {
        await api.post(`/api/syllabi/${x.course_id}/versions/${x.id}/${action}`, { note: w.querySelector("#sv-note").value, ...extra });
        toast(DONE[action], "ok"); go("/syllabi"); return true;
      } catch (err) {
        if (err.status === 409 && action === "publish") {
          w.querySelector("#sv-override").hidden = false;
          toast(err.message, "err"); return false;
        }
        toast(err.message, "err"); return false;
      }
    };
    modal({ title: `${x.code} · ${t("Versiya {n}", { n: x.version })}`, size: "lg", body: html`<div class="stack">
        ${x.forma3.length ? html`<div class="notice warn">${ic("alert", 16)}<div><b>${t("Forma №3-dən fərq")}</b>: ${x.forma3.map((f) => html`${label(WORK, f.kind)} ${f.imported} → ${f.syllabus}; `)}</div></div>` : ""}
        ${x.returned_id ? html`<div><b class="small">${t("Geri qaytarılmış versiyadan fərq (versiya {n})", { n: x.returned_version })}</b>
          ${x.returned_note ? html`<div class="tiny muted">${t("Geri qaytarma şərhi")}: ${x.returned_note}</div>` : ""}${diffList(back)}</div>` : ""}
        ${x.published_id ? html`<div><b class="small">${t("Dərc olunmuş versiyadan fərq")}</b>${diffList(diff)}</div>` : ""}
        ${checksNotice(v.checks)}
        <a class="btn btn-sm" href="/syllabus/${x.course_id}?v=${x.id}&lang=${LANG}" target="_blank" rel="noopener" style="align-self:flex-start">${ic("printer", 15)} ${t("Çap görünüşü")}</a>
        ${readOnly(v.data, v.tags)}
        <div class="field"><label class="label" for="sv-note">${t("Şərh")}</label><textarea class="textarea" id="sv-note" style="min-height:60px"></textarea></div>
        <div id="sv-override" hidden><label class="row small"><input type="checkbox" id="sv-ok"> ${t("Bu fənn üzrə artıq bal qoyulub: dərcə icazə verirəm (səbəb şərhdə göstərilir və audit jurnalında qeydə alınır)")}</label></div></div>`,
      actions: [
        ...(x.actions.includes("return") ? [{ label: STEP().return, onClick: (w) => act("return", w) }] : []),
        ...(x.actions.includes("approve") ? [{ label: STEP().approve, cls: "btn-primary", onClick: (w) => act("approve", w) }] : []),
        ...(x.actions.includes("publish") ? [{ label: STEP().publish, cls: "btn-primary", onClick: (w) => act("publish", w, { override: w.querySelector("#sv-ok").checked }) }] : []),
      ] });
  });
});
