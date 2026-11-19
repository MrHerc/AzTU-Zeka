"""HTTP routes of the structured syllabus (tasks/todo.md, Task 23)."""
from __future__ import annotations

from ...core.perms import STAFF_ROLES
from ...core.web import HTTPError
from ...legacy.common import R
from . import service


@R("GET", "/api/syllabi/{id:int}", roles=STAFF_ROLES)
def get(req):
    req.raw_i18n = True                                 # a syllabus is the teacher's text: never translated on the way out
    out = service.state(req.db, req.user, req.params["id"])
    if out is None:
        raise HTTPError(404, "Fənn tapılmadı")
    return out


@R("POST", "/api/syllabi/{id:int}/draft", roles=("teacher",))
def draft(req):
    req.raw_i18n = True                                 # the first draft keeps the assistant's Azerbaijani text
    out = service.draft(req.db, req.user, req.params["id"])
    if out is None:
        raise HTTPError(404, "Fənn tapılmadı")
    return {"data": out}


@R("PUT", "/api/syllabi/{id:int}", roles=("teacher",))
def save(req):
    req.raw_i18n = True
    status, value = service.save(req.db, req.user, req.params["id"], req.json())
    if status == "missing":
        raise HTTPError(404, "Fənn tapılmadı")
    if status in ("forbidden", "invalid", "stale"):
        raise HTTPError({"forbidden": 403, "invalid": 400, "stale": 409}[status], value)
    return value


@R("GET", "/api/syllabi/{id:int}/versions/{vid:int}", roles=STAFF_ROLES)
def version(req):
    req.raw_i18n = True
    out = service.version(req.db, req.user, req.params["id"], req.params["vid"])
    if out is None:
        raise HTTPError(404, "Versiya tapılmadı")
    return out


# ---------------------------------------------------------------- approval and publication (Task 25)
def _step(req, action):
    req.raw_i18n = True
    status, value = service.act(req.db, req.user, req.params["id"], req.params["vid"], action, req.json())
    if status == "missing":
        raise HTTPError(404, "Versiya tapılmadı")
    if status in ("forbidden", "invalid", "blocked"):
        raise HTTPError({"forbidden": 403, "invalid": 400, "blocked": 409}[status], value)
    return value


@R("POST", "/api/syllabi/{id:int}/versions/{vid:int}/submit", roles=("teacher",))
def submit(req):
    return _step(req, "submit")


@R("POST", "/api/syllabi/{id:int}/versions/{vid:int}/approve", roles=("dept_head",))
def approve(req):
    return _step(req, "approve")


@R("POST", "/api/syllabi/{id:int}/versions/{vid:int}/publish", roles=("academic_office",))
def publish(req):
    return _step(req, "publish")


@R("POST", "/api/syllabi/{id:int}/versions/{vid:int}/return", roles=("dept_head", "academic_office"))
def give_back(req):
    return _step(req, "return")


@R("GET", "/api/syllabi/queue", roles=("dept_head", "academic_office", "admin"))
def queue(req):
    req.raw_i18n = True
    return service.queue(req.db, req.user)


@R("GET", "/api/syllabi/{id:int}/diff", roles=STAFF_ROLES)
def diff(req):
    req.raw_i18n = True
    out = service.compare(req.db, req.user, req.params["id"], req.qint("a", 0, lo=1), req.qint("b", 0, lo=1))
    if out is None:
        raise HTTPError(404, "Versiya tapılmadı")
    return out


@R("GET", "/api/courses/{id:int}/syllabus")
def course_syllabus(req):
    """The course's published syllabus: its students see only this version (Task 25)."""
    req.raw_i18n = True
    return {"published": service.published_for(req.db, req.user, req.params["id"])}
