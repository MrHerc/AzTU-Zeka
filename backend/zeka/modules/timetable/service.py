"""Timetable rows, their conflicts, lessons made from them, cancelled and moved lessons, calendar feeds (Task 19)."""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, timedelta

from ...core import tenant
from ...core.web import an_id
from ...core.i18n import E, T3
from ...legacy.store import audit, iso, notify, now
from ..directory import domain as directory_rules
from ..directory import service as directory
from ..facilities import service as facilities
from . import domain, repo

FEED_PAST, FEED_AHEAD = 60, 200              # days of lessons a calendar feed carries


def _today() -> str:
    return now().date().isoformat()


def term(c, term_id: int | None) -> dict | None:
    return directory.get(c, "terms", term_id) if term_id else directory.current_term(c)


def _slot(r: dict, groups: dict[int, list[int]], idx: dict) -> dict:
    return {"id": r.get("id"), "weekday": r["weekday"], "start": r["start"], "end": r["end"], "weeks": r.get("weeks") or "all",
            "room": facilities.slot_room(idx, r.get("room")), "teacher_id": r.get("teacher_id"),
            "groups": [(g, r.get("subgroup")) for g in groups.get(r["unit_id"], [])] if r.get("unit_id") else []}


def _explain(c, found: list[dict], others: dict[int, dict]) -> list[dict]:
    names = repo.group_names(c, {g for x in found for g in x["groups"]})
    return [{"what": x["what"], "groups": [names.get(g, str(g)) for g in x["groups"]],
             **{k: others[x["id"]].get(k) for k in ("id", "course", "kind", "day", "start", "end", "room", "teacher")}} for x in found]


def row_clashes(c, cand: dict, term_id: int | None) -> list[dict]:
    """What a candidate row (weekday, start, end, weeks, room, unit_id, teacher_id, subgroup, id) clashes with in its term."""
    others = repo.term_rows(c, term_id, cand["weekday"])
    groups = repo.groups_of_units(c, sorted({r["unit_id"] for r in others if r["unit_id"]} | ({cand["unit_id"]} if cand["unit_id"] else set())))
    idx = facilities.room_index(c)
    found = domain.conflicts(_slot(cand, groups, idx), [_slot(o, groups, idx) for o in others])
    return _explain(c, found, {o["id"]: o for o in others})


def _week(day: str) -> tuple[int, int]:
    return date.fromisoformat(day).isocalendar()[:2]


def _unit_id(body) -> int | None:
    return an_id(body.get("unit_id"))


def create_row(c, user, body):
    """('ok', id) | ('invalid', reason) | ('conflict', clashes) | ('busy', None): the term's timetable is being published."""
    values, problem = domain.row_input(body)
    if not problem:
        problem = domain.times_problem(values["start"], values["end"])
    if problem:
        return "invalid", problem
    u = repo.unit(c, _unit_id(body) or 0)
    if not u or not u["active"]:
        return "invalid", E("Tədris vahidi tapılmadı")
    if repo.publishing(c, u["term_id"]):
        return "busy", None
    cand = {**values, "id": None, "unit_id": u["id"], "teacher_id": u["teacher"], "subgroup": u["subgroup"]}
    clashes = row_clashes(c, cand, u["term_id"])
    if clashes:
        return "conflict", clashes
    room_id = facilities.room_of(facilities.room_index(c), values["room"])
    rid = repo.insert_row(c, {**values, "course_id": u["course_id"], "kind": domain.KIND_LABEL[u["kind"]], "room_id": room_id,
                              "unit_id": u["id"]}, iso(now()))
    audit(c, user["id"], "timetable_create", "timetable", f"{rid} · {u['course']} · {values['weekday']} {values['start']}")
    return "ok", rid


def update_row(c, user, rid: int, body):
    """('ok', None) | ('missing', None) | ('invalid', reason) | ('conflict', clashes). Future lessons nobody recorded
    follow the row, except a moved one, which keeps its own day and time; a substitute stays on the lesson of its week.
    The students are told once, unless only the academic hours changed."""
    cur = repo.row_by_id(c, rid)
    if not cur or not cur["active"]:
        return "missing", None
    if repo.publishing(c, cur["term_id"]):
        return "busy", None
    values, problem = domain.row_input(body, partial=True)
    merged = {**cur, **values}
    problem = problem or domain.times_problem(merged["start"], merged["end"])
    if problem:
        return "invalid", problem
    clashes = row_clashes(c, merged, cur["term_id"])
    if clashes:
        return "conflict", clashes
    merged["room_id"] = facilities.room_of(facilities.room_index(c), merged["room"])
    changed = [k for k in ("weekday", "start", "end", "room", "weeks", "academic_hours") if merged[k] != cur[k]]
    if not changed:
        return "ok", None
    stamp = iso(now())
    repo.update_row(c, rid, merged, stamp)
    new = repo.row_by_id(c, rid)
    future = repo.future_lessons(c, rid, _today())
    moved = {x["id"] for x in future if (x["day"], x["start"]) != (x["slot_day"], x["slot_start"])}
    if {"weekday", "start", "weeks"} & set(changed):
        subs = {_week(x["slot_day"]): x["teacher_id"] for x in future if x["id"] not in moved and x["teacher_id"] != cur["teacher_id"]}
        repo.drop_lessons(c, [x["id"] for x in future if x["id"] not in moved])
        t = term(c, cur["term_id"])
        if t and cur["unit_id"]:
            make_lessons(c, [new], t, date.fromisoformat(_today()) + timedelta(days=1))
            for x in repo.future_lessons(c, rid, _today()):
                if x["id"] not in moved and _week(x["slot_day"]) in subs:
                    repo.set_lesson(c, x["id"], {"teacher_id": subs[_week(x["slot_day"])]}, stamp)
    else:
        for x in future:
            fields = {"academic_hours": new["academic_hours"]}
            if x["id"] not in moved:
                fields.update(end=new["end"], room=new["room"], room_id=new["room_id"])
            repo.set_lesson(c, x["id"], fields, stamp)
    if future and set(changed) - {"academic_hours"}:
        _tell(c, cur, _today(), T3("Dərs cədvəli dəyişdi: {course}", course=cur["course"]), "")
    audit(c, user["id"], "timetable_update", "timetable", f"{rid} · " + ", ".join(f"{k}: {cur[k]} → {merged[k]}" for k in changed))
    return "ok", None


def deactivate_row(c, user, rid: int) -> str:
    cur = repo.row_by_id(c, rid)
    if not cur or not cur["active"]:
        return "missing"
    if repo.publishing(c, cur["term_id"]):
        return "busy"
    repo.deactivate_row(c, rid, iso(now()))
    if repo.drop_future_lessons(c, rid, _today()):
        _tell(c, cur, _today(), T3("Dərs cədvəldən çıxarıldı: {course}", course=cur["course"]), "")
    audit(c, user["id"], "timetable_deactivate", "timetable", f"{rid} · {cur['course']}")
    return "ok"


def add_imported_lesson(c, unit_id: int, day: str, start: str, end: str | None, hours: int | None, kind: str | None) -> int:
    """A lesson the old system held and Zəka's timetable has not: made with the record's day and start (Task 38). Without
    an end or hours it is one pair: 2 academic hours of 45 minutes."""
    hours = hours or 2
    if not end:
        m = min(int(start[:2]) * 60 + int(start[3:]) + 45 * hours, 23 * 60 + 59)
        end = f"{m // 60:02d}:{m % 60:02d}"
    return repo.add_imported_lesson(c, unit_id, day, start, end, hours, kind, iso(now()))


def lessons_of(c, user, first: str, last: str) -> list[dict]:
    """A person's lessons between two days: a student's groups' and units', anyone else's own teaching (Checkpoint E,
    SF-E10: a teacher acting in another role still has their lessons)."""
    if user["role"] == "student":
        return repo.student_lessons(c, user["id"], first, last)
    return repo.teacher_lessons(c, user["id"], first, last)


def term_rows(c, term_id: int | None) -> list[dict]:
    """A term's active rows; a row a builder version published carries ``from``, the version's effective date (Task 48):
    its lessons are never made before it."""
    rs = repo.term_rows(c, term_id)
    eff = repo.effective_of(c, sorted({r["version_id"] for r in rs if r.get("version_id")}))
    return [{**r, "from": eff[r["version_id"]]} if r.get("version_id") in eff else r for r in rs]


def make_lessons(c, rows_: list[dict], t: dict, start_from: date | None = None) -> int:
    """The lessons of weekly rows in the term's teaching period; a slot that already has its lesson is left alone."""
    holidays = tenant.load(c)["calendar"]["holidays"]
    stamp = iso(now())
    values = []
    for r in rows_:
        if not r or not r["unit_id"]:
            continue
        first = start_from
        if r.get("from"):
            first = max(first, date.fromisoformat(r["from"])) if first else date.fromisoformat(r["from"])
        for d in domain.lesson_dates(r, t, holidays, first):
            day = d.isoformat()
            values.append((r["course_id"], day, r["start"], r["end"], r["kind"], r["room"], r["room_id"], r["unit_id"], r["teacher_id"],
                           r["academic_hours"], r["id"], day, r["start"], stamp))
    return repo.add_lessons(c, values)


def generate(c, user, term_id: int | None) -> tuple[str, dict | None]:
    t = term(c, term_id)
    if not t:
        return "missing", None
    rs = term_rows(c, t["id"])
    created = make_lessons(c, rs, t)
    audit(c, user["id"] if user else None, "lessons_made", "term", f"{t['code']} · {created}")
    return "ok", {"created": created, "rows": sum(1 for r in rs if r["unit_id"]), "without_unit": sum(1 for r in rs if not r["unit_id"]),
                  "term": {k: t[k] for k in ("id", "code", "name", "teaching_start", "teaching_end")}}


# ---------------------------------------------------------------- one lesson
def audience(c, unit_ids: list[int]) -> dict[int, tuple[list[int], int | None]]:
    """For other modules (the journal, Task 20): {unit id: (its group ids, its subgroup)}."""
    groups, subs = repo.groups_of_units(c, unit_ids), repo.unit_subgroups(c, unit_ids)
    return {u: (groups.get(u, []), subs.get(u)) for u in unit_ids}


def _students(c, les: dict, day: str) -> list[int]:
    aud = audience(c, [les["unit_id"]]) if les.get("unit_id") else {}
    return [s["id"] for s in repo.enrolled(c, les["course_id"], day) if domain.on_list(s, {**les, "day": day}, aud)]


def _tell(c, les: dict, day: str, title, body: str):
    ids = _students(c, les, day)
    if ids:
        notify(c, ids, "schedule", title, body, "/student/schedule")


def cancel_lesson(c, user, lid: int, reason: str) -> str:
    """'ok' | 'missing' | 'recorded' (attendance is already written) | 'cancelled' (already) | 'invalid'."""
    les = repo.lesson(c, lid)
    if not les:
        return "missing"
    if les["status"] == "cancelled":
        return "cancelled"
    if repo.has_attendance(c, lid):
        return "recorded"
    if not 3 <= len(reason) <= 300:
        return "invalid"
    repo.set_lesson(c, lid, {"status": "cancelled", "note": reason}, iso(now()))
    _tell(c, les, les["day"], T3("Dərs ləğv edildi: {course}", course=les["course"]), f"{les['day']} {les['start']} · {reason}")
    audit(c, user["id"], "lesson_cancel", "lesson", f"{lid} · {les['course']} · {les['day']} {les['start']} · {reason}")
    return "ok"


def move_lesson(c, user, lid: int, body):
    """('ok', None) | ('missing', None) | ('invalid', reason) | ('conflict', clashes) | ('recorded', None)."""
    les = repo.lesson(c, lid)
    if not les or les["status"] == "cancelled":
        return "missing", None
    if repo.has_attendance(c, lid):
        return "recorded", None
    day = body.get("day")
    if not isinstance(day, str) or directory_rules.date_problem("day", day):
        return "invalid", E("«{field}» sahəsində tarix İİİİ-AA-GG formatında olmalıdır", field="day")
    if day < _today():
        return "invalid", E("Dərs keçmiş tarixə köçürülə bilməz")
    values, problem = domain.row_input({"weekday": date.fromisoformat(day).isoweekday(), "weeks": "all", "academic_hours": 1,
                                        "start": body.get("start"), "end": body.get("end"),
                                        "room": body.get("room", les["room"])})
    if not problem:
        problem = domain.times_problem(values["start"], values["end"])
    if problem:
        return "invalid", problem
    others = [o for o in repo.lessons_on(c, day) if o["status"] != "cancelled" and o["id"] != lid]
    groups = repo.groups_of_units(c, sorted({o["unit_id"] for o in others if o["unit_id"]} | ({les["unit_id"]} if les["unit_id"] else set())))
    idx = facilities.room_index(c)
    u = repo.unit(c, les["unit_id"]) if les["unit_id"] else None
    cand = {"id": lid, "weekday": values["weekday"], "start": values["start"], "end": values["end"], "weeks": "all", "room": values["room"],
            "unit_id": les["unit_id"], "teacher_id": les["teacher_id"], "subgroup": u["subgroup"] if u else None}
    found = domain.conflicts(_slot(cand, groups, idx), [_slot({**o, "weekday": values["weekday"]}, groups, idx) for o in others])
    if found:
        return "conflict", _explain(c, found, {o["id"]: {**o, "day": day} for o in others})
    was = f"{les['day']} {les['start']}"
    repo.set_lesson(c, lid, {"day": day, "start": values["start"], "end": values["end"], "room": values["room"],
                             "room_id": facilities.room_of(idx, values["room"]), "note": f"{was} → {day} {values['start']}"}, iso(now()))
    _tell(c, les, day, T3("Dərsin vaxtı dəyişdi: {course}", course=les["course"]), f"{was} → {day} {values['start']}–{values['end']}")
    audit(c, user["id"], "lesson_move", "lesson", f"{lid} · {les['course']} · {was} → {day} {values['start']}")
    return "ok", None


# ---------------------------------------------------------------- calendar feeds
def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_feed(c, user) -> str:
    """A new secret feed token for the user; the one before stops working. The token is shown once."""
    token = secrets.token_urlsafe(24)
    repo.set_feed(c, user["id"], _hash(token), iso(now()))
    audit(c, user["id"], "calendar_feed", "user", "new")
    return token


def drop_feed(c, user) -> bool:
    gone = repo.drop_feed(c, user["id"])
    if gone:
        audit(c, user["id"], "calendar_feed", "user", "revoked")
    return gone


def has_feed(c, user) -> bool:
    return repo.has_feed(c, user["id"])


def feed_events(c, token: str) -> tuple[dict, list[dict]] | None:
    """(owner, lessons) of a feed token; None for an unknown or revoked token or a disabled account."""
    if not token or len(token) > 64:
        return None
    u = repo.feed_owner(c, _hash(token))
    if not u:
        return None
    today = now().date()
    first, last = (today - timedelta(days=FEED_PAST)).isoformat(), (today + timedelta(days=FEED_AHEAD)).isoformat()
    from ..qa import office_hours                              # bookings of office hours on both calendars (Task 34)
    if u["role"] == "student":
        return u, repo.student_lessons(c, u["id"], first, last) + office_hours.calendar_events(c, u["id"], first, last)
    if u["role"] in ("teacher", "dept_head"):
        return u, repo.teacher_lessons(c, u["id"], first, last) + office_hours.calendar_events(c, u["id"], first, last)
    return u, []
