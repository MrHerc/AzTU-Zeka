import { api, html, raw, mount, on, md, ic, toast, modal, confirmBox, route, go, S, LANG, t, num, pageHead, fmtDate, ring, progress, loading, empty, failed,
  infoTip, openDoc, openSyllabus, registerTour, refCard, esc, $, $$ } from "./core.js";
import { stat } from "./student.js";

const LET = "ABCD";
const GROUP = () => t("Peşəkar inkişaf");
const crumbsA = (...c) => [[t("Əsas"), "/teacher"], [t("AI Akademiya"), "/teacher/academy"], ...c];
// hours with one decimal, localized separator comes from num()
const hrs = (m) => num(Math.round((m / 60) * 10) / 10, 1);

// ---------------------------------------------------------------- overview
function trackCard(tr, rec) {
  return html`<div class="track slide-up" data-go="/teacher/academy/track/${tr.key}" role="link" tabindex="0" aria-label="${esc(tr.title)}">
    <div class="track-top" style="background:linear-gradient(135deg, ${tr.color}, ${tr.color}cc)"><span class="ti">${ic(tr.icon, 20)}</span>
      <div class="grow"><b>${tr.title}</b><div class="tiny" style="opacity:.85">${t("{n} modul", { n: tr.total })} · ${t("{h} saat", { h: hrs(tr.minutes) })} · ${tr.level}</div></div>
      ${rec ? html`<span class="badge" style="background:#fff;color:var(--coral-700)">${ic("star", 11)} ${t("Tövsiyə")}</span>` : ""}</div>
    <div class="track-b"><div class="small muted">${tr.summary}</div>
      <div class="row between small" style="margin-top:auto"><span class="muted">${t("{done}/{total} modul", { done: tr.done, total: tr.total })}</span><b>${t("{n}%", { n: tr.percent })}</b></div>
      ${progress(tr.percent, tr.percent === 100 ? "green" : "", t("İstiqamətin gedişatı"))}
      ${tr.certificate ? html`<span class="badge b-green">${ic("award", 11)} ${t("Sertifikat alınıb")}</span>` : ""}</div></div>`;
}

function assessmentModal(a, done) {
  const vals = { ...a.assessment };
  const m = modal({ title: t("Özünüqiymətləndirmə"), size: "lg", body: html`<p class="muted" style="margin-top:0">${t("Hər ifadəni 1 (çətinlik çəkirəm) – 5 (əminəm) şkalası ilə qiymətləndirin. Platforma ən çox fayda verəcək 3 istiqaməti tövsiyə edəcək.")}</p>
    <div class="stack">${a.self_assessment.map((s) => html`<div class="row between wrap card pad"><span class="grow" style="min-width:240px">${s.q}</span>
      <div class="scale" role="radiogroup" aria-label="${esc(s.q)}">${[1, 2, 3, 4, 5].map((n) => html`<button type="button" data-tr="${s.track}" data-n="${n}" class="${vals[s.track] === n ? "on" : ""}" role="radio" aria-checked="${vals[s.track] === n}" aria-label="${n}">${n}</button>`)}</div></div>`)}</div>`,
    actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Planı qur"), cls: "btn-primary", onClick: async () => {
      if (Object.keys(vals).length < a.self_assessment.length) { toast(t("Bütün ifadələri qiymətləndirin"), "err"); return false; }
      await api.put("/api/academy/assessment", { values: vals }); toast(t("Fərdi inkişaf planınız yeniləndi"), "ok"); done();
    } }] });
  on(m.el, "click", "[data-tr]", (e, b) => { vals[b.dataset.tr] = +b.dataset.n;
    $$(`[data-tr="${b.dataset.tr}"]`, m.el).forEach((x) => { const onx = x === b; x.classList.toggle("on", onx); x.setAttribute("aria-checked", String(onx)); }); });
}

route("/teacher/academy", async (el) => {
  mount(el, loading());
  let a;
  try { a = await api.get("/api/academy"); } catch (err) { return mount(el, failed(err.message)); }
  const done = a.tracks.reduce((s, tr) => s + tr.done, 0), total = a.tracks.reduce((s, tr) => s + tr.total, 0);
  const pct = Math.round((100 * done) / Math.max(1, total));
  const rec = a.tracks.filter((tr) => a.recommended.includes(tr.key));
  mount(el, html`
    <div class="hero slide-up" data-tour="hero"><div class="row between wrap"><div><h2>${t("AI Akademiya")}</h2>
      <p>${t("Müəllimlər üçün peşəkar inkişaf: süni intellekt, ingilis dilində tədris, akademik ünsiyyət və müasir metodlar.")}</p>
      <div class="row wrap mt"><span class="badge">${ic("clock", 12)} ${t("{h} saat tamamlanıb", { h: hrs(a.hours * 60) })}</span>
        <span class="badge">${ic("award", 12)} ${t("{n} sertifikat", { n: a.certificates.length })}</span><span class="badge">${t("{done}/{total} modul", { done, total })}</span></div></div>
      ${ring(pct, 110, "#fff", t("{n}%", { n: pct }), 10)}</div></div>
    <div class="grid g-12 mt">
      <div class="card brand-border" data-tour="plan"><div class="card-h"><h3>${ic("target", 17)} ${t("Fərdi inkişaf planı")}
          ${infoTip(t("Özünüqiymətləndirmə nəticəsinə görə sizə ən çox fayda verəcək istiqamətlər seçilir. İstədiyiniz vaxt yenidən keçə bilərsiniz."))}</h3>
        <button class="btn btn-sm" id="assess">${ic("sliders", 14)} ${Object.keys(a.assessment).length ? t("Yenidən qiymətləndir") : t("Özünüqiymətləndirmə")}</button></div>
        <div class="card-b">${rec.length ? html`<p class="small muted" style="margin:0 0 10px">${t("Qiymətləndirmənizə əsasən bu istiqamətlərdən başlamağı tövsiyə edirik:")}</p>
          <div class="list">${rec.map((tr, i) => html`<div class="list-item click" data-go="/teacher/academy/track/${tr.key}"><span class="avatar" style="background:${tr.color}">${i + 1}</span>
            <div class="grow"><b class="small">${tr.title}</b><div class="tiny muted">${t("{done}/{total} modul", { done: tr.done, total: tr.total })} · ${t("{h} saat", { h: hrs(tr.minutes) })}</div></div>
            ${tr.next ? html`<button class="btn btn-sm btn-primary" data-go="/teacher/academy/module/${tr.next}">${tr.done ? t("Davam et") : t("Başla")}</button>` : html`<span class="badge b-green">${t("tamamlanıb")}</span>`}</div>`)}</div>`
          : empty("target", t("İnkişaf planı hazır deyil"), t("Bir dəqiqəlik özünüqiymətləndirmədən keçin — sizə uyğun istiqamətləri tövsiyə edək."), { label: t("Özünüqiymətləndirmə"), id: "assess-empty", icon: "sliders" })}</div></div>
      <div class="card" data-tour="certs"><div class="card-h"><h3>${ic("award", 17)} ${t("Sertifikatlar və portfel")}</h3></div><div class="card-b list">
        ${a.certificates.length ? a.certificates.map((c) => html`<div class="list-item"><span class="stat-ic ic-green" style="width:34px;height:34px">${ic("award", 16)}</span>
          <div class="grow"><b class="small">${c.track}</b><div class="tiny muted">${c.reg_no} · ${fmtDate(c.issued_at)}</div></div>
          <button class="btn btn-sm" data-cert="${c.id}" data-ctrack="${esc(c.track)}">${ic("eye", 13)} ${t("Bax")}</button></div>`)
          : empty("award", t("Hələ sertifikat yoxdur"), t("İstiqaməti bitirdikdə QR kodla doğrulanan sertifikat avtomatik verilir."))}
        <div class="tiny muted mt-sm">${t("Peşəkar inkişaf saatları attestasiya üçün portfelinizdə toplanır.")}</div></div></div></div>
    <h3 class="mt" style="font-size:17px;margin-bottom:12px">${t("İstiqamətlər")}</h3>
    <div class="grid g-3" data-tour="tracks">${a.tracks.map((tr) => trackCard(tr, a.recommended.includes(tr.key)))}</div>`);
  on(el, "click", "#assess, #assess-empty", () => assessmentModal(a, () => go("/teacher/academy")));
  on(el, "click", "[data-cert]", (e, b) => openDoc(+b.dataset.cert, t("Sertifikat: {name}", { name: b.dataset.ctrack })));
});

route("/teacher/academy/track/:key", async (el, p) => {
  mount(el, loading());
  let a;
  try { a = await api.get("/api/academy"); } catch (err) { return mount(el, failed(err.message)); }
  const tr = a.tracks.find((x) => x.key === p.key);
  if (!tr) return mount(el, html`${pageHead(t("İstiqamət"), "", "", crumbsA())}
    ${empty("alert", t("İstiqamət tapılmadı"), t("Bu istiqamət mövcud deyil və ya ünvan dəyişib."), { label: t("Bütün istiqamətlər"), go: "/teacher/academy", icon: "cap" })}`);
  mount(el, html`${pageHead(tr.title, t("{level} · {aud}", { level: tr.level, aud: tr.audience }),
      tr.next ? html`<button class="btn btn-ai" data-go="/teacher/academy/module/${tr.next}">${ic("play", 14)} ${tr.done ? t("Davam et") : t("Başla")}</button>` : "",
      crumbsA([tr.title]), { info: t("İstiqamət {total} moduldan ibarətdir, təxminən {h} saat. Modullar ardıcıl açılır, hər birinin sonunda qısa test var.", { total: tr.total, h: hrs(tr.minutes) }) })}
    <div class="grid g-12"><div class="stack" data-tour="modules">${tr.modules.length ? tr.modules.map((m) => html`<div class="mod-row ${m.status === "completed" ? "done" : ""}" data-go="/teacher/academy/module/${m.id}" role="link" tabindex="0">
        <span class="mn">${m.status === "completed" ? raw(ic("check", 14).__html) : m.seq}</span>
        <div class="grow"><b>${m.title}</b><div class="tiny muted">${t("{n} dəq", { n: m.minutes })}${m.score != null ? " · " + t("nəticə {n}%", { n: m.score }) : ""}</div></div>${ic("chevron", 16)}</div>`)
        : empty("book", t("Bu istiqamətdə modul yoxdur"), t("Modullar tezliklə əlavə olunacaq."))}</div>
      <div class="stack"><div class="card"><div class="card-h"><h3>${ic("target", 17)} ${t("Təlim nəticələri")}</h3></div><div class="card-b">
        ${tr.outcomes.map((o) => html`<div class="row small top" style="margin-bottom:6px"><span style="color:var(--green)">${ic("check", 14)}</span> ${o}</div>`)}
        <div class="mt">${progress(tr.percent, tr.percent === 100 ? "green" : "", t("İstiqamətin gedişatı"))}</div>
        <div class="tiny muted mt-sm">${t("{done}/{total} modul tamamlanıb", { done: tr.done, total: tr.total })}</div></div></div>
        ${tr.certificate ? html`<div class="notice ok" data-tour="cert">${ic("award", 18)}<div><b>${t("Sertifikat alınıb")}</b><div class="small mt-sm">${t("Reyestr nömrəsi")}: ${tr.certificate.reg_no}</div>
          <div class="mt-sm"><button class="btn btn-sm btn-primary" data-cert="${tr.certificate.id}">${ic("eye", 13)} ${t("Sertifikata bax")}</button></div></div></div>`
          : html`<div class="notice info" data-tour="cert">${ic("award", 16)}<div>${t("Bütün modulları tamamladıqda QR kodla doğrulanan sertifikat avtomatik veriləcək.")}</div></div>`}</div></div>`);
  on(el, "click", "[data-cert]", (e, b) => openDoc(+b.dataset.cert, t("Sertifikat: {name}", { name: tr.title })));
});

function speak(text) {
  if (!("speechSynthesis" in window)) return toast(t("Brauzer səsləndirməni dəstəkləmir"), "err");
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "en-GB"; u.rate = 0.92;
  speechSynthesis.cancel(); speechSynthesis.speak(u);
}

route("/teacher/academy/module/:id", async (el, p) => {
  mount(el, loading());
  let m;
  try { m = await api.get(`/api/academy/module/${p.id}`); } catch (err) { return mount(el, html`${pageHead(t("Modul"), "", "", crumbsA())}
    ${err.status === 404 ? empty("alert", t("Modul tapılmadı"), t("Bu modul mövcud deyil və ya ünvan dəyişib."), { label: t("AI Akademiya"), go: "/teacher/academy", icon: "cap" }) : failed(err.message)}`); }
  const ans = [];
  mount(el, html`${pageHead(m.title, t("{track} · modul {seq}/{count}", { track: m.track.title, seq: m.seq, count: m.count }),
      m.progress ? html`<span class="badge b-green">${ic("check", 12)} ${t("tamamlanıb · {n}%", { n: m.progress.score })}</span>` : html`<span class="badge b-gray">${t("{n} dəqiqə", { n: m.minutes })}</span>`,
      crumbsA([m.track.title, `/teacher/academy/track/${m.track.key}`], [t("Modul {n}", { n: m.seq })]),
      { info: t("Modulu oxuyun, əsas məqamları və faydalı ifadələri nəzərdən keçirin, praktiki tapşırığı yerinə yetirin və qısa testlə yoxlayın.") })}
    <div data-tour="progress">${progress((100 * m.seq) / m.count, "", t("Modul gedişatı"))}</div>
    <div class="grid g-12 mt"><div class="stack">
      <div class="card pad md" style="font-size:15px">${m.paragraphs.map((x) => html`<p>${x}</p>`)}</div>
      ${m.phrases.length ? html`<div class="card" data-tour="phrases"><div class="card-h"><h3>${ic("globe", 17)} ${t("Faydalı ifadələr")}</h3>
          <span class="tiny muted">${ic("activity", 13)} ${t("tələffüzü dinləyin")}</span></div><div class="card-b stack sm">
        ${m.phrases.map((ph) => html`<div class="phrase ${LANG === "en" ? "en-only" : ""}"><div class="row"><button class="btn btn-ghost btn-icon" data-say="${esc(ph.en)}" aria-label="${t("Dinlə")}">${ic("activity", 16)}</button><span class="en">${ph.en}</span></div>
          ${LANG === "en" ? "" : html`<span class="az">${ph.az}</span>`}</div>`)}</div></div>` : ""}
      <div class="card" data-tour="quiz"><div class="card-h"><h3>${ic("quiz", 17)} ${t("Yoxlama testi")}</h3></div><div class="card-b stack" id="qz">
        ${m.quiz.map((x, i) => html`<div><b>${t("{n}.", { n: i + 1 })} ${x.q}</b><div class="opts mt-sm">${x.o.map((o, j) => html`<button class="opt" data-qi="${i}" data-oi="${j}"><span class="l">${LET[j]}</span><span>${o}</span></button>`)}</div></div>`)}
        <button class="btn btn-ai" id="done">${ic("check", 16)} ${t("Modulu tamamla")}</button></div></div>
      <div class="row between">${m.prev ? html`<button class="btn" data-go="/teacher/academy/module/${m.prev}">${ic("back", 15)} ${t("Əvvəlki")}</button>` : html`<span></span>`}
        ${m.next ? html`<button class="btn" data-go="/teacher/academy/module/${m.next}">${t("Növbəti")} ${ic("chevron", 15)}</button>`
          : html`<button class="btn" data-go="/teacher/academy/track/${m.track.key}">${t("İstiqamətə qayıt")} ${ic("chevron", 15)}</button>`}</div></div>
    <div class="stack"><div class="card"><div class="card-h"><h3>${ic("check", 17)} ${t("Əsas məqamlar")}</h3></div><div class="card-b">
        ${m.key_points.map((k) => html`<div class="row small top" style="margin-bottom:8px"><span style="color:var(--green)">${ic("check", 15)}</span>${k}</div>`)}</div></div>
      <div class="card brand-border" data-tour="task"><div class="card-b"><b class="row" style="gap:6px">${ic("target", 16)} ${t("Praktiki tapşırıq")}</b><p class="small">${m.task}</p>
        ${m.link ? html`<button class="btn btn-sm btn-primary" data-go="${m.link}">${t("Tapşırığa keç")} ${ic("chevron", 14)}</button>` : ""}</div></div>
      ${refCard(m.references, m.references_checked)}
      <div class="notice info">${ic("award", 16)}<div>${t("İstiqamətin bütün modulları tamamlandıqda QR kodla doğrulanan sertifikat avtomatik verilir.")}</div></div></div></div>`);
  on(el, "click", "[data-say]", (e, b) => speak(b.dataset.say));
  on(el, "click", "[data-qi]", (e, b) => { const i = +b.dataset.qi; ans[i] = +b.dataset.oi; $$(`[data-qi="${i}"]`, el).forEach((x) => x.classList.toggle("sel", x === b)); });
  $("#done", el).addEventListener("click", async (e) => {
    if (ans.filter((x) => x !== undefined).length < m.quiz.length) return toast(t("Bütün suallara cavab verin"), "err");
    const btn = e.currentTarget; btn.disabled = true;
    let r;
    try { r = await api.post(`/api/academy/module/${m.id}/complete`, { answers: ans }); } catch (err) { toast(err.message, "err"); btn.disabled = false; return; }
    r.correct.forEach((cr, i) => $$(`[data-qi="${i}"]`, el).forEach((x) => { const j = +x.dataset.oi; x.classList.remove("sel"); x.disabled = true; if (j === cr) x.classList.add("right"); else if (j === ans[i]) x.classList.add("wrong"); }));
    if (!r.passed) { btn.disabled = false; return toast(t("Nəticə {n}% — modulu yenidən nəzərdən keçirin", { n: r.score }), "err"); }
    btn.innerHTML = `${ic("check", 16).__html} ${esc(t("Tamamlandı"))}`;
    if (r.certificate) {
      modal({ title: t("Təbriklər"), body: html`<div class="center"><div class="welcome" style="padding:0"><div class="orb">${ic("award", 30)}</div>
        <h3>${t("“{track}” sertifikatı verildi", { track: m.track.title })}</h3>
        <p>${t("Reyestr nömrəsi")}: <b>${r.certificate.reg_no}</b><br>${t("Doğrulama kodu")}: <b class="mono">${r.certificate.verify_code}</b></p></div></div>`,
        actions: [{ label: t("Bağla"), cls: "btn-ghost" }, { html: `${ic("award", 15).__html} ${esc(t("Sertifikata bax"))}`, cls: "btn-ai", onClick: () => { openDoc(r.certificate.id, t("Sertifikat: {name}", { name: m.track.title })); return false; } }] });
    } else toast(t("Modul tamamlandı ({n}%)", { n: r.score }), "ok");
  });
});

// ---------------------------------------------------------------- tools catalogue
route("/teacher/tools", async (el, p, q) => {
  mount(el, loading());
  let d;
  try { d = await api.get("/api/tools"); } catch (err) { return mount(el, failed(err.message)); }
  let area = "", term = "";
  const brandAbbr = (nm) => (nm.replace(/[^A-Za-zƏə0-9]/g, "").slice(0, 2) || "AI").toUpperCase();
  const priceCls = (tool) => ({ free: "b-green", paid: "b-amber" })[tool.price_tone] || "b-blue";   // tone is language-independent
  const toolCard = (tool) => html`<div class="tool slide-up"><div class="row"><span class="tl" aria-hidden="true">${brandAbbr(tool.name)}</span>
      <div class="grow"><b>${tool.name}</b><div class="tiny muted">${tool.type} · ${tool.platform}</div></div></div>
    <div class="row wrap"><span class="badge ${priceCls(tool)}">${tool.pricing}</span>
      ${tool.areas.some((x) => d.my_areas.includes(x)) ? html`<span class="badge b-coral">${ic("star", 11)} ${t("Kafedranız üçün")}</span>` : ""}</div>
    <div class="small muted">${tool.summary}</div>
    <div class="row wrap" style="margin-top:auto"><button class="btn btn-sm btn-primary" data-tool="${tool.key}">${t("Ətraflı")}</button>
      ${tool.url ? html`<a class="btn btn-sm" href="${tool.url}" target="_blank" rel="noopener noreferrer">${ic("external", 13)} ${t("Rəsmi sayt")}</a>` : ""}</div></div>`;
  const draw = () => {
    const items = d.tools.filter((tool) => (!area || tool.areas.includes(area)) && (!term || (tool.name + " " + tool.summary + " " + tool.type).toLowerCase().includes(term)));
    mount($("#tl", el), items.length ? html`<div class="grid g-3">${items.map(toolCard)}</div>`
      : term ? empty("search", t("Nəticə tapılmadı"), t("“{q}” üzrə alət yoxdur. Başqa açar söz yoxlayın və ya filtri sıfırlayın.", { q: term }), { label: t("Axtarışı təmizlə"), id: "tl-clear", icon: "x" })
        : empty("cpu", t("Bu sahədə alət yoxdur"), t("Başqa sahə seçin və ya bütün alətlərə baxın."), { label: t("Bütün alətlər"), id: "tl-all", icon: "grid" }));
    $$("[data-area]", el).forEach((x) => { const onx = x.dataset.area === area; x.classList.toggle("on", onx); x.setAttribute("aria-pressed", String(onx)); });
  };
  mount(el, html`${pageHead(t("Texnoloji həllər"), t("Fənniniz üçün simulyasiya, virtual laboratoriya, CAD və interaktiv dərs alətləri."), "",
      [[t("Əsas"), "/teacher"], [t("Texnoloji həllər")]], { info: t("Hər alət üçün dərsdə istifadə ssenariləri, başlama addımları və hazır dərs ideyası var. Uyğun alətləri birbaşa öz fənninizə əlavə edə bilərsiniz.") })}
    <div class="row wrap between mb" data-tour="filters"><div class="chips" role="group" aria-label="${t("Sahələr")}">
        <button class="chip" data-area="" aria-pressed="true">${t("Hamısı")}</button>
        ${Object.entries(d.areas).map(([k, l]) => html`<button class="chip" data-area="${k}" aria-pressed="false">${d.my_areas.includes(k) ? html`${ic("star", 12)} ` : ""}${l}</button>`)}</div>
      <input class="input" id="tf" type="search" placeholder="${t("Alət axtarın")}" style="max-width:240px" aria-label="${t("Alət axtarın")}"></div>
    <div id="tl"></div>`);
  draw();
  on(el, "click", "[data-area]", (e, b) => { area = b.dataset.area; draw(); });
  on(el, "click", "#tl-clear", () => { term = ""; $("#tf", el).value = ""; draw(); });
  on(el, "click", "#tl-all", () => { area = ""; draw(); });
  $("#tf", el).addEventListener("input", (e) => { term = e.target.value.trim().toLowerCase(); draw(); });
  const detail = (key) => {
    const tool = d.tools.find((x) => x.key === key);
    if (!tool) return;
    const m = modal({ title: tool.name, size: "lg", body: html`<div class="row wrap mb"><span class="badge b-navy">${tool.type}</span><span class="badge b-gray">${tool.platform}</span><span class="badge ${priceCls(tool)}">${tool.pricing}</span></div>
      <p style="margin-top:0">${tool.summary}</p>
      <div class="grid g-2"><div><div class="label mb-sm">${t("Dərsdə istifadə ssenariləri")}</div>${tool.use_cases.map((u) => html`<div class="row small top" style="margin-bottom:6px">${ic("check", 14)} ${u}</div>`)}</div>
        <div><div class="label mb-sm">${t("Başlamaq üçün 3 addım")}</div><ol class="how">${tool.steps.map((s) => html`<li class="small">${s}</li>`)}</ol></div></div>
      <div class="notice ai mt">${ic("sparkles", 16)}<div><b>${t("Dərs ideyası")}:</b> ${tool.lesson_idea}</div></div>
      ${d.courses.length ? html`<div class="label mb-sm mt">${t("Fənnimə əlavə et")} ${infoTip(t("Əlavə etdiyiniz alət tələbələrə fənn səhifəsində görünəcək."))}</div>
        <div class="chips">${d.courses.map((co) => { const onx = co.tools.includes(tool.key); return html`<button class="chip ${onx ? "on" : ""}" data-ct="${co.id}" aria-pressed="${onx}">${onx ? raw(ic("check", 12).__html) : raw(ic("plus", 12).__html)} ${co.name}</button>`; })}</div>`
        : html`<div class="notice info mt">${ic("info", 16)}<div>${t("Aləti fənnə əlavə etmək üçün sizə təyin olunmuş fənn lazımdır.")}</div></div>`}`,
      actions: [{ label: t("Bağla"), cls: "btn-ghost" }, ...(tool.url ? [{ html: `${ic("external", 15).__html} ${esc(t("Rəsmi sayt"))}`, cls: "btn-primary", onClick: () => { window.open(tool.url, "_blank", "noopener,noreferrer"); return false; } }] : [])] });
    on(m.el, "click", "[data-ct]", async (e, b) => {
      let r;
      try { r = await api.post(`/api/courses/${b.dataset.ct}/tools`, { tool_key: tool.key }); } catch (err) { toast(err.message, "err"); return; }
      const co = d.courses.find((x) => x.id === +b.dataset.ct); co.tools = r.tools;
      b.classList.toggle("on", r.on); b.setAttribute("aria-pressed", String(r.on));
      b.innerHTML = `${(r.on ? ic("check", 12) : ic("plus", 12)).__html} ${esc(co.name)}`;
      toast(r.on ? t("{tool} “{course}” fənninə əlavə edildi", { tool: tool.name, course: co.name }) : t("“{course}” fənnindən çıxarıldı", { course: co.name }), "ok");
    });
  };
  on(el, "click", "[data-tool]", (e, b) => detail(b.dataset.tool));
  if (q.tool) detail(q.tool);
});

// ---------------------------------------------------------------- syllabus assistant
route("/teacher/syllabus", async (el, p, q) => {
  mount(el, loading());
  let cs;
  try { cs = await api.get("/api/courses"); } catch (err) { return mount(el, failed(err.message)); }
  if (!cs.length) return mount(el, html`${pageHead(t("Sillabus köməkçisi"), "", "", [[t("Əsas"), "/teacher"], [t("Sillabus köməkçisi")]])}
    ${empty("layers", t("Fənn tapılmadı"), t("Sillabus hazırlamaq üçün sizə təyin olunmuş fənn lazımdır."), { label: t("Fənlərim"), go: "/teacher/courses", icon: "book" })}`);
  const co = cs.find((x) => x.id === +q.course) || cs[0];
  let saved;
  try { saved = await api.get(`/api/syllabus/${co.id}`); } catch (err) { return mount(el, failed(err.message)); }
  let s = saved.saved;
  let dirty = false;
  const total = () => (s ? s.assessment.reduce((acc, x) => acc + (+x[1] || 0), 0) : 0);
  const draw = () => {
    const sum = total();
    mount(el, html`${pageHead(t("Sillabus köməkçisi"), t("Materiallarınız əsasında sillabus layihəsi — hər bölməni redaktə edə bilərsiniz."),
        html`<label class="sr-only" for="cs">${t("Fənn")}</label><select class="select" id="cs" style="width:auto" aria-label="${t("Fənn")}">${cs.map((x) => html`<option value="${x.id}" ${x.id === co.id ? "selected" : ""}>${x.name}</option>`)}</select>
        <button class="btn btn-ai" id="gen">${ic("sparkles", 15)} ${s ? t("Yenidən hazırla") : t("Layihə hazırla")}</button>`,
        [[t("Əsas"), "/teacher"], [t("Sillabus köməkçisi")]],
        { info: t("Layihə təlim nəticələrini, həftəlik planı, iş yükünü, qiymətləndirməni və qaydaları əhatə edir. Qiymətləndirmə ballarının cəmi 100 olmalıdır. Çap görünüşü portalın daxilində açılır.") })}
      ${!s ? html`<div class="card">${empty("layers", t("Sillabus hazır deyil"), t("“Layihə hazırla” düyməsini seçin — AI materiallarınızdan ilkin variant hazırlayacaq."), { label: t("Layihə hazırla"), id: "gen-empty", icon: "sparkles" })}</div>` : html`
      <div class="row between mb wrap" data-tour="actions"><span class="small muted">${saved.updated_at ? t("Son dəfə saxlanılıb: {d}", { d: fmtDate(saved.updated_at) }) : t("Hələ saxlanılmayıb")}${dirty ? html` · <span class="badge b-amber">${t("Yadda saxlanılmamış dəyişikliklər")}</span>` : ""}</span>
        <div class="row wrap"><button class="btn" id="print">${ic("printer", 15)} ${t("Çap et")}</button><button class="btn btn-primary" id="save">${ic("check", 15)} ${t("Yadda saxla")}</button></div></div>
      <div class="grid g-12"><div class="stack">
        <div class="card"><div class="card-h"><h3>${ic("book", 17)} ${t("Fənnin təsviri")}</h3></div><div class="card-b"><textarea class="textarea" data-k="description" aria-label="${t("Fənnin təsviri")}">${s.description}</textarea></div></div>
        <div class="card" data-tour="outcomes"><div class="card-h"><h3>${ic("target", 17)} ${t("Təlim nəticələri")}</h3><button class="btn btn-sm" id="add-o">${ic("plus", 13)} ${t("Əlavə et")}</button></div><div class="card-b stack sm">
          <div class="tiny muted">${t("Fənni uğurla bitirən tələbə:")}</div>${s.outcomes.map((o, i) => html`<div class="row"><b class="small">${t("{n}.", { n: i + 1 })}</b><input class="input" data-o="${i}" value="${esc(o)}" aria-label="${t("Nəticə {n}", { n: i + 1 })}"><button class="btn btn-ghost btn-icon" data-ro="${i}" aria-label="${t("Sil")}">${ic("x", 14)}</button></div>`)}
          <div class="tiny muted">${t("Məsləhət: “bilir” əvəzinə ölçülə bilən fellər — “izah edir”, “hesablayır”, “layihələndirir”.")}</div></div></div>
        <div class="card"><div class="card-h"><h3>${ic("calendar", 17)} ${t("Həftəlik plan")}</h3></div><div class="table-wrap"><table class="table"><thead><tr><th>${t("Həftə")}</th><th>${t("Mövzu")}</th><th>${t("Fəaliyyət")}</th></tr></thead><tbody>
          ${s.plan.map((w, i) => html`<tr><td><b>${w.week}</b></td><td><input class="input" data-pt="${i}" value="${esc(w.topic)}" aria-label="${t("Mövzu")}"></td><td><input class="input" data-pa="${i}" value="${esc(w.activity)}" aria-label="${t("Fəaliyyət")}"></td></tr>`)}</tbody></table></div></div>
        <div class="card"><div class="card-h"><h3>${ic("shield", 17)} ${t("Qaydalar")}</h3></div><div class="card-b stack sm">${s.policies.map((x, i) => html`<textarea class="textarea" data-pol="${i}" style="min-height:60px" aria-label="${t("Qayda {n}", { n: i + 1 })}">${x}</textarea>`)}</div></div>
      </div><div class="stack">
        <div class="card"><div class="card-h"><h3>${ic("info", 17)} ${t("Fənn haqqında")}</h3></div><div class="card-b review-grid">
          ${[[t("Kod"), s.course.code], [t("Kredit (AKTS)"), s.course.credits], [t("Müəllim"), s.course.teacher], [t("Tədris dili"), s.course.language], [t("Ön şərtlər"), s.course.prereq]].map(([k, v]) => html`<div>${k}</div><div>${v}</div>`)}</div></div>
        <div class="card"><div class="card-h"><h3>${ic("clock", 17)} ${t("İş yükü (AKTS)")}</h3></div><div class="card-b">
          <div class="row between small"><span>${t("Ümumi")}</span><b>${t("{n} saat", { n: s.workload.total })}</b></div><div class="row between small"><span>${t("Auditoriya")}</span><b>${t("{n} saat", { n: s.workload.contact })}</b></div>
          <div class="row between small"><span>${t("Sərbəst iş")}</span><b>${t("{n} saat", { n: s.workload.independent })}</b></div><div class="mt-sm">${progress((100 * s.workload.contact) / Math.max(1, s.workload.total), "", t("Auditoriya payı"))}</div>
          <div class="tiny muted mt-sm">${t("1 kredit ≈ 30 saat ümumi iş yükü; {w} həftə, həftədə {p} cüt dərs.", { w: s.workload.weeks, p: s.workload.pairs })}</div></div></div>
        <div class="card"><div class="card-h"><h3>${ic("chart", 17)} ${t("Qiymətləndirmə")}</h3><span class="badge ${sum === 100 ? "b-green" : "b-red"}" id="asum">${t("Cəmi: {n}", { n: sum })}</span></div><div class="card-b stack sm">
          ${s.assessment.map((a, i) => html`<div class="row"><span class="small grow">${a[0]}</span><input class="input" type="number" data-as="${i}" value="${a[1]}" style="width:80px" min="0" max="100" aria-label="${esc(a[0])}"></div>`)}
          ${sum !== 100 ? html`<div class="tiny" style="color:var(--red)">${t("Ballların cəmi 100 olmalıdır.")}</div>` : ""}</div></div>
        <div class="card"><div class="card-h"><h3>${ic("cpu", 17)} ${t("Rəqəmsal alətlər")}</h3></div><div class="card-b">${s.tools.length ? s.tools.map((tl) => html`<span class="badge b-navy" style="margin:0 6px 6px 0">${tl}</span>`) : html`<span class="small muted">${t("Alət seçilməyib.")}</span>`}
          <div class="mt-sm"><a class="small" href="#/teacher/tools">${t("Kataloqdan alət əlavə et")} ${ic("arrow", 13)}</a></div></div></div>
        <div class="card"><div class="card-h"><h3>${ic("file", 17)} ${t("Materiallar")}</h3></div><div class="card-b">${s.materials.map((mt) => html`<div class="small" style="margin-bottom:4px">• ${mt}</div>`)}</div></div>
      </div></div>`}`);
  };
  draw();
  el.addEventListener("input", (e) => {
    if (!s) return;
    const ds = e.target.dataset;
    if (ds.k) { s[ds.k] = e.target.value; dirty = true; }
    if (ds.o !== undefined) { s.outcomes[+ds.o] = e.target.value; dirty = true; }
    if (ds.pt !== undefined) { s.plan[+ds.pt].topic = e.target.value; dirty = true; }
    if (ds.pa !== undefined) { s.plan[+ds.pa].activity = e.target.value; dirty = true; }
    if (ds.pol !== undefined) { s.policies[+ds.pol] = e.target.value; dirty = true; }
    if (ds.as !== undefined) {
      s.assessment[+ds.as][1] = +e.target.value || 0; dirty = true;
      const sm = total(); const b = $("#asum", el);
      if (b) { b.textContent = t("Cəmi: {n}", { n: sm }); b.className = `badge ${sm === 100 ? "b-green" : "b-red"}`; }
    }
  });
  on(el, "change", "#cs", async (e, n) => {
    if (dirty && !(await confirmBox(t("Yadda saxlanılmamış dəyişikliklər"), t("Dəyişikliklər saxlanılmayıb. Başqa fənnə keçsəniz, itəcək."), t("Davam et")))) { n.value = String(co.id); return; }
    go(`/teacher/syllabus?course=${n.value}`);
  });
  on(el, "click", "#gen, #gen-empty", async (e, b) => {
    if (s && dirty && !(await confirmBox(t("Yenidən hazırla"), t("Mövcud dəyişikliklər yeni layihə ilə əvəz olunacaq."), t("Yenidən hazırla"), true))) return;
    b.disabled = true; b.innerHTML = `<span class="spinner" style="width:14px;height:14px"></span> ${esc(t("Hazırlanır…"))}`;
    try { s = await api.post(`/api/syllabus/${co.id}/generate`, { weeks: 15 }); dirty = true; draw(); toast(t("Layihə hazırdır — redaktə edib yadda saxlayın"), "ok"); }
    catch (err) { toast(err.message, "err"); b.disabled = false; }
  });
  on(el, "click", "#add-o", () => { s.outcomes.push(""); dirty = true; draw(); });
  on(el, "click", "[data-ro]", (e, b) => { s.outcomes.splice(+b.dataset.ro, 1); dirty = true; draw(); });
  const save = async () => {
    const sm = total();
    if (sm !== 100) { toast(t("Qiymətləndirmə ballarının cəmi 100 olmalıdır"), "err"); return false; }
    try { const r = await api.put(`/api/syllabus/${co.id}`, { data: s }); saved.updated_at = r.updated_at; dirty = false; toast(t("Sillabus yadda saxlanıldı"), "ok"); return true; }
    catch (err) { toast(err.message, "err"); return false; }
  };
  on(el, "click", "#save", async () => { if (await save()) draw(); });
  on(el, "click", "#print", async () => { if (dirty && !(await save())) return; openSyllabus(co.id, t("Sillabus: {name}", { name: co.name })); });
});

// ---------------------------------------------------------------- page guides
registerTour("teacher.academy", { route: "/teacher/academy", roles: ["teacher"], title: t("AI Akademiya"), group: GROUP(), icon: "cap", steps: [
  { sel: '[data-tour="hero"]', title: t("Ümumi mənzərə"), text: t("Tamamlanmış saatlar, sertifikatlar və modulların ümumi gedişatı.") },
  { sel: '[data-tour="plan"]', title: t("İnkişaf planı"), text: t("Özünüqiymətləndirmədən keçin — sizə ən uyğun istiqamətlər tövsiyə olunur.") },
  { sel: '[data-tour="certs"]', title: t("Sertifikatlar"), text: t("Qazandığınız sertifikatlar portalın daxilində açılır və attestasiya portfelinizə əlavə olunur.") },
  { sel: '[data-tour="tracks"]', title: t("İstiqamətlər"), text: t("İstiqaməti seçin, modullara baxın və öyrənməyə başlayın.") },
] });
registerTour("teacher.academy.track", { route: "/teacher/academy/track/:key", go: "/teacher/academy/track/ai", roles: ["teacher"], title: t("İstiqamət"), group: GROUP(), icon: "layers", steps: [
  { sel: '[data-tour="modules"]', title: t("Modullar"), text: t("Modullar ardıcıl açılır. Tamamlanan modul yaşıl işarələnir.") },
  { sel: '[data-tour="cert"]', title: t("Sertifikat"), text: t("Bütün modullar tamamlandıqda sertifikat avtomatik verilir.") },
] });
registerTour("teacher.academy.module", { route: "/teacher/academy/module/:id", go: "/teacher/academy/module/1", roles: ["teacher"], title: t("Modul"), group: GROUP(), icon: "book", steps: [
  { sel: '[data-tour="progress"]', title: t("Gedişat"), text: t("İstiqamət daxilində bu modulun yerini göstərir.") },
  { sel: '[data-tour="phrases"]', title: t("Faydalı ifadələr"), text: t("İngilis dilində ifadələri səsləndirmə düyməsi ilə dinləyin.") },
  { sel: '[data-tour="quiz"]', title: t("Yoxlama testi"), text: t("Suallara cavab verin və modulu tamamlayın — nəticə dərhal göstərilir.") },
  { sel: '[data-tour="task"]', title: t("Praktiki tapşırıq"), text: t("Öyrəndiyinizi öz dərsinizdə tətbiq edin.") },
  { sel: '[data-tour="refs"]', title: t("Tövsiyə olunan mənbələr"), text: t("Modulun mövzusu üzrə rəsmi sənədlər və metodik vəsaitlər.") },
] });
registerTour("teacher.tools", { route: "/teacher/tools", roles: ["teacher"], title: t("Texnoloji həllər"), group: GROUP(), icon: "cpu", steps: [
  { sel: '[data-tour="filters"]', title: t("Filtrlər və axtarış"), text: t("Sahə üzrə süzün və ya alət adına görə axtarın. Ulduz kafedranız üçün tövsiyə olunan alətləri göstərir.") },
  { sel: ".tool", title: t("Alət"), text: t("“Ətraflı” düyməsi istifadə ssenarilərini, addımları və dərs ideyasını açır.") },
] });
registerTour("teacher.syllabus", { route: "/teacher/syllabus", roles: ["teacher"], title: t("Sillabus köməkçisi"), group: GROUP(), icon: "layers", steps: [
  { sel: "#gen", title: t("Layihə hazırla"), text: t("AI fənn materiallarınızdan ilkin sillabus variantı qurur.") },
  { sel: '[data-tour="outcomes"]', title: t("Redaktə"), text: t("Hər bölməni dəyişin — təlim nəticələri, həftəlik plan, qiymətləndirmə.") },
  { sel: '[data-tour="actions"]', title: t("Saxla və çap et"), text: t("Dəyişiklikləri yadda saxlayın; çap görünüşü portalın daxilində açılır.") },
] });

export { esc, raw, stat };
