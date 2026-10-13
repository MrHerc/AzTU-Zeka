import { S, api, esc, t, TOURS, tourFor, currentPath, REDUCED, $ } from "./core.js";

// Role onboarding (first visit). Page-level guides are registered by page modules with registerTour().
const ROLE_STEPS = {
  student: [
    { sel: ".brand", title: t("Xoş gəlmisiniz!"), text: t("Bu, AzTU-nun rəqəmsal kampusudur: dərslər, AI tutor, e-xidmətlər və xəbərlər bir yerdə. Qısa tanışlığa başlayaq.") },
    { sel: "#today-card", title: t("Bu gün"), text: t("Bugünkü dərslər, otaqlar və cari dərs burada görünür. Tam cədvəl “Dərs cədvəli” bölməsindədir.") },
    { sel: "[data-path='/student/tutor']", title: t("AI tutor"), text: t("Fənn materiallarına əsaslanan tutor hər cavabda mənbəni göstərir və tapşırığın hazır cavabını vermir.") },
    { sel: "[data-path='/student/services']", title: t("E-xidmətlər"), text: t("Arayış, transkript, akademik məzuniyyət və digər xidmətlər — kağız ərizəsiz, onlayn.") },
    { sel: "[data-path='/student/attendance']", title: t("Davamiyyət"), text: t("Xəstə olmusunuzsa, həkim arayışını buradan yükləyin: dekanlıq təsdiqlədikdə qayıb üzrlü sayılır.") },
    { sel: "[data-path='/achievements']", title: t("AzTU-nun nailiyyətləri"), text: t("Universitetin reytinqləri, elmi və tələbə uğurları — rəsmi mənbələrə keçidlərlə.") },
    { sel: "#lang-btn", title: t("Interfeys dili"), text: t("Portalı azərbaycan, ingilis və ya rus dilində istifadə edin.") },
    { sel: "#burger", title: t("Menyunu yığın"), text: t("Daha geniş iş sahəsi üçün sol paneli yığın. Qısayol: [ düyməsi.") },
    { sel: "#help-btn", title: t("Kömək həmişə yanınızdadır"), text: t("Hər səhifənin öz bələdçisi var: “Bu səhifəni izah et” seçin. Sualınız qalsa, dəstək xidmətinə yazın.") },
  ],
  teacher: [
    { sel: ".brand", title: t("Xoş gəlmisiniz!"), text: t("Zəka tədrisdə vaxta qənaət və peşəkar inkişaf üçün hazırlanıb. Qısa tanışlığa başlayaq.") },
    { sel: "#insights-card", title: t("Tutor müşahidələri"), text: t("Tələbələrin ən çox soruşduğu mövzular və materiallarda cavabı olmayan suallar — anonim statistika.") },
    { sel: "[data-path='/teacher/courses']", title: t("Fənlərim"), text: t("Material yükləyin, tutor rejimlərini tənzimləyin və davamiyyəti izləyin.") },
    { sel: "[data-path='/teacher/studio']", title: t("Test studiyası"), text: t("AI materialdan sual hazırlayır, siz yoxlayıb təsdiqləyirsiniz. Təsdiqlənməmiş sual tələbəyə getmir.") },
    { sel: "[data-path='/teacher/academy']", title: t("AI Akademiya"), text: t("İngilis dilində tədris, sillabus, akademik ünsiyyət və AI üzrə qısa modullar və sertifikatlar.") },
    { sel: "#lang-btn", title: t("Interfeys dili"), text: t("Portalı azərbaycan, ingilis və ya rus dilində istifadə edin.") },
    { sel: "#help-btn", title: t("Səhifə bələdçisi"), text: t("Hər səhifənin öz bələdçisi var. Turu istənilən vaxt buradan yenidən başlada bilərsiniz.") },
  ],
  office: [
    { sel: ".brand", title: t("Dekanlıq paneli"), text: t("Bütün tələbə müraciətləri bir növbədə: icra müddəti, sənədlər və yazışma.") },
    { sel: "#office-stats", title: t("Gündəlik göstəricilər"), text: t("Yeni, icrada olan və müddəti keçən müraciətlər. Qırmızı rəng icra müddətinin pozulduğunu göstərir.") },
    { sel: "#queue", title: t("Növbə"), text: t("Müraciəti açın: məlumatlar, əlavə fayllar və yazışma bir ekrandadır. Sənəd şablondan avtomatik hazırlanır.") },
    { sel: "[data-path='/staff/support']", title: t("Dəstək sorğuları"), text: t("İstifadəçilərin texniki və ümumi sualları burada toplanır.") },
    { sel: "#help-btn", title: t("Bələdçi"), text: t("Hər prosesin addım-addım izahı bələdçidədir.") },
  ],
  leader: [
    { sel: ".brand", title: t("Rəhbərlik paneli"), text: t("Pilotun gedişatı: göstəricilər, AI keyfiyyəti, e-xidmətlər və tövsiyələr.") },
    { sel: "#kpis", title: t("Pilot göstəriciləri"), text: t("Əsas göstəricilər və hədəflər. Yaşıl nişan hədəfə çatıldığını bildirir.") },
    { sel: "#insights", title: t("Diqqət tələb edənlər"), text: t("Platforma avtomatik tövsiyələr verir: materiallardakı boşluqlar, gecikən müraciətlər və s.") },
    { sel: "[data-path='/staff/feedback']", title: t("Rəylər və məmnuniyyət"), text: t("İstifadəçi rəyləri, məmnuniyyət indeksi və NPS bir paneldə.") },
    { sel: "#help-btn", title: t("Bələdçi"), text: t("Paneli necə oxumaq barədə izahat bələdçidədir.") },
  ],
  admin: [
    { sel: ".brand", title: t("Platformanın idarə edilməsi"), text: t("AI mühərriki, limitlər, məxfilik, dəstək və audit.") },
    { sel: "[data-path='/staff/support']", title: t("Dəstək sorğuları"), text: t("Texniki sorğular və istifadəçi rəyləri burada idarə olunur.") },
    { sel: "#help-btn", title: t("Bələdçi"), text: t("LLM-in qoşulması üzrə təlimat bələdçidədir.") },
  ],
};
export const roleTourSteps = (role) => ROLE_STEPS[role] || [];

let active = null;
const KEYS = () => new Set([...(((S.user && S.user.prefs) || {}).tours || [])]);
export const isDone = (key) => KEYS().has(key) || localStorage.getItem(`zeka-tour-${key}`) === "1";
export const tourDone = (role) => isDone(role);
async function markDone(key) {
  localStorage.setItem(`zeka-tour-${key}`, "1");
  const tours = [...new Set([...KEYS(), key])];
  S.user.prefs = { ...(S.user.prefs || {}), tours };
  try { await api.put("/api/me/prefs", { tours }); } catch { /* ignore */ }
}
const visible = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden"; };

export function runTour({ key, title, steps }, { onDone } = {}) {
  if (active) active.finish(false);
  const list = (steps || []).filter((s) => !s.sel || visible(document.querySelector(s.sel)));
  if (!list.length) return false;
  let i = 0;
  const shades = [0, 1, 2, 3].map(() => { const d = document.createElement("div"); d.className = "tour-mask"; return d; });
  const spot = document.createElement("div"); spot.className = "tour-spot";
  const card = document.createElement("div"); card.className = "tour-card"; card.setAttribute("role", "dialog"); card.setAttribute("aria-modal", "true");
  card.setAttribute("aria-label", title || t("Bələdçi"));
  document.body.append(...shades, spot, card);
  document.body.classList.add("touring");
  const finish = (completed) => {
    shades.forEach((s) => s.remove()); spot.remove(); card.remove(); active = null;
    document.body.classList.remove("touring");
    window.removeEventListener("resize", place); document.removeEventListener("keydown", onKey, true);
    if (completed !== false && key) markDone(key);
    onDone && onDone(completed);
  };
  active = { finish };
  function place() {
    const st = list[i];
    const el = st.sel ? document.querySelector(st.sel) : null;
    if (st.sel && !visible(el)) return i < list.length - 1 ? next() : finish(true);
    const W = window.innerWidth, H = window.innerHeight;
    let r = el ? el.getBoundingClientRect() : { left: W / 2, top: H / 2, right: W / 2, bottom: H / 2, width: 0, height: 0 };
    if (el && (r.top < 70 || r.bottom > H - 40)) { el.scrollIntoView({ block: "center", behavior: REDUCED ? "auto" : "smooth" }); setTimeout(position, REDUCED ? 0 : 320); }
    position();
    function position() {
      r = el ? el.getBoundingClientRect() : r;
      const pad = el ? 6 : 0;
      const x = Math.max(0, r.left - pad), y = Math.max(0, r.top - pad), x2 = Math.min(W, r.right + pad), y2 = Math.min(H, r.bottom + pad);
      Object.assign(spot.style, { left: `${x}px`, top: `${y}px`, width: `${x2 - x}px`, height: `${y2 - y}px`, opacity: el ? "1" : "0" });
      const [sTop, sBottom, sLeft, sRight] = shades;
      Object.assign(sTop.style, { left: "0px", top: "0px", width: `${W}px`, height: `${y}px` });
      Object.assign(sBottom.style, { left: "0px", top: `${y2}px`, width: `${W}px`, height: `${Math.max(0, H - y2)}px` });
      Object.assign(sLeft.style, { left: "0px", top: `${y}px`, width: `${x}px`, height: `${y2 - y}px` });
      Object.assign(sRight.style, { left: `${x2}px`, top: `${y}px`, width: `${Math.max(0, W - x2)}px`, height: `${y2 - y}px` });
      card.innerHTML = `<div class="row between mb-sm"><span class="tiny muted">${esc(title || "")}${title ? " · " : ""}${i + 1} / ${list.length}</span>
          <div class="tour-dots" aria-hidden="true">${list.map((_, k) => `<i class="${k === i ? "on" : k < i ? "done" : ""}"></i>`).join("")}</div></div>
        <h4>${esc(st.title)}</h4><p>${esc(st.text)}</p>
        <div class="row between mt"><button class="btn btn-ghost btn-sm" data-t="skip">${esc(t("Bağla"))}</button>
          <div class="row">${i ? `<button class="btn btn-sm" data-t="prev">${esc(t("Geri"))}</button>` : ""}<button class="btn btn-primary btn-sm" data-t="next">${esc(i === list.length - 1 ? t("Tamamla") : t("Növbəti"))}</button></div></div>`;
      const mobile = W < 640;
      card.classList.toggle("sheet", mobile);
      if (mobile) {
        const below = r.top + r.height / 2 < H / 2;
        Object.assign(card.style, { left: "12px", right: "12px", width: "auto", top: below ? "auto" : "12px", bottom: below ? "12px" : "auto" });
      } else {
        const cw = Math.min(360, W - 24), ch = card.offsetHeight || 200;
        let left = r.right + 16, top = r.top;
        if (!el) { left = (W - cw) / 2; top = (H - ch) / 2; }
        else if (left + cw > W - 12) {
          left = Math.max(12, Math.min(r.left, W - cw - 12));
          top = r.bottom + 14 + ch > H ? Math.max(12, r.top - ch - 14) : r.bottom + 14;
        } else top = Math.min(Math.max(12, r.top), H - ch - 12);
        Object.assign(card.style, { left: `${left}px`, top: `${top}px`, right: "auto", bottom: "auto", width: `${cw}px` });
      }
      card.querySelector("[data-t=next]").focus({ preventScroll: true });
    }
  }
  function next() { if (i < list.length - 1) { i += 1; place(); } else finish(true); }
  function prev() { if (i > 0) { i -= 1; place(); } }
  function onKey(e) {
    if (e.key === "Escape") { e.preventDefault(); finish(false); }
    else if (e.key === "ArrowRight") { e.preventDefault(); next(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); prev(); }
  }
  card.addEventListener("click", (e) => { const b = e.target.closest("[data-t]"); if (!b) return; ({ next, prev, skip: () => finish(false) })[b.dataset.t](); });
  shades.forEach((s) => s.addEventListener("click", () => finish(false)));
  window.addEventListener("resize", place);
  document.addEventListener("keydown", onKey, true);
  setTimeout(place, 60);
  return true;
}

export function startTour(force = false) {
  const role = S.user && S.user.role;
  if (!role || active || (!force && tourDone(role))) return;
  runTour({ key: role, title: t("Tanışlıq turu"), steps: ROLE_STEPS[role] });
}

export function startPageTour(key) {
  const tr = key ? TOURS.get(key) : S.user && tourFor(currentPath().path, S.user.role);
  if (!tr) return false;
  hideHint();
  return runTour({ key: "p:" + tr.key, title: tr.title, steps: typeof tr.steps === "function" ? tr.steps() : tr.steps });
}

// First visit to a page with a guide: a small, dismissible hint instead of an automatic tour.
let hintEl = null;
function hideHint() { if (hintEl) { hintEl.remove(); hintEl = null; } }
export function maybeHint() {
  hideHint();
  if (!S.user || active || !tourDone(S.user.role) || new URLSearchParams(location.search).get("audit") === "1") return;
  const tr = tourFor(currentPath().path, S.user.role);
  if (!tr || isDone("p:" + tr.key) || localStorage.getItem(`zeka-hint-${tr.key}`)) return;
  hintEl = document.createElement("div");
  hintEl.className = "tour-hint";
  hintEl.setAttribute("role", "status");
  hintEl.innerHTML = `<span class="th-ic" aria-hidden="true"></span><div class="grow"><b>${esc(t("Bu səhifədə yenisiniz?"))}</b><span>${esc(t("{n} addımlıq qısa bələdçi ilə tanış olun.", { n: (typeof tr.steps === "function" ? tr.steps() : tr.steps).length }))}</span></div>
    <button class="btn btn-primary btn-sm" data-h="go">${esc(t("Başla"))}</button><button class="btn btn-ghost btn-sm btn-icon" data-h="x" aria-label="${esc(t("Bağla"))}">✕</button>`;
  document.body.appendChild(hintEl);
  hintEl.addEventListener("click", (e) => {
    const b = e.target.closest("[data-h]"); if (!b) return;
    localStorage.setItem(`zeka-hint-${tr.key}`, "1");
    if (b.dataset.h === "go") startPageTour(tr.key); else hideHint();
  });
}
export const clearHint = hideHint;
export const tourCatalog = (role) => [...TOURS.values()].filter((x) => !x.roles || x.roles.includes(role)).map((x) => ({
  key: x.key, title: x.title, route: x.go || (typeof x.route === "string" && !x.route.includes(":") ? x.route : null), group: x.group || "", icon: x.icon || "compass",
  steps: (typeof x.steps === "function" ? x.steps() : x.steps).length, done: isDone("p:" + x.key),
}));
export const pageTourActive = () => !!active;
export function _debugActive() { return $(".tour-card"); }
