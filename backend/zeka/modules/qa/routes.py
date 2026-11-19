"""HTTP routes of the course forum (tasks/todo.md, Task 33)."""
from __future__ import annotations

from ...core.i18n import S_
from ...core.web import HTTPError
from ...legacy.common import R
from . import service

READERS = ("student", "teacher", "dept_head")
TEACHERS = ("teacher", "dept_head")
NO_TOPIC = S_("Mövzu tapılmadı")


def _answer(status, value, missing=NO_TOPIC):
    if status == "missing":
        raise HTTPError(404, missing)
    if status == "invalid":
        raise HTTPError(400, value)
    return value


@R("GET", "/api/courses/{id:int}/qa", roles=READERS)
def topics(req):
    out = service.topics(req.db, req.user, req.params["id"])
    return _answer("missing" if out is None else "ok", out, S_("Fənn tapılmadı"))


@R("POST", "/api/courses/{id:int}/qa", roles=READERS)
def create(req):
    return _answer(*service.create(req.db, req.user, req.params["id"], req.json()), S_("Fənn tapılmadı"))


@R("GET", "/api/qa/topics/{id:int}", roles=READERS)
def topic(req):
    out = service.topic(req.db, req.user, req.params["id"])
    return _answer("missing" if out is None else "ok", out)


@R("POST", "/api/qa/topics/{id:int}/replies", roles=READERS)
def reply(req):
    return _answer(*service.reply(req.db, req.user, req.params["id"], req.json()))


@R("POST", "/api/qa/replies/{id:int}/accept", roles=TEACHERS)
def accept(req):
    return _answer(*service.accept(req.db, req.user, req.params["id"]), S_("Cavab tapılmadı"))


@R("POST", "/api/qa/topics/{id:int}/draft", roles=TEACHERS)
def draft(req):
    return _answer(*service.draft(req.db, req.user, req.params["id"], req.lang))


@R("POST", "/api/qa/topics/{id:int}/faq", roles=TEACHERS)
def faq(req):
    on = req.json().get("on")
    if not isinstance(on, bool):
        raise HTTPError(400, "Sorğu düzgün deyil")
    return _answer(*service.faq(req.db, req.user, req.params["id"], on))


@R("POST", "/api/qa/reports", roles=READERS)
def report(req):
    return _answer(*service.report(req.db, req.user, req.json()))


@R("GET", "/api/qa/reports", perm="qa.moderate")
def queue(req):
    return service.queue(req.db)


@R("POST", "/api/qa/reports/{id:int}/resolve", perm="qa.moderate")
def resolve(req):
    return _answer(*service.resolve(req.db, req.user, req.params["id"], req.json()), S_("Şikayət tapılmadı"))
