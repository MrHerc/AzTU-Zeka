"""docs.py — printable certificates/transcripts and the public verification page."""
import json
import re

import pytest

from app import docs

CTX = {"university": {"name": "Azərbaycan Texniki Universiteti", "name_en": "Azerbaijan Technical University", "short": "AzTU", "platform": "Zəka",
                      "semester": "Payız", "semester_en": "Autumn 2026", "semester_dates": "15.09–31.12", "address": "Bakı, H. Cavid 25", "site": "aztu.edu.az"},
       "faculty": {"name": "İnformasiya texnologiyaları fakültəsi", "name_en": "Faculty of IT"},
       "specialty": {"name": "Kompüter mühəndisliyi", "name_en": "Computer Engineering", "level": "Bakalavriat", "level_en": "Bachelor's degree", "years": 4},
       "base_url": "https://zeka.example.az"}
HOLDER = {"full_name": "Aysel Məmmədova", "patronymic": "Elçin qızı", "year": 2, "admission_year": 2025, "group": "İT-25-1",
          "student_no": "25-110001", "funding": "Dövlət sifarişi"}
ISSUER = {"full_name": "Nigar Həsənova"}


def doc(data, kind="request", status="valid", **kw):
    return {"kind": kind, "title": kw.get("title", "Arayış"), "reg_no": "AzTU-ARY-2026-000007", "verify_code": "K7QM-2HXP",
            "data": json.dumps(data, ensure_ascii=False), "hash": "ab" * 32, "issued_at": "2026-10-02T11:30:00", "status": status,
            "revoked_reason": kw.get("reason"), "revoked_at": kw.get("revoked_at")}


@pytest.mark.parametrize("n, s", [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (11, "11th"), (12, "12th"), (13, "13th"), (21, "21st"), (22, "22nd"), (101, "101st"), (111, "111th")])
def test_english_ordinal(n, s):
    assert docs.ordinal(n) == s


@pytest.mark.parametrize("n, s", [(1, "1-ci"), (2, "2-ci"), (3, "3-cü"), (4, "4-cü"), (5, "5-ci"), (6, "6-cı"), (7, "7-ci"), (8, "8-ci"), (9, "9-cu"),
                                  (10, "10-cu"), (20, "20-ci"), (30, "30-cu"), (40, "40-cı"), (90, "90-cı"), (100, "100-cü"), (1000, "1000-ci"), (23, "23-cü")])
def test_azerbaijani_ordinal(n, s):
    assert docs.az_ordinal(n) == s


@pytest.mark.parametrize("year, az, en", [(1, "1-ci kurs", "1st-year"), (2, "2-ci kurs", "2nd-year"), (3, "3-cü kurs", "3rd-year"), (4, "4-cü kurs", "4th-year")])
def test_enrollment_certificate_year_wording(year, az, en):
    # regression: every year was written "-ci kurs" / "-th-year" except 2 ("3-ci kurs", "3th-year")
    h = {**HOLDER, "year": year}
    assert az in docs.enrollment_body(h, {"purpose": "Bank"}, CTX, False)
    assert f"full-time {en} student" in docs.enrollment_body(h, {"purpose": "Bank"}, CTX, True)


def test_enrollment_body_azerbaijani_by_purpose():
    txt = docs.enrollment_body(HOLDER, {"purpose": "Hərbi komissarlıq", "org": "Yasamal RHK"}, CTX, False)
    assert "Aysel Məmmədova Elçin qızı" in txt and "hərbi komissarlığa" in txt and "2025–2029" in txt and "Qurum: Yasamal RHK." in txt
    other = docs.enrollment_body(HOLDER, {"purpose": "Digər", "purpose_other": "kredit üçün"}, CTX, False)
    assert "tələb olunan yerə" in other and "Təyinatı: kredit üçün." in other


def test_enrollment_body_english_is_transliterated():
    txt = docs.enrollment_body(HOLDER, {"purpose": "Səfirlik / viza"}, CTX, True)
    assert "Aysel Mammadova" in txt and "the embassy for visa purposes" in txt and "state-funded" in txt and "ə" not in txt.split("Mammadova")[0]


def test_user_values_are_escaped():
    h = {**HOLDER, "full_name": "<script>x</script>", "group": "<b>"}
    txt = docs.enrollment_body(h, {"purpose": "Digər", "purpose_other": "<img>", "org": "<i>"}, CTX, False)
    assert "<script>" not in txt and "<img>" not in txt and "&lt;b&gt;" in txt and "&lt;i&gt;" in txt


ROWS = [{"name": "I semestr", "name_en": "Semester 1", "courses": [{"name": "Fizika", "name_en": "Physics", "credits": 5, "score": 90, "letter": "B"}]},
        {"name": "II semestr", "name_en": "Semester 2", "courses": [{"name": "Riyaziyyat", "name_en": "Maths", "credits": 5, "score": 80, "letter": "C"}]}]


def test_transcript_body_scope_and_weighted_average():
    full = docs.transcript_body(HOLDER, {"scope": "Bütün semestrlər"}, CTX, ROWS, False)
    assert "I semestr" in full and "II semestr" in full and "Cəmi kredit:</b> 10" in full and "85.0" in full
    last = docs.transcript_body(HOLDER, {"scope": "Son semestr"}, CTX, ROWS, True)
    assert "Semester 1" not in last and "Semester 2" in last and "80.0" in last and "Mammadova" in last
    assert "0.0" in docs.transcript_body(HOLDER, {}, CTX, [], False)


@pytest.mark.parametrize("data, title", [
    ({"type": "enrollment_certificate", "lang": "Azərbaycan dili", "purpose": "Bank", "copies": "2"}, "Arayış"),
    ({"type": "enrollment_certificate", "lang": "İngilis dili", "purpose": "Bank"}, "CERTIFICATE OF ENROLMENT"),
    ({"type": "transcript", "lang": "İngilis dili", "scope": "Bütün semestrlər"}, "ACADEMIC TRANSCRIPT"),
    ({"type": "academic_leave", "reason": "Səhhət", "period": "1 semestr", "start": "2026/2027 payız semestri"}, "Arayış"),
    ({"type": "free_application", "x": "<y>"}, "Arayış"),
])
def test_render_document_variants(data, title):
    page = docs.render_document(doc(data), HOLDER, ISSUER, CTX, ROWS)
    assert page.startswith("<!doctype html>") and f"<h1>{title}</h1>" in page
    assert "https://zeka.example.az/verify/K7QM-2HXP" in page and "<svg" in page and "AzTU-ARY-2026-000007" in page
    assert "Nigar Həsənova" in page and "02.10.2026" in page
    assert "<y>" not in page
    assert ("Nüsxə sayı: 2" in page) == (data.get("copies") == "2")


def test_render_certificate():
    page = docs.render_document(doc({"program": "Təhsildə süni intellekt", "modules": 6, "hours": "7,5"}, kind="certificate"), HOLDER, ISSUER, CTX)
    assert "SERTİFİKAT" in page and "Aysel Məmmədova Elçin qızı" in page and "6 modul" in page and "7,5 saat" in page


def test_render_document_revoked_banner_and_translated_toolbar():
    d = doc({"type": "transcript"}, status="revoked", reason="Səhv məlumat", revoked_at="2026-10-05T10:00:00")
    page = docs.render_document(d, HOLDER, ISSUER, CTX, ROWS, lang="en")
    assert "05.10.2026" in page and "Səhv məlumat" in page and 'class="revoked' in page
    assert "Print / save as PDF" in page


def test_verify_page_valid_shows_only_minimal_data():
    page = docs.render_verify(doc({"type": "transcript"}), HOLDER, CTX)
    assert "Sənəd etibarlıdır" in page and "A. M." in page and "Məmmədova" not in page      # privacy: initials only
    assert "AzTU-ARY-2026-000007" in page and "abababababab" in page


def test_verify_page_revoked_missing_and_english():
    revoked = docs.render_verify(doc({}, status="revoked", reason="Səbəb <x>", revoked_at="2026-10-05T10:00:00"), HOLDER, CTX)
    assert "Sənəd ləğv edilib" in revoked and "05.10.2026" in revoked and "&lt;x&gt;" in revoked
    assert "Sənəd tapılmadı" in docs.render_verify(None, None, CTX)
    assert "valid" in docs.render_verify(doc({}), HOLDER, CTX, "en").lower()


def test_dmy():
    assert docs.dmy("2026-01-02T03:04:05") == "02.01.2026" and docs.dmy("2026-01-02T03:04:05", True) == "02.01.2026 03:04"
    assert docs._initials("Aysel Məmmədova Elçin") == "A. M." and re.fullmatch(r"", docs._initials(""))
