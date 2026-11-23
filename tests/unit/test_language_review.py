"""The Checkpoint F language review (L1-L20): a key shared by two senses is split, a value read from a file is shown as
written, a count has its plural forms, numbers and dates follow the reader's language, and the style guide's forms hold."""
import json
import re
from pathlib import Path

from zeka.core import i18n
from zeka.legacy import r_radar
from zeka.modules.integration import forma3, importer
from zeka.modules.timetable import builder

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "frontend" / "js"
UI = {lg: json.loads((ROOT / "frontend" / "locales" / f"{lg}.json").read_text(encoding="utf-8")) for lg in ("en", "ru")}
SERVER = {lg: json.loads((ROOT / "backend" / "zeka" / "core" / "locales" / f"{lg}.json").read_text(encoding="utf-8")) for lg in ("en", "ru")}


def uses(js: str, key: str) -> bool:
    return f't("{key}"' in (JS / js).read_text(encoding="utf-8")


# (file, key it must use there, en, ru) — the screens the review read wrongly
SPLIT = [
    ("admin-import.js", "Məsləhətlər", "Consultations", "Консультации"),                  # L1: not «Tip / Совет»
    ("teacher.js", "Məsləhət", "Tip", "Совет"),
    ("news.js", "Hədəf auditoriya", "Audience", "Аудитория"),                             # L3: not «Classroom»
    ("admin-import.js", "Fənlərə yazılış", "Enrolments", "Записи на дисциплины"),          # L4
    ("news.js", "Qeydiyyatdan keç", "Register", "Зарегистрироваться"),
    ("news.js", "Qeydiyyatlar", "Registrations", "Регистрации"),
    ("services.js", "Aktiv olanlar", "Active", "Активные"),                               # L10: the filter is plural
    ("services.js", "Açıq olanlar", "Open", "Открытые"),
    ("admin-import.js", "Dəyişən sahələr", "Changed fields", "Изменённые поля"),           # L11
    ("admin-import.js", "Yoxlama qaydası", "Check", "Проверка"),
    ("services.js", "Yeni müraciətlər", "New requests", "Новые заявки"),                   # L16: a count's label
    ("admin-import.js", "Faylı yoxla", "Check file", "Проверить файл"),                   # L20
    ("timetable-prep.js", "Hazırlıq bəndi", "Item", "Пункт"),
    ("teacher.js", "Bağlıdır", "Disabled", "Отключён"),
    ("staff.js", "Cədvəl otaqlarla əlaqələndirildi", "Timetable linked to rooms", "Расписание связано с аудиториями"),   # L17
]


def test_each_sense_has_its_own_key():
    for js, key, en, ru in SPLIT:
        assert uses(js, key), (js, key)
        assert (UI["en"].get(key), UI["ru"].get(key)) == (en, ru), key
    assert not uses("news.js", "Auditoriya") and not uses("admin-import.js", "Qeydiyyat") and not uses("admin-import.js", "Sahələr")
    assert "rooms_linked:" in (JS / "staff.js").read_text(encoding="utf-8")


def test_russian_statuses_are_neutral_and_the_news_button_is_a_verb():
    """L10, L20: style.md §6."""
    assert (UI["ru"]["Aktiv"], UI["ru"]["Etibarlıdır"], UI["ru"]["Yeni xəbər"]) == ("Активно", "Действует", "Создать новость")
    assert UI["en"]["Yeni xəbər"] == "Create a news item"         # not "New news item" (the browser pass after Checkpoint F)


def test_levels_and_grade_components_have_their_own_translations():
    """L5: a track level is not a start time; L7: the grade table's headers are in the catalogue."""
    levels = {t["level"] for t in json.loads((ROOT / "content" / "academy.json").read_text(encoding="utf-8"))["tracks"]}
    assert levels == {"Başlanğıc səviyyə", "Orta səviyyə"}
    assert [SERVER["en"][x] for x in sorted(levels)] == ["Beginner", "Intermediate"]
    assert [SERVER["ru"][x] for x in sorted(levels)] == ["Начальный уровень", "Средний уровень"]
    for name in ("Sərbəst iş 1", "Sərbəst iş 2", "Laboratoriya / məşğələ", "Kollokvium 1"):
        assert i18n.localize({"name": name}, "en")["name"] != name, name


def test_a_value_read_from_the_file_is_shown_as_written_and_the_russian_agrees():
    """L2: «Fizika» from a cell stayed «Physics» in the report; L9: «не найден(а)»."""
    assert importer._missing("Fənn", "Fizika")["en"] == "Course not found: Fizika"
    assert importer._missing("Fənn", "Fizika")["ru"] == "Дисциплина не найдена: Fizika"
    assert importer._missing("Müəllim", "müəllim")["ru"] == "Преподаватель не найден: müəllim"
    assert forma3._m("summary_position", x="müəllim")["en"].endswith(": müəllim")


def test_a_count_of_cells_has_plural_forms():
    """L18: «1 cells»."""
    assert forma3._m("summary_list", n=1)["en"].endswith(": 1 cell") and forma3._m("summary_list", n=3)["en"].endswith(": 3 cells")
    assert forma3._m("summary_list", n=5)["ru"].endswith(": 5 ячеек")


def test_a_units_label_is_translated_part_by_part(monkeypatch):
    """L8: «Fizika I: Mexanika · Laboratoriya» has a ': ' of its own, so the composed line was left in Azerbaijani."""
    monkeypatch.setattr(builder.repo, "units_by_id", lambda c, ids: [{"id": 7, "course": "Fizika I: Mexanika", "kind": "lab"}])
    monkeypatch.setattr(builder.repo, "groups_info", lambda c, ids: {})
    monkeypatch.setattr(builder.repo, "user_names", lambda c, ids: {})
    line = builder._labelled(None, [{"code": "manual_rows", "samples": [7]}])[0]
    assert i18n.localize(line, "en")["labels"] == ["Physics I: Mechanics · Laboratory"]
    assert i18n.localize(line, "az")["labels"] == ["Fizika I: Mexanika · Laboratoriya"]


def test_the_leaders_lines_write_numbers_and_dates_in_the_readers_language(monkeypatch):
    """L15: EN read «9,9%» and «23.11.2026» where the rest of the EN page writes 9.9 and 23/11/2026."""
    monkeypatch.setattr(r_radar.radar, "summary", lambda c: {"at": "2026-11-23T06:15:00", "high": 2, "watch": 3, "measured": 1, "improved": 1})
    text = r_radar.leader_insight(None)["text"]
    assert "23/11/2026 06:15" in text["en"] and "23.11.2026 06:15" in text["az"]
    assert i18n.num3(9.9) == {"az": "9,9", "en": "9.9", "ru": "9,9"}
    src = (JS / "student.js").read_text(encoding="utf-8")
    assert "p: num(c.percent)" in src, "the attendance percentage through the language's number format"


BANNED = [
    (re.compile(r"\b\w+(edəndə|olanda|olunanda|bitəndən|açıqlayandan|açılanda|açıqlayanda|olunandan|dəyişəndə|götürəndə|göndərəndə|"
                r"veriləndə|təsdiqlənəndə)\b|\bSaxlananda\b"), "L12: time clauses with -dıqda / -dıqdan sonra"),
    (re.compile(r"\bolmaz\b"), "L13: «mümkün deyil»"),
    (re.compile(r"\b[Gg]ünlük (və|cüt)"), "L13: «gündəlik»"),
    (re.compile(r"pəncərəsi açıq|pəncərənin uzunluğu"), "L13: an exam's time is «keçirilmə vaxtı»"),
    (re.compile(r"(mək|maq)\?$"), "L14: a confirmation asks in the passive («… silinsin?»)"),
    (re.compile(r"məsələn [A-ZƏ]"), "L19: «məsələn,» takes a comma"),
]


def test_the_style_guides_forms_hold_in_the_interface_and_server_texts():
    keys = [k for f in ("ui", "server") for k in json.loads((ROOT / "i18n" / "source" / f"{f}.json").read_text(encoding="utf-8"))]
    bad = [(why, k[:80]) for k in keys for pat, why in BANNED if pat.search(k)]
    assert not bad, bad


def test_azerbaijani_achievements_quote_with_guillemets():
    """L19: style.md §1."""
    def az(v):
        if isinstance(v, dict):
            return [s for k, x in v.items() for s in ([x] if k == "az" and isinstance(x, str) else az(x))]
        return [s for x in v for s in az(x)] if isinstance(v, list) else []
    texts = az(json.loads((ROOT / "content" / "achievements.json").read_text(encoding="utf-8")))
    assert texts and not [s for s in texts if "“" in s or "”" in s]
