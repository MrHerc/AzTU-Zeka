// The university's structure and terms (Task 15, slice 1): faculties, departments, specialties, groups, terms.
// Lists are paged and searched on the server; rows are deactivated, never deleted.
import { api, html, mount, on, ic, toast, modal, route, pageHead, loading, failed, $, t, S } from "./core.js";
import { HOME } from "./shell.js";

const DEGREES = () => [["bachelor", t("Bakalavriat")], ["master", t("Magistratura")], ["phd", t("Doktorantura")]];
const ENT = () => ({
  faculties: { title: t("Fakültələr"), cols: [["code", t("Kod")], ["name", t("Ad")]],
    fields: [["code", t("Kod"), "text"], ["name", t("Ad"), "text"]] },
  departments: { title: t("Kafedralar"), cols: [["code", t("Kod")], ["name", t("Ad")], ["faculty_id", t("Fakültə"), "faculties"]],
    fields: [["faculty_id", t("Fakültə"), "ref:faculties"], ["code", t("Kod"), "text"], ["name", t("Ad"), "text"]] },
  specialties: { title: t("İxtisaslar"), cols: [["code", t("Kod")], ["name", t("Ad")], ["faculty_id", t("Fakültə"), "faculties"], ["degree", t("Dərəcə"), "degree"]],
    fields: [["faculty_id", t("Fakültə"), "ref:faculties"], ["department_id", t("Kafedra"), "ref?:departments"], ["code", t("Kod"), "text"],
      ["name", t("Ad"), "text"], ["degree", t("Dərəcə"), "degree"]] },
  groups: { title: t("Qruplar"), cols: [["name", t("Qrup")], ["year", t("Qəbul ili")], ["faculty_id", t("Fakültə"), "faculties"], ["specialty_id", t("İxtisas"), "specialties"]],
    fields: [["name", t("Qrup"), "text"], ["year", t("Qəbul ili"), "number"], ["faculty_id", t("Fakültə"), "ref:faculties"], ["specialty_id", t("İxtisas"), "ref?:specialties"]] },
  terms: { title: t("Semestrlər"), cols: [["code", t("Kod")], ["name", t("Ad")], ["teaching_start", t("Tədris"), "period:teaching"], ["exam_start", t("İmtahan sessiyası"), "period:exam"]],
    fields: [["code", t("Kod"), "text"], ["name", t("Ad"), "text"], ["teaching_start", t("Tədrisin başlanğıcı"), "date"], ["teaching_end", t("Tədrisin sonu"), "date"],
      ["exam_start", t("Sessiyanın başlanğıcı"), "date"], ["exam_end", t("Sessiyanın sonu"), "date"]] },
});

route("/admin/directory", async (el, p, q) => {
  const ent = ENT();
  const can = ["admin", "academic_office"].includes(S.user.role);
  let tab = ent[q.tab] ? q.tab : "faculties", page = 1, query = "", refs = {}, items = [], timer = null;
  const refNames = (e) => [...new Set(e.fields.filter(([, , k]) => k.startsWith("ref")).map(([, , k]) => k.split(":")[1]))];
  const loadRefs = async (e) => {
    for (const n of refNames(e)) if (!refs[n]) refs[n] = Object.fromEntries((await api.get(`/api/directory/${n}?active=1`)).items.map((x) => [x.id, x]));
  };
  const cell = (x, [k, , kind]) => {
    if (kind === "degree") return (DEGREES().find(([v]) => v === x[k]) || [, x[k]])[1];
    if (kind === "period:teaching") return `${x.teaching_start} — ${x.teaching_end}`;
    if (kind === "period:exam") return `${x.exam_start} — ${x.exam_end}`;
    if (kind && refs[kind]) return x[k] ? (refs[kind][x[k]] ? refs[kind][x[k]].name : `#${x[k]}`) : "—";
    return x[k] ?? "—";
  };
  const draw = async () => {
    const e = ent[tab];
    let r;
    try { await loadRefs(e); r = await api.get(`/api/directory/${tab}?page=${page}&q=${encodeURIComponent(query)}`); }
    catch (err) { mount(el, failed(err.message)); return; }
    items = r.items;
    mount(el, html`${pageHead(t("Struktur və semestrlər"), t("Fakültə, kafedra, ixtisas, qrup və semestrlər. Sətirlər silinmir, deaktiv edilir."), "",
        [[t("Əsas"), HOME[S.user.role]], [t("Struktur və semestrlər")]])}
      <div class="seg mb" role="tablist">${Object.entries(ent).map(([k, v]) => html`<button role="tab" aria-selected="${k === tab}" class="${k === tab ? "active" : ""}" data-tab="${k}">${v.title}</button>`)}</div>
      <div class="card"><div class="card-h wrap"><input class="input input-sm" id="dir-q" type="search" placeholder="${t("Kod və ya ad üzrə axtar")}" aria-label="${t("Axtar")}" value="${query}" style="max-width:320px">
        ${can ? html`<button class="btn btn-primary btn-sm" id="dir-new">${ic("plus", 15)} ${t("Yeni")}</button>` : ""}</div>
      <div class="table-wrap"><table class="table"><thead><tr>${e.cols.map((c) => html`<th>${c[1]}</th>`)}<th>${t("Vəziyyət")}</th>${can ? html`<th></th>` : ""}</tr></thead><tbody>
        ${items.map((x) => html`<tr><td>${cell(x, e.cols[0])}</td>${e.cols.slice(1).map((c) => html`<td>${cell(x, c)}</td>`)}
          <td>${x.active ? html`<span class="badge b-green">${t("Aktiv")}</span>` : html`<span class="badge b-gray">${t("Deaktiv")}</span>`}</td>
          ${can ? html`<td class="nowrap"><button class="btn btn-ghost btn-sm" data-edit="${x.id}">${t("Düzəlt")}</button><button class="btn btn-ghost btn-sm" data-toggle="${x.id}">${x.active ? t("Deaktiv et") : t("Aktiv et")}</button></td>` : ""}</tr>`)}
      </tbody></table></div>
      ${items.length ? "" : html`<div class="card-b"><p class="muted" style="margin:0">${t("Heç nə tapılmadı")}</p></div>`}
      <div class="card-b row between"><span class="small muted">${t("Cəmi: {n}", { n: r.total })}</span>
        <div class="row"><button class="btn btn-sm" data-page="${page - 1}" aria-label="${t("Əvvəlki səhifə")}">←</button>
          <span class="small">${page} / ${r.pages}</span><button class="btn btn-sm" data-page="${page + 1}" aria-label="${t("Növbəti səhifə")}">→</button></div></div></div>`);
    $("[data-page='" + (page - 1) + "']", el).disabled = page <= 1;
    $("[data-page='" + (page + 1) + "']", el).disabled = page >= r.pages;
  };
  const input = ([k, label, kind], x) => {
    const v = x ? x[k] ?? "" : "";
    if (kind.startsWith("ref")) {
      const target = refs[kind.split(":")[1]] || {};
      return html`<div class="field"><label class="label" for="f-${k}">${label}</label><select class="input" id="f-${k}" name="${k}">
        ${kind.startsWith("ref?") || !v ? html`<option value="">—</option>` : ""}${Object.values(target).map((o) => html`<option value="${o.id}" ${o.id === v ? "selected" : ""}>${o.name}</option>`)}</select></div>`;
    }
    if (kind === "degree") return html`<div class="field"><label class="label" for="f-${k}">${label}</label><select class="input" id="f-${k}" name="${k}">
      ${DEGREES().map(([d, l]) => html`<option value="${d}" ${d === (v || "bachelor") ? "selected" : ""}>${l}</option>`)}</select></div>`;
    const type = kind === "number" ? "number" : kind === "date" ? "date" : "text";
    return html`<div class="field"><label class="label" for="f-${k}">${label}</label><input class="input" id="f-${k}" name="${k}" type="${type}" value="${v}"></div>`;
  };
  const form = (x) => {
    const e = ent[tab];
    modal({ title: x ? t("Düzəlt") : t("Yeni"), body: html`<div class="stack">${e.fields.map((f) => input(f, x))}</div>`,
      actions: [{ label: t("Saxla"), cls: "btn-primary", onClick: async (w) => {
        const body = {};
        for (const [k, , kind] of e.fields) {
          const v = w.querySelector(`[name="${k}"]`).value;
          body[k] = kind.startsWith("ref") || kind === "number" ? (v === "" ? null : Number(v)) : v;
        }
        try {
          if (x) await api.put(`/api/directory/${tab}/${x.id}`, body); else await api.post(`/api/directory/${tab}`, body);
          toast(t("Saxlanıldı"), "ok"); refs = {}; draw();
        } catch (err) { toast(err.message, "err"); return false; }
      } }] });
  };
  on(el, "click", "[data-tab]", (ev, b) => { tab = b.dataset.tab; page = 1; query = ""; draw(); });
  on(el, "click", "[data-page]", (ev, b) => { page = Number(b.dataset.page); draw(); });
  on(el, "input", "#dir-q", (ev, i) => { clearTimeout(timer); timer = setTimeout(() => { query = i.value; page = 1; draw().then(() => { const n = $("#dir-q", el); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }); }, 300); });
  on(el, "click", "#dir-new", () => form(null));
  on(el, "click", "[data-edit]", (ev, b) => form(items.find((x) => x.id === Number(b.dataset.edit))));
  on(el, "click", "[data-toggle]", async (ev, b) => {
    const x = items.find((y) => y.id === Number(b.dataset.toggle));
    try { await api.post(`/api/directory/${tab}/${x.id}/${x.active ? "deactivate" : "activate"}`); refs = {}; draw(); }
    catch (err) { toast(err.message, "err"); }
  });
  mount(el, loading());
  draw();
});
