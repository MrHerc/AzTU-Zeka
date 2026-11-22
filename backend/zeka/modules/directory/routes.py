"""HTTP routes of the directory (tasks/todo.md, Task 15): list, create, update, deactivate (no delete); enrolments,
teaching units' groups, the lesson list of a course, students' status orders."""
from __future__ import annotations

from ...core import perms
from ...core.web import HTTPError
from ...legacy.common import R, course_access, serves
from . import domain, repo, service

READ_PERM = {"users": "directory.manage"}       # people's names, numbers and addresses: not every staff member
MANAGE_PERM = {"users": "users.manage"}         # accounts and their roles: the administrator only


def _entity(req, manage: bool = False) -> str:
    entity = req.params["entity"]
    if entity not in domain.ENTITIES:
        raise HTTPError(404, "Tapılmadı")
    need = (MANAGE_PERM if manage else READ_PERM).get(entity)
    if need and not perms.has(req.user["role"], need):
        raise HTTPError(403, "Bu bölməyə giriş icazəniz yoxdur")
    return entity


def _filters(req, entity: str) -> dict:
    out = {}
    for col in domain.ENTITIES[entity].get("filters", ()):
        v = req.query.get(col)
        if v not in (None, ""):
            out[col] = req.qint(col, 0, lo=1) if col.endswith("_id") else v[:40]
    return out


@R("GET", "/api/directory/{entity}", perm="directory.read")
def list_entities(req):
    entity = _entity(req)
    q = (req.query.get("q") or "").strip()[:100]
    active = {"1": True, "0": False}.get(req.query.get("active", ""))
    page_no = req.qint("page", 1, lo=1, hi=100000)
    items, total = repo.page(req.db, entity, q, active, _filters(req, entity), page_no)
    return {"items": items, "total": total, "page": page_no, "pages": max(1, -(-total // domain.PAGE)), "page_size": domain.PAGE}


def _answer(status, value=None):
    if status == "invalid":
        raise HTTPError(400, value)
    if status == "taken":
        raise HTTPError(409, "Bu kod artıq istifadə olunur")
    if status == "missing":
        raise HTTPError(404, "Tapılmadı")
    if status == "self":
        raise HTTPError(409, "Öz hesabınızın rolunu dəyişə və ya onu deaktiv edə bilməzsiniz")


@R("POST", "/api/directory/{entity}", perm="directory.manage")
def create_entity(req):
    entity = _entity(req, manage=True)
    status, value = service.create(req.db, req.user, entity, req.json())
    _answer(status, value)
    return repo.get(req.db, entity, value, public=True)


@R("PUT", "/api/directory/{entity}/{id:int}", perm="directory.manage")
def update_entity(req):
    entity = _entity(req, manage=True)
    status, value = service.update(req.db, req.user, entity, req.params["id"], req.json())
    _answer(status, value)
    return repo.get(req.db, entity, req.params["id"], public=True)


def _toggle(req, active: bool):
    entity = _entity(req, manage=True)
    _answer(service.set_active(req.db, req.user, entity, req.params["id"], active))
    return repo.get(req.db, entity, req.params["id"], public=True)


@R("POST", "/api/directory/{entity}/{id:int}/deactivate", perm="directory.manage")
def deactivate_entity(req):
    return _toggle(req, False)


@R("POST", "/api/directory/{entity}/{id:int}/activate", perm="directory.manage")
def activate_entity(req):
    return _toggle(req, True)


# ---------------------------------------------------------------- teaching units, enrolments (slice 2)
@R("GET", "/api/directory/units/{id:int}/groups", perm="directory.read")
def unit_groups(req):
    if not repo.get(req.db, "units", req.params["id"]):
        raise HTTPError(404, "Tapılmadı")
    return {"group_ids": repo.unit_groups(req.db, req.params["id"])}


@R("PUT", "/api/directory/units/{id:int}/groups", perm="directory.manage")
def set_unit_groups(req):
    _answer(*service.set_unit_groups(req.db, req.user, req.params["id"], req.json().get("group_ids")))
    return {"group_ids": repo.unit_groups(req.db, req.params["id"])}


@R("GET", "/api/directory/courses/{id:int}/enrollments", perm="directory.manage")
def course_enrollments(req):
    if not repo.get(req.db, "courses", req.params["id"]):
        raise HTTPError(404, "Tapılmadı")
    return repo.enrollments(req.db, req.params["id"])


@R("POST", "/api/directory/courses/{id:int}/enrollments", perm="directory.manage")
def enroll(req):
    status, value = service.enroll(req.db, req.user, req.params["id"], req.json())
    if status == "taken":
        raise HTTPError(409, "Tələbə bu fənn üzrə artıq qeydiyyatdadır")
    _answer(status, value)
    return repo.enrollments(req.db, req.params["id"])


@R("POST", "/api/directory/courses/{id:int}/enrollments/{uid:int}/end", perm="directory.manage")
def end_enrollment(req):
    _answer(*service.end_enrollment(req.db, req.user, req.params["id"], req.params["uid"], req.json().text("end_date", 10)))
    return repo.enrollments(req.db, req.params["id"])


@R("GET", "/api/courses/{id:int}/roster", roles=("teacher", "admin", "academic_office"))
def roster(req):
    """The lesson list of a course on a day (default today): only enrolments in force that day."""
    co = course_access(req, req.params["id"])                 # a teacher: only their own course
    day = req.query.get("day") or service.today()
    if domain.date_problem("day", day):
        raise HTTPError(400, domain.date_problem("day", day))
    return {"course_id": co["id"], "day": day, "students": repo.roster(req.db, co["id"], day)}


# ---------------------------------------------------------------- status orders (slice 2)
def _student(req):
    u = repo.get(req.db, "users", req.params["id"])
    if not u or u["role"] != "student" or not serves(req.db, req.user, u["id"]):    # a dean's office: its faculty only
        raise HTTPError(404, "Tələbə tapılmadı")
    return u


@R("GET", "/api/directory/students/{id:int}/status", perm="students.status.read", audit_read="student_status")
def student_status(req):
    u = _student(req)
    req.read_owner, req.read_object = u["id"], u["id"]
    return service.status_of(req.db, u["id"])


@R("POST", "/api/directory/students/{id:int}/status", perm="students.status")
def add_student_status(req):
    u = _student(req)
    values, problem = domain.status_event(req.json())
    if problem:
        raise HTTPError(400, problem)
    _answer(*service.record_status(req.db, req.user, u, values))
    return service.status_of(req.db, u["id"])
