"""Intents the campus assistant answers from the university's own records (tasks/todo.md, Task 31): where a room is and
the way to it, and the person's next lesson with its room. Each answer names its source (``meta.source``); a question
that is none of these returns None and goes to the knowledge base."""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

from ...core.i18n import S
from ...legacy.r_learning import WEEKDAYS
from ...legacy.store import audit, iso, log_index, now
from . import domain as kb_domain
from . import repo as kb_repo
from ..facilities import domain as rooms_domain
from ..facilities import service as facilities
from ..timetable import service as timetable

NEXT_LESSON = re.compile(r"(növbəti|sonrakı|gələn|ilk)\s+dərs|next\s+(lesson|class)|следующ\w*\s+(занят|пар|урок)", re.I)
WHERE = re.compile(r"hara|harda|necə gedim|necə gedə|otaq|auditoriya|where|how do i get|room|где|как пройти|аудитори|кабинет", re.I)
STEP_FREE = re.compile(r"pilləsiz|lift|əlil|araba|wheelchair|step[- ]?free|лифт|коляск", re.I)
NUMBER = re.compile(r"(?<![\w-])(\d{2,4}[a-zA-Z]?)(?![\w-])")
LOOKAHEAD_DAYS = 14
OFFICE_HOURS = re.compile(r"qəbul saat|office hours|приёмн\w* час|часы приёма", re.I)
AZ_TEXT = re.compile(r"[əğıöüşçƏĞİÖÜŞÇ]")               # not "I": English has it too
CYRILLIC = re.compile(r"[а-яё]", re.I)
WEAK_SHARE = 0.35          # an Azerbaijani question that shares one word with an article must give that word a third of its weight


def campus_answer(c, user, masked: str, lang: str) -> dict:
    """The campus assistant's answer to a question (PII already masked): its own records first, then the knowledge base.
    Every answer that is not a greeting carries a source (``cites`` or ``meta.source``) or a handoff to a person
    (Task 32): one that would carry neither gets the handoff."""
    from ...legacy import engine, tutor                        # here: legacy imports this module
    out = answer(c, user, masked, lang)
    if out is None:
        query = tutor.expand_query(masked)
        hits = engine.INDEX["campus"].search(query, k=3)
        if hits and AZ_TEXT.search(masked) and not CYRILLIC.search(masked):
            matched, share = engine.coverage(engine.INDEX["campus"], query, hits[0]["id"])
            if matched < 2 and share < WEAK_SHARE:            # one shared word is no evidence (Task 32): hand over
                hits = []
        out = tutor.compose_campus(masked, hits, lang)
    offered = kb_repo.offered_codes(c)                         # a closed e-service has no button (Task 46)
    out["actions"] = [a for a in out["actions"] if a["type"] != "request" or a["code"] in offered]
    if out["meta"].get("no_source") and "free_application" not in offered:     # the text offers no closed service (TE46-7)
        out["text"] = S("Bu barədə universitetin bilik bazasında məlumat tapılmadı. Sualınızı dəstək xidmətinə ötürə bilərsiniz.", lang)
    if not (out["cites"] or out["meta"].get("source") or out["meta"].get("greeting") or any(a["type"] == "handoff" for a in out["actions"])):
        out["actions"] = [{"type": "handoff", "label": S("Dəstək xidmətinə ötür", lang)}, *out["actions"]]
    return out


def answer(c, user, question: str, lang: str) -> dict | None:
    """{text, cites, actions, meta} when the question is about a room or the next lesson; None otherwise."""
    q = question.strip()
    if NEXT_LESSON.search(q):
        return _next_lesson(c, user, bool(STEP_FREE.search(q)), lang)
    if OFFICE_HOURS.search(q):
        return _office_hours(c, user, q, lang)
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
    rooms = facilities.rooms_for_search(c)
    found = set()
    for r in sorted(rooms, key=lambda r: -len(rooms_domain.room_key(r["code"]))):   # EK-121 before EK-12 (PY-E8)
        k = rooms_domain.room_key(r["code"])
        if k and k in key:
            found.add(r["id"])
            key = key.replace(k, "|")
    hits = [r for r in rooms if r["id"] in found]
    key = rooms_domain.room_key(question)
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
    lessons = timetable.lessons_of(c, user, today, last)
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
    room = facilities.room_code(c, x["room_id"]) if x.get("room_id") else None
    if room:
        lines += [S("Otaq: {room}", lang, room=room["code"]), "", *_way(c, room["code"], step_free, lang)]
    elif x["room"]:
        lines.append(S("Otaq: {room}", lang, room=x["room"]))
    return _out("\n".join(lines), "timetable", "next_lesson", _room_link(room["code"], lang) if room else [])


# ---------------------------------------------------------------- the knowledge base (Task 32)
def kb_list(c) -> list[dict]:
    """The articles, each with whether its review date has passed."""
    today = now().date().isoformat()
    return [{**a, "overdue": bool(a["review_at"] and a["review_at"] < today)} for a in kb_repo.articles(c)]


def kb_get(c, kid: int) -> dict | None:
    a = kb_repo.article(c, kid)
    return {"article": a, "versions": kb_repo.versions(c, kid)} if a else None


def kb_save(c, user, kid: int | None, body) -> tuple[str, object]:
    """('ok', article) | ('missing', None) | ('invalid', problem). Each save is a version; the search index of every
    worker takes it on its next request (published: the new text; a draft or an archived one: out of the index)."""
    v, problem = kb_domain.kb_input(body, kb_repo.request_codes(c))
    if problem:
        return "invalid", problem
    at = iso(now())
    if kid is None:
        kid = kb_repo.insert(c, v, user["id"], at)
    else:
        old = kb_repo.article(c, kid)
        if not old:
            return "missing", None
        if not kb_repo.has_versions(c, kid):                  # an article from the seed: its first state is kept too
            kb_repo.add_version(c, old, old["updated_by"], old["updated_at"] or at)
        kb_repo.update(c, kid, v, user["id"], at)
    a = kb_repo.article(c, kid)
    kb_repo.add_version(c, a, user["id"], at)
    log_index(c, "campus", [kid], "upsert" if a["status"] == "published" else "delete")
    audit(c, user["id"], "kb_save", "kb", f"#{kid} v{a['version']} {a['status']}: {a['heading'][:80]}")
    return "ok", a


def handoff(c, user, message_id: int) -> tuple[str, object]:
    """A support ticket from an assistant answer that found no source, with the conversation up to it; once per answer
    (asking again returns the same ticket). ('ok', ticket id) | ('missing', None)."""
    m = kb_repo.campus_message(c, message_id, user["id"])
    if not m:
        return "missing", None
    meta = json.loads(m["meta"] or "{}")
    if meta.get("handoff"):
        return "ok", meta["handoff"]
    talk = kb_repo.campus_before(c, user["id"], message_id)
    question = next((x["content"] for x in reversed(talk) if x["role"] == "user"), "")
    body = "\n\n".join(f"{'İstifadəçi' if x['role'] == 'user' else 'Köməkçi'}: {x['content']}" for x in talk)
    from ...legacy.r_support import create_ticket           # here: legacy routes import this module's routes
    tid = create_ticket(c, user, "university", "normal", ("Kampus köməkçisi: " + " ".join(question.split()))[:140],
                        body[:4000], "/chat")
    kb_repo.set_message_meta(c, message_id, json.dumps({**meta, "handoff": tid}, ensure_ascii=False))
    return "ok", tid


def _office_hours(c, user, question: str, lang: str) -> dict:
    """The office hours of the student's teachers (Task 34), only the teacher named in the question when one is."""
    from ..qa import office_hours
    people = office_hours.teachers(c, user) if user["role"] == "student" else [{"id": user["id"], "full_name": user["full_name"]}]
    low = question.lower()
    named = [p for p in people if any(len(w) > 2 and w.lower() in low for w in p["full_name"].split())]
    lines = []
    for p in named or people:
        ranges = office_hours.hours_of(c, p["id"])
        if not ranges:
            lines.append(f"**{p['full_name']}**: " + S("qəbul saatı təyin olunmayıb", lang))
            continue
        lines.append(f"**{p['full_name']}**")
        lines += [f"- {S(WEEKDAYS[h['weekday']], lang)}, {h['start']}–{h['end']} · {h['place'] or h['online_url']}" for h in ranges]
    if not lines:
        lines = [S("Fənlərinizin müəllimləri tapılmadı.", lang)]
    return _out("\n".join(lines), "office_hours", "office_hours", [{"type": "link", "label": S("Qəbul saatına yazıl", lang), "href": "/office-hours"}])
