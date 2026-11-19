"""Timetable rules (tasks/todo.md, Task 19). No I/O.

A slot is a timetable row (weekday, start, end, week pattern) or a lesson on one day, with what it holds: its room
(``#<id>`` once linked to a room, else the room text's key), its teacher and its (group, subgroup) pairs. Two slots at
overlapping times clash on the same room, the same teacher, or a shared group: a whole group (subgroup None) clashes
with each of its subgroups, subgroup 1 does not clash with subgroup 2.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime, timedelta

from ...core.i18n import E

TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
WEEKS = ("all", "odd", "even")          # week 1 is the week (Monday to Sunday) of the term's first teaching day
KIND_LABEL = {"lecture": "Mühazirə", "seminar": "Məşğələ", "lab": "Laboratoriya"}       # the label lessons carry
BS = chr(92)                             # a backslash: escaping in TEXT values (3.3.11)
MAX_HOURS = 8                            # academic hours of one timetable row


def row_input(body, partial: bool = False) -> tuple[dict, dict | None]:
    """weekday, start, end, weeks, academic_hours and room of a timetable row from a request body."""
    out: dict = {}
    if not partial or "weekday" in body:
        wd = body.get("weekday")
        if isinstance(wd, bool) or not isinstance(wd, int) or not 1 <= wd <= 7:
            return {}, E("Həftə günü 1 ilə 7 arasında olmalıdır")
        out["weekday"] = wd
    for k in ("start", "end"):
        if not partial or k in body:
            v = body.get(k)
            if not (isinstance(v, str) and TIME.fullmatch(v)):
                return {}, E("Dərsin vaxtı SS:DD formatında olmalı və bitməsi başlanğıcından sonra olmalıdır")
            out[k] = v
    if not partial or "weeks" in body:
        weeks = body.get("weeks") or "all"
        if weeks not in WEEKS:
            return {}, E("Həftələr: hər həftə, tək və ya cüt həftələr")
        out["weeks"] = weeks
    if not partial or "academic_hours" in body:
        h = body.get("academic_hours")
        if isinstance(h, bool) or not isinstance(h, int) or not 1 <= h <= MAX_HOURS:
            return {}, E("Akademik saat 1 ilə {n} arasında olmalıdır", n=MAX_HOURS)
        out["academic_hours"] = h
    if not partial or "room" in body:
        room = body.get("room")
        if room is not None and not isinstance(room, str):
            return {}, E("Otağı yazın")
        out["room"] = " ".join((room or "").split())[:100] or None
    return out, None


def times_problem(start: str, end: str) -> dict | None:
    return None if start < end else E("Dərsin vaxtı SS:DD formatında olmalı və bitməsi başlanğıcından sonra olmalıdır")


def week_no(day: date, teaching_start: date) -> int:
    monday = teaching_start - timedelta(days=teaching_start.isoweekday() - 1)
    return (day - monday).days // 7 + 1


def in_weeks(weeks: str, n: int) -> bool:
    return weeks == "all" or (weeks == "odd") == (n % 2 == 1)


def lesson_dates(row: dict, term: dict, holidays: Iterable[str], start_from: date | None = None) -> list[date]:
    """The days a weekly row holds a lesson: in the term's teaching period, in its weeks, not on a holiday."""
    first, last = date.fromisoformat(term["teaching_start"]), date.fromisoformat(term["teaching_end"])
    off = set(holidays)
    d = max(first, start_from or first)
    d += timedelta(days=(row["weekday"] - d.isoweekday()) % 7)
    out = []
    while d <= last:
        if in_weeks(row["weeks"], week_no(d, first)) and d.isoformat() not in off:
            out.append(d)
        d += timedelta(days=7)
    return out


def _weeks_meet(a: str, b: str) -> bool:
    return a == "all" or b == "all" or a == b


def _groups_meet(a: Iterable[tuple[int, int | None]], b: Iterable[tuple[int, int | None]]) -> list[int]:
    return sorted({ga for ga, sa in a for gb, sb in b if ga == gb and (sa is None or sb is None or sa == sb)})


def conflicts(new: dict, others: Iterable[dict]) -> list[dict]:
    """What ``new`` clashes with: [{"id", "what": "room" | "teacher" | "group", "groups"}], one entry per clash."""
    out = []
    for o in others:
        if o["id"] == new.get("id") or o["weekday"] != new["weekday"] or not _weeks_meet(o["weeks"], new["weeks"]):
            continue
        if not (o["start"] < new["end"] and new["start"] < o["end"]):
            continue
        if new["room"] and o["room"] == new["room"]:
            out.append({"id": o["id"], "what": "room", "groups": []})
        if new["teacher_id"] and o["teacher_id"] == new["teacher_id"]:
            out.append({"id": o["id"], "what": "teacher", "groups": []})
        shared = _groups_meet(new["groups"], o["groups"])
        if shared:
            out.append({"id": o["id"], "what": "group", "groups": shared})
    return out


def attends(student: dict, unit_groups: list[int], unit_subgroup: int | None) -> bool:
    """Whether an enrolled student is on a unit's lesson list: the unit's group (any, when it names none) and subgroup."""
    return (not unit_groups or student["group_id"] in unit_groups) and (unit_subgroup is None or student["subgroup"] == unit_subgroup)


def on_list(student: dict, lesson: dict, audience: dict[int, tuple[list[int], int | None]]) -> bool:
    """Whether a student (an enrolment: group_id, subgroup, begin_date, end_date) is on a lesson's list: the enrolment is
    in force on the lesson's day and the student attends the lesson's unit. A lesson without a unit: every enrolled student."""
    day = lesson["day"]
    if (student.get("begin_date") and student["begin_date"] > day) or (student.get("end_date") and student["end_date"] <= day):
        return False
    if not lesson.get("unit_id"):
        return True
    groups, subgroup = audience.get(lesson["unit_id"], ([], None))
    return attends(student, groups, subgroup)


# ---------------------------------------------------------------- iCalendar (RFC 5545)
def _text(v) -> str:
    out = str(v or '')
    for a, b in ((BS, BS + BS), (';', BS + ';'), (',', BS + ','), ('\r', ''), ('\n', BS + 'n')):
        out = out.replace(a, b)
    return out


def _fold(line: str) -> list[str]:
    """Lines of at most 75 octets; a continuation starts with a space (3.1). A UTF-8 character is never split."""
    out: list[str] = []
    cur, size = "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > (75 if not out else 74):
            out.append(cur)
            cur, size = "", 0
        cur += ch
        size += n
    out.append(cur)
    return [out[0]] + [" " + x for x in out[1:]]


def _local(day: str, hhmm: str) -> str:
    return day.replace("-", "") + "T" + hhmm.replace(":", "") + "00"


def calendar(events: list[dict], *, tzid: str, offset: str, host: str, stamp: datetime, name: str) -> str:
    """A VCALENDAR of lessons. ``offset`` is the zone's UTC offset as +HHMM (a zone without daylight saving time, like
    Asia/Baku); each event: id, day, start, end, summary, location, status ('scheduled' | 'cancelled'), note."""
    dtstamp = stamp.strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Zeka//Timetable//AZ", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{_text(name)}", f"X-WR-TIMEZONE:{tzid}",
             "BEGIN:VTIMEZONE", f"TZID:{tzid}", "BEGIN:STANDARD", "DTSTART:19700101T000000", f"TZOFFSETFROM:{offset}",
             f"TZOFFSETTO:{offset}", "END:STANDARD", "END:VTIMEZONE"]
    for ev in events:
        lines += ["BEGIN:VEVENT", f"UID:{ev.get('uid') or 'lesson-' + str(ev['id'])}@{host}", f"DTSTAMP:{dtstamp}",
                  f"DTSTART;TZID={tzid}:{_local(ev['day'], ev['start'])}", f"DTEND;TZID={tzid}:{_local(ev['day'], ev['end'])}",
                  f"SUMMARY:{_text(ev['summary'])}", "STATUS:" + ("CANCELLED" if ev["status"] == "cancelled" else "CONFIRMED")]
        if ev.get("location"):
            lines.append(f"LOCATION:{_text(ev['location'])}")
        if ev.get("note"):
            lines.append(f"DESCRIPTION:{_text(ev['note'])}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "".join(x + "\r\n" for line in lines for x in _fold(line))
