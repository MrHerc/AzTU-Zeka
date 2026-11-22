"""Bulk import (tasks/todo.md, Task 16): one file of one kind from one source system, all or nothing.

1. Read and check every row; resolve its references against what Zəka holds. Any refused row: nothing is written and
   the report names each row and the reason.
2. Compare each row with its linked row (import_links): unchanged, an update (the source changed it), or a conflict
   (Zəka changed it since the import and the file says otherwise: not overwritten unless ``prefer_source``, audited).
3. Write in one BEGIN IMMEDIATE transaction; the report gives how long it held the write lock.
"""
from __future__ import annotations

import hashlib
import math
import secrets
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta

from ...core.i18n import E
from ...legacy.store import audit, iso, now, setting
from ...core import tenant
from ..directory import domain as directory_rules
from ..exam import service as exam
from ..identity import domain as identity_rules
from ..identity import service as identity
from ..journal import service as journal
from ..migration import loaders
from ..timetable import domain as timetable_rules
from ..timetable import service as timetable
from . import domain, forma3, repo, tables

MAX_SCREEN_ROWS = 20_000
MAX_FILE_ROWS = tables.MAX_ROWS - 1                 # one file is one transaction (with its header row): tools/etl splits a larger load
# link kind -> (table, compared and written columns, key column)
TARGETS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "users": ("users", ("username", "full_name", "patronymic", "role", "student_no", "email", "group_id", "department_id", "status"), "id"),
    "faculties": ("faculties", ("code", "name"), "id"),
    "departments": ("departments", ("code", "name", "faculty_id"), "id"),
    "terms": ("academic_terms", ("code", "name", "teaching_start", "teaching_end", "exam_start", "exam_end"), "id"),
    "courses": ("courses", ("code", "name", "department_id", "term_id", "credits", "teacher_id"), "id"),
    "classes": ("teaching_units", ("course_id", "kind", "subgroup"), "id"),
    "unit_teachers": ("teaching_units", ("teacher_id",), "id"),
    "enrollments": ("enrollments", ("user_id", "course_id", "group_id", "subgroup", "begin_date", "end_date"), "rowid"),
    "timetable": ("timetable", ("course_id", "weekday", "start", "end", "kind", "room"), "id"),
    "teaching_load": ("teaching_units", ("course_id", "kind", "subgroup", "teacher_id", "hours", "students", "pay", "vacancy", "post_ref",
                                         "anchor"), "id"),
    "rooms": ("rooms", ("code", "number", "name", "building_id", "floor", "kind", "capacity", "accessible"), "id"),
    "attendance_opening": ("attendance_opening", ("student_id", "course_id", "term_id", "held_hours", "unexcused_hours",
                                                  "excused_hours", "as_of"), "id"),
    "grades": ("grades", ("user_id", "course_id", "component", "score", "max"), "rowid"),
    # Task 38: records of the old system; each is written by the module that owns it (WRITERS)
    "attendance": ("attendance", ("lesson_id", "user_id", "status"), "rowid"),
    "results": ("final_grades", ("user_id", "course_code", "course_name", "course_name_en", "term_name", "term_name_en", "term_start",
                                 "credits", "score"), "id"),
    "status_events": ("student_status_events", ("student_id", "kind", "order_no", "order_date", "effective_date", "to_group_id"), "id"),
}
BIG = ("attendance",)                                # too many rows to read whole: only the file's own links and lessons are read
UNIT_LINKS = ("classes", "teaching_load")           # these also carry the unit's groups
STAMPED = ("faculties", "departments", "academic_terms", "courses", "teaching_units", "rooms", "attendance_opening")
IMPORTED_ROLES = ("student", "teacher")              # an import never touches another kind of account


@dataclass(frozen=True)
class Pending:
    """A reference to a row created by this same file (an org's parent faculty); filled in while writing."""
    link: str
    source_id: str

    def __str__(self):
        return f"pending:{self.link}:{self.source_id}"


@dataclass
class Item:
    row: int
    link: str
    source_id: str
    values: dict
    groups: list[int] | None = None
    natural: int | None = None                       # an unlinked row that already is this one (adopted)
    row_id: int | None = None
    action: str = ""
    extra: dict = field(default_factory=dict)


class Context:
    """What the rows of a file are checked and compared against, read once before any write (no query per row)."""

    def __init__(self, c, source: str, links: tuple[str, ...], keys: list[str] | None = None):
        self.c, self.source = c, source
        self.links = {k: repo.links_in(c, k, source, keys or []) if k in BIG else repo.links(c, k, source) for k in links}
        self.rows = {k: {} if k in BIG else repo.table(c, TARGETS[k][0], TARGETS[k][1], TARGETS[k][2]) for k in links}
        self.groups = repo.unit_groups(c)
        self.file_faculties: set[str] = set()          # orgs: faculties of this same file, for their departments
        self.reason = ""                               # grades: "import:<file name>:<its SHA-256>" (Task 21)
        self._cache: dict = {}

    def by(self, name: str, col: str) -> dict:
        if (name, col) not in self._cache:
            self._cache[(name, col)] = repo.by_column(self.c, name, col)
        return self._cache[(name, col)]

    def table(self, name: str, cols: tuple[str, ...], key: str = "id") -> dict:
        if (name, cols) not in self._cache:
            self._cache[(name, cols)] = repo.table(self.c, name, cols, key)
        return self._cache[(name, cols)]

    def enrolled(self) -> dict[tuple[int, int], int]:
        if "enrolled" not in self._cache:
            self._cache["enrolled"] = {(r["user_id"], r["course_id"]): k for k, r in
                                       self.table("enrollments", ("user_id", "course_id"), "rowid").items()}
        return self._cache["enrolled"]

    def keyed(self, name: str, cols: tuple[str, ...], key: str = "id") -> dict[tuple, int]:
        """{(values of ``cols``): row key} of a table, built once per import (Checkpoint C, P4: not once per file row)."""
        if ("keyed", name, cols) not in self._cache:
            self._cache[("keyed", name, cols)] = {tuple(r[x] for x in cols): k for k, r in self.table(name, cols, key).items()}
        return self._cache[("keyed", name, cols)]

    # ---- the journal's own lookups (Task 38)
    def enrolment(self, uid: int, course_id: int) -> dict | None:
        """The student's enrolment in a course as a lesson list reads it (the student's own group when it names none)."""
        key = self.enrolled().get((uid, course_id))
        if key is None:
            return None
        e = self.table("enrollments", ("group_id", "subgroup", "begin_date", "end_date"), "rowid")[key]
        return {**e, "group_id": e["group_id"] or self.table("users", ("group_id",))[uid]["group_id"]}

    def lesson(self, unit: int, day: str, start: str) -> dict | None:
        """The unit's lesson on a day and start: where it was held, else the slot it was planned in."""
        if "lessons" not in self._cache:
            held: dict = {}
            slot: dict = {}
            for r in self.table("lessons", ("unit_id", "day", "start", "slot_day", "slot_start", "status", "academic_hours")).values():
                held[(r["unit_id"], r["day"], r["start"])] = r
                slot[(r["unit_id"], r["slot_day"], r["slot_start"])] = r
            self._cache["lessons"] = (held, slot)
        held, slot = self._cache["lessons"]
        return held.get((unit, day, start)) or slot.get((unit, day, start))

    def marks(self, lesson_id: int) -> dict[int, int]:
        """{student: the key of their record} of one lesson, read when a file row names the lesson."""
        if ("marks", lesson_id) not in self._cache:
            found = repo.marks_of(self.c, lesson_id)
            self.rows["attendance"].update({r["_k"]: r for r in found})
            self._cache[("marks", lesson_id)] = {r["user_id"]: r["_k"] for r in found}
        return self._cache[("marks", lesson_id)]

    def opening_dates(self) -> dict[tuple[int, int], str]:
        if "openings" not in self._cache:
            self._cache["openings"] = {(r["student_id"], r["course_id"]): r["as_of"] for r in
                                       self.table("attendance_opening", ("student_id", "course_id", "as_of")).values()}
        return self._cache["openings"]

    def legacy_pairs(self) -> dict[tuple[int, int], str]:
        if "legacy" not in self._cache:
            self._cache["legacy"] = journal.legacy_pairs(self.c)
        return self._cache["legacy"]

    def role(self, uid: int) -> str | None:
        hit = self.table("users", ("role",)).get(uid)
        return hit["role"] if hit else None

    def linked(self, link: str, sid: str | None) -> int | None:
        if link not in self.links:                     # a reference to another kind's rows, read once
            self.links[link] = repo.links(self.c, link, self.source)
        hit = self.links[link].get(sid) if sid else None
        return hit["row_id"] if hit else None


# ---------------------------------------------------------------- reading the file
def _cells(kind: str, filename: str, data: bytes) -> tuple[list[tuple[int, dict]], dict | None]:
    rows = tables.table_rows(filename, data)                    # (row number in the file, cells)
    if not rows:
        return [], E("Fayl boşdur")
    index, problem = domain.header_map(kind, rows[0][1])
    if problem:
        return [], problem
    return [(n, {col: (r[i] if i < len(r) else "").strip() for col, i in index.items()}) for n, r in rows[1:]], None


def _plan_rows(kind: str, ctx: Context, cells: list[tuple[int, dict]], errors: list) -> list[Item]:
    items: list[Item] = []
    seen: dict[str, int] = {}
    pairs: dict[tuple[int, int], Item] = {}
    for n, x in cells:
        if kind in domain.COMPOSITE_KEYS:
            x["sourcedId"] = domain.source_key(kind, x)
        values, problem = domain.draft(kind, x)
        if not problem and x["sourcedId"] in seen:
            problem = E("sourcedId faylda təkrarlanır (sətir {n})", n=seen[x["sourcedId"]])
        if problem:
            errors.append({"row": n, "reason": problem})
            continue
        seen[x["sourcedId"]] = n
        item, problem = _resolve(kind, ctx, n, x["sourcedId"], values)
        if problem:
            errors.append({"row": n, "reason": problem})
        elif item and item.link == "enrollments" and (item.values["user_id"], item.values["course_id"]) in pairs:
            first = pairs[(item.values["user_id"], item.values["course_id"])]   # a lecture and a lab: one enrolment
            if first.values["subgroup"] is None:
                first.values["subgroup"] = item.values["subgroup"]
            first.extra.setdefault("aliases", []).append(item.source_id)
        elif item:
            if item.link == "enrollments":
                pairs[(item.values["user_id"], item.values["course_id"])] = item
            items.append(item)
    return items


def _missing(what: str, value) -> dict:
    return E("{what} tapılmadı: {value}", what=what, value=value)


def _resolve(kind: str, ctx: Context, n: int, sid: str, v: dict) -> tuple[Item | None, dict | None]:
    """The item a draft becomes once its references are ids; or why it cannot."""
    if kind == "users":
        group, dep = v.pop("_group"), v.pop("_department")
        group_id = ctx.by("study_groups", "name").get(group) if group else None
        if group and not group_id:
            return None, _missing("Qrup", group)
        department_id = ctx.by("departments", "code").get(dep) if dep else None
        if dep and not department_id:
            return None, _missing("Kafedra", dep)
        return Item(n, "users", sid, {**v, "group_id": group_id, "department_id": department_id},
                    natural=ctx.by("users", "username").get(v["username"])), None
    if kind == "orgs":
        entity, parent = v.pop("_entity"), v.pop("_parent")
        if entity == "departments":
            faculty = ctx.linked("faculties", parent) or (Pending("faculties", parent) if parent in ctx.file_faculties else None)
            if not faculty:
                return None, _missing("Fakültə", parent)
            v["faculty_id"] = faculty
        return Item(n, entity, sid, v, natural=ctx.by(entity, "code").get(v["code"])), None
    if kind == "terms":
        return Item(n, "terms", sid, v, natural=ctx.by("academic_terms", "code").get(v["code"])), None
    if kind == "courses":
        out = {k: v[k] for k in ("code", "name", "credits")}
        for col, ref, link, what in (("department_id", "_department", "departments", "Kafedra"), ("term_id", "_term", "terms", "Semestr"),
                                     ("teacher_id", "_teacher", "users", "Müəllim")):
            out[col] = ctx.linked(link, v[ref]) if v[ref] else None
            if v[ref] and not out[col]:
                return None, _missing(what, v[ref])
        if out["teacher_id"] and ctx.role(out["teacher_id"]) != "teacher":
            return None, E("«{field}» sahəsində müəllim seçin", field="teacherSourcedId")
        return Item(n, "courses", sid, out), None
    if kind == "classes":
        course_id = ctx.linked("courses", v["_course"])
        if not course_id:
            return None, _missing("Fənn", v["_course"])
        names = ctx.by("study_groups", "name")
        missing = [g for g in v["_groups"] if g not in names]
        if missing:
            return None, _missing("Qrup", ", ".join(missing))
        return Item(n, "classes", sid, {"course_id": course_id, "kind": v["kind"], "subgroup": v["subgroup"]},
                    groups=sorted({names[g] for g in v["_groups"]})), None
    if kind == "enrollments":
        unit, user = ctx.linked("classes", v["_class"]), ctx.linked("users", v["_user"])
        if not unit:
            return None, _missing("Tədris vahidi", v["_class"])
        if not user:
            return None, _missing("İstifadəçi", v["_user"])
        role = ctx.role(user)
        if v["_role"] == "teacher":
            if role != "teacher":
                return None, E("«{field}» sahəsində müəllim seçin", field="userSourcedId")
            return Item(n, "unit_teachers", sid, {"teacher_id": user}, natural=unit), None
        if role != "student":
            return None, E("Yalnız aktiv tələbə qeydiyyata alınır")
        u = ctx.table("teaching_units", ("course_id", "subgroup"))[unit]
        groups = ctx.groups.get(unit, [])
        values = {"user_id": user, "course_id": u["course_id"], "group_id": groups[0] if len(groups) == 1 else None,
                  "subgroup": u["subgroup"], "begin_date": v["begin_date"], "end_date": v["end_date"]}
        return Item(n, "enrollments", sid, values, natural=ctx.enrolled().get((user, u["course_id"]))), None
    if kind == "timetable":
        ref = v.pop("_course")
        course_id = ctx.linked("courses", ref)
        if not course_id:
            return None, _missing("Fənn", ref)
        return Item(n, "timetable", sid, {"course_id": course_id, **v}), None
    if kind == "rooms":
        code = v.pop("_building")
        building_id = ctx.by("buildings", "code").get(code)
        if not building_id:
            return None, _missing("Korpus", code)
        return Item(n, "rooms", sid, {**v, "building_id": building_id}, natural=ctx.by("rooms", "code").get(v["code"])), None
    if kind == "attendance-opening":
        refs = {k: v.pop(k) for k in ("_term", "_course", "_user")}
        term_id, course_id, student_id = (ctx.linked("terms", refs["_term"]), ctx.linked("courses", refs["_course"]),
                                          ctx.linked("users", refs["_user"]))
        for found, what, ref in ((term_id, "Semestr", "_term"), (course_id, "Fənn", "_course"), (student_id, "Tələbə", "_user")):
            if not found:
                return None, _missing(what, refs[ref])
        if student_id is None or ctx.role(student_id) != "student":
            return None, E("Yalnız aktiv tələbə qeydiyyata alınır")
        if str(v.get("as_of") or "") > now().date().isoformat():
            return None, E("Açılış qalığının tarixi gələcəkdə ola bilməz")      # it would hide the journal's records up to that day
        first = ctx.legacy_pairs().get((student_id, course_id or 0))        # one form per student and course (Task 38): lesson
        if first and first <= str(v.get("as_of") or ""):                       # records up to the opening's date (AR-F8)
            return None, E("Bu tələbə və fənn üzrə ayrı-ayrı dərslərin qeydləri idxal olunub: açılış qalığı qəbul olunmur")
        keys = ctx.keyed("attendance_opening", ("student_id", "course_id", "term_id"))
        values = {"student_id": student_id, "course_id": course_id, "term_id": term_id, **v}
        return Item(n, "attendance_opening", sid, values, natural=keys.get((student_id, course_id, term_id))), None
    if kind == "grades":
        course_id, user_id = ctx.linked("courses", v["_course"]), ctx.linked("users", v["_user"])
        if not course_id:
            return None, _missing("Fənn", v["_course"])
        if not user_id or ctx.role(user_id) != "student":
            return None, _missing("Tələbə", v["_user"])
        if (user_id, course_id) not in ctx.enrolled():
            return None, E("Tələbə bu fənnə yazılmayıb")                         # no score, and no final grade, of a course not taken
        grading = tenant.load(ctx.c)["grading"]
        cols = {x["name"]: x for x in grading["components"] if not x.get("attendance")} | {grading["exam"]["name"]: grading["exam"]}
        comp = cols.get(v["component"])
        if not comp:
            return None, E("Komponent fənnin sxemində yoxdur: {x}", x=v["component"])
        if (v["_max"] is not None and v["_max"] != comp["max"]) or v["score"] > comp["max"]:
            return None, E("Bal 0 ilə {max} arasında olmalıdır", max=comp["max"])
        keys = ctx.keyed("grades", ("user_id", "course_id", "component"), "rowid")
        item = Item(n, "grades", sid, {"user_id": user_id, "course_id": course_id, "component": v["component"], "score": v["score"],
                                       "max": float(comp["max"])}, natural=keys.get((user_id, course_id, v["component"])))
        item.extra["as_of"] = v["_as_of"]
        return item, None
    if kind == "attendance":
        unit, user = ctx.linked("classes", v["_class"]), ctx.linked("users", v["_user"])
        if not unit:
            return None, _missing("Tədris vahidi", v["_class"])
        if not user or ctx.role(user) != "student":
            return None, _missing("Tələbə", v["_user"])
        if v["_as_of"] > now().date().isoformat():
            return None, E("Kəsid tarixi gələcəkdə ola bilməz")
        u = ctx.table("teaching_units", ("course_id", "subgroup", "kind"))[unit]
        enr = ctx.enrolment(user, u["course_id"])
        if not enr or not timetable_rules.on_list(enr, {"day": v["day"], "unit_id": unit}, {unit: (ctx.groups.get(unit, []), u["subgroup"])}):
            return None, E("Tələbə həmin gün bu tədris vahidinin siyahısında deyil")   # the journal would never count the record
        opening = ctx.opening_dates().get((user, u["course_id"]))
        if opening and v["day"] <= opening:                                      # one form per student and course
            return None, E("Bu tələbə və fənn üçün açılış qalığı var ({day}): həmin tarixə qədərki dərs qeydi qəbul olunmur", day=opening)
        les = ctx.lesson(unit, v["day"], v["start"])
        if les and les["status"] == "cancelled":
            return None, E("Zəka platformasında bu dərs ləğv olunub: qeyd sayılmazdı")
        if les and v["_hours"] and les["academic_hours"] and v["_hours"] != les["academic_hours"]:   # Checkpoint F (CR-F2)
            return None, E("Dərsin saatı faylda {a}, Zəka platformasında isə {b}: qeyd başqa saat sayı ilə hesablanardı", a=v["_hours"], b=les["academic_hours"])
        key = f"{unit}|{v['day']}|{v['start']}"
        item = Item(n, "attendance", sid, {"lesson_id": les["_k"] if les else Pending("lessons", key), "user_id": user, "status": v["status"]},
                    natural=ctx.marks(les["_k"]).get(user) if les else None)
        item.extra.update(as_of=v["_as_of"], course_id=u["course_id"], hours=v["_hours"] or (les and les["academic_hours"]) or 2,
                          lesson=(unit, v["day"], v["start"], v["_end"], v["_hours"], domain.KIND_LABEL.get(u["kind"])))
        return item, None
    if kind == "results":
        user = ctx.linked("users", v.pop("_user"))
        if not user or ctx.role(user) != "student":
            return None, _missing("Tələbə", sid.split("|")[0])
        if "finals" not in ctx._cache:                   # a term before Zəka only: the same course and term in Zəka is Zəka's
            ctx._cache["finals"] = {(r["user_id"], r["course_code"], r["term_name"]): r for r in
                                    ctx.table("final_grades", ("user_id", "course_code", "term_name", "source")).values()}
        same = ctx._cache["finals"].get((user, v["course_code"], v["term_name"]))
        if same and same["source"] != "legacy":
            return None, E("Bu fənnin həmin semestrdəki yekun qiyməti Zəka platformasında yazılıb: tarixi nəticə kimi idxal olunmur")
        return Item(n, "results", sid, {"user_id": user, **v}, natural=same["_k"] if same else None), None
    if kind == "status-events":
        user, group = ctx.linked("users", v["_user"]), v["_group"]
        if not user or ctx.role(user) != "student":
            return None, _missing("Tələbə", v["_user"])
        if "groups" not in ctx._cache:                 # built once (PY-F7); every group, the active one first for a reused
            ctx._cache["groups"] = {}                    # name: an order of the past may name a closed group (AR-F7)
            for k, g in sorted(ctx.table("study_groups", ("name", "active")).items(), key=lambda kv: (not kv[1]["active"], kv[0])):
                ctx._cache["groups"].setdefault(g["name"], k)
        groups = ctx._cache["groups"]
        if group and group not in groups:
            return None, _missing("Qrup", group)
        order, problem = directory_rules.status_event({**v, "to_group_id": groups[group] if group else None})
        if problem:
            return None, problem
        events = ctx.keyed("student_status_events", ("student_id", "order_no", "order_date"))
        item = Item(n, "status_events", sid, {"student_id": user, **{k: order[k] for k in ("kind", "order_no", "order_date",
                                                                                       "effective_date", "to_group_id")}},
                    natural=events.get((user, order["order_no"], order["order_date"])))
        item.extra["note"] = order["note"]
        item.extra["student"] = {"id": user, **ctx.table("users", ("username", "role", "group_id"))[user]}
        return item, None
    raise ValueError(kind)


# ---------------------------------------------------------------- Forma №3
def _key(*parts) -> str:
    return domain.row_hash(list(parts))[:40]


def _person_index(c) -> dict[frozenset, list[int]]:
    idx: dict[frozenset, list[int]] = {}
    for r in c.execute("SELECT id, full_name, patronymic FROM users WHERE role IN ('teacher','dept_head') AND status='active'"):
        words = frozenset(forma3.norm(f"{r['full_name']} {r['patronymic'] or ''}").split())
        idx.setdefault(words, []).append(r["id"])
        short = frozenset(forma3.norm(r["full_name"]).split())
        if short != words:
            idx.setdefault(short, []).append(r["id"])
    return idx


def _teacher(idx: dict, name: str) -> int | None:
    words = forma3.norm(name).split()
    for key in (frozenset(words), frozenset(words[:2])):          # Soyad Ad Ata adı, then Soyad Ad
        ids = idx.get(key) or []
        if len(set(ids)) == 1:
            return ids[0]
    return None


def _course_for(c, cache: dict, subject: str, semester: str, department: int | None = None) -> int | None:
    """The course of a subject: the only one of that name, else the one of the file's department, else of the semester."""
    if "courses" not in cache:
        cache["courses"] = [dict(r) for r in repo.active_courses(c)]
    want = forma3.tx.subject_key(subject)
    same = [x for x in cache["courses"] if forma3.tx.subject_key(x["name"]) == want]
    if len(same) > 1 and department:                    # a subject two departments teach: each file means its own course
        same = [x for x in same if x["department_id"] == department] or same
    if len(same) > 1:
        same = [x for x in same if semester in forma3.norm(f"{x['term'] or ''} {x['term_code'] or ''}")]
    return same[0]["id"] if len(same) == 1 else None


def _plan_load(c, filename: str, data: bytes, conflicts: list) -> tuple[list[Item], dict]:
    """The form's units as import items, and the reader's report (docs/forms/forma-3.md). A unit is planned only when its
    post passed the arithmetic controls and holds no blocking conflict; a hidden sheet is listed, never planned; a vacancy
    unit has no teacher (``teacher_id`` NULL, ``vacancy`` 1)."""
    if not (filename or "").lower().endswith(".xlsx"):
        raise tables.TableError("Forma №3 XLSX faylı olmalıdır")
    try:
        form = forma3.read(tables.xlsx_sheets(data))
    except forma3.FormError as ex:
        raise tables.TableError(ex.args[0]) from None
    if not form.posts:
        raise tables.TableError("Faylda Forma №3 tədris yükü tapılmadı")
    people = _person_index(c)
    groups = {forma3.norm(forma3.tx.group_code(k)): v for k, v in repo.by_column(c, "study_groups", "name").items()}
    blocked = {p.ref for p in form.posts if p.blocked}
    cache: dict = {}
    items: list[Item] = []
    seen: dict[str, int] = {}
    refused: set[str] = set()                            # units the registry cannot place: never counted as ready
    placed = [u for u in form.units if not (u.hidden or u.post in blocked)]
    teachers = {u.anchor: None if u.vacancy else _teacher(people, u.teacher or "") for u in placed}
    # the file's department: the one most of its units' teachers belong to (none on a tie); it tells apart a subject
    # that two departments teach in the same term (acceptance on the departments' real files, Tasks 47-48)
    of = repo.departments_of(c, [t for t in teachers.values() if t])
    deps = Counter(of[t] for t in teachers.values() if t and of.get(t)).most_common(2)
    department = deps[0][0] if deps and (len(deps) == 1 or deps[0][1] > deps[1][1]) else None
    for u in placed:
        teacher = teachers[u.anchor]
        course = _course_for(c, cache, u.subject_raw, u.semester, department)
        missing = [x["code_raw"] for x in u.groups if forma3.norm(x["code"]) not in groups]
        reason = (_missing("Müəllim", u.teacher) if not teacher and not u.vacancy else _missing("Fənn", u.subject_raw) if not course
                  else _missing("Qrup", ", ".join(missing)) if missing else None)
        if reason:
            conflicts.append({"row": u.anchor, "reason": reason})
            refused.add(u.anchor)
            continue
        content = _key("f3", u.teacher or "", u.subject_key, u.semester, u.kind, sorted(x["code"] for x in u.groups), u.hourly, u.vacancy)
        seen[content] = seen.get(content, 0) + 1
        if seen[content] > 1:                            # R4: the same class written again is a separate class, never summed
            content = _key(content, seen[content])
        items.append(Item(0, "teaching_load", _key("f3", u.anchor), {
            "course_id": course, "kind": u.kind, "subgroup": None, "teacher_id": teacher, "hours": u.hours,
            "students": u.students_total or None, "pay": "hourly" if u.hourly else "staff", "vacancy": int(u.vacancy),
            "post_ref": u.post, "anchor": u.anchor}, groups=sorted({groups[forma3.norm(x["code"])] for x in u.groups}),
            extra={"where": u.anchor, "aliases": [content]}))
    report = forma3.report(form, known_codes={k for k in groups}, refused=refused)
    return items, report


# ---------------------------------------------------------------- comparing
def _uniques(kind: str, ctx: Context, items: list[Item], errors: list):
    """Unique columns: no two rows of the file and no other row of Zəka may share a value."""
    cols = {"users": ("username", "email", "student_no"), "orgs": ("code",), "terms": ("code",), "rooms": ("code",)}.get(kind, ())
    for col in cols:
        seen: dict = {}
        for it in items:
            v = it.values.get(col)
            if v is None:
                continue
            table = TARGETS[it.link][0]
            owner = ctx.by(table, col).get(v)
            mine = it.row_id or it.natural
            if (owner and owner != mine) or (table, v) in seen:
                errors.append({"row": it.row, "reason": E("«{field}» dəyəri artıq başqa sətirdədir: {value}", field=col, value=v)})
            seen[(table, v)] = it.row


def _current(ctx: Context, it: Item) -> dict | None:
    table, cols, _ = TARGETS[it.link]
    r = ctx.rows[it.link].get(it.row_id) if it.row_id is not None else None
    if r is None:
        return None
    cur = {k: r[k] for k in cols}
    if it.link in UNIT_LINKS:
        cur["groups"] = ctx.groups.get(r["_k"], [])
    return cur


def _new(it: Item) -> dict:
    return {**it.values, **({"groups": it.groups} if it.link in UNIT_LINKS else {})}


def _unit_links(ctx: Context, items: list[Item]) -> dict[int, dict | None]:
    """X21: a Forma №3 unit is keyed on its anchor cell, with its content (teacher, subject, groups, ordinal) as an alias.
    It finds its row by its content first (a row inserted above moves every anchor), then by its anchor (a corrected
    teacher, subject or group, a filled vacancy), and never takes a row another unit of the file has already found."""
    links, taken = ctx.links["teaching_load"], set()
    out: dict[int, dict | None] = {}
    mine = [it for it in items if it.link == "teaching_load"]
    for by_content in (True, False):
        for it in mine:
            if out.get(id(it)) is not None:
                continue
            ids = it.extra.get("aliases", []) if by_content else [it.source_id]
            hit = next((links[s] for s in ids if s in links and links[s]["row_id"] not in taken), None)
            if hit is not None:
                taken.add(hit["row_id"])
            out[id(it)] = hit
    return out


def _classify(ctx: Context, items: list[Item], prefer: bool, conflicts: list, errors: list):
    units = _unit_links(ctx, items) if "teaching_load" in ctx.links else {}
    for it in items:
        link = units[id(it)] if it.link == "teaching_load" else ctx.links[it.link].get(it.source_id)
        rid = link["row_id"] if link and link["row_id"] in ctx.rows[it.link] else None
        it.row_id = rid or (it.natural if it.natural in ctx.rows[it.link] else None)
        if it.link == "users" and it.row_id and ctx.rows["users"][it.row_id]["role"] not in IMPORTED_ROLES:
            errors.append({"row": it.row, "reason": E("Bu hesab idxalla dəyişdirilmir")})
            continue
        if it.link == "users" and it.row_id and ctx.rows["users"][it.row_id]["status"] == "erased":
            it.action = "conflict"                     # Checkpoint F (SEC-F2): an import never undoes an approved erasure
            conflicts.append({"row": it.row, "id": it.row_id, "fields": [],
                              "reason": E("Hesab məxfilik sorğusu ilə silinib: idxal onu bərpa etmir")})
            continue
        cur = _current(ctx, it) if it.row_id else None
        if cur is None:
            it.action = "insert" if it.link != "unit_teachers" else "missing"
            if it.action == "missing":
                errors.append({"row": it.row, "reason": _missing("Tədris vahidi", it.source_id)})
            continue
        new_hash, cur_hash = domain.row_hash(_new(it)), domain.row_hash(cur)
        it.extra["cur_hash"] = cur_hash
        if it.link == "teaching_load" and link and link["source_hash"] != cur_hash:     # an older key of the same row
            own = (ctx.links[it.link].get(k) for k in (it.source_id, *it.extra.get("aliases", [])))
            link = next((x for x in own if x and x["row_id"] == link["row_id"] and x["source_hash"] == cur_hash), link)
        if new_hash == cur_hash:
            it.action = "unchanged" if link and link["source_hash"] == new_hash else "relink"
        elif link and cur_hash == link["source_hash"]:
            it.action = "update"
        elif not link and all(cur[k] in (None, []) for k in cur if cur[k] != _new(it).get(k)):
            it.action = "update"                       # a row never imported: filling its empty fields overwrites nothing
        else:
            changed = sorted(k for k in cur if cur[k] != _new(it).get(k))
            it.action = "overwrite" if prefer and it.link != "status_events" else "conflict"
            it.extra["fields"] = changed
            if it.action == "conflict":
                conflicts.append({"row": it.extra.get("where", it.row), "id": it.row_id, "fields": changed,
                                  "reason": E("Zəka platformasında dəyişdirilib; mənbənin dəyəri yazılmadı")})
        if it.link == "attendance" and it.action == "relink" and not link:
            it.action = "update"                       # the same mark written in Zəka becomes the imported record
        if it.link == "status_events" and it.action == "update":   # an order is never rewritten: a correction is a new order
            it.action = "conflict"
            conflicts.append({"row": it.row, "id": it.row_id, "reason": E("Status əmri dəyişdirilmir: düzəliş yeni əmrlə edilir")})


# ---------------------------------------------------------------- writing
def _now_hash(c, it: Item) -> str | None:
    """The row's compared fields as they are now, inside the write lock."""
    table, cols, key = TARGETS[it.link]
    if it.row_id is None:
        return None
    r = repo.one(c, table, cols, it.row_id, key)
    if r is None:
        return None
    return domain.row_hash({**r, **({"groups": repo.groups_of(c, it.row_id)} if it.link in UNIT_LINKS else {})})


# the old system's journal records and orders are written by the journal and the registry themselves (Task 38)
WRITERS = loaders.WRITERS


def _write(c, ctx: Context, items: list[Item], user_id: int | None, conflicts: list) -> int:
    new_ids: dict[tuple[str, str], int] = {}
    t = iso(now())
    done = 0
    for it in items:                                   # held lessons the timetable did not plan are made first
        ref = it.values.get("lesson_id")
        if isinstance(ref, Pending) and it.action == "insert" and (ref.link, ref.source_id) not in new_ids:
            unit, day, start, end, hours, kind = it.extra["lesson"]
            new_ids[(ref.link, ref.source_id)] = timetable.add_imported_lesson(c, unit, day, start, end, hours, kind)
    order = {k: i for i, k in enumerate(("faculties", "departments"))}
    for it in sorted(items, key=lambda x: order.get(x.link, 9)):
        if it.action in ("unchanged", "conflict"):
            continue
        values = {k: (new_ids[(v.link, v.source_id)] if isinstance(v, Pending) else v) for k, v in it.values.items()}
        table, cols, key = TARGETS[it.link]
        legacy = {"source": "legacy", "status": "published", "entered_by": user_id, "reason": ctx.reason, "as_of": it.extra.get("as_of"),
                  "updated_at": t} if table == "grades" else {}        # an imported score (Task 21): who, from which file
        writer = WRITERS.get(it.link)
        if it.action == "insert":
            extra: dict = {"synthetic": 0} if table == "users" else {"created_at": t, "updated_at": t} if table in STAMPED else {}
            rid = writer(c, ctx, it, values, user_id, t) if writer else repo.insert(c, table, {**values, **extra, **legacy})
            new_ids[(it.link, it.source_id)] = rid
        else:
            rid = it.row_id if it.row_id is not None else 0       # set by _classify for every action but insert
            if it.action == "update" and _now_hash(c, it) != it.extra.get("cur_hash"):
                it.action = "conflict"                            # changed in Zəka while the file was being checked
                conflicts.append({"row": it.extra.get("where", it.row), "id": rid,
                                  "reason": E("İdxal yoxlanılarkən Zəka platformasında dəyişdirildi; mənbənin dəyəri yazılmadı")})
                continue
            if it.action in ("update", "overwrite") and it.link == "users":
                before = repo.one(c, "users", ("role", "status"), rid)
                if before and (before["role"], before["status"]) != (values["role"], values["status"]):
                    identity.end_all_sessions(c, rid)             # a new role or status starts from a new sign-in
            if it.action in ("update", "overwrite") and writer:
                writer(c, ctx, it, values, user_id, t)
            elif it.action in ("update", "overwrite"):
                prior = repo.one(c, "grades", ("score", "status"), rid, "rowid") if table == "grades" else None
                if prior and prior["status"] != "published":
                    legacy["status"] = prior["status"]           # a teacher's draft stays a draft until the teacher publishes it
                repo.update(c, table, rid, {**values, **({"updated_at": t} if table in STAMPED else {}), **legacy}, key)
                if prior and prior["status"] == "published" and prior["score"] != values["score"]:
                    journal.log_change(c, values["user_id"], values["course_id"], str(values["component"]), prior["score"], values["score"],
                                       user_id, ctx.reason, t)        # every change of a published score is in the grade journal
            if it.action == "overwrite":
                audit(c, user_id, "import_overwrite", it.link, f"#{rid} · {ctx.source}:{it.source_id} · {', '.join(it.extra['fields'])}")
        it.row_id = rid
        if it.link in UNIT_LINKS and it.action != "relink":
            repo.set_groups(c, rid, it.groups or [])
        written = domain.row_hash({**values, **({"groups": it.groups} if it.link in UNIT_LINKS else {})})
        for sid in (it.source_id, *it.extra.get("aliases", [])):
            repo.link(c, it.link, ctx.source, sid, rid, written)
        done += it.action != "relink"
    return done


def run(c, kind: str, source: str, filename: str, data: bytes, *, dry_run: bool = False, prefer_source: bool = False,
        user_id: int | None = None, max_rows: int | None = None, as_of: str | None = None, force: bool = False,
        detail: bool = False, on_written=None) -> dict:
    """Import one file; the report says what was (or, with ``dry_run``, would be) written. ``as_of``: the cut-over date of
    the export for the journal kinds (a row may also carry its own). A writing import does not start while an exam is
    going on, unless ``force`` (audited). ``on_written(c, report)`` runs in the import's own transaction before it commits
    (the migration's file log, Checkpoint F SF-F5)."""
    if kind not in domain.KINDS:
        raise tables.TableError("Naməlum idxal növü")
    if not domain.SOURCE.fullmatch(source or ""):
        raise tables.TableError("Mənbə sisteminin adını yazın (--source)")
    if as_of is not None and (kind not in domain.JOURNAL_KINDS or domain.a_date(as_of) != as_of or as_of > now().date().isoformat()):
        raise tables.TableError("Kəsid tarixi (--as-of) yalnız jurnal növləri üçün göstərilir və İİİİ-AA-GG formatında, bu gündən gec olmayan tarix olmalıdır")
    if kind == "status-events" and user_id is None and not dry_run:
        raise tables.TableError("Status əmrini idxal edən hesab göstərilməlidir (--by)")   # it is the order's "entered by"
    going = 0 if dry_run else exam.open_count(c)
    if going and not force:
        raise tables.TableError("İmtahan gedir: məlumat yazan idxal imtahan bağlandıqdan sonra başlaya bilər")
    started = time.monotonic()
    errors: list = []
    conflicts: list = []
    more: dict = {}                                     # teaching-load: the reader's report for the screen and the CLI
    if kind == "teaching-load":
        items, form_report = _plan_load(c, filename, data, conflicts)
        more = {"forma3": form_report}
        ctx = Context(c, source, ("teaching_load",))
        total = len(items) + len(conflicts)
    else:
        cells, problem = _cells(kind, filename, data)
        if problem:
            return _report(kind, source, 0, [], [{"row": 1, "reason": problem}], [], dry_run, None, started)
        if max_rows and len(cells) > max_rows:
            raise tables.TableError("Ekrandan ən çox 20 000 sətir idxal olunur; böyük faylı manage.py ilə idxal edin")
        if len(cells) > MAX_FILE_ROWS:
            raise tables.TableError("Bir faylda ən çox 200 000 sətir idxal olunur: faylı hissələrə bölün")
        for n, x in cells if as_of else ():             # the export's date for every row that names none (Task 38)
            if x.get("asOf") and domain.a_date(x["asOf"]) != as_of:
                errors.append({"row": n, "reason": E("Sətrin tarixi --as-of tarixinə uyğun gəlmir")})
            x["asOf"] = as_of
        links = {"users": ("users",), "orgs": ("faculties", "departments"), "terms": ("terms",), "courses": ("courses",),
                 "classes": ("classes",), "enrollments": ("unit_teachers", "enrollments", "users"), "timetable": ("timetable",),
                 "rooms": ("rooms",), "attendance-opening": ("attendance_opening", "users"), "grades": ("grades", "users"),
                 "attendance": ("attendance", "users"), "results": ("results", "users"), "status-events": ("status_events", "users")}[kind]
        ctx = Context(c, source, links, [domain.source_key(kind, x) for _, x in cells] if kind in domain.COMPOSITE_KEYS else None)
        ctx.reason = f"import:{filename}:{hashlib.sha256(data).hexdigest()}"
        ctx.file_faculties = {x["sourcedId"] for _, x in cells if domain.ORG_TYPES.get(domain.norm(x.get("type", ""))) == "faculties"}
        items = _plan_rows(kind, ctx, cells, errors)
        total = len(cells)
    _classify(ctx, items, prefer_source, conflicts, errors)
    _uniques(kind, ctx, items, errors)
    warnings = _held_check(c, items) if kind == "attendance-opening" else []
    if errors or dry_run:
        out = {**_report(kind, source, total, items, errors, conflicts, dry_run, None, started), **more, "warnings": warnings,
               "checksums": _checksums(items), "hours": _hours(items) if kind in ("attendance", "attendance-opening") else {}}
        if detail:                                    # the reconciliation's sample and difference list (Task 38)
            out["items"] = [{"row": it.row, "source_id": it.source_id, "link": it.link, "row_id": it.row_id, "action": it.action,
                             "values": {k: str(v) if isinstance(v, Pending) else v for k, v in _new(it).items()},
                             "fields": it.extra.get("fields", []), "linked": it.source_id in ctx.links.get(it.link, {}),
                             "aliases": len(it.extra.get("aliases", []))} for it in items]
        return out
    c.commit()                                          # nothing of the request may be pending before the import's own transaction
    lock = time.monotonic()
    c.execute("BEGIN IMMEDIATE")
    try:
        going = exam.open_count(c)                     # again under the lock: an exam may have opened while the file was read (PY-F1)
        if going and not force:
            raise tables.TableError("İmtahan gedir: məlumat yazan idxal imtahan bağlandıqdan sonra başlaya bilər")
        _write(c, ctx, items, user_id, conflicts)
        for finish in loaders.FINISH:                  # the effects of the newest status order per student (AR-F1)
            finish(c, items)
        if kind in ("grades", "attendance-opening", "attendance"):    # the final grades follow the imported scores and hours
            by_course: dict[int, set[int]] = {}
            for it in items:
                if it.action in ("insert", "update", "overwrite"):
                    v = it.values
                    by_course.setdefault(v.get("course_id") or it.extra["course_id"], set()).add(v.get("user_id") or v["student_id"])
            for cid, uids in sorted(by_course.items()):
                journal.refresh_finals(c, cid, uids)
        counts = _counts(items)
        audit(c, user_id, "import", kind, f"{source} · {filename} · +{counts['inserted']} ~{counts['updated']} "
                                          f"={counts['unchanged']} !{len(conflicts)}")
        if going:
            audit(c, user_id, "import_forced", kind, f"{source} · {filename} · exams open: {going}")
        report = {**_report(kind, source, total, items, [], conflicts, False, time.monotonic() - lock, started), **more,
                  "warnings": warnings}
        if on_written:
            on_written(c, report)
        c.commit()
    except sqlite3.IntegrityError:                      # another writer took a unique value after the check
        c.rollback()
        raise tables.TableError("Məlumat idxal yoxlanarkən dəyişdi; faylı yenidən yoxlayıb idxal edin") from None
    except BaseException:
        c.rollback()
        raise
    return report


def _held_check(c, items: list[Item]) -> list[dict]:
    """Opening rows whose held hours differ from what Zəka planned up to their date: listed, not refused (Task 20)."""
    out = []
    for it in items:
        v = it.values
        planned = journal.planned_until(c, v["student_id"], v["course_id"], v["as_of"])
        if planned is not None and planned != v["held_hours"]:
            out.append({"row": it.row, "reason": E("Keçilmiş saatlar Zəka platformasındakı plandan fərqlidir: faylda {a}, Zəka platformasında {b}",
                                                   a=v["held_hours"], b=planned)})
    return out


def _checksums(items: list[Item]) -> dict:
    """The file's rows as the source has them and as Zəka holds them (a row not in Zəka: '-'): equal when nothing differs.
    The reconciliation compares the two (Task 38)."""
    src, cur = hashlib.sha256(), hashlib.sha256()
    for it in sorted(items, key=lambda i: i.source_id):
        new = domain.row_hash(_new(it))
        src.update(f"{it.source_id}:{new}\n".encode())
        cur.update(f"{it.source_id}:{new if it.action in ('unchanged', 'relink') else it.extra.get('cur_hash', '-')}\n".encode())
    return {"source": src.hexdigest(), "zeka": cur.hexdigest()}


def _hours(items: list[Item]) -> dict[str, list[int]]:
    """{"<student>|<course>": [unexcused, excused]} hours the file's rows hold, per student and course."""
    out: dict[str, list[int]] = {}
    for it in items:
        v = it.values
        if it.link == "attendance_opening":
            out[f"{v['student_id']}|{v['course_id']}"] = [v["unexcused_hours"], v["excused_hours"]]
        elif it.link == "attendance":
            pair = out.setdefault(f"{v['user_id']}|{it.extra['course_id']}", [0, 0])
            if v["status"] in ("absent", "excused"):
                pair[v["status"] == "excused"] += it.extra["hours"]
    return out


def _counts(items: list[Item]) -> dict:
    return {"inserted": sum(i.action == "insert" for i in items), "updated": sum(i.action in ("update", "overwrite") for i in items),
            "unchanged": sum(i.action in ("unchanged", "relink") for i in items), "overwritten": sum(i.action == "overwrite" for i in items)}


def _report(kind, source, total, items, errors, conflicts, dry_run, lock_s, started) -> dict:
    return {"kind": kind, "source": source, "rows": total, **_counts(items), "conflicts": conflicts, "errors": errors[:500],
            "error_count": len(errors), "dry_run": dry_run, "written": lock_s is not None,
            "lock_ms": round(lock_s * 1000, 1) if lock_s is not None else None, "seconds": round(time.monotonic() - started, 2)}


# ---------------------------------------------------------------- activation codes
def activation_days(c) -> int:
    v = setting(c, "activation_days", 14)
    return v if isinstance(v, int) and 1 <= v <= 90 else 14


def issue_codes(c, admin_id: int | None, faculty_id: int) -> list[dict]:
    """New codes for the faculty's students without a password; their earlier unused codes stop working. The codes exist
    only in this answer: the database keeps their SHA-256."""
    students = repo.faculty_students(c, faculty_id)
    t = now()
    expires = iso(t + timedelta(days=activation_days(c)))
    out, items = [], []
    for s in students:
        raw = "".join(secrets.choice(domain.CODE_ALPHABET) for _ in range(12))
        items.append((s["id"], domain.code_hash(raw)))
        out.append({"student_no": s["student_no"], "full_name": s["full_name"], "group": s["grp"], "username": s["username"],
                    "code": domain.pretty_code(raw), "expires_at": expires})
    repo.revoke_codes(c, [s["id"] for s in students], iso(t))
    repo.add_codes(c, items, iso(t), expires)
    audit(c, admin_id, "activation_codes", "faculty", f"#{faculty_id} · {len(out)}")
    return out


def activate(c, student_no: str, code: str, password: str, ip: str, t: float | None = None):
    """('ok', user) | ('blocked', seconds) | ('wrong', None) | ('weak', reason). A wrong code counts against the
    (student number, address) pair like a wrong password (Task 10) and does not spend the code."""
    t = time.time() if t is None else t
    account = "activation:" + student_no.strip().lower()[:64]
    wait = identity.throttle_wait(c, account, ip, t)
    if wait:
        return "blocked", math.ceil(wait)
    hit = repo.code(c, domain.code_hash(code)) if domain.code_shape_ok(code) else None
    ok = bool(hit and hit["student_no"] and hit["student_no"].lower() == student_no.strip().lower() and not hit["used_at"]
              and not hit["revoked_at"] and hit["expires_at"] > iso(now()) and hit["status"] == "active" and hit["role"] == "student"
              and not hit["password_hash"] and not hit["totp_enabled_at"] and not hit["sso"])     # only an account with no way in yet
    if not ok or hit is None:
        identity.throttle_failure(c, account, ip, t)
        return "wrong", None
    u = identity.account(c, hit["user_id"])
    if u is None:
        return "wrong", None
    problem = identity.password_problem(u, password)
    if problem:
        return "weak", problem
    new_hash = identity_rules.hash_password(password)       # before the writes: no write lock is held while it computes
    if not repo.spend_code(c, hit["id"], iso(now())):
        return "wrong", None
    identity.set_password(c, u["id"], new_hash)
    audit(c, u["id"], "account_activated", "user", u["username"])
    return "ok", identity.account(c, u["id"])
