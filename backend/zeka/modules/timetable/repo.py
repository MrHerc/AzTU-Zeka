"""SQL of the timetable module (tasks/todo.md, Task 19)."""
from __future__ import annotations

from ...legacy.store import row, rows

ROW_COLS = ("t.id, t.course_id, t.weekday, t.start, t.end, t.kind, t.room, t.room_id, t.unit_id, t.academic_hours, t.weeks, "
            "t.active, co.name course, co.code course_code, co.term_id, u.kind unit_kind, u.subgroup, "
            "COALESCE(u.teacher_id, co.teacher_id) teacher_id, tu.full_name teacher")
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
