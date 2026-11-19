"""HTTP routes of the university settings (tasks/todo.md, Task 17): the administrator reads them and saves one section."""
from __future__ import annotations

from ...core.web import HTTPError
from ...legacy.common import R
from . import service


@R("GET", "/api/admin/settings", roles=("admin",))
def settings(req):
    return service.read(req.db)


@R("PUT", "/api/admin/settings/{section}", roles=("admin",))
def save_section(req):
    section = req.params["section"]
    if section not in service.SECTIONS:
        raise HTTPError(404, "Tapılmadı")
    value = req.json().get("value")
    problem = service.problem(section, value)
    if problem:
        raise HTTPError(400, problem)
    service.save(req.db, req.user, section, value)
    if section in ("grading", "attendance", "journal"):  # the final grades follow the rules they are computed by
        from ..journal import service as journal
        journal.refresh_all_finals(req.db)
    return service.read(req.db)
