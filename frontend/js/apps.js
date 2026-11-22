// The integration hub (Task 37): the apps page (tiles to the systems AzTU keeps, chosen per role by the
// administrator) and the administrator's page of API keys, webhooks and exports. A key and a secret are shown once.
import { api, html, mount, on, ic, toast, modal, route, pageHead, loading, failed, empty, t, S } from "./core.js";

const ROLES = () => ({ student: t("Tələbə"), teacher: t("Müəllim"), dept_head: t("Kafedra müdiri"), office: t("Dekanlıq"),
  academic_office: t("Tədris hissəsi"), leader: t("Rəhbərlik"), admin: t("Administrator") });
const SCOPES = () => ({ "grades.read": t("Qiymətlər"), "attendance.read": t("Davamiyyət"), "registry.read": t("Reyestr (OneRoster)"), "status.read": t("Status dəyişiklikləri") });
const EVENTS = () => ({ "grade.published": t("Bal dərc olundu"), "attendance.barred": t("Davamiyyətə görə imtahana buraxılmadı"), "exam.released": t("İmtahan nəticəsi açıqlandı") });

route("/apps", async (el) => {
  let data;
  const draw = () => mount(el, html`${pageHead(t("Tətbiqlər"), t("Universitetin digər sistemlərinə keçidlər"))}
    ${data.apps.length ? html`<div class="grid g-3">${data.apps.map((a) => html`<a class="card clickable" href="${a.url}" target="_blank" rel="noopener noreferrer">
      ${ic(a.icon || "external", 20)} <b>${a.title}</b>${a.note ? html`<div class="small muted">${a.note}</div>` : ""}</a>`)}</div>` : empty("inbox", t("Hələ tətbiq əlavə olunmayıb"))}
    ${data.all ? html`<div class="card stack"><b>${t("Kartların redaktəsi")}</b>
      <textarea class="input" id="apps-json" rows="10" aria-label="${t("Kartlar")}">${JSON.stringify(data.all, null, 1)}</textarea>
      <p class="small muted">${t("Hər kart: title, url (https://), roles ({roles}), icon, note.", { roles: Object.keys(ROLES()).join(", ") })}</p>
      <button class="btn btn-primary" data-save>${t("Saxla")}</button></div>` : ""}`);
  on(el, "click", "[data-save]", async () => {
    let apps;
    try { apps = JSON.parse(el.querySelector("#apps-json").value); } catch { return toast(t("JSON düzgün deyil"), "err"); }
    try { data = await api.put("/api/apps", { apps }); toast(t("Saxlanıldı"), "ok"); draw(); } catch (err) { toast(err.message, "err"); }
  });
  mount(el, loading());
  try { data = await api.get("/api/apps"); } catch (err) { return mount(el, failed(err.message)); }
  draw();
});

route("/admin/integration", async (el) => {
  const shown = (title, value) => modal({ title, body: html`<p>${t("Bu dəyər yalnız indi göstərilir. Onu təhlükəsiz yerdə saxlayın.")}</p><pre class="secret">${value}</pre>`,
    actions: [{ label: t("Bağla"), cls: "btn-primary" }] });
  const load = async () => {
    let keys, hooks;
    try { [keys, hooks] = await Promise.all([api.get("/api/integration/keys"), api.get("/api/integration/webhooks")]); } catch (err) { return mount(el, failed(err.message)); }
    mount(el, html`${pageHead(t("İnteqrasiya"), t("API açarları, webhook-lar və ixraclar"))}
      <div class="card stack"><b>${t("API açarları")}</b>
        <table class="table"><tbody>${keys.map((k) => html`<tr><td><b>${k.name}</b><div class="small muted">${k.prefix}…</div></td>
          <td class="small">${k.scopes.map((s) => SCOPES()[s] || s).join(", ")}</td><td class="small">${t("{n}/dəq.", { n: k.per_minute })}</td>
          <td class="small">${k.last_used_at ? k.last_used_at.replace("T", " ").slice(0, 16) : "—"}</td>
          <td>${k.revoked_at ? html`<span class="badge b-gray">${t("Ləğv olunub")}</span>` : html`<button class="btn btn-ghost btn-sm" data-revoke="${k.id}">${t("Ləğv et")}</button>`}</td></tr>`)}</tbody></table>
        <div class="row wrap" style="gap:8px"><input class="input" id="key-name" placeholder="${t("Açarın adı")}">
          ${Object.entries(SCOPES()).map(([k, v]) => html`<label class="row" style="gap:4px"><input type="checkbox" name="scope" value="${k}"> ${v}</label>`)}
          <button class="btn btn-primary" data-key>${t("Açar yarat")}</button></div></div>
      <div class="card stack"><b>${t("Webhook-lar")}</b>
        <table class="table"><tbody>${hooks.map((h) => html`<tr><td class="small">${h.url}</td><td class="small">${h.events.map((e) => EVENTS()[e] || e).join(", ")}</td>
          <td class="small">${t("gözləyir: {p} · uğursuz: {f}", { p: h.pending, f: h.failed })}</td>
          <td>${h.active ? html`<button class="btn btn-ghost btn-sm" data-off="${h.id}">${t("Söndür")}</button>` : html`<span class="badge b-gray">${t("Söndürülüb")}</span>`}
            <button class="btn btn-ghost btn-sm" data-log="${h.id}">${t("Jurnal")}</button></td></tr>`)}</tbody></table>
        <div class="row wrap" style="gap:8px"><input class="input grow" id="hook-url" placeholder="https://…">
          ${Object.entries(EVENTS()).map(([k, v]) => html`<label class="row" style="gap:4px"><input type="checkbox" name="event" value="${k}"> ${v}</label>`)}
          <button class="btn btn-primary" data-hook>${t("Webhook əlavə et")}</button></div></div>
      <div class="card stack"><b>${t("İxraclar")}</b><div class="row wrap" style="gap:8px">
        ${[["oneroster", t("Reyestr (OneRoster)")], ["grades", t("Qiymətlər")], ["attendance", t("Davamiyyət")], ["registry", t("Tələbə reyestri")]].map(([k, v]) =>
          html`<a class="btn btn-ghost" href="/api/integration/export/${k}" download>${ic("download", 15)} ${v}</a>`)}</div></div>`);
  };
  on(el, "click", "[data-key]", async () => {
    const scopes = [...el.querySelectorAll("[name=scope]:checked")].map((x) => x.value);
    try { const k = await api.post("/api/integration/keys", { name: el.querySelector("#key-name").value, scopes }); shown(t("Yeni API açarı"), k.token); load(); }
    catch (err) { toast(err.message, "err"); }
  });
  on(el, "click", "[data-revoke]", async (e, b) => { try { await api.post(`/api/integration/keys/${b.dataset.revoke}/revoke`); load(); } catch (err) { toast(err.message, "err"); } });
  on(el, "click", "[data-hook]", async () => {
    const events = [...el.querySelectorAll("[name=event]:checked")].map((x) => x.value);
    try { const h = await api.post("/api/integration/webhooks", { url: el.querySelector("#hook-url").value, events }); shown(t("Webhook-un imza açarı"), h.secret); load(); }
    catch (err) { toast(err.message, "err"); }
  });
  on(el, "click", "[data-off]", async (e, b) => { try { await api.post(`/api/integration/webhooks/${b.dataset.off}/deactivate`); load(); } catch (err) { toast(err.message, "err"); } });
  on(el, "click", "[data-log]", async (e, b) => {
    let log;
    try { log = await api.get(`/api/integration/webhooks/${b.dataset.log}/deliveries`); } catch (err) { return toast(err.message, "err"); }
    modal({ title: t("Çatdırma jurnalı"), body: log.length ? html`<table class="table"><tbody>${log.map((d) => html`<tr><td class="small">${d.created_at.replace("T", " ").slice(0, 16)}</td>
      <td>${EVENTS()[d.event] || d.event}</td><td><span class="badge ${d.status === "sent" ? "b-green" : d.status === "failed" ? "b-red" : "b-gray"}">${d.status}</span></td>
      <td class="small">${t("{n} cəhd", { n: d.attempts })} ${d.last_status || ""} ${d.last_error || ""}</td></tr>`)}</tbody></table>` : empty("inbox", t("Çatdırma yoxdur")),
      actions: [{ label: t("Bağla"), cls: "btn-primary" }] });
  });
  if (S.user.role !== "admin") return mount(el, failed(t("Bu bölməyə giriş icazəniz yoxdur")));
  mount(el, loading());
  await load();
});
