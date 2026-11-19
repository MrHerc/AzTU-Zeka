// Clubs and channels (Task 35): clubs a dean's office approved, membership, chat and announcement channels polled
// every 3 seconds, the code of conduct before the first post, reports, and the moderators' tools.
import { api, html, mount, on, ic, toast, modal, route, pageHead, loading, failed, empty, go, t, S } from "./core.js";

const POLL_MS = 3000;
const when = (iso) => (iso || "").slice(0, 16).replace("T", " ");
const CONDUCT = () => t("Hörmətli olun, şəxsi məlumat paylaşmayın, akademik dürüstlüyü pozan material (cavab, hazır iş) göndərməyin, reklam etməyin. Qaydanı pozan mesaj gizlədilir, üzv susdurula və ya klubdan çıxarıla bilər.");

route("/clubs", async (el) => {
  const draw = async () => {
    let list;
    try { list = await api.get("/api/clubs"); } catch (err) { return mount(el, failed(err.message)); }
    const state = (c) => c.status !== "approved" ? html`<span class="badge b-amber">${c.status === "pending" ? t("Təsdiq gözləyir") : t("Rədd edilib")}</span>`
      : c.my_status === "member" ? html`<span class="badge b-green">${c.my_role === "leader" ? t("Rəhbər") : t("Üzv")}</span>`
      : c.my_status === "requested" ? html`<span class="badge b-gray">${t("Sorğu göndərilib")}</span>`
      : c.my_status === "removed" ? "" : html`<button class="btn btn-sm" data-join="${c.id}">${t("Qoşul")}</button>`;
    mount(el, html`${pageHead(t("Klublar"), t("Tələbə klubları və onların kanalları"), html`<button class="btn btn-primary" data-new>${ic("plus", 15)} ${t("Klub təklif et")}</button>`)}
      ${list.length ? html`<div class="grid g-3">${list.map((c) => html`<div class="card club-card"><b class="clickable" data-go="/clubs/${c.id}">${c.name}</b>
        <div class="small muted">${c.leader} · ${t("{n} üzv", { n: c.members })}</div><p class="small">${c.description}</p><div>${state(c)}</div></div>`)}</div>`
        : empty(t("Hələ klub yoxdur"))}`);
  };
  on(el, "click", "[data-go]", (e, b) => go(b.dataset.go));
  on(el, "click", "[data-join]", async (e, b) => { try { await api.post(`/api/clubs/${b.dataset.join}/join`); toast(t("Sorğu göndərildi"), "ok"); draw(); } catch (err) { toast(err.message, "err"); } });
  on(el, "click", "[data-new]", () => modal({ title: t("Klub təklif et"),
    body: html`<div class="stack"><label class="field"><span>${t("Ad")}</span><input class="input" name="name" maxlength="80"></label>
      <label class="field"><span>${t("Təsvir")}</span><textarea class="input" name="description" rows="4" maxlength="1000"></textarea></label>
      <p class="small muted">${t("Klubu dekanlıq təsdiqləyir; siz onun rəhbəri olursunuz.")}</p></div>`,
    actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Göndər"), cls: "btn-primary", onClick: async (w) => {
      try { await api.post("/api/clubs", { name: w.querySelector("[name=name]").value, description: w.querySelector("[name=description]").value }); toast(t("Təklif dekanlığa göndərildi"), "ok"); draw(); }
      catch (err) { toast(err.message, "err"); return false; }
    } }] }));
  mount(el, loading());
  await draw();
});

route("/clubs/:id", async (el, p) => {
  let info, channel = null, last = 0, timer = null, msgs = [];
  const stop = () => { clearTimeout(timer); timer = null; };
  const msgRow = (m) => html`<div class="club-msg ${m.hidden ? "hidden-msg" : ""}" data-mid="${m.id}"><div class="small muted"><b>${m.author}</b> · ${when(m.created_at)}
      ${m.hidden ? html` · <span class="badge b-amber">${t("Gizlədilib")}</span>` : ""}</div><div class="club-text">${m.text}</div>
    <div class="row" style="gap:6px">${m.author_id !== S.user.id ? html`<button class="btn btn-ghost btn-xs" data-report="${m.id}">${t("Şikayət et")}</button>` : ""}
      ${info.moderates && !m.hidden ? html`<button class="btn btn-ghost btn-xs" data-hide="${m.id}">${t("Gizlət")}</button>` : ""}</div></div>`;
  const drawMsgs = () => { const box = el.querySelector("#club-msgs"); if (box) { mount(box, html`${msgs.length ? msgs.map(msgRow) : empty(t("Hələ mesaj yoxdur"))}`); box.scrollTop = box.scrollHeight; } };
  const poll = async () => {
    if (!el.isConnected || !channel) return stop();
    try {
      const r = await api.get(`/api/channels/${channel.id}/messages${last ? `?since_id=${last}` : ""}`);
      if (r.messages.length) { msgs = last ? msgs.concat(r.messages) : r.messages; last = msgs[msgs.length - 1].id; drawMsgs(); }
    } catch (err) { if (err.status === 403) { stop(); return mount(el, failed(err.message)); } }
    timer = setTimeout(poll, POLL_MS);
  };
  const open = (ch) => { stop(); channel = ch; last = 0; msgs = []; draw(); poll(); };
  const draw = () => {
    const c = info.club, m = info.membership;
    const canWrite = channel && (channel.kind === "chat" || (m && m.role === "leader"));
    mount(el, html`${pageHead(c.name, c.description, "", [[t("Klublar"), "/clubs"]])}
      ${!m || m.status !== "member" ? html`<div class="card">${m && m.status === "requested" ? t("Sorğunuz rəhbərin təsdiqini gözləyir.") : t("Kanalları yalnız klubun üzvləri görür.")}</div>` : html`
      <div class="club-layout"><nav class="card club-channels">${info.channels.map((ch) => html`<button class="btn ${channel && ch.id === channel.id ? "btn-primary" : "btn-ghost"} btn-sm" data-ch="${ch.id}">
          ${ch.kind === "announce" ? ic("megaphone", 14) : ic("message", 14)} ${ch.name}</button>`)}
        ${info.moderates ? html`<button class="btn btn-ghost btn-sm" data-members>${ic("users", 14)} ${t("Üzvlər")}</button>` : ""}</nav>
        <section class="card club-chat">${channel ? html`<div id="club-msgs" class="club-msgs" aria-live="polite"></div>
          ${canWrite ? html`<div class="row" style="gap:8px"><textarea class="input grow" id="club-text" rows="2" maxlength="2000" aria-label="${t("Mesaj")}"></textarea>
            <button class="btn btn-primary" data-send>${ic("send", 15)}</button></div>` : html`<p class="small muted">${t("Bu kanala yalnız klubun rəhbəri yazır.")}</p>`}`
          : empty(t("Kanal seçin"))}</section></div>`}`);
    drawMsgs();
  };
  const send = async () => {
    const box = el.querySelector("#club-text");
    try { await api.post(`/api/channels/${channel.id}/messages`, { text: box.value }); box.value = ""; stop(); poll(); }
    catch (err) {
      if (err.status === 409) return modal({ title: t("Davranış qaydaları"), body: html`<p>${CONDUCT()}</p>`,
        actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Qəbul edirəm"), cls: "btn-primary", onClick: async () => {
          await api.post(`/api/clubs/${p.id}/conduct`); info = await api.get(`/api/clubs/${p.id}`); send();
        } }] });
      toast(err.message, "err");
    }
  };
  on(el, "click", "[data-ch]", (e, b) => open(info.channels.find((x) => x.id === +b.dataset.ch)));
  on(el, "click", "[data-send]", send);
  on(el, "keydown", "#club-text", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
  on(el, "click", "[data-report]", (e, b) => modal({ title: t("Şikayət et"), body: html`<label class="field"><span>${t("Səbəb")}</span><textarea class="input" name="reason" rows="3" maxlength="300"></textarea></label>`,
    actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Göndər"), cls: "btn-primary", onClick: async (w) => {
      try { await api.post(`/api/club-messages/${b.dataset.report}/report`, { reason: w.querySelector("[name=reason]").value }); toast(t("Şikayət moderatorlara göndərildi"), "ok"); }
      catch (err) { toast(err.message, "err"); return false; }
    } }] }));
  on(el, "click", "[data-hide]", async (e, b) => { try { await api.post(`/api/club-messages/${b.dataset.hide}/hide`); last = 0; stop(); poll(); } catch (err) { toast(err.message, "err"); } });
  on(el, "click", "[data-members]", async () => {
    let people;
    try { people = await api.get(`/api/clubs/${p.id}/members`); } catch (err) { return toast(err.message, "err"); }
    const act = async (uid, action, body = {}) => { try { await api.post(`/api/clubs/${p.id}/members/${uid}/${action}`, body); toast(t("Qeyd olundu"), "ok"); } catch (err) { toast(err.message, "err"); } };
    modal({ title: t("Üzvlər"), body: html`<table class="table"><tbody>${people.map((x) => html`<tr><td>${x.full_name}</td><td class="small">${x.role === "leader" ? t("Rəhbər") : x.status}
        ${x.muted_until ? html` · ${t("susdurulub: {until}", { until: when(x.muted_until) })}` : ""}</td>
      <td>${x.role !== "leader" ? html`${x.status === "requested" ? html`<button class="btn btn-sm" data-act="approve" data-uid="${x.user_id}">${t("Qəbul et")}</button>` : ""}
        ${x.status === "member" ? html`<button class="btn btn-ghost btn-sm" data-act="mute" data-uid="${x.user_id}">${t("Sustur")}</button>` : ""}
        ${x.status !== "removed" ? html`<button class="btn btn-danger btn-sm" data-act="remove" data-uid="${x.user_id}">${t("Çıxar")}</button>` : ""}` : ""}</td></tr>`)}</tbody></table>`,
      actions: [{ label: t("Bağla"), cls: "btn-ghost" }],
      onMount: (w) => on(w, "click", "[data-act]", async (e, b) => {
        if (b.dataset.act === "mute") {
          const reason = prompt(t("Səbəb"));
          if (reason) await act(b.dataset.uid, "mute", { minutes: 60, reason });
        } else await act(b.dataset.uid, b.dataset.act);
      }) });
  });
  mount(el, loading());
  try { info = await api.get(`/api/clubs/${p.id}`); } catch (err) { return mount(el, failed(err.message)); }
  if (info.channels.length) open(info.channels[0]); else draw();
});

route("/staff/clubs", async (el) => {
  const load = async () => {
    let pending = [], reports = [];
    try {
      [pending, reports] = await Promise.all([api.get("/api/clubs/pending").catch(() => []), api.get("/api/community/reports")]);
    } catch (err) { return mount(el, failed(err.message)); }
    mount(el, html`${pageHead(t("Klublar və şikayətlər"), t("Təklif olunan klubların təsdiqi və kanal şikayətləri; hər addım auditdədir"))}
      <div class="card stack"><b>${t("Təsdiq gözləyən klublar")}</b>${pending.length ? pending.map((c) => html`<div class="row wrap" style="gap:8px;justify-content:space-between">
        <div><b>${c.name}</b> · <span class="small muted">${c.leader}</span><div class="small">${c.description}</div></div>
        <div class="row" style="gap:6px"><button class="btn btn-primary btn-sm" data-decide="${c.id}" data-ok="1">${t("Təsdiqlə")}</button>
          <button class="btn btn-ghost btn-sm" data-decide="${c.id}" data-ok="0">${t("Rədd et")}</button></div></div>`) : empty(t("Gözləyən klub yoxdur"))}</div>
      <div class="card stack"><b>${t("Şikayətlər")}</b>${reports.length ? reports.map((r) => html`<div class="stack"><div class="small muted">${r.club} · ${when(r.created_at)} · ${t("şikayət edən")}: ${r.reporter}</div>
        <div><b>${r.author}:</b> ${r.text}</div><div><b>${t("Səbəb")}:</b> ${r.reason}</div>
        <div class="row" style="gap:6px"><button class="btn btn-danger btn-sm" data-resolve="${r.id}" data-action="hide">${t("Gizlət")}</button>
          <button class="btn btn-ghost btn-sm" data-resolve="${r.id}" data-action="keep">${t("Saxla")}</button></div></div>`) : empty(t("Açıq şikayət yoxdur"))}</div>`);
  };
  on(el, "click", "[data-decide]", async (e, b) => { try { await api.post(`/api/clubs/${b.dataset.decide}/decide`, { approve: b.dataset.ok === "1" }); load(); } catch (err) { toast(err.message, "err"); } });
  on(el, "click", "[data-resolve]", async (e, b) => { try { await api.post(`/api/community/reports/${b.dataset.resolve}/resolve`, { action: b.dataset.action }); load(); } catch (err) { toast(err.message, "err"); } });
  mount(el, loading());
  await load();
});
