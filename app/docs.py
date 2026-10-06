"""Printable documents and the public verification page (server-rendered, AzTU branded)."""
from __future__ import annotations

import html
import json
from datetime import datetime

from .engine import translit
from .i18n import S
from .qr import qr_svg

e = html.escape

PLACE_AZ = {"Hərbi komissarlıq": "hərbi komissarlığa", "Dövlət Sosial Müdafiə Fondu (DSMF)": "Dövlət Sosial Müdafiə Fonduna",
            "Bank": "banka", "Səfirlik / viza": "səfirliyə (viza məqsədilə)", "İş yeri": "iş yerinə",
            "ASAN xidmət / dövlət qurumu": "aidiyyəti dövlət qurumuna"}
PLACE_EN = {"Hərbi komissarlıq": "the military commissariat", "Dövlət Sosial Müdafiə Fondu (DSMF)": "the State Social Protection Fund",
            "Bank": "the bank", "Səfirlik / viza": "the embassy for visa purposes", "İş yeri": "the employer",
            "ASAN xidmət / dövlət qurumu": "the relevant state authority"}
FUND_EN = {"Dövlət sifarişi": "state-funded", "Ödənişli": "tuition-paying"}


def dmy(iso_ts: str, with_time: bool = False) -> str:
    dt = datetime.fromisoformat(iso_ts)
    return dt.strftime("%d.%m.%Y %H:%M" if with_time else "%d.%m.%Y")


def _page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="az"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title>
<link rel="icon" href="/static/img/brand/icon.png"><link rel="stylesheet" href="/static/css/doc.css"></head><body>{body}
<script src="/static/js/print.js"></script></body></html>"""


def _head(uni, unit_az, unit_en, en):
    return f"""<header class="doc-head"><img class="crest" src="/static/img/brand/icon.png" alt="AzTU">
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
        txt = (f"This is to certify that <b>{e(name)}</b> is a full-time {yr}{'nd' if yr == 2 else 'th'}-year student of the "
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
            f"<b>{yr}-ci kurs</b> tələbəsidir (qrup: {e(holder.get('group') or '—')}, tələbə bileti № {e(holder.get('student_no') or '—')}).</p>"
            f"<p>Təhsil forması: əyani; təhsil pilləsi: {e(sp['level'].lower())}; qəbul ili: {adm}. {extra}</p>"
            f"<p>Arayış {e(place)} təqdim edilmək üçün verilir.{other}{(' Qurum: ' + e(org) + '.') if org else ''}")


def transcript_body(holder, data, ctx, rows_, en):
    sp = ctx["specialty"]
    scope = rows_[-1:] if data.get("scope") == "Son semestr" else rows_
    name = translit(holder["full_name"]) if en else f"{holder['full_name']} {holder.get('patronymic') or ''}".strip()
    head = (f"Student: <b>{e(name)}</b> · {e(sp['name_en'])} · group {e(holder.get('group') or '—')} · ID {e(holder.get('student_no') or '—')}" if en
            else f"Tələbə: <b>{e(name)}</b> · “{e(sp['name'])}” ixtisası · qrup {e(holder.get('group') or '—')} · tələbə bileti № {e(holder.get('student_no') or '—')}")
    out = [f"<p class='noindent'>{head}</p>"]
    tot_cr = tot_w = 0
    for s in scope:
        out.append(f"<h3 class='sem'>{e(s['name_en'] if en else s['name'])}</h3><table class='grades'><tr><th>{'Course' if en else 'Fənn'}</th>"
                   f"<th>{'Credits (ECTS)' if en else 'Kredit (AKTS)'}</th><th>{'Score' if en else 'Bal'}</th><th>{'Grade' if en else 'Qiymət'}</th></tr>")
        for r in s["courses"]:
            out.append(f"<tr><td>{e(r['name_en'] if en else r['name'])}</td><td>{r['credits']}</td><td>{r['score']}</td><td>{r['letter']}</td></tr>")
            tot_cr += r["credits"]
            tot_w += r["credits"] * r["score"]
        out.append("</table>")
    avg = tot_w / tot_cr if tot_cr else 0
    out.append(f"<p class='noindent'><b>{'Total credits' if en else 'Cəmi kredit'}:</b> {tot_cr} · <b>{'Weighted average score' if en else 'Orta çəkili bal'}:</b> "
               f"{avg:.1f}{'' if en else ''}</p>")
    out.append(f"<p class='muted noindent'>{'Grading scale: A 91–100, B 81–90, C 71–80, D 61–70, E 51–60, F below 51. Scores are synthetic (demo).' if en else 'Qiymət şkalası: A 91–100, B 81–90, C 71–80, D 61–70, E 51–60, F 51-dən aşağı. Ballar sintetikdir (demo).'}</p>")
    return "".join(out)


def leave_body(holder, data, ctx, doc):
    sp = ctx["specialty"]
    full = f"{holder['full_name']} {holder.get('patronymic') or ''}".strip()
    return (f"Rektorun {dmy(doc['issued_at'])} tarixli əmrindən çıxarış:</p>"
            f"<p>“{e(sp['name'])}” ixtisası üzrə {holder.get('year') or 2}-ci kurs tələbəsi (qrup {e(holder.get('group') or '—')}) "
            f"<b>{e(full)}</b> {e((data.get('reason') or '').lower())} səbəbindən {e(data.get('start') or '')}ndən başlayaraq "
            f"{e(data.get('period') or '')} müddətinə akademik məzuniyyətə buraxılsın.</p>"
            f"<p>Akademik məzuniyyət müddətində tələbənin statusu saxlanılır; təhsilin bərpası üçün müddət bitməzdən əvvəl dekanlığa müraciət edilməlidir.")


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
  <img class="cert-logo" src="/static/img/brand/logo-dark.png" alt="AzTU">
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
        else:
            content, title = e(json.dumps(data, ensure_ascii=False)), doc["title"]
        copies = data.get("copies")
        body = f"""
<div class="paper">
  <div class="watermark">DEMO</div>
  {_head(uni, 'Tədris hissəsi', "Registrar's Office", en)}
  <div class="doc-meta"><span>№ {e(doc['reg_no'])}</span><span>{'Baku' if en else 'Bakı'}, {dmy(doc['issued_at'])}</span></div>
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


def render_verify(doc: dict | None, holder: dict | None, ctx: dict, lang: str = "az") -> str:
    uni = ctx["university"]
    s = lambda text, **k: S(text, lang, **k)  # noqa: E731
    if not doc:
        card = (f'<div class="v-card bad"><div class="v-icon">?</div><h1>{e(s("Sənəd tapılmadı"))}</h1>'
                f'<p>{e(s("Bu doğrulama koduna uyğun sənəd reyestrdə yoxdur. Kodu yenidən yoxlayın."))}</p></div>')
    else:
        ok = doc["status"] == "valid"
        issuer_unit = s("AI Akademiya") if doc["kind"] == "certificate" else s("Tədris hissəsi")
        rows_html = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in [
            (e(s("Sənəd")), e(doc["title"])), (e(s("Reyestr nömrəsi")), e(doc["reg_no"])), (e(s("Verilmə tarixi")), dmy(doc["issued_at"])),
            (e(s("Sənəd sahibi")), e(_initials(holder["full_name"])) if holder else "—"),
            (e(s("Verən qurum")), f"{e(uni['short'])} — {e(issuer_unit)}"),
            (e(s("Məzmun bütövlüyü")), f"SHA-256 ✓ <code>{e(doc['hash'][:12])}</code>"),
        ])
        head = (f'<div class="v-icon">✓</div><h1>{e(s("Sənəd etibarlıdır"))}</h1><p>{e(s("Sənəd universitetin rəsmi reyestrində qeydiyyatdadır."))}</p>' if ok else
                f'<div class="v-icon">✕</div><h1>{e(s("Sənəd ləğv edilib"))}</h1>'
                f'<p>{e(s("{date} tarixində ləğv edilib. Səbəb: {reason}", date=dmy(doc["revoked_at"]), reason=doc["revoked_reason"] or "—"))}</p>')
        card = f'<div class="v-card {"good" if ok else "bad"}">{head}<table>{rows_html}</table></div>'
    body = f"""<div class="verify"><div class="v-brand"><img src="/static/img/brand/icon.png" alt="AzTU" class="v-logo">
<div><b>{e(uni['name'])}</b><br><span>{e(s("Sənədlərin onlayn doğrulanması"))}</span></div></div>
{card}<p class="v-note">{e(s("Şəxsi məlumatların qorunması məqsədilə yalnız minimal məlumat göstərilir. DEMO versiya."))}</p></div>"""
    return _page(s("Sənəd doğrulama · AzTU"), body)
