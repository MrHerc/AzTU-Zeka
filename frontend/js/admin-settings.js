// University settings (Task 17): profile, grading scheme, attendance rules, journal cut-over, lesson times and holidays,
// document register, sessions, single sign-on, activation codes. Each card saves one section; the server checks it.
// List values are edited one item per line: "Name | max | attendance", "A 91", "10 9", "09:00-10:20", "2026-01-01".
import { api, html, mount, on, ic, toast, route, pageHead, loading, failed, $, t, S } from "./core.js";
import { HOME } from "./shell.js";

const lines = (v) => v.split("\n").map((x) => x.trim()).filter(Boolean);
const num = (v) => (v === "" || v == null ? null : Number(String(v).replace(",", ".")));
const list = (v) => v.split(",").map((x) => x.trim()).filter(Boolean);

const READ = {
  university: (w, v) => Object.fromEntries(["name", "name_en", "short", "platform", "semester", "semester_en", "semester_dates", "address", "site", "city", "city_en"]
    .map((k) => [k, $(`[name=u-${k}]`, w).value])),
  grading: (w) => ({
    components: lines($("[name=g-components]", w).value).map((x) => { const [name, max, att] = x.split("|").map((y) => y.trim());
      return { name, max: num(max), ...(att ? { attendance: true } : {}) }; }),
    exam: { name: $("[name=g-exam-name]", w).value.trim(), max: num($("[name=g-exam-max]", w).value), min: num($("[name=g-exam-min]", w).value) },
    pass_mark: num($("[name=g-pass]", w).value),
    scale: lines($("[name=g-scale]", w).value).map((x) => { const [l, lo] = x.split(/\s+/); return [l, num(lo)]; }) }),
  attendance: (w) => ({ limit_percent: num($("[name=a-limit]", w).value), excused_counts_toward_limit: $("[name=a-excused]", w).checked,
    points_rule: lines($("[name=a-rule]", w).value).map((x) => x.split(/[\s→>-]+/).filter(Boolean).map(num)) }),
  journal: (w) => ({ cutover_date: $("[name=j-cutover]", w).value || null, edit_hours: Number($("[name=j-hours]", w).value) }),
  calendar: (w) => ({ lesson_times: lines($("[name=c-times]", w).value).map((x) => x.split(/\s*[-–]\s*/)), holidays: lines($("[name=c-holidays]", w).value) }),
  registry: (w) => ({ prefix: $("[name=r-prefix]", w).value.trim() }),
  sessions: (w) => ({ staff: { idle_minutes: num($("[name=s-staff-idle]", w).value), absolute_hours: num($("[name=s-staff-abs]", w).value) },
    student: { idle_minutes: num($("[name=s-student-idle]", w).value), absolute_hours: num($("[name=s-student-abs]", w).value) } }),
  sso: (w) => ({ enabled: $("[name=o-enabled]", w).checked, issuer: $("[name=o-issuer]", w).value.trim() || null, client_id: $("[name=o-client]", w).value.trim() || null,
    label: $("[name=o-label]", w).value.trim() || null, student_claim: $("[name=o-claim]", w).value.trim() || null,
    scopes: list($("[name=o-scopes]", w).value), mfa_amr: list($("[name=o-amr]", w).value), mfa_acr: list($("[name=o-acr]", w).value) }),
  activation: (w) => ({ days: num($("[name=v-days]", w).value) }),
  retention: (w) => Object.fromEntries(["chats_days", "community_days", "notifications_days", "logs_days", "audit_days"].map((k) => [k, num($(`[name=p-${k}]`, w).value)])),
};

const field = (name, label, value, type = "text", extra = "") => html`<div class="field"><label class="label" for="${name}">${label}</label>
  <input class="input" id="${name}" name="${name}" type="${type}" value="${value ?? ""}" ${extra}></div>`;
const area = (name, label, value, hint) => html`<div class="field"><label class="label" for="${name}">${label}</label>
  <textarea class="textarea" id="${name}" name="${name}" rows="5" spellcheck="false">${value}</textarea>${hint ? html`<span class="tiny muted">${hint}</span>` : ""}</div>`;
const card = (section, icon, title, body) => html`<div class="card" data-section="${section}"><div class="card-h"><h3>${ic(icon, 17)} ${title}</h3>
  <button class="btn btn-sm btn-primary" data-save="${section}">${t("Saxla")}</button></div><div class="card-b stack">${body}</div></div>`;

function view(s) {
  const u = s.university, g = s.grading, a = s.attendance, cal = s.calendar, o = s.sso;
  return html`<div class="grid g-2">
    ${card("university", "building", t("Universitet profili"), html`${field("u-name", t("Ad"), u.name)}${field("u-name_en", t("Ad (ingiliscə)"), u.name_en)}
      <div class="row wrap">${field("u-short", t("Qısa ad"), u.short)}${field("u-platform", t("Platformanın adı"), u.platform)}</div>
      ${field("u-semester", t("Cari dövrün adı"), u.semester)}${field("u-semester_en", t("Cari dövrün adı (ingiliscə)"), u.semester_en)}
      ${field("u-semester_dates", t("Dövrün tarixləri (göstərmək üçün)"), u.semester_dates)}
      ${field("u-address", t("Ünvan"), u.address)}<div class="row wrap">${field("u-city", t("Şəhər"), u.city)}${field("u-city_en", t("Şəhər (ingiliscə)"), u.city_en)}</div>
      ${field("u-site", t("Sayt"), u.site)}`)}
    ${card("grading", "target", t("Qiymətləndirmə sxemi"), html`
      ${area("g-components", t("Komponentlər"), g.components.map((x) => `${x.name} | ${x.max}${x.attendance ? " | davamiyyət" : ""}`).join("\n"),
        t("Hər sətirdə: ad | maksimal bal | (davamiyyətdirsə) davamiyyət. Komponentlər və imtahan birlikdə 100 bal edir."))}
      <div class="row wrap">${field("g-exam-name", t("İmtahan"), g.exam.name)}${field("g-exam-max", t("İmtahanın maksimumu"), g.exam.max, "number")}
        ${field("g-exam-min", t("İmtahan minimumu"), g.exam.min, "number")}${field("g-pass", t("Keçid balı"), g.pass_mark, "number")}</div>
      ${area("g-scale", t("Hərf şkalası"), g.scale.map((x) => `${x[0]} ${x[1]}`).join("\n"), t("Hər sətirdə: hərf və aşağı hədd, yuxarıdan aşağı; son hədd keçid balıdır."))}`)}
    ${card("attendance", "calcheck", t("Davamiyyət"), html`${field("a-limit", t("Buraxılmış dərslərin həddi, %"), a.limit_percent, "number")}
      <label class="check"><input type="checkbox" name="a-excused" ${a.excused_counts_toward_limit ? "checked" : ""}> ${t("Üzrlü qayıb həddə sayılır")}</label>
      ${area("a-rule", t("Davamiyyət balı cədvəli"), a.points_rule.map((x) => `${x[0]} ${x[1]}`).join("\n"),
        t("Hər sətirdə: buraxılmış faiz (bu həddədək) və bal. Boş qalsa, bal iştirak faizinə mütənasibdir."))}`)}
    ${card("journal", "book", t("Elektron jurnal"), html`${field("j-cutover", t("Kəsid tarixi: jurnalın Zəka-da başladığı gün"), s.journal.cutover_date, "date")}
      <p class="small muted" style="margin:0">${t("Boşdursa və ya cari tədris dövründən kənardırsa, kəsid yoxdur.")}</p>
      ${field("j-hours", t("Müəllimin düzəliş pəncərəsi (dərs bitəndən sonra, saat)"), s.journal.edit_hours ?? 48, "number")}`)}
    ${card("calendar", "calendar", t("Dərs saatları və bayramlar"), html`${area("c-times", t("Dərs saatları"), cal.lesson_times.map((x) => x.join("-")).join("\n"), t("Hər sətirdə: 09:00-10:20"))}
      ${area("c-holidays", t("Bayram günləri"), cal.holidays.join("\n"), t("Hər sətirdə bir tarix: İİİİ-AA-GG"))}`)}
    ${card("registry", "file", t("Sənəd reyestri"), html`${field("r-prefix", t("Reyestr prefiksi"), s.registry.prefix)}
      <p class="small muted" style="margin:0">${t("Yeni sənədlərin nömrəsi bununla başlayır; verilmiş sənədlərin nömrəsi dəyişmir.")}</p>`)}
    ${card("sessions", "lock", t("Sessiyalar"), html`<div class="row wrap">${field("s-staff-idle", t("İşçi: boş qalma, dəq"), s.sessions.staff.idle_minutes, "number")}
        ${field("s-staff-abs", t("İşçi: ümumi, saat"), s.sessions.staff.absolute_hours, "number")}</div>
      <div class="row wrap">${field("s-student-idle", t("Tələbə: boş qalma, dəq"), s.sessions.student.idle_minutes, "number")}
        ${field("s-student-abs", t("Tələbə: ümumi, saat"), s.sessions.student.absolute_hours, "number")}</div>`)}
    ${card("sso", "link", t("Vahid giriş (OIDC)"), html`<label class="check"><input type="checkbox" name="o-enabled" ${o.enabled ? "checked" : ""}> ${t("Vahid giriş açıqdır")}</label>
      ${field("o-issuer", t("Issuer (https)"), o.issuer)}${field("o-client", "client_id", o.client_id)}${field("o-label", t("Düymənin adı"), o.label)}
      ${field("o-claim", t("Tələbə nömrəsinin iddiası"), o.student_claim)}${field("o-scopes", t("Əlavə scope-lar (vergüllə)"), (o.scopes || []).join(", "))}
      ${field("o-amr", t("Etibarlı amr dəyərləri (vergüllə)"), (o.mfa_amr || []).join(", "))}${field("o-acr", t("Etibarlı acr dəyərləri (vergüllə)"), (o.mfa_acr || []).join(", "))}
      <p class="small muted" style="margin:0">${t("Müştəri sirri burada saxlanmır: serverdə ZEKA_OIDC_CLIENT_SECRET mühit dəyişənidir.")}</p>`)}
    ${card("activation", "users", t("Aktivləşdirmə kodları"), html`${field("v-days", t("Kodun müddəti, gün"), s.activation.days, "number")}`)}
    ${card("retention", "clock", t("Saxlama müddətləri"), html`<div class="row wrap">${field("p-chats_days", t("AI söhbətləri, gün"), s.retention.chats_days, "number")}
        ${field("p-community_days", t("Klub mesajları, gün"), s.retention.community_days, "number")}${field("p-notifications_days", t("Bildirişlər, gün"), s.retention.notifications_days, "number")}</div>
      <div class="row wrap">${field("p-logs_days", t("Texniki jurnallar, gün"), s.retention.logs_days, "number")}${field("p-audit_days", t("Audit jurnalı, gün"), s.retention.audit_days, "number")}</div>
      <p class="small muted" style="margin:0">${t("Gündəlik təmizləmə işi bu müddətdən köhnə sətirləri silir. Akademik qeydlər və imtahan jurnalı silinmir.")}</p>`)}
  </div>`;
}

// Task 46: which e-services are offered. A flag per type only (no form or step editor); a type whose effect is not
// registered in code cannot be opened (the server refuses it, the switch is disabled).
const offer = (types) => html`<div class="card mt" data-offer><div class="card-h"><h3>${ic("grid", 17)} ${t("E-xidmətlər")}</h3></div><div class="card-b stack">
  <p class="small muted" style="margin:0">${t("Açılan xidmət tələbələrə təklif olunur; bağlı xidmət kataloqda, axtarışda və köməkçidə görünmür.")}</p>
  ${types.map((x) => html`<label class="row"><span class="switch"><input type="checkbox" data-type="${x.code}" ${x.enabled ? "checked" : ""} ${x.registered ? "" : "disabled"}
    aria-label="${x.name}"><span></span></span><span class="grow small">${x.name} <span class="tiny muted">· ${x.effect}</span></span></label>`)}</div></div>`;

route("/admin/settings", async (el) => {
  const head = pageHead(t("Universitet ayarları"), t("Universitetə aid qaydalar: kod dəyişmədən tətbiq olunur. Hər bölmə ayrıca yoxlanıb saxlanır."), "",
    [[t("Əsas"), HOME[S.user.role]], [t("Universitet ayarları")]]);
  let types = [];
  const draw = (s) => mount(el, html`${head}${view(s)}${offer(types)}`);
  mount(el, loading());
  try { const [s, ts] = await Promise.all([api.get("/api/admin/settings"), api.get("/api/admin/request-types")]); types = ts; draw(s); }
  catch (err) { mount(el, failed(err.message)); return; }
  on(el, "change", "[data-type]", async (e, b) => {
    try { types = await api.put(`/api/admin/request-types/${b.dataset.type}`, { enabled: b.checked }); toast(t("Saxlanıldı"), "ok"); }
    catch (err) { b.checked = !b.checked; toast(err.message, "err"); }
  });
  on(el, "click", "[data-save]", async (e, b) => {
    const section = b.dataset.save;
    b.classList.add("loading");
    try {
      const s = await api.put(`/api/admin/settings/${section}`, { value: READ[section](b.closest("[data-section]")) });
      if (section === "university") S.app.university = s.university;
      if (section === "grading") S.app.grading = { pass_mark: s.grading.pass_mark, scale: s.grading.scale };
      draw(s);
      toast(t("Saxlanıldı"), "ok");
    } catch (err) { b.classList.remove("loading"); toast(err.message, "err"); }
  });
});
