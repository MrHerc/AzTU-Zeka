"""HTTP routes of assignments (tasks/todo.md, Task 22)."""
from __future__ import annotations

from ...core.web import HTTPError
from ...legacy.common import R
from . import service


def _answer(status, value, missing="Tapşırıq tapılmadı"):
    if status == "missing":
        raise HTTPError(404, missing)
    if status in ("invalid", "late"):
        raise HTTPError(400 if status == "invalid" else 409, value)
    if status == "forbidden":
        raise HTTPError(403, value)
    return value


@R("GET", "/api/courses/{id:int}/assignments")
def assignments(req):
    out = service.list_for(req.db, req.user, req.params["id"])
    if out is None:
        raise HTTPError(404, "Fənn tapılmadı")
    return out


@R("POST", "/api/courses/{id:int}/assignments", roles=("teacher", "dept_head"))
def create(req):
    return _answer(*service.create(req.db, req.user, req.params["id"], req.json()), missing="Fənn tapılmadı")


@R("POST", "/api/assignments/{id:int}/submit", roles=("student",))
def submit(req):
    return _answer(*service.submit(req.db, req.user, req.params["id"], req.json()))


@R("GET", "/api/assignments/{id:int}/submissions", roles=("teacher", "dept_head"))
def submissions(req):
    out = service.submissions(req.db, req.user, req.params["id"])
    if out is None:
        raise HTTPError(404, "Tapşırıq tapılmadı")
    return out


@R("GET", "/api/submissions/{id:int}", audit_read="submission")
def submission(req):
    s = service.submission(req.db, req.user, req.params["id"])
    if not s:
        raise HTTPError(404, "Göndəriş tapılmadı")
    req.read_owner, req.read_object = s["student_id"], s["id"]
    return s


@R("POST", "/api/submissions/{id:int}/grade", roles=("teacher", "dept_head"))
def grade(req):
    return _answer(*service.grade(req.db, req.user, req.params["id"], req.json()), missing="Göndəriş tapılmadı")
