import { api, html, raw, mount, on, md, icon, ic, toast, modal, confirmBox, esc, highlight, MODE_LABEL, LANG, go, sleep, S, t, infoTip, empty, failed } from "./core.js";

/**
 * Shared chat component — AI tutor (/student/tutor/:cid, teacher tutor test) and campus assistant (/student/campus).
 * cfg: { kind: "tutor"|"campus", base: "/api/tutor/1" | "/api/campus", modes, mode, suggestions,
 *        title, text, locked, canForward, prefill }
 * Signature chatView(el, cfg) and every cfg field are preserved for student.js / teacher.js callers.
 */
export async function chatView(el, cfg) {
  const st = { messages: [], mode: cfg.mode || (cfg.modes || ["socratic"])[0], busy: false, usage: null, lastQuestion: "", lastError: null };
  const histUrl = cfg.kind === "tutor" ? `${cfg.base}/history` : "/api/campus/history";
  const askUrl = cfg.kind === "tutor" ? `${cfg.base}/ask` : "/api/campus/ask";
  const clearUrl = cfg.kind === "tutor" ? `${cfg.base}/clear` : "/api/campus/clear";
  // Course quotes stay in the language of instruction (Azerbaijani); flag it for EN/RU users.
  const langTip = LANG !== "az"
    ? infoTip(t("Fənn materialları tədris dilində (azərbaycan dilində) təqdim olunur; sitatlar orijinal dildə göstərilir.")).__html
    : "";

  mount(el, html`
    <div class="chat-wrap">
      <div class="card chat">
        <div class="chat-top">
          <div class="row wrap">
            ${cfg.modes ? html`<div class="seg" id="modes" data-tour="chat-modes" role="tablist" aria-label="${t("Söhbət rejimi")}">${cfg.modes.map((m) => html`<button data-mode="${m}" role="tab" aria-selected="${m === st.mode}" class="${m === st.mode ? "active" : ""}" title="${modeHint(m)}" aria-label="${t("Rejim: {mode}", { mode: MODE_LABEL[m] })} — ${modeHint(m)}">${MODE_LABEL[m]}</button>`)}</div>` : ""}
            <span class="badge b-navy">${ic("cpu", 13)} ${S.app.engine.label}</span>
            ${raw(langTip)}
          </div>
          <button class="btn btn-ghost btn-sm" id="clear">${ic("refresh", 15)} ${t("Yeni söhbət")}</button>
        </div>
        ${cfg.locked ? lockedBanner() : ""}
        <div class="chat-scroll" id="cs" aria-live="polite" aria-label="${t("Söhbət")}"></div>
        <div class="composer" data-tour="chat-input">
          <div class="composer-box">
            <textarea id="inp" rows="1" maxlength="2000" aria-label="${cfg.kind === "tutor" ? t("Fənn üzrə sualınız") : t("Universitet qaydaları barədə sualınız")}"
              placeholder="${cfg.kind === "tutor" ? t("Fənn üzrə sualınızı yazın…") : t("Universitet qaydaları barədə soruşun…")}" ${cfg.locked ? "disabled" : ""}></textarea>
            <button class="btn btn-ai btn-icon" id="send" title="${t("Göndər (Enter)")}" aria-label="${t("Göndər")}" ${cfg.locked ? "disabled" : ""}>${ic("send", 17)}</button>
          </div>
          <div class="composer-foot">
            <span>${ic("shield", 13)} ${t("Şəxsi məlumatlar AI-a göndərilməzdən əvvəl maskalanır. AI səhv edə bilər — mənbəni yoxlayın.")}</span>
            <span id="usage" data-tour="chat-usage"></span>
          </div>
        </div>
      </div>
      <div class="card side-panel" data-tour="chat-sources">
        <div class="card-h"><h3>${ic("book", 17)} ${t("Mənbə")}</h3></div>
        <div class="card-b src-view" id="src">${srcPlaceholder(cfg)}</div>
      </div>
    </div>`);
  const cs = el.querySelector("#cs"), inp = el.querySelector("#inp"), srcEl = el.querySelector("#src");
  const isMobile = () => window.matchMedia("(max-width: 1220px)").matches;

  function modeHint(m) {
    return {
      socratic: t("Hazır cavab vermir, addım-addım düşünməyə yönəldir"),
      explain: t("Mövzunu qısa və aydın izah edir"),
      practice: t("Sual verir və cavabınızı yoxlayır"),
    }[m] || "";
  }
  function lockedBanner() {
    return html`<div class="notice warn chat-locked" style="margin:12px 16px 0" role="status">${ic("lock", 16)}
      <div><b>${t("Tutor müvəqqəti bağlıdır")}</b><div class="small">${t("Müəllim bu fənn üzrə tutoru müvəqqəti bağlayıb (məsələn, test davam edir). Bir qədər sonra yenidən cəhd edin.")}</div></div></div>`;
  }
  function setUsage(u) {
    st.usage = u || st.usage;
    const box = el.querySelector("#usage");
    if (!box) return;
    const uu = st.usage;
    if (uu && uu.limit) {
      const left = Math.max(0, uu.limit - uu.used);
      box.innerHTML = html`<span class="usage ${left === 0 ? "spent" : left <= 2 ? "low" : ""}" title="${t("Gündəlik sual limiti")}">${ic("timer", 13)} ${t("Bu gün: {used}/{limit} sual", { used: uu.used, limit: uu.limit })}</span>`.__html;
      if (left === 0) lockComposer(t("Günlük sual limitiniz bitib. Limit sabah yenilənir."));
    } else {
      box.textContent = "";
    }
  }
  function lockComposer(reason) {
    const sendBtn = el.querySelector("#send");
    inp.disabled = true; if (sendBtn) sendBtn.disabled = true;
    inp.placeholder = reason;
  }

  function welcome() {
    const sugg = cfg.suggestions || [];
    return html`<div class="welcome">
      <div class="orb">${ic("sparkles", 30)}</div>
      <h3>${cfg.title}</h3><p>${cfg.text}</p>
      ${sugg.length ? html`<div class="suggest-head" data-tour="chat-suggestions">${t("Nümunə suallar")}</div>
        <div class="chips suggest-chips" style="justify-content:center">${sugg.map((s) => html`<button class="chip" data-suggest="${esc(s)}">${ic("message", 13)} ${s}</button>`)}</div>`
        : html`<div class="suggest-head" data-tour="chat-suggestions">${t("Sualınızı aşağıdakı xanaya yazın.")}</div>`}
    </div>`;
  }
  function msgHtml(m) {
    if (m.role === "user") {
      const pii = (m.meta && m.meta.pii) || [];
      return html`<div class="msg user" data-id="${m.id}"><div class="bubble">${m.content}${pii.length ? html`<div class="pii-note">${ic("shield", 12)} ${t("Maskalandı: {items}", { items: pii.join(", ") })}</div>` : ""}</div></div>`;
    }
    const meta = m.meta || {};
    return html`<div class="msg ai" data-id="${m.id}">
      <span class="avatar ai">${ic("sparkles", 16)}</span>
      <div class="grow" style="min-width:0">
        <div class="bubble"><div class="body">${md(m.content)}</div>
          ${m.cites && m.cites.length ? html`<div class="src-list">${m.cites.map((c) => html`<button class="src" data-src="${c.n}" aria-label="${t("Mənbə {n}: {title}", { n: c.n, title: `${c.material} · ${c.heading}` })}">${raw(`<b>${c.n}</b>`)}<span class="ellipsis" style="max-width:260px">${c.material} · ${c.heading}</span></button>`)}</div>` : ""}
          ${(meta.actions || []).length ? html`<div class="action-btns">${meta.actions.map((a) => html`<button class="btn btn-primary btn-sm" data-request="${a.code}">${ic("file", 14)} ${a.label}</button>`)}</div>` : ""}
        </div>
        <div class="msg-meta">
          ${meta.mode ? html`<span class="badge b-gray">${MODE_LABEL[meta.mode] || meta.mode}</span>` : ""}
          ${meta.guardrail ? html`<span class="badge b-amber">${ic("shield", 12)} ${t("Hazır cavab verilmədi")}</span>` : ""}
          ${meta.no_source ? html`<span class="badge b-amber">${t("Materialda tapılmadı")}</span>` : ""}
          ${meta.note ? html`<span class="badge b-red">${meta.note}</span>` : ""}
          <div class="msg-actions">
            <button data-rate="1" class="${m.rating === 1 ? "on" : ""}" title="${t("Faydalı")}" aria-label="${t("Faydalı")}" aria-pressed="${m.rating === 1}">${ic("up", 14)}</button>
            <button data-rate="-1" class="${m.rating === -1 ? "on" : ""}" title="${t("Faydalı deyil")}" aria-label="${t("Faydalı deyil")}" aria-pressed="${m.rating === -1}">${ic("down", 14)}</button>
            <button data-copy title="${t("Kopyala")}" aria-label="${t("Kopyala")}">${ic("copy", 14)}</button>
            ${cfg.canForward ? html`<button data-forward title="${t("Müəllimə göndər")}" aria-label="${t("Müəllimə göndər")}">${ic("send", 14)} ${t("Müəllimə göndər")}</button>` : ""}
          </div>
        </div>
      </div></div>`;
  }
  function render() {
    mount(cs, st.messages.length ? html`${st.messages.map(msgHtml)}` : welcome());
    cs.scrollTop = cs.scrollHeight;
  }
  async function typeOut(node, text) {
    const parts = text.split(/(\s+)/);
    const total = parts.length, step = Math.max(2, Math.ceil(total / 70));
    const body = node.querySelector(".body");
    for (let i = step; i < total + step; i += step) {
      mount(body, md(parts.slice(0, i).join("")));
      cs.scrollTop = cs.scrollHeight;
      await sleep(16);
    }
  }
  async function send(text) {
    text = (text || "").trim();
    if (!text || st.busy || inp.disabled) return;
    st.busy = true;
    st.lastQuestion = text;
    st.lastError = null;
    inp.value = "";
    inp.style.height = "auto";
    const tmp = { id: "tmp", role: "user", content: text, meta: {} };
    st.messages.push(tmp);
    render();
    cs.insertAdjacentHTML("beforeend", `<div class="msg ai" id="typing"><span class="avatar ai">${icon("sparkles", 16)}</span><div class="bubble"><span class="typing" aria-hidden="true"><i></i><i></i><i></i></span> <span class="small muted">${esc(t("Materiallarda axtarılır…"))}</span></div></div>`);
    cs.scrollTop = cs.scrollHeight;
    try {
      const [r] = await Promise.all([api.post(askUrl, { message: text, mode: st.mode }), sleep(650)]);
      st.messages[st.messages.length - 1] = r.user;
      el.querySelector("#typing")?.remove();
      st.messages.push(r.answer);
      render();
      const node = cs.querySelector(`.msg[data-id="${r.answer.id}"]`);
      if (node) {
        const full = node.querySelector(".body").innerHTML;
        await typeOut(node, r.answer.content);
        node.querySelector(".body").innerHTML = full;
      }
      setUsage(r.usage);
      if (r.answer.cites && r.answer.cites[0]) showSource(r.answer.cites[0], text);
    } catch (e) {
      el.querySelector("#typing")?.remove();
      st.messages.pop();
      st.lastError = { text, message: e.message };
      render();
      renderErrorRetry();
      toast(e.message, "err");
    } finally {
      st.busy = false;
      if (!inp.disabled) inp.focus();
    }
  }
  // Inline error card with a retry button that re-sends the failed question.
  function renderErrorRetry() {
    if (!st.lastError) return;
    cs.insertAdjacentHTML("beforeend", `<div class="msg ai chat-error" id="send-error"><span class="avatar ai">${icon("alert", 16)}</span>
      <div class="bubble"><div class="body"><b>${esc(t("Cavab alınmadı"))}</b><div class="small muted mt-sm">${esc(st.lastError.message)}</div></div>
      <div class="action-btns"><button class="btn btn-sm" id="retry-send">${icon("refresh", 14)} ${esc(t("Yenidən cəhd et"))}</button></div></div></div>`);
    cs.scrollTop = cs.scrollHeight;
    el.querySelector("#retry-send")?.addEventListener("click", () => {
      const q = st.lastError.text; el.querySelector("#send-error")?.remove(); st.lastError = null; send(q);
    });
  }
  async function showSource(c, query) {
    const panelHost = document.createElement("div");
    const body = html`<div class="src-view">
      <div class="src-load"><div class="skeleton" style="height:18px;width:60%"></div><div class="skeleton mt-sm" style="height:120px"></div></div></div>`;
    // On mobile the side panel is hidden, so open sources as a bottom-sheet modal (core.js makes modals sheets ≤720px).
    let sheet = null, target;
    if (isMobile()) {
      sheet = modal({ title: t("Mənbə"), size: "lg", cls: "src-sheet", body });
      target = sheet.el.querySelector(".src-view");
    } else {
      mount(srcEl, html`<div class="src-load"><div class="skeleton" style="height:18px;width:60%"></div><div class="skeleton mt-sm" style="height:120px"></div></div>`);
      target = srcEl;
    }
    void panelHost;
    try {
      const s = await api.get(c.kind === "kb" ? `/api/source/kb/${c.id}` : `/api/source/chunk/${c.id}`);
      const bodyHtml = md(s.text).__html;
      mount(target, html`
        <div class="small muted">${ic("file", 13)} ${s.material}</div>
        <h3 class="src-heading">${raw(`<span class="cite" style="cursor:default">${c.n}</span>`)} ${s.heading}</h3>
        ${raw(highlight(bodyHtml, query || st.lastQuestion))}
        <div class="notice ai mt">${ic("check", 15)}<div>${t("Cavab bu bölməyə əsaslanır. Sarı ilə işarələnmiş sözlər sualınızdakı anlayışlarla üst-üstə düşür.")}</div></div>
        ${LANG !== "az" ? html`<div class="tiny muted mt-sm">${ic("info", 12)} ${t("Sitat orijinal (tədris) dilində göstərilir.")}</div>` : ""}`);
    } catch (e) {
      mount(target, failed(t("Mənbə açılmadı. {msg}", { msg: e.message })));
    }
  }
  function srcPlaceholder(c) {
    return empty("book", t("Cavabın mənbəyi burada görünəcək"),
      c.kind === "tutor"
        ? t("Tutor yalnız müəllimin yüklədiyi materiallara əsaslanır. Cavabdakı [1] işarəsinə toxunub mənbəyə baxın.")
        : t("Köməkçi universitetin qaydalarına istinad edir. Cavabdakı istinad işarəsinə toxunun."));
  }

  // ---- events
  inp.addEventListener("input", () => { inp.style.height = "auto"; inp.style.height = Math.min(inp.scrollHeight, 160) + "px"; });
  inp.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(inp.value); } });
  el.querySelector("#send").addEventListener("click", () => send(inp.value));
  on(el, "click", "[data-suggest]", (e, b) => send(b.dataset.suggest));
  on(el, "click", "[data-mode]", (e, b) => {
    st.mode = b.dataset.mode;
    el.querySelectorAll("[data-mode]").forEach((x) => { const on_ = x === b; x.classList.toggle("active", on_); x.setAttribute("aria-selected", on_); });
    if (st.mode === "practice" && !st.busy && !inp.disabled) send(t("Mənə bir məşq sualı verin."));
  });
  el.querySelector("#clear").addEventListener("click", async () => {
    if (!st.messages.length) return;
    const ok = await confirmBox(t("Söhbəti silmək?"), t("Bu söhbətin tarixçəsi silinəcək. Bu əməliyyat geri qaytarıla bilməz."), t("Sil"), true);
    if (!ok) return;
    try { await api.post(clearUrl); } catch (e) { return toast(e.message, "err"); }
    st.messages = []; st.lastError = null;
    render();
    if (isMobile()) toast(t("Söhbət silindi"), "ok"); else mount(srcEl, srcPlaceholder(cfg));
    if (!inp.disabled) inp.focus();
  });
  const msgOf = (node) => st.messages.find((m) => String(m.id) === node.closest(".msg").dataset.id);
  on(cs, "click", "[data-src], .cite", (e, b) => {
    const m = msgOf(b);
    const n = +(b.dataset.src || b.dataset.cite);
    const c = m && (m.cites || []).find((x) => x.n === n);
    const idx = st.messages.indexOf(m);
    const q = idx > 0 ? st.messages[idx - 1].content : "";
    if (c) showSource(c, q);
  });
  on(cs, "click", "[data-rate]", async (e, b) => {
    const m = msgOf(b);
    const v = +b.dataset.rate;
    m.rating = m.rating === v ? null : v;
    try { await api.post(`/api/messages/${m.id}/rate`, { rating: m.rating || 0 }); } catch (err) { return toast(err.message, "err"); }
    b.closest(".msg-actions").querySelectorAll("[data-rate]").forEach((x) => { const on_ = +x.dataset.rate === m.rating; x.classList.toggle("on", on_); x.setAttribute("aria-pressed", on_); });
    if (m.rating) toast(t("Rəyiniz üçün təşəkkürlər — müəllim analitikasında nəzərə alınacaq."), "ok");
  });
  on(cs, "click", "[data-copy]", async (e, b) => {
    try { await navigator.clipboard.writeText(msgOf(b).content); toast(t("Kopyalandı"), "ok"); } catch { toast(t("Kopyalamaq mümkün olmadı"), "err"); }
  });
  on(cs, "click", "[data-request]", (e, b) => go(`/student/apply/${b.dataset.request}`));
  on(cs, "click", "[data-forward]", (e, b) => {
    const m = msgOf(b);
    const idx = st.messages.indexOf(m);
    const q = idx > 0 ? st.messages[idx - 1].content : "";
    modal({
      title: t("Sualı müəllimə göndər"),
      body: html`<div class="stack">
        <div class="notice info">${ic("info", 16)}<div>${t("Müəllim sualınızı və tutorun cavabını görəcək. Cavab sizə bildiriş kimi gələcək.")}</div></div>
        <div class="field"><label class="label" for="fq">${t("Sual")}</label><textarea class="textarea" id="fq">${q}</textarea></div>
        <label class="check"><input type="checkbox" id="fa"> ${t("Anonim göndər (müəllim adınızı görməyəcək)")}</label></div>`,
      actions: [{ label: t("Ləğv et") }, {
        label: t("Göndər"), cls: "btn-primary", onClick: async (w) => {
          const question = w.querySelector("#fq").value.trim();
          if (!question) { toast(t("Sual mətni boş ola bilməz"), "err"); return false; }
          await api.post(`${cfg.base}/forward`, { question, anonymous: w.querySelector("#fa").checked, context: m.content.slice(0, 1200) });
          toast(t("Sual müəllimə göndərildi"), "ok");
        },
      }],
    });
  });

  // ---- load history
  try {
    const h = await api.get(histUrl);
    st.messages = h.messages || [];
    setUsage(h.usage);
  } catch (e) {
    render();
    renderHistoryError(e.message);
    return { send };
  }
  render();
  if (cfg.locked) lockComposer(t("Tutor müvəqqəti bağlıdır."));
  const last = [...st.messages].reverse().find((m) => m.role === "assistant" && m.cites && m.cites.length);
  if (last && !isMobile()) showSource(last.cites[0], "");
  if (cfg.prefill) send(cfg.prefill);

  function renderHistoryError(msg) {
    mount(cs, failed(t("Söhbət tarixçəsi yüklənmədi. {msg}", { msg })));
    el.querySelector("#retry-page")?.addEventListener("click", () => chatView(el, cfg));
  }
  return { send };
}
