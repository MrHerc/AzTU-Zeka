"""Attendance rules (tasks/todo.md, Task 20). No I/O.

Percent = missed academic hours / planned academic hours of a student in a course. Planned: the hours of the course's
lessons in the teaching period that are not cancelled and that the student is on the list of (an enrolment in force on
the day, the unit's group and subgroup). Missed: before the cut-over date, the imported hours (an opening balance, or
lesson-level rows with source 'legacy'); after it, the absences recorded in Zəka. An unexcused absence always counts;
an excused one when the university says so. Status: 'normal', 'warning' (past 80% of the limit), 'not_admitted' (past
the limit) or 'incomplete' (lessons before the cut-over date but nothing imported for them: never 'not_admitted').
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ...core.i18n import E

MARKS = ("present", "absent", "late")        # what a teacher marks; 'excused' comes from an approved request
STATUSES = ("present", "absent", "late", "excused")
DEFAULT_HOURS = 2                            # shortcut: a lesson made before Task 19 has no academic hours; one pair is 2
WARNING_SHARE = 0.8


def hours(lesson: dict) -> int:
    return lesson.get("academic_hours") or DEFAULT_HOURS


def marks_input(body, roster: set[int]) -> tuple[dict[int, str], dict | None]:
    """{student id: mark} from {"marks": {"<id>": "absent" | "late" | "present"}}; everyone else on the list is present."""
    raw = body.get("marks") or {}
    if not isinstance(raw, dict):
        return {}, E("Qeydlər siyahı kimi göndərilməlidir")
    out = {uid: "present" for uid in roster}
    for k, v in raw.items():
        uid = int(k) if isinstance(k, str) and k.isascii() and k.isdigit() else None
        if uid not in roster:
            return {}, E("Tələbə bu dərsin siyahısında deyil")
        if v not in MARKS:
            return {}, E("Qeyd iştirak, qayıb və ya gecikmə olmalıdır")
        out[uid] = v
    return out, None


def window_open(day: str, end: str, now: datetime, hours_: int) -> bool:
    """A teacher writes the lesson's attendance from its day on, until ``hours_`` after it ends."""
    start_of_day = datetime.fromisoformat(day)
    return start_of_day <= now <= datetime.fromisoformat(f"{day}T{end}") + timedelta(hours=hours_)


def standing(lessons: list[dict], records: dict[int, dict], *, cutover: str | None, opening: dict | None,
             excused_counts: bool, limit_percent: float) -> dict:
    """The student's standing in one course. ``lessons``: the lessons the student is on the list of in the teaching
    period, not cancelled (id, day, academic_hours). ``records``: their attendance by lesson id (status, source)."""
    planned = sum(hours(x) for x in lessons)
    unexcused = excused = 0
    before = [x for x in lessons if cutover and x["day"] <= cutover]
    imported = False
    if opening:
        unexcused, excused, imported = opening["unexcused_hours"], opening["excused_hours"], True
    for x in lessons:
        r = records.get(x["id"])
        if not r:
            continue
        if cutover and x["day"] <= cutover:
            if opening or r.get("source") != "legacy":
                continue                                # an opening balance holds them; Zəka rows before the cut-over do not count
            imported = True
        if r["status"] == "absent":
            unexcused += hours(x)
        elif r["status"] == "excused":
            excused += hours(x)
    missed = unexcused + (excused if excused_counts else 0)
    percent = round(100 * missed / planned, 1) if planned else 0.0
    if before and not imported:
        status = "incomplete"
    elif planned and missed * 100 > limit_percent * planned:
        status = "not_admitted"
    elif planned and missed * 100 > WARNING_SHARE * limit_percent * planned:
        status = "warning"
    else:
        status = "normal"
    return {"planned_hours": planned, "unexcused_hours": unexcused, "excused_hours": excused, "missed_hours": missed,
            "percent": percent, "limit_percent": limit_percent, "allowed_hours": int(planned * limit_percent / 100),
            "status": status, "as_of": opening["as_of"] if opening else cutover}


def effective_limit(tenant_limit: float, syllabus_limit: float | None) -> float:
    return min(tenant_limit, syllabus_limit) if syllabus_limit is not None else tenant_limit
