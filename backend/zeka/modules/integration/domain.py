"""Import kinds (tasks/todo.md, Task 16): their columns (OneRoster 1.2 CSV names and Azerbaijani headings), the checks
of one row, and the hash a row is compared by. No I/O.

A row becomes a draft: clean values for the target table, plus references still written as the file gives them (a
group name, a department code, a source id), which the service resolves against what Zəka holds.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, timedelta

from ...core.i18n import E
from ..directory import domain as directory

SOURCE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._:@/-]{0,63}$")       # --source and sourcedId values
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# canonical column -> accepted headings (compared after lower-casing and collapsing spaces)
COLUMNS: dict[str, dict[str, tuple[str, ...]]] = {
    "users": {"sourcedId": ("sourcedid", "mənbə id"), "username": ("username", "istifadəçi adı"),
              "givenName": ("givenname", "ad"), "familyName": ("familyname", "soyad"), "middleName": ("middlename", "ata adı"),
              "role": ("role", "rol"), "identifier": ("identifier", "tələbə bileti №", "tələbə bileti", "bilet №"),
              "email": ("email", "e-poçt"), "group": ("group", "qrup"), "enabledUser": ("enableduser", "aktiv"),
              "department": ("department", "kafedra")},
    "orgs": {"sourcedId": ("sourcedid", "mənbə id"), "name": ("name", "ad"), "type": ("type", "növ"),
             "identifier": ("identifier", "kod"), "parentSourcedId": ("parentsourcedid", "üst təşkilat")},
    "terms": {"sourcedId": ("sourcedid", "mənbə id"), "title": ("title", "ad"), "identifier": ("identifier", "kod"),
              "startDate": ("startdate", "tədrisin başlanğıcı"), "endDate": ("enddate", "tədrisin sonu"),
              "examStartDate": ("examstartdate", "sessiyanın başlanğıcı"), "examEndDate": ("examenddate", "sessiyanın sonu")},
    "courses": {"sourcedId": ("sourcedid", "mənbə id"), "title": ("title", "ad"), "courseCode": ("coursecode", "kod"),
                "orgSourcedId": ("orgsourcedid", "kafedra"), "termSourcedId": ("termsourcedid", "schoolyearsourcedid", "semestr"),
                "credits": ("credits", "kredit"), "teacherSourcedId": ("teachersourcedid", "müəllim")},
    "classes": {"sourcedId": ("sourcedid", "mənbə id"), "courseSourcedId": ("coursesourcedid", "fənn"),
                "kind": ("kind", "növ"), "subgroup": ("subgroup", "yarımqrup"), "groups": ("groups", "qruplar")},
    "enrollments": {"sourcedId": ("sourcedid", "mənbə id"), "classSourcedId": ("classsourcedid", "tədris vahidi"),
                    "userSourcedId": ("usersourcedid", "istifadəçi"), "role": ("role", "rol"),
                    "beginDate": ("begindate", "başlanğıc"), "endDate": ("enddate", "bitmə")},
    "timetable": {"sourcedId": ("sourcedid", "mənbə id"), "courseSourcedId": ("coursesourcedid", "fənn"),
                  "weekday": ("weekday", "həftə günü"), "start": ("start", "başlanğıc"), "end": ("end", "son"),
                  "kind": ("kind", "növ"), "room": ("room", "otaq")},
}
REQUIRED = {
    "users": ("sourcedId", "username", "givenName", "familyName", "role"),
    "orgs": ("sourcedId", "name", "type", "identifier"),
    "terms": ("sourcedId", "title", "identifier", "startDate", "endDate", "examStartDate", "examEndDate"),
    "courses": ("sourcedId", "title", "courseCode"),
    "classes": ("sourcedId", "courseSourcedId"),
    "enrollments": ("sourcedId", "classSourcedId", "userSourcedId", "role"),
    "timetable": ("sourcedId", "courseSourcedId", "weekday", "start", "end"),
}
KINDS = (*COLUMNS, "teaching-load")
IMPORT_ROLES = {"student": "student", "tələbə": "student", "teacher": "teacher", "müəllim": "teacher"}
UNIT_KIND = {"lecture": "lecture", "mühazirə": "lecture", "seminar": "seminar", "məşğələ": "seminar", "lab": "lab",
             "laboratoriya": "lab", "scheduled": "lecture"}
KIND_LABEL = {"lecture": "Mühazirə", "seminar": "Məşğələ", "lab": "Laboratoriya"}      # the timetable keeps the label
ORG_TYPES = {"faculty": "faculties", "school": "faculties", "college": "faculties", "fakültə": "faculties",
             "department": "departments", "kafedra": "departments"}
YES = {"", "true", "1", "yes", "bəli", "hə"}
NO = {"false", "0", "no", "xeyr", "yox"}


AZ_LOWER = str.maketrans({"I": "ı", "İ": "i"})         # Python lowers İ to i + a combining dot


def norm(heading: str) -> str:
    """Lower case the Azerbaijani way (``FƏNNİN ADI`` -> ``fənnin adı``), spaces collapsed, no BOM."""
    return " ".join((heading or "").replace("\ufeff", "").translate(AZ_LOWER).lower().split())


def key(v: str) -> str:
    """The form values are compared in: ``norm`` with ı = i, so Latin capitals typed the English way (SEMINAR, sourcedId,
    MÜHAZIRƏ, FƏNNIN ADI) match their Azerbaijani spelling."""
    return norm(v).replace("ı", "i")


def _lookup(table: dict[str, str], v: str) -> str | None:
    return {key(k): x for k, x in table.items()}.get(key(v))


def header_map(kind: str, header: list[str]) -> tuple[dict[str, int], dict | None]:
    """{canonical column: index} for a header row, or the missing required columns."""
    wanted = {key(alias): col for col, aliases in COLUMNS[kind].items() for alias in aliases}
    found: dict[str, int] = {}
    for i, h in enumerate(header):
        col = wanted.get(key(h))
        if col and col not in found:
            found[col] = i
    missing = [c for c in REQUIRED[kind] if c not in found]
    if missing:
        return {}, E("Faylda məcburi sütunlar yoxdur: {cols}", cols=", ".join(missing))
    return found, None


def row_hash(values: dict | list) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def a_date(v: str) -> str | None:
    """YYYY-MM-DD, DD.MM.YYYY or an Excel day number as an ISO date; None when it is none of them."""
    v = v.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            return date.fromisoformat(v).isoformat()
        m = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", v)
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        if re.fullmatch(r"\d{5}(\.0+)?", v):
            return (date(1899, 12, 30) + timedelta(days=int(float(v)))).isoformat()
    except ValueError:
        return None
    return None


def an_int(v: str, lo: int, hi: int) -> int | None:
    try:
        n = float(v.strip().replace(",", "."))
    except ValueError:
        return None
    return int(n) if n.is_integer() and lo <= n <= hi else None


def _field(kind: str, name: str, v) -> tuple[object, dict | None]:
    return directory.field_value(kind, name, v)


def draft(kind: str, cells: dict[str, str]) -> tuple[dict, dict | None]:
    """The draft of one row of a kind (everything but teaching-load), or the reason it is refused."""
    sid = cells.get("sourcedId", "")
    if not SOURCE.fullmatch(sid):
        return {}, E("sourcedId 1–64 hərf, rəqəm və ._:@/- simvolları olmalıdır")
    return {"users": _user, "orgs": _org, "terms": _term, "courses": _course, "classes": _class,
            "enrollments": _enrollment, "timetable": _lesson}[kind](cells)


def _user(x: dict) -> tuple[dict, dict | None]:
    role = _lookup(IMPORT_ROLES, x.get("role", ""))
    if not role:
        return {}, E("Rol student və ya teacher olmalıdır")
    full = " ".join(f"{x.get('givenName', '')} {x.get('familyName', '')}".split())
    out: dict = {"role": role, "patronymic": " ".join(x.get("middleName", "").split()) or None}
    for name, kind, v in (("username", "login", x.get("username")), ("full_name", "text", full),
                          ("email", "email?", x.get("email") or None), ("student_no", "code?", x.get("identifier") or None)):
        out[name], problem = _field(kind, name, v)
        if problem:
            return {}, problem
    enabled = norm(x.get("enabledUser", ""))
    if enabled not in YES | NO:
        return {}, E("enabledUser true və ya false olmalıdır")
    out["status"] = "active" if enabled in YES else "disabled"
    if role == "student" and not out["student_no"]:
        return {}, E("Tələbənin bilet nömrəsi (identifier) yazılmalıdır")
    if role != "student" and (out["student_no"] or x.get("group")):
        return {}, E("Qrup və tələbə bileti nömrəsi yalnız tələbəyə verilir")
    out["_group"], out["_department"] = x.get("group") or None, x.get("department") or None
    return out, None


def _org(x: dict) -> tuple[dict, dict | None]:
    entity = _lookup(ORG_TYPES, x.get("type", ""))
    if not entity:
        return {}, E("Təşkilatın növü faculty və ya department olmalıdır")
    out: dict = {"_entity": entity, "_parent": x.get("parentSourcedId") or None}
    for name, kind, v in (("code", "code", x.get("identifier")), ("name", "text", x.get("name"))):
        out[name], problem = _field(kind, name, v)
        if problem:
            return {}, problem
    if entity == "departments" and not out["_parent"]:
        return {}, E("Kafedranın fakültəsi (parentSourcedId) yazılmalıdır")
    return out, None


def _term(x: dict) -> tuple[dict, dict | None]:
    out: dict = {}
    for name, kind, v in (("code", "code", x.get("identifier")), ("name", "text", x.get("title"))):
        out[name], problem = _field(kind, name, v)
        if problem:
            return {}, problem
    for name, col in (("teaching_start", "startDate"), ("teaching_end", "endDate"), ("exam_start", "examStartDate"),
                      ("exam_end", "examEndDate")):
        out[name] = a_date(x.get(col, ""))
        if not out[name]:
            return {}, E("«{field}» sahəsində tarix İİİİ-AA-GG formatında olmalıdır", field=col)
    return out, directory.record_problem("terms", out)


def _course(x: dict) -> tuple[dict, dict | None]:
    out: dict = {"_department": x.get("orgSourcedId") or None, "_term": x.get("termSourcedId") or None,
                 "_teacher": x.get("teacherSourcedId") or None}
    for name, kind, v in (("code", "code", x.get("courseCode")), ("name", "text", x.get("title"))):
        out[name], problem = _field(kind, name, v)
        if problem:
            return {}, problem
    credits = x.get("credits", "").strip()
    out["credits"] = an_int(credits, 0, 60) if credits else None
    if credits and out["credits"] is None:
        return {}, E("«{field}» sahəsində {lo} ilə {hi} arasında tam ədəd olmalıdır", field="credits", lo=0, hi=60)
    return out, None


def _class(x: dict) -> tuple[dict, dict | None]:
    kind = _lookup(UNIT_KIND, x.get("kind", "") or "lecture")
    if not kind:
        return {}, E("Dərsin növü mühazirə, məşğələ və ya laboratoriya olmalıdır")
    sub = x.get("subgroup", "").strip()
    subgroup = an_int(sub, 1, 9) if sub else None
    if sub and subgroup is None:
        return {}, E("«{field}» sahəsində {lo} ilə {hi} arasında tam ədəd olmalıdır", field="subgroup", lo=1, hi=9)
    groups = [g for g in re.split(r"[;,]", x.get("groups", "")) if g.strip()]
    return {"kind": kind, "subgroup": subgroup, "_course": x["courseSourcedId"], "_groups": [g.strip() for g in groups]}, None


def _enrollment(x: dict) -> tuple[dict, dict | None]:
    role = _lookup(IMPORT_ROLES, x.get("role", ""))
    if not role:
        return {}, E("Rol student və ya teacher olmalıdır")
    out: dict = {"_role": role, "_class": x["classSourcedId"], "_user": x["userSourcedId"]}
    for name, col in (("begin_date", "beginDate"), ("end_date", "endDate")):
        v = x.get(col, "").strip()
        out[name] = a_date(v) if v else None
        if v and not out[name]:
            return {}, E("«{field}» sahəsində tarix İİİİ-AA-GG formatında olmalıdır", field=col)
    if out["begin_date"] and out["end_date"] and out["end_date"] <= out["begin_date"]:
        return {}, E("Bitmə tarixi başlanğıc tarixindən sonra olmalıdır")
    return out, None


def _lesson(x: dict) -> tuple[dict, dict | None]:
    weekday = an_int(x.get("weekday", ""), 1, 7)
    if weekday is None:
        return {}, E("Həftə günü 1 ilə 7 arasında olmalıdır")
    start, end = x.get("start", "").strip(), x.get("end", "").strip()
    if not (TIME.fullmatch(start) and TIME.fullmatch(end) and start < end):
        return {}, E("Dərsin vaxtı SS:DD formatında olmalı və bitməsi başlanğıcından sonra olmalıdır")
    kind = _lookup(UNIT_KIND, x.get("kind", "") or "lecture")
    if not kind:
        return {}, E("Dərsin növü mühazirə, məşğələ və ya laboratoriya olmalıdır")
    room = " ".join(x.get("room", "").split())[:100] or None
    return {"weekday": weekday, "start": start, "end": end, "kind": KIND_LABEL[kind], "room": room,
            "_course": x["courseSourcedId"]}, None


# ---------------------------------------------------------------- activation codes
CODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"           # base32: 12 characters carry 60 bits


def csv_cell(v) -> str:
    """A cell of an exported CSV: text that a spreadsheet would run as a formula starts with a quote instead."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def code_hash(code: str) -> str:
    return hashlib.sha256("".join(code.upper().replace("-", "").split()).encode()).hexdigest()


def code_shape_ok(code: str) -> bool:
    c = "".join(code.upper().replace("-", "").split())
    return len(c) == 12 and all(ch in CODE_ALPHABET for ch in c)


def pretty_code(raw: str) -> str:
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"
