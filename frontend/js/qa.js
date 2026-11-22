// The course forum (Task 33): topics of a course for its students and teachers, replies, the teacher's accepted
// answer, the AI draft the teacher alone sees, the course FAQ, reports; and the moderators' queue.
import { api, html, mount, on, ic, toast, modal, route, pageHead, loading, failed, empty, md, go, t, S } from "./core.js";

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
      <b>${c.name}</b><div class="small muted">${c.code || ""}</div></button>`)}</div>` : empty("inbox", t("Fənniniz yoxdur"))}`);
  on(el, "click", "[data-go]", (e, b) => go(b.dataset.go));
});

route("/qa/:cid", async (el, p) => {
  mount(el, loading());
  let topics;
  try { topics = await api.get(`/api/courses/${p.cid}/qa`); } catch (err) { return mount(el, failed(err.message)); }
  mount(el, html`${pageHead(t("Fənn forumu"), t("Suallar yalnız bu fənnin tələbələrinə və müəlliminə görünür"), html`<button class="btn btn-primary" data-new>${ic("plus", 15)} ${t("Sual ver")}</button>`)}
    ${topics.length ? html`<div class="card"><table class="table"><tbody>${topics.map((x) => html`<tr class="clickable" data-go="/qa/${p.cid}/${x.id}" tabindex="0">
      <td><b>${x.title}</b> ${x.tag ? html`<span class="badge b-gray">${x.tag}</span>` : ""} ${x.faq ? html`<span class="badge b-blue">FAQ</span>` : ""}
        ${x.hidden ? html`<span class="badge b-amber">${t("Gizlədilib")}</span>` : ""} ${x.private ? html`<span class="badge b-gray" title="${t("Yalnız müəllif və fənnin müəllimləri görür")}">${t("Şəxsi")}</span>` : ""}<div>${byline(x)}</div></td>
      <td><span class="badge ${x.status === "answered" ? "b-green" : "b-gray"}">${x.status === "answered" ? t("Cavablanıb") : t("Açıq")}</span></td>
      <td class="small muted">${t("{n} cavab", { n: x.replies })}</td></tr>`)}</tbody></table></div>` : empty("inbox", t("Hələ sual yoxdur"))}`);
  on(el, "click", "[data-go]", (e, b) => go(b.dataset.go));
  on(el, "keydown", "[data-go]", (e, b) => { if (e.key === "Enter") go(b.dataset.go); });
  on(el, "click", "[data-new]", () => modal({ title: t("Sual ver"),
    body: html`<div class="stack"><label class="field"><span>${t("Başlıq")}</span><input class="input" name="title" maxlength="140"></label>
      <label class="field"><span>${t("Sual")}</span><textarea class="input" name="text" rows="6" maxlength="4000"></textarea></label>
      <label class="field"><span>${t("Həftə və ya mövzu (istəyə görə)")}</span><input class="input" name="tag" maxlength="40"></label>
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
    <div class="card stack">${byline(x)} ${x.tag ? html`<span class="badge b-gray">${x.tag}</span>` : ""} ${x.private ? html`<span class="badge b-gray" title="${t("Yalnız müəllif və fənnin müəllimləri görür")}">${t("Şəxsi")}</span>` : ""}<div class="md">${md(x.text)}</div>
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
  on(el, "click", "[data-draft]", async (e, b) => { b.disabled = true; try { const d = await api.post(`/api/qa/topics/${p.tid}/draft`); if (d.no_source) toast(t("Fənn materiallarında bu suala uyğun mənbə tapılmadı"), "err"); x.ai_draft = d.ai_draft; draw(x); } catch (err) { b.disabled = false; toast(err.message, "err"); } });
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
    mount(el, html`${pageHead(t("Forum şikayətləri"), t("Fənn forumlarından gələn şikayətlər: gizlət və ya saxla; hər addım audit jurnalına yazılır"))}
      ${list.length ? list.map((r) => html`<div class="card stack"><div class="small muted">${r.course} · ${r.created_at.slice(0, 16).replace("T", " ")} · ${t("şikayət edən")}: ${r.reporter}</div>
        <b>${r.title}</b><div class="small">${t("Müəllif")}: ${r.reply_id ? r.reply_author : r.topic_author}${!r.reply_id && r.anonymous ? html` (${t("anonim")})` : ""}</div>
        <blockquote>${r.reply_id ? r.reply_text : r.question}</blockquote><div><b>${t("Səbəb")}:</b> ${r.reason}</div>
        <div class="row" style="gap:8px"><button class="btn btn-danger btn-sm" data-resolve="${r.id}" data-action="hide">${t("Gizlət")}</button>
          <button class="btn btn-ghost btn-sm" data-resolve="${r.id}" data-action="keep">${t("Saxla")}</button></div></div>`) : empty("inbox", t("Açıq şikayət yoxdur"))}`);
  };
  on(el, "click", "[data-resolve]", async (e, b) => {
    try { await api.post(`/api/qa/reports/${b.dataset.resolve}/resolve`, { action: b.dataset.action }); toast(t("Qeyd olundu"), "ok"); load(); }
    catch (err) { toast(err.message, "err"); }
  });
  mount(el, loading());
  await load();
});

// ---- office hours (Task 34): a teacher's weekly ranges; a student books one slot; either side cancels
const WEEKDAY = () => ["", t("Bazar ertəsi"), t("Çərşənbə axşamı"), t("Çərşənbə"), t("Cümə axşamı"), t("Cümə"), t("Şənbə")];

route("/office-hours", async (el) => {
  const teacher = ["teacher", "dept_head"].includes(S.user.role);
  let pick = null;
  const bookingRow = (b) => html`<tr><td>${b.day} ${b.start}–${b.end}</td><td>${teacher ? b.student : b.teacher}</td><td class="small">${b.place || b.online_url || ""}</td>
    <td class="small">${b.topic || ""}</td><td>${b.status === "booked" ? html`<button class="btn btn-ghost btn-sm" data-cancel="${b.id}">${t("Ləğv et")}</button>`
      : html`<span class="badge b-gray">${t("Ləğv olunub")}</span>`}</td></tr>`;
  const load = async () => {
    try {
      const bookings = await api.get("/api/office-hours/bookings");
      const mine = html`<div class="card"><b>${t("Görüşlər")}</b>${bookings.length ? html`<table class="table"><tbody>${bookings.map(bookingRow)}</tbody></table>` : empty("inbox", t("Görüş yoxdur"))}</div>`;
      if (teacher) {
        const hours = await api.get("/api/office-hours");
        return mount(el, html`${pageHead(t("Qəbul saatları"), t("Həftəlik qəbul saatlarınız: tələbələr iki həftə əvvəlcədən qəbula yazıla bilər"))}
          <div class="card stack"><b>${t("Həftəlik aralıqlar")}</b>
            ${hours.map((h) => html`<div class="row" style="gap:8px">${WEEKDAY()[h.weekday]}, ${h.start}–${h.end} · ${t("{n} dəq.", { n: h.slot_min })} · ${h.place || h.online_url}
              <button class="btn btn-ghost btn-sm" data-end="${h.id}">${t("Bitir")}</button></div>`)}
            <div class="row wrap" style="gap:8px"><select class="input" name="weekday">${WEEKDAY().slice(1).map((d, i) => html`<option value="${i + 1}">${d}</option>`)}</select>
              <input class="input" name="start" type="time" value="14:00" aria-label="${t("Başlanğıc")}"><input class="input" name="end" type="time" value="16:00" aria-label="${t("Son")}">
              <select class="input" name="slot_min">${[10, 15, 20, 30, 45, 60].map((m) => html`<option value="${m}" ${m === 15 ? "selected" : ""}>${t("{n} dəq.", { n: m })}</option>`)}</select>
              <input class="input" name="place" placeholder="${t("Otaq, məsələn EK-305")}"><input class="input" name="online_url" placeholder="https://…">
              <button class="btn btn-primary" data-add>${t("Əlavə et")}</button></div></div>${mine}`);
      }
      const teachers = await api.get("/api/office-hours/teachers");
      pick ||= teachers[0] && teachers[0].id;
      const slots = pick ? await api.get(`/api/office-hours/teachers/${pick}/free`) : [];
      const days = [...new Set(slots.map((s) => s.day))];
      mount(el, html`${pageHead(t("Qəbul saatları"), t("Müəlliminizin qəbuluna yazılın"))}
        <div class="card stack"><label class="field"><span>${t("Müəllim")}</span><select class="input" id="oh-teacher">
          ${teachers.map((x) => html`<option value="${x.id}" ${x.id === pick ? "selected" : ""}>${x.full_name}</option>`)}</select></label>
          ${days.length ? days.map((d) => html`<div><b>${d}</b><div class="row wrap" style="gap:6px">${slots.filter((s) => s.day === d).map((s) =>
            html`<button class="btn btn-sm" data-slot="${s.hours_id}|${s.day}|${s.start}">${s.start}</button>`)}</div></div>`) : empty("inbox", t("Boş vaxt yoxdur"))}</div>${mine}`);
    } catch (err) { mount(el, failed(err.message)); }
  };
  on(el, "change", "#oh-teacher", (e, s) => { pick = +s.value; load(); });
  on(el, "click", "[data-slot]", (e, b) => {
    const [hours_id, day, start] = b.dataset.slot.split("|");
    modal({ title: t("Qəbula yazıl: {day} {start}", { day, start }), body: html`<label class="field"><span>${t("Mövzu (istəyə görə)")}</span><input class="input" name="topic" maxlength="300"></label>`,
      actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Qəbula yazıl"), cls: "btn-primary", onClick: async (w) => {
        try { await api.post("/api/office-hours/book", { hours_id: +hours_id, day, start, topic: w.querySelector("[name=topic]").value }); toast(t("Qəbula yazıldınız"), "ok"); load(); }
        catch (err) { toast(err.message, "err"); load(); }
      } }] });
  });
  on(el, "click", "[data-cancel]", async (e, b) => {
    try { await api.post(`/api/office-hours/bookings/${b.dataset.cancel}/cancel`); toast(t("Görüş ləğv olundu"), "ok"); load(); } catch (err) { toast(err.message, "err"); }
  });
  on(el, "click", "[data-end]", async (e, b) => {
    try { await api.post(`/api/office-hours/${b.dataset.end}/end`); load(); } catch (err) { toast(err.message, "err"); }
  });
  on(el, "click", "[data-add]", async () => {
    const v = (k) => el.querySelector(`[name=${k}]`).value;
    try { await api.post("/api/office-hours", { weekday: +v("weekday"), start: v("start"), end: v("end"), slot_min: +v("slot_min"), place: v("place"), online_url: v("online_url") }); load(); }
    catch (err) { toast(err.message, "err"); }
  });
  mount(el, loading());
  await load();
});
