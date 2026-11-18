"""Directory changes: validation, references, uniqueness and the audit log (tasks/todo.md, Task 15)."""
from __future__ import annotations

from ...core.i18n import E
from ...legacy.store import audit, now
from ..identity import service as identity
from . import domain, repo


def today() -> str:
    return now().date().isoformat()


def _check_refs(c, entity: str, values: dict) -> dict | None:
    roles = domain.ENTITIES[entity].get("ref_roles", {})
    for field, target in domain.refs(entity).items():
        rid = values.get(field)
        if rid is None:
            continue
        ref = repo.get(c, target, rid)
        if not ref:
            return E("«{field}» sahəsində seçilən sətir tapılmadı", field=field)
        if field in roles and ref["role"] not in roles[field]:
            return E("«{field}» sahəsində müəllim seçin", field=field)
    return None


def _taken(c, entity: str, values: dict, exclude: int | None = None) -> bool:
    return any(values.get(col) is not None and repo.taken(c, entity, col, values[col], exclude) for col in domain.unique(entity))


def _label(entity: str, values: dict) -> str:
    keys = domain.unique(entity)
    return str(values.get(keys[0]) if keys else values.get("name") or values.get("course_id") or "")


def create(c, user, entity: str, body: dict):
    """('ok', id) | ('invalid', reason) | ('taken', None)."""
    values, problem = domain.clean(entity, body)
    problem = problem or domain.record_problem(entity, values) or _check_refs(c, entity, values)
    if problem:
        return "invalid", problem
    if _taken(c, entity, values):
        return "taken", None
    rid = repo.insert(c, entity, values)
    audit(c, user["id"], "directory_create", entity, f"{rid} · {_label(entity, values)}")
    return "ok", rid


def update(c, user, entity: str, rid: int, body: dict):
    """('ok', None) | ('missing', None) | ('invalid', reason) | ('taken', None) | ('self', None)."""
    current = repo.get(c, entity, rid)
    if not current:
        return "missing", None
    values, problem = domain.clean(entity, body, partial=True)
    merged = {**current, **values}
    problem = problem or domain.record_problem(entity, merged) or _check_refs(c, entity, values)
    if problem:
        return "invalid", problem
    if _taken(c, entity, values, exclude=rid):
        return "taken", None
    changed = {k: v for k, v in values.items() if current[k] != v}
    if entity == "users" and "role" in changed:
        if rid == user["id"]:
            return "self", None                 # nobody takes their own administrator role away by accident
        identity.end_all_sessions(c, rid)       # a new role starts from a new sign-in
    if changed:
        repo.update(c, entity, rid, changed)
        audit(c, user["id"], "directory_update", entity, f"{rid} · " + ", ".join(f"{k}: {current[k]} → {v}" for k, v in changed.items()))
    return "ok", None


def set_active(c, user, entity: str, rid: int, active: bool) -> str:
    """'ok' | 'missing' | 'self'. A deactivated account can no longer sign in; its sessions end at once."""
    if not repo.get(c, entity, rid):
        return "missing"
    if entity == "users" and not active:
        if rid == user["id"]:
            return "self"
        identity.end_all_sessions(c, rid)
    repo.set_active(c, entity, rid, active)
    audit(c, user["id"], "directory_activate" if active else "directory_deactivate", entity, str(rid))
    return "ok"


def set_unit_groups(c, user, unit_id: int, group_ids) -> tuple[str, dict | None]:
    if not repo.get(c, "units", unit_id):
        return "missing", None
    if not isinstance(group_ids, list) or len(group_ids) > 50 or \
            any(isinstance(g, bool) or not isinstance(g, int) or g < 1 for g in group_ids):
        return "invalid", E("Qrupların siyahısı düzgün deyil")
    ids = sorted(set(group_ids))
    if ids and repo.existing_groups(c, ids) != set(ids):
        return "invalid", E("«{field}» sahəsində seçilən sətir tapılmadı", field="group_ids")
    repo.set_unit_groups(c, unit_id, ids)
    audit(c, user["id"], "directory_update", "units", f"{unit_id} · groups: {ids}")
    return "ok", None


# ---------------------------------------------------------------- enrolments (slice 2)
def enroll(c, user, course_id: int, body: dict) -> tuple[str, dict | None]:
    """'ok' | 'missing' | 'invalid' | 'taken'. Only an active student is enrolled; an enrolment is ended, never deleted."""
    if not repo.get(c, "courses", course_id):
        return "missing", None
    values, problem = domain.enrollment(body)
    if problem:
        return "invalid", problem
    student = repo.get(c, "users", values["user_id"])
    if not student or student["role"] != "student" or student["status"] != "active":
        return "invalid", E("Yalnız aktiv tələbə qeydiyyata alınır")
    if values["group_id"] and not repo.get(c, "groups", values["group_id"]):
        return "invalid", E("«{field}» sahəsində seçilən sətir tapılmadı", field="group_id")
    if repo.enrollment(c, course_id, values["user_id"]):
        return "taken", None
    repo.enroll(c, course_id, values)
    audit(c, user["id"], "enrollment_create", "course", f"{course_id} · {student['username']}")
    return "ok", None


def end_enrollment(c, user, course_id: int, user_id: int, end_date) -> tuple[str, dict | None]:
    e = repo.enrollment(c, course_id, user_id)
    if not e:
        return "missing", None
    problem = domain.date_problem("end_date", end_date)
    if problem:
        return "invalid", problem
    if e["begin_date"] and end_date <= e["begin_date"]:
        return "invalid", E("Bitmə tarixi başlanğıc tarixindən sonra olmalıdır")
    repo.end_enrollment(c, course_id, user_id, end_date)
    audit(c, user["id"], "enrollment_end", "course", f"{course_id} · #{user_id} · {end_date}")
    return "ok", None


# ---------------------------------------------------------------- status orders (slice 2)
def status_of(c, student_id: int) -> dict:
    events = repo.status_events(c, student_id)
    return {"status": domain.academic_status(events, today()), "events": events}


def record_status(c, user, student, values: dict) -> tuple[str, object]:
    """Write one status order: ('ok', event id) | ('invalid', reason). Leave, expulsion, transfer out and graduation end
    the student's open enrolments on the effective date: earlier attendance and grades stay; the account stays active,
    so a student on leave still signs in and sees their own documents."""
    if student["role"] != "student":
        return "invalid", E("Status əmri yalnız tələbəyə verilir")
    if values["to_group_id"]:
        group = repo.get(c, "groups", values["to_group_id"])
        if not group or not group["active"]:
            return "invalid", E("«{field}» sahəsində seçilən sətir tapılmadı", field="to_group_id")
    eid = repo.add_status_event(c, student["id"], values, student["group_id"], user["id"])
    if values["kind"] in domain.ENDS_STUDY:
        repo.end_open_enrollments(c, student["id"], values["effective_date"])
    if values["to_group_id"]:
        # shortcut: the group changes when the order is entered, also for a later effective date; a dated move waits for
        # the scheduler of Task 37
        repo.move_to_group(c, student["id"], values["to_group_id"])
    audit(c, user["id"], "status_" + values["kind"], "user",
          f"{student['username']} · №{values['order_no']} · {values['order_date']} → {values['effective_date']}")
    return "ok", eid


def current_term(c) -> dict | None:
    """For other modules (attendance limits, Radar, the syllabus): the term in progress or the last one begun."""
    return repo.current_term(c, today())
