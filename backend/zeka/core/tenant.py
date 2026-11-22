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
    # Task 48: the timetable builder's rules and soft weights; every value is a default until its key is in `confirmed`
    "timetable": {
        "days": [1, 2, 3, 4, 5, 6], "pair_hours": 2, "weeks_expected": 15,
        "shifts": {"morning": [1, 2, 3, 4], "afternoon": [4, 5, 6], "evening": [7, 8]},
        "max_pairs_day_group": 4, "max_pairs_day_teacher": 5, "max_week_hours_group": 30, "max_week_pairs_teacher": None,
        "hours_tolerance": 2, "default_need": 30, "travel_default_min": 15, "fixed_slots": [],
        "weights": {"group_window": 10, "teacher_window": 3, "same_day_course": 8, "lecture_after_seminar": 5, "undesired": 6,
                    "extra_day": 2, "building_change_group": 6, "building_change_teacher": 3, "saturday": 4, "late_pair": 1,
                    "room_waste_10": 1, "foreign_building": 2, "stability_time": 50, "stability_room": 5, "stability_weeks": 20,
                    "move_repair": 1000, "hours_miss": 2, "fair_teacher": 1, "fair_group": 1},
        "targets": {"hours_fidelity": 980, "group_windows": 50, "teacher_windows": 100, "rooms_waste": 400},
        "solver": {"construct_ejections": 50, "iter_budget": 50000, "time_budget_s": 600, "chunk_s": 20, "chunk_exam_s": 5,
                   "atomic_exam_max_s": 10, "stall": 20000, "lns_k": 30},
        "offsets": {"needs": -28, "groups": -28, "availability": -21, "review": -9, "publish": -7},
        "availability_cap_pct": 30, "availability_load_factor_pct": 150, "coverage_min_week_hours": 12, "notice_days": 2,
        "review_required": True, "review_silence": "approved", "official_document": True,
        "approver": {"title": "Tədris işləri üzrə prorektor", "name": ""},
        "publish_requires": ["term_dates", "lesson_times", "pattern"], "confirmed": []},
}
# the defaults of the timetable section a person can confirm (readiness shows the others as "standart, təsdiqlənməyib")
TT_CONFIRM = ("term_dates", "lesson_times", "pattern", "shifts", "rooms", "limits", "travel", "fixed_slots", "weights",
              "availability_cap", "review", "approver")
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
            "registry": _registry, "timetable": _timetable}[section]({**DEFAULTS[section], **v})


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


def _int(v, lo: int, hi: int) -> bool:
    return type(v) is int and lo <= v <= hi


def _ints(v, lo: int, hi: int, n: int) -> bool:
    """A non-empty list of at most n distinct ints in lo..hi."""
    return isinstance(v, list) and 0 < len(v) <= n and all(_int(x, lo, hi) for x in v) and len(set(v)) == len(v)


def _same_keys(v, section: str, key: str) -> bool:
    return isinstance(v, dict) and set(v) == set(DEFAULTS[section][key])


SOLVER_LIMITS = {"construct_ejections": (0, 1000), "iter_budget": (1, 5_000_000), "time_budget_s": (10, 7200),
                 "chunk_s": (5, 60), "chunk_exam_s": (1, 60), "atomic_exam_max_s": (1, 60), "stall": (100, 10_000_000),
                 "lns_k": (2, 200)}


def _timetable(t: dict) -> dict | None:
    bad = E("Ayarın quruluşu düzgün deyil")
    if not _ints(t["days"], 1, 7, 7) or t["days"] != sorted(t["days"]):
        return E("Dərs günləri 1 (bazar ertəsi) ilə 7 (bazar) arasında təkrarlanmayan rəqəmlərdir")
    shifts = t["shifts"]
    if not (isinstance(shifts, dict) and len(shifts) <= 10 and all(
            isinstance(k, str) and 1 <= len(k) <= 20 and _ints(p, 1, 16, 16) for k, p in shifts.items())):
        return E("Növbənin dərs cütləri 1 ilə 16 arasındakı nömrələrlə yazılır")
    if not _int(t["max_week_hours_group"], 1, 30):
        return E("Qrupun həftəlik auditoriya yükü 30 saatdan çox ola bilməz")
    if not (_int(t["pair_hours"], 1, 4) and _int(t["weeks_expected"], 1, 20) and _int(t["max_pairs_day_group"], 1, 8)
            and _int(t["max_pairs_day_teacher"], 1, 8) and (t["max_week_pairs_teacher"] is None or _int(t["max_week_pairs_teacher"], 1, 48))
            and _num(t["hours_tolerance"]) and 0 <= t["hours_tolerance"] <= 10 and _int(t["default_need"], 1, 1000)
            and _int(t["travel_default_min"], 0, 120) and _int(t["availability_cap_pct"], 0, 100)
            and _int(t["availability_load_factor_pct"], 100, 400) and _int(t["coverage_min_week_hours"], 0, 30)
            and _int(t["notice_days"], 0, 60) and isinstance(t["review_required"], bool) and isinstance(t["official_document"], bool)
            and t["review_silence"] in ("approved", "pending")):
        return bad
    slots = t["fixed_slots"]
    if not (isinstance(slots, list) and len(slots) <= 50 and all(
            isinstance(x, dict) and set(x) <= {"weekday", "period", "groups"} and _int(x.get("weekday"), 1, 7)
            and _int(x.get("period"), 1, 16) and (x.get("groups") is None or _ints(x["groups"], 1, 2**62, 500)) for x in slots)):
        return bad
    if not (_same_keys(t["weights"], "timetable", "weights") and all(_int(x, 0, 10_000) for x in t["weights"].values())):
        return E("Əmsallar 0 ilə 10 000 arasında tam ədədlərdir")
    if not (_same_keys(t["targets"], "timetable", "targets") and all(_int(x, 0, 1_000_000) for x in t["targets"].values())):
        return bad
    sol = t["solver"]
    if not (_same_keys(sol, "timetable", "solver") and all(_int(sol[k], lo, hi) for k, (lo, hi) in SOLVER_LIMITS.items())):
        return E("Hesablamanın bir mərhələsi 5 ilə 60 saniyə arasında olmalıdır; həllin digər hədləri tam ədədlərdir")
    if not (_same_keys(t["offsets"], "timetable", "offsets") and all(_int(x, -365, -1) for x in t["offsets"].values())):
        return E("Son tarix dərslər başlamazdan neçə gün əvvəl olduğunu göstərən mənfi ədədlə yazılır")
    ap = t["approver"]
    if not (_same_keys(ap, "timetable", "approver") and _text(ap["title"], 1, 120) and isinstance(ap["name"], str) and len(ap["name"]) <= 120):
        return bad
    for key in ("publish_requires", "confirmed"):
        v = t[key]
        if not (isinstance(v, list) and all(isinstance(x, str) and x in TT_CONFIRM for x in v) and len(set(v)) == len(v)):
            return E("Təsdiq siyahısında naməlum bənd var")
    if not {"term_dates", "lesson_times", "pattern"} <= set(t["publish_requires"]):
        return E("Dərc üçün dərs tarixləri, zəng cədvəli və həftəlik bölgü qaydası mütləq təsdiqlənməlidir")
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
