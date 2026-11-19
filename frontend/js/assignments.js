// Assignments (Task 22): a course's teacher sets them, its students submit a text or a file, the teacher grades and
// the score goes to the grade journal's component (a draft there until published).
import { api, html, mount, on, ic, toast, modal, fmtDateTime, empty, fileToB64, t } from "./core.js";

const RULE = () => ({ mark: t("Gecikmiş göndəriş qəbul olunur, “gecikib” qeyd olunur"), refuse: t("Son tarixdən sonra qəbul olunmur") });

export async function teacherAssignments(tgt, c) {
  let list, cols = [];
  try {
    [list, cols] = await Promise.all([api.get(`/api/courses/${c.id}/assignments`),
      api.get(`/api/journal/courses/${c.id}/grades`).then((g) => g.columns.filter((x) => x.kind === "component")).catch(() => [])]);
  } catch (err) { mount(tgt, html`<div class="card pad">${err.message}</div>`); return; }
  mount(tgt, html`<div class="card"><div class="card-h wrap"><h3>${ic("file", 17)} ${t("Tapşırıqlar")}</h3>
      <button class="btn btn-primary btn-sm" id="as-new">${ic("plus", 15)} ${t("Yeni tapşırıq")}</button></div>
    ${list.length ? html`<div class="table-wrap"><table class="table"><thead><tr><th>${t("Tapşırıq")}</th><th>${t("Son tarix")}</th><th>${t("Komponent")}</th>
      <th>${t("Göndərilib")}</th><th>${t("Qiymətləndirilib")}</th><th></th></tr></thead><tbody>
      ${list.map((a) => html`<tr><td><b class="small">${a.title}</b><div class="tiny muted">${t("maks. {n}", { n: a.max_score })} · ${RULE()[a.late_rule]}</div></td>
        <td class="nowrap small">${a.due_at.replace("T", " ")}</td><td>${a.component}</td><td>${a.submitted}</td><td>${a.graded}</td>
        <td><button class="btn btn-sm" data-subs="${a.id}">${t("Göndərişlər")}</button></td></tr>`)}</tbody></table></div>`
      : html`<div class="card-b">${empty("file", t("Hələ tapşırıq yoxdur"), t("Tapşırığın balı qiymət jurnalının seçdiyiniz komponentinə düşür."))}</div>`}</div>`);
  on(tgt, "click", "#as-new", () => modal({ title: t("Yeni tapşırıq"), size: "lg", body: html`<div class="stack">
      <div class="field"><label class="label" for="as-title">${t("Ad")}</label><input class="input" id="as-title" maxlength="200"></div>
      <div class="field"><label class="label" for="as-body">${t("Tapşırığın mətni")}</label><textarea class="input" id="as-body" rows="5"></textarea></div>
      <div class="row wrap"><div class="field"><label class="label" for="as-due">${t("Son tarix")}</label><input class="input" id="as-due" type="datetime-local"></div>
        <div class="field"><label class="label" for="as-comp">${t("Komponent")}</label><select class="input" id="as-comp">${cols.map((x) => html`<option value="${x.key}">${x.name} (${t("maks. {n}", { n: x.max })})</option>`)}</select></div>
        <div class="field"><label class="label" for="as-max">${t("Maksimum bal")}</label><input class="input" id="as-max" type="number" min="0.5" step="0.5" value="5"></div></div>
      <div class="field"><label class="label" for="as-rule">${t("Gecikmə")}</label><select class="input" id="as-rule">${Object.entries(RULE()).map(([k, l]) => html`<option value="${k}">${l}</option>`)}</select></div></div>`,
    actions: [{ label: t("Saxla"), cls: "btn-primary", onClick: async (w) => {
      try {
        await api.post(`/api/courses/${c.id}/assignments`, { title: w.querySelector("#as-title").value, body: w.querySelector("#as-body").value,
          due_at: w.querySelector("#as-due").value, component: w.querySelector("#as-comp").value, max_score: Number(w.querySelector("#as-max").value),
          late_rule: w.querySelector("#as-rule").value });
        toast(t("Saxlanıldı"), "ok"); teacherAssignments(tgt, c);
      } catch (err) { toast(err.message, "err"); return false; }
    } }] }));
  on(tgt, "click", "[data-subs]", async (e, b) => {
    const a = list.find((x) => x.id === Number(b.dataset.subs));
    let subs;
    try { subs = await api.get(`/api/assignments/${a.id}/submissions`); } catch (err) { toast(err.message, "err"); return; }
    const m = modal({ title: a.title, size: "lg", body: subs.length ? html`<div class="stack">${subs.map((s) => html`<div class="card pad">
        <div class="row between wrap"><b>${s.student}</b><span class="small muted">${fmtDateTime(s.submitted_at)}${s.late ? html` <span class="badge b-amber">${t("gecikib")}</span>` : ""}</span></div>
        ${s.text ? html`<p class="small" style="white-space:pre-wrap">${s.text}</p>` : ""}
        ${s.file_id ? html`<a class="btn btn-sm" href="/api/files/${s.file_id}?download=1">${ic("download", 14)} ${s.filename || t("Fayl")}</a>` : ""}
        <div class="row wrap mt"><input class="input input-sm" type="number" min="0" max="${a.max_score}" step="0.5" style="width:90px" data-score="${s.id}" value="${s.score ?? ""}" aria-label="${t("Bal")}">
          <input class="input input-sm grow" data-fb="${s.id}" value="${s.feedback || ""}" placeholder="${t("Rəy")}" aria-label="${t("Rəy")}">
          <button class="btn btn-sm btn-primary" data-grade="${s.id}">${t("Qiymətləndir")}</button></div></div>`)}</div>`
      : html`<p class="muted" style="margin:0">${t("Hələ göndəriş yoxdur")}</p>` });
    on(m.el, "click", "[data-grade]", async (ev, g) => {
      const id = g.dataset.grade;
      try {
        await api.post(`/api/submissions/${id}/grade`, { score: Number(m.el.querySelector(`[data-score="${id}"]`).value),
          feedback: m.el.querySelector(`[data-fb="${id}"]`).value });
        toast(t("Bal jurnala yazıldı (qaralama)"), "ok");
      } catch (err) { toast(err.message, "err"); }
    });
  });
}

export async function studentAssignments(box, c) {
  let list;
  try { list = await api.get(`/api/courses/${c.id}/assignments`); } catch { return; }
  mount(box, html`<div class="card"><div class="card-h"><h3>${ic("file", 17)} ${t("Tapşırıqlar")}</h3></div><div class="card-b list">
    ${list.length ? list.map((a) => { const s = a.submission; return html`<div class="list-item"><div class="grow"><b class="small">${a.title}</b>
        <div class="tiny muted">${t("Son tarix")}: ${a.due_at.replace("T", " ")} · ${t("maks. {n}", { n: a.max_score })}</div>
        ${s ? html`<div class="tiny">${s.score != null ? html`<span class="badge b-green">${t("Bal: {n}", { n: s.score })}</span>${s.feedback ? html` <span class="muted">${s.feedback}</span>` : ""}`
          : html`<span class="badge b-blue">${t("Göndərilib")}</span>${s.late ? html` <span class="badge b-amber">${t("gecikib")}</span>` : ""}`}</div>` : ""}</div>
      ${!s || s.score == null ? html`<button class="btn btn-sm" data-submit="${a.id}">${s ? t("Yenidən göndər") : t("Göndər")}</button>` : ""}</div>`; })
      : empty("file", t("Tapşırıq yoxdur"))}</div></div>`);
  on(box, "click", "[data-submit]", (e, b) => {
    const a = list.find((x) => x.id === Number(b.dataset.submit));
    modal({ title: a.title, size: "lg", body: html`<div class="stack"><div class="small" style="white-space:pre-wrap">${a.body}</div>
        <div class="field"><label class="label" for="sub-text">${t("Cavab")}</label><textarea class="input" id="sub-text" rows="5"></textarea></div>
        <div class="field"><label class="label" for="sub-file">${t("Fayl (PDF, DOCX, JPG, PNG)")}</label><input class="input" id="sub-file" type="file" accept=".pdf,.docx,.jpg,.jpeg,.png"></div></div>`,
      actions: [{ label: t("Göndər"), cls: "btn-primary", onClick: async (w) => {
        try {
          const f = w.querySelector("#sub-file").files[0];
          const file_id = f ? (await api.post("/api/files", { filename: f.name, content_b64: await fileToB64(f) })).id : null;
          await api.post(`/api/assignments/${a.id}/submit`, { text: w.querySelector("#sub-text").value, file_id });
          toast(t("Göndərildi"), "ok"); studentAssignments(box, c);
        } catch (err) { toast(err.message, "err"); return false; }
      } }] });
  });
}
