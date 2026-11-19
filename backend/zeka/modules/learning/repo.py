"""SQL of assignments (tasks/todo.md, Task 22)."""
from __future__ import annotations

from ...legacy.store import row, rows


def course(c, course_id: int):
    return row(c, "SELECT * FROM courses WHERE id=?", (course_id,))


def enrolled(c, uid: int, course_id: int, day: str) -> bool:
    return row(c, "SELECT 1 FROM enrollments e JOIN users u ON u.id=e.user_id WHERE e.user_id=? AND e.course_id=? AND u.status='active' "
                  "AND (e.end_date IS NULL OR e.end_date>?)", (uid, course_id, day)) is not None


def teaches(c, uid: int, course_id: int) -> bool:
    return row(c, "SELECT 1 FROM courses WHERE id=? AND teacher_id=? UNION ALL SELECT 1 FROM teaching_units WHERE course_id=? "
                  "AND teacher_id=? AND active=1 LIMIT 1", (course_id, uid, course_id, uid)) is not None


def insert(c, course_id: int, v: dict, by: int, at: str) -> int:
    return c.execute("INSERT INTO assignments(course_id,title,body,due_at,max_score,component,late_rule,created_by,created_at,updated_at) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?)", (course_id, v["title"], v["body"], v["due_at"], v["max_score"], v["component"],
                                                     v["late_rule"], by, at, at)).lastrowid


def assignment(c, aid: int):
    return row(c, "SELECT a.*, co.name course FROM assignments a JOIN courses co ON co.id=a.course_id WHERE a.id=? AND a.active=1", (aid,))


def of_course(c, course_id: int) -> list[dict]:
    return rows(c, "SELECT a.*, (SELECT COUNT(*) FROM submissions s WHERE s.assignment_id=a.id) submitted, "
                   "(SELECT COUNT(*) FROM submissions s WHERE s.assignment_id=a.id AND s.score IS NOT NULL) graded "
                   "FROM assignments a WHERE a.course_id=? AND a.active=1 ORDER BY a.due_at, a.id", (course_id,))


def submission_of(c, aid: int, uid: int):
    return row(c, "SELECT * FROM submissions WHERE assignment_id=? AND student_id=?", (aid, uid))


def submission(c, sid: int):
    return row(c, "SELECT s.*, a.course_id, a.title, a.max_score, a.component, u.full_name student FROM submissions s "
                  "JOIN assignments a ON a.id=s.assignment_id JOIN users u ON u.id=s.student_id WHERE s.id=?", (sid,))


def submissions_of(c, aid: int) -> list[dict]:
    return rows(c, "SELECT s.*, u.full_name student, u.student_no, f.filename FROM submissions s JOIN users u ON u.id=s.student_id "
                   "LEFT JOIN files f ON f.id=s.file_id WHERE s.assignment_id=? ORDER BY u.full_name", (aid,))


def save_submission(c, aid: int, uid: int, text: str | None, file_id: int | None, at: str, late: bool) -> bool:
    """False when the submission was graded meanwhile: a graded one is not replaced."""
    return c.execute("INSERT INTO submissions(assignment_id,student_id,text,file_id,submitted_at,late) VALUES(?,?,?,?,?,?) "
              "ON CONFLICT(assignment_id,student_id) DO UPDATE SET text=excluded.text, file_id=excluded.file_id, "
              "submitted_at=excluded.submitted_at, late=excluded.late WHERE submissions.score IS NULL",
              (aid, uid, text, file_id, at, int(late))).rowcount > 0


def grade(c, sid: int, score: float, feedback: str | None, by: int, at: str):
    c.execute("UPDATE submissions SET score=?, feedback=?, graded_by=?, graded_at=? WHERE id=?", (score, feedback, by, at, sid))


def graded_scores(c, course_id: int, uid: int, component: str) -> list[float]:
    return [r["score"] for r in rows(c, "SELECT s.score FROM submissions s JOIN assignments a ON a.id=s.assignment_id WHERE a.course_id=? "
                                        "AND a.component=? AND a.active=1 AND s.student_id=? AND s.score IS NOT NULL", (course_id, component, uid))]


def file_owner(c, file_id: int):
    return row(c, "SELECT * FROM files WHERE id=?", (file_id,))


def file_course(c, file_id: int) -> int | None:
    """The course whose submission holds this file (a teacher of that course may read it)."""
    r = row(c, "SELECT a.course_id FROM submissions s JOIN assignments a ON a.id=s.assignment_id WHERE s.file_id=? LIMIT 1", (file_id,))
    return r["course_id"] if r else None
