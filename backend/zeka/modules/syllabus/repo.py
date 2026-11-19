"""SQL of the syllabus module (tasks/todo.md, Task 23)."""
from __future__ import annotations

from ...legacy.store import row, rows

META = "v.id, v.course_id, v.version, v.status, v.created_at, v.note, v.decided_at, u.full_name author"


def course(c, cid: int):
    return row(c, "SELECT * FROM courses WHERE id=?", (cid,))


def units(c, cid: int) -> list[dict]:
    return rows(c, "SELECT kind, hours, students FROM teaching_units WHERE course_id=? AND active=1", (cid,))


def versions(c, cid: int) -> list[dict]:
    return rows(c, f"SELECT {META} FROM syllabus_versions v LEFT JOIN users u ON u.id=v.author_id "  # nosec B608 (constant columns)
                   "WHERE v.course_id=? ORDER BY v.version DESC", (cid,))


def version(c, cid: int, vid: int):
    return row(c, "SELECT * FROM syllabus_versions WHERE course_id=? AND id=?", (cid, vid))


def latest(c, cid: int):
    return row(c, "SELECT * FROM syllabus_versions WHERE course_id=? ORDER BY version DESC LIMIT 1", (cid,))


def published(c, cid: int):
    return row(c, "SELECT * FROM syllabus_versions WHERE course_id=? AND status='published' ORDER BY version DESC LIMIT 1", (cid,))


def add_version(c, cid: int, data: str, author: int, at: str) -> int:
    """The next version number in the same statement: two saves at once cannot take one number."""
    return c.execute("INSERT INTO syllabus_versions(course_id,version,status,data,author_id,created_at) "
                     "SELECT ?, COALESCE(MAX(version), 0) + 1, 'draft', ?, ?, ? FROM syllabus_versions WHERE course_id=?",
                     (cid, data, author, at, cid)).lastrowid


def legacy(c, cid: int):
    """A syllabus saved before Task 23 (one row per course, the assistant's shape)."""
    return row(c, "SELECT data FROM syllabi WHERE course_id=?", (cid,))


# ---------------------------------------------------------------- approval and publication (Task 25)
def set_status(c, vid: int, status: str, note: str, by: int, at: str):
    c.execute("UPDATE syllabus_versions SET status=?, note=?, decided_by=?, decided_at=? WHERE id=?", (status, note or None, by, at, vid))


def add_step(c, vid: int, action: str, by: int, note: str, at: str):
    c.execute("INSERT INTO syllabus_steps(version_id,action,user_id,note,at) VALUES(?,?,?,?,?)", (vid, action, by, note or None, at))


def steps(c, vid: int) -> list[dict]:
    return rows(c, "SELECT s.action, s.note, s.at, u.full_name who FROM syllabus_steps s LEFT JOIN users u ON u.id=s.user_id "
                   "WHERE s.version_id=? ORDER BY s.id", (vid,))


def has_grades(c, cid: int) -> bool:
    return row(c, "SELECT 1 FROM grades WHERE course_id=? AND score IS NOT NULL LIMIT 1", (cid,)) is not None


def publish_course(c, cid: int, grading: str, limit: float, modes: str, locked: int):
    """What a published syllabus configures on its course (Task 25)."""
    c.execute("UPDATE courses SET grading=?, attendance_limit=?, tutor_modes=?, tutor_locked=? WHERE id=?", (grading, limit, modes, locked, cid))


def pending(c, status: str) -> list[dict]:
    return rows(c, "SELECT v.id, v.course_id, v.version, v.status, v.created_at, v.data, co.code, co.name, co.department_id, "
                   "u.full_name author FROM syllabus_versions v JOIN courses co ON co.id=v.course_id LEFT JOIN users u ON u.id=v.author_id "
                   "WHERE v.status=? ORDER BY v.created_at", (status,))


def enrolled(c, cid: int, uid: int) -> bool:
    return row(c, "SELECT 1 FROM enrollments WHERE course_id=? AND user_id=?", (cid, uid)) is not None


def students(c, cid: int) -> list[int]:
    return [r["user_id"] for r in rows(c, "SELECT user_id FROM enrollments WHERE course_id=?", (cid,))]
