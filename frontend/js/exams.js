// Exams of a course (Task 26): the teacher sets an exam (window in local time, duration, plan over the exam question
// pool), opens it (the roster is drawn from the journal's admission), follows the attempts and closes it (grading).
import { api, html, mount, on, ic, toast, modal, fmtDateTime, empty, t, go, route, pageHead, loading, failed, S } from "./core.js";
import { HOME } from "./shell.js";

const KIND = () => ({ main: t("Əsas"), retake: t("Təkrar imtahan"), individual: t("Fərdi vaxt") });
const STATUS = () => ({ draft: [t("Qaralama"), "b-gray"], open: [t("Açıq"), "b-green"], closed: [t("Bağlanıb"), "b-blue"], released: [t("Açıqlanıb"), "b-navy"] });
const ROSTER = () => ({ eligible: [t("Buraxılıb"), "b-green"], excluded: [t("Buraxılmayıb"), "b-red"], exception: [t("İstisna qaydasında"), "b-amber"] });
const badge = (map, k) => { const [l, c] = map()[k] || [k, "b-gray"]; return html`<span class="badge ${c}">${l}</span>`; };

export async function teacherExams(tgt, c) {
  let list;
  try { list = await api.get(`/api/courses/${c.id}/exams`); } catch (err) { mount(tgt, html`<div class="card pad">${err.message}</div>`); return; }
  mount(tgt, html`<div class="card"><div class="card-h wrap"><h3>${ic("shield", 17)} ${t("İmtahanlar")}</h3>
      <button class="btn btn-primary btn-sm" id="ex-new">${ic("plus", 15)} ${t("Yeni imtahan")}</button></div>
    ${list.length ? html`<div class="table-wrap"><table class="table"><thead><tr><th>${t("İmtahan")}</th><th>${t("Keçirilmə vaxtı")}</th><th>${t("Müddət")}</th>
      <th>${t("Status")}</th><th></th></tr></thead><tbody>
      ${list.map((e) => html`<tr><td><b class="small">${e.title}</b><div class="tiny muted">${KIND()[e.kind] || e.kind}</div></td>
        <td class="small nowrap">${fmtDateTime(e.opens_at)} – ${fmtDateTime(e.closes_at)}</td><td>${t("{n} dəq.", { n: e.duration_min })}</td>
        <td>${badge(STATUS, e.status)}</td><td class="nowrap"><button class="btn btn-sm" data-manage="${e.id}">${t("Bax")}</button>
        ${e.status === "draft" ? html`<button class="btn btn-sm btn-primary" data-open="${e.id}">${t("Aç")}</button>` : ""}
        ${e.status === "open" ? html`<button class="btn btn-sm" data-close="${e.id}">${t("Bağla və qiymətləndir")}</button>` : ""}
        ${e.status === "closed" ? html`<button class="btn btn-sm btn-primary" data-release="${e.id}">${t("Nəticəni açıqla")}</button>` : ""}
        ${e.status === "closed" || e.status === "released" ? html`<button class="btn btn-sm" data-results="${e.id}">${t("Nəticələr")}</button>
          <button class="btn btn-sm" data-analysis="${e.id}">${t("Təhlil")}</button>` : ""}</td></tr>`)}</tbody></table></div>`
      : html`<div class="card-b">${empty("shield", t("Hələ imtahan yoxdur"), t("İmtahan yalnız «imtahan sualı» kimi təsdiqlənmiş suallardan tərtib olunur: bu suallar məşqdə, tutorda və testlərdə istifadə edilmir."))}</div>`}</div>`);
  on(tgt, "click", "#ex-new", () => modal({ title: t("Yeni imtahan"), size: "lg", body: html`<div class="stack">
      <div class="field"><label class="label" for="ex-title">${t("Ad")}</label><input class="input" id="ex-title" maxlength="200"></div>
      <div class="row wrap"><div class="field"><label class="label" for="ex-kind">${t("Növ")}</label><select class="input" id="ex-kind">${Object.entries(KIND()).map(([k, l]) => html`<option value="${k}">${l}</option>`)}</select></div>
        <div class="field"><label class="label" for="ex-day">${t("Tarix")}</label><input class="input" id="ex-day" type="date"></div>
        <div class="field"><label class="label" for="ex-start">${t("Başlanğıc")}</label><input class="input" id="ex-start" type="time" value="10:00"></div>
        <div class="field"><label class="label" for="ex-end">${t("Son")}</label><input class="input" id="ex-end" type="time" value="12:00"></div>
        <div class="field"><label class="label" for="ex-dur">${t("Müddət, dəq.")}</label><input class="input" id="ex-dur" type="number" min="5" value="90"></div></div>
      <div class="field"><label class="label" for="ex-plan">${t("Plan: hər sətirdə «çətinlik; mövzu; say» (boş xana istənilən dəyər deməkdir)")}</label>
        <textarea class="input" id="ex-plan" rows="3" placeholder="Asan;;10&#10;Orta;Om qanunu;5"></textarea></div>
      <div class="field"><label class="label" for="ex-prot">${t("Qoruma")}</label><select class="input" id="ex-prot">
        <option value="open">${t("Adi brauzer (portal)")}</option><option value="seb">${t("Safe Exam Browser məcburidir")}</option></select></div>
      <div class="field"><label class="label" for="ex-cidrs">${t("Şəbəkə siyahısı: imtahan otağının ünvan blokları, vergüllə (boş: hər yerdən)")}</label>
        <input class="input mono" id="ex-cidrs" placeholder="10.20.30.0/24"></div>
      <div class="tiny muted">${t("Vaxt universitetin saat qurşağı üzrə göstərilir. Hər tələbə öz variantını alır; son vaxtı server saatı müəyyən edir.")}</div></div>`,
    actions: [{ label: t("Saxla"), cls: "btn-primary", onClick: async (w) => {
      const plan = w.querySelector("#ex-plan").value.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
        const [difficulty, topic, count] = l.split(";").map((x) => (x || "").trim());
        return { difficulty: difficulty || null, topic: topic || null, count: Number(count) };
      });
      try {
        await api.post(`/api/courses/${c.id}/exams`, { title: w.querySelector("#ex-title").value, kind: w.querySelector("#ex-kind").value,
          day: w.querySelector("#ex-day").value, start: w.querySelector("#ex-start").value, end: w.querySelector("#ex-end").value,
          duration_min: Number(w.querySelector("#ex-dur").value), plan,
          allowed_cidrs: w.querySelector("#ex-cidrs").value.split(/[\s,]+/).filter(Boolean), protection: w.querySelector("#ex-prot").value });
        toast(t("Saxlanıldı"), "ok"); teacherExams(tgt, c);
      } catch (err) { toast(err.message, "err"); return false; }
    } }] }));
  on(tgt, "click", "[data-open]", async (e, b) => {
    try { await api.post(`/api/exams/${b.dataset.open}/open`); toast(t("İmtahan açıldı: siyahı jurnal əsasında tərtib edildi"), "ok"); teacherExams(tgt, c); }
    catch (err) { toast(err.message, "err"); }
  });
  on(tgt, "click", "[data-close]", async (e, b) => {
    try { await api.post(`/api/exams/${b.dataset.close}/close`); toast(t("İmtahan bağlandı və qiymətləndirildi"), "ok"); teacherExams(tgt, c); }
    catch (err) { toast(err.message, "err"); }
  });
  on(tgt, "click", "[data-release]", async (e, b) => {
    if (!confirm(t("Ballar jurnalın imtahan sütununa yazılacaq və tələbələrə görünəcək. Açıqlayaq?"))) return;
    try { await api.post(`/api/exams/${b.dataset.release}/release`); toast(t("Nəticə açıqlandı: ballar jurnalda"), "ok"); teacherExams(tgt, c); }
    catch (err) { toast(err.message, "err"); }
  });
  on(tgt, "click", "[data-results]", async (e, b) => {
    let r;
    try { r = await api.get(`/api/exams/${b.dataset.results}/results`); } catch (err) { toast(err.message, "err"); return; }
    modal({ title: `${r.exam.title} · ${t("Nəticələr")}`, size: "lg", body: resultsTable(r) });
  });
  on(tgt, "click", "[data-analysis]", async (e, b) => {
    let a;
    try { a = await api.get(`/api/exams/${b.dataset.analysis}/analysis`); } catch (err) { toast(err.message, "err"); return; }
    modal({ title: `${a.exam.title} · ${t("Təhlil")}`, size: "lg", body: html`<div class="stack">
      <h4 style="margin:0">${t("Suallar: ən çətinindən başlayaraq")}</h4>
      <div class="table-wrap"><table class="table"><thead><tr><th>${t("Sual")}</th><th>${t("Cavab verən")}</th><th>${t("Düzgün")}</th><th>${t("Ən çox verilən səhv cavablar")}</th></tr></thead><tbody>
        ${a.questions.map((q) => html`<tr><td class="small">${q.text}</td><td>${q.answered}</td><td>${q.rate == null ? "—" : `${Math.round(q.rate * 100)}%`}</td>
          <td class="small mono">${q.wrong.map((w) => `${w.value} × ${w.n}`).join(", ") || "—"}</td></tr>`)}</tbody></table></div>
      <h4 style="margin:0">${t("Eyni səhv cavablar")}</h4>
      <p class="tiny muted" style="margin:0">${t("Bu siyahını yalnız müəllim görür. Siyahı hökm deyil, yalnız diqqət yetirilməli cütləri göstərir.")}</p>
      ${a.pairs.length ? html`<div class="list">${a.pairs.map((p) => html`<div class="list-item"><div class="grow small">${p.a_name} · ${p.b_name}</div>
        <span class="badge b-amber">${t("{n} eyni səhv", { n: p.same })}</span></div>`)}</div>` : html`<p class="small muted" style="margin:0">${t("Belə cüt yoxdur")}</p>`}</div>` });
  });
  on(tgt, "click", "[data-manage]", async (e, b) => {
    let m;
    try { m = await api.get(`/api/exams/${b.dataset.manage}/manage`); } catch (err) { toast(err.message, "err"); return; }
    const att = Object.fromEntries(m.attempts.map((a) => [a.student_id, a]));
    const w = modal({ title: m.exam.title, size: "lg", body: html`<div class="stack">
      <div class="row wrap"><div class="small muted grow">${t("Sual bankında {n} imtahan sualı", { n: m.pool })} · ${badge(STATUS, m.exam.status)}
        · ${m.exam.allowed_cidrs.length ? t("Şəbəkə: {list}", { list: m.exam.allowed_cidrs.join(", ") }) : t("Şəbəkə məhdudiyyəti yoxdur")}</div>
        ${m.exam.status === "open" ? html`<button class="btn btn-sm btn-primary" id="ex-board">${ic("eye", 14)} ${t("Lövhə")}</button>` : ""}
        ${m.exam.protocol_id ? html`<button class="btn btn-sm" data-doc="${m.exam.protocol_id}">${ic("qr", 14)} ${t("Protokol")}</button>` : ""}</div>
      ${m.exam.seb ? html`<div class="card pad stack" style="margin:0"><b class="small">${ic("shield", 14)} Safe Exam Browser</b>
        <div class="tiny muted">${t("Tələbə imtahana SEB vasitəsilə daxil olur. Çıxış parolu nəzarətçidə saxlanılır.")}</div>
        <div class="row wrap small"><span>${t("Çıxış parolu")}: <b class="mono">${m.exam.seb.quit_password}</b></span>
          <a class="btn btn-sm" href="${m.exam.seb.download}">${t("Konfiqurasiyanı yüklə")}</a></div>
        <div class="tiny muted mono" style="word-break:break-all">Config Key: ${m.exam.seb.key}</div></div>` : ""}
      <div class="field"><label class="label" for="ex-proctors">${t("Nəzarətçilər: istifadəçi adları, vergüllə")}</label>
        <div class="row"><input class="input grow mono" id="ex-proctors" value="${m.proctors.map((x) => x.username).join(", ")}">
        <button class="btn btn-sm" id="ex-proctors-save">${t("Saxla")}</button></div></div>
      ${m.roster.length ? html`<div class="table-wrap"><table class="table"><thead><tr><th>${t("Tələbə")}</th><th>${t("Siyahı")}</th><th>${t("Cəhd")}</th><th>${t("Bal")}</th></tr></thead><tbody>
        ${m.roster.map((r) => html`<tr><td>${r.full_name} <span class="tiny muted">${r.student_no || ""}</span></td><td>${badge(ROSTER, r.status)}${r.reason ? html`<div class="tiny muted">${r.reason}</div>` : ""}</td>
          <td class="small">${att[r.student_id] ? att[r.student_id].status : "—"}${att[r.student_id] && att[r.student_id].auto ? html` <span class="badge b-amber">${t("avtomatik")}</span>` : ""}</td>
          <td>${att[r.student_id] && att[r.student_id].score != null ? `${att[r.student_id].score} / ${att[r.student_id].max_score}` : "—"}</td></tr>`)}</tbody></table></div>`
        : html`<p class="small muted" style="margin:0">${t("Siyahı imtahan açıldıqda jurnal əsasında tərtib edilir.")}</p>`}</div>` });
    const box = w.el;
    const board = box.querySelector("#ex-board");
    if (board) board.onclick = () => { w.close(); go(`/proctor/${m.exam.id}`); };
    on(box, "click", "[data-doc]", (ev, d) => openDoc(d.dataset.doc));
    box.querySelector("#ex-proctors-save").onclick = async () => {
      try {
        await api.put(`/api/exams/${m.exam.id}/proctors`, { usernames: box.querySelector("#ex-proctors").value.split(/[\s,]+/).filter(Boolean) });
        toast(t("Saxlanıldı"), "ok");
      } catch (err) { toast(err.message, "err"); }
    };
  });
}

// A student's exams of a course (Task 27): an open one is entered here; the exam page opens in an exam-only session
// (every other session of the student ends).
export async function studentExams(box, c) {
  let list;
  try { list = await api.get(`/api/courses/${c.id}/exams`); } catch (err) { mount(box, failed(err.message)); return; }   // never an empty box (SF-16)
  if (!list.length) return;
  mount(box, html`<div class="card"><div class="card-h"><h3>${ic("shield", 17)} ${t("İmtahanlar")}</h3></div><div class="card-b list">
    ${list.map((e) => html`<div class="list-item"><div class="grow"><b class="small">${e.title}</b>
        <div class="tiny muted">${fmtDateTime(e.opens_at)} – ${fmtDateTime(e.closes_at)} · ${t("{n} dəq.", { n: e.duration_min })}</div>
        ${e.seb_link ? html`<div class="tiny">${t("Bu imtahan yalnız Safe Exam Browser-də açılır.")} <a href="${e.seb_link}">${t("SEB-də aç")}</a></div>` : ""}
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

const RESULT = () => ({ passed: [t("keçdi"), "b-green"], exam_min: [t("imtahan < minimum"), "b-red"], pass_mark: [t("cəm < keçid"), "b-red"],
  not_admitted: [t("buraxılmayıb"), "b-gray"], absent: [t("gəlməyib"), "b-gray"] });
const num = (v) => (v == null ? "—" : String(v));

async function openDoc(id) {
  try { const r = await api.post(`/api/documents/${id}/link`); window.open(r.url, "_blank", "noopener"); }
  catch (err) { toast(err.message, "err"); }
}

// A released exam's results (Task 30): raw score, the points in the journal, semester, total, letter and status.
function resultsTable(r, act) {
  return html`<div class="table-wrap"><table class="table"><thead><tr><th>${t("Tələbə")}</th><th>${t("Qrup")}</th><th>${t("Xam bal")}</th>
    <th>${t("İmtahan")}</th><th>${t("Semestr")}</th><th>${t("Cəm")}</th><th>${t("Qiymət")}</th><th>${t("Nəticə")}</th>${act ? html`<th></th>` : ""}</tr></thead><tbody>
    ${r.rows.map((x) => html`<tr><td>${x.full_name} <span class="tiny muted">${x.student_no || ""}</span></td><td class="small">${x.group_name || "—"}</td>
      <td>${x.raw == null ? "—" : `${x.raw} / ${x.raw_max}`}</td><td>${num(x.points)}</td><td>${num(x.semester)}</td><td>${num(x.total)}</td><td>${x.letter || "—"}</td>
      <td>${badge(RESULT, x.status)}</td>${act ? html`<td>${act(x)}</td>` : ""}</tr>`)}</tbody></table></div>`;
}

// The dean's office (Task 30): released exams; each group's statement is closed here (a QR document), and after that
// an exam score changes only here, with a reason and a grade appeal or an order number.
route("/office/exams", async (el) => {
  mount(el, loading());
  let list;
  try { list = await api.get("/api/exam-statements"); } catch (err) { return mount(el, failed(err.message)); }
  const crumbs = [[t("Əsas"), HOME[S.user.role] || "/"], [t("İmtahan-qiymət cədvəlləri")]];
  mount(el, html`${pageHead(t("İmtahan-qiymət cədvəlləri"), t("Nəticəsi açıqlanmış imtahanlar: hər qrupun cədvəlini bağlayın; bundan sonra balı yalnız dekanlıq apellyasiya qərarı və ya əmr əsasında dəyişə bilər."), "", crumbs)}
    <div class="card">${list.length ? html`<div class="table-wrap"><table class="table"><thead><tr><th>${t("İmtahan")}</th><th>${t("Fənn")}</th>
      <th>${t("Bağlanmış cədvəl")}</th><th></th></tr></thead><tbody>${list.map((e) => html`<tr><td><b class="small">${e.title}</b></td>
      <td class="small">${e.course_code} · ${e.course_name}</td><td>${e.closed} / ${e.groups}</td>
      <td><button class="btn btn-sm" data-groups="${e.id}">${t("Qruplar")}</button></td></tr>`)}</tbody></table></div>`
      : html`<div class="card-b">${empty("qr", t("Nəticəsi açıqlanmış imtahan yoxdur"), t("Müəllim nəticəni açıqladıqda imtahan burada görünür."))}</div>`}</div>`);
  const groups = async (eid) => {
    let st, res;
    try { [st, res] = await Promise.all([api.get(`/api/exams/${eid}/statements`), api.get(`/api/exams/${eid}/results`)]); } catch (err) { toast(err.message, "err"); return; }
    const closed = new Set(st.groups.filter((g) => g.closed).map((g) => g.group_id));
    const w = modal({ title: st.exam.title, size: "lg", body: html`<div class="stack">
      <div class="list">${st.groups.map((g) => html`<div class="list-item"><div class="grow"><b class="small">${g.group_name}</b>
        <div class="tiny muted">${t("{n} tələbə", { n: g.students })}${g.closed ? ` · ${g.reg_no}` : ""}</div></div>
        ${g.closed ? html`<button class="btn btn-sm" data-doc="${g.document_id}">${ic("qr", 14)} ${t("Cədvəl")}</button>`
          : html`<button class="btn btn-sm btn-primary" data-close-group="${g.group_id}">${t("Cədvəli bağla")}</button>`}</div>`)}</div>
      ${resultsTable(res, (x) => (closed.has(x.group_id) ? html`<button class="btn btn-sm" data-score="${x.student_id}">${t("Balı dəyiş")}</button>` : ""))}</div>` });
    on(w.el, "click", "[data-doc]", (ev, d) => openDoc(d.dataset.doc));
    on(w.el, "click", "[data-close-group]", async (ev, b) => {
      if (!confirm(t("Cədvəl bağlanacaq və QR kodlu sənəd kimi veriləcək. Bundan sonra balı yalnız dekanlıq dəyişə bilər. Davam edək?"))) return;
      try { await api.post(`/api/exams/${eid}/statements/${b.dataset.closeGroup}/close`); toast(t("Cədvəl bağlandı"), "ok"); w.close(); groups(eid); }
      catch (err) { toast(err.message, "err"); }
    });
    on(w.el, "click", "[data-score]", (ev, b) => {
      const x = res.rows.find((r) => r.student_id === Number(b.dataset.score));
      modal({ title: `${t("Balı dəyiş")} · ${x.full_name}`, body: html`<div class="stack">
          <div class="field"><label class="label" for="sc-score">${t("Yeni imtahan balı (0–{max})", { max: res.exam_max })}</label>
            <input class="input" id="sc-score" type="number" min="0" max="${res.exam_max}" step="0.1" value="${x.points ?? ""}"></div>
          <div class="field"><label class="label" for="sc-reason">${t("Səbəb")}</label><textarea class="input" id="sc-reason" rows="2" maxlength="300"></textarea></div>
          <div class="row wrap"><div class="field"><label class="label" for="sc-appeal">${t("Apellyasiya müraciətinin №")}</label><input class="input" id="sc-appeal" type="number" min="1"></div>
            <div class="field"><label class="label" for="sc-order">${t("və ya əmrin №")}</label><input class="input" id="sc-order" maxlength="40"></div></div></div>`,
        actions: [{ label: t("Saxla"), cls: "btn-primary", onClick: async (m) => {
          const appeal = m.querySelector("#sc-appeal").value;
          const body = { score: Number(m.querySelector("#sc-score").value), reason: m.querySelector("#sc-reason").value, order_no: m.querySelector("#sc-order").value };
          if (appeal) body.appeal_id = Number(appeal);
          try { await api.put(`/api/exams/${eid}/scores/${x.student_id}`, body); toast(t("Saxlanıldı: dəyişiklik qiymət jurnalındadır"), "ok"); w.close(); groups(eid); }
          catch (err) { toast(err.message, "err"); return false; }
        } }] });
    });
  };
  on(el, "click", "[data-groups]", (e, b) => groups(Number(b.dataset.groups)));
});
