"""HTTP routes of the attendance journal (tasks/todo.md, Task 20)."""
from __future__ import annotations

from ...core.perms import STAFF_ROLES
from ...core.web import HTTPError
from ...legacy.common import R, serves
from ...legacy.store import now
from ..directory import domain as directory_rules
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
    return repo.lessons_of_course(req.db, req.params["id"], now().date().isoformat())


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
