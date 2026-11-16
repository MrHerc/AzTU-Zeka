// Zəka Radar — early warning for teachers, the dean's office and leadership; support plans for students.
// Every number on these pages is explained: drivers, evidence and the material a plan step cites.
import { api, html, raw, mount, on, ic, icon, toast, modal, confirmBox, route, go, S, pageHead, fmtDate, fmtDayMonth, ago, ring, progress, loading,
  skelLines, failed, empty, infoTip, lineChart, cnt, num, md, avatar, registerTour, t, LANG, $, $$, esc } from "./core.js";
import { refreshBadges } from "./shell.js";

const LV = { high: ["b-red", "var(--rd-high)", "#d64045"], watch: ["b-amber", "var(--rd-watch)", "#c27803"], ok: ["b-green", "var(--rd-ok)", "#0e9f6e"] };
const LV_LABEL = { high: t("Yüksək risk"), watch: t("Diqqət"), ok: t("Normal") };
const DRV = { attendance: ["calcheck", "var(--rd-att)"], assessment: ["target", "var(--rd-ass)"], concept: ["layers", "var(--rd-con)"], engagement: ["activity", "var(--rd-eng)"] };
const DRV_LABEL = { attendance: t("Davamiyyət"), assessment: t("Qiymətləndirmə"), concept: t("Anlayış boşluğu"), engagement: t("Aktivlik") };
const KIND = { plan: [t("Fərdi dəstək planı"), "target"], consult: [t("Konsultasiya"), "users"], nudge: [t("Xatırlatma"), "bell"], office: [t("Dekanlığa yönəlt"), "inbox"] };
const STEP_IC = { read: "book", practice: "quiz", attend: "calcheck", consult: "users", tutor: "sparkles", quiz: "quiz" };
const STEP_CTA = { read: t("Tutorda izah al"), practice: t("Məşqə başla"), attend: t("Davamiyyətə bax"), consult: t("Fənn səhifəsi"), tutor: t("Tutoru aç"), quiz: t("Testlərə bax") };
const ATT_LABEL = { present: t("İştirak edib"), late: t("Gecikib"), absent: t("Qayıb"), excused: t("Üzrlü") };
const CONF = { high: t("yüksək"), medium: t("orta"), low: t("aşağı") };

const levelBadge = (lv) => html`<span class="badge ${LV[lv][0]}">${LV_LABEL[lv]}</span>`;
const score = (s, lv) => html`<span class="rd-score ${lv}">${num(s, 0)}<small> / 100</small></span>`;
export const driverBar = (drivers, lg = false) => html`<div class="rd-bar ${lg ? "lg" : ""}" role="img" aria-label="${drivers.map((d) => `${DRV_LABEL[d.key]}: ${num(d.points, 0)}`).join(", ")}">${
  ["attendance", "assessment", "concept", "engagement"].map((k) => { const d = drivers.find((x) => x.key === k); return d && d.points > 0
    ? html`<span class="rd-${k}" style="width:${d.points}%" title="${DRV_LABEL[k]}: ${num(d.points, 1)}"></span>` : ""; })}</div>`;
const legend = () => html`<div class="rd-legend">${Object.keys(DRV).map((k) => html`<span class="rd-key"><i class="rd-${k}"></i>${DRV_LABEL[k]}</span>`)}</div>`;
const crumbs = (...c) => [[t("Zəka Radar"), "/radar"], ...c];
const back = () => (S.user.role === "teacher" ? "/teacher" : S.user.role === "office" ? "/office" : S.user.role === "leader" ? "/leader" : "/admin");

// ---------------------------------------------------------------- source viewer (lecture passages cited by a plan)
export async function openSource(id) {
  const m = modal({ title: t("Mənbə"), size: "lg", body: html`${skelLines(5)}` });
  const box = m.el.querySelector(".modal-b");
  try {
    const s = await api.get(`/api/source/chunk/${id}`);
    mount(box, html`<div class="small muted">${ic("file", 13)} ${s.material}</div><h3 class="src-heading">${s.heading}</h3>${md(s.text)}
      ${LANG !== "az" ? html`<div class="tiny muted mt">${ic("info", 12)} ${t("Sitat orijinal (tədris) dilində göstərilir.")}</div>` : ""}`);
  } catch (err) { mount(box, failed(err.message)); }
}
on(document, "click", "[data-src]", (e, b) => { e.preventDefault(); e.stopPropagation(); openSource(+b.dataset.src); });

// ---------------------------------------------------------------- plan steps (shared: teacher preview, plan history, student page)
function planSteps(plan, { interactive = false, links = false } = {}) {
  return html`<div class="rd-steps">${plan.steps.map((s, i) => html`<div class="rd-step ${s.done ? "done" : ""}">
    ${interactive ? html`<button class="rd-check" data-step="${i}" data-done="${s.done ? "0" : "1"}" aria-pressed="${!!s.done}" aria-label="${s.done ? t("Yerinə yetirilməyib kimi qeyd et") : t("Yerinə yetirdim")}">${ic("check", 15)}</button>`
      : html`<span class="rd-check" aria-hidden="true">${ic("check", 15)}</span>`}
    <div class="grow"><div class="rd-step-t">${ic(STEP_IC[s.kind] || "target", 15)} ${s.title}
      ${s.done ? html`<span class="badge b-green">${s.auto ? t("Avtomatik qeyd olundu") : t("Yerinə yetirilib")}</span>` : ""}</div>
      <div class="rd-step-x">${s.text}</div>
      ${s.cites && s.cites.length ? html`<div class="rd-cites">${s.cites.map((c) => html`<button class="rd-cite" data-src="${c.id}" title="${c.snippet}">${ic("file", 12)}<span>${c.material} · ${c.heading}</span></button>`)}</div>` : ""}
      ${s.done && s.done_at ? html`<div class="tiny muted mt-sm">${ago(s.done_at)}</div>` : ""}
      ${links && s.link && !s.done ? html`<div class="rd-step-a"><button class="btn btn-sm ${s.kind === "read" || s.kind === "practice" || s.kind === "tutor" ? "btn-ai" : ""}" data-go="${s.link}">${ic(STEP_IC[s.kind] || "arrow", 14)} ${STEP_CTA[s.kind] || t("Aç")}</button></div>` : ""}
    </div></div>`)}</div>`;
}

// ---------------------------------------------------------------- dashboard
route("/radar", async (el, p, q) => {
  mount(el, loading());
  let d;
  try { d = await api.get("/api/radar" + (q.course ? `?course=${encodeURIComponent(q.course)}` : "")); } catch (err) { return mount(el, failed(err.message)); }
  const sc = d.scope, sel = sc.courses.find((c) => c.id === sc.selected);
  const k = d.counts, im = d.impact;
  const scopeLabel = sel ? `${sel.code} · ${sel.name}` : t("Bütün fənlər");
  const courseSelect = sc.courses.length > 1 ? html`<select class="select rd-course-sel" id="rd-course" aria-label="${t("Fənn")}">
      ${S.user.role !== "teacher" ? html`<option value="">${t("Bütün fənlər")}</option>` : ""}
      ${sc.courses.map((c) => html`<option value="${c.id}" ${c.id === sc.selected ? "selected" : ""}>${c.code} · ${c.name}</option>`)}</select>` : "";
  const labels = d.trend.map((x) => fmtDayMonth(x.week_start));
  mount(el, html`${pageHead(t("Zəka Radar"), t("Erkən xəbərdarlıq · {scope} · {n} tələbə", { scope: scopeLabel, n: k.students }),
      html`<span class="demo-banner">${t("Pilot · sintetik məlumat")}</span>${courseSelect}`, [[t("Əsas"), back()], [t("Zəka Radar")]],
      { info: t("Risk balı platformanın artıq topladığı məlumatlardan hesablanır: davamiyyət, cari ballar, testlər və AI tutorla iş. Hər balın səbəbləri göstərilir. Qərarı həmişə insan verir.") })}
    <div class="grid g-4" id="rd-kpis">
      <div class="card rd-kpi high"><span class="stat-ic ic-red">${ic("alert", 21)}</span><div><div class="stat-v">${cnt(k.high)}</div><div class="stat-l">${t("Yüksək risk")}</div></div></div>
      <div class="card rd-kpi watch"><span class="stat-ic ic-amber">${ic("eye", 21)}</span><div><div class="stat-v">${cnt(k.watch)}</div><div class="stat-l">${t("Diqqət siyahısı")}</div></div></div>
      <div class="card rd-kpi plan"><span class="stat-ic ic-violet">${ic("target", 21)}</span><div><div class="stat-v">${cnt(im.open)}</div><div class="stat-l">${t("Açıq dəstək planı")} · ${t("{n} tamamlanıb", { n: im.completed })}</div></div></div>
      <div class="card rd-kpi good"><span class="stat-ic ic-green">${ic("trend", 21)}</span><div><div class="stat-v">${im.measured ? html`${im.improved}/${im.measured}` : "—"}</div>
        <div class="stat-l">${t("Plandan sonra riski azalanlar")}${im.avg_delta != null ? html` · <b class="rd-delta down">${num(im.avg_delta, 1)}</b> ${t("bal")}` : ""}</div></div></div>
    </div>
    <div class="grid g-12 mt">
        <div class="card" id="rd-trend"><div class="card-h"><h3>${ic("chart", 17)} ${t("Həftəlik dinamika")}</h3>${infoTip(t("Hər həftə üçün risk həmin həftənin məlumatları ilə yenidən hesablanır. Semestrin əvvəlində məlumat az olduğu üçün risk aşağı görünür."))}</div>
          <div class="card-b">${lineChart({ labels, series: [{ name: t("Yüksək risk"), values: d.trend.map((x) => x.high), color: LV.high[2] }, { name: t("Diqqət"), values: d.trend.map((x) => x.watch), color: LV.watch[2] }],
            label: t("Həftəlik risk dinamikası"), height: 210 })}
            <div class="row small mt-sm"><span class="dot" style="background:${LV.high[2]};box-shadow:none"></span>${t("Yüksək risk")}<span class="dot" style="background:${LV.watch[2]};box-shadow:none;margin-left:8px"></span>${t("Diqqət")}</div></div></div>
        <div class="card" id="rd-impact"><div class="card-h"><h3>${ic("trend", 17)} ${t("Planların təsiri")}</h3>${infoTip(t("Plan göndərilən andakı risk balı ilə indiki bal müqayisə olunur. Ən azı 7 gün əvvəl göndərilmiş planlar ölçülür."))}</div>
          <div class="card-b list">${im.items.length ? im.items.slice(0, 6).map((x) => html`<div class="list-item click" data-go="/radar/student/${x.student_id}?course=${x.course_id}">
            ${avatar(x.student, "#64748b", "sm")}<div class="grow"><b class="small">${x.student}</b><div class="tiny muted">${x.code} · ${x.status === "completed" ? t("Tamamlanıb") : t("{d}/{n} addım", { d: x.progress.done, n: x.progress.total })} · ${ago(x.created_at)}</div></div>
            ${x.fresh ? html`<span class="badge b-blue" title="${t("Nəticə plan göndərildikdən 7 gün sonra ölçülür.")}">${ic("clock", 11)} ${t("Ölçülür")}</span>`
              : html`<span class="small nowrap">${num(x.risk_before, 0)} → <b>${num(x.risk_now, 0)}</b></span><span class="rd-delta ${x.delta <= 0 ? "down" : "up"} small">${x.delta > 0 ? "+" : ""}${num(x.delta, 0)}</span>`}</div>`)
            : empty("target", t("Hələ plan göndərilməyib"), t("Riskli tələbənin profilindən bir kliklə dəstək planı hazırlayın."))}</div></div>
    </div>
    <div class="grid g-12 mt">
      <div class="card" id="rd-list">
        <div class="card-h"><h3>${ic("activity", 17)} ${t("Diqqət tələb edən tələbələr")}</h3>${legend()}</div>
        <div class="rd-tools"><div class="seg" role="tablist" id="rd-filter">
            <button data-f="risk" class="active">${t("Riskli")} <span class="count-pill">${k.high + k.watch}</span></button>
            <button data-f="high">${t("Yüksək")} <span class="count-pill">${k.high}</span></button>
            <button data-f="plan">${t("Plan göndərilib")} <span class="count-pill">${d.rows.filter((r) => r.intervention).length}</span></button>
            <button data-f="all">${t("Hamısı")} <span class="count-pill">${k.students}</span></button></div>
          <input class="input input-sm rd-search" id="rd-q" type="search" placeholder="${t("Ad və ya qrup…")}" aria-label="${t("Tələbə axtar")}"></div>
        <div id="rd-rows"></div></div>
      <div class="stack">
        <div class="card" id="rd-gaps"><div class="card-h"><h3>${ic("layers", 17)} ${t("Qrup üzrə anlayış boşluqları")}</h3>${infoTip(t("Bir neçə riskli tələbənin eyni anda çətinlik çəkdiyi mövzular. Bu, tələbəyə deyil, dərsə aid siqnaldır: mövzunu növbəti dərsdə qısa təkrarlamaq tövsiyə olunur."))}</div>
          <div class="card-b list">${d.gaps.length ? d.gaps.map((g) => html`<div class="list-item"><span class="stat-ic ic-violet" style="width:34px;height:34px">${ic("layers", 16)}</span>
            <div class="grow"><b class="small">${g.topic}</b><div class="tiny muted">${g.code} · ${t("{n} riskli tələbə", { n: g.students })}${g.material ? html` · ${g.material}` : ""}</div></div>
            ${g.chunk_id ? html`<button class="btn btn-sm" data-src="${g.chunk_id}">${ic("eye", 13)} ${t("Mənbə")}</button>` : ""}</div>`)
            : empty("check", t("Qrup üzrə boşluq yoxdur"), t("Riskli tələbələr arasında ortaq çətin mövzu tapılmadı."))}</div></div>
      </div>
    </div>
    <div class="card mt" id="rd-model"><div class="card-h"><h3>${ic("shield", 17)} ${t("Model necə işləyir")}</h3><span class="badge b-gray">${t("Yüksək risk ≥ {h} · Diqqət ≥ {w}", { h: d.model.levels.high, w: d.model.levels.watch })}</span></div>
      <div class="card-b"><div class="rd-model">${Object.entries(d.model.weights).map(([key, w]) => html`<div><b><span class="rd-key"><i class="rd-${key}"></i></span>${DRV_LABEL[key]}</b><div class="w">${w}</div><div class="tiny muted">${{
          attendance: t("Üzrsüz qayıblar və ardıcıl buraxılan dərslər. Üzrlü qayıblar sayılmır."),
          assessment: t("Cari ballar və test nəticələri, nəticənin azalması."),
          concept: t("Tutorda tez-tez soruşulan və səhv cavablandırılan mövzular (son 4 həftə)."),
          engagement: t("Tutordan və testlərdən uzaqlaşma — qrupun mediyanı ilə müqayisədə."),
        }[key]}</div></div>`)}</div>
        <ul class="rd-principles">
          <li>${ic("check", 15)} <span>${t("İzah olunan: hər bal səbəbləri və sübutları ilə göstərilir.")}</span></li>
          <li>${ic("check", 15)} <span>${t("Ədalətli: üzrlü qayıblar heç vaxt sayılmır; az məlumatla qərar verilmir.")}</span></li>
          <li>${ic("check", 15)} <span>${t("Məxfi: tutor söhbətlərinin mətni oxunmur — yalnız mövzu və say.")}</span></li>
          <li>${ic("check", 15)} <span>${t("İnsan nəzarəti: plan yalnız müəllim təsdiqləyib göndərəndə tələbəyə çatır; tələbə risk balını görmür.")}</span></li>
        </ul></div></div>`);

  const draw = () => {
    const f = $("#rd-filter .active", el).dataset.f, qq = ($("#rd-q", el).value || "").toLowerCase().trim();
    let list = d.rows.filter((r) => (f === "all" || (f === "risk" && r.level !== "ok") || (f === "high" && r.level === "high") || (f === "plan" && r.intervention)));
    if (qq) list = list.filter((r) => `${r.name} ${r.group || ""}`.toLowerCase().includes(qq));
    const box = $("#rd-rows", el);
    if (!list.length) { mount(box, html`<div class="card-b">${empty("check", t("Bu filtrə uyğun tələbə yoxdur"), t("Filtri dəyişin və ya axtarışı təmizləyin."))}</div>`); return; }
    mount(box, html`<div class="table-wrap"><table class="table rd-table"><thead><tr><th>${t("Tələbə")}</th><th>${t("Risk")}</th><th>${t("Niyə?")}</th><th>${t("Addım")}</th></tr></thead><tbody>
      ${list.slice(0, 80).map((r) => html`<tr class="click" data-sid="${r.id}" data-cid="${r.course_id}">
        <td><div class="rd-who">${avatar(r.name, r.color)}<div><b class="small">${r.name}</b><div class="tiny muted">${r.group || "—"}${!sel ? html` · ${r.courses[0].code}` : ""}${r.at_risk_courses > 1 ? html` · ${t("{n} fənn üzrə", { n: r.at_risk_courses })}` : ""}</div></div></div></td>
        <td><div class="rd-risk"><div class="row between">${score(r.score, r.level)}${levelBadge(r.level)}</div>${driverBar(r.drivers)}</div></td>
        <td><div class="rd-why">${r.why || html`<span class="muted">${t("Siqnal yoxdur")}</span>`}</div>
          ${r.gaps.length ? html`<div class="rd-gaps">${r.gaps.map((g) => html`<span class="rd-gap">${g.topic}</span>`)}</div>` : ""}</td>
        <td class="nowrap">${r.intervention ? html`<span class="badge b-violet">${ic("target", 11)} ${t("Plan · {d}/{n}", { d: r.intervention.progress.done, n: r.intervention.progress.total })}</span>`
          : r.recommendation && sc.can_act ? html`<button class="btn btn-sm btn-ai" data-plan="${r.id}" data-cid="${r.course_id}">${ic("wand", 13)} ${t("Plan hazırla")}</button>`
          : html`<button class="btn btn-sm">${t("Bax")}</button>`}</td></tr>`)}</tbody></table></div>
      ${list.length > 80 ? html`<div class="tiny muted center" style="padding:10px">${t("İlk 80 tələbə göstərilir. Axtarışdan istifadə edin.")}</div>` : ""}`);
  };
  draw();
  on(el, "click", "#rd-filter [data-f]", (e, b) => { $$("#rd-filter [data-f]", el).forEach((x) => x.classList.toggle("active", x === b)); draw(); });
  $("#rd-q", el).addEventListener("input", draw);
  on(el, "click", "tr[data-sid]", (e, tr) => {
    const pb = e.target.closest("[data-plan]");
    go(`/radar/student/${tr.dataset.sid}?course=${tr.dataset.cid}${pb ? "&plan=1" : ""}`);
  });
  const cs = $("#rd-course", el);
  if (cs) cs.addEventListener("change", () => go(cs.value ? `/radar?course=${cs.value}` : "/radar"));
});

// ---------------------------------------------------------------- explainable student profile
route("/radar/student/:id", async (el, p, q) => {
  mount(el, loading());
  let d;
  try { d = await api.get(`/api/radar/student/${p.id}${q.course ? `?course=${encodeURIComponent(q.course)}` : ""}`); } catch (err) { return mount(el, failed(err.message)); }
  const pr = d.profile, st = d.student, co = d.course, lv = pr.level;
  const open = d.interventions.find((x) => x.status === "open" && x.course.id === co.id);
  const hist = d.history;
  const asm = pr.stats.assessment, att = pr.stats.attendance;
  mount(el, html`${pageHead(st.name, `${st.group || "—"} · ${co.code} ${co.name} · ${co.teacher}`,
      d.can_act && !open ? html`<button class="btn btn-ai" id="rd-make">${ic("wand", 16)} ${t("AI dəstək planı hazırla")}</button>` : "",
      crumbs([st.name]), { info: t("Tələbənin tutor söhbətlərinin mətni göstərilmir — yalnız mövzu və say. Tələbə bu səhifəni və risk balını görmür.") })}
    ${d.courses.length > 1 ? html`<div class="chips mb">${d.courses.map((c) => html`<button class="chip ${c.id === co.id ? "on" : ""}" data-go="/radar/student/${st.id}?course=${c.id}">
      <span class="dot" style="background:${LV[c.level][2]};box-shadow:none"></span>${c.code} · ${num(c.score, 0)}</button>`)}</div>` : ""}
    <div class="grid g-12">
      <div class="stack">
        <div class="card" id="rd-why"><div class="card-b"><div class="rd-head">
            <div class="rd-gauge">${ring(pr.score, 112, LV[lv][2], num(pr.score, 0), 10)}</div>
            <div class="grow"><div class="row wrap">${levelBadge(lv)}<span class="badge b-gray">${t("Etibarlılıq: {c}", { c: CONF[pr.confidence] })}</span>
              ${d.cohort.rank ? html`<span class="badge b-navy">${t("{n} tələbə arasında {r}-ci", { n: d.cohort.students, r: d.cohort.rank })}</span>` : ""}</div>
              <h3 class="mt-sm">${t("Niyə bu bal?")}</h3><div class="small muted">${t("Bal dörd siqnalın cəmidir. Hər siqnalın altında onu yaradan faktlar var.")}</div>
              <div class="mt-sm">${driverBar(pr.drivers, true)}</div></div></div>
          <div class="divider"></div>
          ${pr.drivers.map((x) => html`<div class="rd-driver"><div class="rd-driver-top"><span class="rd-driver-ic" style="background:${DRV[x.key][1]}">${ic(DRV[x.key][0], 15)}</span>
              <b class="small">${DRV_LABEL[x.key]}</b><span class="pts">${num(x.points, 1)} <small>/ ${x.weight}</small></span></div>
            <div class="rd-meter"><span style="width:${(100 * x.points) / x.weight}%;background:${DRV[x.key][1]}"></span></div>
            ${x.evidence.length ? html`<ul class="rd-ev">${x.evidence.map((ev) => html`<li>${ev}</li>`)}</ul>` : html`<ul class="rd-ev"><li class="muted">${t("Bu siqnal üzrə problem yoxdur")}</li></ul>`}</div>`)}
        </div></div>
        <div class="card"><div class="card-h"><h3>${ic("trend", 17)} ${t("Riskin dinamikası")}</h3><span class="small muted">${t("həftəlik")}</span></div>
          <div class="card-b">${lineChart({ labels: hist.map((x) => fmtDayMonth(x.as_of)), series: [{ name: t("Risk balı"), values: hist.map((x) => x.score), color: LV[lv][2] }],
            target: { value: 50, label: t("Yüksək risk həddi") }, max: 100, height: 200, label: t("Riskin dinamikası") })}</div></div>
        <div class="grid g-2">
          <div class="card"><div class="card-h"><h3>${ic("calcheck", 17)} ${t("Son dərslər")}</h3></div><div class="card-b">
            <div class="rd-dots">${d.lessons.map((x) => html`<span class="rd-dot ${x.status}" title="${fmtDate(x.day)} ${x.start} · ${ATT_LABEL[x.status] || x.status}${x.topic ? " · " + x.topic : ""}">${x.status === "absent" ? "✕" : x.status === "excused" ? "+" : x.status === "late" ? "!" : ""}</span>`)}</div>
            <div class="rd-legend mt-sm">${["present", "late", "absent", "excused"].map((s) => html`<span class="rd-key"><i class="rd-dot ${s}" style="width:10px;height:10px;border-radius:3px"></i>${ATT_LABEL[s]}</span>`)}</div>
            ${att.missed_topics.length ? html`<div class="small mt">${t("Buraxılmış mövzular")}: <b>${att.missed_topics.join(", ")}</b></div>` : ""}</div></div>
          <div class="card"><div class="card-h"><h3>${ic("quiz", 17)} ${t("Testlər və ballar")}</h3></div><div class="card-b">
            ${asm.series.length ? asm.series.map((x) => html`<div class="bar-row"><span class="ellipsis small" title="${x.title}">${x.title}</span>${progress(x.percent, x.percent < 50 ? "coral" : "green")}<b class="right small">${x.percent}%</b></div>`)
              : html`<div class="small muted">${t("Test cəhdi yoxdur")}</div>`}
            <div class="rd-compare mt">
              <div><b>${att.rate == null ? "—" : att.rate + "%"}</b><span>${t("Davamiyyət")} · ${t("kurs: {n}%", { n: d.cohort.attendance ?? "—" })}</span></div>
              <div><b>${asm.grade_pct == null ? "—" : asm.grade_pct + "%"}</b><span>${t("Cari ballar")} · ${t("kurs: {n}%", { n: d.cohort.grades ?? "—" })}</span></div>
              <div><b>${num(pr.stats.engagement.asks_14d)}</b><span>${t("Tutor sualı (14 gün)")}</span></div></div></div></div>
        </div>
      </div>
      <div class="stack">
        ${pr.recommendation ? html`<div class="card rd-rec" id="rd-rec"><div class="card-h"><h3>${ic("sparkles", 17)} ${t("Tövsiyə olunan addım")}</h3><span class="badge b-violet">${KIND[pr.recommendation.kind][0]}</span></div>
          <div class="card-b"><p class="small" style="margin:0">${pr.recommendation.text}</p>
          ${pr.recommendation.cc_office ? html`<div class="notice warn mt">${ic("inbox", 15)}<div class="small">${t("Davamiyyət siqnalı güclüdür — plan göndərildikdə dekanlıq da xəbərdar ediləcək.")}</div></div>` : ""}
          ${d.can_act && !open ? html`<button class="btn btn-ai btn-block mt" id="rd-make2">${ic("wand", 16)} ${t("Planı hazırla və bax")}</button>` : ""}
          ${open ? html`<div class="notice ok mt">${ic("check", 15)}<div class="small">${t("Bu fənn üzrə dəstək planı artıq göndərilib.")}</div></div>` : ""}</div></div>`
          : html`<div class="card pad">${empty("check", t("Müdaxilə tələb olunmur"), t("Risk normal həddədir. Radar vəziyyəti izləməyə davam edir."))}</div>`}
        ${pr.gaps.filter((g) => g.score >= 2).length ? html`<div class="card"><div class="card-h"><h3>${ic("layers", 17)} ${t("Anlayış boşluqları")}</h3>${infoTip(t("Son 4 həftədə tutorda tez-tez soruşulan və məşqdə və ya testdə səhv cavablandırılan mövzular."))}</div>
          <div class="card-b list">${pr.gaps.filter((g) => g.score >= 2).map((g) => html`<div class="list-item"><span class="rd-gap">${g.topic}</span><span class="grow"></span>
            <span class="tiny muted nowrap">${t("{a} sual · {w} səhv", { a: g.asks, w: g.wrong })}</span></div>`)}</div></div>` : ""}
        <div class="card" id="rd-plans"><div class="card-h"><h3>${ic("target", 17)} ${t("Dəstək planları")}</h3><span class="small muted">${d.interventions.length}</span></div>
          <div class="card-b">${d.interventions.length ? d.interventions.map((x) => html`<div class="rd-iv">
            <div class="row between wrap"><b class="small">${x.plan.title}</b>${x.status === "open" ? html`<span class="badge b-violet">${t("Açıq")}</span>` : x.status === "completed" ? html`<span class="badge b-green">${t("Tamamlanıb")}</span>` : html`<span class="badge b-gray">${x.status}</span>`}</div>
            <div class="tiny muted">${x.author} · ${fmtDate(x.created_at)} · ${t("risk o zaman: {s}", { s: num(x.risk_before, 0) })}</div>
            <div class="row mt-sm">${progress(x.progress.percent, "green")}<span class="small nowrap">${x.progress.done}/${x.progress.total}</span></div>
            <details class="mt-sm"><summary class="small">${t("Addımlar")}</summary><div class="mt-sm">${planSteps(x.plan)}</div></details>
            ${x.status === "open" && d.can_act ? html`<div class="row wrap mt-sm"><button class="btn btn-sm" data-ivs="completed" data-iv="${x.id}">${ic("check", 13)} ${t("Tamamlandı kimi bağla")}</button>
              <button class="btn btn-sm btn-ghost" data-ivs="cancelled" data-iv="${x.id}">${t("Ləğv et")}</button></div>` : ""}</div>`)
            : empty("target", t("Hələ plan yoxdur"), d.can_act ? t("Tövsiyə olunan addımdan plan hazırlayın — tələbə onu bildiriş kimi alacaq.") : t("Müəllim və ya dekanlıq plan göndərdikdə burada görünəcək."))}</div></div>
        <div class="notice ai">${ic("shield", 16)}<div class="small">${t("Bu profil yalnız fənn müəlliminə, dekanlığa və rəhbərliyə görünür. Hər baxış audit jurnalına yazılır.")}</div></div>
      </div></div>`);
  const make = () => composer(d, () => go(`/radar/student/${st.id}?course=${co.id}`));
  $("#rd-make", el)?.addEventListener("click", make);
  $("#rd-make2", el)?.addEventListener("click", make);
  on(el, "click", "[data-ivs]", async (e, b) => {
    const okd = b.dataset.ivs === "completed" || await confirmBox(t("Planı ləğv etmək?"), t("Tələbə planı artıq görməyəcək."), t("Ləğv et"), true);
    if (!okd) return;
    try { await api.post(`/api/interventions/${b.dataset.iv}/status`, { status: b.dataset.ivs }); toast(t("Plan yeniləndi"), "ok"); go(`/radar/student/${st.id}?course=${co.id}&r=${Date.now()}`); }
    catch (err) { toast(err.message, "err"); }
  });
  if (q.plan === "1" && d.can_act && !open) setTimeout(make, 350);
});

function composer(d, onDone) {
  const rec = d.profile.recommendation;
  let kind = (rec && rec.kind) || "plan", preview = null;
  const m = modal({ title: t("Dəstək planı · {name}", { name: d.student.name }), size: "lg", body: html`
      <div class="small muted mb-sm">${t("Plan fənn materiallarına əsaslanır: hər addım mühazirənin konkret hissəsinə və məşq suallarına istinad edir.")}</div>
      <div class="seg" id="pk" role="tablist">${Object.entries(KIND).map(([key, [l, i]]) => html`<button data-k="${key}" class="${key === kind ? "active" : ""}" role="tab">${ic(i, 14)} ${l}${rec && rec.kind === key ? " ★" : ""}</button>`)}</div>
      <div id="pv" class="mt">${skelLines(5)}</div>
      <label class="field mt"><span class="label">${t("Tələbəyə qısa qeyd (istəyə görə)")}</span>
        <textarea class="textarea" id="pn" rows="2" maxlength="600" placeholder="${t("Məsələn: Gəlin bu mövzunu birlikdə bərpa edək. Sualınız olsa, dərsdən sonra yaxınlaşın.")}"></textarea></label>
      <div class="notice ai mt">${ic("shield", 16)}<div class="small">${t("Plan yalnız siz göndərdikdən sonra tələbəyə görünür. Tələbə risk balını və səbəbləri görmür — yalnız dəstək addımlarını.")}</div></div>`,
    actions: [{ label: t("Ləğv et"), cls: "btn-ghost" },
      { html: `${icon("send", 15)} ${esc(t("Tələbəyə göndər"))}`, cls: "btn-ai", onClick: async (w) => {
        const r = await api.post(`/api/radar/student/${d.student.id}/plan`, { course_id: d.course.id, kind, note: w.querySelector("#pn").value });
        toast(t("Plan göndərildi: {name}", { name: d.student.name }), "ok");
        refreshBadges();
        window.dispatchEvent(new CustomEvent("zeka:plan-sent", { detail: { id: r.id, student: d.student.id } }));
        onDone && onDone(r);
      } }] });
  const box = m.el.querySelector("#pv");
  const load = async () => {
    mount(box, skelLines(5));
    try {
      preview = await api.post(`/api/radar/student/${d.student.id}/plan`, { course_id: d.course.id, kind, preview: true });
      mount(box, html`<div class="row between wrap mb-sm"><b>${preview.plan.title}</b><span class="tiny muted">${t("Son tarix: {d}", { d: fmtDate(preview.plan.due_at) })}</span></div>
        ${preview.plan.topics.length ? html`<div class="small mb-sm">${preview.plan.topics_source === "gaps" ? t("Mövzular anlayış boşluqlarından seçilib") : t("Mövzular buraxılmış dərslərdən seçilib")}:
          ${preview.plan.topics.map((x) => html`<span class="rd-gap">${x}</span> `)}</div>` : ""}
        ${planSteps(preview.plan)}`);
    } catch (err) { mount(box, failed(err.message)); }
  };
  on(m.el, "click", "[data-k]", (e, b) => { kind = b.dataset.k; $$("[data-k]", m.el).forEach((x) => x.classList.toggle("active", x === b)); load(); });
  load();
}

// ---------------------------------------------------------------- the student's side
route("/student/plan/:id?", async (el, p) => {
  mount(el, loading());
  const head = pageHead(t("Dəstək planım"), t("Müəlliminizin sizin üçün hazırladığı addımlar."), "", [[t("Əsas"), "/student"], [t("Dəstək planım")]],
    { info: t("Addımlar fəaliyyətinizə görə avtomatik qeyd olunur: tutorda izah istədikdə, məşqdə düzgün cavab verdikdə və dərslərdə iştirak etdikdə.") });
  if (!p.id) {
    let r;
    try { r = await api.get("/api/student/plans"); } catch (err) { return mount(el, failed(err.message)); }
    const it = r.items.find((x) => x.status === "open") || r.items[0];
    if (it) return go(`/student/plan/${it.id}`);
    return mount(el, html`${head}<div class="card">${empty("target", t("Aktiv dəstək planı yoxdur"), t("Müəlliminiz sizin üçün fərdi dəstək planı hazırlasa, burada görünəcək və bildiriş alacaqsınız."), { label: t("AI tutor"), go: "/student/tutor", icon: "sparkles" })}</div>`);
  }
  const draw = async () => {
    let pl;
    try { pl = await api.get(`/api/student/plans/${p.id}`); } catch (err) { return mount(el, failed(err.message)); }
    const pg = pl.progress, plan = pl.plan;
    mount(el, html`${head}
      <div class="grid g-12">
        <div class="stack">
          <div class="card brand-border" id="plan-hero"><div class="card-b rd-plan-hero">${ring(pg.percent, 96, "url(#ringg)", `${pg.done}/${pg.total}`)}
            <div class="grow"><div class="row wrap"><span class="badge b-violet">${ic("target", 11)} ${pl.course.code}</span>
              ${pl.status === "completed" ? html`<span class="badge b-green">${t("Tamamlanıb")}</span>` : html`<span class="badge b-amber">${t("Son tarix: {d}", { d: fmtDate(pl.due_at) })}</span>`}</div>
              <h2 class="mt-sm" style="font-size:20px">${plan.title}</h2>
              <div class="small muted">${t("{author} hazırlayıb · {when}", { author: pl.author, when: fmtDate(pl.created_at) })}</div></div></div></div>
          ${pl.note ? html`<div class="rd-quote">${ic("message", 14)} ${pl.note}<div class="tiny muted mt-sm">— ${pl.author}</div></div>` : ""}
          ${pl.status === "completed" ? html`<div class="notice ok">${ic("award", 18)}<div><b>${t("Əla nəticə!")}</b> ${t("Planın bütün addımlarını yerinə yetirdiniz. Müəlliminiz xəbərdar edildi.")}</div></div>` : ""}
          <div class="card" id="plan-steps"><div class="card-h"><h3>${ic("list", 17)} ${t("Addımlar")}</h3><span class="small muted">${t("{d} / {n} yerinə yetirilib", { d: pg.done, n: pg.total })}</span></div>
            <div class="card-b">${planSteps(plan, { interactive: pl.status === "open", links: pl.status === "open" })}</div></div>
        </div>
        <div class="stack">
          <div class="card"><div class="card-h"><h3>${ic("help", 17)} ${t("Bu plan nədir?")}</h3></div><div class="card-b stack small">
            <div>${t("Bu, qiymət və ya cəza deyil. Müəlliminiz mövzunu daha yaxşı mənimsəməniz üçün qısa addımlar seçib.")}</div>
            <div>${ic("sparkles", 14)} ${t("Mövzu addımları tutorda açılır — cavablar müəllimin mühazirələrinə əsaslanır.")}</div>
            <div>${ic("check", 14)} ${t("Tutorda izah istədikdə və məşqdə düzgün cavab verdikdə addım özü qeyd olunur.")}</div>
            <div>${ic("users", 14)} ${t("Konsultasiyaya gəlmək üçün dərsdən sonra müəlliminizə yaxınlaşın.")}</div></div></div>
          <div class="card pad"><div class="row"><span class="stat-ic ic-navy">${ic("message", 20)}</span><div class="grow"><b>${t("Sualınız var?")}</b>
            <div class="small muted">${t("Tutordan soruşun və ya sualı anonim olaraq müəllimə göndərin.")}</div></div>
            <button class="btn btn-sm" data-go="/student/tutor/${pl.course.id}">${t("Tutor")}</button></div></div>
        </div></div>`);
  };
  await draw();
  on(el, "click", "[data-step]", async (e, b) => {
    b.disabled = true;
    try { await api.post(`/api/student/plans/${p.id}/steps`, { index: +b.dataset.step, done: b.dataset.done === "1" }); refreshBadges(); await draw(); }
    catch (err) { toast(err.message, "err"); b.disabled = false; }
  });
});

// ---------------------------------------------------------------- cards on other dashboards
export async function studentPlanCard(box) {
  if (!box) return;
  let r;
  try { r = await api.get("/api/student/plans"); } catch { box.remove(); return; }
  const it = r.items.find((x) => x.status === "open");
  if (!it) { box.remove(); return; }
  const next = it.plan.steps.find((s) => !s.done);
  mount(box, html`<div class="card brand-border mt" id="plan-card"><div class="card-b row wrap">${ring(it.progress.percent, 64, "url(#ringg)", `${it.progress.done}/${it.progress.total}`, 7)}
    <div class="grow"><b>${t("Sizin üçün dəstək planı hazırlanıb")}</b><div class="small muted">${it.course.name} · ${it.author}</div>
      ${next ? html`<div class="small mt-sm">${t("Növbəti addım")}: <b>${next.title}</b></div>` : ""}</div>
    <button class="btn btn-ai" data-go="/student/plan/${it.id}">${ic("target", 15)} ${t("Plana bax")}</button></div></div>`);
}

export async function radarTeacherAlert(box) {
  if (!box) return;
  let d;
  try { d = await api.get("/api/radar"); } catch { box.remove(); return; }
  const risky = d.rows.filter((r) => r.level !== "ok");
  if (!risky.length) { box.remove(); return; }
  mount(box, html`<div class="card mt" id="radar-alert" style="border-left:4px solid var(--rd-high)"><div class="card-b rd-alert">
    <span class="stat-ic ic-red">${ic("activity", 21)}</span>
    <div class="grow"><b>${t("Zəka Radar: {h} tələbə yüksək risk, {w} tələbə diqqət siyahısında", { h: d.counts.high, w: d.counts.watch })}</b>
      <div class="rd-names mt-sm">${risky.slice(0, 3).map((r) => html`<button class="chip" data-go="/radar/student/${r.id}?course=${r.course_id}"><span class="dot" style="background:${LV[r.level][2]};box-shadow:none"></span>${r.name} · ${num(r.score, 0)}</button>`)}</div></div>
    <button class="btn btn-primary" data-go="/radar">${ic("activity", 15)} ${t("Radarı aç")}</button></div></div>`);
}

export async function radarLeaderCard(box) {
  if (!box) return;
  let d;
  try { d = await api.get("/api/radar"); } catch { box.remove(); return; }
  const k = d.counts, im = d.impact;
  mount(box, html`<div class="card mt" id="leader-radar"><div class="card-h"><h3>${ic("activity", 17)} ${t("Zəka Radar · erkən xəbərdarlıq")}</h3><a class="small" href="#/radar">${t("Radarı aç")} ${ic("arrow", 13)}</a></div>
    <div class="card-b grid g-12"><div>${lineChart({ labels: d.trend.map((x) => fmtDayMonth(x.week_start)), series: [{ name: t("Yüksək risk"), values: d.trend.map((x) => x.high), color: LV.high[2] }, { name: t("Diqqət"), values: d.trend.map((x) => x.watch), color: LV.watch[2] }], height: 170, label: t("Həftəlik risk dinamikası") })}</div>
      <div class="stack sm">
        <div class="row between"><span class="small muted">${t("Yüksək risk")}</span><b class="rd-score high">${k.high}</b></div>
        <div class="row between"><span class="small muted">${t("Diqqət siyahısı")}</span><b class="rd-score watch">${k.watch}</b></div>
        <div class="row between"><span class="small muted">${t("Plandan sonra riski azalanlar")}</span><b>${im.measured ? `${im.improved}/${im.measured}` : "—"}</b></div>
        <div class="row between"><span class="small muted">${t("Orta dəyişmə")}</span><b class="rd-delta down">${im.avg_delta == null ? "—" : num(im.avg_delta, 1)}</b></div>
        <div class="divider"></div>
        ${d.course_counts.filter((c) => c.high || c.watch).sort((a, b) => b.high * 3 + b.watch - (a.high * 3 + a.watch)).slice(0, 4).map((c) => html`<div class="row between small">
          <span class="row"><span class="dot" style="background:${c.color};box-shadow:none"></span>${c.code}</span><span><b style="color:var(--rd-high)">${c.high}</b> · <span style="color:var(--rd-watch)">${c.watch}</span></span></div>`)}</div></div></div>`);
}

// ---------------------------------------------------------------- page guides
registerTour("radar", { route: "/radar", roles: ["teacher", "office", "leader", "admin"], title: t("Zəka Radar"), group: t("Tədris"), icon: "activity", steps: [
  { sel: "#rd-kpis", title: t("Bir baxışda"), text: t("Neçə tələbə yüksək risk altındadır, neçəsinə plan göndərilib və planlar nəticə verirmi.") },
  { sel: "#rd-list", title: t("Kimə və niyə?"), text: t("Tələbələr risk balına görə sıralanır. Rəngli zolaq balın hansı siqnallardan yarandığını, “Niyə?” sütunu isə faktları göstərir.") },
  { sel: "#rd-gaps", title: t("Dərsə aid siqnal"), text: t("Bir neçə tələbənin eyni anda çətinlik çəkdiyi mövzu — onu növbəti dərsdə təkrarlamaq tövsiyə olunur.") },
  { sel: "#rd-model", title: t("Şəffaf model"), text: t("Çəkilər, hədlər və prinsiplər açıq göstərilir: üzrlü qayıblar sayılmır, söhbətlərin mətni oxunmur, qərarı insan verir.") },
] });
registerTour("radar.student", { route: "/radar/student/:id", roles: ["teacher", "office", "leader", "admin"], title: t("Tələbə profili"), group: t("Tədris"), icon: "activity", steps: [
  { sel: "#rd-why", title: t("Balın izahı"), text: t("Dörd siqnalın hər biri neçə bal verib və hansı faktlara əsaslanır.") },
  { sel: "#rd-rec", title: t("Tövsiyə"), text: t("Sistem ən təsirli addımı təklif edir. Planı bir kliklə hazırlayıb baxdıqdan sonra göndərin.") },
  { sel: "#rd-plans", title: t("Planlar və nəticə"), text: t("Addımlar tələbənin real fəaliyyətinə görə avtomatik qeyd olunur.") },
] });
