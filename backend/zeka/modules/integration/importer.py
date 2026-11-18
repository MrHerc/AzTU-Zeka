"""Bulk import (tasks/todo.md, Task 16): one file of one kind from one source system, all or nothing.

1. Read and check every row; resolve its references against what Zəka holds. Any refused row: nothing is written and
   the report names each row and the reason.
2. Compare each row with its linked row (import_links): unchanged, an update (the source changed it), or a conflict
   (Zəka changed it since the import and the file says otherwise: not overwritten unless ``prefer_source``, audited).
3. Write in one BEGIN IMMEDIATE transaction; the report gives how long it held the write lock.
"""
from __future__ import annotations

import math
import secrets
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import timedelta

from ...core.i18n import E
from ...legacy.store import audit, iso, now, setting
from ..identity import domain as identity_rules
from ..identity import service as identity
from . import domain, forma3, repo, tables

MAX_SCREEN_ROWS = 20_000
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
    "teaching_load": ("teaching_units", ("course_id", "kind", "subgroup", "teacher_id", "hours", "students"), "id"),
    "rooms": ("rooms", ("code", "number", "name", "building_id", "floor", "kind", "capacity", "accessible"), "id"),
}
UNIT_LINKS = ("classes", "teaching_load")           # these also carry the unit's groups
STAMPED = ("faculties", "departments", "academic_terms", "courses", "teaching_units", "rooms")
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

    def __init__(self, c, source: str, links: tuple[str, ...]):
        self.c, self.source = c, source
        self.links = {k: repo.links(c, k, source) for k in links}
        self.rows = {k: repo.table(c, TARGETS[k][0], TARGETS[k][1], TARGETS[k][2]) for k in links}
        self.groups = repo.unit_groups(c)
        self.file_faculties: set[str] = set()          # orgs: faculties of this same file, for their departments
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


def _course_for(c, cache: dict, subject: str, semester: str) -> int | None:
    if "courses" not in cache:
        cache["courses"] = [dict(r) for r in c.execute("SELECT co.id, co.name, t.name term, t.code term_code FROM courses co "
                                                       "LEFT JOIN academic_terms t ON t.id=co.term_id WHERE co.active=1")]
    same = [x for x in cache["courses"] if forma3.norm(x["name"]) == forma3.norm(subject)]
    if len(same) > 1:
        same = [x for x in same if semester in forma3.norm(f"{x['term'] or ''} {x['term_code'] or ''}")]
    return same[0]["id"] if len(same) == 1 else None


def _plan_load(c, filename: str, data: bytes, conflicts: list) -> list[Item]:
    if not (filename or "").lower().endswith(".xlsx"):
        raise tables.TableError("Forma №3 XLSX faylı olmalıdır")
    lines, skipped = forma3.read(tables.xlsx_sheets(data))
    conflicts += [{"row": f"{sheet}!{n}", "reason": reason} for sheet, n, reason in skipped]
    if not lines and not skipped:
        raise tables.TableError("Faylda Forma №3 tədris yükü tapılmadı")
    people = _person_index(c)
    groups = {forma3.norm(k): v for k, v in repo.by_column(c, "study_groups", "name").items()}
    cache: dict = {}
    items = []
    for ln in lines:
        where = f"{ln.sheet}!{ln.row}"
        teacher = _teacher(people, ln.teacher)
        course = _course_for(c, cache, ln.subject, ln.semester)
        missing = [g for g, _ in ln.groups if forma3.norm(g) not in groups]
        reason = (_missing("Müəllim", ln.teacher) if not teacher else _missing("Fənn", ln.subject) if not course
                  else _missing("Qrup", ", ".join(missing)) if missing else None)
        if reason:
            conflicts.append({"row": where, "reason": reason})
            continue
        subgroup = ln.groups[0][1] if len(ln.groups) == 1 else None
        sid = _key(ln.sheet, ln.teacher, ln.subject, ln.semester, ln.kind, sorted(f"{g} {s or ''}" for g, s in ln.groups))
        items.append(Item(0, "teaching_load", sid, {"course_id": course, "kind": ln.kind, "subgroup": subgroup, "teacher_id": teacher,
                                                     "hours": ln.hours, "students": ln.students},
                          groups=sorted({groups[forma3.norm(g)] for g, _ in ln.groups}), extra={"where": where}))
    seen: dict[str, Item] = {}
    for it in items:                                   # the same unit twice in one form: its hours add up, and it is said
        if it.source_id in seen:
            seen[it.source_id].values["hours"] += it.values["hours"]
            conflicts.append({"row": it.extra["where"], "reason": E("Eyni tədris vahidi formada təkrarlanır: saatlar toplandı ({x})",
                                                                    x=seen[it.source_id].extra["where"])})
        else:
            seen[it.source_id] = it
    return list(seen.values())


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


def _classify(ctx: Context, items: list[Item], prefer: bool, conflicts: list, errors: list):
    for it in items:
        link = ctx.links[it.link].get(it.source_id)
        rid = link["row_id"] if link and link["row_id"] in ctx.rows[it.link] else None
        it.row_id = rid or (it.natural if it.natural in ctx.rows[it.link] else None)
        if it.link == "users" and it.row_id and ctx.rows["users"][it.row_id]["role"] not in IMPORTED_ROLES:
            errors.append({"row": it.row, "reason": E("Bu hesab idxalla dəyişdirilmir")})
            continue
        cur = _current(ctx, it) if it.row_id else None
        if cur is None:
            it.action = "insert" if it.link != "unit_teachers" else "missing"
            if it.action == "missing":
                errors.append({"row": it.row, "reason": _missing("Tədris vahidi", it.source_id)})
            continue
        new_hash, cur_hash = domain.row_hash(_new(it)), domain.row_hash(cur)
        it.extra["cur_hash"] = cur_hash
        if new_hash == cur_hash:
            it.action = "unchanged" if link and link["source_hash"] == new_hash else "relink"
        elif link and cur_hash == link["source_hash"]:
            it.action = "update"
        elif not link and all(cur[k] in (None, []) for k in cur if cur[k] != _new(it).get(k)):
            it.action = "update"                       # a row never imported: filling its empty fields overwrites nothing
        else:
            changed = sorted(k for k in cur if cur[k] != _new(it).get(k))
            it.action = "overwrite" if prefer else "conflict"
            it.extra["fields"] = changed
            if not prefer:
                conflicts.append({"row": it.extra.get("where", it.row), "id": it.row_id, "fields": changed,
                                  "reason": E("Zəka-da dəyişdirilib; mənbənin dəyəri yazılmadı")})


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


def _write(c, ctx: Context, items: list[Item], user_id: int | None, conflicts: list) -> int:
    new_ids: dict[tuple[str, str], int] = {}
    t = iso(now())
    done = 0
    order = {k: i for i, k in enumerate(("faculties", "departments"))}
    for it in sorted(items, key=lambda x: order.get(x.link, 9)):
        if it.action in ("unchanged", "conflict"):
            continue
        values = {k: (new_ids[(v.link, v.source_id)] if isinstance(v, Pending) else v) for k, v in it.values.items()}
        table, cols, key = TARGETS[it.link]
        if it.action == "insert":
            extra: dict = {"synthetic": 0} if table == "users" else {"created_at": t, "updated_at": t} if table in STAMPED else {}
            rid = repo.insert(c, table, {**values, **extra})
            new_ids[(it.link, it.source_id)] = rid
        else:
            rid = it.row_id if it.row_id is not None else 0       # set by _classify for every action but insert
            if it.action == "update" and _now_hash(c, it) != it.extra.get("cur_hash"):
                it.action = "conflict"                            # changed in Zəka while the file was being checked
                conflicts.append({"row": it.extra.get("where", it.row), "id": rid,
                                  "reason": E("İdxal yoxlanarkən Zəka-da dəyişdirildi; mənbənin dəyəri yazılmadı")})
                continue
            if it.action in ("update", "overwrite") and it.link == "users":
                before = repo.one(c, "users", ("role", "status"), rid)
                if before and (before["role"], before["status"]) != (values["role"], values["status"]):
                    identity.end_all_sessions(c, rid)             # a new role or status starts from a new sign-in
            if it.action in ("update", "overwrite"):
                repo.update(c, table, rid, {**values, **({"updated_at": t} if table in STAMPED else {})}, key)
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
        user_id: int | None = None, max_rows: int | None = None) -> dict:
    """Import one file; the report says what was (or, with ``dry_run``, would be) written."""
    if kind not in domain.KINDS:
        raise tables.TableError("Naməlum idxal növü")
    if not domain.SOURCE.fullmatch(source or ""):
        raise tables.TableError("Mənbə sisteminin adını yazın (--source)")
    started = time.monotonic()
    errors: list = []
    conflicts: list = []
    if kind == "teaching-load":
        items = _plan_load(c, filename, data, conflicts)
        ctx = Context(c, source, ("teaching_load",))
        total = len(items) + len(conflicts)
    else:
        cells, problem = _cells(kind, filename, data)
        if problem:
            return _report(kind, source, 0, [], [{"row": 1, "reason": problem}], [], dry_run, None, started)
        if max_rows and len(cells) > max_rows:
            raise tables.TableError("Ekrandan ən çox 20 000 sətir idxal olunur; böyük faylı manage.py ilə idxal edin")
        links = {"users": ("users",), "orgs": ("faculties", "departments"), "terms": ("terms",), "courses": ("courses",),
                 "classes": ("classes",), "enrollments": ("unit_teachers", "enrollments", "users"), "timetable": ("timetable",),
                 "rooms": ("rooms",)}[kind]
        ctx = Context(c, source, links)
        ctx.file_faculties = {x["sourcedId"] for _, x in cells if domain.ORG_TYPES.get(domain.norm(x.get("type", ""))) == "faculties"}
        items = _plan_rows(kind, ctx, cells, errors)
        total = len(cells)
    _classify(ctx, items, prefer_source, conflicts, errors)
    _uniques(kind, ctx, items, errors)
    if errors or dry_run:
        return _report(kind, source, total, items, errors, conflicts, dry_run, None, started)
    c.commit()                                          # nothing of the request may be pending before the import's own transaction
    lock = time.monotonic()
    c.execute("BEGIN IMMEDIATE")
    try:
        _write(c, ctx, items, user_id, conflicts)
        counts = _counts(items)
        audit(c, user_id, "import", kind, f"{source} · {filename} · +{counts['inserted']} ~{counts['updated']} "
                                          f"={counts['unchanged']} !{len(conflicts)}")
        c.commit()
    except sqlite3.IntegrityError:                      # another writer took a unique value after the check
        c.rollback()
        raise tables.TableError("Məlumat idxal yoxlanarkən dəyişdi; faylı yenidən yoxlayıb idxal edin") from None
    except BaseException:
        c.rollback()
        raise
    return _report(kind, source, total, items, [], conflicts, False, time.monotonic() - lock, started)


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
