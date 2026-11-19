// Exams of a course (Task 26): the teacher sets an exam (window in local time, duration, plan over the exam question
// pool), opens it (the roster is drawn from the journal's admission), follows the attempts and closes it (grading).
import { api, html, mount, on, ic, toast, modal, fmtDateTime, empty, t } from "./core.js";

const KIND = () => ({ main: t("Əsas"), retake: t("Təkrar"), individual: t("Fərdi vaxt") });
const STATUS = () => ({ draft: [t("Qaralama"), "b-gray"], open: [t("Açıq"), "b-green"], closed: [t("Bağlanıb"), "b-blue"], released: [t("Açıqlanıb"), "b-navy"] });
const ROSTER = () => ({ eligible: [t("Buraxılıb"), "b-green"], excluded: [t("Buraxılmayıb"), "b-red"], exception: [t("İstisna"), "b-amber"] });
const badge = (map, k) => { const [l, c] = map()[k] || [k, "b-gray"]; return html`<span class="badge ${c}">${l}</span>`; };

export async function teacherExams(tgt, c) {
  let list;
  try { list = await api.get(`/api/courses/${c.id}/exams`); } catch (err) { mount(tgt, html`<div class="card pad">${err.message}</div>`); return; }
  mount(tgt, html`<div class="card"><div class="card-h wrap"><h3>${ic("shield", 17)} ${t("İmtahanlar")}</h3>
      <button class="btn btn-primary btn-sm" id="ex-new">${ic("plus", 15)} ${t("Yeni imtahan")}</button></div>
    ${list.length ? html`<div class="table-wrap"><table class="table"><thead><tr><th>${t("İmtahan")}</th><th>${t("Pəncərə")}</th><th>${t("Müddət")}</th>
      <th>${t("Status")}</th><th></th></tr></thead><tbody>
      ${list.map((e) => html`<tr><td><b class="small">${e.title}</b><div class="tiny muted">${KIND()[e.kind] || e.kind}</div></td>
        <td class="small nowrap">${fmtDateTime(e.opens_at)} – ${fmtDateTime(e.closes_at)}</td><td>${t("{n} dəq.", { n: e.duration_min })}</td>
        <td>${badge(STATUS, e.status)}</td><td class="nowrap"><button class="btn btn-sm" data-manage="${e.id}">${t("Bax")}</button>
        ${e.status === "draft" ? html`<button class="btn btn-sm btn-primary" data-open="${e.id}">${t("Aç")}</button>` : ""}
        ${e.status === "open" ? html`<button class="btn btn-sm" data-close="${e.id}">${t("Bağla və qiymətləndir")}</button>` : ""}</td></tr>`)}</tbody></table></div>`
      : html`<div class="card-b">${empty("shield", t("Hələ imtahan yoxdur"), t("İmtahan yalnız “imtahan sualı” kimi təsdiqlənmiş suallardan qurulur: onlar məşqə, tutora və testlərə düşmür."))}</div>`}</div>`);
  on(tgt, "click", "#ex-new", () => modal({ title: t("Yeni imtahan"), size: "lg", body: html`<div class="stack">
      <div class="field"><label class="label" for="ex-title">${t("Ad")}</label><input class="input" id="ex-title" maxlength="200"></div>
      <div class="row wrap"><div class="field"><label class="label" for="ex-kind">${t("Növ")}</label><select class="input" id="ex-kind">${Object.entries(KIND()).map(([k, l]) => html`<option value="${k}">${l}</option>`)}</select></div>
        <div class="field"><label class="label" for="ex-day">${t("Tarix")}</label><input class="input" id="ex-day" type="date"></div>
        <div class="field"><label class="label" for="ex-start">${t("Başlanğıc")}</label><input class="input" id="ex-start" type="time" value="10:00"></div>
        <div class="field"><label class="label" for="ex-end">${t("Son")}</label><input class="input" id="ex-end" type="time" value="12:00"></div>
        <div class="field"><label class="label" for="ex-dur">${t("Müddət, dəq.")}</label><input class="input" id="ex-dur" type="number" min="5" value="90"></div></div>
      <div class="field"><label class="label" for="ex-plan">${t("Plan: hər sətirdə “çətinlik; mövzu; say” (boş xana hər hansı deməkdir)")}</label>
        <textarea class="input" id="ex-plan" rows="3" placeholder="Asan;;10&#10;Orta;Om qanunu;5"></textarea></div>
      <div class="tiny muted">${t("Vaxt universitetin saat qurşağındadır. Hər tələbə öz variantını alır; son vaxtı server saatı müəyyən edir.")}</div></div>`,
    actions: [{ label: t("Saxla"), cls: "btn-primary", onClick: async (w) => {
      const plan = w.querySelector("#ex-plan").value.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
        const [difficulty, topic, count] = l.split(";").map((x) => (x || "").trim());
        return { difficulty: difficulty || null, topic: topic || null, count: Number(count) };
      });
      try {
        await api.post(`/api/courses/${c.id}/exams`, { title: w.querySelector("#ex-title").value, kind: w.querySelector("#ex-kind").value,
          day: w.querySelector("#ex-day").value, start: w.querySelector("#ex-start").value, end: w.querySelector("#ex-end").value,
          duration_min: Number(w.querySelector("#ex-dur").value), plan });
        toast(t("Saxlanıldı"), "ok"); teacherExams(tgt, c);
      } catch (err) { toast(err.message, "err"); return false; }
    } }] }));
  on(tgt, "click", "[data-open]", async (e, b) => {
    try { await api.post(`/api/exams/${b.dataset.open}/open`); toast(t("İmtahan açıldı: siyahı jurnaldan çəkildi"), "ok"); teacherExams(tgt, c); }
    catch (err) { toast(err.message, "err"); }
  });
  on(tgt, "click", "[data-close]", async (e, b) => {
    try { await api.post(`/api/exams/${b.dataset.close}/close`); toast(t("İmtahan bağlandı və qiymətləndirildi"), "ok"); teacherExams(tgt, c); }
    catch (err) { toast(err.message, "err"); }
  });
  on(tgt, "click", "[data-manage]", async (e, b) => {
    let m;
    try { m = await api.get(`/api/exams/${b.dataset.manage}/manage`); } catch (err) { toast(err.message, "err"); return; }
    const att = Object.fromEntries(m.attempts.map((a) => [a.student_id, a]));
    modal({ title: m.exam.title, size: "lg", body: html`<div class="stack">
      <div class="small muted">${t("Hovuzda {n} imtahan sualı", { n: m.pool })} · ${badge(STATUS, m.exam.status)}</div>
      ${m.roster.length ? html`<div class="table-wrap"><table class="table"><thead><tr><th>${t("Tələbə")}</th><th>${t("Siyahı")}</th><th>${t("Cəhd")}</th><th>${t("Bal")}</th></tr></thead><tbody>
        ${m.roster.map((r) => html`<tr><td>${r.full_name} <span class="tiny muted">${r.student_no || ""}</span></td><td>${badge(ROSTER, r.status)}${r.reason ? html`<div class="tiny muted">${r.reason}</div>` : ""}</td>
          <td class="small">${att[r.student_id] ? att[r.student_id].status : "—"}${att[r.student_id] && att[r.student_id].auto ? html` <span class="badge b-amber">${t("avtomatik")}</span>` : ""}</td>
          <td>${att[r.student_id] && att[r.student_id].score != null ? `${att[r.student_id].score} / ${att[r.student_id].max_score}` : "—"}</td></tr>`)}</tbody></table></div>`
        : html`<p class="small muted" style="margin:0">${t("Siyahı imtahan açılanda jurnaldan çəkilir.")}</p>`}</div>` });
  });
}

// A student's exams of a course (Task 27): an open one is entered here; the exam page opens in an exam-only session
// (every other session of the student ends).
export async function studentExams(box, c) {
  let list;
  try { list = await api.get(`/api/courses/${c.id}/exams`); } catch { return; }
  if (!list.length) return;
  mount(box, html`<div class="card"><div class="card-h"><h3>${ic("shield", 17)} ${t("İmtahanlar")}</h3></div><div class="card-b list">
    ${list.map((e) => html`<div class="list-item"><div class="grow"><b class="small">${e.title}</b>
        <div class="tiny muted">${fmtDateTime(e.opens_at)} – ${fmtDateTime(e.closes_at)} · ${t("{n} dəq.", { n: e.duration_min })}</div>
        ${e.roster === "excluded" ? html`<div class="tiny" style="color:var(--red)">${t("Davamiyyət həddi keçildiyi üçün imtahana buraxılmırsınız. Dekanlığa müraciət edin.")}</div>` : ""}</div>
      ${e.status === "open" && e.roster !== "excluded" && e.attempt !== "submitted" && e.attempt !== "graded"
        ? html`<button class="btn btn-sm btn-primary" data-enter="${e.id}">${ic("shield", 14)} ${e.attempt ? t("Davam et") : t("İmtahana daxil ol")}</button>`
        : html`${badge(STATUS, e.attempt === "submitted" || e.attempt === "graded" ? "closed" : e.status)}`}</div>`)}</div></div>`);
  on(box, "click", "[data-enter]", async (e, b) => {
    if (!confirm(t("İmtahan səhifəsi açılacaq və bu brauzerdəki digər girişləriniz bağlanacaq. Davam edək?"))) return;
    try { const r = await api.post(`/api/exams/${b.dataset.enter}/enter`); location.href = r.url; }
    catch (err) { toast(err.message, "err"); }
  });
}
