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
