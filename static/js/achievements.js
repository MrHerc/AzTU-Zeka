import { S, api, html, raw, mount, on, ic, toast, route, go, pageHead, loading, empty, infoTip, cnt, t, LANG, $, $$, esc, fmtDate, fmtMonthYear, fmtDayMonth,
  copyText, registerTour, num } from "./core.js";
import { HOME } from "./shell.js";

let A = null;
const data = async () => (A ||= await api.get("/api/achievements"));
const srcLang = (s) => (s.lang !== LANG ? html` <span class="tiny muted">(${s.lang === "az" ? t("azərbaycan dilində") : s.lang === "en" ? t("ingilis dilində") : t("rus dilində")})</span>` : "");
const dateLabel = (d) => (!d ? t("Tarix göstərilməyib") : d.length === 7 ? fmtMonthYear(d + "-01") : `${fmtDayMonth(d)} ${d.slice(0, 4)}`);

function card(x, cats) {
  const cat = cats.find((c) => c.key === x.category) || {};
  const [main, ...more] = x.sources;
  return html`<article class="ach-card tone-${x.tone}" id="ach-${x.id}" data-cat="${x.category}">
    <div class="ach-top"><span class="ach-ic">${ic(x.icon, 20)}</span><div class="grow"><span class="badge b-gray">${cat.name || ""}</span></div><time class="tiny muted" datetime="${x.date || ""}">${dateLabel(x.date)}</time></div>
    <div class="ach-metric">${x.highlight}</div>
    <h3>${x.title}</h3>
    <p class="ach-sum">${x.summary}</p>
    <div class="ach-foot"><a class="btn btn-sm btn-primary" href="${main.url}" target="_blank" rel="noopener noreferrer">${t("Mənbəni oxu")} ${ic("external", 13)}</a>
      ${more.map((s) => html`<a class="btn btn-sm btn-ghost" href="${s.url}" target="_blank" rel="noopener noreferrer">${t("Əlaqəli xəbər")} ${ic("external", 13)}</a>`)}
      <span class="grow"></span><span class="tiny muted ach-src" title="${main.url}">${ic("globe", 12)} ${main.name}${srcLang(main)}</span>
      <button class="btn btn-ghost btn-icon btn-sm" data-copy="${main.url}" aria-label="${t("Keçidi kopyala")}" title="${t("Keçidi kopyala")}">${ic("copy", 14)}</button></div></article>`;
}

route("/achievements", async (el, p, q) => {
  const a = await data();
  let cat = q.cat || "all";
  const total = a.items.length;
  const draw = () => {
    const items = a.items.filter((x) => cat === "all" || x.category === cat);
    const groups = [];
    for (const x of items) {
      const k = x.date ? x.date.slice(0, 7) : "none";
      let g = groups.find((y) => y.k === k);
      if (!g) groups.push((g = { k, label: x.date ? fmtMonthYear(k + "-01") : t("Digər əlamətdar hadisələr"), items: [] }));
      g.items.push(x);
    }
    mount($("#ach-list", el), groups.length ? html`${groups.map((g) => html`<section class="ach-group"><h2 class="ach-month"><span>${g.label}</span></h2>
      <div class="ach-grid">${g.items.map((x) => card(x, a.categories))}</div></section>`)}` : empty("trophy", t("Bu kateqoriyada nailiyyət yoxdur")));
    $$("[data-fcat]", el).forEach((b) => { b.classList.toggle("on", b.dataset.fcat === cat); b.setAttribute("aria-pressed", String(b.dataset.fcat === cat)); });
  };
  mount(el, html`${pageHead(t("AzTU-nun nailiyyətləri"), t("Reytinqlər, elm, tələbə uğurları və əməkdaşlıq — rəsmi mənbələrə keçidlərlə."), "", [[t("Əsas"), HOME[S.user.role]], [t("Nailiyyətlər")]],
      { info: t("Bütün məlumatlar AzTU-nun rəsmi saytından (aztu.edu.az) və Elm və Təhsil Nazirliyinin saytından (edu.gov.az) götürülüb. Hər kartda orijinal xəbərə keçid var. Son yoxlama: {d}.", { d: fmtDate(a.checked) }) })}
    <section class="ach-hero" aria-label="${t("Əsas göstəricilər")}"><div class="ach-hero-in">
      <div class="ach-hero-t"><span class="eyebrow">${ic("trophy", 15)} ${t("Azərbaycan Texniki Universiteti")}</span>
        <h2>${t("Mühəndislik təhsilində 75 illik ənənə, yeni nəslin texnoloji uğurları")}</h2>
        <p>${t("Seçilmiş nailiyyətlər rəsmi xəbərlər əsasında hazırlanıb. Hər birinin mənbəsini oxuya bilərsiniz.")}</p></div>
      <div class="ach-stats">${a.stats.map((s) => html`<div class="ach-stat"><div class="v">${s.format === "year" ? s.value : html`${s.prefix || ""}${cnt(s.value)}`}</div><div class="l">${s.label}</div></div>`)}</div></div></section>
    <div class="chips" role="group" aria-label="${t("Kateqoriyalar")}"><button class="chip on" data-fcat="all" aria-pressed="true">${t("Hamısı")} <span>${total}</span></button>
      ${a.categories.map((c) => html`<button class="chip" data-fcat="${c.key}" aria-pressed="false">${ic(c.icon, 14)} ${c.name} <span>${c.n}</span></button>`)}</div>
    <div id="ach-list"></div>
    <p class="tiny muted center mt">${ic("shield", 12)} ${t("Mənbələr")}: <a href="https://aztu.edu.az/news" target="_blank" rel="noopener noreferrer">aztu.edu.az/news</a> · <a href="https://edu.gov.az" target="_blank" rel="noopener noreferrer">edu.gov.az</a></p>`);
  draw();
  on(el, "click", "[data-fcat]", (e, b) => { cat = b.dataset.fcat; draw(); });
  on(el, "click", "[data-copy]", (e, b) => copyText(b.dataset.copy));
  if (q.id) setTimeout(() => { const c = $(`#ach-${CSS.escape(q.id)}`, el); if (c) { c.scrollIntoView({ block: "center", behavior: "smooth" }); c.classList.add("flash"); } }, 350);
});

// Small card for dashboards
export async function achievementsTeaser(n = 3) {
  try {
    const a = await data();
    const top = a.items.filter((x) => x.featured).slice(0, n);
    return html`<div class="card ach-teaser"><div class="card-h"><h3>${ic("trophy", 17)} ${t("AzTU-nun nailiyyətləri")}</h3><a class="small" href="#/achievements">${t("Hamısı")} ${ic("arrow", 13)}</a></div>
      <div class="card-b list">${top.map((x) => html`<a class="list-item click" href="#/achievements?id=${x.id}"><span class="ach-ic sm tone-${x.tone}">${ic(x.icon, 15)}</span>
        <div class="grow"><b class="small">${x.title}</b><div class="tiny muted">${x.highlight} · ${dateLabel(x.date)}</div></div>${ic("chevron", 14)}</a>`)}</div></div>`;
  } catch { return ""; }
}

// ---------------------------------------------------------------- contact
route("/contact", async (el) => {
  const c = await api.get("/api/contact");
  const SOC = { facebook: "facebook", instagram: "instagram", linkedin: "linkedin", youtube: "youtube", wikipedia: "wikipedia" };
  mount(el, html`${pageHead(t("Əlaqə"), t("Azərbaycan Texniki Universitetinin rəsmi əlaqə məlumatları."), "", [[t("Əsas"), HOME[S.user.role]], [t("Əlaqə")]],
      { info: t("Məlumatlar universitetin rəsmi saytından götürülüb. Struktur bölmələrin əlaqə nömrələri üçün rəsmi saytın “Əlaqə” səhifəsinə baxın.") })}
    <div class="grid g-12">
      <div class="stack">
        <div class="card contact-hero"><div class="card-b">
          <div class="row" style="gap:14px"><img src="/static/img/brand/icon.png" alt="" width="56" height="56" style="border-radius:12px"><div><h2 style="font-size:20px">${c.name}</h2><div class="small muted">${t("{y}-ci ildən", { y: c.founded })}</div></div></div>
          <div class="contact-grid mt">
            <div class="contact-item"><span class="ci-ic">${ic("pin", 18)}</span><div class="grow"><div class="tiny muted">${t("Ünvan")}</div><b>${c.address}</b></div><button class="btn btn-ghost btn-icon btn-sm" data-copy="${c.address}" aria-label="${t("Kopyala")}">${ic("copy", 14)}</button></div>
            <div class="contact-item"><span class="ci-ic">${ic("phone", 18)}</span><div class="grow"><div class="tiny muted">${t("Telefon")}</div><a href="${c.phone_href}"><b>${c.phone}</b></a></div><button class="btn btn-ghost btn-icon btn-sm" data-copy="${c.phone}" aria-label="${t("Kopyala")}">${ic("copy", 14)}</button></div>
            <div class="contact-item"><span class="ci-ic">${ic("mail", 18)}</span><div class="grow"><div class="tiny muted">${t("E-poçt")}</div><a href="mailto:${c.email}"><b>${c.email}</b></a></div><button class="btn btn-ghost btn-icon btn-sm" data-copy="${c.email}" aria-label="${t("Kopyala")}">${ic("copy", 14)}</button></div>
            <div class="contact-item"><span class="ci-ic">${ic("globe", 18)}</span><div class="grow"><div class="tiny muted">${t("Rəsmi sayt")}</div><a href="${c.website}" target="_blank" rel="noopener noreferrer"><b>aztu.edu.az</b></a></div>${ic("external", 14)}</div>
          </div></div></div>
        <div class="map-card" role="img" aria-label="${t("Xəritə: {a}", { a: c.address })}">
          <div class="map-art" aria-hidden="true"><span class="road r1"></span><span class="road r2"></span><span class="road r3"></span><span class="block b1"></span><span class="block b2"></span><span class="block b3"></span>
            <span class="map-pin">${ic("pin", 30)}</span><span class="map-label">AzTU</span></div>
          <div class="map-actions"><div><b>${t("Universitetə necə gəlmək olar?")}</b><div class="small muted">${c.address}</div></div>
            <div class="row wrap"><a class="btn btn-primary btn-sm" href="${c.map.google}" target="_blank" rel="noopener noreferrer">${ic("map", 15)} Google Maps ${ic("external", 12)}</a>
              <a class="btn btn-sm" href="${c.map.osm}" target="_blank" rel="noopener noreferrer">OpenStreetMap ${ic("external", 12)}</a></div></div></div>
        <div class="card"><div class="card-h"><h3>${ic("layers", 17)} ${t("Universitetin rəsmi sistemləri")}</h3></div><div class="card-b sys-grid">
          ${c.systems.map((s) => html`<a class="sys-card" href="${s.url}" target="_blank" rel="noopener noreferrer"><span class="stat-ic ic-navy">${ic(s.icon, 18)}</span><div class="grow"><b>${s.name}</b><div class="tiny muted">${s.text}</div></div>${ic("external", 14)}</a>`)}</div></div>
      </div>
      <div class="stack">
        <div class="card"><div class="card-h"><h3>${ic("message", 17)} ${t("Universitetə sual verin")}</h3></div><form class="card-b stack" id="ask-uni">
          <p class="small muted" style="margin:0">${t("Sualınız dəstək sorğusu kimi qeydə alınır və aidiyyəti bölməyə yönləndirilir.")}</p>
          <label class="field"><span>${t("Mövzu")}</span><input class="input" id="au-subject" maxlength="140" required></label>
          <label class="field"><span>${t("Sualınız")}</span><textarea class="input" id="au-body" rows="4" maxlength="4000" required></textarea></label>
          <button class="btn btn-primary" type="submit">${ic("send", 15)} ${t("Göndər")}</button></form></div>
        <div class="card"><div class="card-h"><h3>${ic("users", 17)} ${t("Sosial şəbəkələr")}</h3></div><div class="card-b social">
          ${c.social.map((s) => html`<a class="social-btn s-${s.key}" href="${s.url}" target="_blank" rel="noopener noreferrer" aria-label="${s.label}">${ic(SOC[s.key] || "globe", 18)}<span>${s.label}</span></a>`)}</div></div>
        <div class="card"><div class="card-h"><h3>${ic("external", 17)} ${t("Faydalı keçidlər")}</h3></div><div class="card-b list">
          ${c.pages.map((pg) => html`<a class="list-item click" href="${pg.url}" target="_blank" rel="noopener noreferrer"><span class="grow small">${pg.name}</span>${ic("external", 13)}</a>`)}</div></div>
        <div class="notice info">${ic("ticket", 16)}<div>${t("Portalla bağlı texniki sual üçün")} <a href="#/support?tab=new">${t("dəstək xidmətinə yazın")}</a>.</div></div>
      </div></div>`);
  on(el, "click", "[data-copy]", (e, b) => copyText(b.dataset.copy));
  $("#ask-uni", el).addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector("[type=submit]"); btn.disabled = true;
    try {
      const r = await api.post("/api/support/tickets", { category: "university", priority: "normal", subject: $("#au-subject", el).value, body: $("#au-body", el).value, page: "/contact" });
      toast(t("Sualınız göndərildi (№ {id})", { id: r.id }), "ok");
      go(`/support/${r.id}`);
    } catch (err) { toast(err.message, "err"); btn.disabled = false; }
  });
});

registerTour("achievements", { route: "/achievements", title: t("AzTU-nun nailiyyətləri"), group: t("Universitet"), icon: "trophy", steps: [
  { sel: ".ach-hero", title: t("Əsas göstəricilər"), text: t("Universitetin reytinqlərdəki mövqeyi və son uğurların qısa xülasəsi.") },
  { sel: ".chips", title: t("Kateqoriyalar"), text: t("Reytinqlər, elm, tələbə uğurları, innovasiya və əməkdaşlıq üzrə süzgəc.") },
  { sel: ".ach-card .btn-primary", title: t("Rəsmi mənbə"), text: t("Hər nailiyyətin orijinal xəbərini universitetin və ya nazirliyin saytında oxuyun.") },
] });
registerTour("contact", { route: "/contact", title: t("Əlaqə"), group: t("Universitet"), icon: "phone", steps: [
  { sel: ".contact-hero", title: t("Rəsmi əlaqə"), text: t("Ünvan, telefon və e-poçt. Kopyalama düyməsi ilə məlumatı tez götürün.") },
  { sel: ".map-card", title: t("Xəritə"), text: t("Universitetin yerini Google Maps və ya OpenStreetMap-də açın.") },
  { sel: "#ask-uni", title: t("Sual verin"), text: t("Sualınız qeydə alınır və cavabı “Dəstək” bölməsində görünür.") },
] });
