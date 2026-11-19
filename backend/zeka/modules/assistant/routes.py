"""HTTP routes of the campus assistant's knowledge base and its handoff to a person (tasks/todo.md, Task 32)."""
from __future__ import annotations

from ...core.i18n import S_
from ...core.web import HTTPError
from ...legacy.common import R
from . import service


NO_ARTICLE = S_("Məqalə tapılmadı")


def _answer(status, value, missing=NO_ARTICLE):
    if status == "missing":
        raise HTTPError(404, missing)
    if status == "invalid":
        raise HTTPError(400, value)
    return value


@R("GET", "/api/kb", perm="kb.manage")
def kb_list(req):
    return service.kb_list(req.db)


@R("GET", "/api/kb/{id:int}", perm="kb.manage")
def kb_get(req):
    return _answer("missing" if (v := service.kb_get(req.db, req.params["id"])) is None else "ok", v)


@R("POST", "/api/kb", perm="kb.manage")
def kb_create(req):
    return _answer(*service.kb_save(req.db, req.user, None, req.json()))


@R("PUT", "/api/kb/{id:int}", perm="kb.manage")
def kb_update(req):
    return _answer(*service.kb_save(req.db, req.user, req.params["id"], req.json()))


@R("POST", "/api/campus/handoff")
def handoff(req):
    status, tid = service.handoff(req.db, req.user, req.json().integer("message_id", lo=1))
    return {"ticket_id": _answer(status, tid, S_("Cavab tapılmadı"))}
