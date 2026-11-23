"""Students' status orders (tasks/todo.md, Task 15, slice 2): an order needs its number, order date and effective date;
leave and expulsion take the student off lesson lists from the effective date, earlier attendance and grades stay, and
a student on leave still signs in and sees their own documents. Orders are only added, never changed."""
import base64
import sqlite3
from datetime import timedelta

import pytest

from zeka.legacy import store

TODAY = store.now().date()


def db():
    return store.connect()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def q(sql, args=()):
    c = db()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def day(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


@pytest.fixture(scope="module")
def registrar(app_db):
    """The dean's office user acting as the academic office (a granted role)."""
    admin = app_db.client("admin")
    office_id = app_db.client("office").user["id"]
    admin.post(f"/api/admin/users/{office_id}/roles", {"role": "academic_office"})
    r = app_db.client("office")
    assert r.post("/api/me/role", {"role": "academic_office"}).status == 200
    return r


@pytest.fixture(scope="module")
def aysel(app_db):
    sid = app_db.client("student").user["id"]
    course = q("SELECT course_id FROM enrollments WHERE user_id=? ORDER BY course_id LIMIT 1", (sid,))[0]["course_id"]
    return {"id": sid, "course": course}


def order(kind="academic_leave", **over):
    return {"kind": kind, "order_no": "123-T", "order_date": day(-3), "effective_date": day(2), "note": "", **over}


def on_list(client, course, d):
    return {s["id"] for s in client.get(f"/api/courses/{course}/roster?day={d}").json["students"]}


@pytest.mark.parametrize("missing", ["order_no", "order_date", "effective_date"])
def test_no_status_changes_without_the_order_s_number_and_dates(registrar, aysel, missing):
    before = q("SELECT COUNT(*) n FROM student_status_events")[0]["n"]
    r = registrar.post(f"/api/directory/students/{aysel['id']}/status", order(**{missing: ""}))
    assert r.status == 400
    assert registrar.post(f"/api/directory/students/{aysel['id']}/status", order(order_date="31.12.2026")).status == 400
    assert q("SELECT COUNT(*) n FROM student_status_events")[0]["n"] == before
    assert registrar.get(f"/api/directory/students/{aysel['id']}/status").json["status"] == "active"


def test_only_the_academic_office_enters_orders(app_db, aysel):
    for role in ("admin", "office", "teacher", "student"):
        assert app_db.client(role).post(f"/api/directory/students/{aysel['id']}/status", order()).status == 403, role


def test_academic_leave_takes_the_student_off_lesson_lists_from_the_effective_date(app_db, registrar, aysel):
    teacher_course = aysel["course"]
    marks_before = q("SELECT COUNT(*) n FROM attendance WHERE user_id=?", (aysel["id"],))[0]["n"]
    grades_before = q("SELECT COUNT(*) n FROM grades WHERE user_id=?", (aysel["id"],))[0]["n"]
    assert aysel["id"] in on_list(registrar, teacher_course, day(1))
    r = registrar.post(f"/api/directory/students/{aysel['id']}/status", order(effective_date=day(2)))
    assert r.status == 200 and r.json["events"][-1]["kind"] == "academic_leave" and r.json["status"] == "active"
    assert aysel["id"] in on_list(registrar, teacher_course, day(1)), "before the effective date: still on the list"
    assert aysel["id"] not in on_list(registrar, teacher_course, day(2))
    assert aysel["id"] not in on_list(registrar, teacher_course, day(40))
    assert q("SELECT COUNT(*) n FROM attendance WHERE user_id=?", (aysel["id"],))[0]["n"] == marks_before
    assert q("SELECT COUNT(*) n FROM grades WHERE user_id=?", (aysel["id"],))[0]["n"] == grades_before
    student = app_db.client("student")                    # the account stays active: sign-in and own documents work
    doc = q("SELECT id FROM documents WHERE holder_id=? ORDER BY id LIMIT 1", (aysel["id"],))[0]["id"]
    assert student.get("/api/requests").status == 200 and student.get(f"/doc/{doc}").status == 200
    assert student.get("/api/grades").status == 200


def test_the_status_follows_the_effective_date(registrar, aysel):
    r = registrar.post(f"/api/directory/students/{aysel['id']}/status",
                       order("reinstatement", order_no="124-T", effective_date=day(-1), note="leave order entered in error"))
    assert r.status == 200 and r.json["status"] == "active"
    r = registrar.post(f"/api/directory/students/{aysel['id']}/status", order(order_no="125-T", effective_date=day(0)))
    assert r.json["status"] == "on_leave"
    assert "125-T" in [e["order_no"] for e in r.json["events"]], "the leave of 123-T starts later: today it is 125-T's"


def test_orders_are_never_changed_or_deleted(aysel):
    c = db()
    try:
        eid = store.row(c, "SELECT id FROM student_status_events WHERE student_id=? LIMIT 1", (aysel["id"],))["id"]
        with pytest.raises(sqlite3.DatabaseError):
            c.execute("UPDATE student_status_events SET order_no='x' WHERE id=?", (eid,))
        with pytest.raises(sqlite3.DatabaseError):
            c.execute("DELETE FROM student_status_events WHERE id=?", (eid,))
        c.execute("UPDATE student_status_events SET reported_at='2026-01-01' WHERE id=?", (eid,))   # the one column that may change
        c.rollback()
    finally:
        c.close()


def test_expulsion_also_ends_the_lesson_lists(app_db, registrar):
    other = q("SELECT e.user_id, e.course_id FROM enrollments e JOIN users u ON u.id=e.user_id WHERE u.role='student' "
              "AND u.username<>'aysel' AND e.end_date IS NULL ORDER BY e.user_id LIMIT 1")[0]
    assert other["user_id"] in on_list(registrar, other["course_id"], day(0))
    assert registrar.post(f"/api/directory/students/{other['user_id']}/status",
                          order("expulsion", order_no="200-X", effective_date=day(0))).status == 200
    assert other["user_id"] not in on_list(registrar, other["course_id"], day(0))
    assert registrar.get(f"/api/directory/students/{other['user_id']}/status").json["status"] == "expelled"


def test_a_group_change_moves_the_student_and_records_where_from(app_db, registrar):
    admin = app_db.client("admin")
    fid = admin.get("/api/directory/faculties").json["items"][0]["id"]
    gid = admin.post("/api/directory/groups", {"name": "S-26-9", "year": 2026, "faculty_id": fid}).json["id"]
    st = q("SELECT id, group_id FROM users WHERE role='student' AND username<>'aysel' ORDER BY id DESC LIMIT 1")[0]
    assert registrar.post(f"/api/directory/students/{st['id']}/status", order("group_change", order_no="7-Q")).status == 400, \
        "the new group is required"
    r = registrar.post(f"/api/directory/students/{st['id']}/status", order("group_change", order_no="7-Q", to_group_id=gid))
    assert r.status == 200 and r.json["events"][-1]["from_group_id"] == st["group_id"]
    assert q("SELECT group_id FROM users WHERE id=?", (st["id"],))[0]["group_id"] == gid


def test_a_back_dated_order_is_history_and_changes_nothing(app_db, registrar):
    """TE-F4: only the newest order (by effective date) acts; an expulsion dated before a transfer ends no enrolment."""
    admin = app_db.client("admin")
    fid = admin.get("/api/directory/faculties").json["items"][0]["id"]
    gid = admin.post("/api/directory/groups", {"name": "S-26-8", "year": 2026, "faculty_id": fid}).json["id"]
    st = q("SELECT u.id FROM users u WHERE u.role='student' AND u.username<>'aysel' AND EXISTS(SELECT 1 FROM enrollments e "
           "WHERE e.user_id=u.id AND e.end_date IS NULL) AND NOT EXISTS(SELECT 1 FROM student_status_events s WHERE s.student_id=u.id) "
           "ORDER BY u.id DESC LIMIT 1 OFFSET 2")[0]["id"]
    opened = q("SELECT COUNT(*) n FROM enrollments WHERE user_id=? AND end_date IS NULL", (st,))[0]["n"]
    r = registrar.post(f"/api/directory/students/{st}/status", order("group_change", order_no="8-Q", effective_date=day(5), to_group_id=gid))
    assert r.status == 200 and q("SELECT group_id FROM users WHERE id=?", (st,))[0]["group_id"] == gid
    r = registrar.post(f"/api/directory/students/{st}/status", order("expulsion", order_no="9-X", effective_date=day(1)))
    assert r.status == 200 and [e["order_no"] for e in r.json["events"]][-1] == "8-Q"
    assert q("SELECT COUNT(*) n FROM enrollments WHERE user_id=? AND end_date IS NULL", (st,))[0]["n"] == opened
    assert q("SELECT group_id FROM users WHERE id=?", (st,))[0]["group_id"] == gid


def test_a_dean_s_office_reads_only_its_faculty_and_the_read_is_audited(app_db, aysel):
    office = app_db.client("office")
    office.post("/api/me/role", {"role": "office"})
    assert office.get(f"/api/directory/students/{aysel['id']}/status").status == 200
    assert any(f"#{aysel['id']}" in r["detail"] for r in q("SELECT detail FROM audit WHERE action='read_student_status'"))
    admin = app_db.client("admin")
    fb = admin.post("/api/directory/faculties", {"code": "FST", "name": "Başqa fakültə"}).json["id"]
    gb = admin.post("/api/directory/groups", {"name": "FST-1", "year": 2025, "faculty_id": fb}).json["id"]
    st = q("SELECT id FROM users WHERE role='student' AND username<>'aysel' ORDER BY id LIMIT 1")[0]["id"]
    c = db()
    c.execute("UPDATE users SET group_id=? WHERE id=?", (gb, st))
    c.commit()
    c.close()
    assert office.get(f"/api/directory/students/{st}/status").status == 404
    assert app_db.client("teacher").get(f"/api/directory/students/{st}/status").status == 403


def test_issuing_an_academic_leave_needs_the_order_and_prints_it(app_db, registrar, pdf_bytes):
    student = app_db.client("student")
    data = {"reason": "Səhhət", "period": "1 semestr", "start": "2026/2027 payız semestri", "details": "Müalicə."}
    f = student.post("/api/files", {"filename": "arayis.pdf", "content_b64": b64(pdf_bytes)}).json
    r = student.post("/api/requests", {"type_code": "academic_leave", "data": data, "files": [f["id"]]})
    assert r.status == 200, r.text
    rid = r.json["id"]
    office = app_db.client("office")
    office.post("/api/me/role", {"role": "office"})
    assert office.post(f"/api/requests/{rid}/action", {"action": "approve"}).status == 200       # the dean's office's step
    assert registrar.post(f"/api/requests/{rid}/action", {"action": "approve"}).status == 200    # then the academic office's (Task 46)
    assert registrar.post(f"/api/requests/{rid}/action", {"action": "issue"}).status == 400
    done = registrar.post(f"/api/requests/{rid}/action", {"action": "issue", "order_no": "301-AM", "order_date": day(-1),
                                                          "effective_date": day(10)})
    assert done.status == 200, done.text
    ev = q("SELECT * FROM student_status_events WHERE order_no='301-AM'")
    assert len(ev) == 1 and ev[0]["kind"] == "academic_leave" and ev[0]["effective_date"] == day(10)
    doc_id = q("SELECT document_id FROM requests WHERE id=?", (rid,))[0]["document_id"]
    page = office.get(f"/doc/{doc_id}").text
    assert "301-AM" in page and (TODAY - timedelta(days=1)).strftime("%d.%m.%Y") in page
