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
