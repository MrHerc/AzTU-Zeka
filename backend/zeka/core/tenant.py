"""University (tenant) settings (tasks/todo.md, Task 17): what differs between universities, kept in the ``tenant``
setting instead of the code: the grading scheme, the attendance rules, the journal cut-over date, lesson times,
holidays and the document register prefix. Semester dates are not settings: they are ``academic_terms`` (Task 15).

The defaults are neutral (the national 100-point scale); a university's own values come from its content
(``content/seed.json`` -> ``tenant``) or the admin screen. Every value is checked before it is saved (``problem``).
"""
from __future__ import annotations

import bisect
import json
import math
import re
from datetime import date

from .i18n import E

DEFAULTS: dict = {
    "grading": {"components": [{"name": "Semestr ərzində", "max": 50}],
                "exam": {"name": "İmtahan", "max": 50, "min": 0}, "pass_mark": 51,
                "scale": [["A", 91], ["B", 81], ["C", 71], ["D", 61], ["E", 51]]},
    "attendance": {"limit_percent": 25, "excused_counts_toward_limit": True, "points_rule": []},
    "journal": {"cutover_date": None, "edit_hours": 48},   # a teacher corrects a lesson for 48 h after it ends (Task 20)
    "calendar": {"lesson_times": [], "holidays": []},
    "registry": {"prefix": "DOC"},
}
SECTIONS = tuple(DEFAULTS)
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
PREFIX = re.compile(r"^[0-9A-Za-zƏəİıÖöÜüĞğŞşÇç]{2,12}$")
LETTER = re.compile(r"^[A-Z][+-]?$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load(c) -> dict:
    """The tenant settings of the database ``c`` over the defaults, section by section."""
    r = c.execute("SELECT value FROM settings WHERE key='tenant'").fetchone()
    stored = json.loads(r[0]) if r else {}
    return {k: {**v, **(stored.get(k) or {})} for k, v in DEFAULTS.items()}


# ---------------------------------------------------------------- checks
def _num(v) -> bool:
    try:
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    except OverflowError:                          # an int too large for a float (10**400)
        return False


def _text(v, lo: int = 1, hi: int = 80) -> bool:
    return isinstance(v, str) and lo <= len(v.strip()) <= hi


def _iso(v) -> bool:
    try:                                           # YYYY-MM-DD only: Python 3.11 also parses week dates (2026-W01-1)
        return isinstance(v, str) and bool(DATE.fullmatch(v)) and bool(date.fromisoformat(v))
    except ValueError:
        return False


def problem(section: str, v) -> dict | None:
    """Why a section's new value cannot be saved, or None."""
    if section not in DEFAULTS or not isinstance(v, dict) or set(v) - set(DEFAULTS[section]):
        return E("Ayarın quruluşu düzgün deyil")
    return {"grading": _grading, "attendance": _attendance, "journal": _journal, "calendar": _calendar,
            "registry": _registry}[section]({**DEFAULTS[section], **v})


def _grading(g: dict) -> dict | None:
    comps, exam, scale = g["components"], g["exam"], g["scale"]
    if not isinstance(comps, list) or not 1 <= len(comps) <= 20 or not all(
            isinstance(x, dict) and not set(x) - {"name", "max", "attendance"} and _text(x.get("name")) and _num(x.get("max"))
            and x["max"] > 0 for x in comps):
        return E("Qiymətləndirmə komponentlərinin adı və müsbət maksimal balı olmalıdır")
    if len({x["name"].strip() for x in comps}) != len(comps) or sum(bool(x.get("attendance")) for x in comps) > 1:
        return E("Komponentlərin adları təkrarlanmamalıdır; davamiyyət ən çox bir komponentdir")
    if not (isinstance(exam, dict) and _text(exam.get("name")) and _num(exam.get("max")) and _num(exam.get("min"))
            and 0 <= exam["min"] <= exam["max"]):
        return E("İmtahanın adı, maksimal balı və minimumu (0 ilə maksimum arasında) olmalıdır")
    total = sum(x["max"] for x in comps) + exam["max"]
    if abs(total - 100) > 1e-9:
        return E("Komponentlər və imtahan birlikdə 100 bal etməlidir (indi: {n})", n=round(total, 2))
    if not _num(g["pass_mark"]) or not 1 <= g["pass_mark"] <= 100:
        return E("Keçid balı 1 ilə 100 arasında olmalıdır")
    if not isinstance(scale, list) or not 1 <= len(scale) <= 12 or not all(
            isinstance(x, list) and len(x) == 2 and isinstance(x[0], str) and LETTER.fullmatch(x[0]) and _num(x[1]) for x in scale):
        return E("Hərf şkalası hərf və aşağı həddən ibarət sətirlərdir")
    lows = [x[1] for x in scale]
    if any(not 0 < x <= 100 for x in lows) or lows != sorted(lows, reverse=True) or len(set(lows)) != len(lows) or lows[-1] != g["pass_mark"]:
        return E("Hərf şkalası yuxarıdan aşağı düzülməli və son hədd keçid balı olmalıdır")
    return None


def _attendance(a: dict) -> dict | None:
    if not _num(a["limit_percent"]) or not 0 < a["limit_percent"] <= 100:
        return E("Davamiyyət həddi 1 ilə 100 faiz arasında olmalıdır")
    if not isinstance(a["excused_counts_toward_limit"], bool):
        return E("Ayarın quruluşu düzgün deyil")
    rule = a["points_rule"]
    if not isinstance(rule, list) or len(rule) > 20 or not all(
            isinstance(x, list) and len(x) == 2 and _num(x[0]) and _num(x[1]) and 0 <= x[0] <= 100 and x[1] >= 0 for x in rule):
        return E("Davamiyyət balı cədvəli \"buraxılmış faiz → bal\" cütlərindən ibarətdir")
    if [x[0] for x in rule] != sorted({x[0] for x in rule}):
        return E("Davamiyyət balı cədvəlində faizlər artan sırada və təkrarsız olmalıdır")
    return None


def _journal(j: dict) -> dict | None:
    if j["cutover_date"] is not None and not _iso(j["cutover_date"]):
        return E("«{field}» sahəsində tarix İİİİ-AA-GG formatında olmalıdır", field="cutover_date")
    h = j["edit_hours"]
    if type(h) is not int or not 1 <= h <= 720:
        return E("Düzəliş pəncərəsi 1 ilə 720 saat arasında olmalıdır")
    return None


def _calendar(cal: dict) -> dict | None:
    times, days = cal["lesson_times"], cal["holidays"]
    if not isinstance(times, list) or len(times) > 16 or not all(
            isinstance(x, list) and len(x) == 2 and all(isinstance(t, str) and TIME.fullmatch(t) for t in x) and x[0] < x[1]
            for x in times):
        return E("Dərs saatları SS:DD başlanğıc və son cütləridir")
    if [x[0] for x in times] != sorted(x[0] for x in times) or any(a[1] > b[0] for a, b in zip(times, times[1:], strict=False)):
        return E("Dərs saatları sıra ilə gəlməli və üst-üstə düşməməlidir")
    if not isinstance(days, list) or len(days) > 100 or not all(_iso(d) for d in days):
        return E("Bayram günləri İİİİ-AA-GG tarixləridir")
    return None


def _registry(r: dict) -> dict | None:
    if not isinstance(r["prefix"], str) or not PREFIX.fullmatch(r["prefix"]):
        return E("Reyestr prefiksi 2–12 hərf və ya rəqəmdir")
    return None


# ---------------------------------------------------------------- rules that read the settings
def letter(score: float, scale: list) -> str:
    """The letter of a 100-point total; below the last threshold: F."""
    return next((x[0] for x in scale if score >= x[1]), "F")


def bands(scale: list) -> tuple[list[float], list[str]]:
    """Lower edges and labels of the score bands (for a histogram): below passing, then one band per letter."""
    lows = sorted(x[1] for x in scale)
    edges = [0, *lows, 101]
    labels = [f"{_fmt(a)}–{_fmt(b - 1)}" if b <= 100 else f"{_fmt(a)}–100" for a, b in zip(edges, edges[1:], strict=False)]
    return lows, labels


def band(score: float, lows: list[float]) -> int:
    return bisect.bisect_right(lows, score)


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def outcome(scores: dict, exam: float | None, grading: dict) -> dict:
    """Semester points, and once the exam is in: the total, its letter and whether it passes. Below the exam minimum
    the result is F whatever the semester points are."""
    semester = round(sum(min(max(scores.get(x["name"]) or 0, 0), x["max"]) for x in grading["components"]), 2)
    if exam is None:
        return {"semester": semester, "exam": None, "total": None, "letter": None, "passed": None, "reason": None}
    exam = min(max(exam, 0), grading["exam"]["max"])
    total = round(semester + exam, 2)
    if exam < grading["exam"]["min"]:
        return {"semester": semester, "exam": exam, "total": total, "letter": "F", "passed": False, "reason": "exam_min"}
    passed = total >= grading["pass_mark"]
    return {"semester": semester, "exam": exam, "total": total, "letter": letter(total, grading["scale"]) if passed else "F",
            "passed": passed, "reason": None if passed else "pass_mark"}


def attendance_points(attended: int, total: int, max_points: float, rule: list) -> float | None:
    """Points of the attendance component: by the rule (missed % -> points, first row the missed share fits under),
    or in proportion to the lessons attended when there is no rule."""
    if not total:
        return None
    missed = 100 * (total - attended) / total
    if rule:
        return float(min(next((p for limit, p in rule if missed <= limit), 0), max_points))
    return round(max_points * attended / total, 1)


def teaching_weeks(term: dict | None) -> int:
    if not term:
        return 0
    days = (date.fromisoformat(term["teaching_end"]) - date.fromisoformat(term["teaching_start"])).days + 1
    return max(0, math.ceil(days / 7))
