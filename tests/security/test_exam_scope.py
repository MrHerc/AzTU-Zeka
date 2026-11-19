"""The exam-scoped session (tasks/todo.md, Task 27), built from the route table: a session scoped to an exam reaches
nothing but that exam's routes; an exam's routes answer nothing but a session scoped to that exam; entering an exam
ends the student's other sessions in one request; an ordinary sign-in during the attempt neither ends the exam session
nor reaches the exam, and both are exam events."""
import json
import re
from pathlib import Path

import pytest

from zeka.legacy import store

MATRIX = json.loads((Path(__file__).parent / "matrix.json").read_text(encoding="utf-8"))
EXAM_ROUTES = [k for k, v in MATRIX.items() if v.get("scope") == "exam"]


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def call(client, key: str, exam_id: int):
    method, path = key.split(" ", 1)
    path = path.replace("{id:int}", str(exam_id)) if "/exams/" in path else path
    path = re.sub(r"\{\w+(:int)?\}", "1", path)
    return getattr(client, {"GET": "get", "POST": "post", "PUT": "put", "DELETE": "delete"}[method])(path, *([{}] if method in ("POST", "PUT") else []))


@pytest.fixture(scope="module")
def exams(app_db):
    """Two open exams of a course the demo student takes, each with exam questions."""
    teacher, student = app_db.client("teacher"), app_db.client("student")
    cid = q("SELECT c.id FROM courses c JOIN enrollments e ON e.course_id=c.id WHERE c.teacher_id=? AND e.user_id=? ORDER BY c.id LIMIT 1",
            (teacher.user["id"], student.user["id"]))[0]["id"]
    c = store.connect()
    try:
        for i in range(4):
            c.execute("INSERT INTO questions(course_id,qtype,text,options,answer,unit,explanation,difficulty,topic,status,purpose,created_at) "
                      "VALUES(?,'numeric',?,'[]','1','','x','Asan','Əhatə','approved','exam','x')", (cid, f"Əhatə sualı {i}"))
        c.commit()
    finally:
        c.close()
    ids = []
    for title in ("Əhatə A", "Əhatə B"):
        r = teacher.post(f"/api/courses/{cid}/exams", {"title": title, "day": store.now().date().isoformat(), "start": "00:01", "end": "23:59",
                                                       "duration_min": 60, "plan": [{"topic": "Əhatə", "count": 2}]})
        assert r.status == 200, r.text
        assert teacher.post(f"/api/exams/{r.json['id']}/open").status == 200
        ids.append(r.json["id"])
    return ids


def test_the_route_table_marks_the_exam_routes():
    assert len(EXAM_ROUTES) >= 5 and all("/api/exams/{id:int}" in k for k in EXAM_ROUTES)


def test_an_exam_session_reaches_no_route_outside_its_exam(app_db, exams):
    s = app_db.client("student")
    assert s.post(f"/api/exams/{exams[0]}/enter").status == 200
    others = [k for k, v in MATRIX.items() if v.get("scope") != "exam" and not k.startswith(("GET /static", "GET /healthz"))]
    keyed = {k for k, v in MATRIX.items() if str(v.get("scope") or "").startswith("token:")}   # API key routes read no cookie: 401
    leaks = [k for k in others if call(s, k, exams[0]).status != (401 if k in keyed else 403)]
    assert leaks == []
    assert s.get(f"/api/exams/{exams[0]}").status == 200, "and its own exam answers"


def test_an_ordinary_session_reaches_no_exam_route(app_db, exams):
    s = app_db.client("student")
    assert [k for k in EXAM_ROUTES if call(s, k, exams[0]).status != 403] == []


def test_one_exam_s_session_does_not_reach_another_exam(app_db, exams):
    s = app_db.client("student")
    assert s.post(f"/api/exams/{exams[0]}/enter").status == 200
    assert [k for k in EXAM_ROUTES if call(s, k, exams[1]).status != 403] == []


def test_entering_ends_the_other_sessions_and_a_sign_in_during_the_attempt_ends_nothing(app_db, exams):
    phone, laptop = app_db.client("student"), app_db.client("student")
    assert phone.get("/api/me").status == 200 and laptop.get("/api/me").status == 200
    assert laptop.post(f"/api/exams/{exams[1]}/enter").status == 200
    assert phone.get("/api/me").status == 401, "the other session ended in the same request"
    assert laptop.post(f"/api/exams/{exams[1]}/start").status == 200
    later = app_db.client("student")                                    # an ordinary sign-in while the attempt runs
    assert later.get(f"/api/exams/{exams[1]}").status == 403
    assert laptop.get(f"/api/exams/{exams[1]}").status == 200, "the exam session goes on"
    kinds = [e["kind"] for e in q("SELECT kind FROM exam_events WHERE exam_id=? ORDER BY seq", (exams[1],))]
    assert "session.entered" in kinds and "login.during_exam" in kinds
    again = app_db.client("student")
    assert again.post(f"/api/exams/{exams[1]}/enter").status == 200, "a new entry takes the attempt over"
    assert laptop.get(f"/api/exams/{exams[1]}").status == 401
    assert "session.takeover" in [e["kind"] for e in q("SELECT kind FROM exam_events WHERE exam_id=?", (exams[1],))]
