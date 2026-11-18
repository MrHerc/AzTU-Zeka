"""Directory changes: validation, references, uniqueness and the audit log (tasks/todo.md, Task 15, slice 1)."""
from __future__ import annotations

from ...core.i18n import E
from ...legacy.store import audit
from . import domain, repo


def _check_refs(c, entity: str, values: dict) -> dict | None:
    for field, target in domain.refs(entity).items():
        rid = values.get(field)
        if rid is not None and not repo.get(c, target, rid):
            return E("«{field}» sahəsində seçilən sətir tapılmadı", field=field)
    return None


def create(c, user, entity: str, body: dict):
    """('ok', id) | ('invalid', reason) | ('taken', None)."""
    values, problem = domain.clean(entity, body)
    problem = problem or domain.record_problem(entity, values) or _check_refs(c, entity, values)
    if problem:
        return "invalid", problem
    if repo.taken(c, entity, values[domain.UNIQUE[entity]]):
        return "taken", None
    rid = repo.insert(c, entity, values)
    audit(c, user["id"], "directory_create", entity, f"{rid} · {values[domain.UNIQUE[entity]]}")
    return "ok", rid


def update(c, user, entity: str, rid: int, body: dict):
    """('ok', None) | ('missing', None) | ('invalid', reason) | ('taken', None)."""
    current = repo.get(c, entity, rid)
    if not current:
        return "missing", None
    values, problem = domain.clean(entity, body, partial=True)
    merged = {**current, **values}
    problem = problem or domain.record_problem(entity, merged) or _check_refs(c, entity, values)
    if problem:
        return "invalid", problem
    key = domain.UNIQUE[entity]
    if key in values and repo.taken(c, entity, values[key], exclude=rid):
        return "taken", None
    if values:
        repo.update(c, entity, rid, values)
        changed = ", ".join(f"{k}: {current[k]} → {v}" for k, v in values.items() if current[k] != v)
        audit(c, user["id"], "directory_update", entity, f"{rid} · {changed or '-'}")
    return "ok", None


def set_active(c, user, entity: str, rid: int, active: bool) -> bool:
    if not repo.get(c, entity, rid):
        return False
    repo.update(c, entity, rid, {"active": int(active)})
    audit(c, user["id"], "directory_activate" if active else "directory_deactivate", entity, str(rid))
    return True
