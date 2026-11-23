"""Timetable rules (tasks/todo.md, Task 19). No I/O.

A slot is a timetable row (weekday, start, end, week pattern) or a lesson on one day, with what it holds: its room
(``#<id>`` once linked to a room, else the room text's key), its teacher and its (group, subgroup) pairs. Two slots at
overlapping times clash on the same room, the same teacher, or a shared group: a whole group (subgroup None) clashes
with each of its subgroups, subgroup 1 does not clash with subgroup 2.
"""
from __future__ import annotations

import math
import re
from collections.abc import Iterable
from datetime import date, datetime, timedelta

from ...core.i18n import E
from ..directory.domain import ROOM_KINDS

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
                return {}, E("Dərsin vaxtı SS:DD formatında olmalı, bitmə vaxtı isə başlama vaxtından sonra olmalıdır")
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
    return None if start < end else E("Dərsin vaxtı SS:DD formatında olmalı, bitmə vaxtı isə başlama vaxtından sonra olmalıdır")


def week_no(day: date, teaching_start: date) -> int:
    monday = teaching_start - timedelta(days=teaching_start.isoweekday() - 1)
    return (day - monday).days // 7 + 1


# ---------------------------------------------------------------- week sets (Task 48)
MAX_WEEK = 53
WEEK_LIST = re.compile(r"^\d{1,2}(-\d{1,2})?(,\d{1,2}(-\d{1,2})?)*$")


def week_mask(text, n: int) -> int:
    """The weeks of ``text`` (``all | odd | even | N[-M](,N[-M])*``, 1 <= N <= M <= 53) as a bit mask over n teaching
    weeks: bit 0 is week 1. Text outside the grammar is the empty set, 0."""
    n = max(0, min(int(n), MAX_WEEK))
    full = (1 << n) - 1
    t = text.strip().lower().replace(" ", "") if isinstance(text, str) else ""
    if t == "all":
        return full
    if t in ("odd", "even"):
        return sum(1 << i for i in range(0 if t == "odd" else 1, n, 2))
    if not WEEK_LIST.fullmatch(t):
        return 0
    mask = 0
    for part in t.split(","):
        lo, _, hi = part.partition("-")
        a, b = int(lo), int(hi or lo)
        if not 1 <= a <= b <= MAX_WEEK:
            return 0
        mask |= ((1 << (b - a + 1)) - 1) << (a - 1)
    return mask & full


def week_text(mask: int, n: int) -> str:
    """The canonical text of a week mask: a mask equal to all, odd or even is the word, else ranges ("1-4,9")."""
    n = max(0, min(int(n), MAX_WEEK))
    mask &= (1 << n) - 1
    for word in ("all", "odd", "even"):
        if mask and mask == week_mask(word, n):
            return word
    out, w = [], 0
    while w < n:
        if mask >> w & 1:
            s = w
            while w + 1 < n and mask >> (w + 1) & 1:
                w += 1
            out.append(str(s + 1) if s == w else f"{s + 1}-{w + 1}")
        w += 1
    return ",".join(out)


def in_weeks(weeks: str, n: int) -> bool:
    return 1 <= n <= MAX_WEEK and bool(week_mask(weeks, MAX_WEEK) >> (n - 1) & 1)


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
    full = (1 << MAX_WEEK) - 1          # a text outside the grammar meets every week: a clash is reported, never hidden
    return bool((week_mask(a, MAX_WEEK) or full) & (week_mask(b, MAX_WEEK) or full))


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


def conflicts_all(rows: list[dict]) -> list[dict]:
    """Every clash of a whole set of rows by the rule of ``conflicts``, bucketed by weekday and resource and swept by
    start time (linear in the rows plus the bucket sizes): [{"a", "b", "what", "groups"}], a < b, one per pair and kind."""
    buckets: dict[tuple, list[dict]] = {}
    for r in rows:
        keys: list[tuple] = [("group", g) for g in sorted({g for g, _ in r["groups"]})]
        if r.get("room"):
            keys.append(("room", r["room"]))
        if r.get("teacher_id"):
            keys.append(("teacher", r["teacher_id"]))
        for k in keys:
            buckets.setdefault((r["weekday"], *k), []).append(r)
    found: dict[tuple, set] = {}
    for (_, what, res), items in buckets.items():
        active: list[dict] = []
        for x in sorted(items, key=lambda r: r["start"]):
            active = [y for y in active if y["end"] > x["start"]]
            for y in active:
                if not _weeks_meet(x["weeks"], y["weeks"]):
                    continue
                if what == "group" and not _groups_meet([c for c in x["groups"] if c[0] == res], [c for c in y["groups"] if c[0] == res]):
                    continue
                a, b = sorted((x["id"], y["id"]))
                found.setdefault((a, b, what), set()).update([res] if what == "group" else [])
            active.append(x)
    return [{"a": a, "b": b, "what": w, "groups": sorted(gs)} for (a, b, w), gs in sorted(found.items())]


# ---------------------------------------------------------------- the timetable builder (Task 48): pure rules
# A meeting is one weekly appointment of a teaching unit, key "{unit_id}:{part}"; its value is a weekday, a first
# period (pair number, 1-based), a week mask and a room. The problem is the snapshot a run solves (ids only):
#   weeks, lesson_times, settings (the tenant section "timetable"), rooms, groups, units, needs, availability, blocks,
#   obstacles (rows the run may not move), locked and reference placements, from_week and repair (a mid-term repair).
UNIT_ROOM_KINDS = {"lecture": ["lecture_hall", "classroom"], "seminar": ["classroom", "lecture_hall"], "lab": ["lab", "computer_lab"]}
# D3: when the university has no bell times yet, 6 pairs of 80 minutes from 09:00 and 2 evening pairs
DEFAULT_TIMES = [["09:00", "10:20"], ["10:30", "11:50"], ["12:00", "13:20"], ["13:50", "15:10"], ["15:20", "16:40"],
                 ["16:50", "18:10"], ["18:20", "19:40"], ["19:50", "21:10"]]
LATE_AFTER = 4          # S7: pairs after the fourth are late for a group without a shift


def _minutes(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def lesson_times(problem: dict) -> list[list[str]]:
    return problem.get("lesson_times") or DEFAULT_TIMES


def breaks(times: list[list[str]]) -> list[int]:
    """Minutes between pair p and pair p + 1 (0-based)."""
    return [_minutes(b[0]) - _minutes(a[1]) for a, b in zip(times, times[1:], strict=False)]


def _half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def pattern(hours, n_weeks: int, pair_hours: int, duration: int = 1, override: list | None = None) -> list[list[int]]:
    """Semester hours to weekly meetings, each a list of the week masks it may take (tasks/todo.md, Task 48, the
    weekly-pattern table). P = hours / (pair_hours x duration) meeting-weeks; floor(P / W) weekly meetings; the
    remainder r becomes fortnightly (odd or even) or one aligned block of round_half_up(r) consecutive weeks, whichever
    is closer to r, fortnightly on a tie; a remainder under half a week is dropped. An override (week-set texts) replaces
    the rule, one meeting per text. Hours <= 0: no meeting."""
    if override:
        masks = [week_mask(w, n_weeks) for w in override]
        return [[m] for m in masks if m]
    try:
        h = float(hours)
    except (TypeError, ValueError):
        return []
    if not (math.isfinite(h) and h > 0 and n_weeks > 0 and pair_hours > 0 and duration > 0):
        return []
    n = min(n_weeks, MAX_WEEK)
    full = (1 << n) - 1
    p = h / (pair_hours * duration)
    k = int(p // n)
    r = p - k * n
    out = [[full] for _ in range(k)]
    if r > 1e-9:
        odd, even = week_mask("odd", n), week_mask("even", n)
        cands: list[tuple[float, int, list[int]]] = [
            (min(abs(odd.bit_count() - r), abs(even.bit_count() - r)), 0, [odd, even] if even else [odd]), (r, 2, [])]
        b = min(_half_up(r), n)
        if b > 0:
            cands.append((abs(b - r), 1, [((1 << b) - 1) << s for s in range(0, n - b + 1, b)]))
        best = min(cands, key=lambda c: (c[0], c[1]))
        if best[2]:
            out.append(best[2])
    return out


def _blocks(problem: dict) -> dict[tuple[str, int], int]:
    """Blocked weeks by (subject_type, subject_id), active blocks only."""
    out: dict[tuple[str, int], int] = {}
    for b in problem.get("blocks") or []:
        if b.get("active", 1):
            k = (b["subject_type"], b["subject_id"])
            out[k] = out.get(k, 0) | week_mask(b["weeks"], problem["weeks"])
    return out


def future_mask(problem: dict) -> int:
    """The weeks a run may change: from ``from_week`` (a repair) to the end; the past blocks nothing."""
    n = problem["weeks"]
    return ((1 << n) - 1) & ~((1 << (max(1, problem.get("from_week") or 1) - 1)) - 1)


def meetings_of(problem: dict) -> tuple[list[dict], list[dict]]:
    """The meetings of the problem's units, in unit id order, and the units that cannot be scheduled
    ({unit_id, code}: no_groups, no_hours). Variants lose the blocked weeks of the unit's groups and teacher (H16) and,
    in a repair, the past weeks."""
    st, n = problem["settings"], problem["weeks"]
    needs = {x["unit_id"]: x for x in problem.get("needs") or []}
    sizes = {g["id"]: g.get("size") or 0 for g in problem.get("groups") or []}
    blocks = _blocks(problem)
    future = future_mask(problem)
    out: list[dict] = []
    excluded: list[dict] = []
    for u in sorted(problem["units"], key=lambda x: x["id"]):
        nd = needs.get(u["id"]) or {}
        groups = sorted(set(u.get("groups") or []))
        if not groups:
            excluded.append({"unit_id": u["id"], "code": "no_groups"})
            continue
        dur = int(nd.get("duration") or 1)
        parts = pattern(u.get("hours"), n, st["pair_hours"], dur, nd.get("pattern"))
        if not parts:
            excluded.append({"unit_id": u["id"], "code": "no_hours"})
            continue
        blocked = blocks.get(("teacher", u.get("teacher_id")), 0) if u.get("teacher_id") else 0
        for g in groups:
            blocked |= blocks.get(("group", g), 0)
        if nd.get("need"):
            need, source = int(nd["need"]), "override"
        elif u.get("students"):
            need, source = int(u["students"]), "students"
        elif sum(sizes.get(g, 0) for g in groups):
            need, source = sum(sizes.get(g, 0) for g in groups), "registry"
        else:
            need, source = int(st["default_need"]), "default"
        online = nd.get("mode") == "online"
        for part, variants in enumerate(parts):
            masked: list[int] = []
            for v in variants:
                m = v & ~blocked & future
                if m and m not in masked:
                    masked.append(m)
            out.append({"key": f"{u['id']}:{part}", "unit_id": u["id"], "part": part, "course_id": u.get("course_id"),
                        "kind": u.get("kind"), "teacher_id": u.get("teacher_id"), "groups": groups, "subgroup": u.get("subgroup"),
                        "hours": u.get("hours"), "variants": masked, "duration": dur, "online": online, "need": need,
                        "need_source": source, "kinds": nd.get("room_kinds") or UNIT_ROOM_KINDS.get(u.get("kind") or "", []),
                        "room_ids": nd.get("room_ids")})
    return out, excluded


def subgroups(problem: dict) -> dict[int, list[int]]:
    """The subgroups of each group that some unit or obstacle names: a group's cells are None (the whole group) and these."""
    subs: dict[int, set[int]] = {}
    for u in problem["units"]:
        for g in u.get("groups") or []:
            subs.setdefault(g, set())
            if u.get("subgroup"):
                subs[g].add(u["subgroup"])
    for o in problem.get("obstacles") or []:
        for g, s in o["groups"]:
            subs.setdefault(g, set())
            if s:
                subs[g].add(s)
    return {g: sorted(s) for g, s in subs.items()}


def room_fits(m: dict, room: dict) -> bool:
    """H4 and H5: capacity, kind, schedulable, a listed room, a dedicated room only for a unit that lists it."""
    listed = m["room_ids"] is not None and room["id"] in m["room_ids"]
    return (not m["online"] and bool(room.get("schedulable", 1)) and room["kind"] in m["kinds"]
            and (room.get("capacity") or 0) >= m["need"] and (m["room_ids"] is None or listed)
            and (not room.get("dedicated") or listed))


def _avail(problem: dict, subject: str, level: str) -> dict[tuple[int, int, int], int]:
    """(subject_id, weekday, period) -> week mask of the availability cells of a level."""
    out: dict[tuple[int, int, int], int] = {}
    for a in problem.get("availability") or []:
        if a["subject_type"] == subject and a["level"] == level:
            k = (a["subject_id"], a["weekday"], a["period"])
            out[k] = out.get(k, 0) | week_mask(a.get("weeks") or "all", problem["weeks"])
    return out


def _shift_periods(problem: dict, group: dict | None) -> set[int] | None:
    shift = (group or {}).get("shift")
    periods = problem["settings"]["shifts"].get(shift) if shift else None
    return set(periods) if periods else None


def _fixed(problem: dict) -> list[dict]:
    return problem["settings"].get("fixed_slots") or []


def _bits(items: list[dict]) -> int:
    out = 0
    for it in items:
        out |= ((1 << it["duration"]) - 1) << it["period"]
    return out


def _gaps(bits: int) -> int:
    return bits.bit_length() - (bits & -bits).bit_length() + 1 - bits.bit_count() if bits else 0


def lost_weeks(term: dict, holidays: Iterable[str], n: int) -> list[int]:
    """Per weekday (index 1..7; 0 unused) the bit mask of the term's weeks whose day of that weekday holds no lesson: a
    holiday, or a day before teaching_start or after teaching_end. The hours a placement yields are its week set without
    these (Checkpoint F, CORR-F1): the solver, the scorecard and the hours report share this definition."""
    first, last = date.fromisoformat(term["teaching_start"]), date.fromisoformat(term["teaching_end"])
    monday = first - timedelta(days=first.isoweekday() - 1)
    off = set(holidays)
    out = [0] * 8
    for wd in range(1, 8):
        for wk in range(n):
            day = monday + timedelta(days=7 * wk + wd - 1)
            if not first <= day <= last or day.isoformat() in off:
                out[wd] |= 1 << wk
    return out


def off_of(problem: dict, weekday: int) -> int:
    """The lost weeks of a weekday in a problem (none when the problem carries no ``off``, as in the unit tests)."""
    off = problem.get("off") or []
    return off[weekday] if 0 <= weekday < len(off) else 0


def _hours_cost(planned: int, form, settings: dict) -> int:
    """S10: academic hours by which a unit's planned hours miss its form hours beyond the tolerance. Planned: the weeks
    each placement actually holds (its week set without the lost weeks of its weekday, ``lost_weeks``) x pair hours x
    duration."""
    miss = abs(planned - float(form or 0)) - settings["hours_tolerance"]
    return math.ceil(miss - 1e-9) if miss > 1e-9 else 0


def _items(problem: dict, placements: list[dict]) -> tuple[list[dict], list[dict]]:
    """Placements and obstacles as one shape: key, weekday, periods, mask, teacher, groups (cells), room, online,
    meeting (None for an obstacle); and the problems of placements that do not name a known meeting once."""
    meetings, _ = meetings_of(problem)
    by_key = {m["key"]: m for m in meetings}
    n = problem["weeks"]
    future = future_mask(problem)
    out: list[dict] = []
    bad: list[dict] = []
    seen: set[str] = set()
    for p in placements:
        m = by_key.get(p["key"])
        if m is None or p["key"] in seen:
            bad.append({"code": "unknown_meeting" if m is None else "duplicate", "keys": [p["key"]], "slot": None, "weeks": None})
            continue
        seen.add(p["key"])
        out.append({"key": p["key"], "weekday": p["weekday"], "period": p["period"], "duration": p.get("duration") or m["duration"],
                    "mask": week_mask(p["weeks"], n), "teacher_id": m["teacher_id"],
                    "cells": [(g, m["subgroup"]) for g in m["groups"]], "room_id": p.get("room_id"), "online": m["online"], "meeting": m})
    for o in problem.get("obstacles") or []:
        out.append({"key": o["key"], "weekday": o["weekday"], "period": o["period"], "duration": o.get("duration") or 1,
                    "mask": week_mask(o["weeks"], n) & future, "teacher_id": o.get("teacher_id"),
                    "cells": [(g, s) for g, s in o["groups"]], "room_id": o.get("room_id"), "online": bool(o.get("online")), "meeting": None})
    return out, bad


def check(problem: dict, placements: list[dict]) -> list[dict]:
    """The independent checker (H1-H14, H16): every hard violation of the placements against the problem as
    {code, keys, slot: [weekday, period], weeks}. It shares only the week grammar, the pattern rule and the meeting
    list with the solver. Obstacles are checked only against placements, never against each other."""
    st, n = problem["settings"], problem["weeks"]
    items, out = _items(problem, placements)
    times = lesson_times(problem)
    gaps = breaks(times)
    rooms = {r["id"]: r for r in problem.get("rooms") or []}
    groups = {g["id"]: g for g in problem.get("groups") or []}
    subs = subgroups(problem)
    blocks = _blocks(problem)
    t_un, r_un = _avail(problem, "teacher", "unavailable"), _avail(problem, "room", "unavailable")
    locked = {x["key"]: x for x in problem.get("locked") or []}
    future = future_mask(problem)
    past = ((1 << n) - 1) & ~future

    def v(code, keys, wd=None, p=None, mask=None):
        out.append({"code": code, "keys": sorted(keys), "slot": None if wd is None else [wd, p],
                    "weeks": None if mask is None else week_text(mask, n)})

    for it in items:
        m = it["meeting"]
        if m is None:
            continue
        k, wd, p0, mask = it["key"], it["weekday"], it["period"], it["mask"]
        periods = range(p0, p0 + it["duration"])
        if wd not in st["days"]:
            v("day", [k], wd, p0)
        if it["duration"] != m["duration"] or p0 < 1 or p0 + it["duration"] - 1 > len(times):
            v("duration", [k], wd, p0)
        if mask not in m["variants"]:
            v("pattern", [k], wd, p0, mask)
        if mask & past:
            v("past", [k], wd, p0, mask & past)
        if k in locked:
            lk = locked[k]
            # a repair keeps a lock in its future weeks only, as the solver does
            if (lk["weekday"], lk["period"], week_mask(lk["weeks"], n) & future, lk.get("room_id")) != (wd, p0, mask, it["room_id"]):
                v("locked", [k], wd, p0)
        for g in m["groups"]:
            allowed = _shift_periods(problem, groups.get(g))
            if allowed is not None and not set(periods) <= allowed:
                v("shift", [k], wd, p0)
            if blocks.get(("group", g), 0) & mask:
                v("block", [k], wd, p0, blocks[("group", g)] & mask)
        for f in _fixed(problem):
            if f["weekday"] == wd and f["period"] in periods and (f.get("groups") is None or set(f["groups"]) & set(m["groups"])):
                v("fixed_slot", [k], wd, f["period"])
        if m["teacher_id"]:
            if blocks.get(("teacher", m["teacher_id"]), 0) & mask:
                v("block", [k], wd, p0, blocks[("teacher", m["teacher_id"])] & mask)
            for p in periods:
                if t_un.get((m["teacher_id"], wd, p), 0) & mask:
                    v("teacher_unavailable", [k], wd, p, t_un[(m["teacher_id"], wd, p)] & mask)
        room = rooms.get(it["room_id"]) if it["room_id"] is not None else None
        if m["online"]:
            if it["room_id"] is not None:
                v("room_fit", [k], wd, p0)
        elif room is None:
            v("no_room", [k], wd, p0)
        else:
            if (room.get("capacity") or 0) < m["need"]:
                v("capacity", [k], wd, p0)
            elif not room_fits(m, room):
                v("room_fit", [k], wd, p0)
            if blocks.get(("room", room["id"]), 0) & mask:
                v("block", [k], wd, p0, blocks[("room", room["id"])] & mask)
            for p in periods:
                if r_un.get((room["id"], wd, p), 0) & mask:
                    v("room_unavailable", [k], wd, p, r_un[(room["id"], wd, p)] & mask)

    def building(it):
        r = rooms.get(it["room_id"]) if not it["online"] and it["room_id"] is not None else None
        return r["building_id"] if r else None

    # resources by (weekday, kind, id); a group bucket holds the items of every cell of the group
    res: dict[tuple, list[dict]] = {}
    for it in items:
        keys = [("teacher", it["teacher_id"])] if it["teacher_id"] else []
        keys += [("group", g) for g in sorted({g for g, _ in it["cells"]})]
        if it["room_id"] is not None and not it["online"]:
            keys.append(("room", it["room_id"]))
        for kk in keys:
            res.setdefault((it["weekday"], *kk), []).append(it)
    travel = st["travel_default_min"]
    for (wd, what, rid), its in res.items():
        for i, a in enumerate(its):
            for b in its[i + 1:]:
                if (a["meeting"] is None and b["meeting"] is None) or not a["mask"] & b["mask"] or (what == "group" and not _groups_meet(
                        [c for c in a["cells"] if c[0] == rid], [c for c in b["cells"] if c[0] == rid])):
                    continue
                ra, rb = range(a["period"], a["period"] + a["duration"]), range(b["period"], b["period"] + b["duration"])
                if set(ra) & set(rb):
                    v(f"{what}_clash", [a["key"], b["key"]], wd, max(ra[0], rb[0]), a["mask"] & b["mask"])
                elif what != "room":
                    first, second = (a, b) if ra[-1] < rb[0] else (b, a)
                    end = first["period"] + first["duration"] - 1
                    ba, bb = building(first), building(second)
                    if (second["period"] == end + 1 and ba is not None and bb is not None and ba != bb
                            and gaps[end - 1] < travel):
                        v("travel", [a["key"], b["key"]], wd, second["period"], a["mask"] & b["mask"])
    # H11, H12: pairs per weekday of a teacher and of each group cell, auditorium hours per week of each group cell
    def over(its, limit, code, wd=None, per=1):
        """A day counts the distinct pairs taken (two rows in one pair are one pair of the person's day), a week the hours."""
        load = [0] * n
        mine = [0] * n
        for w in range(n):
            here = [it for it in its if it["mask"] >> w & 1]
            mine[w] = sum(it["meeting"] is not None for it in here)
            if wd is not None:
                load[w] = _bits(here).bit_count()
            else:
                load[w] = sum(it["duration"] * per for it in here)
        bad = sum(1 << w for w in range(n) if load[w] > limit and mine[w])
        if bad:
            v(code, [it["key"] for it in its if it["meeting"] is not None and it["mask"] & bad], wd, None, bad)

    by_day: dict[tuple, list[dict]] = {}
    by_week: dict[tuple, list[dict]] = {}
    for it in items:
        if it["teacher_id"]:
            by_day.setdefault(("t", it["teacher_id"], it["weekday"]), []).append(it)
            by_week.setdefault(("t", it["teacher_id"]), []).append(it)
        for g in sorted({g for g, _ in it["cells"]}):
            mine = {s for gg, s in it["cells"] if gg == g}
            for cell in [None, *subs.get(g, [])]:
                if None in mine or cell in mine:
                    by_day.setdefault(("g", g, cell, it["weekday"]), []).append(it)
                    by_week.setdefault(("g", g, cell), []).append(it)
    for key, its in by_day.items():
        if key[0] == "t":
            over(its, st["max_pairs_day_teacher"], "day_limit_teacher", key[2])
        else:
            over(its, st["max_pairs_day_group"], "day_limit_group", key[3])
    for key, its in by_week.items():
        if key[0] == "g":
            over(its, st["max_week_hours_group"], "week_hours", None, st["pair_hours"])
        elif st.get("max_week_pairs_teacher"):
            over(its, st["max_week_pairs_teacher"], "week_pairs_teacher")
    return sorted(out, key=lambda x: (x["code"], x["keys"], x["slot"] or [0, 0]))


def scorecard(problem: dict, placements: list[dict]) -> dict:
    """The soft components of a set of placements, recomputed from scratch with the definitions the solver keeps
    incrementally: value (in the component's unit) and cost (value x weight), their total ``soft``, and coverage."""
    st, n = problem["settings"], problem["weeks"]
    w = st["weights"]
    items, _ = _items(problem, placements)
    rooms = {r["id"]: r for r in problem.get("rooms") or []}
    groups = {g["id"]: g for g in problem.get("groups") or []}
    subs = subgroups(problem)
    und = _avail(problem, "teacher", "undesired")
    meetings, excluded = meetings_of(problem)
    ref = {x["key"]: x for x in problem.get("reference") or []}
    repair = bool(problem.get("repair"))
    val = dict.fromkeys(("group_window", "teacher_window", "same_day_course", "undesired", "saturday", "late_pair",
                         "room_waste_10", "foreign_building", "hours_miss", "stability_time", "stability_weeks",
                         "stability_room", "move_repair"), 0)
    # windows: per resource, weekday and week, the empty pairs between two pairs (a group: per cell, as in check)
    profile: dict[tuple, list[int]] = {}
    courses: dict[tuple, list[int]] = {}
    for it in items:
        bits = ((1 << it["duration"]) - 1) << (it["period"] - 1)
        keys = [("teacher_window", it["teacher_id"])] if it["teacher_id"] else []
        for g in sorted({g for g, _ in it["cells"]}):
            mine = {s for gg, s in it["cells"] if gg == g}
            keys += [("group_window", (g, c)) for c in [None, *subs.get(g, [])] if None in mine or c in mine]
        for comp, r in keys:
            pr = profile.setdefault((comp, r, it["weekday"]), [0] * n)
            for wk in range(n):
                if it["mask"] >> wk & 1:
                    pr[wk] |= bits
            if comp == "group_window" and it["meeting"] is not None and it["meeting"]["course_id"] is not None:
                lst = courses.setdefault((r, it["weekday"], it["meeting"]["course_id"]), [])
                val["same_day_course"] += sum((it["mask"] & x).bit_count() for x in lst)
                lst.append(it["mask"])
    for (comp, _, _), pr in profile.items():
        val[comp] += sum(_gaps(b) for b in pr)
    planned: dict[int, int] = {}
    for it in items:
        m = it["meeting"]
        if m is None:
            continue
        weeks = it["mask"].bit_count()
        held = (it["mask"] & ~off_of(problem, it["weekday"])).bit_count()
        planned[m["unit_id"]] = planned.get(m["unit_id"], 0) + held * st["pair_hours"] * it["duration"]
        if it["weekday"] == 6:
            val["saturday"] += weeks * it["duration"]
        if any(_shift_periods(problem, groups.get(g)) is None for g in m["groups"]):
            val["late_pair"] += weeks * sum(1 for p in range(it["period"], it["period"] + it["duration"]) if p > LATE_AFTER)
        if m["teacher_id"]:
            val["undesired"] += sum((und.get((m["teacher_id"], it["weekday"], p), 0) & it["mask"]).bit_count()
                                    for p in range(it["period"], it["period"] + it["duration"]))
        room = rooms.get(it["room_id"]) if it["room_id"] is not None else None
        if room is not None and not m["online"]:
            val["room_waste_10"] += max(0, (room.get("capacity") or 0) - m["need"]) // 10
            val["foreign_building"] += sum(1 for g in m["groups"] if (groups.get(g) or {}).get("home_building_id")
                                           not in (None, room["building_id"]))
        r = ref.get(it["key"])
        if r is not None:
            moved = (r["weekday"], r["period"]) != (it["weekday"], it["period"])
            reweek = week_mask(r["weeks"], n) & future_mask(problem) != it["mask"]
            reroom = not m["online"] and r.get("room_id") != it["room_id"]
            val["stability_time"] += moved
            val["stability_weeks"] += reweek
            val["stability_room"] += reroom
            val["move_repair"] += repair and (moved or reweek or reroom)
    units = {u["id"]: u for u in problem["units"]}
    for uid in sorted({m["unit_id"] for m in meetings}):
        val["hours_miss"] += _hours_cost(planned.get(uid, 0), units[uid].get("hours"), st)
    # the hours over every unit of the problem, as hours_report counts them (BR-T1): an excluded unit plans nothing
    flagged = sum(abs(planned.get(uid, 0) - float(u.get("hours") or 0)) > st["hours_tolerance"] for uid, u in units.items())
    comps = {k: {"value": x, "cost": x * w[k]} for k, x in val.items()}
    placed = len({p["key"] for p in placements} & {m["key"] for m in meetings})
    return {"components": comps, "soft": sum(c["cost"] for c in comps.values()), "placed": placed,
            "unplaced": len(meetings) - placed, "excluded": len(excluded),
            "coverage": placed * 1000 // len(meetings) if meetings else 1000,
            "hours": {"flagged": flagged, "form_h": sum(float(u.get("hours") or 0) for u in units.values()), "planned_h": sum(planned.values())}}


def hours_report(problem: dict, placements: list[dict], term: dict, holidays: Iterable[str], lessons: list[dict] | None = None) -> dict:
    """Planned against form hours per unit, with the reason of every difference, and the totals per course, teacher and
    group. Planned = the teaching weeks of each placement whose day is in the term and not a holiday x pair hours x
    duration; once published, the unit's lessons instead (``lessons``: unit_id, status, academic_hours)."""
    st, n = problem["settings"], problem["weeks"]
    meetings, excluded = meetings_of(problem)
    needs = {x["unit_id"]: x for x in problem.get("needs") or []}
    by_key = {p["key"]: p for p in placements}
    lost_of = lost_weeks(term, holidays, n)
    real: dict[int, list[dict]] = {}
    for x in lessons or []:
        real.setdefault(x["unit_id"], []).append(x)
    lines = []
    for u in sorted(problem["units"], key=lambda x: x["id"]):
        mine = [m for m in meetings if m["unit_id"] == u["id"]]
        reasons: list[str] = []
        planned = 0.0
        lost = False                                    # a meeting's week that falls on a holiday or outside the term
        for m in mine:
            p = by_key.get(m["key"])
            if p is None:
                if "unplaced" not in reasons:
                    reasons.append("unplaced")
                continue
            mask, gone = week_mask(p["weeks"], n), lost_of[p["weekday"]] if 1 <= p["weekday"] <= 7 else 0
            planned += (mask & ~gone).bit_count() * st["pair_hours"] * m["duration"]
            lost = lost or bool(mask & gone)
        if u["id"] in real:                             # published: the lessons themselves; the placements still say why
            done = [x for x in real[u["id"]] if x["status"] != "cancelled"]
            planned = float(sum(x.get("academic_hours") or 0 for x in done))
            if len(done) < len(real[u["id"]]):
                reasons.append("cancelled")
        if lost:
            reasons.append("holidays")
        form = float(u.get("hours") or 0)
        delta = round(planned - form, 2)
        if not mine:
            reasons.append(next((x["code"] for x in excluded if x["unit_id"] == u["id"]), "no_hours"))
        elif delta and not reasons:
            if needs.get(u["id"], {}).get("pattern"):
                reasons.append("pattern_override")
            elif any(len(m["variants"]) > 1 and week_mask("odd", n) in m["variants"] for m in mine):
                reasons.append("fortnight_rounding")
            else:
                reasons.append("block_rounding")
        lines.append({"unit_id": u["id"], "course_id": u.get("course_id"), "teacher_id": u.get("teacher_id"),
                      "groups": sorted(set(u.get("groups") or [])), "form_h": form, "planned_h": planned, "delta": delta,
                      "reasons": reasons, "flagged": abs(delta) > st["hours_tolerance"]})

    def total(key):
        acc: dict = {}
        for x in lines:
            for k in (x[key] if key == "groups" else [x[key]]):
                a = acc.setdefault(k, {"id": k, "form_h": 0.0, "planned_h": 0.0})
                a["form_h"] += x["form_h"]
                a["planned_h"] += x["planned_h"]
        return [acc[k] for k in sorted(acc, key=lambda v: (v is None, v or 0))]

    return {"units": lines, "courses": total("course_id"), "teachers": total("teacher_id"), "groups": total("groups"),
            "flagged": sum(x["flagged"] for x in lines)}


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


# ---------------------------------------------------------------- the builder's service rules (Task 48, slice 2)
AVAIL_LEVELS = ("unavailable", "undesired", "preferred")
MODES = ("in_person", "online")
SPLITS = ("whole", "split")
MAX_DURATION = 4                          # pairs of one meeting
TERM_KEYS = ("practice", "reserved_weeks", "fixed_slots", "online")      # per-term confirmations (tt_terms.confirmed)
ROOM_CODES = ("no_room", "capacity", "room_fit", "room_clash", "room_unavailable", "travel")


def term_weeks(term: dict | None) -> int:
    """The teaching weeks of a term: week 1 holds teaching_start, the last one teaching_end; 0 without valid dates."""
    try:
        first, last = date.fromisoformat(term["teaching_start"]), date.fromisoformat(term["teaching_end"])  # type: ignore[index]
    except (TypeError, ValueError, KeyError):
        return 0
    return week_no(last, first) if last >= first else 0


def pair_span(times: list[list[str]], period: int, duration: int) -> tuple[str, str] | None:
    """Clock times of ``duration`` pairs from pair ``period`` (1-based); None off the bell schedule."""
    if period < 1 or duration < 1 or period + duration - 1 > len(times):
        return None
    return times[period - 1][0], times[period + duration - 2][1]


def pairs_of(times: list[list[str]], start: str, end: str) -> tuple[int, int] | None:
    """(first pair, number of pairs) a clock-time row overlaps: a manual row as an obstacle of the builder."""
    hit = [i + 1 for i, (a, b) in enumerate(times) if a < end and start < b]
    return (hit[0], hit[-1] - hit[0] + 1) if hit else None


def weekly_pairs(units: list[dict], settings: dict, n: int) -> int:
    """A teacher's pairs in an average teaching week: the form hours of their units over pair hours and weeks, rounded up."""
    hours = sum(float(u.get("hours") or 0) for u in units if (u.get("hours") or 0) > 0)
    return math.ceil(hours / (settings["pair_hours"] * n) - 1e-9) if n > 0 and hours > 0 else 0


def availability_input(cells, days: list[int], periods: int, n: int) -> tuple[list[dict], dict | None]:
    """A teacher's or a room's whole grid from a request: one cell per (weekday, period) of the teaching week, a level, a
    week set (default all) and an optional note."""
    bad = E("Məşğulluq cədvəlinin xanası düzgün deyil")
    if not isinstance(cells, list) or len(cells) > len(days) * periods:
        return [], bad
    out, seen = [], set()
    for x in cells:
        if not isinstance(x, dict):
            return [], bad
        wd, p, level, weeks, note = x.get("weekday"), x.get("period"), x.get("level"), x.get("weeks", "all"), x.get("note")
        if (type(wd) is not int or wd not in days or type(p) is not int or not 1 <= p <= periods or level not in AVAIL_LEVELS
                or (note is not None and not isinstance(note, str))):
            return [], bad
        if not isinstance(weeks, str) or not week_mask(weeks, n):
            return [], E("Xananın həftələri düzgün deyil: bütün, tək və ya cüt həftələri, yaxud 1-8, 10 kimi nömrələri seçin")
        if (wd, p) in seen:
            return [], E("Eyni xana iki dəfə yazılıb")
        seen.add((wd, p))
        out.append({"weekday": wd, "period": p, "level": level, "weeks": week_text(week_mask(weeks, n), n),
                    "note": " ".join((note or "").split())[:200] or None})
    return sorted(out, key=lambda c: (c["weekday"], c["period"])), None


def availability_feedback(cells: list[dict], pairs: int, settings: dict, days: int, periods: int) -> dict:
    """The live meter and the cap (D18): at most ``availability_cap_pct`` % of the teaching cells unavailable, and free
    cells at least ``availability_load_factor_pct`` % of the weekly pairs. ``over_cap``: cells beyond the cap (0: within)."""
    total = days * periods
    un = sum(1 for c in cells if c["level"] == "unavailable")
    needed = math.ceil(pairs * settings["availability_load_factor_pct"] / 100 - 1e-9)
    over = max(0, un - total * settings["availability_cap_pct"] // 100, needed - (total - un))
    return {"cells": total, "unavailable": un, "unavailable_pct": un * 100 // total if total else 0, "free_cells": total - un,
            "weekly_pairs": pairs, "needed_cells": needed, "over_cap": over}


def needs_input(body: dict, unit: dict, settings: dict, n: int, rooms: set[int]) -> tuple[dict, dict | None]:
    """What a unit needs from a room and a week (tt_unit_needs) from a request body; absent keys keep the default."""
    bad = E("Vahidin tələbləri düzgün yazılmayıb")
    kinds, ids, need, reason = body.get("room_kinds"), body.get("room_ids"), body.get("need"), body.get("need_reason")
    dur, mode, pat, split = body.get("duration", 1), body.get("mode", "in_person"), body.get("pattern"), body.get("split")
    if kinds is not None and not (isinstance(kinds, list) and 0 < len(kinds) <= len(ROOM_KINDS)
                                  and all(isinstance(k, str) and k in ROOM_KINDS for k in kinds) and len(set(kinds)) == len(kinds)):
        return {}, bad
    if ids is not None and not (isinstance(ids, list) and 0 < len(ids) <= 50 and all(type(r) is int for r in ids)
                                and len(set(ids)) == len(ids)):
        return {}, bad
    if ids is not None and not set(ids) <= rooms:
        return {}, E("Seçilən otaq tapılmadı")
    if need is not None and not (type(need) is int and 1 <= need <= 2000):
        return {}, bad
    reason = " ".join(reason.split()) if isinstance(reason, str) else ""
    if need is not None and not 3 <= len(reason) <= 300:
        return {}, E("Yer sayını dəyişdirdikdə səbəbini yazın")
    if type(dur) is not int or not 1 <= dur <= MAX_DURATION or mode not in MODES or (split is not None and split not in SPLITS):
        return {}, bad
    if pat is not None:
        if not (isinstance(pat, list) and 0 < len(pat) <= 10 and all(isinstance(w, str) and week_mask(w, n) for w in pat)):
            return {}, E("Həftələrin bölgüsü düzgün yazılmayıb")
        planned = sum(week_mask(w, n).bit_count() for w in pat) * settings["pair_hours"] * dur
        form = float(unit.get("hours") or 0)
        if abs(planned - form) > settings["hours_tolerance"]:
            return {}, E("Bu bölgü {planned} saat verir, Forma №3-də isə {hours} saatdır: fərq {tol} saatdan çox ola bilməz",
                         planned=planned, hours=f"{form:g}", tol=f"{settings['hours_tolerance']:g}")
        pat = [week_text(week_mask(w, n), n) for w in pat]
    return {"room_kinds": kinds, "room_ids": sorted(ids) if ids is not None else None, "need": need,
            "need_reason": reason if need is not None else None, "duration": dur, "mode": mode, "pattern": pat, "split": split}, None


def _line(code: str, level: str, blocks: list[str], found: int = 0, of: int = 0, samples=(), fix: str = "",
          confirm_key: str | None = None) -> dict:
    return {"code": code, "level": level, "blocks": blocks, "found": found, "of": of, "samples": list(samples)[:20],
            "fix": fix, "confirm_key": confirm_key}


def readiness(facts: dict, settings: dict, today: str) -> list[dict]:
    """The readiness checklist of a term (design §7.2; the lines of slice 2). Pure and total: a missing fact is a
    warning, never ok. ``blocks`` names what a line stops: "run" (a solver run) or "publish"."""
    conf = set(settings.get("confirmed") or [])
    need = set(settings.get("publish_requires") or [])
    out = []
    n = facts.get("weeks") or 0
    term_ok = bool(facts.get("term")) and 1 <= n <= 20
    blocks = ([] if term_ok else ["run", "publish"]) + ([] if "term_dates" in conf or "term_dates" not in need or not term_ok else ["publish"])
    # confirmed by the office, the term's weeks are what they are (a term that starts mid-week counts its partial weeks)
    out.append(_line("term_dates", "block" if blocks else ("warn" if "term_dates" not in conf else "ok"),
                     blocks, n, settings["weeks_expected"], fix="/admin/directory", confirm_key="term_dates"))
    out.append(_line("pattern", "block" if "pattern" in need and "pattern" not in conf else ("warn" if "pattern" not in conf else "ok"),
                     ["publish"] if "pattern" in need and "pattern" not in conf else [], fix="/admin/settings", confirm_key="pattern"))
    stored = facts.get("lesson_times") or []
    times = stored or DEFAULT_TIMES
    missing = sorted({p for ps in settings["shifts"].values() for p in ps if p > len(times)})
    blocks = (["run", "publish"] if missing else []) + (["publish"] if not missing and "lesson_times" in need and (not stored or "lesson_times" not in conf) else [])
    out.append(_line("lesson_times", "block" if blocks else ("warn" if "lesson_times" not in conf else "ok"), blocks,
                     len(stored), len(times), missing, fix="/admin/settings", confirm_key="lesson_times"))
    groups, no_shift = facts.get("groups") or [], facts.get("groups_no_shift") or []
    out.append(_line("group_shifts", "warn" if no_shift else "ok", [], len(no_shift), len(groups), no_shift, fix="/office/timetable"))
    rooms = [r for r in facts.get("rooms") or [] if r.get("schedulable", 1) and (r.get("capacity") or 0) > 0]
    over = facts.get("units_over_room") or []
    out.append(_line("rooms", "block" if not rooms else ("warn" if over else "ok"), [] if rooms else ["run"], len(over),
                     len(facts.get("units") or []), over, fix="/admin/directory"))
    unconf, pending = facts.get("teachers_unconfirmed") or [], facts.get("pending") or []
    due = facts.get("availability_due") or ""
    late = bool(unconf) and bool(due) and today > due
    out.append(_line("availability_late" if late else "availability", "warn" if unconf or pending else "ok", [], len(unconf),
                     len(facts.get("teachers") or []), unconf, fix="/dept/timetable"))
    if pending:
        out.append(_line("availability_pending", "warn", [], len(pending), len(facts.get("teachers") or []), pending, fix="/dept/timetable"))
    no_groups = facts.get("units_no_groups") or []
    out.append(_line("unit_groups", "warn" if no_groups else "ok", [], len(no_groups), len(facts.get("units") or []), no_groups,
                     fix="/admin/directory"))
    vac = facts.get("units_no_teacher") or []
    out.append(_line("vacancies", "warn" if vac else "ok", [], len(vac), len(facts.get("units") or []), vac, fix="/dept/timetable"))
    manual = facts.get("units_manual") or []
    if manual:                                      # a run keeps these units as they are: their rows stay obstacles
        out.append(_line("manual_rows", "warn", [], len(manual), len(facts.get("units") or []), manual, fix="/admin/timetable"))
    left = [k for k in ("shifts", "rooms", "limits", "travel", "fixed_slots", "weights", "availability_cap") if k not in conf]
    if "travel" in left and len({r.get("building_id") for r in rooms}) <= 1:
        left.remove("travel")                       # one building: no travel time to confirm
    out.append(_line("defaults", "warn" if left else "ok", [], len(left), 0, left, fix="/admin/timetable/build"))
    return out


def gate(lines: list[dict], action: str) -> list[dict]:
    """The readiness lines that stop ``action`` ("run" or "publish")."""
    return [x for x in lines if action in x["blocks"]]


def published_row(p: dict, times: list[list[str]], pair_hours: int) -> dict | None:
    """The timetable row values a placement publishes as (None when its pairs are off the bell schedule)."""
    span = pair_span(times, p["period"], p["duration"])
    if span is None:
        return None
    return {"meeting_key": p["meeting_key"], "unit_id": p["unit_id"], "weekday": p["weekday"], "period": p["period"],
            "start": span[0], "end": span[1], "weeks": p["weeks"], "room_id": p.get("room_id"),
            "academic_hours": min(MAX_HOURS, pair_hours * p["duration"])}


PUBLISHED_COLS = ("weekday", "period", "start", "end", "weeks", "room_id", "academic_hours")


def publish_plan(published: list[dict], wanted: list[dict]) -> dict:
    """Rows to keep, update, deactivate and insert, matched by meeting_key (manual rows, without a key, are never in it).
    ``published``: the active rows {id, meeting_key, ...PUBLISHED_COLS}; ``wanted``: published_row values. Sorted by key."""
    have = {r["meeting_key"]: r for r in published if r.get("meeting_key")}
    want = {w["meeting_key"]: w for w in wanted}
    out: dict[str, list] = {"unchanged": [], "update": [], "deactivate": [], "insert": []}
    for k in sorted(set(have) | set(want)):
        h, w = have.get(k), want.get(k)
        if h is None:
            out["insert"].append(w)
        elif w is None:
            out["deactivate"].append(h["id"])
        elif any(h.get(c) != w.get(c) for c in PUBLISHED_COLS) or h.get("unit_id") != w["unit_id"]:
            out["update"].append({**w, "id": h["id"]})
        else:
            out["unchanged"].append(h["id"])
    return out


def _mine(found: list[dict], key: str) -> list[dict]:
    return [v for v in found if key in v["keys"]]


def move_problems(problem: dict, placements: list[dict], to: dict) -> list[dict]:
    """The hard violations a placement would take part in at value ``to`` (key, weekday, period, duration, weeks,
    room_id), checked against its neighbourhood: the other placements and obstacles of its teacher, groups and room."""
    others = [p for p in placements if p["key"] != to["key"]]
    return _mine(check(problem, [*others, to]), to["key"])


def _room_busy(problem: dict, others: list[dict], room_id: int, wd: int, p: int, dur: int, mask: int) -> bool:
    n = problem["weeks"]
    span = set(range(p, p + dur))
    for o in [*others, *(problem.get("obstacles") or [])]:
        if (o.get("room_id") == room_id and o["weekday"] == wd and week_mask(o["weeks"], n) & mask
                and span & set(range(o["period"], o["period"] + (o.get("duration") or 1)))):
            return True
    return False


def options(problem: dict, placements: list[dict], key: str) -> list[dict]:
    """Every slot of the week for a placed meeting with its week set kept: [{weekday, period, room_id, reasons}], reasons
    the codes of the hard rules the slot breaks (empty: feasible, with the room it would take: the current one when it
    is free, else the smallest free one that fits). Time rules are checked first; rooms only for slots whose time is free."""
    meetings, _ = meetings_of(problem)
    m = next((x for x in meetings if x["key"] == key), None)
    cur = next((x for x in placements if x["key"] == key), None)
    if m is None or cur is None:
        return []
    n, times = problem["weeks"], lesson_times(problem)
    mask = week_mask(cur["weeks"], n)
    others = [x for x in placements if x["key"] != key]
    fitting = sorted((r for r in problem.get("rooms") or [] if room_fits(m, r)),
                     key=lambda r: (r["id"] != cur.get("room_id"), r.get("capacity") or 0, r["id"]))
    out = []
    for wd in problem["settings"]["days"]:
        for p in range(1, len(times) - m["duration"] + 2):
            cand = {**cur, "weekday": wd, "period": p, "duration": m["duration"], "room_id": None}
            found = [v["code"] for v in move_problems(problem, others, cand)]
            reasons = sorted({c for c in found if c not in ROOM_CODES or m["online"]})
            room = None
            if not reasons and not m["online"]:
                free = [r["id"] for r in fitting if not _room_busy(problem, others, r["id"], wd, p, m["duration"], mask)]
                reasons = ["no_room"] if not fitting else ["rooms_busy"] if not free else []
                for rid in free[:3]:
                    found = sorted({v["code"] for v in move_problems(problem, others, {**cand, "room_id": rid})})
                    if not found:
                        room, reasons = rid, []
                        break
                    reasons = found
            out.append({"weekday": wd, "period": p, "room_id": room, "reasons": reasons,
                        "current": (wd, p) == (cur["weekday"], cur["period"])})
    return out
