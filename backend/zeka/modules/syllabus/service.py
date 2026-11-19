"""The structured syllabus (tasks/todo.md, Task 23): read, a first draft, a new version on every save."""
from __future__ import annotations

import json

from ...core import tenant
from ...core.i18n import E, T3
from ...legacy.store import J, audit, iso, notify, now
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
            "can_edit": may_write(user, co), "limit_percent": tenant.load(c)["attendance"]["limit_percent"],
            "actions": actions(c, user, co, repo.latest(c, cid)), "steps": repo.steps(c, latest["id"]) if latest else []}


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


# ---------------------------------------------------------------- approval and publication (Task 25)
def _covers(c, user, co: dict) -> bool:
    from ..journal import service as journal     # a department head's grant decides which courses are theirs (Task 13)
    return journal.may_correct(c, user, co)


def actions(c, user, co: dict, v: dict | None) -> list[str]:
    """The steps this user may take on this version now."""
    if not v:
        return []
    out = []
    for action in domain.STEPS:
        if domain.step(v["status"], action, user["role"]) is None:
            continue
        if user["role"] == "teacher" and not may_write(user, co):
            continue
        if user["role"] == "dept_head" and not _covers(c, user, co):
            continue
        out.append(action)
    return out


def act(c, user, cid: int, vid: int, action: str, body) -> tuple[str, object]:
    """('ok', state) | ('missing', None) | ('forbidden', reason) | ('invalid', reason) | ('blocked', reason)."""
    co, v = repo.course(c, cid), repo.version(c, cid, vid)
    if not co or not v or not may_read(c, user, cid):
        return "missing", None
    new = domain.step(v["status"], action, user["role"])
    if new is None or action not in actions(c, user, co, v):
        return "forbidden", E("Bu addım sizin rolunuzun növbəsi deyil")
    latest = repo.latest(c, cid)
    if action == "submit" and latest["id"] != vid:
        return "invalid", E("Yalnız son versiya təqdim olunur")
    note = " ".join(str(body.get("note") or "").split())[:1000]
    if action == "return" and len(note) < 3:
        return "invalid", E("Geri qaytarmanın səbəbini yazın")
    at = iso(now())
    if action == "publish":
        graded = repo.has_grades(c, cid)
        if graded and not (body.get("override") is True and len(note) >= 3):
            return "blocked", E("Bu fəndə artıq bal yazılıb: dərc üçün tədris şöbəsinin açıq icazəsi və səbəbi lazımdır")
        data, rules = J(v["data"], {}), tenant.load(c)
        modes, locked = domain.tutor_modes(data["rules"]["ai_policy"])
        repo.publish_course(c, cid, json.dumps(domain.course_grading(data, rules["grading"]), ensure_ascii=False),
                            data["rules"]["attendance_limit"], json.dumps(modes), locked)
        from ..journal import service as journal
        journal.refresh_finals(c, cid, repo.students(c, cid))      # the course's components and limit changed
        if graded:
            audit(c, user["id"], "syllabus_publish_override", "course", f"{co['code']} · v{v['version']} · {note}")
    repo.set_status(c, vid, new, note, user["id"], at)
    repo.add_step(c, vid, action, user["id"], note, at)
    audit(c, user["id"], f"syllabus_{action}", "course", f"{co['code']} · v{v['version']}" + (f" · {note}" if note else ""))
    if action in ("return", "publish") and v["author_id"]:
        title = (T3("Sillabus geri qaytarıldı: {course}", course=co["name"]) if action == "return"
                 else T3("Sillabus dərc olundu: {course}", course=co["name"]))
        notify(c, [v["author_id"]], "syllabus", title, note, f"/teacher/syllabus?course={cid}")
    return "ok", state(c, user, cid)


def queue(c, user) -> list[dict]:
    """The versions waiting for this user: submitted ones for a department head (of the courses the grant covers),
    approved ones for the academic office; an administrator sees both."""
    statuses = {"dept_head": ("submitted",), "academic_office": ("approved",), "admin": ("submitted", "approved")}.get(user["role"], ())
    out = []
    for status in statuses:
        for v in repo.pending(c, status):
            if user["role"] == "dept_head" and not _covers(c, user, {"id": v["course_id"], "department_id": v["department_id"]}):
                continue
            data, pub = J(v["data"], {}), repo.published(c, v["course_id"])
            co = repo.course(c, v["course_id"])
            out.append({k: v[k] for k in ("id", "course_id", "version", "status", "created_at", "code", "name", "author")} |
                       {"actions": actions(c, user, co, v), "published_id": pub["id"] if pub else None} |
                       {"forma3": domain.workload_diff(data.get("workload", {}), imported(c, v["course_id"])),
                        "changes": len(domain.diff(J(pub["data"], {}), data)) if pub else None})
    return out


def compare(c, user, cid: int, a: int, b: int) -> list[dict] | None:
    va, vb = repo.version(c, cid, a), repo.version(c, cid, b)
    if not va or not vb or not may_read(c, user, cid):
        return None
    return domain.diff(J(va["data"], {}), J(vb["data"], {}))


def published_for(c, user, cid: int) -> dict | None:
    """The published syllabus of a course: what its students see (only that version), and its staff."""
    if user["role"] == "student":
        if not repo.enrolled(c, cid, user["id"]):
            return None
    elif not may_read(c, user, cid):
        return None
    return _version(repo.published(c, cid))
