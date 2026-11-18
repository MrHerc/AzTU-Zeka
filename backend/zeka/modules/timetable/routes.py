"""HTTP routes of the timetable (tasks/todo.md, Task 19): rows and their conflicts, making lessons, cancelling and
moving one lesson, and each person's calendar feed."""
from __future__ import annotations

from urllib.parse import urlsplit

from ...core import clock
from ...core.i18n import S
from ...core.security import LIMITS
from ...core.web import HTTPError, Response, json_resp
from ...legacy.common import BASE_URL, R
from ...legacy.store import now
from . import domain, repo, service


def _conflict(req, clashes):
    return json_resp({"error": S("Cədvəldə toqquşma var", req.lang), "conflicts": clashes}, 409)


def _int(req, name):
    v = req.query.get(name)
    return req.qint(name, 0, lo=1) if v not in (None, "") else None


def _with_groups(c, rs: list[dict]) -> list[dict]:
    groups = repo.groups_of_units(c, sorted({r["unit_id"] for r in rs if r["unit_id"]}))
    names = service._group_names(c, {g for v in groups.values() for g in v})
    return [{**r, "groups": [names[g] for g in groups.get(r["unit_id"], []) if g in names]} for r in rs]


@R("GET", "/api/timetable", perm="directory.read")
def list_rows(req):
    t = service.term(req.db, _int(req, "term_id"))
    rs = repo.listed(req.db, t["id"] if t else None, _int(req, "group_id"), _int(req, "teacher_id"))
    return {"term": t, "rows": _with_groups(req.db, rs)}


@R("POST", "/api/timetable", perm="timetable.manage")
def create_row(req):
    status, value = service.create_row(req.db, req.user, req.json())
    if status == "conflict":
        return _conflict(req, value)
    if status == "invalid":
        raise HTTPError(400, value)
    return _with_groups(req.db, [repo.row_by_id(req.db, value)])[0]


@R("PUT", "/api/timetable/{id:int}", perm="timetable.manage")
def update_row(req):
    status, value = service.update_row(req.db, req.user, req.params["id"], req.json())
    if status == "conflict":
        return _conflict(req, value)
    if status == "invalid":
        raise HTTPError(400, value)
    if status == "missing":
        raise HTTPError(404, "Tapılmadı")
    return _with_groups(req.db, [repo.row_by_id(req.db, req.params["id"])])[0]


@R("POST", "/api/timetable/{id:int}/deactivate", perm="timetable.manage")
def deactivate_row(req):
    if service.deactivate_row(req.db, req.user, req.params["id"]) == "missing":
        raise HTTPError(404, "Tapılmadı")
    return {"ok": True}


@R("POST", "/api/timetable/generate", perm="timetable.manage")
def generate(req):
    status, report = service.generate(req.db, req.user, req.json().integer("term_id", None, lo=1))
    if status == "missing":
        raise HTTPError(404, "Semestr tapılmadı")
    return report


@R("GET", "/api/lessons", perm="directory.read")
def lessons_on(req):
    day = req.query.get("day") or now().date().isoformat()
    if service.directory_rules.date_problem("day", day):
        raise HTTPError(400, service.directory_rules.date_problem("day", day))
    return repo.lessons_on(req.db, day, _int(req, "group_id"), _int(req, "teacher_id"))


@R("POST", "/api/lessons/{id:int}/cancel", perm="timetable.manage")
def cancel_lesson(req):
    status = service.cancel_lesson(req.db, req.user, req.params["id"], " ".join(req.json().text("reason", 300).split()))
    if status == "missing":
        raise HTTPError(404, "Dərs tapılmadı")
    if status == "recorded":
        raise HTTPError(409, "Bu dərsin davamiyyəti yazılıb: onu ləğv etmək olmaz")
    if status == "cancelled":
        raise HTTPError(409, "Dərs artıq ləğv edilib")
    if status == "invalid":
        raise HTTPError(400, "Ləğvin səbəbini yazın")
    return repo.lesson(req.db, req.params["id"])


@R("POST", "/api/lessons/{id:int}/move", perm="timetable.manage")
def move_lesson(req):
    status, value = service.move_lesson(req.db, req.user, req.params["id"], req.json())
    if status == "conflict":
        return _conflict(req, value)
    if status == "missing":
        raise HTTPError(404, "Dərs tapılmadı")
    if status == "recorded":
        raise HTTPError(409, "Bu dərsin davamiyyəti yazılıb: onu köçürmək olmaz")
    if status == "invalid":
        raise HTTPError(400, value)
    return repo.lesson(req.db, req.params["id"])


# ---------------------------------------------------------------- calendar feed
def _feed_url(token: str) -> str:
    return f"{BASE_URL['value']}/ical/{token}"


@R("GET", "/api/me/calendar")
def my_feed(req):
    return {"active": service.has_feed(req.db, req.user)}


@R("POST", "/api/me/calendar")
def new_feed(req):
    return {"url": _feed_url(service.new_feed(req.db, req.user)), "active": True}


@R("DELETE", "/api/me/calendar")
def drop_feed(req):
    service.drop_feed(req.db, req.user)
    return {"active": False}


@R("GET", "/ical/{token}", auth=False)
def feed(req):
    if not LIMITS["ical"].hit(req.ip):
        raise HTTPError(429, "Çox sayda sorğu. Bir az sonra yenidən cəhd edin.")
    found = service.feed_events(req.db, str(req.params["token"]))
    if not found:
        raise HTTPError(404, "Tapılmadı")
    u, lessons = found
    lang = "az"                                         # a calendar app sends no language; the catalogue keys are Azerbaijani
    events = [{**x, "summary": f"{x['course']} · {x['kind']}" if x["kind"] else x["course"], "location": x["room"]} for x in lessons]
    offset = clock.now().astimezone(clock.ZONE).strftime("%z") if clock.ZONE else "+0400"
    body = domain.calendar(events, tzid=clock.TZ_NAME, offset=offset, host=urlsplit(BASE_URL["value"]).hostname or "zeka",
                           stamp=clock.now(), name=S("Zəka: dərs cədvəli", lang) + f" · {u['full_name']}")
    return Response(body, 200, "text/calendar; charset=utf-8", [("Cache-Control", "private, max-age=900")])
