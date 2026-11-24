"""Exports (tasks/todo.md, Task 37): the one export service. The screen (``routes.py``) and ``manage.py export`` both
call ``run``; there is no second path. Like ``repo.py`` this file holds SQL; table names in it are constants.

- OneRoster 1.2-style CSV files (``oneroster_files``) in the columns of the Task 16 importer, which reads them back.
  A row's sourcedId is the id the first import linked it to (``import_links``), else ``zeka:<table>:<id>``.
- Grades and attendance as CSV; with ``since`` only the rows written or changed after that moment (``updated_at``,
  ``marked_at``: the university's naive wall clock, ``store.now()``).
- A register of students or users with columns chosen from a fixed list.
- The change list for the "Tələbə-məzun" operator: status orders entered after a moment, with the days left to report.
- The timetable (Task 48): a version's placements, or the rows in force of a term (``timetable.service.export_rows``).
"""
from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta

from ...core import clock
from ...core.i18n import E
from ...legacy.store import audit, iso, now, row, rows
from ..timetable import domain as timetable_rules
from ..timetable import service as timetable
from . import domain

KINDS = ("grades", "attendance", "oneroster", "registry", "status-changes", "timetable")
HTTP_CAP = 300_000         # rows of grades or attendance in one HTTP export; more: since, or manage.py export (AR-E1)
FILES = ("orgs", "terms", "users", "courses", "classes", "enrollments")      # also the order they are imported in
# Assumption (SPEC Open Questions 17): the 10 days to report a status order to "Tələbə-məzun" are counted from the
# order's date (order_date), not from its effective date or from when it was entered; to be checked against Decree No. 225.
REPORT_DAYS = 10
# the import kinds whose links name a row of the table; "unit_teachers" links name an enrolment row, not a class
LINKS = {"users": ("users",), "faculties": ("faculties",), "departments": ("departments",), "academic_terms": ("terms",),
         "courses": ("courses",), "teaching_units": ("classes", "teaching_load")}
GRADE_COLUMNS = ("courseSourcedId", "courseCode", "userSourcedId", "identifier", "component", "score", "max", "status", "source",
                 "updatedAt")
ATTENDANCE_COLUMNS = ("courseSourcedId", "courseCode", "userSourcedId", "identifier", "lessonId", "lessonDate", "lessonStart",
                      "status", "source", "markedAt")
STATUS_COLUMNS = ("id", "student_no", "full_name", "grp", "kind", "order_no", "order_date", "effective_date", "deadline",
                  "days_left", "created_at", "reported_at")
# register -> (the rest of its query, {column: SQL expression}); the screen and the command choose columns from these only
REGISTRY: dict[str, tuple[str, dict[str, str]]] = {
    "students": ("FROM users u LEFT JOIN study_groups g ON g.id=u.group_id LEFT JOIN faculties f ON f.id=g.faculty_id "
                 "LEFT JOIN specialties sp ON sp.id=g.specialty_id WHERE u.role='student' ORDER BY g.name, u.full_name, u.id",
                 {"student_no": "u.student_no", "full_name": "u.full_name", "patronymic": "u.patronymic", "username": "u.username",
                  "email": "u.email", "group": "g.name", "faculty": "f.code", "specialty": "sp.code",
                  "admission_year": "u.admission_year", "funding": "u.funding", "form": "u.form", "status": "u.status"}),
    "users": ("FROM users u LEFT JOIN departments d ON d.id=u.department_id ORDER BY u.role, u.full_name, u.id",
              {"username": "u.username", "full_name": "u.full_name", "patronymic": "u.patronymic", "role": "u.role",
               "email": "u.email", "department": "d.code", "status": "u.status"}),
}


def _wall(t: datetime) -> str:
    """A moment in the stored form: the university's naive wall clock to the second (a moment without a zone already is).
    Microseconds are dropped, so a row of the same second is included rather than lost."""
    if t.tzinfo:
        t = t.astimezone(clock.zone()).replace(tzinfo=None)          # never the host's own time (WF27F-4)
    return iso(t.replace(microsecond=0))


def _cell(v) -> str:
    if v is None:
        return ""
    return str(v) if isinstance(v, (int, float)) else domain.csv_cell(v)


def _csv(columns: tuple[str, ...], data: list[dict]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(columns)
    w.writerows([[_cell(r.get(k)) for k in columns] for r in data])
    return out.getvalue()


def _sids(c, table: str, ids) -> dict[int, str]:
    """{row id: sourcedId}: the source id of the row's first import link, else ``zeka:<table>:<id>``; an id two rows
    share (linked from two source systems) falls back to the Zəka form for both, in every export alike (Checkpoint E)."""
    if not ids:                                     # nothing to name: no read of the link table (AR-E13)
        return {}
    kinds = LINKS[table]
    linked: dict[int, str] = {}
    for r in rows(c, f"SELECT row_id, source_id FROM import_links WHERE kind IN ({','.join('?' * len(kinds))}) ORDER BY id", kinds):  # nosec B608
        linked.setdefault(r["row_id"], r["source_id"])
    twice = {s for s, n in Counter(linked.values()).items() if n > 1}
    return {i: linked[i] if linked.get(i) and linked[i] not in twice else f"zeka:{table}:{i}" for i in ids}


def _enrolment_sid(class_sid: str, user_sid: str, role: str) -> str:
    """Derived from the class and the person, so the same enrolment keeps its id through an export and import."""
    return "zeka:enr:" + hashlib.sha256(f"{class_sid}|{user_sid}|{role}".encode()).hexdigest()[:24]


# ---------------------------------------------------------------- OneRoster
def oneroster_files(c, report: dict | None = None) -> dict[str, str]:
    """{file name: CSV text} in the columns of the import kinds. Every row is exported, deactivated ones too (the
    importer has no active flag). Students and teachers only; a reference to anything not exported is left empty.

    Enrolments are per class: a student is listed for each teaching unit of the course they attend (the unit's groups
    and subgroup, ``timetable.domain.attends``), the unit's teacher as role teacher. The importer keeps one enrolment
    per student and course, with the group of the first row when that unit has one group; so the rows of one-group
    units come first. Shortcut: an enrolment in a course with no unit the student attends is not listed, and one with
    another group attended only through units of several groups comes back with the student's own group (a OneRoster
    enrolment names no group); upgrade when a receiving system needs those."""
    fac = rows(c, "SELECT id, code, name FROM faculties ORDER BY id")
    dep = rows(c, "SELECT id, faculty_id, code, name FROM departments ORDER BY id")
    terms = rows(c, "SELECT id, code, name, teaching_start, teaching_end, exam_start, exam_end FROM academic_terms ORDER BY id")
    people = rows(c, "SELECT u.id, u.username, u.full_name, u.patronymic, u.role, u.student_no, u.email, u.status, g.name grp, "
                     "d.code dep FROM users u LEFT JOIN study_groups g ON g.id=u.group_id LEFT JOIN departments d ON d.id=u.department_id "
                     "WHERE u.role IN ('student','teacher') ORDER BY u.id")
    courses = rows(c, "SELECT id, code, name, department_id, term_id, credits, teacher_id FROM courses ORDER BY id")
    units = rows(c, "SELECT id, course_id, kind, subgroup, teacher_id FROM teaching_units ORDER BY id")
    groups: dict[int, list[tuple[int, str]]] = {}
    for r in rows(c, "SELECT ug.unit_id, ug.group_id, g.name FROM teaching_unit_groups ug JOIN study_groups g ON g.id=ug.group_id "
                     "ORDER BY g.name"):
        groups.setdefault(r["unit_id"], []).append((r["group_id"], r["name"]))
    enrolled = rows(c, "SELECT e.user_id, e.course_id, COALESCE(e.group_id, u.group_id) group_id, e.subgroup, e.begin_date, e.end_date "
                       "FROM enrollments e JOIN users u ON u.id=e.user_id WHERE u.role='student' ORDER BY e.course_id, e.user_id")
    fs, ds = _sids(c, "faculties", [x["id"] for x in fac]), _sids(c, "departments", [x["id"] for x in dep])
    ts, us = _sids(c, "academic_terms", [x["id"] for x in terms]), _sids(c, "users", [x["id"] for x in people])
    cs = _sids(c, "courses", [x["id"] for x in courses])
    units = [u for u in units if u["course_id"] in cs]
    ks = _sids(c, "teaching_units", [u["id"] for u in units])
    teachers = {x["id"] for x in people if x["role"] == "teacher"}
    out: dict[str, list[dict]] = {
        "orgs": [{"sourcedId": fs[x["id"]], "name": x["name"], "type": "faculty", "identifier": x["code"]} for x in fac]
        + [{"sourcedId": ds[x["id"]], "name": x["name"], "type": "department", "identifier": x["code"],
            "parentSourcedId": fs.get(x["faculty_id"])} for x in dep],
        "terms": [{"sourcedId": ts[x["id"]], "title": x["name"], "identifier": x["code"], "startDate": x["teaching_start"],
                   "endDate": x["teaching_end"], "examStartDate": x["exam_start"], "examEndDate": x["exam_end"]} for x in terms],
        "users": [],
        "courses": [{"sourcedId": cs[x["id"]], "title": x["name"], "courseCode": x["code"], "orgSourcedId": ds.get(x["department_id"]),
                     "termSourcedId": ts.get(x["term_id"]), "credits": x["credits"],
                     "teacherSourcedId": us[x["teacher_id"]] if x["teacher_id"] in teachers else None} for x in courses],
        "classes": [{"sourcedId": ks[u["id"]], "courseSourcedId": cs[u["course_id"]], "kind": u["kind"], "subgroup": u["subgroup"],
                     "groups": ";".join(name for _, name in groups.get(u["id"], []))} for u in units],
    }
    for x in people:
        given, _, family = " ".join((x["full_name"] or "").split()).partition(" ")     # the importer joins them back
        student = x["role"] == "student"
        out["users"].append({"sourcedId": us[x["id"]], "username": x["username"], "givenName": given, "familyName": family,
                             "middleName": x["patronymic"], "role": x["role"], "identifier": x["student_no"] if student else None,
                             "email": x["email"], "group": x["grp"] if student else None,
                             "enabledUser": "true" if x["status"] == "active" else "false", "department": x["dep"]})
    by_course: dict[int, list[dict]] = {}
    for u in units:
        by_course.setdefault(u["course_id"], []).append(u)
    listed: list[tuple] = []
    for e in enrolled:
        before = len(listed)
        for u in by_course.get(e["course_id"], []):
            ids = [g for g, _ in groups.get(u["id"], [])]
            if timetable_rules.attends(e, ids, u["subgroup"]):
                listed.append((len(ids) != 1, u["id"], e["user_id"], {"classSourcedId": ks[u["id"]], "userSourcedId": us[e["user_id"]],
                                                                      "role": "student", "beginDate": e["begin_date"], "endDate": e["end_date"]}))
        if report is not None and len(listed) == before:      # no class of the course the student attends (SF-E5)
            report["dropped"] = report.get("dropped", 0) + 1
    listed.sort(key=lambda x: x[:3])
    rows_ = [x[3] for x in listed] + [{"classSourcedId": ks[u["id"]], "userSourcedId": us[u["teacher_id"]], "role": "teacher"}
                                      for u in units if u["teacher_id"] in teachers]
    out["enrollments"] = [{"sourcedId": _enrolment_sid(r["classSourcedId"], r["userSourcedId"], r["role"]), **r} for r in rows_]
    return {f"{k}.csv": _csv(tuple(domain.COLUMNS[k]), out[k]) for k in FILES}


def oneroster_zip(c, report: dict | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in oneroster_files(c, report).items():
            z.writestr(name, text)
    return buf.getvalue()


# ---------------------------------------------------------------- grades and attendance
def _cap(c, count_sql: str, args: tuple, cap: int | None):
    """Over HTTP an export holds a worker and its memory: past ``cap`` rows it is refused with the way round (AR-E1)."""
    if cap is not None and (n := row(c, count_sql, args)["n"]) > cap:
        raise ValueError(E("Fayl çox böyükdür ({n} sətir, ən çox {cap}). Yalnız dəyişiklikləri almaq üçün since parametrindən istifadə edin və ya serverdə manage.py "
                           "export əmrini işə salın.", n=n, cap=cap))


def grades_csv(c, since: datetime | None = None, cap: int | None = None) -> str:
    """Every score (drafts too: ``status`` says which), or only those written or changed after ``since``."""
    where, args = ("WHERE g.updated_at>=?", (_wall(since),)) if since else ("", ())     # >=: a row of the same second (CR-E3)
    _cap(c, f"SELECT COUNT(*) n FROM grades g {where}", args, cap)  # nosec B608 - constants
    data = rows(c, "SELECT g.user_id, g.course_id, g.component, g.score, g.max, g.status, g.source, g.updated_at, co.code, u.student_no "
                   f"FROM grades g JOIN courses co ON co.id=g.course_id JOIN users u ON u.id=g.user_id {where} "  # nosec B608 - constants
                   "ORDER BY g.updated_at, g.course_id, g.user_id, g.component", args)
    us, cs = _sids(c, "users", {x["user_id"] for x in data}), _sids(c, "courses", {x["course_id"] for x in data})
    return _csv(GRADE_COLUMNS, [{"courseSourcedId": cs[x["course_id"]], "courseCode": x["code"], "userSourcedId": us[x["user_id"]],
                                 "identifier": x["student_no"], "component": x["component"], "score": x["score"], "max": x["max"],
                                 "status": x["status"], "source": x["source"], "updatedAt": x["updated_at"]} for x in data])


def attendance_csv(c, since: datetime | None = None, cap: int | None = None) -> str:
    """Every lesson mark, or only those written or changed after ``since`` (a row without ``marked_at``, from the demo
    seed or before Task 20, is never "after")."""
    where, args = ("WHERE a.marked_at>=?", (_wall(since),)) if since else ("", ())
    _cap(c, f"SELECT COUNT(*) n FROM attendance a {where}", args, cap)  # nosec B608 - constants
    data = rows(c, "SELECT a.lesson_id, a.user_id, a.status, a.source, a.marked_at, l.course_id, l.day, l.start, co.code, u.student_no "
                   "FROM attendance a JOIN lessons l ON l.id=a.lesson_id JOIN courses co ON co.id=l.course_id JOIN users u ON u.id=a.user_id "
                   f"{where} ORDER BY a.marked_at, l.day, l.start, a.lesson_id, a.user_id", args)  # nosec B608 - constants
    us, cs = _sids(c, "users", {x["user_id"] for x in data}), _sids(c, "courses", {x["course_id"] for x in data})
    return _csv(ATTENDANCE_COLUMNS, [{"courseSourcedId": cs[x["course_id"]], "courseCode": x["code"], "userSourcedId": us[x["user_id"]],
                                      "identifier": x["student_no"], "lessonId": x["lesson_id"], "lessonDate": x["day"],
                                      "lessonStart": x["start"], "status": x["status"], "source": x["source"], "markedAt": x["marked_at"]}
                                     for x in data])


# ---------------------------------------------------------------- register
def registry_csv(c, kind: str, columns: list[str] | None = None) -> str:
    """A register of ``students`` or ``users`` with the chosen columns (all of them when none is chosen)."""
    if kind not in REGISTRY:
        raise ValueError(E("Naməlum reyestr: {kind}. Mövcud reyestrlər: {kinds}", kind=kind, kinds=", ".join(REGISTRY)))
    tail, allowed = REGISTRY[kind]
    cols = list(dict.fromkeys(columns or allowed))
    bad = [x for x in cols if x not in allowed]
    if bad:
        raise ValueError(E("Naməlum sütun: {cols}. Mümkün sütunlar: {allowed}", cols=", ".join(bad), allowed=", ".join(allowed)))
    data = rows(c, f"SELECT {', '.join(f'{allowed[x]} AS c{i}' for i, x in enumerate(cols))} {tail}")  # nosec B608 - constants
    return _csv(tuple(cols), [{x: r[f"c{i}"] for i, x in enumerate(cols)} for r in data])


# ---------------------------------------------------------------- "Tələbə-məzun" change list
def _events(c, where: str, args: tuple) -> list[dict]:
    out = rows(c, "SELECT e.id, e.student_id, u.student_no, u.full_name, g.name grp, e.kind, e.order_no, e.order_date, e.effective_date, "
                  "e.created_at, e.reported_at FROM student_status_events e JOIN users u ON u.id=e.student_id "
                  f"LEFT JOIN study_groups g ON g.id=u.group_id {where} ORDER BY e.created_at, e.id", args)  # nosec B608 - constants
    today = now().date()
    for x in out:
        deadline = date.fromisoformat(x["order_date"]) + timedelta(days=REPORT_DAYS)
        x["deadline"], x["days_left"] = deadline.isoformat(), (deadline - today).days      # negative: overdue
    return out


def status_changes(c, since: datetime | None = None) -> list[dict]:
    """Every status order entered (``created_at``) after ``since``: an order entered late, with an earlier effective
    date, is new to the operator all the same. ``days_left`` to ``order_date`` + 10 days, ``reported_at`` once marked."""
    return _events(c, "WHERE e.created_at>=?", (_wall(since),)) if since else _events(c, "", ())


def mark_reported(c, user: dict | None, event_id: int) -> dict | None:
    """Mark an order as entered into "Tələbə-məzun": ``reported_at`` is set once (audited); marking again changes
    nothing. None when there is no such order."""
    if not row(c, "SELECT 1 FROM student_status_events WHERE id=?", (event_id,)):
        return None
    if c.execute("UPDATE student_status_events SET reported_at=? WHERE id=? AND reported_at IS NULL", (iso(now()), event_id)).rowcount:
        audit(c, user["id"] if user else None, "status_reported", "student_status_event", f"#{event_id}")
    return _events(c, "WHERE e.id=?", (event_id,))[0]


# ---------------------------------------------------------------- the one path
def run(c, kind: str, *, since: datetime | None = None, registry: str = "students", columns: list[str] | None = None,
        user_id: int | None = None, cap: int | None = None, term_id: int | None = None, version_id: int | None = None) -> tuple[str, str, bytes]:
    """(file name, media type, body) of an export; ``since`` counts for grades, attendance and status changes; ``cap``:
    the most rows of grades or attendance (HTTP_CAP over HTTP, none on the command line); ``term_id``/``version_id``: the
    timetable's term (default: the current one) or version. Raises ValueError (a translatable message) for a register or
    column not on the lists, a file over the cap, or a term or version that does not exist. Audited, after the reading."""
    report: dict = {}
    if kind == "oneroster":
        name, ctype, body = "oneroster.zip", "application/zip", oneroster_zip(c, report)
    else:
        if kind == "grades":
            text = grades_csv(c, since, cap)
        elif kind == "attendance":
            text = attendance_csv(c, since, cap)
        elif kind == "registry":
            text = registry_csv(c, registry, columns)
        elif kind == "status-changes":
            text = _csv(STATUS_COLUMNS, status_changes(c, since))
        elif kind == "timetable":
            text = _csv(timetable.EXPORT_COLUMNS, timetable.export_rows(c, term_id, version_id))
        else:
            raise ValueError(kind)
        name, ctype, body = f"registry-{registry}.csv" if kind == "registry" else f"{kind}.csv", "text/csv; charset=utf-8", text.encode("utf-8")
    scope = f"version {version_id}" if version_id else f"term {term_id}" if term_id else ""
    audit(c, user_id, "export", kind, " · ".join(x for x in (registry if kind == "registry" else scope if kind == "timetable" else "", _wall(since) if since else "",
                                                             f"enrolments left out {report['dropped']}" if report.get("dropped") else "") if x))
    return name, ctype, body
