// 3-minute presenter mode: a floating script that switches roles, opens the right page, highlights what to show and says what
// to tell. State lives in sessionStorage, so it survives role switches and language reloads. Start: login page button,
// "?demo=1" in the address, or the profile menu.
import { S, api, html, mount, ic, toast, go, t, $, TOURS } from "./core.js";

const KEY = "zeka-demo";
let story = null;

const STEPS = [
  { role: "leader", path: "/leader", focus: "#leader-radar", title: t("Problem: risk gec görünür"),
    say: t("Universitet tələbəni adətən imtahandan sonra itirir. Zəka davamiyyəti, balları, testləri və AI tutordakı fəaliyyəti birləşdirib riski həftələr əvvəl göstərir."),
    act: t("Radar kartını göstərin: yüksək risk, diqqət siyahısı və planların təsiri.") },
  { role: "teacher", path: "/radar", focus: "#rd-list", title: t("Müəllim: kimə kömək lazımdır?"),
    say: t("Müəllim fənni üzrə 120 tələbəni risk balına görə görür. Rəngli zolaq balın səbəblərini, “Niyə?” sütunu faktları göstərir."),
    act: t("Siyahının başındakı Murad Hüseynovu göstərin.") },
  { role: "teacher", path: () => `/radar/student/${story.students.murad}?course=${story.course_id}`, focus: "#rd-why", title: t("Niyə Murad?"),
    say: t("Son 4 dərsə gəlməyib, test nəticəsi 67%-dən 25%-ə düşüb, Kirxhof qanunu üzrə dəfələrlə sual verib. Söhbətlərin mətni göstərilmir — yalnız mövzu və say."),
    act: t("Riskin dinamikasını göstərin: bir həftə əvvəl hər şey normal görünürdü.") },
  { role: "teacher", path: () => `/radar/student/${story.students.murad}?course=${story.course_id}&plan=1`, focus: "#pv", title: t("Bir kliklə dəstək planı"),
    say: t("AI planı müəllimin öz mühazirələrindən qurur: mövzunu təkrarlamaq, məşq, dərsə qayıdış, konsultasiya. Müəllim baxır və göndərir — qərarı insan verir."),
    act: t("“Tələbəyə göndər” düyməsini basın.") },
  { role: "student", user: "murad", path: "/student/plan", focus: "#plan-hero", title: t("Tələbə: etiket yox, dəstək"),
    say: t("Murad risk balını görmür — müəlliminin hazırladığı addımları görür. Hər addım mühazirənin konkret hissəsinə istinad edir."),
    act: t("“Növbəti” düyməsi birinci addımı tutorda açacaq.") },
  { role: "student", user: "murad", path: stepLink, focus: "#chat", title: t("Öyrənmə dövrəsi"),
    say: t("Tutor cavabı mühazirəyə istinadla verir — [1] işarəsinə klikləyib mənbəni göstərin. Bu fəaliyyət planda avtomatik qeyd olunur."),
    act: t("Cavab gəldikdən sonra “Növbəti” düyməsini basın.") },
  { role: "student", user: "murad", path: "/student/plan", focus: "#plan-steps", title: t("Addım özü qeyd olundu"),
    say: t("Birinci addım tamamlandı — tələbənin real fəaliyyətindən. Müəllim heç nəyi əl ilə yoxlamır, yalnız nəticəni görür."),
    act: t("İstəsəniz, məşq addımında düzgün cavab yazın: B (yükün saxlanması).") },
  { role: "leader", path: "/radar", focus: "#rd-impact", title: t("Nəticə: ölçülən təsir"),
    say: t("Rəhbərlik bütün fənlər üzrə riski, göndərilən planları və onların nəticəsini görür. Pilot təklifi: bir fakültə, bir semestr, hədəf — riskli tələbələrin itkisini azaltmaq."),
    act: t("Demonu bitirin. Təkrar üçün: python run.py --reset") },
];

async function stepLink() {
  try {
    const r = await api.get("/api/student/plans");
    const it = r.items.find((x) => x.status === "open");
    const s = it && it.plan.steps.find((x) => !x.done && x.link);
    return s ? s.link : "/student/plan";
  } catch { return "/student/plan"; }
}

const load = () => { try { return JSON.parse(sessionStorage.getItem(KEY) || "null"); } catch { return null; } };
const save = (st) => sessionStorage.setItem(KEY, JSON.stringify(st));

async function become(role, user) {
  const same = S.user && S.user.role === role && (user ? S.user.username === user : role !== "student" || S.user.username === "aysel");
  if (same) return;
  const r = await api.post("/api/auth/demo", user ? { role, user } : { role });
  sessionStorage.setItem("zeka-sid", r.token);
  S.user = r.user;
  document.getElementById("root").dataset.shell = "";
}

function quietTours() {        // no welcome tours or page hints in the middle of a pitch
  for (const r of ["student", "teacher", "office", "leader", "admin"]) localStorage.setItem(`zeka-tour-${r}`, "1");
  for (const k of TOURS.keys()) localStorage.setItem(`zeka-hint-${k}`, "1");
}

async function waitFor(sel, ms = 6000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { const el = $(sel); if (el && el.getBoundingClientRect().height) return el; await new Promise((r) => setTimeout(r, 150)); }
  return null;
}

async function run(i) {
  const st = load();
  if (!st) return;
  st.i = Math.max(0, Math.min(STEPS.length - 1, i));
  save(st);
  draw();
  const s = STEPS[st.i];
  try {
    if (!story) story = await api.get("/api/demo/storyline");
    if (!story.students.murad) { toast(t("Demo hekayəsi tapılmadı. Bazanı sıfırlayın: python run.py --reset"), "err"); return; }
    await become(s.role, s.user);
    const path = typeof s.path === "function" ? await s.path() : s.path;
    go(path);
    const el = await waitFor(s.focus);
    if (el) {
      if (el.closest(".modal")) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
      else window.scrollTo({ top: Math.max(0, el.getBoundingClientRect().top + window.scrollY - 84), behavior: "smooth" });
      el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
    }
  } catch (err) { toast(err.message, "err"); }
}

function fmt(ms) { const s = Math.max(0, Math.floor(ms / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; }
let timer = null;
function draw() {
  const st = load();
  let box = document.getElementById("demo-panel");
  document.body.classList.toggle("demo-on", !!st);
  if (!st) { if (box) box.remove(); clearInterval(timer); return; }
  if (!box) { box = document.createElement("aside"); box.id = "demo-panel"; box.className = "demo-panel"; box.setAttribute("aria-label", t("Demo ssenarisi")); document.body.appendChild(box); }
  box.classList.toggle("min", !!st.min);
  const s = STEPS[st.i];
  mount(box, html`<div class="dp-h">${ic("play", 15)}<div class="grow"><b>${t("3 dəqiqəlik demo")}</b></div>
      <span class="dp-timer" style="color:#dfe6f7">${fmt(Date.now() - st.t0)}</span>
      <button data-dp="min" class="${st.min ? "" : "rot"}" aria-label="${st.min ? t("Panel aç") : t("Paneli kiçilt")}" title="${st.min ? t("Panel aç") : t("Paneli kiçilt")}">${ic("chevron", 14)}</button>
      <button data-dp="x" aria-label="${t("Demonu bitir")}" title="${t("Demonu bitir")}">${ic("x", 14)}</button></div>
    <div class="dp-b"><div class="dp-step">${t("Addım {i} / {n}", { i: st.i + 1, n: STEPS.length })} · ${{ leader: t("Rəhbərlik"), teacher: t("Müəllim"), student: t("Tələbə") }[s.role]}</div>
      <h4>${s.title}</h4><p class="dp-say">${s.say}</p><div class="dp-do">${ic("bolt", 13)} ${s.act}</div>
      <div class="dp-bar" aria-hidden="true">${STEPS.map((_, k) => html`<i class="${k === st.i ? "on" : k < st.i ? "done" : ""}"></i>`)}</div>
      <div class="dp-f"><button class="btn btn-sm btn-ghost" data-dp="prev" ${st.i ? "" : "disabled"}>${t("Geri")}</button>
        <button class="btn btn-sm" data-dp="again" title="${t("Bu addımı yenidən göstər")}">${ic("refresh", 13)}</button>
        ${st.i < STEPS.length - 1 ? html`<button class="btn btn-sm btn-primary" data-dp="next">${t("Növbəti")} ${ic("arrow", 13)}</button>`
          : html`<button class="btn btn-sm btn-success" data-dp="x">${ic("check", 13)} ${t("Bitir")}</button>`}</div></div>`);
  clearInterval(timer);
  timer = setInterval(() => { const tm = box.querySelector(".dp-timer"); const cur = load(); if (tm && cur) tm.textContent = fmt(Date.now() - cur.t0); }, 1000);
}

document.addEventListener("click", (e) => {
  const b = e.target.closest("#demo-panel [data-dp]");
  if (!b) return;
  const st = load();
  if (!st) return;
  const a = b.dataset.dp;
  if (a === "x") { sessionStorage.removeItem(KEY); draw(); return; }
  if (a === "min") { st.min = !st.min; save(st); draw(); return; }
  run(a === "next" ? st.i + 1 : a === "prev" ? st.i - 1 : st.i);
});

export function startDemo() {
  quietTours();
  save({ i: 0, t0: Date.now(), min: false });
  run(0);
}
window.addEventListener("zeka:demo", startDemo);
// After a plan is sent in step 4 the presenter moves on by itself.
window.addEventListener("zeka:plan-sent", () => { const st = load(); if (st && st.i === 3) setTimeout(() => run(4), 900); });

if (new URLSearchParams(location.search).get("demo") === "1") {
  const url = new URL(location.href); url.searchParams.delete("demo"); history.replaceState(null, "", url.toString());
  setTimeout(startDemo, 600);
} else if (load()) setTimeout(draw, 300);

export const demoButton = () => html`<button class="btn btn-ai btn-block demo-start" id="demo-start">${ic("play", 16)} ${t("3 dəqiqəlik demo ssenarisi")}</button>`;
document.addEventListener("click", (e) => { if (e.target.closest("#demo-start, [data-demo-start]")) { e.preventDefault(); startDemo(); } });
