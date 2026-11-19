"""The structured syllabus (tasks/todo.md, Task 23): read, a first draft, a new version on every save."""
from __future__ import annotations

import json

from ...core import tenant
from ...core.i18n import E
from ...legacy.store import J, audit, iso, now
from . import domain, repo


def may_read(c, user, cid: int) -> bool:
    """The course's teachers, a department head whose grant covers it, and the readers of every course."""
    from ..journal import service as journal     # here: journal imports the legacy layer this module is loaded from
    return journal.can_read_course(c, user, cid)


def may_write(user, co: dict) -> bool:
    """The syllabus is the course head's: one author per course, the department head approves it (Task 25)."""
    return user["role"] == "teacher" and co["teacher_id"] == user["id"]


def _prereq(co: dict) -> list[str]:
    """The course's prerequisite field (Task 17) as the syllabus's first list."""
    return [p.strip() for p in str(co.get("prereq") or "").split(",") if p.strip() and p.strip() != "—"]


def imported(c, cid: int) -> dict[str, float]:
    return domain.workload_from_units(repo.units(c, cid))


def _version(v) -> dict | None:
    return {"id": v["id"], "version": v["version"], "status": v["status"], "created_at": v["created_at"], "data": J(v["data"], {})} if v else None


def state(c, user, cid: int) -> dict | None:
    co = repo.course(c, cid)
    if not co or not may_read(c, user, cid):
        return None
    latest, forma3 = _version(repo.latest(c, cid)), imported(c, cid)
    return {"course": {k: co[k] for k in ("id", "code", "name", "credits")}, "versions": repo.versions(c, cid), "latest": latest,
            "published": _version(repo.published(c, cid)), "imported": forma3,
            "diff": domain.workload_diff(latest["data"].get("workload", {}), forma3) if latest else [],
            "can_edit": may_write(user, co), "limit_percent": tenant.load(c)["attendance"]["limit_percent"]}


def draft(c, user, cid: int) -> dict | None:
    """A first draft, not saved: from a syllabus saved before Task 23, else from the syllabus assistant."""
    co = repo.course(c, cid)
    if not co or not may_write(user, co):
        return None
    old = repo.legacy(c, cid)
    gen = J(old["data"], None) if old else None
    if not isinstance(gen, dict):
        from ...legacy import r_academy         # the assistant stays as the first fill (Task 23)
        gen = r_academy.build_syllabus(c, co)
    return domain.initial(gen, tenant.load(c), imported(c, cid), _prereq(co))


def save(c, user, cid: int, body) -> tuple[str, object]:
    """('ok', state) | ('missing', None) | ('forbidden', reason) | ('invalid', reason) | ('stale', reason)."""
    co = repo.course(c, cid)
    if not co or not may_read(c, user, cid):
        return "missing", None
    if not may_write(user, co):
        return "forbidden", E("Sillabusu fənnin rəhbər müəllimi yazır")
    base, latest = body.get("base"), repo.latest(c, cid)
    if isinstance(base, int) and not isinstance(base, bool) and (latest["version"] if latest else 0) != base:
        return "stale", E("Bu müddətdə sillabusun yeni versiyası saxlanıb: səhifəni yeniləyin")
    clean, problem = domain.validate(body.get("data"), tenant.load(c))
    if problem:
        return "invalid", problem
    blob = json.dumps(clean, ensure_ascii=False)
    if len(blob) > 200_000:
        return "invalid", E("Sillabus çox böyükdür")
    repo.add_version(c, cid, blob, user["id"], iso(now()))
    audit(c, user["id"], "syllabus_saved", "course", f"{co['code']} · v{(latest['version'] if latest else 0) + 1}")
    return "ok", state(c, user, cid)


def version(c, user, cid: int, vid: int) -> dict | None:
    if not may_read(c, user, cid):
        return None
    return _version(repo.version(c, cid, vid))


def printable(c, user, cid: int, vid: int | None) -> tuple[dict, dict, dict | None] | None:
    """(course, syllabus data, version or None) for the printable page: the asked version, else the latest one, else an
    unsaved first draft (marked as such on the page)."""
    co = repo.course(c, cid)
    if not co:
        return None
    v = repo.version(c, cid, vid) if vid else repo.latest(c, cid)
    if v:
        return co, J(v["data"], {}), _version(v)
    old = repo.legacy(c, cid)
    gen = J(old["data"], None) if old else None
    if not isinstance(gen, dict):
        from ...legacy import r_academy
        gen = r_academy.build_syllabus(c, co)
    return co, domain.initial(gen, tenant.load(c), imported(c, cid), _prereq(co)), None
