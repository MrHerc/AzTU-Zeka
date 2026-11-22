"""SQL of the timetable module (tasks/todo.md, Task 19)."""
from __future__ import annotations

import json

from ...legacy.store import row, rows

ROW_COLS = ("t.id, t.course_id, t.weekday, t.start, t.end, t.kind, t.room, t.room_id, t.unit_id, t.academic_hours, t.weeks, "
            "t.active, co.name course, co.code course_code, co.term_id, u.kind unit_kind, u.subgroup, "
            "COALESCE(u.teacher_id, co.teacher_id) teacher_id, tu.full_name teacher, t.meeting_key, t.period, t.version_id")
ROW_FROM = ("timetable t JOIN courses co ON co.id=t.course_id LEFT JOIN teaching_units u ON u.id=t.unit_id "
            "LEFT JOIN users tu ON tu.id=COALESCE(u.teacher_id, co.teacher_id)")


def unit(c, unit_id: int):
    return row(c, "SELECT u.*, co.term_id, co.name course, COALESCE(u.teacher_id, co.teacher_id) teacher FROM teaching_units u "
                  "JOIN courses co ON co.id=u.course_id WHERE u.id=?", (unit_id,))


def groups_of_units(c, unit_ids: list[int]) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {u: [] for u in unit_ids}
    for i in range(0, len(unit_ids), 500):
        part = unit_ids[i:i + 500]
        for r in rows(c, f"SELECT unit_id, group_id FROM teaching_unit_groups WHERE unit_id IN ({','.join('?' * len(part))}) "  # nosec B608
                         "ORDER BY group_id", tuple(part)):
            out[r["unit_id"]].append(r["group_id"])
    return out


def group_names(c, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {g["id"]: g["name"] for g in rows(c, f"SELECT id, name FROM study_groups WHERE id IN ({','.join('?' * len(ids))})",  # nosec B608
                                             tuple(ids))}


def row_by_id(c, rid: int):
    return row(c, f"SELECT {ROW_COLS} FROM {ROW_FROM} WHERE t.id=?", (rid,))  # nosec B608 (constant SQL)


def term_rows(c, term_id: int | None, weekday: int | None = None) -> list[dict]:
    """The active rows of a term's courses (term None: of the courses with no term)."""
    where, args = ("co.term_id=?", [term_id]) if term_id else ("co.term_id IS NULL", [])
    if weekday:
        where += " AND t.weekday=?"
        args.append(weekday)
    return rows(c, f"SELECT {ROW_COLS} FROM {ROW_FROM} WHERE t.active=1 AND {where} ORDER BY t.weekday, t.start, t.id",  # nosec B608
                tuple(args))


def listed(c, term_id: int | None, group_id: int | None, teacher_id: int | None, limit: int = 1000) -> list[dict]:
    where, args = ["t.active=1"], []
    if term_id:
        where.append("co.term_id=?")
        args.append(term_id)
    if group_id:
        where.append("t.unit_id IN (SELECT unit_id FROM teaching_unit_groups WHERE group_id=?)")
        args.append(group_id)
    if teacher_id:
        where.append("COALESCE(u.teacher_id, co.teacher_id)=?")
        args.append(teacher_id)
    return rows(c, f"SELECT {ROW_COLS} FROM {ROW_FROM} WHERE {' AND '.join(where)} ORDER BY t.weekday, t.start, t.id LIMIT ?",  # nosec B608
                (*args, limit))


def insert_row(c, v: dict, stamp: str) -> int:
    return c.execute("INSERT INTO timetable(course_id,weekday,start,end,kind,room,room_id,unit_id,academic_hours,weeks,active,updated_at) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,1,?)", (v["course_id"], v["weekday"], v["start"], v["end"], v["kind"], v["room"],
                                                         v["room_id"], v["unit_id"], v["academic_hours"], v["weeks"], stamp)).lastrowid


def update_row(c, rid: int, v: dict, stamp: str):
    cols = ("weekday", "start", "end", "room", "room_id", "academic_hours", "weeks")
    c.execute(f"UPDATE timetable SET {', '.join(k + '=?' for k in cols)}, updated_at=? WHERE id=?",  # nosec B608 (constant columns)
              (*(v[k] for k in cols), stamp, rid))


def deactivate_row(c, rid: int, stamp: str):
    c.execute("UPDATE timetable SET active=0, updated_at=? WHERE id=?", (stamp, rid))


def future_lessons(c, rid: int, after_day: str) -> list[dict]:
    """Scheduled lessons of a row after ``after_day`` that nobody recorded."""
    return rows(c, "SELECT id, day, start, slot_day, slot_start, teacher_id FROM lessons WHERE timetable_id=? AND day>? "
                   "AND status='scheduled' AND NOT EXISTS (SELECT 1 FROM attendance a WHERE a.lesson_id=lessons.id)", (rid, after_day))


def drop_lessons(c, ids: list[int]):
    c.executemany("DELETE FROM lessons WHERE id=?", [(i,) for i in ids])


def drop_future_lessons(c, rid: int, after_day: str) -> int:
    """Lessons of a row after ``after_day`` that nobody recorded: they have not happened and are made again."""
    return c.execute("DELETE FROM lessons WHERE timetable_id=? AND day>? AND status='scheduled' "
                     "AND NOT EXISTS (SELECT 1 FROM attendance a WHERE a.lesson_id=lessons.id)", (rid, after_day)).rowcount


def add_lessons(c, values: list[tuple]) -> int:
    before = c.total_changes
    c.executemany("INSERT OR IGNORE INTO lessons(course_id,day,start,end,kind,room,room_id,unit_id,teacher_id,academic_hours,"
                  "timetable_id,slot_day,slot_start,status,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'scheduled',?)", values)
    return c.total_changes - before


def add_imported_lesson(c, unit_id: int, day: str, start: str, end: str, hours: int, kind: str | None, at: str) -> int:
    """A held lesson of the old system that the timetable did not plan (Task 38), in the slot its record names."""
    return c.execute("INSERT INTO lessons(course_id,day,start,end,kind,unit_id,teacher_id,academic_hours,slot_day,slot_start,status,"
                     "updated_at) SELECT u.course_id,?,?,?,?,u.id,COALESCE(u.teacher_id, co.teacher_id),?,?,?,'scheduled',? "
                     "FROM teaching_units u JOIN courses co ON co.id=u.course_id WHERE u.id=?",
                     (day, start, end, kind, hours, day, start, at, unit_id)).lastrowid


def lesson(c, lid: int):
    return row(c, "SELECT l.*, co.name course FROM lessons l JOIN courses co ON co.id=l.course_id WHERE l.id=?", (lid,))


def lessons_on(c, day: str, group_id: int | None = None, teacher_id: int | None = None) -> list[dict]:
    where: list[str] = ["l.day=?"]
    args: list[object] = [day]
    if group_id:
        where.append("l.unit_id IN (SELECT unit_id FROM teaching_unit_groups WHERE group_id=?)")
        args.append(group_id)
    if teacher_id:
        where.append("l.teacher_id=?")
        args.append(teacher_id)
    return rows(c, "SELECT l.id, l.course_id, l.day, l.start, l.end, l.kind, l.room, l.room_id, l.unit_id, l.teacher_id, l.status, "
                   "l.note, l.academic_hours, co.name course, tu.full_name teacher, u.subgroup FROM lessons l "
                   "JOIN courses co ON co.id=l.course_id LEFT JOIN teaching_units u ON u.id=l.unit_id "
                   f"LEFT JOIN users tu ON tu.id=l.teacher_id WHERE {' AND '.join(where)} ORDER BY l.start, l.id", tuple(args))  # nosec B608


def has_attendance(c, lid: int) -> bool:
    return row(c, "SELECT 1 FROM attendance WHERE lesson_id=? LIMIT 1", (lid,)) is not None


def set_lesson(c, lid: int, values: dict, stamp: str):
    cols = list(values)
    c.execute(f"UPDATE lessons SET {', '.join(k + '=?' for k in cols)}, updated_at=? WHERE id=?",  # nosec B608 (constant columns)
              (*values.values(), stamp, lid))


def unit_subgroups(c, unit_ids: list[int]) -> dict[int, int | None]:
    out: dict[int, int | None] = {}
    for i in range(0, len(unit_ids), 500):
        part = unit_ids[i:i + 500]
        for r in rows(c, f"SELECT id, subgroup FROM teaching_units WHERE id IN ({','.join('?' * len(part))})", tuple(part)):  # nosec B608
            out[r["id"]] = r["subgroup"]
    return out


def enrolled(c, course_id: int, day: str) -> list[dict]:
    return rows(c, "SELECT u.id, COALESCE(e.group_id, u.group_id) group_id, e.subgroup FROM enrollments e JOIN users u ON u.id=e.user_id "
                   "WHERE e.course_id=? AND u.status='active' AND (e.begin_date IS NULL OR e.begin_date<=?) "
                   "AND (e.end_date IS NULL OR e.end_date>?)", (course_id, day, day))


# ---------------------------------------------------------------- calendar feeds
def feed_owner(c, token_hash: str):
    return row(c, "SELECT u.* FROM ical_feeds f JOIN users u ON u.id=f.user_id WHERE f.token_hash=? AND u.status='active'", (token_hash,))


def has_feed(c, uid: int) -> bool:
    return row(c, "SELECT 1 FROM ical_feeds WHERE user_id=?", (uid,)) is not None


def set_feed(c, uid: int, token_hash: str, stamp: str):
    c.execute("INSERT INTO ical_feeds(user_id,token_hash,created_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
              "token_hash=excluded.token_hash, created_at=excluded.created_at", (uid, token_hash, stamp))


def drop_feed(c, uid: int) -> bool:
    return c.execute("DELETE FROM ical_feeds WHERE user_id=?", (uid,)).rowcount > 0


def teacher_lessons(c, uid: int, first: str, last: str) -> list[dict]:
    return rows(c, "SELECT l.id, l.day, l.start, l.end, l.kind, l.room, l.room_id, l.status, l.note, co.name course FROM lessons l "
                   "JOIN courses co ON co.id=l.course_id WHERE l.teacher_id=? AND l.day BETWEEN ? AND ? ORDER BY l.day, l.start",
                (uid, first, last))


def student_lessons(c, uid: int, first: str, last: str) -> list[dict]:
    """The lessons of the units a student attends: an enrolment in force on the day, the unit's group and subgroup."""
    return rows(c, "SELECT l.id, l.day, l.start, l.end, l.kind, l.room, l.room_id, l.status, l.note, co.name course FROM enrollments e "
                   "JOIN users s ON s.id=e.user_id JOIN lessons l ON l.course_id=e.course_id JOIN courses co ON co.id=l.course_id "
                   "LEFT JOIN teaching_units u ON u.id=l.unit_id WHERE e.user_id=? AND l.day BETWEEN ? AND ? "
                   "AND (e.begin_date IS NULL OR e.begin_date<=l.day) AND (e.end_date IS NULL OR e.end_date>l.day) "
                   "AND (u.subgroup IS NULL OR u.subgroup=e.subgroup) AND (l.unit_id IS NULL OR NOT EXISTS "
                   "(SELECT 1 FROM teaching_unit_groups g WHERE g.unit_id=l.unit_id) OR EXISTS (SELECT 1 FROM teaching_unit_groups g "
                   "WHERE g.unit_id=l.unit_id AND g.group_id=COALESCE(e.group_id, s.group_id))) ORDER BY l.day, l.start",
                (uid, first, last))


# ---------------------------------------------------------------- the timetable builder (Task 48, slice 2)
def _in(ids) -> str:
    return ",".join("?" * len(ids))


def _chunks(ids: list, size: int = 500):
    for i in range(0, len(ids), size):
        yield ids[i:i + size]


UNIT_COLS = ("u.id, u.course_id, u.kind, u.teacher_id, u.subgroup, u.hours, u.students, co.department_id, d.faculty_id, "
             "co.name course, co.term_id")
UNIT_FROM = "teaching_units u JOIN courses co ON co.id=u.course_id LEFT JOIN departments d ON d.id=co.department_id"


def grants(c, uid: int, role: str) -> list[dict]:
    return rows(c, "SELECT scope_type, scope_id FROM role_grants WHERE user_id=? AND role=?", (uid, role))


def user_unit(c, uid: int):
    """A person's department and its faculty (a head without a grant covers its own department)."""
    return row(c, "SELECT u.id, u.role, u.status, u.full_name, u.department_id, d.faculty_id FROM users u "
                  "LEFT JOIN departments d ON d.id=u.department_id WHERE u.id=?", (uid,))


def user_names(c, ids: list[int]) -> dict[int, str]:
    out: dict[int, str] = {}
    for part in _chunks(sorted(ids)):
        out.update({r["id"]: r["full_name"] for r in rows(c, f"SELECT id, full_name FROM users WHERE id IN ({_in(part)})", tuple(part))})  # nosec B608
    return out


def term_units(c, term_id: int) -> list[dict]:
    """The active teaching units of a term's active courses, with their department and faculty."""
    return rows(c, f"SELECT {UNIT_COLS} FROM {UNIT_FROM} WHERE co.term_id=? AND co.active=1 AND u.active=1 ORDER BY u.id",  # nosec B608
                (term_id,))


def units_by_id(c, ids: list[int]) -> list[dict]:
    out: list[dict] = []
    for part in _chunks(sorted(ids)):
        out += rows(c, f"SELECT {UNIT_COLS} FROM {UNIT_FROM} WHERE u.id IN ({_in(part)}) AND u.active=1 AND co.active=1", tuple(part))  # nosec B608
    return sorted(out, key=lambda u: u["id"])


def term_unit_groups(c, term_id: int) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for r in rows(c, "SELECT g.unit_id, g.group_id FROM courses co JOIN teaching_units u ON u.course_id=co.id "
                     "JOIN teaching_unit_groups g ON g.unit_id=u.id WHERE co.term_id=? AND u.active=1 ORDER BY g.unit_id, g.group_id",
                  (term_id,)):
        out.setdefault(r["unit_id"], []).append(r["group_id"])
    return out


def teacher_term_units(c, term_id: int, teacher_id: int) -> list[int]:
    return [r["id"] for r in rows(c, "SELECT u.id FROM teaching_units u JOIN courses co ON co.id=u.course_id WHERE u.teacher_id=? "
                                     "AND co.term_id=? AND u.active=1 AND co.active=1", (teacher_id, term_id))]


def group_term_units(c, term_id: int, group_ids: list[int]) -> list[int]:
    out: set[int] = set()
    for part in _chunks(sorted(group_ids)):
        out.update(r["unit_id"] for r in rows(c, f"SELECT g.unit_id FROM teaching_unit_groups g JOIN teaching_units u ON u.id=g.unit_id "  # nosec B608
                                                 f"JOIN courses co ON co.id=u.course_id WHERE g.group_id IN ({_in(part)}) AND co.term_id=? "
                                                 "AND u.active=1", (*part, term_id)))
    return sorted(out)


def groups_info(c, ids: list[int]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for part in _chunks(sorted(ids)):
        for r in rows(c, f"SELECT id, name, faculty_id, active FROM study_groups WHERE id IN ({_in(part)})", tuple(part)):  # nosec B608
            out[r["id"]] = r
    return out


def registry_sizes(c, group_ids: list[int]) -> dict[int, int]:
    out: dict[int, int] = {}
    for part in _chunks(sorted(group_ids)):
        for r in rows(c, f"SELECT group_id, COUNT(*) n FROM users WHERE group_id IN ({_in(part)}) AND role='student' "  # nosec B608
                         "AND status='active' GROUP BY group_id", tuple(part)):
            out[r["group_id"]] = r["n"]
    return out


def group_terms(c, term_id: int) -> dict[int, dict]:
    return {r["group_id"]: r for r in rows(c, "SELECT group_id, shift, home_building_id FROM tt_group_terms WHERE term_id=?", (term_id,))}


def set_group_term(c, term_id: int, gid: int, shift, building, uid: int, at: str):
    c.execute("INSERT INTO tt_group_terms(term_id,group_id,shift,home_building_id,updated_by,updated_at) VALUES(?,?,?,?,?,?) "
              "ON CONFLICT(term_id, group_id) DO UPDATE SET shift=excluded.shift, home_building_id=excluded.home_building_id, "
              "updated_by=excluded.updated_by, updated_at=excluded.updated_at", (term_id, gid, shift, building, uid, at))


def building_ids(c) -> set[int]:
    return {r["id"] for r in rows(c, "SELECT id FROM buildings WHERE active=1")}


def rooms(c) -> list[dict]:
    return rows(c, "SELECT id, code, building_id, kind, capacity, schedulable, dedicated FROM rooms WHERE active=1 ORDER BY id")


def term_needs(c, term_id: int) -> dict[int, dict]:
    return {r["unit_id"]: r for r in rows(c, "SELECT n.* FROM courses co JOIN teaching_units u ON u.course_id=co.id "
                                             "JOIN tt_unit_needs n ON n.unit_id=u.id WHERE co.term_id=?", (term_id,))}


def needs_of(c, ids: list[int]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for part in _chunks(sorted(ids)):
        for r in rows(c, f"SELECT * FROM tt_unit_needs WHERE unit_id IN ({_in(part)})", tuple(part)):  # nosec B608
            out[r["unit_id"]] = r
    return out


def set_needs(c, uid: int, v: dict, by: int, at: str):
    cols = ("room_kinds", "room_ids", "need", "need_reason", "duration", "mode", "pattern", "split")
    vals = [json.dumps(v[k]) if k in ("room_kinds", "room_ids", "pattern") and v[k] is not None else v[k] for k in cols]
    c.execute(f"INSERT INTO tt_unit_needs(unit_id,{','.join(cols)},updated_by,updated_at) VALUES(?,{_in(cols)},?,?) "  # nosec B608
              f"ON CONFLICT(unit_id) DO UPDATE SET {', '.join(k + '=excluded.' + k for k in cols)}, updated_by=excluded.updated_by, "
              "updated_at=excluded.updated_at", (uid, *vals, by, at))


def term_availability(c, term_id: int, subject_type: str) -> list[dict]:
    return rows(c, "SELECT subject_type, subject_id, weekday, period, weeks, level FROM tt_availability WHERE subject_type=? AND term_id=? "
                   "ORDER BY subject_id, weekday, period", (subject_type, term_id))


def subject_availability(c, term_id: int, subject_type: str, sid: int) -> list[dict]:
    return rows(c, "SELECT weekday, period, weeks, level, note FROM tt_availability WHERE subject_type=? AND subject_id=? AND term_id=? "
                   "ORDER BY weekday, period", (subject_type, sid, term_id))


def subjects_availability(c, term_id: int, subject_type: str, ids: list[int]) -> list[dict]:
    out: list[dict] = []
    for part in _chunks(sorted(ids)):
        out += rows(c, f"SELECT subject_type, subject_id, weekday, period, weeks, level FROM tt_availability WHERE subject_type=? "  # nosec B608
                       f"AND subject_id IN ({_in(part)}) AND term_id=?", (subject_type, *part, term_id))
    return out


def replace_availability(c, term_id: int, subject_type: str, sid: int, cells: list[dict], by: int, at: str):
    c.execute("DELETE FROM tt_availability WHERE subject_type=? AND subject_id=? AND term_id=?", (subject_type, sid, term_id))
    c.executemany("INSERT INTO tt_availability(term_id,subject_type,subject_id,weekday,period,weeks,level,note,updated_by,updated_at) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?)",
                  [(term_id, subject_type, sid, x["weekday"], x["period"], x["weeks"], x["level"], x["note"], by, at) for x in cells])


def availability_status(c, term_id: int) -> dict[int, dict]:
    return {r["teacher_id"]: r for r in rows(c, "SELECT * FROM tt_availability_status WHERE term_id=?", (term_id,))}


def availability_status_of(c, term_id: int, tid: int):
    return row(c, "SELECT * FROM tt_availability_status WHERE term_id=? AND teacher_id=?", (term_id, tid))


def set_availability_status(c, term_id: int, tid: int, **v):
    c.execute("INSERT OR IGNORE INTO tt_availability_status(term_id, teacher_id) VALUES(?,?)", (term_id, tid))
    c.execute(f"UPDATE tt_availability_status SET {', '.join(k + '=?' for k in v)} WHERE term_id=? AND teacher_id=?",  # nosec B608 (constant columns)
              (*v.values(), term_id, tid))


def heads_of(c, department_id: int | None, faculty_id: int | None) -> list[int]:
    """The active department heads whose scope covers a department: its own heads without a grant, and every grant of
    the department, of its faculty or without a scope."""
    if not department_id:
        return []
    return [r["id"] for r in rows(c, "SELECT u.id FROM role_grants g JOIN users u ON u.id=g.user_id WHERE g.role='dept_head' "
                                     "AND u.status='active' AND (g.scope_type IS NULL OR (g.scope_type='department' AND g.scope_id=?) "
                                     "OR (g.scope_type='faculty' AND g.scope_id=?)) UNION SELECT u.id FROM users u WHERE u.role='dept_head' "
                                     "AND u.status='active' AND u.department_id=? AND NOT EXISTS (SELECT 1 FROM role_grants g "
                                     "WHERE g.user_id=u.id AND g.role='dept_head') ORDER BY 1", (department_id, faculty_id, department_id))]


def term_blocks(c, term_id: int) -> list[dict]:
    return [b for st in ("group", "teacher", "room") for b in
            rows(c, "SELECT subject_type, subject_id, weeks, active FROM tt_blocks WHERE subject_type=? AND term_id=? AND active=1",
                 (st, term_id))]


def tt_term(c, term_id: int):
    return row(c, "SELECT * FROM tt_terms WHERE term_id=?", (term_id,))


def set_tt_term(c, term_id: int, v: dict, by: int, at: str):
    cols = ("needs_due", "groups_due", "availability_due", "review_due", "publish_target", "confirmed")
    c.execute(f"INSERT INTO tt_terms(term_id,{','.join(cols)},updated_by,updated_at) VALUES(?,{_in(cols)},?,?) "  # nosec B608
              f"ON CONFLICT(term_id) DO UPDATE SET {', '.join(k + '=excluded.' + k for k in cols)}, updated_by=excluded.updated_by, "
              "updated_at=excluded.updated_at", (term_id, *(json.dumps(v[k]) if k == "confirmed" else v[k] for k in cols), by, at))


# runs
RUN_COLS = ("id, term_id, kind, scope, base_version_id, version_id, effective_from, params, status, cancel, seed, iter_budget, "
            "time_budget_s, iterations, cpu_ms, stopped, progress, input_sha256, inputs_fp, error, fails, requested_by, requested_at, "
            "started_at, finished_at, heartbeat_at")


def insert_run(c, v: dict) -> int:
    cols = list(v)
    return c.execute(f"INSERT INTO tt_runs({','.join(cols)}) VALUES({_in(cols)})", tuple(v.values())).lastrowid  # nosec B608


def run(c, rid: int, blobs: bool = False):
    return row(c, f"SELECT {'*' if blobs else RUN_COLS} FROM tt_runs WHERE id=?", (rid,))  # nosec B608 (constant columns)


def next_run(c):
    """The oldest run that is queued or running, with its blobs."""
    r = row(c, "SELECT id FROM tt_runs WHERE status IN ('queued','running') ORDER BY id LIMIT 1")
    return run(c, r["id"], blobs=True) if r else None


def active_run(c, term_id: int):
    return row(c, f"SELECT {RUN_COLS} FROM tt_runs WHERE term_id=? AND status IN ('queued','running')", (term_id,))  # nosec B608


def update_run(c, rid: int, **v):
    c.execute(f"UPDATE tt_runs SET {', '.join(k + '=?' for k in v)} WHERE id=?", (*v.values(), rid))  # nosec B608 (constant columns)


def version_busy(c, term_id: int, vid: int) -> bool:
    """A check or publish run of the version is queued or running: its placements must not move (design C18)."""
    return row(c, "SELECT 1 FROM tt_runs WHERE term_id=? AND kind IN ('check','publish') AND status IN ('queued','running') "
                  "AND version_id=? LIMIT 1", (term_id, vid)) is not None


def publishing(c, term_id: int | None) -> bool:
    return bool(term_id) and row(c, "SELECT 1 FROM tt_runs WHERE term_id=? AND kind='publish' AND status IN ('queued','running') LIMIT 1",
                                 (term_id,)) is not None


# versions and placements
def insert_version(c, v: dict) -> int:
    cols = list(v)
    return c.execute(f"INSERT INTO tt_versions({','.join(cols)}) VALUES({_in(cols)})", tuple(v.values())).lastrowid  # nosec B608


def version(c, vid: int):
    return row(c, "SELECT * FROM tt_versions WHERE id=?", (vid,))


def versions(c, term_id: int) -> list[dict]:
    return rows(c, "SELECT id, term_id, run_id, parent_id, status, name, rev, checked_rev, violations, scope, effective_from, unplaced, "
                   "excluded, created_by, created_at, published_by, published_at FROM tt_versions WHERE term_id=? ORDER BY id DESC LIMIT 200",
                (term_id,))


def published_version(c, term_id: int):
    return row(c, "SELECT * FROM tt_versions WHERE term_id=? AND status='published' ORDER BY id DESC LIMIT 1", (term_id,))


def update_version(c, vid: int, **v):
    c.execute(f"UPDATE tt_versions SET {', '.join(k + '=?' for k in v)} WHERE id=?", (*v.values(), vid))  # nosec B608 (constant columns)


def bump_rev(c, vid: int, rev: int) -> bool:
    """The optimistic lock of an edit: +1 only when the version is still at ``rev`` and editable."""
    return c.execute("UPDATE tt_versions SET rev=rev+1 WHERE id=? AND rev=? AND status IN ('draft','review')", (vid, rev)).rowcount == 1


def supersede(c, term_id: int, keep: int):
    c.execute("UPDATE tt_versions SET status='superseded' WHERE term_id=? AND status='published' AND id<>?", (term_id, keep))


def insert_placements(c, vid: int, items: list[dict], origin: str, at: str):
    c.executemany("INSERT INTO tt_placements(version_id,meeting_key,unit_id,part,weekday,period,duration,weeks,room_id,locked,origin,changed_at) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                  [(vid, p["key"], p["unit_id"], p["part"], p["weekday"], p["period"], p["duration"], p["weeks"], p["room_id"],
                    int(bool(p.get("locked"))), origin, at) for p in items])


PLACE_COLS = "p.id, p.meeting_key, p.unit_id, p.part, p.weekday, p.period, p.duration, p.weeks, p.room_id, p.locked, p.origin"


def placements(c, vid: int) -> list[dict]:
    return rows(c, f"SELECT {PLACE_COLS} FROM tt_placements p WHERE p.version_id=? ORDER BY p.meeting_key", (vid,))  # nosec B608


def placement(c, vid: int, pid: int):
    return row(c, f"SELECT {PLACE_COLS} FROM tt_placements p WHERE p.id=? AND p.version_id=?", (pid, vid))  # nosec B608


def placements_of_units(c, vid: int, unit_ids: list[int]) -> list[dict]:
    out: list[dict] = []
    for part in _chunks(sorted(unit_ids)):
        out += rows(c, f"SELECT {PLACE_COLS} FROM tt_placements p WHERE p.version_id=? AND p.unit_id IN ({_in(part)})",  # nosec B608
                    (vid, *part))
    return out


def placements_in_rooms(c, vid: int, room_ids: list[int]) -> list[dict]:
    out: list[dict] = []
    for part in _chunks(sorted(room_ids)):
        out += rows(c, f"SELECT {PLACE_COLS} FROM tt_placements p WHERE p.version_id=? AND p.room_id IN ({_in(part)})",  # nosec B608
                    (vid, *part))
    return out


GRID_JOIN = ("JOIN courses co ON co.id=u.course_id LEFT JOIN users tu ON tu.id=u.teacher_id LEFT JOIN rooms r ON r.id=p.room_id")
GRID_COLS = f"{PLACE_COLS}, u.kind, u.subgroup, u.teacher_id, tu.full_name teacher, co.name course, co.code course_code, r.code room"


def grid(c, vid: int, group_id: int | None, teacher_id: int | None, room_id: int | None) -> list[dict]:
    """A version's placements of one group (its units), one teacher or one room. CROSS JOIN keeps the selective side
    first: the group's or teacher's units, never the whole version."""
    order = "ORDER BY p.weekday, p.period, p.id"
    if group_id:
        return rows(c, f"SELECT {GRID_COLS} FROM teaching_unit_groups g CROSS JOIN tt_placements p ON p.version_id=? AND p.unit_id=g.unit_id "  # nosec B608
                       f"JOIN teaching_units u ON u.id=p.unit_id {GRID_JOIN} WHERE g.group_id=? {order}", (vid, group_id))
    if teacher_id:
        return rows(c, f"SELECT {GRID_COLS} FROM teaching_units u CROSS JOIN tt_placements p ON p.version_id=? AND p.unit_id=u.id "  # nosec B608
                       f"{GRID_JOIN} WHERE u.teacher_id=? {order}", (vid, teacher_id))
    return rows(c, f"SELECT {GRID_COLS} FROM tt_placements p JOIN teaching_units u ON u.id=p.unit_id {GRID_JOIN} "  # nosec B608
                   f"WHERE p.version_id=? AND p.room_id=? {order}", (vid, room_id))


def move_placement(c, pid: int, to: dict, by: int, at: str):
    c.execute("UPDATE tt_placements SET weekday=?, period=?, weeks=?, room_id=?, origin='manual', changed_by=?, changed_at=? WHERE id=?",
              (to["weekday"], to["period"], to["weeks"], to["room_id"], by, at, pid))


def set_locked(c, vid: int, ids: list[int], locked: bool, by: int, at: str) -> int:
    n = 0
    for part in _chunks(sorted(ids)):
        n += c.execute(f"UPDATE tt_placements SET locked=?, changed_by=?, changed_at=? WHERE version_id=? AND id IN ({_in(part)})",  # nosec B608
                       (int(locked), by, at, vid, *part)).rowcount
    return n


def insert_unplaced(c, vid: int, items: list[dict]):
    c.executemany("INSERT INTO tt_unplaced(version_id,meeting_key,unit_id,reasons) VALUES(?,?,?,?)",
                  [(vid, x["key"], x["unit_id"], json.dumps(x["reasons"], ensure_ascii=False)) for x in items])


def unplaced(c, vid: int) -> list[dict]:
    return rows(c, "SELECT meeting_key, unit_id, reasons FROM tt_unplaced WHERE version_id=? ORDER BY meeting_key", (vid,))


def link_rows(c, vid: int):
    """Each placement of a published version names the timetable row it became."""
    c.execute("UPDATE tt_placements SET timetable_id=(SELECT t.id FROM timetable t WHERE t.meeting_key=tt_placements.meeting_key "
              "AND t.active=1) WHERE version_id=?", (vid,))


# rows the builder may not move, rows it publishes, and their lessons
def unit_rows(c, unit_ids: list[int]) -> list[dict]:
    """The active timetable rows of units (an obstacle when the unit has no placement in the version)."""
    out: list[dict] = []
    for part in _chunks(sorted(unit_ids)):
        out += rows(c, f"SELECT {ROW_COLS} FROM {ROW_FROM} WHERE t.unit_id IN ({_in(part)}) AND t.active=1", tuple(part))  # nosec B608
    return out


def room_rows(c, term_id: int, room_ids: list[int]) -> list[dict]:
    out: list[dict] = []
    for part in _chunks(sorted(room_ids)):
        out += rows(c, f"SELECT {ROW_COLS} FROM {ROW_FROM} WHERE t.room_id IN ({_in(part)}) AND t.active=1 AND co.term_id=?",  # nosec B608
                    (*part, term_id))
    return out


def insert_published(c, v: dict, course_id: int, kind: str, room: str | None, vid: int, stamp: str) -> int:
    return c.execute("INSERT INTO timetable(course_id,weekday,start,end,kind,room,room_id,unit_id,academic_hours,weeks,active,updated_at,"
                     "meeting_key,period,version_id) VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)",
                     (course_id, v["weekday"], v["start"], v["end"], kind, room, v["room_id"], v["unit_id"], v["academic_hours"], v["weeks"],
                      stamp, v["meeting_key"], v["period"], vid)).lastrowid


def update_published(c, rid: int, v: dict, room: str | None, vid: int, stamp: str):
    c.execute("UPDATE timetable SET weekday=?, start=?, end=?, room=?, room_id=?, academic_hours=?, weeks=?, period=?, version_id=?, "
              "updated_at=? WHERE id=?", (v["weekday"], v["start"], v["end"], room, v["room_id"], v["academic_hours"], v["weeks"],
                                          v["period"], vid, stamp, rid))


def drop_lessons_from(c, rid: int, day: str) -> int:
    """A row's lessons from ``day`` on that nobody recorded and nobody moved by hand: they have not happened and are made
    again from the new row (a moved lesson keeps its own day and time, as Task 19 keeps it)."""
    return c.execute("DELETE FROM lessons WHERE timetable_id=? AND day>=? AND status='scheduled' AND day=slot_day AND start=slot_start "
                     "AND NOT EXISTS (SELECT 1 FROM attendance a WHERE a.lesson_id=lessons.id)", (rid, day)).rowcount


def students_of_groups(c, group_ids: list[int]) -> list[int]:
    out: set[int] = set()
    for part in _chunks(sorted(group_ids)):
        out.update(r["id"] for r in rows(c, f"SELECT id FROM users WHERE group_id IN ({_in(part)}) AND role='student' AND status='active'",  # nosec B608
                                          tuple(part)))
    return sorted(out)


def effective_of(c, version_ids: list[int]) -> dict[int, str]:
    out: dict[int, str] = {}
    for part in _chunks(sorted(version_ids)):
        for r in rows(c, f"SELECT id, effective_from FROM tt_versions WHERE id IN ({_in(part)})", tuple(part)):  # nosec B608
            if r["effective_from"]:
                out[r["id"]] = r["effective_from"]
    return out
