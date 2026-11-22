"""The university's structure and registry (tasks/todo.md, Task 15): which fields each entity has and their rules. No I/O.

Field kinds: ``code`` (2-30 letters, digits, ``.``, ``_``, ``-``), ``code?`` (optional), ``text`` (2-200 characters),
``date`` (YYYY-MM-DD), ``year`` (1990-2100), ``int:lo:hi`` / ``int?:lo:hi``, ``ref:<entity>`` (a required id of another
entity), ``ref?:<entity>`` (optional), ``degree``, ``login`` (a user name), ``role``, ``email?``, ``unit_kind``;
for rooms (Task 18): ``ucode`` (a code kept in upper case: it is a URL and is printed on a QR sheet), ``short`` (1-30
characters, a door number), ``room_kind`` and ``flag`` (yes or no, stored as 1 or 0).
"""
from __future__ import annotations

import re
from datetime import date

from ...core.i18n import E
from ...core.perms import ROLES

PAGE = 50
DEGREES = ("bachelor", "master", "phd")
UNIT_KINDS = ("lecture", "seminar", "lab")             # mühazirə, məşğələ, laboratoriya
TEACHING_ROLES = ("teacher", "dept_head")
ROOM_KINDS = ("lecture_hall", "classroom", "lab", "computer_lab", "office", "other")
CODE = re.compile(r"^[0-9A-Za-zƏəİıÖöÜüĞğŞşÇç._-]{2,30}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")               # not week dates (2026-W01-1), which Python 3.11 also reads
LOGIN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,39}$")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
# What a user list or a saved user returns: never the password hash, the TOTP secret or the failure counters.
USER_COLUMNS = ("id, username, full_name, role, group_id, student_no, email, department_id, status, must_change, "
                "(status='active') AS active")

ENTITIES: dict[str, dict] = {
    "faculties": {"table": "faculties", "order": "name", "search": ("code", "name"), "unique": ("code",),
                  "fields": {"code": "code", "name": "text"}},
    "departments": {"table": "departments", "order": "name", "search": ("code", "name"), "unique": ("code",),
                    "fields": {"faculty_id": "ref:faculties", "code": "code", "name": "text"}, "filters": ("faculty_id",)},
    "specialties": {"table": "specialties", "order": "name", "search": ("code", "name"), "unique": ("code",),
                    "fields": {"faculty_id": "ref:faculties", "department_id": "ref?:departments", "code": "code",
                               "name": "text", "degree": "degree"}},
    "groups": {"table": "study_groups", "order": "name", "search": ("name",), "unique": ("name",), "stamps": False,
               "fields": {"name": "code", "year": "year", "faculty_id": "ref:faculties", "specialty_id": "ref?:specialties"}},
    "terms": {"table": "academic_terms", "order": "teaching_start DESC", "search": ("code", "name"), "unique": ("code",),
              "fields": {"code": "code", "name": "text", "teaching_start": "date", "teaching_end": "date",
                         "exam_start": "date", "exam_end": "date"}},
    # slice 2: people, courses (a course row of a term is the offering), teaching units
    "users": {"table": "users", "order": "full_name", "search": ("username", "full_name", "student_no", "email"),
              "unique": ("username", "email", "student_no"), "stamps": False, "columns": USER_COLUMNS,
              "active": ("status", "active", "disabled"), "perm": "users.manage", "filters": ("role", "group_id"),
              "fields": {"username": "login", "full_name": "text", "role": "role", "group_id": "ref?:groups",
                         "student_no": "code?", "email": "email?", "department_id": "ref?:departments"}},
    "courses": {"table": "courses", "order": "name", "search": ("code", "name"), "unique": (),
                "filters": ("term_id", "department_id", "teacher_id"), "ref_roles": {"teacher_id": TEACHING_ROLES},
                "fields": {"code": "code", "name": "text", "teacher_id": "ref?:users", "credits": "int:0:60",
                           "department_id": "ref?:departments", "term_id": "ref?:terms"}},
    "units": {"table": "teaching_units", "order": "id", "search": (), "unique": (), "filters": ("course_id",),
              "ref_roles": {"teacher_id": TEACHING_ROLES},
              "fields": {"course_id": "ref:courses", "kind": "unit_kind", "teacher_id": "ref?:users", "subgroup": "int?:1:9"}},
    # Task 18: buildings and rooms (a floor is a number of the room, not a table of its own)
    "buildings": {"table": "buildings", "order": "name", "search": ("code", "name"), "unique": ("code",),
                  "fields": {"code": "ucode", "name": "text", "address": "text?"}},
    "rooms": {"table": "rooms", "order": "code", "search": ("code", "number", "name"), "unique": ("code",), "filters": ("building_id",),
              "fields": {"building_id": "ref:buildings", "code": "ucode", "number": "short", "name": "text?", "floor": "int?:-5:200",
                         "kind": "room_kind", "capacity": "int?:0:5000", "accessible": "flag"}},
}


def unique(entity: str) -> tuple[str, ...]:
    return ENTITIES[entity]["unique"]


def active_column(entity: str) -> tuple[str, object, object]:
    """(column, value when active, value when not)."""
    return ENTITIES[entity].get("active", ("active", 1, 0))


def _int(field: str, v, lo: int, hi: int, optional: bool):
    if v in (None, "") and optional:
        return None, None
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        return None, E("«{field}» sahəsində {lo} ilə {hi} arasında tam ədəd olmalıdır", field=field, lo=lo, hi=hi)
    return v, None


def _value(kind: str, field: str, v):
    """(clean value, None) or (None, reason)."""
    if kind.startswith("ref"):
        optional = kind.startswith("ref?")
        if v in (None, "") and optional:
            return None, None
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            return None, E("«{field}» sahəsində mövcud bir sətir seçin", field=field)
        return v, None
    if kind == "year":
        if isinstance(v, bool) or not isinstance(v, int) or not 1990 <= v <= 2100:
            return None, E("«{field}» sahəsində il 1990 ilə 2100 arasında olmalıdır", field=field)
        return v, None
    if kind.startswith("int"):
        _, lo, hi = kind.split(":")
        return _int(field, v, int(lo), int(hi), kind.startswith("int?"))
    if kind == "flag":
        if v in (None, "", False, 0, "0"):
            return 0, None
        if v in (True, 1, "1"):
            return 1, None
        return None, E("«{field}» sahəsində bəli və ya xeyr seçin", field=field)
    if kind.endswith("?") and v in (None, ""):
        return None, None
    if not isinstance(v, str):
        return None, E("«{field}» sahəsi doldurulmalıdır", field=field)
    v = " ".join(v.split())
    if kind.rstrip("?") in ("code", "ucode") and not CODE.fullmatch(v):
        return None, E("«{field}» sahəsində kod 2–30 hərf, rəqəm, nöqtə, defis və ya alt xətdən ibarət olmalıdır", field=field)
    if kind == "ucode":
        v = v.upper()               # plain, not Azerbaijani, upper case: "it-101" stays ASCII in a URL ("IT-101")
    if kind.rstrip("?") == "text" and not 2 <= len(v) <= 200:
        return None, E("«{field}» sahəsi 2–200 simvol olmalıdır", field=field)
    if kind == "short" and not 1 <= len(v) <= 30:
        return None, E("«{field}» sahəsi 1–30 simvol olmalıdır", field=field)
    if kind == "room_kind" and v not in ROOM_KINDS:
        return None, E("Otağın növü düzgün deyil")
    if kind == "degree" and v not in DEGREES:
        return None, E("«{field}» sahəsində təhsil pilləsi bakalavriat, magistratura və ya doktorantura olmalıdır", field=field)
    if kind == "login":
        v = v.lower()
        if not LOGIN.fullmatch(v):
            return None, E("İstifadəçi adı 3–40 kiçik latın hərfi, rəqəm, nöqtə, defis və ya alt xətdən ibarət olmalıdır")
    if kind == "role" and v not in ROLES:
        return None, E("Naməlum rol")
    if kind == "email?":
        v = v.lower()
        if len(v) > 254 or not EMAIL.fullmatch(v):
            return None, E("E-poçt ünvanı düzgün deyil")
    if kind == "unit_kind" and v not in UNIT_KINDS:
        return None, E("Dərsin növü mühazirə, məşğələ və ya laboratoriya olmalıdır")
    if kind == "date":
        problem = date_problem(field, v)
        if problem:
            return None, problem
    return v, None


def field_value(kind: str, field: str, v):
    """One field checked by its kind (for other modules, e.g. the import of Task 16): (clean value, None) or (None, reason)."""
    return _value(kind, field, v)


def date_problem(field: str, v) -> dict | None:
    try:
        if not (isinstance(v, str) and DATE.fullmatch(v)):
            raise ValueError(v)
        date.fromisoformat(v)
        return None
    except (TypeError, ValueError):
        return E("«{field}» sahəsində tarix İİİİ-AA-GG formatında olmalıdır", field=field)


def clean(entity: str, body: dict, partial: bool = False) -> tuple[dict, dict | None]:
    """The entity's fields from a request body. ``partial``: only the fields that are present (an update)."""
    out = {}
    for field, kind in ENTITIES[entity]["fields"].items():
        if partial and field not in body:
            continue
        v, problem = _value(kind, field, body.get(field))
        if problem:
            return {}, problem
        out[field] = v
    return out, None


def record_problem(entity: str, record: dict) -> dict | None:
    """Rules across fields, checked on the whole record after an update is merged into it."""
    if entity == "terms":
        ts, te, es, ee = (record[k] for k in ("teaching_start", "teaching_end", "exam_start", "exam_end"))
        if not (ts < te and es <= ee):
            return E("Başlanğıc tarixi bitmə tarixindən əvvəl olmalıdır")
        if not te < es:
            return E("Tədris dövrü imtahan sessiyası başlamazdan əvvəl bitməlidir")
    if entity == "users" and record.get("role") != "student" and (record.get("group_id") or record.get("student_no")):
        return E("Qrup və tələbə bileti nömrəsi yalnız tələbəyə verilir")
    return None


def refs(entity: str) -> dict[str, str]:
    """{field: referenced entity} of the entity's reference fields."""
    return {f: k.split(":", 1)[1] for f, k in ENTITIES[entity]["fields"].items() if k.startswith("ref")}


# ---------------------------------------------------------------- enrolments and status orders (slice 2)
STATUS_KINDS = ("admission", "group_change", "transfer_in", "transfer_out", "academic_leave", "expulsion",
                "reinstatement", "graduation")
ENDS_STUDY = ("transfer_out", "academic_leave", "expulsion", "graduation")     # the enrolments end on the effective date
MOVES_GROUP = ("group_change", "transfer_in")                                   # these name the new group
STATUS_AFTER = {"admission": "active", "transfer_in": "active", "reinstatement": "active", "academic_leave": "on_leave",
                "expulsion": "expelled", "transfer_out": "transferred", "graduation": "graduated"}


def enrollment(body: dict) -> tuple[dict, dict | None]:
    """user_id, group_id (NULL: the student's own group), subgroup, begin_date from a request body."""
    out: dict = {}
    for field, kind in (("user_id", "ref:users"), ("group_id", "ref?:groups"), ("subgroup", "int?:1:9")):
        out[field], problem = _value(kind, field, body.get(field))
        if problem:
            return {}, problem
    begin = body.get("begin_date")
    if begin not in (None, ""):
        problem = date_problem("begin_date", begin)
        if problem:
            return {}, problem
    out["begin_date"] = begin or None
    return out, None


def status_event(body: dict) -> tuple[dict, dict | None]:
    """A status order from a request body: kind, order number, order date and effective date are all required."""
    kind = body.get("kind")
    if kind not in STATUS_KINDS:
        return {}, E("Əmrin növü düzgün deyil")
    order_no = " ".join(str(body.get("order_no") or "").split())
    if not 1 <= len(order_no) <= 50:
        return {}, E("Əmrin nömrəsini yazın")
    for field in ("order_date", "effective_date"):
        problem = date_problem(field, body.get(field)) if body.get(field) else E("«{field}» sahəsi doldurulmalıdır", field=field)
        if problem:
            return {}, problem
    to_group, problem = _value("ref?:groups", "to_group_id", body.get("to_group_id"))
    if problem:
        return {}, problem
    if kind in MOVES_GROUP and to_group is None:
        return {}, E("Yeni qrupu seçin")
    note = " ".join(str(body.get("note") or "").split())[:500] or None
    return {"kind": kind, "order_no": order_no, "order_date": body.get("order_date"), "effective_date": body.get("effective_date"),
            "to_group_id": to_group if kind in MOVES_GROUP else None, "note": note}, None


def academic_status(events: list[dict], today: str) -> str:
    """The student's status on ``today`` from their orders (by effective date, then entry order). No order: active."""
    status = "active"
    for ev in sorted(events, key=lambda e: (e["effective_date"], e["id"])):
        if ev["effective_date"] <= today:
            status = STATUS_AFTER.get(ev["kind"], status)
    return status
