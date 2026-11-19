"""Printable documents and the public verification page (server-rendered, in the university's name: Task 17)."""
from __future__ import annotations

import html
import json
from datetime import datetime

from .engine import translit
from ..core import tenant
from ..core.i18n import S
from .qr import qr_svg

e = html.escape

PLACE_AZ = {"Hərbi komissarlıq": "hərbi komissarlığa", "Dövlət Sosial Müdafiə Fondu (DSMF)": "Dövlət Sosial Müdafiə Fonduna",
            "Bank": "banka", "Səfirlik / viza": "səfirliyə (viza məqsədilə)", "İş yeri": "iş yerinə",
            "ASAN xidmət / dövlət qurumu": "aidiyyəti dövlət qurumuna"}
PLACE_EN = {"Hərbi komissarlıq": "the military commissariat", "Dövlət Sosial Müdafiə Fondu (DSMF)": "the State Social Protection Fund",
            "Bank": "the bank", "Səfirlik / viza": "the embassy for visa purposes", "İş yeri": "the employer",
            "ASAN xidmət / dövlət qurumu": "the relevant state authority"}
FUND_EN = {"Dövlət sifarişi": "state-funded", "Ödənişli": "tuition-paying"}


def ordinal(n: int) -> str:
    """English ordinal: 1st, 2nd, 3rd, 4th … 11th, 12th, 13th, 21st."""
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


_AZ_ORD_UNITS = {1: "ci", 2: "ci", 3: "cü", 4: "cü", 5: "ci", 6: "cı", 7: "ci", 8: "ci", 9: "cu"}
_AZ_ORD_TENS = {1: "cu", 2: "ci", 3: "cu", 4: "cı", 5: "ci", 6: "cı", 7: "ci", 8: "ci", 9: "cı"}


def az_ordinal(n: int) -> str:
    """Azerbaijani ordinal with vowel harmony: 1-ci, 3-cü, 6-cı, 9-cu, 10-cu, 40-cı, 100-cü."""
    if n % 10:
        suffix = _AZ_ORD_UNITS[n % 10]
    elif n % 100:
        suffix = _AZ_ORD_TENS[n % 100 // 10]
    else:
        suffix = "cü" if n % 1000 else "ci"          # yüzüncü, mininci
    return f"{n}-{suffix}"


def dmy(iso_ts: str, with_time: bool = False) -> str:
    dt = datetime.fromisoformat(iso_ts)
    return dt.strftime("%d.%m.%Y %H:%M" if with_time else "%d.%m.%Y")


def _page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="az"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title>
<link rel="icon" href="/static/img/brand/icon.png"><link rel="stylesheet" href="/static/css/doc.css"></head><body>{body}
<script src="/static/js/print.js"></script></body></html>"""


def _head(uni, unit_az, unit_en, en):
    return f"""<header class="doc-head"><img class="crest" src="/static/img/brand/icon.png" alt="{e(uni['short'])}">
  <div><div class="org">{e((uni['name_en'] if en else uni['name']).upper())}</div>
  <div class="sub">{e(unit_en if en else unit_az)} · {e(uni['address'])} · {e(uni['site'])}</div></div></header>"""


def _sign(doc, issuer, qr, en, role_az="Tədris hissəsi", role_en="Registrar's Office"):
    return f"""<div class="sign">
    <div><div class="role">{e(role_en if en else role_az)}</div><div class="esign">✓ {'Electronically approved' if en else 'Elektron təsdiqlənib'}<br>
      <span>{e(issuer['full_name'])} · {dmy(doc['issued_at'], True)}</span></div></div>
    <div class="qr">{qr}<small>{'Verification code' if en else 'Doğrulama kodu'}<br><b>{e(doc['verify_code'])}</b></small></div></div>"""


def _foot(doc, verify_url, platform, en):
    if en:
        return (f'<footer class="doc-foot">Verify this document by scanning the QR code or at {e(verify_url)}.<br>'
                f'SHA-256: {e(doc["hash"][:16])}… · generated on the {e(platform)} platform · DEMO — not legally valid.</footer>')
    return (f'<footer class="doc-foot">Sənədin həqiqiliyini QR kodu skan etməklə və ya {e(verify_url)} ünvanında yoxlaya bilərsiniz.<br>'
            f'SHA-256: {e(doc["hash"][:16])}… · {e(platform)} platformasında yaradılıb · DEMO — hüquqi qüvvəsi yoxdur. '
            f'Pilotda ASAN İmza / SİMA ilə imzalanacaq.</footer>')


def enrollment_body(holder, data, ctx, en):
    uni, fac, sp = ctx["university"], ctx["faculty"], ctx["specialty"]
    yr = holder.get("year") or 2
    adm = holder.get("admission_year") or 2025
    purpose = data.get("purpose", "")
    org = (data.get("org") or "").strip()
    if en:
        name = translit(f"{holder['full_name']}")
        place = PLACE_EN.get(purpose) or (data.get("purpose_other") or "the requesting organisation")
        txt = (f"This is to certify that <b>{e(name)}</b> is a full-time {ordinal(int(yr))}-year student of the "
               f"{e(sp['level_en'])} programme in <b>{e(sp['name_en'])}</b>, {e(fac['name_en'])}, {e(uni['name_en'])} "
               f"(group {e(holder.get('group') or '—')}, student ID {e(holder.get('student_no') or '—')}).</p>"
               f"<p>Period of study: {adm}–{adm + sp['years']}. Mode of study: full-time. Basis of study: "
               f"{e(FUND_EN.get(holder.get('funding') or '', 'state-funded'))}. Current term: {e(uni['semester_en'])} ({e(uni['semester_dates'])}).</p>"
               f"<p>This certificate is issued at the student's request for submission to {e(place)}{(' — ' + e(org)) if org else ''}.")
        return txt
    full = f"{holder['full_name']} {holder.get('patronymic') or ''}".strip()
    place = PLACE_AZ.get(purpose) or "tələb olunan yerə"
    extra = {
        "Hərbi komissarlıq": f"Tələbə əyani təhsil alır; təhsilin normativ müddəti {adm}–{adm + sp['years']}-cü illərdir.",
        "Dövlət Sosial Müdafiə Fondu (DSMF)": "Tələbə əyani təhsil formasında təhsil alır.",
        "Bank": f"Təhsilin əsası: {e((holder.get('funding') or 'Dövlət sifarişi').lower())}.",
        "Səfirlik / viza": f"Cari semestr: {e(uni['semester_dates'])}. Tələbə təhsilini davam etdirir.",
        "İş yeri": "Dərslər həftə içi, əyani formada keçirilir.",
    }.get(purpose, "")
    other = f" Təyinatı: {e(data.get('purpose_other'))}." if purpose == "Digər" and data.get("purpose_other") else ""
    return (f"Verilir ona ki, <b>{e(full)}</b> həqiqətən {e(uni['name'])}nin {e(fac['name'])}nin <b>“{e(sp['name'])}”</b> ixtisası üzrə "
            f"<b>{az_ordinal(int(yr))} kurs</b> tələbəsidir (qrup: {e(holder.get('group') or '—')}, tələbə bileti № {e(holder.get('student_no') or '—')}).</p>"
            f"<p>Təhsil forması: əyani; təhsil pilləsi: {e(sp['level'].lower())}; qəbul ili: {adm}. {extra}</p>"
            f"<p>Arayış {e(place)} təqdim edilmək üçün verilir.{other}{(' Qurum: ' + e(org) + '.') if org else ''}")


def transcript_body(holder, data, ctx, rows_, en):
    sp = ctx["specialty"]
    scope = rows_[-1:] if data.get("scope") == "Son semestr" else rows_
    name = translit(holder["full_name"]) if en else f"{holder['full_name']} {holder.get('patronymic') or ''}".strip()
    head = (f"Student: <b>{e(name)}</b> · {e(sp['name_en'])} · group {e(holder.get('group') or '—')} · ID {e(holder.get('student_no') or '—')}" if en
            else f"Tələbə: <b>{e(name)}</b> · “{e(sp['name'])}” ixtisası · qrup {e(holder.get('group') or '—')} · tələbə bileti № {e(holder.get('student_no') or '—')}")
    out = [f"<p class='noindent'>{head}</p>"]
    tot_cr = tot_w = all_cr = 0
    for s in scope:
        out.append(f"<h3 class='sem'>{e(s['name_en'] if en else s['name'])}</h3><table class='grades'><tr><th>{'Course' if en else 'Fənn'}</th>"
                   f"<th>{'Credits (ECTS)' if en else 'Kredit (AKTS)'}</th><th>{'Score' if en else 'Bal'}</th><th>{'Grade' if en else 'Qiymət'}</th></tr>")
        for r in s["courses"]:
            out.append(f"<tr><td>{e(r['name_en'] if en else r['name'])}</td><td>{r['credits']}</td><td>{r['score']}</td><td>{r['letter']}</td></tr>")
            all_cr += r["credits"]
            tot_w += r["credits"] * r["score"]
            tot_cr += r["credits"] if r.get("passed", True) else 0      # Task 21: only a passed course earns its credits
        out.append("</table>")
    avg = tot_w / all_cr if all_cr else 0
    out.append(f"<p class='noindent'><b>{'Total credits' if en else 'Cəmi kredit'}:</b> {tot_cr} · <b>{'Weighted average score' if en else 'Orta çəkili bal'}:</b> "
               f"{avg:.1f}{'' if en else ''}</p>")
    out.append(f"<p class='muted noindent'>{e(scale_text(ctx.get('grading') or tenant.DEFAULTS['grading'], en))}</p>")
    return "".join(out)


def scale_text(grading: dict, en: bool) -> str:
    """The printed scale (each letter from its lower edge to the next one, F below the pass mark), from the setting."""
    sc, parts = grading["scale"], []
    for i, (mark, low) in enumerate(sc):
        high = 100 if i == 0 else sc[i - 1][1] - 1
        parts.append(f"{mark} {low:g}–{high:g}")
    tail = f"F below {grading['pass_mark']:g}" if en else f"F: {grading['pass_mark']:g} baldan aşağı"
    return ("Grading scale: " if en else "Qiymət şkalası: ") + ", ".join(parts) + f", {tail}."


def leave_body(holder, data, ctx, doc):
    sp = ctx["specialty"]
    full = f"{holder['full_name']} {holder.get('patronymic') or ''}".strip()
    # Task 15: the order's own number and date, not the day the extract was printed (a preview has no order yet)
    order = (f"{dmy(data['order_date'])} tarixli {e(data['order_no'])} nömrəli" if data.get("order_no") and data.get("order_date")
             else "… tarixli … nömrəli")
    return (f"Rektorun {order} əmrindən çıxarış:</p>"
            f"<p>“{e(sp['name'])}” ixtisası üzrə {az_ordinal(int(holder.get('year') or 2))} kurs tələbəsi (qrup {e(holder.get('group') or '—')}) "
            f"<b>{e(full)}</b> {e((data.get('reason') or '').lower())} səbəbindən {e(data.get('start') or '')}ndən başlayaraq "
            f"{e(data.get('period') or '')} müddətinə akademik məzuniyyətə buraxılsın.</p>"
            f"<p>Akademik məzuniyyət müddətində tələbənin statusu saxlanılır; təhsilin bərpası üçün müddət bitməzdən əvvəl dekanlığa müraciət edilməlidir.")


KIND_AZ = {"main": "əsas", "retake": "təkrar", "individual": "fərdi vaxt"}
RESULT_AZ = {"passed": "keçdi", "exam_min": "imtahan balı minimumdan aşağı", "pass_mark": "cəm keçid balından aşağı",
             "not_admitted": "buraxılmayıb", "absent": "gəlməyib"}
INCIDENT_AZ = {"client.blur": "pəncərədən çıxma", "client.fullscreen_exit": "tam ekrandan çıxma", "client.reconnect": "yenidən qoşulma",
               "net.changed": "ünvan dəyişməsi", "net.refused": "kənar ünvandan sorğu", "login.during_exam": "imtahan zamanı başqa giriş",
               "session.refused": "rədd edilmiş giriş", "session.takeover": "başqa kompüterdən davam", "seb.refused": "SEB yoxlamasından keçməyən sorğu"}
ACTION_AZ = {"proctor.extend": "vaxt əlavəsi", "proctor.pause": "dayandırma", "proctor.resume": "davam etdirmə", "proctor.end": "cəhdin bitirilməsi",
             "proctor.reopen": "cəhdin yenidən açılması", "proctor.unlock": "giriş kilidinin açılması"}


def _root_line(data) -> str:
    return (f'<p class="small">Hadisə zəncirinin kökü (№ {e(str(data.get("seq")))} hadisə):<br><code style="word-break:break-all">'
            f'{e(data.get("root") or "")}</code></p>')


def exam_protocol_body(data) -> str:
    """The closing protocol of an exam (Task 30): facts, counts, incidents, the proctors' actions and the chain's root."""
    r, a = data.get("roster") or {}, data.get("attempts") or {}
    window = f'{dmy(data.get("opens_at") or "", True)} – {dmy(data.get("closes_at") or "", True)}'
    facts = [("Fənn", data.get("course")), ("İmtahan", f'{data.get("title")} · {KIND_AZ.get(data.get("kind"), data.get("kind"))} · {data.get("attempt_no")}-ci cəhd'),
             ("Pəncərə (UTC)", window), ("Müddət", f'{data.get("duration_min")} dəq.'),
             ("Siyahı", f'buraxılıb {r.get("eligible", 0)} · istisna {r.get("exception", 0)} · buraxılmayıb {r.get("excluded", 0)}'),
             ("Cəhdlər", f'başlayıb {a.get("started", 0)} · avtomatik təslim {a.get("auto", 0)} · gəlməyib {a.get("absent", 0)}')]
    inc = ", ".join(f"{INCIDENT_AZ.get(k, k)}: {n}" for k, n in (data.get("incidents") or {}).items()) or "yoxdur"
    act = ", ".join(f"{ACTION_AZ.get(k, k)}: {n}" for k, n in (data.get("actions") or {}).items()) or "yoxdur"
    rows_ = "".join(f"<tr><th>{e(k)}</th><td>{e(str(v))}</td></tr>" for k, v in facts + [("Hadisələr", inc), ("Nəzarətçi əməliyyatları", act)])
    return f'<table class="grades">{rows_}</table>{_root_line(data)}'


def exam_statement_body(data) -> str:
    """A group's exam-and-grade statement (Task 30), closed by the dean's office."""
    num = lambda v: "—" if v is None else f"{v:g}"  # noqa: E731
    body = "".join(f'<tr><td>{i}</td><td>{e(x.get("full_name") or "")}</td><td style="white-space:nowrap">{e(x.get("student_no") or "")}</td><td>{num(x.get("semester"))}</td>'
                   f'<td>{num(x.get("points"))}</td><td>{num(x.get("total"))}</td><td>{e(x.get("letter") or "—")}</td>'
                   f'<td>{e(RESULT_AZ.get(x.get("status"), x.get("status") or ""))}</td></tr>' for i, x in enumerate(data.get("rows") or [], 1))
    head = (f'<p>Fənn: <b>{e(data.get("course") or "")}</b> · Qrup: <b>{e(data.get("group_name") or "")}</b> · '
            f'{e(data.get("title") or "")} ({e(str(data.get("attempt_no")))}-ci cəhd)</p>')
    return (head + '<table class="grades"><thead><tr><th>№</th><th>Tələbə</th><th>Bilet №</th><th>Semestr</th><th>İmtahan</th>'
            f'<th>Cəm</th><th>Qiymət</th><th>Nəticə</th></tr></thead><tbody>{body}</tbody></table>{_root_line(data)}')


def render_document(doc: dict, holder: dict, issuer: dict, ctx: dict, transcript=None, lang: str = "az") -> str:
    data = json.loads(doc["data"] or "{}")
    uni, base = ctx["university"], ctx["base_url"]
    verify_url = f"{base}/verify/{doc['verify_code']}"
    qr = qr_svg(verify_url, scale=3)
    en = data.get("lang") == "İngilis dili"
    if doc["kind"] == "certificate":
        full = f"{holder['full_name']} {holder.get('patronymic') or ''}".strip()
        body = f"""
<div class="cert">
  <img class="cert-logo" src="/static/img/brand/logo-dark.png" alt="{e(uni['short'])}">
  <div class="cert-org">{e(uni['name'])} · {e(uni['platform'])} AI Akademiya</div>
  <h1>SERTİFİKAT</h1>
  <p class="cert-lead">Bu sertifikat təsdiq edir ki,</p>
  <div class="cert-name">{e(full)}</div>
  <p class="cert-lead">“{e(data.get('program', 'Təhsildə süni intellekt'))}” peşəkar inkişaf proqramını ({e(str(data.get('modules', '')))} modul,
  {e(str(data.get('hours', '')))} saat) uğurla başa vurmuşdur.</p>
  <div class="cert-foot">
    <div><b>Reyestr №</b> {e(doc['reg_no'])}<br><b>Tarix:</b> {dmy(doc['issued_at'])}<br><span class="muted">DEMO — hüquqi qüvvəsi yoxdur</span></div>
    <div class="qr">{qr}<small>{e(doc['verify_code'])}</small></div>
  </div>
</div>"""
    else:
        t = data.get("type")
        if t == "enrollment_certificate":
            content, title = enrollment_body(holder, data, ctx, en), ("CERTIFICATE OF ENROLMENT" if en else doc["title"])
        elif t == "transcript":
            content, title = transcript_body(holder, data, ctx, transcript or [], en), ("ACADEMIC TRANSCRIPT" if en else doc["title"])
        elif t == "academic_leave":
            content, title, en = leave_body(holder, data, ctx, doc), doc["title"], False
        elif t == "exam_protocol":
            content, title, en = exam_protocol_body(data), doc["title"], False
        elif t == "exam_statement":
            content, title, en = exam_statement_body(data), doc["title"], False
        else:
            content, title = e(json.dumps(data, ensure_ascii=False)), doc["title"]
        copies = data.get("copies")
        body = f"""
<div class="paper">
  <div class="watermark">DEMO</div>
  {_head(uni, 'Tədris hissəsi', "Registrar's Office", en)}
  <div class="doc-meta"><span>№ {e(doc['reg_no'])}</span><span>{e(uni.get('city_en' if en else 'city') or '')}, {dmy(doc['issued_at'])}</span></div>
  <h1>{e(title)}</h1>
  <div class="doc-body"><p>{content}</p></div>
  {f'<p class="copies">{"Copies" if en else "Nüsxə sayı"}: {e(copies)}</p>' if copies and copies != "1" else ''}
  {_sign(doc, issuer, qr, en)}
  {_foot(doc, verify_url, uni['platform'], en)}
</div>"""
    toolbar = (f'<div class="toolbar no-print"><button id="print-btn">🖨 {e(S("Çap et / PDF kimi saxla", lang))}</button>'
               f'<a href="/verify/{e(doc["verify_code"])}" target="_blank" rel="noopener">{e(S("Doğrulama səhifəsi", lang))} ↗</a></div>')
    status = ""
    if doc["status"] == "revoked":
        status = (f'<div class="revoked no-print">⚠ '
                  f'{e(S("Bu sənəd {date} tarixində ləğv edilib: {reason}", lang, date=dmy(doc["revoked_at"]), reason=doc["revoked_reason"] or ""))}</div>')
    return _page(f"{doc['title']} · {doc['reg_no']}", toolbar + status + body)


def _initials(name: str) -> str:
    return " ".join(p[0] + "." for p in name.split()[:2] if p)


def unverified_card(doc: dict, lang: str, state: str) -> str:
    """A document whose stored content is missing ('none', issued before Task 45) or no longer matches its hash ('changed')."""
    s = lambda text, **k: S(text, lang, **k)  # noqa: E731
    if state == "changed":
        head = (f'<div class="v-icon">!</div><h1>{e(s("Sənəd dəyişdirilib"))}</h1>'
                f'<p>{e(s("Reyestrdəki məzmun sənəd veriləndə saxlanmış məzmunla uyğun gəlmir. Bu sənədə etibar etməyin və universitetlə əlaqə saxlayın."))}</p>')
    else:
        head = (f'<div class="v-icon">?</div><h1>{e(s("Bu sənəd doğrulanmır"))}</h1>'
                f'<p>{e(s("Sənəd verilmə anındakı məzmunu saxlanmadan əvvəl verilib. Həqiqiliyini universitetdən soruşun."))}</p>')
    return f'<div class="v-card bad">{head}<table><tr><th>{e(s("Reyestr nömrəsi"))}</th><td>{e(doc["reg_no"])}</td></tr></table></div>'


def render_unverified(doc: dict, ctx: dict, lang: str, state: str) -> str:
    """/doc of a document that cannot be shown from its stored content: it is never rebuilt from live rows."""
    uni = ctx["university"]
    body = f'<div class="verify"><div class="v-brand"><b>{e(uni["name"])}</b></div>{unverified_card(doc, lang, state)}</div>'
    return _page(f"{doc['title']} · {doc['reg_no']}", body)


def _chain_row(doc: dict, s) -> list[tuple[str, str]]:
    """An exam document (Task 30) shows the full root of the exam's event chain it printed, to compare with the e-mail."""
    try:
        data = json.loads(doc.get("data") or "{}")
    except (TypeError, ValueError):
        return []
    if doc.get("kind") not in ("exam_protocol", "exam_statement") or not data.get("root"):
        return []
    return [(e(s("Zəncirin kökü")), f'<code style="word-break:break-all">{e(data["root"])}</code>')]


def render_verify(doc: dict | None, holder: dict | None, ctx: dict, lang: str = "az", state: str = "ok") -> str:
    uni = ctx["university"]
    s = lambda text, **k: S(text, lang, **k)  # noqa: E731
    if not doc:
        card = (f'<div class="v-card bad"><div class="v-icon">?</div><h1>{e(s("Sənəd tapılmadı"))}</h1>'
                f'<p>{e(s("Bu doğrulama koduna uyğun sənəd reyestrdə yoxdur. Kodu yenidən yoxlayın."))}</p></div>')
    elif state != "ok":
        card = unverified_card(doc, lang, state)
    else:
        ok = doc["status"] == "valid"
        issuer_unit = s("AI Akademiya") if doc["kind"] == "certificate" else s("Tədris hissəsi")
        rows_html = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in [
            (e(s("Sənəd")), e(doc["title"])), (e(s("Reyestr nömrəsi")), e(doc["reg_no"])), (e(s("Verilmə tarixi")), dmy(doc["issued_at"])),
            (e(s("Sənəd sahibi")), e(_initials(holder["full_name"])) if holder else "—"),
            (e(s("Verən qurum")), f"{e(uni['short'])} — {e(issuer_unit)}"),
            (e(s("Məzmun bütövlüyü")), f"SHA-256 ✓ <code>{e(doc['hash'][:12])}</code>"),
        ] + _chain_row(doc, s))
        head = (f'<div class="v-icon">✓</div><h1>{e(s("Sənəd etibarlıdır"))}</h1><p>{e(s("Sənəd universitetin rəsmi reyestrində qeydiyyatdadır."))}</p>' if ok else
                f'<div class="v-icon">✕</div><h1>{e(s("Sənəd ləğv edilib"))}</h1>'
                f'<p>{e(s("{date} tarixində ləğv edilib. Səbəb: {reason}", date=dmy(doc["revoked_at"]), reason=doc["revoked_reason"] or "—"))}</p>')
        card = f'<div class="v-card {"good" if ok else "bad"}">{head}<table>{rows_html}</table></div>'
    body = f"""<div class="verify"><div class="v-brand"><img src="/static/img/brand/icon.png" alt="{e(uni['short'])}" class="v-logo">
<div><b>{e(uni['name'])}</b><br><span>{e(s("Sənədlərin onlayn doğrulanması"))}</span></div></div>
{card}<p class="v-note">{e(s("Şəxsi məlumatların qorunması məqsədilə yalnız minimal məlumat göstərilir. DEMO versiya."))}</p></div>"""
    return _page(s("Sənəd doğrulama · {x}", x=uni["short"]), body)
