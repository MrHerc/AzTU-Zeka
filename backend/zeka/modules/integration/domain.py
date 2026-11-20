"""Import kinds (tasks/todo.md, Task 16): their columns (OneRoster 1.2 CSV names and Azerbaijani headings), the checks
of one row, and the hash a row is compared by. No I/O.

A row becomes a draft: clean values for the target table, plus references still written as the file gives them (a
group name, a department code, a source id), which the service resolves against what Zəka holds.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta

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
    # Task 18: not a OneRoster kind; the university's own room list
    "rooms": {"sourcedId": ("sourcedid", "mənbə id"), "identifier": ("identifier", "kod"), "number": ("number", "nömrə", "otaq"),
              "name": ("name", "ad"), "building": ("building", "korpus"), "floor": ("floor", "mərtəbə"), "kind": ("kind", "növ"),
              "capacity": ("capacity", "tutum", "yer sayı"), "accessible": ("accessible", "əlçatan")},
    # Task 20: an opening balance per student, course and term; the source key is the three source ids together
    "attendance-opening": {"termSourcedId": ("termsourcedid", "semestr"), "courseSourcedId": ("coursesourcedid", "fənn"),
                           "userSourcedId": ("usersourcedid", "tələbə"), "heldHours": ("heldhours", "keçilmiş saat"),
                           "unexcusedHours": ("unexcusedhours", "üzrsüz qayıb saatı"), "excusedHours": ("excusedhours", "üzrlü qayıb saatı"),
                           "asOf": ("asof", "tarix", "kəsid tarixi")},
    # Task 21: a score per student, course and component (the source key is the three together)
    "grades": {"courseSourcedId": ("coursesourcedid", "fənn"), "userSourcedId": ("usersourcedid", "tələbə"),
               "component": ("component", "komponent"), "score": ("score", "bal"), "max": ("max", "maksimum"),
               "asOf": ("asof", "tarix")},
    # Task 38: a lesson record of the old system up to the cut-over (the source key: class, student, day and start)
    "attendance": {"classSourcedId": ("classsourcedid", "tədris vahidi"), "userSourcedId": ("usersourcedid", "tələbə"),
                   "date": ("date", "tarix"), "start": ("start", "başlanğıc"), "status": ("status", "qeyd"),
                   "end": ("end", "son"), "hours": ("hours", "saat"), "asOf": ("asof", "kəsid tarixi")},
    # Task 38: a final grade of a term before Zəka, for the transcript (the source key: student, course code and term)
    "results": {"userSourcedId": ("usersourcedid", "tələbə"), "courseCode": ("coursecode", "fənnin kodu"),
                "courseTitle": ("coursetitle", "fənn"), "courseTitleEn": ("coursetitleen", "fənn (en)"),
                "termTitle": ("termtitle", "semestr"), "termTitleEn": ("termtitleen", "semestr (en)"),
                "termStart": ("termstart", "semestrin başlanğıcı"), "credits": ("credits", "kredit"), "score": ("score", "bal")},
    # Task 38: a status order given in the old system (the source key: student, order number and order date)
    "status-events": {"userSourcedId": ("usersourcedid", "tələbə"), "kind": ("kind", "növ"),
                      "orderNo": ("orderno", "əmr №", "əmrin nömrəsi"), "orderDate": ("orderdate", "əmrin tarixi"),
                      "effectiveDate": ("effectivedate", "qüvvəyə minmə tarixi"), "group": ("group", "qrup"),
                      "note": ("note", "qeyd")},
}
REQUIRED = {
    "users": ("sourcedId", "username", "givenName", "familyName", "role"),
    "orgs": ("sourcedId", "name", "type", "identifier"),
    "terms": ("sourcedId", "title", "identifier", "startDate", "endDate", "examStartDate", "examEndDate"),
    "courses": ("sourcedId", "title", "courseCode"),
    "classes": ("sourcedId", "courseSourcedId"),
    "enrollments": ("sourcedId", "classSourcedId", "userSourcedId", "role"),
    "timetable": ("sourcedId", "courseSourcedId", "weekday", "start", "end"),
    "rooms": ("sourcedId", "identifier", "number", "building"),
    # asOf: a column, or --as-of for the whole file (Task 38)
    "attendance-opening": ("termSourcedId", "courseSourcedId", "userSourcedId", "heldHours", "unexcusedHours", "excusedHours"),
    "grades": ("courseSourcedId", "userSourcedId", "component", "score"),
    "attendance": ("classSourcedId", "userSourcedId", "date", "start", "status"),
    "results": ("userSourcedId", "courseCode", "courseTitle", "termTitle", "termStart", "credits", "score"),
    "status-events": ("userSourcedId", "kind", "orderNo", "orderDate", "effectiveDate"),
}
KINDS = (*COLUMNS, "teaching-load")
JOURNAL_KINDS = ("attendance", "attendance-opening", "grades")      # their rows carry the export's cut-over date (as_of)
MARKS = {"present": "present", "iştirak": "present", "+": "present", "absent": "absent", "qayıb": "absent", "-": "absent",
         "late": "late", "gecikmə": "late", "excused": "excused", "üzrlü": "excused"}
IMPORT_ROLES = {"student": "student", "tələbə": "student", "teacher": "teacher", "müəllim": "teacher"}
UNIT_KIND = {"lecture": "lecture", "mühazirə": "lecture", "seminar": "seminar", "məşğələ": "seminar", "lab": "lab",
             "laboratoriya": "lab", "scheduled": "lecture"}
KIND_LABEL = {"lecture": "Mühazirə", "seminar": "Məşğələ", "lab": "Laboratoriya"}      # the timetable keeps the label
ORG_TYPES = {"faculty": "faculties", "school": "faculties", "college": "faculties", "fakültə": "faculties",
             "department": "departments", "kafedra": "departments"}
ROOM_KIND = {k: k for k in directory.ROOM_KINDS} | {"mühazirə zalı": "lecture_hall", "auditoriya": "classroom",
                                                    "laboratoriya": "lab", "kompüter laboratoriyası": "computer_lab",
                                                    "otaq": "office", "ofis": "office", "digər": "other"}
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
    if kind == "attendance-opening":
        return _opening(cells)
    if kind == "grades":
        return _grade(cells)
    if kind in ("attendance", "results", "status-events"):
        return {"attendance": _mark, "results": _result, "status-events": _status_event}[kind](cells)
    sid = cells.get("sourcedId", "")
    if not SOURCE.fullmatch(sid):
        return {}, E("sourcedId 1–64 hərf, rəqəm və ._:@/- simvolları olmalıdır")
    return {"users": _user, "orgs": _org, "terms": _term, "courses": _course, "classes": _class,
            "enrollments": _enrollment, "timetable": _lesson, "rooms": _room}[kind](cells)


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


def _room(x: dict) -> tuple[dict, dict | None]:
    out: dict = {"_building": (x.get("building") or "").strip().upper()}
    for name, kind, v in (("code", "ucode", x.get("identifier")), ("number", "short", x.get("number")),
                          ("name", "text?", x.get("name") or None)):
        out[name], problem = _field(kind, name, v)
        if problem:
            return {}, problem
    for name, lo, hi in (("floor", -5, 200), ("capacity", 0, 5000)):
        v = x.get(name, "").strip()
        out[name] = an_int(v, lo, hi) if v else None
        if v and out[name] is None:
            return {}, E("«{field}» sahəsində {lo} ilə {hi} arasında tam ədəd olmalıdır", field=name, lo=lo, hi=hi)
    out["kind"] = _lookup(ROOM_KIND, x.get("kind", "") or "classroom")
    if not out["kind"]:
        return {}, E("Otağın növü düzgün deyil")
    accessible = norm(x.get("accessible", "") or "no")
    if accessible not in YES | NO:
        return {}, E("«{field}» sahəsində bəli və ya xeyr seçin", field="accessible")
    out["accessible"] = int(accessible in YES)
    return out, None


COMPOSITE_KEYS = {"attendance-opening": ("termSourcedId", "courseSourcedId", "userSourcedId"),
                  "grades": ("courseSourcedId", "userSourcedId", "component"),
                  "attendance": ("classSourcedId", "userSourcedId", "date", "start"),
                  "results": ("userSourcedId", "courseCode", "termTitle"),
                  "status-events": ("userSourcedId", "orderNo", "orderDate")}
DATE_PARTS = ("date", "orderDate")           # written the same in the key however the export writes them


def source_key(kind: str, cells: dict) -> str:
    """The source key of a kind without a sourcedId column: its parts together."""
    return "|".join((a_date(cells.get(k, "")) if k in DATE_PARTS else None) or " ".join(cells.get(k, "").split())
                    for k in COMPOSITE_KEYS[kind])


def _number(v: str) -> float | None:
    try:
        n = float((v or "").strip().replace(",", "."))
    except ValueError:
        return None
    return n if n == n and abs(n) != float("inf") else None


def _grade(x: dict) -> tuple[dict, dict | None]:
    for k in ("courseSourcedId", "userSourcedId"):
        if not SOURCE.fullmatch(x.get(k, "")):
            return {}, E("«{field}» sahəsində mənbə id-si 1–64 hərf, rəqəm və ._:@/- simvolları olmalıdır", field=k)
    component = " ".join(x.get("component", "").split())
    if not 1 <= len(component) <= 100:
        return {}, E("«{field}» sahəsi doldurulmalıdır", field="component")
    score = _number(x.get("score", ""))
    if score is None or score < 0:
        return {}, E("Bal rəqəm olmalıdır")
    maximum = _number(x["max"]) if x.get("max", "").strip() else None
    if x.get("max", "").strip() and maximum is None:
        return {}, E("«{field}» sahəsində rəqəm olmalıdır", field="max")
    as_of = a_date(x["asOf"]) if x.get("asOf", "").strip() else None
    if x.get("asOf", "").strip() and not as_of:
        return {}, E("«{field}» sahəsində tarix İİİİ-AA-GG formatında olmalıdır", field="asOf")
    return {"_course": x["courseSourcedId"], "_user": x["userSourcedId"], "component": component, "score": round(score, 2),
            "_max": maximum, "_as_of": as_of}, None


def _opening(x: dict) -> tuple[dict, dict | None]:
    for k in ("termSourcedId", "courseSourcedId", "userSourcedId"):
        if not SOURCE.fullmatch(x.get(k, "")):
            return {}, E("«{field}» sahəsində mənbə id-si 1–64 hərf, rəqəm və ._:@/- simvolları olmalıdır", field=k)
    out: dict = {"_term": x["termSourcedId"], "_course": x["courseSourcedId"], "_user": x["userSourcedId"]}
    for name, col in (("held_hours", "heldHours"), ("unexcused_hours", "unexcusedHours"), ("excused_hours", "excusedHours")):
        out[name] = an_int(x.get(col, ""), 0, 5000)
        if out[name] is None:
            return {}, E("«{field}» sahəsində {lo} ilə {hi} arasında tam ədəd olmalıdır", field=col, lo=0, hi=5000)
    if out["unexcused_hours"] + out["excused_hours"] > out["held_hours"]:
        return {}, E("Buraxılmış saatlar keçilmiş saatlardan çox ola bilməz")
    out["as_of"] = a_date(x.get("asOf", ""))
    if not out["as_of"]:
        return {}, E("«{field}» sahəsində tarix İİİİ-AA-GG formatında olmalıdır", field="asOf")
    return out, None


# ---------------------------------------------------------------- the old system's journal and orders (Task 38)
def _refs(x: dict, *cols: str) -> dict | None:
    for k in cols:
        if not SOURCE.fullmatch(x.get(k, "")):
            return E("«{field}» sahəsində mənbə id-si 1–64 hərf, rəqəm və ._:@/- simvolları olmalıdır", field=k)
    return None


def _day(x: dict, col: str) -> tuple[str | None, dict | None]:
    day = a_date(x.get(col, ""))
    return day, (None if day else E("«{field}» sahəsində tarix İİİİ-AA-GG formatında olmalıdır", field=col))


def _mark(x: dict) -> tuple[dict, dict | None]:
    problem = _refs(x, "classSourcedId", "userSourcedId")
    day, bad_day = _day(x, "date")
    if problem or bad_day:
        return {}, problem or bad_day
    start, end = x.get("start", "").strip(), x.get("end", "").strip() or None
    if not TIME.fullmatch(start) or (end and not (TIME.fullmatch(end) and start < end)):
        return {}, E("Dərsin vaxtı SS:DD formatında olmalı və bitməsi başlanğıcından sonra olmalıdır")
    hours = an_int(x["hours"], 1, 12) if x.get("hours", "").strip() else None
    if x.get("hours", "").strip() and hours is None:
        return {}, E("«{field}» sahəsində {lo} ilə {hi} arasında tam ədəd olmalıdır", field="hours", lo=1, hi=12)
    status = _lookup(MARKS, x.get("status", ""))
    if not status:
        return {}, E("Qeyd iştirak, qayıb, gecikmə və ya üzrlü olmalıdır")
    as_of = a_date(x.get("asOf", ""))
    if not as_of:
        return {}, E("Kəsid tarixi yoxdur: onu --as-of ilə və ya «asOf» sütununda verin")
    if day > as_of:                                    # type: ignore[operator]  # day is a date here
        return {}, E("Dərsin tarixi kəsid tarixindən sonradır")
    return {"_class": x["classSourcedId"], "_user": x["userSourcedId"], "day": day, "start": start, "_end": end, "_hours": hours,
            "status": status, "_as_of": as_of}, None


def _result(x: dict) -> tuple[dict, dict | None]:
    problem = _refs(x, "userSourcedId")
    start, bad_day = _day(x, "termStart")
    if problem or bad_day:
        return {}, problem or bad_day
    text = {k: " ".join(x.get(col, "").split()) for k, col in (("course_code", "courseCode"), ("course_name", "courseTitle"),
                                                              ("course_name_en", "courseTitleEn"), ("term_name", "termTitle"),
                                                              ("term_name_en", "termTitleEn"))}
    for k, col, most in (("course_code", "courseCode", 40), ("course_name", "courseTitle", 200), ("term_name", "termTitle", 100)):
        if not 1 <= len(text[k]) <= most:
            return {}, E("«{field}» sahəsi doldurulmalıdır", field=col)
    credits = an_int(x.get("credits", ""), 0, 60)
    if credits is None:
        return {}, E("«{field}» sahəsində {lo} ilə {hi} arasında tam ədəd olmalıdır", field="credits", lo=0, hi=60)
    score = _number(x.get("score", ""))
    if score is None or not 0 <= score <= 100:
        return {}, E("Bal 0 ilə {max} arasında olmalıdır", max=100)
    return {"_user": x["userSourcedId"], "course_code": text["course_code"], "course_name": text["course_name"],
            "course_name_en": text["course_name_en"][:200] or None, "term_name": text["term_name"],
            "term_name_en": text["term_name_en"][:100] or None, "term_start": start, "credits": credits, "score": round(score, 2)}, None


def _status_event(x: dict) -> tuple[dict, dict | None]:
    problem = _refs(x, "userSourcedId")
    order_date, bad_order = _day(x, "orderDate")
    effective, bad_effective = _day(x, "effectiveDate")
    if problem or bad_order or bad_effective:
        return {}, problem or bad_order or bad_effective
    return {"_user": x["userSourcedId"], "kind": key(x.get("kind", "")), "order_no": x.get("orderNo", ""), "order_date": order_date,
            "effective_date": effective, "_group": " ".join(x.get("group", "").split()) or None, "note": x.get("note", "")}, None


# ---------------------------------------------------------------- activation codes
CODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"           # base32: 12 characters carry 60 bits


def csv_cell(v) -> str:
    """A cell of an exported CSV: text that a spreadsheet would run as a formula starts with a quote instead."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def moment(text: str | None) -> datetime | None:
    """``--since`` / ``?since=`` (Task 37): an ISO 8601 date-time, best with an offset; without one it is the university's
    wall clock. None when empty; ValueError when it is not a date-time. A query string turns the ``+`` of ``+04:00`` into
    a space, which is put back."""
    v = (text or "").strip()
    if not v:
        return None
    if "T" in v:
        v = re.sub(r" (\d\d:?\d\d)$", r"+\1", v)
    t = datetime.fromisoformat(v[:-1] + "+00:00" if v[-1:] in "Zz" else v)          # Python 3.10 does not read Z
    if not 1900 <= t.year <= 2999:                  # 0001-01-01T00:00+04:00 overflowed later, in the export (PY-E2)
        raise ValueError(text)
    return t


def code_hash(code: str) -> str:
    return hashlib.sha256("".join(code.upper().replace("-", "").split()).encode()).hexdigest()


def code_shape_ok(code: str) -> bool:
    c = "".join(code.upper().replace("-", "").split())
    return len(c) == 12 and all(ch in CODE_ALPHABET for ch in c)


def pretty_code(raw: str) -> str:
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"
