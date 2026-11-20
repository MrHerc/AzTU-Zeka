"""Measured indicators of the leadership dashboard and the accreditation evidence (tasks/todo.md, Task 39).

A tile is a measure (queries in repo.py) over a stated period, with a translatable definition: ``tile()`` gives its
value, its 8 weekly points, its period and its target. A number that cannot be measured is not a tile: the test
preparation time, the satisfaction score, the learning gain and the AI cost per student were literals and are gone (the
satisfaction survey is on the feedback page). The targets are the pilot's goals, not measurements.
"""
from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import datetime, timedelta

from ...core import clock, perms
from ...core.i18n import S, S_, T3, localize
from ...legacy.store import iso, now
from . import repo

WEEKS = 8
EVIDENCE_DAYS = 30


def _weekly(rs: list[dict], key: str) -> list[float]:
    """8 weekly sums of ``key``, oldest first, from per-week rows."""
    out = [0.0] * WEEKS
    for r in rs:
        if 0 <= r["w"] < WEEKS:
            out[WEEKS - 1 - r["w"]] += r[key] or 0
    return out


# A measure: (c, since, until, t) -> (numerators, denominators), 8 weeks each, oldest first; no denominators for a count.
def _active(role: str):
    def measure(c, since, until, t):
        return _weekly(repo.active_weekly(c, role, since, until), "n"), [repo.accounts(c, role)] * WEEKS
    return measure


def _journal(c, since, until, t):
    rs = repo.lessons_weekly(c, since, until)
    return _weekly(rs, "filled"), _weekly(rs, "held")


def _request_hours(c, since, until, t):
    rs = repo.requests_weekly(c, since, until)
    return _weekly(rs, "hours"), _weekly(rs, "n")


def _request_sla(c, since, until, t):
    rs = repo.requests_weekly(c, since, until)
    return _weekly(rs, "in_time"), _weekly(rs, "due")


def _cited(c, since, until, t):
    rs = repo.answers_weekly(c, since, until)
    return _weekly(rs, "cited"), _weekly(rs, "n")


def _exams(c, since, until, t):
    u = clock.now()                                  # exam times are aware UTC
    return _weekly(repo.exams_weekly(c, (u - timedelta(weeks=WEEKS)).isoformat(timespec="seconds"), u.isoformat(timespec="seconds")), "n"), None


def _academy(c, since, until, t):
    """Teachers with at least 3 completed modules by the end of each week (a running total)."""
    done = repo.academy_completions(c)
    ends = [iso(t - timedelta(weeks=WEEKS - 1 - i)) for i in range(WEEKS)]
    counts = [sum(n >= 3 for n in Counter(r["user_id"] for r in done if r["completed_at"] <= end).values()) for end in ends]
    return counts, [repo.accounts(c, "teacher")] * WEEKS


# weeks: the value's period in weeks back from now (None: a running total up to now); lower: a smaller value is better
TILES: tuple[dict, ...] = (
    {"key": "wau_student", "label": S_("Həftəlik aktiv tələbələr"), "unit": "pct", "weeks": 1, "target": 60, "measure": _active("student"),
     "definition": S_("Son 7 gündə portala daxil olan və ya orada iş görən tələbələrin aktiv tələbə hesablarına nisbəti.")},
    {"key": "wau_teacher", "label": S_("Həftəlik aktiv müəllimlər"), "unit": "pct", "weeks": 1, "target": 70, "measure": _active("teacher"),
     "definition": S_("Son 7 gündə portala daxil olan və ya orada iş görən müəllimlərin aktiv müəllim hesablarına nisbəti.")},
    {"key": "journal", "label": S_("Davamiyyəti yazılmış dərslər"), "unit": "pct", "weeks": 4, "target": None, "measure": _journal,
     "definition": S_("Son 28 gündə keçirilmiş (bitmiş və ləğv olunmamış) dərslərdən davamiyyəti jurnala yazılanların payı.")},
    {"key": "request_hours", "label": S_("Müraciətin orta icra müddəti"), "unit": "hours", "weeks": 4, "target": 24, "lower": True,
     "measure": _request_hours,
     "definition": S_("Son 28 gündə bağlanan (hazır və ya rədd edilmiş) müraciətlərin verildiyi andan bağlandığı ana qədər orta müddəti, saatla.")},
    {"key": "request_sla", "label": S_("Vaxtında bağlanan müraciətlər"), "unit": "pct", "weeks": 4, "target": None, "measure": _request_sla,
     "definition": S_("Son 28 gündə bağlanan və icra müddəti olan müraciətlərdən müddət bitənədək bağlananların payı.")},
    {"key": "cited", "label": S_("Mənbəyə istinad edən cavablar"), "unit": "pct", "weeks": 4, "target": 95, "measure": _cited,
     "definition": S_("Son 28 gündə AI tutorun və kampus köməkçisinin cavablarından ən azı bir mənbəyə (fənn materialına və ya bilik bazası məqaləsinə) istinad edənlərin payı.")},
    {"key": "exams", "label": S_("Açılan imtahanlar"), "unit": "count", "weeks": 4, "target": None, "measure": _exams,
     "definition": S_("Son 28 gündə açılan onlayn imtahanların sayı.")},
    {"key": "academy", "label": S_("Akademiyada ≥ 3 modul keçən müəllimlər"), "unit": "pct", "weeks": None, "target": 80, "measure": _academy,
     "definition": S_("Aktiv müəllim hesablarından AI Akademiyada ən azı 3 modulu tamamlayanların payı, bu günə qədər.")},
)


def _value(unit: str, num: float, den: float | None):
    if unit == "count":
        return int(num)
    if not den:
        return None                                  # nothing to measure in the period: not zero
    return round(num / den * (1 if unit == "hours" else 100), 1)


def tile(c, spec: dict, t: datetime) -> dict:
    since, until = iso(t - timedelta(weeks=WEEKS)), iso(t)
    num, den = spec["measure"](c, since, until, t)
    k = spec["weeks"] or 1
    value = _value(spec["unit"], sum(num[-k:]), sum(den[-k:]) if den else None)
    target = spec["target"]
    return {"key": spec["key"], "label": T3(spec["label"]), "definition": T3(spec["definition"]), "unit": spec["unit"], "value": value,
            "series": [_value(spec["unit"], num[i], den[i] if den else None) for i in range(WEEKS)], "target": target,
            "lower": bool(spec.get("lower")),
            "ok": None if value is None or target is None else value <= target if spec.get("lower") else value >= target,
            "range": {"from": None if spec["weeks"] is None else iso(t - timedelta(weeks=k)), "to": until}}


def tiles(c) -> list[dict]:
    t = now()
    return [tile(c, spec, t) for spec in TILES]


def active_roles(c) -> list[dict]:
    """Distinct active users of the last 7 days per role the session acted in."""
    t = now()
    return repo.active_by_role(c, iso(t - timedelta(days=7)), iso(t))


# ---------------------------------------------------------------- accreditation evidence
# Indicators of the ministry's accreditation criteria (decision KQ-05, 30.09.2022) as docs/research/01 summarises them:
# 3.5.1, 3.5.3 and 5.4.2-5.4.8. The titles are short; 5.4.5, 5.4.6 and 5.4.8 follow that summary's order and must be
# checked against the decision's text. A measure: (count key, label, counted over the period or not).
INDICATORS = (
    ("3.5.1", S_("Sinxron və asinxron tədris və qiymətləndirmə üçün e-təhsil sistemi"),
     (("courses", S_("Fənlər"), False), ("materials", S_("Tədris materialları"), False), ("assignments", S_("Tapşırıqlar"), False),
      ("lessons_held", S_("Keçirilmiş dərslər"), True), ("exams", S_("Açılan onlayn imtahanlar"), True)),
     ((S_("Fənlər üzrə göstəricilər"), "/leader", ("leader", "admin")), (S_("İmtahan cədvəlləri"), "/office/exams", ("admin",))), None),
    ("3.5.3", S_("Tələbə fəaliyyətini qeydə alan platforma və jurnal"),
     (("student_events", S_("Tələbə fəaliyyəti qeydləri"), True), ("attendance_marks", S_("Davamiyyət qeydləri"), True)),
     ((S_("Audit jurnalı"), "/admin/audit", ("leader", "admin")), (S_("Davamiyyət"), "/journal", ("admin",))), None),
    ("5.4.2", S_("Sistemin əhatəsi"),
     (("services", S_("Açıq e-xidmətlər"), False), ("modules", S_("İstifadə olunan modullar"), True)),
     ((S_("E-xidmətlər"), "/office", ("leader", "admin")),), None),
    ("5.4.3", S_("Rolların ayrılması"),
     (("roles", S_("İstifadədə olan rollar"), False), ("grants", S_("Əlavə rol təyinatları"), False), ("perms", S_("İcazə qaydaları"), False)),
     ((S_("Struktur və reyestr"), "/admin/directory", ("admin",)),), None),
    ("5.4.4", S_("Tələbələrin istifadəsi"),
     (("students_active", S_("Aktiv tələbələr"), True), ("students", S_("Aktiv tələbə hesabları"), False)),
     ((S_("Pilot paneli"), "/leader", ("leader", "admin")),), None),
    ("5.4.5", S_("Müəllimlərin istifadəsi"),
     (("teachers_active", S_("Aktiv müəllimlər"), True), ("teachers", S_("Aktiv müəllim hesabları"), False)),
     ((S_("Pilot paneli"), "/leader", ("leader", "admin")),), None),
    ("5.4.6", S_("İnformasiya təhlükəsizliyi"),
     (("staff_mfa", S_("İkinci faktoru olan işçi hesabları"), False), ("staff", S_("Aktiv işçi hesabları"), False)),
     ((S_("Audit jurnalı"), "/admin/audit", ("leader", "admin")),), None),
    ("5.4.7", S_("TMİS ilə inteqrasiya"),
     (("status_reported", S_("«Tələbə-məzun» sisteminə daxil edilmiş status dəyişiklikləri"), False), ("api_keys", S_("Aktiv API açarları"), False)),
     ((S_("İnteqrasiya"), "/admin/integration", ("admin",)),),
     S_("Birbaşa inteqrasiya yoxdur: TMİS-in açıq API-si tapılmayıb. Zəka reyestri və status dəyişikliklərini faylla ixrac edir.")),
    ("5.4.8", S_("Texniki xidmət və dəstək"),
     (("jobs_ok", S_("Uğurla icra olunmuş dövri işlər"), True),),
     ((S_("Dəstək sorğuları"), "/staff/support", ("admin",)),),
     S_("Xidmət və təhlükəsizlik müqavilələri platformada saxlanmır; burada dövri texniki işlərin icrası sayılır.")),
)


def evidence(c, role: str) -> dict:
    t, u = now(), clock.now()
    since, until = iso(t - timedelta(days=EVIDENCE_DAYS)), iso(t)
    counts = {**repo.evidence_counts(c, since, until, (u - timedelta(days=EVIDENCE_DAYS)).isoformat(timespec="seconds")),
              "perms": len(perms.PERMS)}
    return {"range": {"from": since, "to": until}, "indicators": [
        {"code": code, "title": T3(title), "note": T3(note) if note else None,
         "measures": [{"key": k, "label": T3(label), "value": counts[k], "range": {"from": since if period else None, "to": until}}
                      for k, label, period in measures],
         "links": [{"label": T3(label), "href": href} for label, href, roles in links if role in roles]}
        for code, title, measures, links, note in INDICATORS]}


def evidence_csv(c, role: str, lang: str) -> str:
    """The evidence page as a spreadsheet: one row per measure."""
    ev = localize(evidence(c, role), lang)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([S(h, lang) for h in (S_("Göstərici"), S_("Ad"), S_("Ölçü"), S_("Say"), S_("Başlanğıc"), S_("Son"))])
    for ind in ev["indicators"]:
        w.writerows([ind["code"], ind["title"], m["label"], m["value"], m["range"]["from"] or "", m["range"]["to"]] for m in ind["measures"])
    return buf.getvalue()
