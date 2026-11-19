"""SQL of the exam module (tasks/todo.md, Task 26)."""
from __future__ import annotations

import json

from ...legacy.store import row, rows

EXAM_PUBLIC = "id, course_id, kind, title, opens_at, closes_at, duration_min, protection, status, attempt_no"


def course(c, cid: int):
    return row(c, "SELECT * FROM courses WHERE id=?", (cid,))


def pool(c, cid: int) -> list[dict]:
    """The course's approved exam questions (Task 26: purpose='exam')."""
    return rows(c, "SELECT id, qtype, text, options, answer, unit, difficulty, topic FROM questions WHERE course_id=? "
                   "AND status='approved' AND purpose='exam' ORDER BY id", (cid,))


def questions(c, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    return {q["id"]: q for q in rows(c, f"SELECT id, qtype, text, options, answer, unit FROM questions WHERE id IN ({','.join('?' * len(ids))})",  # nosec B608
                                     tuple(ids))}


def add_exam(c, cid: int, v: dict, secret: str, by: int, at: str) -> int:
    return c.execute("INSERT INTO exams(course_id,kind,title,opens_at,closes_at,duration_min,plan,protection,allowed_cidrs,attempt_no,secret,"
                     "created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (cid, v["kind"], v["title"], v["opens_at"], v["closes_at"], v["duration_min"], json.dumps(v["plan"], ensure_ascii=False),
                      v["protection"], json.dumps(v["allowed_cidrs"]), 2 if v["kind"] == "retake" else 1, secret, by, at)).lastrowid


def exam(c, eid: int):
    return row(c, "SELECT * FROM exams WHERE id=?", (eid,))


def exams_of(c, cid: int, statuses: tuple[str, ...] | None = None) -> list[dict]:
    extra = f" AND status IN ({','.join('?' * len(statuses))})" if statuses else ""
    return rows(c, f"SELECT {EXAM_PUBLIC} FROM exams WHERE course_id=?{extra} ORDER BY opens_at DESC", (cid, *(statuses or ())))  # nosec B608


def set_exam(c, eid: int, **values):
    c.execute(f"UPDATE exams SET {', '.join(k + '=?' for k in values)} WHERE id=?", (*values.values(), eid))  # nosec B608 (keyword names)


def enrolled(c, cid: int) -> list[int]:
    return [r["user_id"] for r in rows(c, "SELECT user_id FROM enrollments WHERE course_id=?", (cid,))]


def roster(c, eid: int) -> list[dict]:
    return rows(c, "SELECT r.*, u.full_name, u.student_no FROM exam_roster r JOIN users u ON u.id=r.student_id WHERE r.exam_id=? "
                   "ORDER BY u.full_name", (eid,))


def roster_of(c, eid: int, sid: int):
    return row(c, "SELECT * FROM exam_roster WHERE exam_id=? AND student_id=?", (eid, sid))


def put_roster(c, eid: int, sid: int, status: str, reason: str | None, by: int | None, at: str):
    c.execute("INSERT INTO exam_roster(exam_id,student_id,status,reason,added_by,added_at) VALUES(?,?,?,?,?,?) "
              "ON CONFLICT(exam_id,student_id) DO UPDATE SET status=excluded.status, reason=excluded.reason, added_by=excluded.added_by, "
              "added_at=excluded.added_at", (eid, sid, status, reason, by, at))


def form(c, eid: int, sid: int):
    return row(c, "SELECT * FROM exam_forms WHERE exam_id=? AND student_id=?", (eid, sid))


def add_form(c, eid: int, sid: int, seed: str, items: list[dict], at: str):
    c.execute("INSERT OR IGNORE INTO exam_forms(exam_id,student_id,seed,items,created_at) VALUES(?,?,?,?,?)",
              (eid, sid, seed, json.dumps(items), at))


def attempt(c, eid: int, sid: int):
    return row(c, "SELECT * FROM exam_attempts WHERE exam_id=? AND student_id=?", (eid, sid))


def add_attempt(c, eid: int, sid: int, started: str, deadline: str) -> bool:
    """False when the student already has an attempt: two starts at once give one attempt."""
    return c.execute("INSERT OR IGNORE INTO exam_attempts(exam_id,student_id,started_at,deadline_at) VALUES(?,?,?,?)",
                     (eid, sid, started, deadline)).rowcount == 1


def attempts(c, eid: int) -> list[dict]:
    return rows(c, "SELECT a.*, u.full_name FROM exam_attempts a JOIN users u ON u.id=a.student_id WHERE a.exam_id=? ORDER BY u.full_name", (eid,))


def overdue(c, now: str) -> list[dict]:
    return rows(c, "SELECT * FROM exam_attempts WHERE status='in_progress' AND deadline_at<=?", (now,))


def set_attempt(c, aid: int, **values):
    c.execute(f"UPDATE exam_attempts SET {', '.join(k + '=?' for k in values)} WHERE id=?", (*values.values(), aid))  # nosec B608 (keyword names)


def answers(c, aid: int) -> dict[int, str]:
    return {r["qid"]: r["value"] for r in rows(c, "SELECT qid, value FROM exam_answers WHERE attempt_id=?", (aid,))}


def put_answer(c, aid: int, qid: int, value: str, at: str):
    c.execute("INSERT INTO exam_answers(attempt_id,qid,value,saved_at) VALUES(?,?,?,?) ON CONFLICT(attempt_id,qid) DO UPDATE SET "
              "value=excluded.value, saved_at=excluded.saved_at", (aid, qid, value, at))


def add_event(c, eid: int, kind: str, actor: int | None, student: int | None, data: dict, at: str):
    """Append to the exam's log; the next seq is taken in the same statement (Task 30 adds the hash chain)."""
    c.execute("INSERT INTO exam_events(exam_id,seq,kind,actor_id,student_id,data,at) SELECT ?, COALESCE(MAX(seq), 0) + 1, ?, ?, ?, ?, ? "
              "FROM exam_events WHERE exam_id=?", (eid, kind, actor, student, json.dumps(data, ensure_ascii=False, sort_keys=True), at, eid))


def events(c, eid: int) -> list[dict]:
    return rows(c, "SELECT * FROM exam_events WHERE exam_id=? ORDER BY seq", (eid,))
