// The campus assistant's knowledge base (Task 32): articles with their source, review date and versions. A saved
// article reaches the assistant on the next question in every worker; a draft or an archived one is not searched.
import { api, html, mount, on, ic, toast, modal, route, pageHead, loading, failed, t } from "./core.js";

const STATUS = () => ({ published: t("Dərc olunub"), draft: t("Qaralama"), archived: t("Arxivdə") });

route("/admin/kb", async (el) => {
  mount(el, loading());
  let list;
  try { list = await api.get("/api/kb"); } catch (err) { return mount(el, failed(err.message)); }
  let filter = "";
  const draw = () => {
    const shown = list.filter((a) => !filter || a.heading.toLowerCase().includes(filter));
    mount(el, html`${pageHead(t("Bilik bazası"), t("Kampus köməkçisinin cavab verdiyi məqalələr: mənbə, yenidən baxış tarixi, versiyalar"))}
      <div class="row wrap" style="gap:8px;margin-bottom:12px">
        <input class="input grow" id="kb-filter" placeholder="${t("Başlıqda axtar")}" value="${filter}" aria-label="${t("Başlıqda axtar")}">
        <button class="btn btn-primary" data-new>${ic("plus", 15)} ${t("Yeni məqalə")}</button></div>
      <div class="card"><table class="table"><thead><tr><th>${t("Başlıq")}</th><th>${t("Mənbə")}</th><th>${t("Yenidən baxış")}</th>
        <th>${t("Status")}</th><th>${t("Versiya")}</th></tr></thead><tbody>
        ${shown.map((a) => html`<tr class="clickable" data-id="${a.id}" tabindex="0"><td><b>${a.heading}</b></td>
          <td class="small">${a.source || "—"}${a.source_ref ? html` · ${a.source_ref}` : ""}</td>
          <td>${a.review_at || "—"} ${a.overdue ? html`<span class="badge b-amber">${t("Vaxtı keçib")}</span>` : ""}</td>
          <td><span class="badge ${a.status === "published" ? "b-green" : "b-gray"}">${STATUS()[a.status] || a.status}</span></td>
          <td>${a.version}</td></tr>`)}
      </tbody></table></div>`);
  };
  const reload = async () => { list = await api.get("/api/kb"); draw(); };
  const form = async (id) => {
    let a = { heading: "", text: "", source: "", source_ref: "", request: "", action_label: "", review_at: "", status: "published" };
    let versions = [];
    if (id) {
      try { ({ article: a, versions } = await api.get(`/api/kb/${id}`)); } catch (err) { return toast(err.message, "err"); }
    }
    const field = (k, label, extra = "") => html`<label class="field"><span>${label}</span>
      <input class="input" name="${k}" value="${a[k] || ""}" ${extra}></label>`;
    modal({ title: id ? t("Məqaləni düzəlt") : t("Yeni məqalə"),
      body: html`<div class="stack">${field("heading", t("Başlıq"))}
        <label class="field"><span>${t("Mətn")}</span><textarea class="input" name="text" rows="10" maxlength="8000">${a.text || ""}</textarea></label>
        <div class="row wrap" style="gap:8px">${field("source", t("Mənbə sənədi"))}${field("source_ref", t("Bənd"))}</div>
        <div class="row wrap" style="gap:8px">${field("request", t("E-xidmətin kodu (könüllü)"))}${field("action_label", t("Düymənin adı"))}</div>
        <div class="row wrap" style="gap:8px">${field("review_at", t("Yenidən baxış tarixi"))}
          <label class="field"><span>${t("Status")}</span><select class="input" name="status">
            ${Object.entries(STATUS()).map(([k, v]) => html`<option value="${k}" ${k === a.status ? "selected" : ""}>${v}</option>`)}</select></label></div>
        ${versions.length ? html`<div class="small muted"><b>${t("Versiyalar")}</b>
          ${versions.map((v) => html`<div>v${v.version} · ${v.changed_at} · ${v.changed_by || "—"} · ${STATUS()[v.status] || v.status}</div>`)}</div>` : ""}</div>`,
      actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Saxla"), cls: "btn-primary", onClick: async (w) => {
        const body = {};
        for (const k of ["heading", "text", "source", "source_ref", "request", "action_label", "review_at", "status"]) body[k] = w.querySelector(`[name="${k}"]`).value;
        try {
          if (id) await api.put(`/api/kb/${id}`, body); else await api.post("/api/kb", body);
          toast(t("Saxlanıldı"), "ok"); await reload();
        } catch (err) { toast(err.message, "err"); return false; }
      } }] });
  };
  on(el, "input", "#kb-filter", (e, x) => { filter = x.value.trim().toLowerCase(); draw(); const f = el.querySelector("#kb-filter"); f.focus(); f.setSelectionRange(f.value.length, f.value.length); });
  on(el, "click", "[data-new]", () => form(null));
  on(el, "click", "tr[data-id]", (e, tr) => form(+tr.dataset.id));
  on(el, "keydown", "tr[data-id]", (e, tr) => { if (e.key === "Enter") form(+tr.dataset.id); });
  draw();
});
