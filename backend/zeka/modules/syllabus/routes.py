"""HTTP routes of the structured syllabus (tasks/todo.md, Task 23)."""
from __future__ import annotations

from ...core.i18n import localize
from ...core.perms import STAFF_ROLES
from ...core.web import HTTPError, Response
from ...legacy.common import R
from . import frameworks, service


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
    return out | {"tags": localize(out["tags"], req.lang)}        # the built-in frameworks' items are translated, the text is not


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


# ---------------------------------------------------------------- frameworks and the outcome map (Task 24)
@R("GET", "/api/frameworks", roles=STAFF_ROLES)
def framework_list(req):
    return frameworks.listing(req.db)


@R("GET", "/api/frameworks/{id:int}/items", roles=STAFF_ROLES)
def framework_items(req):
    """The picker's search: ``?q=&kind=&role=<work role code>&page=&size=``, server side and paged."""
    out = frameworks.search(req.db, req.params["id"], req.query.get("q"), req.query.get("kind"), req.query.get("role"),
                            req.qint("page", 1, lo=1, hi=100000), req.qint("size", 20, lo=1, hi=100))
    if out is None:
        raise HTTPError(404, "Çərçivə tapılmadı")
    return out


@R("GET", "/api/syllabi/{id:int}/frameworks", roles=STAFF_ROLES)
def outcome_map(req):
    out = frameworks.course_map(req.db, req.user, req.params["id"])
    if out is None:
        raise HTTPError(404, "Fənn tapılmadı")
    return out


@R("PUT", "/api/syllabi/{id:int}/outcomes/{oid}/items", roles=("teacher",))
def map_outcome(req):
    """Replace one outcome's framework items: ``{"items": [<item id>, ...]}``."""
    status, value = frameworks.set_outcome(req.db, req.user, req.params["id"], req.params["oid"], req.json())
    if status != "ok":
        raise HTTPError(404 if status == "missing" else 400, value)
    return value


@R("GET", "/api/frameworks/programmes", roles=frameworks.COVERAGE_ROLES)
def framework_programmes(req):
    return frameworks.programmes(req.db, req.user)


@R("GET", "/api/frameworks/coverage", roles=frameworks.COVERAGE_ROLES)
def framework_coverage(req):
    """``?programme=<specialty id>&framework=<id, default the newest NICE>&role=<work role code>``; ``&format=csv``
    for the whole report as a spreadsheet. A programme outside the caller's scope is 404."""
    req.raw_i18n = True                                 # course names and outcomes are the teachers' text, NICE is English
    sid, fid = req.qint("programme", 0, lo=0), req.qint("framework", 0, lo=0) or None
    if req.query.get("format") == "csv":
        out = frameworks.coverage_csv(req.db, req.user, sid, fid, req.lang)
        if out is None:
            raise HTTPError(404, "İxtisas tapılmadı")
        return Response(out[1], 200, "text/csv; charset=utf-8",
                        [("Content-Disposition", f'attachment; filename="{out[0]}"'), ("Cache-Control", "private, no-store")])
    rep = frameworks.coverage(req.db, req.user, sid, fid, req.query.get("role") or None)
    if rep is None:
        raise HTTPError(404, "İxtisas tapılmadı")
    return localize({k: rep[k] for k in ("framework", "labels")}, req.lang) | {k: v for k, v in rep.items() if k not in ("framework", "labels")}
