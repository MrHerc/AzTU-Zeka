// The structured syllabus (Task 23): outcomes with a Bloom level, a weekly plan that names its outcomes, weighted
// assessment, rules, prerequisites, literature and the workload from Forma №3. Every save is a new version; the server
// checks the university's rules (weights, the exam's weight, the attendance limit) and says what is wrong.
import { api, html, mount, on, ic, toast, route, go, t, pageHead, fmtDate, loading, empty, failed, confirmBox, openSyllabus, registerTour } from "./core.js";

const BLOOM = () => [["remember", t("Xatırlama")], ["understand", t("Anlama")], ["apply", t("Tətbiq")], ["analyze", t("Təhlil")],
  ["evaluate", t("Qiymətləndirmə")], ["create", t("Yaratma")]];
const KIND = () => [["component", t("Cari qiymətləndirmə")], ["attendance", t("Davamiyyət")], ["exam", t("İmtahan")]];
const AI = () => [["allowed", t("İcazə verilir")], ["limited", t("Məhdud: izah və məşq üçün")], ["forbidden", t("Qadağandır")]];
const LIT = () => [["main", t("Əsas")], ["extra", t("Əlavə")]];
const WORK = () => [["lecture", t("Mühazirə")], ["seminar", t("Məşğələ")], ["lab", t("Laboratoriya")], ["independent", t("Sərbəst iş")]];
const STATUS = () => ({ draft: [t("Qaralama"), "b-gray"], submitted: [t("Təqdim olunub"), "b-blue"], approved: [t("Kafedra təsdiqləyib"), "b-amber"],
  published: [t("Dərc olunub"), "b-green"], returned: [t("Geri qaytarılıb"), "b-red"] });
const opts = (list, cur) => list.map(([k, l]) => html`<option value="${k}" ${k === cur ? "selected" : ""}>${l}</option>`);
const clone = (x) => JSON.parse(JSON.stringify(x));
const nextId = (outs) => `N${Math.max(0, ...outs.map((o) => +o.id.slice(1) || 0)) + 1}`;

route("/teacher/syllabus", async (el, p, q) => {
  mount(el, loading());
  let cs;
  try { cs = await api.get("/api/courses"); } catch (err) { return mount(el, failed(err.message)); }
  const crumbs = [[t("Əsas"), "/teacher"], [t("Sillabus")]];
  if (!cs.length) return mount(el, html`${pageHead(t("Sillabus"), "", "", crumbs)}
    ${empty("layers", t("Fənn tapılmadı"), t("Sillabus hazırlamaq üçün sizə təyin olunmuş fənn lazımdır."), { label: t("Fənlərim"), go: "/teacher/courses", icon: "book" })}`);
  const co = cs.find((x) => x.id === +q.course) || cs[0];
  let st, s = null, dirty = false;
  try {
    st = await api.get(`/api/syllabi/${co.id}`);
    s = st.latest ? clone(st.latest.data) : null;
  } catch (err) { return mount(el, failed(err.message)); }
  const sum = () => (s ? s.assessment.reduce((a, x) => a + (+x.weight || 0), 0) : 0);

  const draw = () => {
    const total = Math.round(sum() * 100) / 100, imported = st.imported || {};
    mount(el, html`${pageHead(t("Sillabus"), t("Struktur sillabus: hər saxlama yeni versiyadır, dərc olunmuş versiya dəyişmir."),
        html`<select class="select" id="cs" style="width:auto" aria-label="${t("Fənn")}">${cs.map((x) => html`<option value="${x.id}" ${x.id === co.id ? "selected" : ""}>${x.name}</option>`)}</select>
        ${st.can_edit ? html`<button class="btn btn-ai" id="gen">${ic("sparkles", 15)} ${s ? t("Yeni layihə") : t("Layihə hazırla")}</button>` : ""}`, crumbs)}
      ${!s ? html`<div class="card">${empty("layers", t("Sillabus hələ yoxdur"), st.can_edit ? t("“Layihə hazırla” materiallarınızdan və Forma №3-dən ilkin variant qurur.") : t("Fənnin müəllimi sillabusu hələ saxlamayıb."),
          st.can_edit ? { label: t("Layihə hazırla"), id: "gen-empty", icon: "sparkles" } : undefined)}</div>` : html`
      <div class="row between mb wrap" data-tour="actions"><span class="small muted">${st.latest ? t("Versiya {n} · {d}", { n: st.latest.version, d: fmtDate(st.latest.created_at) }) : t("Hələ saxlanılmayıb")}
          ${dirty ? html` · <span class="badge b-amber">${t("Yadda saxlanılmamış dəyişikliklər")}</span>` : ""}</span>
        <div class="row wrap"><button class="btn" id="print">${ic("printer", 15)} ${t("Çap et")}</button>
          ${st.can_edit ? html`<button class="btn btn-primary" id="save">${ic("check", 15)} ${t("Yeni versiya kimi saxla")}</button>` : ""}</div></div>
      <div class="grid g-12"><div class="stack">
        <div class="card"><div class="card-h"><h3>${ic("book", 17)} ${t("Fənnin təsviri")}</h3></div><div class="card-b"><textarea class="textarea" data-f="description" aria-label="${t("Fənnin təsviri")}">${s.description}</textarea></div></div>
        <div class="card" data-tour="outcomes"><div class="card-h"><h3>${ic("target", 17)} ${t("Təlim nəticələri")}</h3><button class="btn btn-sm" id="add-o">${ic("plus", 13)} ${t("Əlavə et")}</button></div>
          <div class="table-wrap"><table class="table"><thead><tr><th>${t("Kod")}</th><th>${t("Nəticə")}</th><th>${t("Bloom səviyyəsi")}</th><th></th></tr></thead><tbody>
          ${s.outcomes.map((o, i) => html`<tr><td><b>${o.id}</b></td><td><input class="input" data-o-text="${i}" value="${o.text}" aria-label="${t("Nəticə")}"></td>
            <td><select class="select" data-o-bloom="${i}" aria-label="${t("Bloom səviyyəsi")}">${opts(BLOOM(), o.bloom)}</select></td>
            <td><button class="btn btn-ghost btn-icon" data-o-del="${i}" aria-label="${t("Sil")}">${ic("x", 14)}</button></td></tr>`)}</tbody></table></div>
          <div class="card-b tiny muted">${t("Ölçülə bilən fellər yazın: “izah edir”, “hesablayır”, “layihələndirir”.")}</div></div>
        <div class="card"><div class="card-h"><h3>${ic("calendar", 17)} ${t("Həftəlik plan")}</h3><button class="btn btn-sm" id="add-w">${ic("plus", 13)} ${t("Həftə əlavə et")}</button></div>
          <div class="table-wrap"><table class="table"><thead><tr><th>${t("Həftə")}</th><th>${t("Mövzu")}</th><th>${t("Nəticələr")}</th><th>${t("Fəaliyyət")}</th><th></th></tr></thead><tbody>
          ${s.plan.map((w, i) => html`<tr><td><input class="input" type="number" min="1" max="30" style="width:70px" data-p-week="${i}" value="${w.week}" aria-label="${t("Həftə")}"></td>
            <td><input class="input" data-p-topic="${i}" value="${w.topic}" aria-label="${t("Mövzu")}"></td>
            <td class="nowrap">${s.outcomes.map((o) => html`<label class="small" style="margin-right:6px"><input type="checkbox" data-p-out="${i}" value="${o.id}" ${w.outcomes.includes(o.id) ? "checked" : ""}> ${o.id}</label>`)}</td>
            <td><input class="input" data-p-act="${i}" value="${w.activity}" aria-label="${t("Fəaliyyət")}"></td>
            <td><button class="btn btn-ghost btn-icon" data-p-del="${i}" aria-label="${t("Sil")}">${ic("x", 14)}</button></td></tr>`)}</tbody></table></div></div>
        <div class="card"><div class="card-h"><h3>${ic("chart", 17)} ${t("Qiymətləndirmə")}</h3><span class="badge ${total === 100 ? "b-green" : "b-red"}" id="asum">${t("Cəmi: {n}", { n: total })}</span></div>
          <div class="table-wrap"><table class="table"><thead><tr><th>${t("Komponent")}</th><th>${t("Növ")}</th><th>${t("Çəki")}</th><th></th></tr></thead><tbody>
          ${s.assessment.map((a, i) => html`<tr><td><input class="input" data-a-name="${i}" value="${a.name}" aria-label="${t("Komponent")}"></td>
            <td><select class="select" data-a-kind="${i}" aria-label="${t("Növ")}">${opts(KIND(), a.kind)}</select></td>
            <td><input class="input" type="number" min="0.5" max="100" step="0.5" style="width:76px" data-a-weight="${i}" value="${a.weight}" aria-label="${t("Çəki")}"></td>
            <td><button class="btn btn-ghost btn-icon" data-a-del="${i}" aria-label="${t("Sil")}">${ic("x", 14)}</button></td></tr>`)}</tbody></table></div>
          <div class="card-b stack sm"><button class="btn btn-sm" id="add-a">${ic("plus", 13)} ${t("Komponent əlavə et")}</button>
            <div class="tiny muted">${t("Çəkilərin cəmi 100 olmalıdır; imtahanın çəkisini universitet təyin edir.")}</div></div></div>
        <div class="card"><div class="card-h"><h3>${ic("shield", 17)} ${t("Qaydalar")}</h3></div><div class="card-b stack sm">
          <div class="field"><label class="label" for="r-lim">${t("Davamiyyət həddi, %")}</label><input class="input" id="r-lim" type="number" min="1" max="${st.limit_percent}" step="0.5" data-r="attendance_limit" value="${s.rules.attendance_limit}">
            <div class="tiny muted">${t("Universitetin həddi {n}%: sillabus onu yalnız aşağı sala bilər.", { n: st.limit_percent })}</div></div>
          <div class="field"><label class="label" for="r-late">${t("Gecikmiş işlər")}</label><textarea class="textarea" id="r-late" data-r="late_policy" style="min-height:60px">${s.rules.late_policy}</textarea></div>
          <div class="field"><label class="label" for="r-ai">${t("Süni intellektdən istifadə")}</label><select class="select" id="r-ai" data-r="ai_policy">${opts(AI(), s.rules.ai_policy)}</select>
            <textarea class="textarea mt-sm" data-r="ai_note" style="min-height:50px" aria-label="${t("AI siyasətinin izahı")}">${s.rules.ai_note}</textarea></div></div></div>
      </div><div class="stack">
        <div class="card"><div class="card-h"><h3>${ic("clock", 17)} ${t("İş yükü, saat")}</h3></div><div class="card-b stack sm">
          ${WORK().map(([k, l]) => html`<div class="row between"><label class="small" for="w-${k}">${l}</label><span class="row">
            ${imported[k] != null ? html`<span class="tiny ${+imported[k] !== +s.workload[k] ? "badge b-amber" : "muted"}">${t("Forma №3: {n}", { n: imported[k] })}</span>` : ""}
            <input class="input" id="w-${k}" type="number" min="0" step="0.5" style="width:90px" data-w="${k}" value="${s.workload[k]}"></span></div>`)}
          ${Object.keys(imported).length ? html`<div class="tiny muted">${t("Forma №3-dən fərqlənən saat təsdiqdə kafedra müdirinə fərq kimi göstərilir.")}</div>` : html`<div class="tiny muted">${t("Bu fənn üçün Forma №3 idxal olunmayıb.")}</div>`}</div></div>
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
            ${st.can_edit ? html`<button class="btn btn-sm" data-from="${v.id}">${t("Bundan davam et")}</button>` : ""}</div>`) : html`<span class="small muted">${t("Hələ versiya yoxdur")}</span>`}</div></div>
      </div></div>`}`);
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
    } else return;
    dirty = true;
  });
  const edit = (fn) => { fn(); dirty = true; draw(); };
  on(el, "click", "#add-o", () => edit(() => s.outcomes.push({ id: nextId(s.outcomes), text: "", bloom: "apply" })));
  on(el, "click", "[data-o-del]", (e, b) => edit(() => {
    const [gone] = s.outcomes.splice(+b.dataset.oDel, 1);
    s.plan.forEach((w) => { w.outcomes = w.outcomes.filter((x) => x !== gone.id); });
  }));
  on(el, "click", "#add-w", () => edit(() => s.plan.push({ week: Math.max(0, ...s.plan.map((w) => w.week)) + 1, topic: "", outcomes: [], activity: "" })));
  on(el, "click", "[data-p-del]", (e, b) => edit(() => s.plan.splice(+b.dataset.pDel, 1)));
  on(el, "click", "#add-a", () => edit(() => s.assessment.splice(Math.max(0, s.assessment.length - 1), 0, { name: "", kind: "component", weight: 5 })));
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
