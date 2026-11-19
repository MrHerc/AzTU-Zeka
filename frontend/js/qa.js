// The course forum (Task 33): topics of a course for its students and teachers, replies, the teacher's accepted
// answer, the AI draft the teacher alone sees, the course FAQ, reports; and the moderators' queue.
import { api, html, mount, on, ic, toast, modal, route, pageHead, loading, failed, empty, md, go, t } from "./core.js";

const byline = (x) => html`<span class="small muted">${x.author}${x.by_teacher ? html` · <b>${t("müəllim")}</b>` : ""} · ${(x.created_at || "").slice(0, 16).replace("T", " ")}</span>`;

const report = (topicId, replyId = null) => modal({ title: t("Şikayət et"),
  body: html`<label class="field"><span>${t("Səbəb")}</span><textarea class="input" name="reason" rows="3" maxlength="300"></textarea></label>`,
  actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Göndər"), cls: "btn-primary", onClick: async (w) => {
    try { await api.post("/api/qa/reports", { topic_id: topicId, reply_id: replyId, reason: w.querySelector("[name=reason]").value }); toast(t("Şikayət moderatorlara göndərildi"), "ok"); }
    catch (err) { toast(err.message, "err"); return false; }
  } }] });

route("/qa", async (el) => {
  mount(el, loading());
  let courses;
  try { courses = await api.get("/api/courses"); } catch (err) { return mount(el, failed(err.message)); }
  mount(el, html`${pageHead(t("Sual-cavab"), t("Fənnin müəllimi və qrup yoldaşları ilə sual-cavab"))}
    ${courses.length ? html`<div class="grid g-3">${courses.map((c) => html`<button class="card clickable" data-go="/qa/${c.id}" style="text-align:left">
      <b>${c.name}</b><div class="small muted">${c.code || ""}</div></button>`)}</div>` : empty(t("Fənniniz yoxdur"))}`);
  on(el, "click", "[data-go]", (e, b) => go(b.dataset.go));
});

route("/qa/:cid", async (el, p) => {
  mount(el, loading());
  let topics;
  try { topics = await api.get(`/api/courses/${p.cid}/qa`); } catch (err) { return mount(el, failed(err.message)); }
  mount(el, html`${pageHead(t("Fənn forumu"), t("Suallar yalnız bu fənnin tələbələrinə və müəlliminə görünür"), html`<button class="btn btn-primary" data-new>${ic("plus", 15)} ${t("Sual ver")}</button>`)}
    ${topics.length ? html`<div class="card"><table class="table"><tbody>${topics.map((x) => html`<tr class="clickable" data-go="/qa/${p.cid}/${x.id}" tabindex="0">
      <td><b>${x.title}</b> ${x.tag ? html`<span class="badge b-gray">${x.tag}</span>` : ""} ${x.faq ? html`<span class="badge b-blue">FAQ</span>` : ""}
        ${x.hidden ? html`<span class="badge b-amber">${t("Gizlədilib")}</span>` : ""}<div>${byline(x)}</div></td>
      <td><span class="badge ${x.status === "answered" ? "b-green" : "b-gray"}">${x.status === "answered" ? t("Cavablanıb") : t("Açıq")}</span></td>
      <td class="small muted">${t("{n} cavab", { n: x.replies })}</td></tr>`)}</tbody></table></div>` : empty(t("Hələ sual yoxdur"))}`);
  on(el, "click", "[data-go]", (e, b) => go(b.dataset.go));
  on(el, "keydown", "[data-go]", (e, b) => { if (e.key === "Enter") go(b.dataset.go); });
  on(el, "click", "[data-new]", () => modal({ title: t("Sual ver"),
    body: html`<div class="stack"><label class="field"><span>${t("Başlıq")}</span><input class="input" name="title" maxlength="140"></label>
      <label class="field"><span>${t("Sual")}</span><textarea class="input" name="text" rows="6" maxlength="4000"></textarea></label>
      <label class="field"><span>${t("Həftə və ya mövzu (könüllü)")}</span><input class="input" name="tag" maxlength="40"></label>
      <label class="row" style="gap:6px"><input type="checkbox" name="anonymous"> ${t("Qrup yoldaşlarına anonim göstər (müəllim adınızı görür)")}</label></div>`,
    actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Göndər"), cls: "btn-primary", onClick: async (w) => {
      const v = (k) => w.querySelector(`[name=${k}]`);
      try {
        const r = await api.post(`/api/courses/${p.cid}/qa`, { title: v("title").value, text: v("text").value, tag: v("tag").value, anonymous: v("anonymous").checked });
        go(`/qa/${p.cid}/${r.id}`);
      } catch (err) { toast(err.message, "err"); return false; }
    } }] }));
});

route("/qa/:cid/:tid", async (el, p) => {
  const draw = (x) => mount(el, html`${pageHead(x.title, "", "", [[t("Fənn forumu"), `/qa/${p.cid}`]])}
    <div class="card stack">${byline(x)} ${x.tag ? html`<span class="badge b-gray">${x.tag}</span>` : ""}<div class="md">${md(x.text)}</div>
      <div class="row" style="gap:8px">${!x.mine ? html`<button class="btn btn-ghost btn-sm" data-report>${ic("alert", 14)} ${t("Şikayət et")}</button>` : ""}
        ${x.can_moderate_course ? html`<button class="btn btn-ghost btn-sm" data-faq="${x.faq ? "0" : "1"}">${ic("bookmark", 14)} ${x.faq ? t("FAQ-dan çıxar") : t("FAQ-a əlavə et")}</button>
          <button class="btn btn-ai btn-sm" data-draft>${ic("sparkles", 14)} ${t("AI qaralaması")}</button>` : ""}</div></div>
    ${x.can_moderate_course && x.ai_draft ? html`<div class="card"><b>${t("AI qaralaması (yalnız siz görürsünüz)")}</b><div class="md">${md(x.ai_draft)}</div>
      <button class="btn btn-sm" data-use>${t("Cavab sahəsinə köçür")}</button></div>` : ""}
    ${x.replies.map((r) => html`<div class="card ${r.accepted ? "accepted" : ""}">${byline(r)}
      ${r.accepted ? html` <span class="badge b-green">${ic("check", 12)} ${t("Təsdiqlənmiş cavab")}</span>` : ""}
      ${r.hidden ? html` <span class="badge b-amber">${t("Gizlədilib")}</span>` : ""}<div class="md">${md(r.text)}</div>
      <div class="row" style="gap:8px">${x.can_moderate_course && !r.accepted && !r.hidden ? html`<button class="btn btn-sm" data-accept="${r.id}">${t("Cavabı təsdiqlə")}</button>` : ""}
        ${!r.mine ? html`<button class="btn btn-ghost btn-sm" data-report-reply="${r.id}">${t("Şikayət et")}</button>` : ""}</div></div>`)}
    <div class="card stack"><label class="field"><span>${t("Cavab yaz")}</span><textarea class="input" id="qa-reply" rows="4" maxlength="4000"></textarea></label>
      <button class="btn btn-primary" data-reply>${t("Göndər")}</button></div>`);
  let x;
  const load = async () => { try { x = await api.get(`/api/qa/topics/${p.tid}`); draw(x); } catch (err) { mount(el, failed(err.message)); } };
  const act = async (fn) => { try { x = await fn(); draw(x); } catch (err) { toast(err.message, "err"); } };
  on(el, "click", "[data-reply]", () => act(async () => { const r = await api.post(`/api/qa/topics/${p.tid}/replies`, { text: el.querySelector("#qa-reply").value }); return r; }));
  on(el, "click", "[data-accept]", (e, b) => act(() => api.post(`/api/qa/replies/${b.dataset.accept}/accept`)));
  on(el, "click", "[data-faq]", (e, b) => act(() => api.post(`/api/qa/topics/${p.tid}/faq`, { on: b.dataset.faq === "1" })));
  on(el, "click", "[data-draft]", async (e, b) => { b.disabled = true; try { const d = await api.post(`/api/qa/topics/${p.tid}/draft`); x.ai_draft = d.ai_draft; draw(x); } catch (err) { b.disabled = false; toast(err.message, "err"); } });
  on(el, "click", "[data-use]", () => { el.querySelector("#qa-reply").value = x.ai_draft; el.querySelector("#qa-reply").focus(); });
  on(el, "click", "[data-report]", () => report(+p.tid));
  on(el, "click", "[data-report-reply]", (e, b) => report(+p.tid, +b.dataset.reportReply));
  mount(el, loading());
  await load();
});

route("/staff/qa", async (el) => {
  const load = async () => {
    let list;
    try { list = await api.get("/api/qa/reports"); } catch (err) { return mount(el, failed(err.message)); }
    mount(el, html`${pageHead(t("Forum şikayətləri"), t("Fənn forumlarından gələn şikayətlər: gizlət və ya saxla; hər addım auditdədir"))}
      ${list.length ? list.map((r) => html`<div class="card stack"><div class="small muted">${r.course} · ${r.created_at.slice(0, 16).replace("T", " ")} · ${t("şikayət edən")}: ${r.reporter}</div>
        <b>${r.title}</b><div class="small">${t("Müəllif")}: ${r.reply_id ? r.reply_author : r.topic_author}${!r.reply_id && r.anonymous ? html` (${t("anonim")})` : ""}</div>
        <blockquote>${r.reply_id ? r.reply_text : r.question}</blockquote><div><b>${t("Səbəb")}:</b> ${r.reason}</div>
        <div class="row" style="gap:8px"><button class="btn btn-danger btn-sm" data-resolve="${r.id}" data-action="hide">${t("Gizlət")}</button>
          <button class="btn btn-ghost btn-sm" data-resolve="${r.id}" data-action="keep">${t("Saxla")}</button></div></div>`) : empty(t("Açıq şikayət yoxdur"))}`);
  };
  on(el, "click", "[data-resolve]", async (e, b) => {
    try { await api.post(`/api/qa/reports/${b.dataset.resolve}/resolve`, { action: b.dataset.action }); toast(t("Qeyd olundu"), "ok"); load(); }
    catch (err) { toast(err.message, "err"); }
  });
  mount(el, loading());
  await load();
});
