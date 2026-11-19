// The proctor panel (Task 29): the exams a person watches, and an exam's live board polled every 5 seconds. Each
// student on the roster: the attempt's state, progress, time left, when last seen, the address and the flagged events
// (focus lost, full screen left, reconnected, address changed or refused, a sign-in elsewhere). Every action needs a
// reason and goes into the exam's log; the server allows it only for a student on this exam's roster.
import { api, html, mount, on, ic, toast, route, go, t, pageHead, loading, empty, failed, modal, S, fmtDateTime, fmtTime } from "./core.js";
import { HOME } from "./shell.js";

const POLL_MS = 5000;
const ATTEMPT = () => ({ in_progress: [t("Yazır"), "b-green"], paused: [t("Dayandırılıb"), "b-amber"], submitted: [t("Təslim edib"), "b-blue"],
  graded: [t("Qiymətləndirilib"), "b-navy"] });
const FLAG = () => ({ "client.blur": t("pəncərədən çıxıb"), "client.fullscreen_exit": t("tam ekrandan çıxıb"), "client.reconnect": t("yenidən qoşulub"),
  "net.changed": t("ünvan dəyişib"), "net.refused": t("kənar ünvan"), "login.during_exam": t("başqa yerdən giriş"), "seb.refused": t("SEB yoxlanmayıb") });
const EVENT = () => ({ "session.entered": t("imtahana daxil oldu"), "session.takeover": t("başqa kompüterdən davam etdi"), "session.refused": t("girişi rədd edildi"),
  "attempt.started": t("başladı"), "attempt.submitted": t("təslim etdi"), "attempt.refused": t("başlaya bilmədi"), ...FLAG(),
  "proctor.extend": t("vaxt əlavə olundu"), "proctor.pause": t("dayandırıldı"), "proctor.resume": t("davam etdirildi"), "proctor.end": t("cəhd bitirildi"),
  "proctor.reopen": t("cəhd yenidən açıldı"), "proctor.unlock": t("giriş kilidi açıldı"), "proctors.set": t("nəzarətçilər təyin olundu"),
  "seb.verified": t("SEB yoxlandı"), "exam.opened": t("imtahan açıldı"), "exam.closed": t("imtahan bağlandı"), "exam.created": t("imtahan yaradıldı"), "roster.exception": t("istisna verildi") });
const ACTION = () => ({ extend: t("Vaxt əlavə et"), pause: t("Dayandır"), resume: t("Davam etdir"), end: t("Cəhdi bitir"), reopen: t("Yenidən aç"),
  unlock: t("Giriş kilidini aç") });
const NEEDS_MINUTES = ["extend", "reopen"];
const ALLOWED = { null: ["unlock"], in_progress: ["extend", "pause", "end", "unlock"], paused: ["extend", "resume", "end", "unlock"],
  submitted: ["reopen", "unlock"], graded: [] };

const clock = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
const seen = (s) => (s == null ? "—" : s < 60 ? t("{n} san. əvvəl", { n: s }) : t("{n} dəq. əvvəl", { n: Math.floor(s / 60) }));
const badge = (map, k, fallback) => { const [l, c] = map()[k] || [fallback, "b-gray"]; return html`<span class="badge ${c}">${l}</span>`; };

route("/proctor", async (el) => {
  mount(el, loading());
  let list;
  try { list = await api.get("/api/proctor/exams"); } catch (err) { return mount(el, failed(err.message)); }
  const crumbs = [[t("Əsas"), HOME[S.user.role] || "/"], [t("İmtahan nəzarəti")]];
  mount(el, html`${pageHead(t("İmtahan nəzarəti"), t("Sizə təyin olunmuş və fənlərinizin açıq imtahanları. Lövhə hər 5 saniyədən bir yenilənir."), "", crumbs)}
    <div class="card">${list.length ? html`<div class="list card-b">${list.map((e) => html`<div class="list-item click" data-board="${e.id}">
        <span class="dot ${e.status === "open" ? "" : "amber"}"></span><div class="grow"><b class="small">${e.title}</b>
        <div class="tiny muted">${e.course_code} · ${e.course_name} · ${fmtDateTime(e.opens_at)} – ${fmtTime(e.closes_at)}</div></div>
        <button class="btn btn-sm btn-primary">${ic("eye", 14)} ${t("Lövhə")}</button></div>`)}</div>`
      : html`<div class="card-b">${empty("shield", t("Nəzarət ediləcək imtahan yoxdur"), t("Müəllim sizi imtahana nəzarətçi təyin edəndə burada görünür."))}</div>`}</div>`);
  on(el, "click", "[data-board]", (e, b) => go(`/proctor/${b.dataset.board}`));
});

route("/proctor/:id", async (el, p) => {
  const id = Number(p.id);
  mount(el, loading());
  let data, feed = [], seq = 0, stale = false, fetchedAt = performance.now(), filter = "all";
  try { data = await api.get(`/api/exams/${id}/board`); } catch (err) { return mount(el, failed(err.message)); }
  feed = data.events.slice(-60); seq = data.seq;

  const counts = () => {
    const n = { all: data.students.length, writing: 0, paused: 0, done: 0, waiting: 0, flagged: 0 };
    for (const s of data.students) {
      if (s.attempt === "in_progress") n.writing++; else if (s.attempt === "paused") n.paused++;
      else if (s.attempt === "submitted" || s.attempt === "graded") n.done++; else if (s.roster !== "excluded") n.waiting++;
      if (Object.keys(s.flags).length) n.flagged++;
    }
    return n;
  };
  const shown = () => data.students.filter((s) => filter === "all" || (filter === "writing" && s.attempt === "in_progress") ||
    (filter === "paused" && s.attempt === "paused") || (filter === "done" && (s.attempt === "submitted" || s.attempt === "graded")) ||
    (filter === "waiting" && !s.attempt && s.roster !== "excluded") || (filter === "flagged" && Object.keys(s.flags).length));

  const row = (s) => html`<tr class="${Object.keys(s.flags).length ? "px-flagged" : ""}">
    <td><b class="small">${s.full_name}</b><div class="tiny muted">${s.student_no || ""}${s.roster === "excluded" ? html` · <span style="color:var(--red)">${t("buraxılmayıb")}</span>` : ""}</div></td>
    <td>${s.attempt ? badge(ATTEMPT, s.attempt, s.attempt) : html`<span class="badge b-gray">${t("Başlamayıb")}</span>`}</td>
    <td class="px-progress"><div class="progress ${s.answered >= s.total ? "green" : ""}"><span style="width:${s.total ? Math.round((100 * s.answered) / s.total) : 0}%"></span></div>
      <div class="tiny muted">${s.answered} / ${s.total}</div></td>
    <td class="nowrap mono" data-left="${s.attempt === "in_progress" ? s.remaining_s : ""}">${s.attempt === "in_progress" || s.attempt === "paused" ? clock(s.remaining_s) : "—"}</td>
    <td class="small nowrap"><span class="dot ${s.online ? "" : "amber"}"></span> ${seen(s.seen_s)}<div class="tiny muted mono">${s.ip || ""}</div></td>
    <td>${Object.entries(s.flags).map(([k, n]) => html`<span class="badge ${k === "net.refused" || k === "login.during_exam" ? "b-red" : "b-amber"} px-flag">${FLAG()[k] || k} × ${n}</span>`)}</td>
    <td>${(ALLOWED[s.attempt] || []).length ? html`<select class="input px-act" data-sid="${s.student_id}" aria-label="${t("Əməliyyat: {name}", { name: s.full_name })}">
      <option value="">${t("Əməliyyat…")}</option>${ALLOWED[s.attempt].map((a) => html`<option value="${a}">${ACTION()[a]}</option>`)}</select>` : ""}</td></tr>`;

  const entry = (x) => html`<div class="list-item"><div class="grow small"><b>${x.student_name || x.actor_name || "—"}</b> ${EVENT()[x.kind] || x.kind}
    ${x.data && x.data.reason ? html`<div class="tiny muted">${t("Səbəb")}: ${x.data.reason}${x.actor_name ? ` · ${x.actor_name}` : ""}</div>` : ""}
    ${x.kind === "net.changed" ? html`<div class="tiny muted mono">${x.data.from} → ${x.data.to}</div>` : ""}
    ${x.kind === "net.refused" || (x.kind === "session.refused" && x.data.ip) ? html`<div class="tiny muted mono">${x.data.ip}</div>` : ""}</div>
    <span class="tiny muted nowrap">${fmtTime(x.at)}</span></div>`;

  // The page is drawn once; a poll replaces only the parts that change (a full redraw replays the page's entry
  // animation every 5 seconds and closes a dropdown the proctor has open).
  const update = () => {
    const n = counts();
    const tab = (k, label) => html`<button class="chip ${filter === k ? "on" : ""}" data-filter="${k}">${label} <b>${n[k]}</b></button>`;
    el.querySelector("#px-live").className = `px-live small ${stale ? "px-stale" : ""}`;
    mount(el.querySelector("#px-live"), html`<span class="dot ${stale ? "amber" : ""}"></span>
      ${stale ? t("Bağlantı yoxdur: lövhə köhnə ola bilər") : t("Canlı · hər 5 saniyədən bir yenilənir")}`);
    mount(el.querySelector("#px-filters"), html`${tab("all", t("Hamısı"))}${tab("writing", t("Yazır"))}${tab("paused", t("Dayandırılıb"))}
      ${tab("done", t("Təslim edib"))}${tab("waiting", t("Başlamayıb"))}${tab("flagged", t("Diqqət"))}`);
    if (!(document.activeElement && document.activeElement.classList.contains("px-act"))) {
      mount(el.querySelector("#px-rows"), shown().length ? html`${shown().map(row)}` : html`<tr><td colspan="7" class="muted small">${t("Bu süzgəcdə tələbə yoxdur")}</td></tr>`);
      tick();                                     // the time left counts from when the data came, not from this redraw (SF-13)
    }
    mount(el.querySelector("#px-feed"), feed.length ? html`${feed.slice().reverse().map(entry)}` : html`<p class="small muted" style="margin:0">${t("Hələ hadisə yoxdur")}</p>`);
  };

  const draw = () => {
    const e = data.exam;
    const crumbs = [[t("Əsas"), HOME[S.user.role] || "/"], [t("İmtahan nəzarəti"), "/proctor"], [e.title]];
    mount(el, html`${pageHead(e.title, html`${fmtDateTime(e.opens_at)} – ${fmtTime(e.closes_at)} · ${t("{n} dəq.", { n: e.duration_min })}
        ${e.allowed_cidrs.length ? html` · ${t("Şəbəkə: {list}", { list: e.allowed_cidrs.join(", ") })}` : html` · ${t("Şəbəkə məhdudiyyəti yoxdur")}`}`, "", crumbs)}
      <div id="px-live" class="px-live small"></div><div id="px-filters" class="chips px-filters"></div>
      <div class="px-grid"><div class="card"><div class="table-wrap"><table class="table px-table"><thead><tr><th>${t("Tələbə")}</th><th>${t("Vəziyyət")}</th>
        <th>${t("İrəliləyiş")}</th><th>${t("Qalan vaxt")}</th><th>${t("Son görünmə")}</th><th>${t("Hadisələr")}</th><th></th></tr></thead>
        <tbody id="px-rows"></tbody></table></div></div>
      <div class="card px-feed"><div class="card-h"><h3>${ic("list", 16)} ${t("İmtahan jurnalı")}</h3></div><div class="card-b list" id="px-feed"></div></div></div>`);
    update();
  };

  const tick = () => {
    if (!document.body.contains(el) || location.hash !== `#/proctor/${id}` || !el.querySelector("#px-rows")) return false;
    const gone = Math.floor((performance.now() - fetchedAt) / 1000);
    for (const td of el.querySelectorAll("[data-left]")) if (td.dataset.left !== "") td.textContent = clock(Math.max(0, Number(td.dataset.left) - gone));
    return true;
  };
  const poll = async () => {
    if (!tick()) return;
    try {
      const next = await api.get(`/api/exams/${id}/board?after=${seq}`);
      data = next; feed = feed.concat(next.events).slice(-60); seq = next.seq; stale = false; fetchedAt = performance.now();
    } catch (err) {
      if ([401, 403, 404].includes(err.status)) { mount(el, failed(err.message)); return; }   // not a lost connection: said, not polled (SF-13)
      stale = true;
    }
    if (!document.querySelector(".modal") && tick()) update();       // an open action dialog is not redrawn under the proctor
    setTimeout(poll, POLL_MS);
  };
  const ticker = setInterval(() => { if (!tick()) clearInterval(ticker); }, 1000);

  on(el, "click", "[data-filter]", (e, b) => { filter = b.dataset.filter; update(); });
  on(el, "change", ".px-act", (e, sel) => {
    const action = sel.value, sid = Number(sel.dataset.sid);
    sel.value = "";
    sel.blur();
    if (!action) return;
    const s = data.students.find((x) => x.student_id === sid);
    modal({ title: `${ACTION()[action]} · ${s ? s.full_name : ""}`, body: html`<div class="stack">
        ${NEEDS_MINUTES.includes(action) ? html`<div class="field"><label class="label" for="px-min">${action === "extend" ? t("Neçə dəqiqə əlavə olunsun") : t("Neçə dəqiqəlik açılsın")}</label>
          <input class="input" id="px-min" type="number" min="1" max="240" value="10"></div>` : ""}
        <div class="field"><label class="label" for="px-reason">${t("Səbəb (məcburidir, imtahan jurnalına yazılır)")}</label>
          <textarea class="input" id="px-reason" rows="3" maxlength="300"></textarea></div></div>`,
      actions: [{ label: ACTION()[action], cls: action === "end" ? "btn-danger" : "btn-primary", onClick: async (w) => {
        const body = { reason: w.querySelector("#px-reason").value };
        if (NEEDS_MINUTES.includes(action)) body.minutes = Number(w.querySelector("#px-min").value);
        try {
          const next = await api.post(`/api/exams/${id}/students/${sid}/${action}`, body);
          data = next; feed = feed.concat(next.events.filter((x) => x.seq > seq)).slice(-60); seq = Math.max(seq, next.seq); fetchedAt = performance.now();
          toast(t("Saxlanıldı"), "ok"); setTimeout(update, 0);
        } catch (err) { toast(err.message, "err"); return false; }
      } }] });
  });
  draw();
  setTimeout(poll, POLL_MS);
});
