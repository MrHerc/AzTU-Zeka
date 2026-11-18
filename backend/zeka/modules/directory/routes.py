"""HTTP routes of the directory (tasks/todo.md, Task 15, slice 1): list, create, update, deactivate. No delete."""
from __future__ import annotations

from ...core.web import HTTPError
from ...legacy.common import R
from . import domain, repo, service


def _entity(req) -> str:
    entity = req.params["entity"]
    if entity not in domain.ENTITIES:
        raise HTTPError(404, "Tapılmadı")
    return entity


@R("GET", "/api/directory/{entity}", perm="directory.read")
def list_entities(req):
    entity = _entity(req)
    q = (req.query.get("q") or "").strip()[:100]
    active = {"1": 1, "0": 0}.get(req.query.get("active", ""))
    page_no = req.qint("page", 1, lo=1, hi=100000)
    items, total = repo.page(req.db, entity, q, active, page_no)
    return {"items": items, "total": total, "page": page_no, "pages": max(1, -(-total // domain.PAGE)), "page_size": domain.PAGE}


def _answer(status, value):
    if status == "invalid":
        raise HTTPError(400, value)
    if status == "taken":
        raise HTTPError(409, "Bu kod artıq istifadə olunur")
    if status == "missing":
        raise HTTPError(404, "Tapılmadı")


@R("POST", "/api/directory/{entity}", perm="directory.manage")
def create_entity(req):
    entity = _entity(req)
    status, value = service.create(req.db, req.user, entity, req.json())
    _answer(status, value)
    return repo.get(req.db, entity, value)


@R("PUT", "/api/directory/{entity}/{id:int}", perm="directory.manage")
def update_entity(req):
    entity = _entity(req)
    status, value = service.update(req.db, req.user, entity, req.params["id"], req.json())
    _answer(status, value)
    return repo.get(req.db, entity, req.params["id"])


@R("POST", "/api/directory/{entity}/{id:int}/deactivate", perm="directory.manage")
def deactivate_entity(req):
    entity = _entity(req)
    if not service.set_active(req.db, req.user, entity, req.params["id"], False):
        raise HTTPError(404, "Tapılmadı")
    return repo.get(req.db, entity, req.params["id"])


@R("POST", "/api/directory/{entity}/{id:int}/activate", perm="directory.manage")
def activate_entity(req):
    entity = _entity(req)
    if not service.set_active(req.db, req.user, entity, req.params["id"], True):
        raise HTTPError(404, "Tapılmadı")
    return repo.get(req.db, entity, req.params["id"])
