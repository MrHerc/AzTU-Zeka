import { api, html, mount, on, md, ic, route, go, S, pageHead, loading, empty, t, $, $$, registerTour, progress, fold } from "./core.js";
import { HOME } from "./shell.js";
import { tourCatalog, startTour, roleTourSteps, isDone } from "./tour.js";

let G = null;
async function guide() { if (!G || G.role !== S.user.role) { G = await api.get("/api/guide"); G.role = S.user.role; } return G; }
export function launchTour(key, path) {
  sessionStorage.setItem("zeka-start-tour", key);
  go(path);
}

route("/guide", async (el, p, q) => {
  mount(el, loading());
  const g = await guide();
  const tab = q.tab || "tours";
  const tours = tourCatalog(S.user.role).filter((x) => x.route);
  const done = tours.filter((x) => x.done).length;
  const roleDone = isDone(S.user.role);
  mount(el, html`${pageHead(t("Bələdçi mərkəzi"), t("İnteraktiv səhifə bələdçiləri, təlimatlar və tez-tez verilən suallar."),
      html`<button class="btn btn-primary" id="tour">${ic("play", 15)} ${t("Tanışlıq turu")}</button>`, [[t("Əsas"), HOME[S.user.role]], [t("Bələdçi")]],
      { info: t("Hər səhifənin yuxarısındakı “Səhifə bələdçisi” düyməsi həmin səhifənin hissələrini addım-addım izah edir.") })}
    <div class="guide-hero card"><div class="card-b row wrap" style="gap:18px">
      <span class="stat-ic ic-navy" style="width:52px;height:52px">${ic("compass", 24)}</span>
      <div class="grow"><b>${t("Bələdçilərdə irəliləyişiniz")}</b><div class="small muted">${t("{d} / {n} səhifə bələdçisi tamamlanıb", { d: done, n: tours.length })}${roleDone ? "" : " · " + t("tanışlıq turu hələ keçilməyib")}</div>
        <div class="mt-sm" style="max-width:420px">${progress(tours.length ? (100 * done) / tours.length : 0)}</div></div>
      <button class="btn" data-go="/support?tab=new">${ic("ticket", 15)} ${t("Dəstəyə yaz")}</button></div></div>
    <div class="tabs" role="tablist">${[["tours", t("Səhifə bələdçiləri"), "compass"], ["guides", t("Təlimatlar"), "book"], ["faq", t("Suallar"), "help"], ["shortcuts", t("Qısayollar"), "keyboard"]].map(([k, l, i]) =>
      html`<button class="tab ${tab === k ? "active" : ""}" role="tab" aria-selected="${tab === k}" data-go="/guide?tab=${k}">${ic(i, 15)} ${l}</button>`)}</div>
    <div id="gb"></div>`);
  const b = $("#gb", el);
  if (tab === "tours") {
    const groups = [];
    for (const x of tours) { let gr = groups.find((y) => y.name === x.group); if (!gr) groups.push((gr = { name: x.group || t("Ümumi"), items: [] })); gr.items.push(x); }
    mount(b, groups.length ? html`${groups.map((gr) => html`<h3 class="section-t">${gr.name}</h3><div class="grid g-auto">${gr.items.map((x) => html`<div class="tour-tile ${x.done ? "done" : ""}">
        <span class="stat-ic ${x.done ? "ic-green" : "ic-blue"}">${ic(x.done ? "check" : x.icon, 18)}</span>
        <div class="grow"><b>${x.title}</b><div class="tiny muted">${t("{n} addım", { n: x.steps })}${x.done ? " · " + t("tamamlanıb") : ""}</div></div>
        <button class="btn btn-sm ${x.done ? "" : "btn-primary"}" data-start="${x.key}" data-path="${x.route}">${x.done ? t("Təkrar") : t("Başla")}</button></div>`)}</div>`)}`
      : empty("compass", t("Bələdçi tapılmadı")));
    on(b, "click", "[data-start]", (e, btn) => launchTour(btn.dataset.start, btn.dataset.path));
  } else if (tab === "guides") {
    let term = "";
    const cards = () => {
      const f = fold(term);
      const list = g.articles.filter((a) => !f || fold(a.title + " " + a.summary + " " + (a.tags || []).join(" ")).includes(f));
      return list.length ? html`<div class="grid g-2">${list.map((a) => html`<div class="guide-card" data-go="/guide/${a.id}" tabindex="0" role="link"><span class="stat-ic ic-navy">${ic(a.icon, 20)}</span>
        <div class="grow"><b>${a.title}</b><div class="small muted mt-sm">${a.summary}</div><div class="tiny muted mt-sm">${t("{n} addım", { n: a.steps.length })}</div></div>${ic("chevron", 16)}</div>`)}</div>`
        : empty("search", t("Təlimat tapılmadı"), t("Başqa açar söz yazın."));
    };
    mount(b, html`<input class="input mb" id="gs" type="search" placeholder="${t("Təlimat axtar: arayış, qayıb, test…")}" style="max-width:460px" aria-label="${t("Təlimat axtarın")}"><div id="gl">${cards()}</div>`);
    $("#gs", el).addEventListener("input", (e) => { term = e.target.value; mount($("#gl", el), cards()); });
    on(b, "keydown", ".guide-card", (e, c) => { if (e.key === "Enter") go(c.dataset.go); });
  } else if (tab === "faq") {
    mount(b, html`<div class="stack" style="max-width:860px">${g.faq.map((f) => html`<details class="faq"><summary>${f.q}</summary><p>${f.a}</p></details>`)}</div>`);
  } else {
    mount(b, html`<div class="card" style="max-width:640px"><div class="card-b list">${g.shortcuts.map((s) => html`<div class="list-item"><span class="grow">${s.text}</span><span class="kbd">${s.keys}</span></div>`)}</div></div>`);
  }
  on(el, "click", "#tour", () => { go(HOME[S.user.role]); setTimeout(() => startTour(true), 700); });
});

route("/guide/:id", async (el, p) => {
  mount(el, loading());
  const g = await guide();
  const a = g.articles.find((x) => x.id === p.id);
  if (!a) return mount(el, empty("help", t("Təlimat tapılmadı"), "", { label: t("Bələdçi mərkəzi"), go: "/guide?tab=guides" }));
  const others = g.articles.filter((x) => x.id !== a.id).slice(0, 5);
  mount(el, html`${pageHead(a.title, a.summary, a.link ? html`<button class="btn btn-primary" data-go="${a.link}">${a.link_label} ${ic("arrow", 15)}</button>` : "", [[t("Əsas"), HOME[S.user.role]], [t("Bələdçi"), "/guide?tab=guides"], [a.title]])}
    <div class="grid g-12"><ol class="how">${a.steps.map((s) => html`<li><div>${md(s)}</div></li>`)}</ol>
      <div class="stack"><div class="card"><div class="card-h"><h3>${ic("book", 17)} ${t("Digər təlimatlar")}</h3></div><div class="card-b list">
        ${others.map((o) => html`<div class="list-item click" data-go="/guide/${o.id}"><span class="stat-ic ic-blue" style="width:32px;height:32px">${ic(o.icon, 15)}</span><b class="small grow">${o.title}</b></div>`)}</div></div>
        <div class="notice info">${ic("help", 16)}<div>${t("Cavab tapmadınız?")} ${S.user.role === "student" ? html`<a href="#/student/campus">${t("Kampus köməkçisinə soruşun")}</a> ${t("və ya")} ` : ""}<a href="#/support?tab=new">${t("dəstək xidmətinə yazın")}</a>.</div></div></div></div>`);
});

registerTour("guide", { route: "/guide", title: t("Bələdçi mərkəzi"), group: t("Kömək"), icon: "buoy", steps: [
  { sel: ".guide-hero", title: t("İrəliləyiş"), text: t("Neçə səhifə bələdçisini keçdiyinizi göstərir.") },
  { sel: ".tabs", title: t("Bölmələr"), text: t("İnteraktiv bələdçilər, addım-addım təlimatlar, suallar və klaviatura qısayolları.") },
  { sel: "#gb", title: t("Bələdçini başladın"), text: t("“Başla” düyməsi sizi səhifəyə aparır və onun hissələrini bir-bir göstərir.") },
] });
export const _roleSteps = roleTourSteps;
