"""SQL of the course forum (tasks/todo.md, Task 33)."""
from __future__ import annotations

from ...legacy.store import row, rows

FAQ_FILE = "qa-faq.md"


def course(c, cid: int):
    return row(c, "SELECT * FROM courses WHERE id=?", (cid,))


def topics(c, cid: int) -> list[dict]:
    return rows(c, "SELECT tq.id, tq.course_id, tq.student_id, tq.anonymous, tq.title, tq.tag, tq.status, tq.hidden, tq.faq_chunk_id, "
                   "tq.created_at, u.full_name AS author, u.role AS author_role, "
                   "(SELECT COUNT(*) FROM qa_replies r WHERE r.topic_id=tq.id AND r.hidden=0) AS replies FROM teacher_questions tq "
                   "JOIN users u ON u.id=tq.student_id WHERE tq.course_id=? ORDER BY tq.id DESC LIMIT 500", (cid,))


def topic(c, tid: int):
    return row(c, "SELECT tq.*, u.full_name AS author, u.role AS author_role FROM teacher_questions tq JOIN users u ON u.id=tq.student_id "
                  "WHERE tq.id=?", (tid,))


def replies(c, tid: int) -> list[dict]:
    return rows(c, "SELECT r.id, r.topic_id, r.author_id, r.text, r.accepted, r.hidden, r.created_at, u.full_name AS author, u.role AS author_role "
                   "FROM qa_replies r JOIN users u ON u.id=r.author_id WHERE r.topic_id=? ORDER BY r.id", (tid,))


def reply(c, rid: int):
    return row(c, "SELECT * FROM qa_replies WHERE id=?", (rid,))


def add_topic(c, cid: int, uid: int, v: dict, at: str) -> int:
    return c.execute("INSERT INTO teacher_questions(course_id,student_id,anonymous,title,question,tag,context,status,created_at,updated_at) "
                     "VALUES(?,?,?,?,?,?,'',?,?,?)", (cid, uid, int(v["anonymous"]), v["title"], v["text"], v["tag"], "open", at, at)).lastrowid


def add_reply(c, tid: int, uid: int, text: str, at: str) -> int:
    rid = c.execute("INSERT INTO qa_replies(topic_id,author_id,text,created_at) VALUES(?,?,?,?)", (tid, uid, text, at)).lastrowid
    c.execute("UPDATE teacher_questions SET updated_at=? WHERE id=?", (at, tid))
    return rid


def accept(c, tid: int, rid: int, text: str, at: str):
    """The accepted reply (one per topic); the old single-answer columns follow it for the teacher's list."""
    c.execute("UPDATE qa_replies SET accepted=(id=?) WHERE topic_id=?", (rid, tid))
    c.execute("UPDATE teacher_questions SET status='answered', answer=?, answered_at=?, updated_at=? WHERE id=?", (text, at, at, tid))


def accepted(c, tid: int):
    return row(c, "SELECT * FROM qa_replies WHERE topic_id=? AND accepted=1 AND hidden=0", (tid,))


def set_draft(c, tid: int, text: str | None):
    c.execute("UPDATE teacher_questions SET ai_draft=? WHERE id=?", (text, tid))


def set_hidden(c, table: str, oid: int, hidden: bool):
    c.execute({"topic": "UPDATE teacher_questions SET hidden=? WHERE id=?", "reply": "UPDATE qa_replies SET hidden=? WHERE id=?"}[table],
              (int(hidden), oid))


def faq_material(c, cid: int, title: str, by: int, at: str) -> int:
    m = row(c, "SELECT id FROM materials WHERE course_id=? AND filename=?", (cid, FAQ_FILE))
    if m:
        return m["id"]
    return c.execute("INSERT INTO materials(course_id,title,filename,text,chunk_count,term_count,uploaded_by,created_at) VALUES(?,?,?,'',0,0,?,?)",
                     (cid, title, FAQ_FILE, by, at)).lastrowid


def add_faq_chunk(c, mid: int, cid: int, heading: str, text: str) -> int:
    seq = row(c, "SELECT COALESCE(MAX(seq), -1) + 1 AS n FROM chunks WHERE material_id=?", (mid,))["n"]
    return c.execute("INSERT INTO chunks(material_id,course_id,seq,heading,text) VALUES(?,?,?,?,?)", (mid, cid, seq, heading, text)).lastrowid


def drop_faq_chunk(c, chunk_id: int):
    c.execute("DELETE FROM chunks WHERE id=?", (chunk_id,))


def set_faq(c, tid: int, chunk_id: int | None):
    c.execute("UPDATE teacher_questions SET faq_chunk_id=? WHERE id=?", (chunk_id, tid))


def refresh_faq_material(c, mid: int):
    """The FAQ material's text and count are its current sections, so the course's material list reads true."""
    parts = rows(c, "SELECT heading, text FROM chunks WHERE material_id=? ORDER BY seq", (mid,))
    c.execute("UPDATE materials SET text=?, chunk_count=? WHERE id=?",
              ("\n\n".join(f"## {p['heading']}\n\n{p['text']}" for p in parts), len(parts), mid))


def add_report(c, tid: int, rid: int | None, uid: int, reason: str, at: str) -> int:
    return c.execute("INSERT INTO qa_reports(topic_id,reply_id,reporter_id,reason,created_at) VALUES(?,?,?,?,?)", (tid, rid, uid, reason, at)).lastrowid


def open_reports(c) -> list[dict]:
    """The open reports with what was reported and its real author (a moderator sees an anonymous one, Task 33)."""
    return rows(c, "SELECT p.id, p.topic_id, p.reply_id, p.reason, p.created_at, tq.title, tq.question, tq.course_id, co.name AS course, "
                   "ta.full_name AS topic_author, tq.anonymous, r.text AS reply_text, ra.full_name AS reply_author, u.full_name AS reporter "
                   "FROM qa_reports p JOIN teacher_questions tq ON tq.id=p.topic_id JOIN courses co ON co.id=tq.course_id "
                   "JOIN users ta ON ta.id=tq.student_id LEFT JOIN qa_replies r ON r.id=p.reply_id LEFT JOIN users ra ON ra.id=r.author_id "
                   "JOIN users u ON u.id=p.reporter_id WHERE p.resolved_at IS NULL ORDER BY p.id LIMIT 200")


def report(c, pid: int):
    return row(c, "SELECT * FROM qa_reports WHERE id=?", (pid,))


def resolve(c, pid: int, by: int, outcome: str, at: str):
    """Every open report on the same target is closed with it."""
    p = report(c, pid)
    c.execute("UPDATE qa_reports SET resolved_at=?, resolved_by=?, outcome=? WHERE topic_id=? AND COALESCE(reply_id,0)=? AND resolved_at IS NULL",
              (at, by, outcome, p["topic_id"], p["reply_id"] or 0))


# ---------------------------------------------------------------- office hours (Task 34)
def hours_of(c, teacher_id: int) -> list[dict]:
    return rows(c, "SELECT * FROM office_hours WHERE teacher_id=? AND active=1 ORDER BY weekday, start", (teacher_id,))


def hours(c, hid: int):
    return row(c, "SELECT * FROM office_hours WHERE id=?", (hid,))


def add_hours(c, teacher_id: int, v: dict, at: str) -> int:
    return c.execute("INSERT INTO office_hours(teacher_id,weekday,start,end,slot_min,place,online_url,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (teacher_id, v["weekday"], v["start"], v["end"], v["slot_min"], v["place"], v["online_url"], at)).lastrowid


def drop_hours(c, hid: int):
    c.execute("UPDATE office_hours SET active=0 WHERE id=?", (hid,))


def booked_slots(c, teacher_id: int, first: str, last: str) -> set[tuple[str, str]]:
    return {(r["day"], r["start"]) for r in rows(c, "SELECT day, start FROM office_bookings WHERE teacher_id=? AND status='booked' "
                                                    "AND day BETWEEN ? AND ?", (teacher_id, first, last))}


def add_booking(c, h: dict, student_id: int, day: str, start: str, end: str, topic: str | None, at: str) -> int:
    """Raises sqlite3.IntegrityError when the slot is already booked (idx_office_bookings_slot)."""
    return c.execute("INSERT INTO office_bookings(hours_id,teacher_id,student_id,day,start,end,topic,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (h["id"], h["teacher_id"], student_id, day, start, end, topic, at)).lastrowid


def lock(c):
    """The write lock before a check and its write (the cap of upcoming bookings, Checkpoint E, TM-E9)."""
    if not c.in_transaction:
        c.execute("BEGIN IMMEDIATE")


def open_bookings_with(c, student_id: int, teacher_id: int, today: str, hhmm: str) -> int:
    """Upcoming bookings only: one that ended earlier today no longer counts (CR-E4)."""
    return row(c, "SELECT COUNT(*) AS n FROM office_bookings WHERE student_id=? AND teacher_id=? AND status='booked' "
                  "AND (day>? OR (day=? AND end>?))", (student_id, teacher_id, today, today, hhmm))["n"]


def booking(c, bid: int):
    return row(c, "SELECT b.*, h.place, h.online_url FROM office_bookings b JOIN office_hours h ON h.id=b.hours_id WHERE b.id=?", (bid,))


def cancel_booking(c, bid: int, by: int, at: str):
    c.execute("UPDATE office_bookings SET status='cancelled', cancelled_at=?, cancelled_by=? WHERE id=?", (at, by, bid))


def future_bookings_of_hours(c, hid: int, today: str, hhmm: str) -> list[dict]:
    return rows(c, "SELECT * FROM office_bookings WHERE hours_id=? AND status='booked' AND (day>? OR (day=? AND end>?))",
                (hid, today, today, hhmm))


def bookings_for(c, uid: int, first: str, last: str) -> list[dict]:
    """A person's bookings as student or teacher, with the other party's name, from ``first`` to ``last``."""
    return rows(c, "SELECT b.id, b.day, b.start, b.end, b.topic, b.status, b.teacher_id, b.student_id, h.place, h.online_url, "
                   "t.full_name AS teacher, s.full_name AS student FROM office_bookings b JOIN office_hours h ON h.id=b.hours_id "
                   "JOIN users t ON t.id=b.teacher_id JOIN users s ON s.id=b.student_id "
                   "WHERE (b.student_id=? OR b.teacher_id=?) AND b.day BETWEEN ? AND ? ORDER BY b.day, b.start", (uid, uid, first, last))


def teachers_of_student(c, uid: int, today: str) -> list[dict]:
    """The teachers of the courses a student is enrolled in (the course's head and its units' teachers)."""
    return rows(c, "SELECT DISTINCT u.id, u.full_name FROM enrollments e JOIN courses co ON co.id=e.course_id "
                   "JOIN users u ON u.id=co.teacher_id WHERE e.user_id=? AND (e.end_date IS NULL OR e.end_date>?) AND u.status='active' "
                   "UNION SELECT DISTINCT u.id, u.full_name FROM enrollments e JOIN teaching_units tu ON tu.course_id=e.course_id AND tu.active=1 "
                   "JOIN users u ON u.id=tu.teacher_id WHERE e.user_id=? AND (e.end_date IS NULL OR e.end_date>?) AND u.status='active' "
                   "ORDER BY 2", (uid, today, uid, today))


def bookings_starting(c, day: str, first: str, last: str) -> list[dict]:
    return rows(c, "SELECT b.*, t.full_name AS teacher, s.full_name AS student FROM office_bookings b JOIN users t ON t.id=b.teacher_id "
                   "JOIN users s ON s.id=b.student_id WHERE b.status='booked' AND b.day=? AND b.start BETWEEN ? AND ?", (day, first, last))
