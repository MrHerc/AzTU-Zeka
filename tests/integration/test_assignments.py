"""Assignments (tasks/todo.md, Task 22, slice 1): set by the course's teacher, submitted by its students, late
submissions by the rule, read only by the student and the teacher, graded into the journal's component."""
import base64
from datetime import timedelta

import pytest

from zeka.legacy import store


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def due(days: int) -> str:
    return (store.now() + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")


@pytest.fixture(scope="module")
def course(app_db):
    """The demo teacher's first course, which the demo student is enrolled in."""
    teacher, student = app_db.client("teacher"), app_db.client("student")
    return q("SELECT c.id FROM courses c JOIN enrollments e ON e.course_id=c.id WHERE c.teacher_id=? AND e.user_id=? ORDER BY c.id LIMIT 1",
             (teacher.user["id"], student.user["id"]))[0]["id"]


def make(teacher, course, **kw):
    body = {"title": "Om qanunu üzrə hesabat", "body": "Üç məsələni həll edin.", "due_at": due(3), "max_score": 3,
            "component": "Sərbəst iş 2", "late_rule": "mark", **kw}
    return teacher.post(f"/api/courses/{course}/assignments", body)


def test_bad_assignments_are_refused(app_db, course):
    teacher = app_db.client("teacher")
    for bad in ({"component": "Davamiyyət"}, {"component": "İmtahan"}, {"max_score": 6}, {"max_score": 0}, {"due_at": "sabah"},
                {"late_rule": "maybe"}, {"title": "x"}, {"body": ""}):
        assert make(teacher, course, **bad).status == 400, bad
    assert make(app_db.client("student"), course).status == 403
    other = q("SELECT id FROM courses WHERE teacher_id<>? ORDER BY id LIMIT 1", (teacher.user["id"],))[0]["id"]
    assert make(teacher, other).status == 404, "only the course's own teacher"


def test_a_submission_on_time_and_a_late_one_by_the_rule(app_db, course):
    teacher, student = app_db.client("teacher"), app_db.client("student")
    on_time = make(teacher, course).json
    late_mark = make(teacher, course, title="Gecikmə qeyd olunur", due_at=due(-1)).json
    late_refuse = make(teacher, course, title="Gecikmə qəbul olunmur", due_at=due(-1), late_rule="refuse").json
    assert student.post(f"/api/assignments/{on_time['id']}/submit", {}).status == 400, "a text or a file"
    r = student.post(f"/api/assignments/{on_time['id']}/submit", {"text": "R = U / I"})
    assert r.status == 200 and r.json["late"] == 0
    assert student.post(f"/api/assignments/{late_mark['id']}/submit", {"text": "gec"}).json["late"] == 1
    assert student.post(f"/api/assignments/{late_refuse['id']}/submit", {"text": "gec"}).status == 409
    mine = {a["id"]: a for a in student.get(f"/api/courses/{course}/assignments").json}
    assert mine[on_time["id"]]["submission"]["text"] == "R = U / I" and mine[late_refuse["id"]]["submission"] is None


def test_only_an_enrolled_student_submits(app_db, course):
    teacher, admin, student = app_db.client("teacher"), app_db.client("admin"), app_db.client("student")
    other = admin.post("/api/directory/courses", {"code": "AS-NO", "name": "Qeydiyyatsız fənn", "credits": 3,
                                                  "teacher_id": teacher.user["id"]}).json["id"]
    a = make(teacher, other).json
    assert student.post(f"/api/assignments/{a['id']}/submit", {"text": "x"}).status == 404
    assert student.get(f"/api/courses/{other}/assignments").status == 404


def test_only_the_student_and_the_teacher_read_a_submission(app_db, course):
    teacher, student = app_db.client("teacher"), app_db.client("student")
    a = make(teacher, course, title="Oxuma hüququ").json
    sid = student.post(f"/api/assignments/{a['id']}/submit", {"text": "cavab"}).json["id"]
    assert student.get(f"/api/submissions/{sid}").status == 200
    assert teacher.get(f"/api/submissions/{sid}").status == 200
    for role in ("office", "leader"):
        assert app_db.client(role).get(f"/api/submissions/{sid}").status in (403, 404), role
    assert app_db.client("office").get(f"/api/assignments/{a['id']}/submissions").status == 403


def test_a_graded_score_goes_to_the_journal_component(app_db, course):
    teacher, student = app_db.client("teacher"), app_db.client("student")
    a1 = make(teacher, course, title="Birinci", max_score=3).json
    a2 = make(teacher, course, title="İkinci", max_score=3).json
    s1 = student.post(f"/api/assignments/{a1['id']}/submit", {"text": "1"}).json["id"]
    s2 = student.post(f"/api/assignments/{a2['id']}/submit", {"text": "2"}).json["id"]
    assert teacher.post(f"/api/submissions/{s1}/grade", {"score": 4}).status == 400, "above the assignment's maximum"
    assert teacher.post(f"/api/submissions/{s1}/grade", {"score": 3, "feedback": "Əla"}).status == 200
    assert teacher.post(f"/api/submissions/{s2}/grade", {"score": 2.5}).status == 200
    cell = q("SELECT score, status FROM grades WHERE user_id=? AND course_id=? AND component='Sərbəst iş 2'", (student.user["id"], course))[0]
    assert cell == {"score": 5.0, "status": "draft"}, "3 + 2.5 capped at the component's 5, a draft until published"
    assert student.post(f"/api/assignments/{a1['id']}/submit", {"text": "yenisi"}).status == 400, "graded: no new submission"
    seen = {a["id"]: a for a in student.get(f"/api/courses/{course}/assignments").json}[a1["id"]]["submission"]
    assert seen["score"] == 3 and seen["feedback"] == "Əla"


def test_a_file_submission_is_read_by_the_course_s_teacher(app_db, course, pdf_bytes):
    teacher, student = app_db.client("teacher"), app_db.client("student")
    a = make(teacher, course, title="Fayl ilə").json
    fid = student.post("/api/files", {"filename": "hesabat.pdf", "content_b64": base64.b64encode(pdf_bytes).decode()}).json["id"]
    other = q("SELECT id FROM files WHERE owner_id<>? ORDER BY id LIMIT 1", (student.user["id"],))
    if other:
        assert student.post(f"/api/assignments/{a['id']}/submit", {"file_id": other[0]["id"]}).status == 400, "someone else's file"
    assert student.post(f"/api/assignments/{a['id']}/submit", {"file_id": fid}).status == 200
    got = teacher.get(f"/api/files/{fid}")
    assert got.status == 200 and got.body == pdf_bytes
