"""HTTP routes of the attendance journal (tasks/todo.md, Task 20)."""
from __future__ import annotations

import csv
import io
from datetime import timedelta

from ...core.i18n import S, localize
from ...core.perms import STAFF_ROLES
from ...core.web import HTTPError, Response, json_resp
from ...legacy.common import R, scope_sql, serves
from ...legacy.store import now
from ..directory import domain as directory_rules
from ..integration.domain import csv_cell
from . import repo, service


def _answer(status, value):
    if status == "missing":
        raise HTTPError(404, "Dərs tapılmadı")
    if status == "forbidden":
        raise HTTPError(403, value)
    if status == "invalid":
        raise HTTPError(400, value)
    return value


@R("GET", "/api/journal/lessons", roles=STAFF_ROLES)
def my_lessons(req):
    day = req.query.get("day") or None
    if day and directory_rules.date_problem("day", day):
        raise HTTPError(400, directory_rules.date_problem("day", day))
    return service.teacher_lessons(req.db, req.user, day)


@R("GET", "/api/journal/courses/{id:int}/lessons", roles=STAFF_ROLES)
def course_lessons(req):
    if not service.can_read_course(req.db, req.user, req.params["id"]):
        raise HTTPError(404, "Fənn tapılmadı")
    return repo.lessons_of_course(req.db, req.params["id"], (now().date() + timedelta(days=14)).isoformat())   # upcoming: to substitute


@R("GET", "/api/journal/lessons/{id:int}", roles=STAFF_ROLES)
def lesson(req):
    view = service.lesson_view(req.db, req.user, req.params["id"])
    if not view:
        raise HTTPError(404, "Dərs tapılmadı")
    return view


@R("PUT", "/api/journal/lessons/{id:int}/attendance", roles=STAFF_ROLES)
def save_attendance(req):
    return _answer(*service.save_marks(req.db, req.user, req.params["id"], req.json()))


@R("POST", "/api/journal/lessons/{id:int}/teacher", perm="journal.correct")
def substitute(req):
    return _answer(*service.substitute(req.db, req.user, req.params["id"], req.json()))


@R("GET", "/api/journal/courses/{id:int}/standing", roles=STAFF_ROLES)
def standing(req):
    c, u = req.db, req.user
    if not service.can_read_course(c, u, req.params["id"]):
        raise HTTPError(404, "Fənn tapılmadı")
    out = service.course_standing(c, req.params["id"])
    return [x for x in out if serves(c, u, x["student_id"])] if u["role"] == "office" else out


@R("PUT", "/api/journal/openings/{id:int}", perm="journal.correct")
def correct_opening(req):
    status, value = service.correct_opening(req.db, req.user, req.params["id"], req.json())
    if status == "missing":
        raise HTTPError(404, "Tapılmadı")
    return _answer(status, value)


# ---------------------------------------------------------------- grades (Task 21)
def _table(req, table):
    if not table:
        raise HTTPError(404, "Fənn tapılmadı")
    if req.user["role"] == "office":                   # a dean's office: its own faculty's students
        table["students"] = [s for s in table["students"] if serves(req.db, req.user, s["id"])]
    return table


@R("GET", "/api/journal/courses/{id:int}/grades", roles=STAFF_ROLES)
def grades(req):
    return _table(req, service.grade_table(req.db, req.user, req.params["id"]))


@R("PUT", "/api/journal/courses/{id:int}/grades", roles=STAFF_ROLES)
def save_grades(req):
    status, value = service.save_grades(req.db, req.user, req.params["id"], req.json())
    if status == "cells":
        return json_resp({"error": S("Bəzi xanalar saxlanmadı", req.lang), "cells": localize(value, req.lang)}, 400)   # reasons only: keys are kept
    if status == "missing":
        raise HTTPError(404, "Fənn tapılmadı")
    return _table(req, _answer(status, value))


@R("POST", "/api/journal/courses/{id:int}/grades/publish", roles=STAFF_ROLES)
def publish_grades(req):
    status, value = service.publish_grades(req.db, req.user, req.params["id"])
    if status == "missing":
        raise HTTPError(404, "Fənn tapılmadı")
    return _table(req, _answer(status, value))


@R("GET", "/api/journal/courses/{id:int}/grades/log", roles=STAFF_ROLES)
def grade_log(req):
    if not service.can_read_course(req.db, req.user, req.params["id"]):
        raise HTTPError(404, "Fənn tapılmadı")
    out = repo.changes(req.db, req.params["id"])
    return [x for x in out if serves(req.db, req.user, x["user_id"])] if req.user["role"] == "office" else out


@R("GET", "/api/journal/debts", roles=("office", "academic_office", "admin", "leader"))
def debts(req):
    """The academic debts (final grades that did not pass); ``?format=csv`` for a spreadsheet."""
    c, u = req.db, req.user
    scope, args = scope_sql(u, "f.user_id")             # a dean's office: its faculties, in SQL before the page
    if req.query.get("format") != "csv":
        return service.debts(c, scope, args, req.qint("page", 1, lo=1, hi=100000))
    out = service.debts(c, scope, args)["items"]
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = ("student_no", "full_name", "grp", "term_name", "course_code", "course_name", "credits", "score", "letter")
    w.writerow(cols)
    w.writerows([[csv_cell(x[k]) for k in cols] for x in out])
    return Response(buf.getvalue(), 200, "text/csv; charset=utf-8", [("Content-Disposition", 'attachment; filename="akademik-borclar.csv"')])


@R("POST", "/api/journal/students/{id:int}/reconcile", roles=("office", "academic_office", "admin"))
def reconcile(req):
    c, u = req.db, req.user
    if (u["role"] == "office" and not serves(c, u, req.params["id"])) or not service.reconcile(c, u, req.params["id"]):
        raise HTTPError(404, "Tələbə tapılmadı")
    return {"ok": True}
