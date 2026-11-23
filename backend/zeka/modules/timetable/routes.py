"""HTTP routes of the timetable (tasks/todo.md, Task 19): rows and their conflicts, making lessons, cancelling and
moving one lesson, and each person's calendar feed; and the semester timetable builder (Task 48, slice 2: none of its
routes is slow, none computes a whole term)."""
from __future__ import annotations

import functools
import hashlib
from urllib.parse import urlsplit

from ...core import clock
from ...core.i18n import S, localize
from ...core.security import LIMITS
from ...core.web import HTTPError, Response, json_resp
from ...legacy.common import BASE_URL, R
from ...legacy.store import now
from . import builder, domain, repo, service


def _conflict(req, clashes):
    return json_resp({"error": S("Cədvəldə toqquşma var", req.lang), "conflicts": clashes}, 409)


def _busy(status):
    if status == "busy":                        # Task 48: a publication of the term's timetable is under way
        raise HTTPError(409, "Semestrin cədvəli dərc olunur: bir az sonra yenidən cəhd edin")


LIST_LIMIT = 1000                   # rows in one answer; a longer term is read by group or teacher


def _int(req, name):
    v = req.query.get(name)
    return req.qint(name, 0, lo=1) if v not in (None, "") else None


def _with_groups(c, rs: list[dict]) -> list[dict]:
    groups = repo.groups_of_units(c, sorted({r["unit_id"] for r in rs if r["unit_id"]}))
    names = repo.group_names(c, {g for v in groups.values() for g in v})
    return [{**r, "groups": [names[g] for g in groups.get(r["unit_id"], []) if g in names]} for r in rs]


@R("GET", "/api/timetable", perm="directory.read")
def list_rows(req):
    t = service.term(req.db, _int(req, "term_id"))
    rs = repo.listed(req.db, t["id"] if t else None, _int(req, "group_id"), _int(req, "teacher_id"), LIST_LIMIT + 1)
    return {"term": t, "rows": _with_groups(req.db, rs[:LIST_LIMIT]), "more": len(rs) > LIST_LIMIT}


@R("POST", "/api/timetable", perm="timetable.manage")
def create_row(req):
    status, value = service.create_row(req.db, req.user, req.json())
    _busy(status)
    if status == "conflict":
        return _conflict(req, value)
    if status == "invalid":
        raise HTTPError(400, value)
    return _with_groups(req.db, [repo.row_by_id(req.db, value)])[0]


@R("PUT", "/api/timetable/{id:int}", perm="timetable.manage")
def update_row(req):
    status, value = service.update_row(req.db, req.user, req.params["id"], req.json())
    _busy(status)
    if status == "conflict":
        return _conflict(req, value)
    if status == "invalid":
        raise HTTPError(400, value)
    if status == "missing":
        raise HTTPError(404, "Tapılmadı")
    return _with_groups(req.db, [repo.row_by_id(req.db, req.params["id"])])[0]


@R("POST", "/api/timetable/{id:int}/deactivate", perm="timetable.manage")
def deactivate_row(req):
    status = service.deactivate_row(req.db, req.user, req.params["id"])
    _busy(status)
    if status == "missing":
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
        raise HTTPError(409, "Bu dərsin davamiyyəti yazılıb: onu ləğv etmək mümkün deyil")
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
        raise HTTPError(409, "Bu dərsin davamiyyəti yazılıb: onu köçürmək mümkün deyil")
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
    token = str(req.params["token"])
    if not LIMITS["ical_client"].hit(req.ip):         # calendar services and a campus share addresses: a wide cap per client
        raise HTTPError(429, "Çox sayda sorğu. Bir az sonra yenidən cəhd edin.")
    found = service.feed_events(req.db, token)
    if not found:
        raise HTTPError(404, "Tapılmadı")
    if not LIMITS["ical"].hit("f" + hashlib.sha256(token.encode()).hexdigest()[:32]):      # and a narrow one per feed
        raise HTTPError(429, "Çox sayda sorğu. Bir az sonra yenidən cəhd edin.")
    u, lessons = found
    lang = "az"                                         # a calendar app sends no language; the catalogue keys are Azerbaijani
    events = [{**x, "summary": f"{x['course']} · {x['kind']}" if x["kind"] else x["course"], "location": x["room"]} for x in lessons]
    offset = clock.now().astimezone(clock.ZONE).strftime("%z") if clock.ZONE else "+0400"
    body = domain.calendar(events, tzid=clock.TZ_NAME, offset=offset, host=urlsplit(BASE_URL["value"]).hostname or "zeka",
                           stamp=clock.now(), name=S("Zəka: dərs cədvəli", lang) + f" · {u['full_name']}")
    return Response(body, 200, "text/calendar; charset=utf-8", [("Cache-Control", "private, max-age=900")])


# ---------------------------------------------------------------- the timetable builder (Task 48)
B = "/api/timetable/build/{term:int}"
AV = B + "/teachers/{uid:int}/availability"
V = "/api/timetable/versions/{id:int}"
GRID_ROLES = ("teacher", "dept_head", "academic_office", "admin")      # a teacher's own grid, or one in the caller's scope


def _refusable(fn):
    """A builder refusal with a payload (readiness lines, the gate, a move's reasons) as a translated JSON answer."""
    @functools.wraps(fn)
    def handler(req):
        try:
            return fn(req)
        except builder.Refused as ex:
            return json_resp(localize(ex.body, req.lang), ex.status)
    return handler


@R("GET", B, perm="timetable.prepare")
def tt_start(req):
    return builder.start_page(req.db, req.user, req.params["term"])


@R("PUT", B + "/plan", perm="timetable.manage")
def tt_plan(req):
    return builder.save_plan(req.db, req.user, req.params["term"], req.json())


@R("GET", B + "/readiness", perm="timetable.prepare")
def tt_readiness(req):
    return builder.readiness(req.db, req.user, req.params["term"], _int(req, "department_id"))


@R("GET", "/api/timetable/settings", perm="timetable.prepare")
def tt_settings(req):
    return builder.get_settings(req.db)


@R("PUT", "/api/timetable/settings", perm="timetable.manage")
def tt_save_settings(req):
    return builder.put_settings(req.db, req.user, req.json().get("value"))


@R("GET", B + "/units", perm="timetable.prepare")
def tt_units(req):
    return builder.units(req.db, req.user, req.params["term"], _int(req, "department_id"), req.qint("offset", 0, lo=0))


@R("PUT", "/api/timetable/units/{id:int}/needs", perm="timetable.prepare")
def tt_needs(req):
    return builder.put_needs(req.db, req.user, req.params["id"], req.json())


@R("GET", B + "/groups", perm="timetable.prepare")
def tt_groups(req):
    return builder.groups(req.db, req.user, req.params["term"])


@R("PUT", B + "/groups", perm="timetable.prepare")
def tt_save_groups(req):
    return builder.put_groups(req.db, req.user, req.params["term"], req.json())


@R("GET", B + "/teachers", perm="timetable.prepare")
def tt_teachers(req):
    return builder.teachers(req.db, req.user, req.params["term"], _int(req, "department_id"))


@R("GET", AV, roles=GRID_ROLES)
def tt_availability(req):
    return builder.availability(req.db, req.user, req.params["term"], req.params["uid"])


@R("PUT", AV, roles=GRID_ROLES)
def tt_save_availability(req):
    return builder.put_availability(req.db, req.user, req.params["term"], req.params["uid"], req.json())


@R("POST", AV + "/confirm", roles=GRID_ROLES)
def tt_confirm_availability(req):
    req.json()
    return builder.confirm_availability(req.db, req.user, req.params["term"], req.params["uid"])


@R("POST", AV + "/decide", perm="timetable.prepare")
def tt_decide_availability(req):
    approve = req.json().get("approve")
    if not isinstance(approve, bool):
        raise HTTPError(400, "Qərarı göndərin: təsdiq və ya imtina")
    return builder.decide_availability(req.db, req.user, req.params["term"], req.params["uid"], approve)


@R("POST", AV + "/reopen", perm="timetable.prepare")
def tt_reopen_availability(req):
    return builder.reopen_availability(req.db, req.user, req.params["term"], req.params["uid"], req.json().get("until"))


@R("POST", B + "/runs", perm="timetable.manage")
@_refusable
def tt_start_run(req):
    return builder.start_run(req.db, req.user, req.params["term"], req.json())


@R("GET", "/api/timetable/runs/{id:int}", perm="timetable.manage")
def tt_run(req):
    return builder.get_run(req.db, req.user, req.params["id"])


@R("POST", "/api/timetable/runs/{id:int}/cancel", perm="timetable.manage")
def tt_cancel_run(req):
    req.json()
    return builder.cancel_run(req.db, req.user, req.params["id"])


@R("GET", B + "/versions", perm="timetable.prepare")
def tt_versions(req):
    return builder.versions(req.db, req.user, req.params["term"])


@R("GET", V + "/grid", perm="timetable.prepare")
def tt_grid(req):
    return builder.grid(req.db, req.user, req.params["id"], _int(req, "group_id"), _int(req, "teacher_id"), _int(req, "room_id"))


@R("GET", V + "/unplaced", perm="timetable.prepare")
def tt_unplaced(req):
    return builder.unplaced(req.db, req.user, req.params["id"])


@R("GET", V + "/scorecard", perm="timetable.prepare")
def tt_scorecard(req):
    return builder.scorecard(req.db, req.user, req.params["id"])


@R("GET", V + "/placements/{pid:int}/options", perm="timetable.manage")
def tt_options(req):
    return builder.options(req.db, req.user, req.params["id"], req.params["pid"])


@R("POST", V + "/placements/{pid:int}/move", perm="timetable.manage")
@_refusable
def tt_move(req):
    return builder.move(req.db, req.user, req.params["id"], req.params["pid"], req.json())


@R("POST", V + "/lock", perm="timetable.manage")
def tt_lock(req):
    return builder.lock(req.db, req.user, req.params["id"], req.json())


@R("POST", V + "/publish", perm="timetable.publish")
@_refusable
def tt_publish(req):
    return builder.publish(req.db, req.user, req.params["id"], req.json())
