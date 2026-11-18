"""The university's structure (tasks/todo.md, Task 15, slice 1): which fields each entity has and their rules. No I/O.

Field kinds: ``code`` (2-30 letters, digits, ``.``, ``_``, ``-``), ``text`` (2-200 characters), ``date`` (YYYY-MM-DD),
``year`` (1990-2100), ``ref:<entity>`` (a required id of another entity), ``ref?:<entity>`` (optional), ``degree``.
"""
from __future__ import annotations

import re
from datetime import date

from ...core.i18n import E

PAGE = 50
DEGREES = ("bachelor", "master", "phd")
CODE = re.compile(r"^[0-9A-Za-zƏəİıÖöÜüĞğŞşÇç._-]{2,30}$")

ENTITIES: dict[str, dict] = {
    "faculties": {"table": "faculties", "order": "name", "search": ("code", "name"),
                  "fields": {"code": "code", "name": "text"}},
    "departments": {"table": "departments", "order": "name", "search": ("code", "name"),
                    "fields": {"faculty_id": "ref:faculties", "code": "code", "name": "text"}},
    "specialties": {"table": "specialties", "order": "name", "search": ("code", "name"),
                    "fields": {"faculty_id": "ref:faculties", "department_id": "ref?:departments", "code": "code",
                               "name": "text", "degree": "degree"}},
    "groups": {"table": "study_groups", "order": "name", "search": ("name",),
               "fields": {"name": "code", "year": "year", "faculty_id": "ref:faculties", "specialty_id": "ref?:specialties"}},
    "terms": {"table": "academic_terms", "order": "teaching_start DESC", "search": ("code", "name"),
              "fields": {"code": "code", "name": "text", "teaching_start": "date", "teaching_end": "date",
                         "exam_start": "date", "exam_end": "date"}},
}
UNIQUE = {"faculties": "code", "departments": "code", "specialties": "code", "groups": "name", "terms": "code"}


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
    if not isinstance(v, str):
        return None, E("«{field}» sahəsi doldurulmalıdır", field=field)
    v = " ".join(v.split())
    if kind == "code" and not CODE.fullmatch(v):
        return None, E("«{field}» sahəsində kod 2–30 hərf, rəqəm, nöqtə, defis və ya alt xətdən ibarət olmalıdır", field=field)
    if kind == "text" and not 2 <= len(v) <= 200:
        return None, E("«{field}» sahəsi 2–200 simvol olmalıdır", field=field)
    if kind == "degree" and v not in DEGREES:
        return None, E("«{field}» sahəsində dərəcə bakalavr, magistr və ya doktorantura olmalıdır", field=field)
    if kind == "date":
        try:
            date.fromisoformat(v)
        except ValueError:
            return None, E("«{field}» sahəsində tarix İİİİ-AA-GG formatında olmalıdır", field=field)
    return v, None


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
    return None


def refs(entity: str) -> dict[str, str]:
    """{field: referenced entity} of the entity's reference fields."""
    return {f: k.split(":", 1)[1] for f, k in ENTITIES[entity]["fields"].items() if k.startswith("ref")}
