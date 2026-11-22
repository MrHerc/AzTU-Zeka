// Privacy (Task 40): the privacy notice (from the sign-in page, the consent dialog and the profile), the AI study aids'
// consent dialog, the person's own consents, export and deletion request (profile), and the academic office's queue of
// deletion requests.
import { api, html, mount, on, ic, toast, modal, confirmBox, infoTip, route, pageHead, loading, failed, empty, fmtDateTime, t, S } from "./core.js";
import { HOME } from "./shell.js";

const days = (n) => t("{n} gün", { n });
export const REQ_STATUS = () => ({ pending: t("Baxılır"), done: t("Silindi"), rejected: t("Rədd edildi") });

export async function privacyNotice() {
  let p;
  try { p = await api.get("/api/privacy"); } catch (err) { toast(err.message, "err"); return; }
  const r = p.retention;
  const sec = (h, body) => html`<section class="stack" style="gap:6px"><h4 style="margin:0">${h}</h4>${body}</section>`;
  modal({ title: t("Məxfilik bildirişi"), size: "lg", body: html`<div class="stack">
    ${sec(t("Kim emal edir"), html`<p style="margin:0">${t("{operator} Zəka platformasında fərdi məlumatlarınızın operatorudur. Suallarınızı dekanlığa yazın.", { operator: p.operator || t("Universitet") })}</p>`)}
    ${sec(t("Hansı məlumatlar"), html`<p style="margin:0">${t("Universitet reyestrindən gələn şəxsi və təhsil məlumatları; davamiyyət, qiymətlər, imtahan cəhdləri və verilmiş sənədlər; müraciətləriniz, mesajlarınız və AI söhbətləriniz; giriş və audit jurnalları.")}</p>`)}
    ${sec(t("Nə üçün"), html`<p style="margin:0">${t("Təhsil prosesini təşkil etmək, qanunla tələb olunan akademik qeydləri aparmaq, e-xidmətləri göstərmək və platformanın təhlükəsizliyini qorumaq. AI tutor və kampus köməkçisi istəyə bağlı köməkçilərdir: suallarınızı yalnız razılığınızla emal edir, razılıq vermədən də portalın qalan bölmələrindən tam istifadə edə bilərsiniz.")}</p>`)}
    ${sec(t("Xarici AI xidməti"), html`<p style="margin:0">${t("Suallarınız xarici AI xidmətinə yalnız ayrıca razılığınızla və şəxsi məlumatlar maskalandıqdan sonra göndərilir. Razılıq mətni və ya xidmət dəyişəndə razılıq yenidən soruşulur.")}</p>
      <p style="margin:0">${p.external_ai.enabled
        ? t("Qoşulmuş xidmət: {vendor}. Xidmətin yerləşdiyi ölkə: {country}.", { vendor: p.external_ai.vendor || t("göstərilməyib"), country: p.external_ai.country || t("göstərilməyib") })
        : t("Hazırda xarici AI xidməti qoşulmayıb: suallarınıza platformanın öz mühərriki cavab verir.")}</p>`)}
    ${sec(t("Razılıq mətnləri"), html`<ul class="consent-list">${p.purposes.map((x) => html`<li>${ic("check", 15)} <span>${x.text} <span class="tiny muted">(${t("versiya")} ${x.version})</span></span></li>`)}</ul>`)}
    ${sec(t("Saxlama müddəti"), html`<ul class="consent-list">
      <li>${ic("clock", 15)} <span>${t("AI söhbətləri")}: ${days(r.chats_days)}</span></li>
      <li>${ic("clock", 15)} <span>${t("Klub mesajları")}: ${days(r.community_days)}</span></li>
      <li>${ic("clock", 15)} <span>${t("Bildirişlər")}: ${days(r.notifications_days)}</span></li>
      <li>${ic("clock", 15)} <span>${t("Texniki jurnallar")}: ${days(r.logs_days)}</span></li>
      <li>${ic("clock", 15)} <span>${t("Audit jurnalı")}: ${days(r.audit_days)}</span></li>
      <li>${ic("lock", 15)} <span>${t("Qiymətlər, davamiyyət, imtahan qeydləri və verilmiş sənədlər: qanunun tələb etdiyi müddət.")}</span></li></ul>`)}
    ${sec(t("Hüquqlarınız"), html`<p style="margin:0">${t("Profil səhifəsində məlumatlarınızın surətini yükləyə, razılığı geri götürə və məlumatlarınızın silinməsini istəyə bilərsiniz. AI tutor və kampus köməkçisi üçün razılığı geri götürəndə bu köməkçilərlə söhbətləriniz silinir. Qanunla saxlanmalı qeydlər (qiymətlər, davamiyyət, imtahan qeydləri, verilmiş sənədlər) silinmir; hesabınızdan ad və əlaqə məlumatları silinir.")}</p>
      <p class="small muted" style="margin:0">${t("İmtahan variantları, imtahan sualları və açıqlanmamış imtahan balları ixraca düşmür. Nəticə açıqlanandan sonra ixracda yalnız öz cavablarınız və balınız olur.")}</p>`)}
  </div>`, actions: [{ label: t("Bağla"), cls: "btn-primary" }] });
}
document.addEventListener("click", (e) => { const a = e.target.closest("[data-privacy-notice]"); if (a) { e.preventDefault(); privacyNotice(); } });

const current = (x) => !!(x && x.consent && x.consent.granted && x.consent.current);

// The AI tutor and the campus assistant are optional study aids: their page asks for the consent when the person has
// none to the current text, and "not now" leaves only them closed. Resolves whether the consent is already in place;
// otherwise the dialog stays open and ``onGiven`` runs once the person consents.
export async function aiConsent(onGiven) {
  let p;
  try { p = await api.get("/api/privacy"); } catch { return false; }
  const [ai, ext] = ["ai", "external_ai"].map((id) => p.purposes.find((x) => x.id === id));
  if (current(ai)) return true;
  let given = false;
  modal({
    title: t("Məlumatlarınızın emalı"), onClose: () => { if (given) onGiven(); }, body: html`<div class="stack">
      <p style="margin:0">${t("AI tutor və kampus köməkçisi istəyə bağlı köməkçilərdir və suallarınızı yalnız razılığınızla emal edir. Razılıq vermədən də portalın qalan bölmələrindən tam istifadə edə bilərsiniz.")}</p>
      <ul class="consent-list">
        <li>${ic("shield", 15)} <span>${t("Şəxsi məlumatlar (FİN, telefon, e-poçt) AI-yə göndərilməzdən əvvəl maskalanır.")}</span></li>
        <li>${ic("lock", 15)} <span>${t("Tələbə məlumatları AI modellərini öyrətmək üçün istifadə edilmir.")}</span></li>
        <li>${ic("eye", 15)} <span>${t("Tibbi sənədləri yalnız dekanlıq görür; müəllim fərdi söhbətlərinizi görmür.")}</span>
          ${infoTip(t("Söhbətlər universitet platformasında {n} gün saxlanılır. Hər sənədə baxış audit jurnalına yazılır.", { n: p.retention.chats_days }))}</li>
      </ul>
      <label class="check"><input type="checkbox" id="c1"> ${ai.text}</label>
      <label class="check"><input type="checkbox" id="c2" ${current(ext) ? "checked" : ""}> ${ext.text} <span class="tiny muted">(${t("istəyə görə")})</span></label>
      <span class="tiny muted">${t("Razılığı istənilən vaxt “Profil” bölməsində geri götürə bilərsiniz.")} <a href="#" data-privacy-notice>${t("Məxfilik bildirişi")}</a></span></div>`,
    actions: [{ label: t("İndi yox"), cls: "btn-ghost" }, { label: t("Qəbul edirəm"), cls: "btn-primary", onClick: async (w) => {
      if (!w.querySelector("#c1").checked) { toast(t("AI köməkçilərindən istifadə üçün birinci razılıq lazımdır"), "err"); return false; }
      await api.post("/api/consent", { ai: true, external: w.querySelector("#c2").checked, versions: { ai: ai.version, external_ai: ext.version } });
      given = true; toast(t("Razılığınız qeydə alındı"), "ok");
    } }],
  });
  return false;
}

const consentLine = (x) => !x.consent ? t("Razılıq verilməyib")
  : !x.consent.granted ? `${t("Geri götürülüb")}: ${fmtDateTime(x.consent.at)}`
  : !x.consent.current ? t("Mətn yenilənib: yenidən razılıq lazımdır")
  : `${t("Razılıq verilib")}: ${fmtDateTime(x.consent.at)}`;

// The profile's privacy card: each purpose's state, export, the deletion request.
export async function privacyCard(box) {
  const draw = async () => {
    let p;
    try { p = await api.get("/api/privacy"); } catch { return mount(box, html`<span class="small muted">—</span>`); }
    const reqs = p.requests || [], pending = reqs.some((r) => r.status === "pending");
    mount(box, html`${p.purposes.map((x) => html`<div class="set-row"><div><span class="small">${x.text}</span><div class="small muted">${consentLine(x)}</div></div>
          ${current(x) ? html`<button class="btn btn-sm btn-ghost" data-consent="${x.id}" data-version="${x.version}" data-grant="0">${t("Geri götür")}</button>`
            : html`<button class="btn btn-sm" data-consent="${x.id}" data-version="${x.version}" data-grant="1">${t("Razılıq ver")}</button>`}</div>`)}
      <ul class="consent-list"><li>${ic("shield", 15)} <span>${t("Şəxsi məlumatlar AI xidmətlərinə göndərilməzdən əvvəl maskalanır.")}</span></li>
        <li>${ic("lock", 15)} <span>${t("Tələbə məlumatları ilə AI modeli öyrədilmir.")}</span></li>
        <li>${ic("eye", 15)} <span>${t("Tibbi və sosial sənədlərə yalnız dekanlıq baxa bilər; hər baxış audit jurnalına yazılır.")}</span></li></ul>
      <div class="row wrap"><button class="btn btn-sm" id="pv-export">${ic("download", 15)} ${t("Məlumatlarımı yüklə")}</button>
        <button class="btn btn-sm btn-danger" id="pv-erase" ${pending ? "disabled" : ""}>${ic("trash", 15)} ${t("Məlumatlarımın silinməsini istə")}</button>
        <button class="btn btn-sm btn-ghost" data-privacy-notice>${t("Məxfilik bildirişi")}</button></div>
      ${reqs.slice(0, 3).map((r) => html`<p class="small muted" style="margin:0">${t("Silmə sorğusu")}: ${fmtDateTime(r.created_at)} · ${REQ_STATUS()[r.status] || r.status}${r.note ? ` · ${r.note}` : ""}</p>`)}`);
  };
  on(box, "click", "[data-consent]", async (e, b) => {
    const id = b.dataset.consent, grant = b.dataset.grant === "1";
    if (id === "ai" && !grant && !(await confirmBox(t("AI razılığını geri götürmək?"),
      t("AI tutor və kampus köməkçisi sizin üçün bağlanacaq, bu köməkçilərlə bütün söhbətləriniz silinəcək. Portalın qalan bölmələri əvvəlki kimi işləyəcək. Razılığı sonra yenidən verə bilərsiniz."),
      t("Geri götür"), true))) return;
    try {
      await api.post("/api/consent", { [id === "ai" ? "ai" : "external"]: grant, versions: { [id]: b.dataset.version } });
      toast(grant ? t("Razılığınız qeydə alındı") : t("Razılıq geri götürüldü"), "ok"); draw();
    } catch (err) { toast(err.message, "err"); draw(); }
  });
  on(box, "click", "#pv-export", async (e, b) => {
    b.classList.add("loading");
    try {
      const data = await api.get("/api/me/export");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 1)], { type: "application/json" }));
      a.download = `zeka-export-${new Date().toISOString().slice(0, 10)}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (err) { toast(err.message, "err"); } finally { b.classList.remove("loading"); }
  });
  on(box, "click", "#pv-erase", () => modal({ title: t("Məlumatlarımın silinməsi"), body: html`<div class="stack">
      <p style="margin:0">${t("Sorğunu tədris şöbəsi yoxlayır. Təsdiq olunsa, söhbətləriniz, mesajlarınız, bildirişləriniz və hesabınıza giriş silinir; qanunla saxlanmalı akademik qeydlər qalır, hesabınızdan ad və əlaqə məlumatları silinir. Bu əməliyyat geri qaytarılmır.")}</p>
      <label class="field"><span>${t("Səbəb")} <span class="muted">(${t("istəyə görə")})</span></span><textarea class="input" id="pv-reason" rows="3" maxlength="1000"></textarea></label></div>`,
    actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Sorğunu göndər"), cls: "btn-danger", onClick: async (w) => {
      try { await api.post("/api/me/erase", { reason: w.querySelector("#pv-reason").value }); toast(t("Sorğu göndərildi"), "ok"); draw(); }
      catch (err) { toast(err.message, "err"); return false; }
    } }] }));
  await draw();
}

// The academic office's queue (privacy.decide)
route("/staff/privacy", async (el) => {
  const draw = async () => {
    let r;
    try { r = await api.get("/api/privacy/requests"); } catch (err) { return mount(el, failed(err.message)); }
    mount(el, html`${pageHead(t("Məxfilik sorğuları"), t("Məlumatların silinməsi sorğuları: təsdiq inventara görə silir və ya anonimləşdirir."), "", [[t("Əsas"), HOME[S.user.role] || "/"], [t("Məxfilik sorğuları")]])}
      ${r.items.length ? html`<div class="card"><div class="card-b stack">${r.items.map((x) => html`<div class="set-row"><div><b>${x.full_name}</b> <span class="small muted">${x.username}${x.student_no ? ` · ${x.student_no}` : ""}</span>
          <div class="small muted">${fmtDateTime(x.created_at)} · ${REQ_STATUS()[x.status] || x.status}${x.reason ? ` · ${x.reason}` : ""}${x.note ? ` · ${x.note}` : ""}</div></div>
          ${x.status === "pending" ? html`<div class="row"><button class="btn btn-sm btn-danger" data-decide="${x.id}" data-ok="1">${t("Təsdiqlə və sil")}</button>
            <button class="btn btn-sm" data-decide="${x.id}" data-ok="0">${t("Rədd et")}</button></div>` : ""}</div>`)}</div></div>`
        : empty("shield", t("Sorğu yoxdur"))}`);
  };
  on(el, "click", "[data-decide]", (e, b) => modal({ title: b.dataset.ok === "1" ? t("Silməni təsdiqlə") : t("Sorğunu rədd et"), size: "sm",
    body: html`<label class="field"><span>${t("Qeyd")}</span><textarea class="input" id="pv-note" rows="3" maxlength="1000"></textarea></label>`,
    actions: [{ label: t("Ləğv et"), cls: "btn-ghost" }, { label: t("Təsdiqlə"), cls: b.dataset.ok === "1" ? "btn-danger" : "btn-primary", onClick: async (w) => {
      try { await api.post(`/api/privacy/requests/${b.dataset.decide}/decide`, { approve: b.dataset.ok === "1", note: w.querySelector("#pv-note").value }); toast(t("Saxlanıldı"), "ok"); draw(); }
      catch (err) { toast(err.message, "err"); return false; }
    } }] }));
  mount(el, loading());
  await draw();
});
