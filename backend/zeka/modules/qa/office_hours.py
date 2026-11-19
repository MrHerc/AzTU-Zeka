"""Office hours (tasks/todo.md, Task 34): a teacher's weekly ranges, the free slots a student of the teacher's courses
sees two weeks ahead, a booking of one slot (once: the database refuses the second), cancelling with a word to the
other side, both calendars (the iCal feed) and a reminder an hour or two before."""
from __future__ import annotations

import sqlite3
from datetime import timedelta

from ...core.i18n import S, T3
from ...legacy.store import audit, iso, notify, now
from . import domain, repo

TEACHERS = ("teacher", "dept_head")


def _today():
    return now().date()


def my_hours(c, user) -> list[dict]:
    return repo.hours_of(c, user["id"])


def add_hours(c, user, body) -> tuple[str, object]:
    v, problem = domain.hours_input(body)
    if problem:
        return "invalid", problem
    hid = repo.add_hours(c, user["id"], v, iso(now()))
    audit(c, user["id"], "office_hours_add", "office_hours", f"#{hid} {v['weekday']} {v['start']}-{v['end']}")
    return "ok", repo.hours_of(c, user["id"])


def drop_hours(c, user, hid: int) -> tuple[str, object]:
    """The range ends; its future bookings are cancelled and each student is told."""
    h = repo.hours(c, hid)
    if not h or h["teacher_id"] != user["id"] or not h["active"]:
        return "missing", None
    for b in repo.future_bookings_of_hours(c, hid, _today().isoformat()):
        _cancel(c, user, b)
    repo.drop_hours(c, hid)
    audit(c, user["id"], "office_hours_drop", "office_hours", f"#{hid}")
    return "ok", repo.hours_of(c, user["id"])


def teachers(c, user) -> list[dict]:
    return repo.teachers_of_student(c, user["id"], _today().isoformat()) if user["role"] == "student" else []


def _may_book_with(c, user, teacher_id: int) -> bool:
    return user["role"] == "student" and any(t["id"] == teacher_id for t in teachers(c, user))


def free(c, user, teacher_id: int) -> list[dict] | None:
    if not _may_book_with(c, user, teacher_id):
        return None
    t = now()
    last = (t.date() + timedelta(days=domain.BOOK_AHEAD_DAYS)).isoformat()
    return domain.free_slots(repo.hours_of(c, teacher_id), repo.booked_slots(c, teacher_id, t.date().isoformat(), last), t.date(), t.strftime("%H:%M"))


def book(c, user, body) -> tuple[str, object]:
    """('ok', booking) | ('missing') | ('invalid', why) | ('taken', why): the slot must be one of the free ones now."""
    h = repo.hours(c, body.integer("hours_id", lo=1) or 0)
    if not h or not h["active"] or not _may_book_with(c, user, h["teacher_id"]):
        return "missing", None
    day, start = body.text("day", 10), body.text("start", 5)
    topic = " ".join(body.text("topic", 400).split())[:300] or None
    slot = next((s for s in free(c, user, h["teacher_id"]) or [] if s["hours_id"] == h["id"] and s["day"] == day and s["start"] == start), None)
    if not slot:
        return "taken", T3("Bu vaxt artıq tutulub və ya keçib")
    if repo.open_bookings_with(c, user["id"], h["teacher_id"], _today().isoformat()) >= domain.MAX_OPEN_PER_TEACHER:
        return "invalid", T3("Bu müəllimlə ən çox iki gələcək görüşünüz ola bilər")
    try:
        bid = repo.add_booking(c, h, user["id"], day, start, slot["end"], topic, iso(now()))
    except sqlite3.IntegrityError:                       # booked by someone else between the check and the insert
        return "taken", T3("Bu vaxt artıq tutulub və ya keçib")
    notify(c, h["teacher_id"], "schedule", T3("Qəbul saatına yazılış"), f"{user['full_name']}: {day} {start}" + (f" · {topic[:60]}" if topic else ""),
           "/office-hours")
    audit(c, user["id"], "office_book", "office_booking", f"#{bid} {day} {start}")
    return "ok", repo.booking(c, bid)


def _cancel(c, user, b: dict):
    repo.cancel_booking(c, b["id"], user["id"], iso(now()))
    other = b["teacher_id"] if user["id"] == b["student_id"] else b["student_id"]
    notify(c, other, "schedule", T3("Qəbul saatı görüşü ləğv olundu"), f"{b['day']} {b['start']} · {user['full_name']}", "/office-hours")
    audit(c, user["id"], "office_cancel", "office_booking", f"#{b['id']} {b['day']} {b['start']}")


def cancel(c, user, bid: int) -> tuple[str, object]:
    b = repo.booking(c, bid)
    if not b or user["id"] not in (b["student_id"], b["teacher_id"]):
        return "missing", None
    if b["status"] != "booked" or (b["day"], b["end"]) <= (_today().isoformat(), now().strftime("%H:%M")):
        return "invalid", T3("Bu görüş artıq ləğv olunub və ya keçib")
    _cancel(c, user, b)
    return "ok", repo.booking(c, bid)


def mine(c, user) -> list[dict]:
    t = _today()
    return repo.bookings_for(c, user["id"], (t - timedelta(days=7)).isoformat(), (t + timedelta(days=domain.BOOK_AHEAD_DAYS)).isoformat())


def calendar_events(c, uid: int, first: str, last: str) -> list[dict]:
    """The person's bookings in the shape of the iCal feed's lessons (a distinct UID per booking)."""
    out = []
    for b in repo.bookings_for(c, uid, first, last):
        other = b["student"] if b["teacher_id"] == uid else b["teacher"]
        out.append({"id": b["id"], "uid": f"office-{b['id']}", "day": b["day"], "start": b["start"], "end": b["end"],
                    "status": "cancelled" if b["status"] == "cancelled" else "scheduled", "course": S("Qəbul saatı: {name}", "az", name=other), "kind": "",
                    "room": b["place"] or b["online_url"] or "", "note": b["topic"] or ""})
    return out


def remind(c, once) -> int:
    """The periodic reminder: each side of a booking that starts within two hours is told once."""
    t = now()
    sent = 0
    soon = t + timedelta(hours=2)
    last = soon.strftime("%H:%M") if soon.date() == t.date() else "23:59"      # a booking just after midnight waits for that day's runs
    for b in repo.bookings_starting(c, t.date().isoformat(), t.strftime("%H:%M"), last):
        if once(c, "office", b["id"], "soon"):
            for uid, other in ((b["student_id"], b["teacher"]), (b["teacher_id"], b["student"])):
                notify(c, uid, "schedule", T3("Qəbul saatı görüşü yaxınlaşır"), f"{b['start']} · {other}", "/office-hours")
            sent += 1
    return sent
