"""HTTP routes of the exam core (tasks/todo.md, Task 26). A student's routes answer with the public keys of a question
only (``domain.PUBLIC``); tests/security/test_exam_item_leak.py checks every route a student can call."""
from __future__ import annotations

from ...core.i18n import localize
from ...core.web import HTTPError, json_resp
from ...legacy.common import R
from . import service

MANAGERS = ("teacher", "dept_head")


def _answer(status, value, missing="İmtahan tapılmadı"):
    if status == "missing":
        raise HTTPError(404, missing)
    if status in ("invalid", "refused", "closed"):
        raise HTTPError({"invalid": 400, "refused": 403, "closed": 409}[status], value)
    return value


@R("POST", "/api/courses/{id:int}/exams", roles=MANAGERS)
def create(req):
    return _answer(*service.create(req.db, req.user, req.params["id"], req.json()), missing="Fənn tapılmadı")


@R("GET", "/api/courses/{id:int}/exams")
def list_exams(req):
    out = service.list_for(req.db, req.user, req.params["id"])
    if out is None:
        raise HTTPError(404, "Fənn tapılmadı")
    return out


@R("GET", "/api/exams/{id:int}/manage", roles=("teacher", "dept_head", "office", "academic_office", "admin", "leader"))
def manage(req):
    out = service.manage(req.db, req.user, req.params["id"])
    if out is None:
        raise HTTPError(404, "İmtahan tapılmadı")
    return out


@R("POST", "/api/exams/{id:int}/open", roles=MANAGERS)
def open_exam(req):
    return _answer(*service.open_exam(req.db, req.user, req.params["id"]))


@R("POST", "/api/exams/{id:int}/close", roles=MANAGERS)
def close(req):
    return _answer(*service.close(req.db, req.user, req.params["id"]))


@R("POST", "/api/exams/{id:int}/roster/{sid:int}/exception", roles=("office", "academic_office", "admin"))
def exception(req):
    return _answer(*service.exception(req.db, req.user, req.params["id"], req.params["sid"], req.json()))


@R("GET", "/api/exams/{id:int}", roles=("student",))
def view(req):
    out = service.view(req.db, req.user, req.params["id"])
    if out is None:
        raise HTTPError(404, "İmtahan tapılmadı")
    return out


@R("POST", "/api/exams/{id:int}/start", roles=("student",))
def start(req):
    status, value = service.start(req.db, req.user, req.params["id"])
    if status == "refused":            # returned, not raised: the refusal's event in the exam log commits
        return json_resp({"error": localize(value, req.lang)}, 403)
    return _answer(status, value)


@R("PUT", "/api/exams/{id:int}/answers/{qid:int}", roles=("student",))
def answer(req):
    return _answer(*service.answer(req.db, req.user, req.params["id"], req.params["qid"], req.json()), missing="Sual tapılmadı")


@R("POST", "/api/exams/{id:int}/submit", roles=("student",))
def submit(req):
    return _answer(*service.submit(req.db, req.user, req.params["id"]))
