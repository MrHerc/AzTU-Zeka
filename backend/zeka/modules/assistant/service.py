"""Intents the campus assistant answers from the university's own records (tasks/todo.md, Task 31): where a room is and
the way to it, and the person's next lesson with its room. Each answer names its source (``meta.source``); a question
that is none of these returns None and goes to the knowledge base."""
from __future__ import annotations

import re
from datetime import date, timedelta

from ...core.i18n import S
from ...legacy.r_learning import WEEKDAYS
from ...legacy.store import now
from ..facilities import domain as rooms_domain
from ..facilities import repo as rooms_repo
from ..facilities import service as facilities
from ..timetable import repo as timetable_repo

NEXT_LESSON = re.compile(r"(növbəti|sonrakı|gələn|ilk)\s+dərs|next\s+(lesson|class)|следующ\w*\s+(занят|пар|урок)", re.I)
WHERE = re.compile(r"hara|harda|necə gedim|necə gedə|otaq|auditoriya|where|how do i get|room|где|как пройти|аудитори|кабинет", re.I)
STEP_FREE = re.compile(r"pilləsiz|lift|əlil|araba|wheelchair|step[- ]?free|лифт|коляск", re.I)
NUMBER = re.compile(r"(?<![\w-])(\d{2,4}[a-zA-Z]?)(?![\w-])")
LOOKAHEAD_DAYS = 14


def answer(c, user, question: str, lang: str) -> dict | None:
    """{text, cites, actions, meta} when the question is about a room or the next lesson; None otherwise."""
    q = question.strip()
    if NEXT_LESSON.search(q):
        return _next_lesson(c, user, bool(STEP_FREE.search(q)), lang)
    found = find_rooms(c, q)
    if len(found) == 1:
        return _room(c, found[0], bool(STEP_FREE.search(q)), lang)
    if len(found) > 1:
        codes = ", ".join(sorted(r["code"] for r in found)[:8])
        return _out(S("Bu ada uyğun bir neçə otaq var: {codes}. Otağın kodunu yazın.", lang, codes=codes), "rooms", "room")
    return None


def find_rooms(c, question: str) -> list[dict]:
    """The rooms a question names: by code, then by name; a bare number counts only in a question about a place."""
    key = rooms_domain.room_key(question)
    rooms = rooms_repo.rooms_for_search(c)
    hits = [r for r in rooms if rooms_domain.room_key(r["code"]) in key]
    if not hits:
        hits = [r for r in rooms if r["name"] and len(r["name"]) > 3 and rooms_domain.room_key(r["name"]) in key]
    if not hits and WHERE.search(question):
        numbers = {n.lower() for n in NUMBER.findall(question)}
        hits = [r for r in rooms if str(r["number"]).lower() in numbers]
    return hits


def _out(text: str, source: str, intent: str, actions: list | None = None) -> dict:
    return {"text": text, "cites": [], "actions": actions or [], "meta": {"source": source, "intent": intent}}


def _way(c, code: str, step_free: bool, lang: str) -> list[str]:
    r = facilities.route(c, code, None, step_free)
    if r is None:
        return []
    if r["missing"]:
        return [S(facilities.MISSING[r["missing"]], lang)]
    head = S("Pilləsiz yol, təxminən {m} m:", lang, m=r["length_m"]) if step_free else S("Yol, təxminən {m} m:", lang, m=r["length_m"])
    return [head] + [f"{i}. {S(t, lang, **p)}" for i, (t, p) in enumerate(r["steps"], 1)]


def _room_link(code: str, lang: str) -> list[dict]:
    return [{"type": "link", "label": S("Otağın səhifəsi", lang), "href": f"/r/{code}"}]


def _room(c, room: dict, step_free: bool, lang: str) -> dict:
    where = S("**{code}** · {building}, mərtəbə: {floor}", lang, code=room["code"], building=room["building"],
              floor=room["floor"] if room["floor"] is not None else "—")
    name = f" · {room['name']}" if room["name"] else ""
    return _out("\n".join([where + name, "", *_way(c, room["code"], step_free, lang)]), "rooms", "room", _room_link(room["code"], lang))


def next_lesson(c, user) -> dict | None:
    """The lesson in progress or the next one in the person's timetable (a student's units, a teacher's lessons) within
    two weeks, cancelled ones left out."""
    t = now()
    today, hhmm = t.date().isoformat(), t.strftime("%H:%M")
    last = (t.date() + timedelta(days=LOOKAHEAD_DAYS)).isoformat()
    if user["role"] == "student":
        lessons = timetable_repo.student_lessons(c, user["id"], today, last)
    elif user["role"] in ("teacher", "dept_head"):
        lessons = timetable_repo.teacher_lessons(c, user["id"], today, last)
    else:
        return None
    return next((x for x in lessons if x["status"] != "cancelled" and (x["day"], x["end"]) > (today, hhmm)), None)


def _next_lesson(c, user, step_free: bool, lang: str) -> dict:
    x = next_lesson(c, user)
    if not x:
        return _out(S("Yaxın iki həftədə cədvəlinizdə dərs yoxdur.", lang), "timetable", "next_lesson")
    t = now()
    day = date.fromisoformat(x["day"])
    if x["day"] == t.date().isoformat():
        when = S("İndi gedir", lang) if x["start"] <= t.strftime("%H:%M") else S("Bu gün", lang)
    else:
        when = f"{S(WEEKDAYS[day.isoweekday()], lang)}, {x['day']}"
    lines = [f"**{x['course']}** · {S(x['kind'] or '', lang)}", f"{when}, {x['start']}–{x['end']}"]
    room = rooms_repo.room_code(c, x["room_id"]) if x.get("room_id") else None
    if room:
        lines += [S("Otaq: {room}", lang, room=room["code"]), "", *_way(c, room["code"], step_free, lang)]
    elif x["room"]:
        lines.append(S("Otaq: {room}", lang, room=x["room"]))
    return _out("\n".join(lines), "timetable", "next_lesson", _room_link(room["code"], lang) if room else [])
