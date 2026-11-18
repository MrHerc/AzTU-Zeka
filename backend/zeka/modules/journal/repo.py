"""SQL of the journal (tasks/todo.md, Task 20)."""
from __future__ import annotations

from ...legacy.store import row, rows


def lesson(c, lid: int):
    return row(c, "SELECT l.*, co.name course, co.code course_code, co.teacher_id course_teacher, co.department_id, co.term_id, "
                  "co.attendance_limit, tu.full_name teacher FROM lessons l JOIN courses co ON co.id=l.course_id "
                  "LEFT JOIN users tu ON tu.id=l.teacher_id WHERE l.id=?", (lid,))


def course(c, cid: int):
    return row(c, "SELECT * FROM courses WHERE id=?", (cid,))


def enrolments(c, course_id: int, uid: int | None = None) -> list[dict]:
    """Every enrolment of the course's active students (ended ones too: their lessons before the end still count)."""
    extra, args = ("AND e.user_id=?", (course_id, uid)) if uid else ("", (course_id,))
    return rows(c, "SELECT u.id, u.full_name, u.student_no, COALESCE(e.group_id, u.group_id) group_id, g.name grp, e.subgroup, "
                   "e.begin_date, e.end_date FROM enrollments e JOIN users u ON u.id=e.user_id "
                   "LEFT JOIN study_groups g ON g.id=COALESCE(e.group_id, u.group_id) "
                   f"WHERE e.course_id=? AND u.status='active' AND u.role='student' {extra} ORDER BY u.full_name, u.id", args)  # nosec B608


def course_lessons(c, course_id: int, first: str, last: str) -> list[dict]:
    return rows(c, "SELECT id, day, start, end, unit_id, academic_hours, status FROM lessons WHERE course_id=? AND day BETWEEN ? AND ? "
                   "ORDER BY day, start", (course_id, first, last))


def records(c, course_id: int, uid: int | None = None) -> dict[tuple[int, int], dict]:
    extra, args = ("AND a.user_id=?", (course_id, uid)) if uid else ("", (course_id,))
    out = rows(c, "SELECT a.user_id, a.lesson_id, a.status, a.source FROM attendance a JOIN lessons l ON l.id=a.lesson_id "
                  f"WHERE l.course_id=? {extra}", args)  # nosec B608 (constant SQL)
    return {(r["user_id"], r["lesson_id"]): r for r in out}


def openings(c, course_id: int, term_id: int | None, uid: int | None = None) -> dict[int, dict]:
    extra, args = ("AND student_id=?", (course_id, term_id, uid)) if uid else ("", (course_id, term_id))
    return {r["student_id"]: r for r in rows(c, f"SELECT * FROM attendance_opening WHERE course_id=? AND term_id=? {extra}", args)}  # nosec B608


def opening(c, oid: int):
    return row(c, "SELECT o.*, co.department_id FROM attendance_opening o JOIN courses co ON co.id=o.course_id WHERE o.id=?", (oid,))


def update_opening(c, oid: int, values: dict, at: str):
    c.execute("UPDATE attendance_opening SET held_hours=?, unexcused_hours=?, excused_hours=?, updated_at=? WHERE id=?",
              (values["held_hours"], values["unexcused_hours"], values["excused_hours"], at, oid))


def marks(c, lid: int) -> dict[int, dict]:
    return {r["user_id"]: r for r in rows(c, "SELECT * FROM attendance WHERE lesson_id=?", (lid,))}


def write_marks(c, lid: int, values: list[tuple[int, str]], by: int, at: str):
    """Insert or change the marks; a corrected imported row keeps its source."""
    c.executemany("INSERT INTO attendance(lesson_id,user_id,status,source,marked_by,marked_at) VALUES(?,?,?,'zeka',?,?) "
                  "ON CONFLICT(lesson_id,user_id) DO UPDATE SET status=excluded.status, marked_by=excluded.marked_by, "
                  "marked_at=excluded.marked_at", [(lid, uid, st, by, at) for uid, st in values])


def dept_scopes(c, uid: int) -> set[int]:
    return {r["scope_id"] for r in rows(c, "SELECT scope_id FROM role_grants WHERE user_id=? AND role='dept_head' "
                                           "AND scope_type='department'", (uid,))}


def teaches(c, uid: int, course_id: int) -> bool:
    return row(c, "SELECT 1 FROM courses WHERE id=? AND teacher_id=? UNION ALL SELECT 1 FROM lessons WHERE course_id=? AND teacher_id=? "
                  "LIMIT 1", (course_id, uid, course_id, uid)) is not None


def teacher(c, uid: int):
    return row(c, "SELECT id, full_name, role FROM users WHERE id=? AND status='active' AND role IN ('teacher','dept_head')", (uid,))


def set_teacher(c, lid: int, tid: int, at: str):
    c.execute("UPDATE lessons SET teacher_id=?, updated_at=? WHERE id=?", (tid, at, lid))


def lessons_of_teacher(c, uid: int, first: str, last: str) -> list[dict]:
    return rows(c, "SELECT l.id, l.course_id, l.day, l.start, l.end, l.kind, l.room, l.status, co.name course, "
                   "(SELECT COUNT(*) FROM attendance a WHERE a.lesson_id=l.id) marked FROM lessons l JOIN courses co ON co.id=l.course_id "
                   "WHERE l.teacher_id=? AND l.day BETWEEN ? AND ? ORDER BY l.day DESC, l.start DESC", (uid, first, last))


def lessons_of_course(c, course_id: int, until: str) -> list[dict]:
    return rows(c, "SELECT l.id, l.course_id, l.day, l.start, l.end, l.kind, l.room, l.status, l.teacher_id, tu.full_name teacher, "
                   "(SELECT COUNT(*) FROM attendance a WHERE a.lesson_id=l.id) marked FROM lessons l LEFT JOIN users tu ON tu.id=l.teacher_id "
                   "WHERE l.course_id=? AND l.day<=? ORDER BY l.day DESC, l.start DESC", (course_id, until))
