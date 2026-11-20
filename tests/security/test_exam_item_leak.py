"""An exam question never leaves its attempt (tasks/todo.md, Task 26): with exam questions that carry a marker in their
text, options and explanation, an enrolled student calls every GET route a student may call, practises with the tutor
until the pool runs out and opens a Radar plan; no answer holds the marker. An exam question is refused in a practice
test, and an approved question keeps its purpose. The student's own export (Task 40) holds no exam form or question,
and the score and the answers only after the release."""
import json
from pathlib import Path

import pytest

from zeka.legacy import store

MARK = "ZKLEAK7F3A"
MATRIX = json.loads((Path(__file__).parent / "matrix.json").read_text(encoding="utf-8"))
COURSE = 1


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


@pytest.fixture(scope="module")
def leak(app_db):
    c = store.connect()
    try:
        ids = []
        for i in range(8):
            qid = c.execute("INSERT INTO questions(course_id,qtype,text,options,answer,unit,explanation,difficulty,topic,status,purpose,created_at) "
                            "VALUES(?,?,?,?,?,'',?,'Asan','Om qanunu','approved','exam','x')",
                            (COURSE, "mcq", f"{MARK} sual {i}: Om qanunu nəyi göstərir?", json.dumps([f"{MARK} a", "b", "c", "d"]), "0",
                             f"{MARK} izah: Om qanunu")).lastrowid
            store.index_question(store.row(c, "SELECT * FROM questions WHERE id=?", (qid,)))
            store.log_index(c, "questions", [qid])
            ids.append(qid)
        c.commit()
    finally:
        c.close()
    teacher = app_db.client("teacher")
    r = teacher.post(f"/api/courses/{COURSE}/exams", {"title": "Sızma sınağı", "day": store.now().date().isoformat(), "start": "00:01",
                                                      "end": "23:59", "duration_min": 60, "plan": [{"topic": "Om qanunu", "count": 4}]})
    assert r.status == 200, r.text
    assert teacher.post(f"/api/exams/{r.json['id']}/open").status == 200
    return {"exam": r.json["id"], "ids": ids}


def student_gets():
    for key, v in MATRIX.items():
        method, path = key.split(" ", 1)
        if method == "GET" and ("student" in v["access"] or v["access"] in ("any", "public")) and not path.startswith(("/demo/", "/api/auth/sso")):
            yield path


def concrete(path: str, exam_id: int) -> str:
    out = path.replace("{cid:int}", str(COURSE))
    if "/exams/" in out:
        out = out.replace("{id:int}", str(exam_id))
    if "/courses/" in out or "/tutor/" in out:
        out = out.replace("{id:int}", str(COURSE))
    for p in ("{id:int}", "{qid:int}", "{sid:int}", "{vid:int}", "{gid:int}"):
        out = out.replace(p, "1")
    return out + (f"?q={MARK}" if out == "/api/search" else "")


def test_no_route_a_student_can_get_answers_with_an_exam_question(app_db, leak):
    student = app_db.client("student")
    seen = 0
    for path in student_gets():
        r = student.get(concrete(path, leak["exam"]))
        assert MARK not in r.text, path
        seen += 1
    assert seen > 40


def test_practice_with_the_tutor_never_asks_an_exam_question(app_db, leak):
    student = app_db.client("student")
    student.post(f"/api/tutor/{COURSE}/clear")
    for msg in ["Məşq edək", "Om qanunu"] + ["Davam"] * 40:
        r = student.post(f"/api/tutor/{COURSE}/ask", {"message": msg, "mode": "practice"})
        assert MARK not in r.text
    assert MARK not in student.get(f"/api/tutor/{COURSE}/history").text


def test_a_radar_plan_never_holds_an_exam_question(app_db, leak):
    teacher, student = app_db.client("teacher"), app_db.client("student")
    r = teacher.post(f"/api/radar/student/{student.user['id']}/plan", {"course_id": COURSE, "kind": "plan", "note": "Om qanununu təkrarlayaq."})
    assert r.status in (200, 400, 404, 409)
    assert MARK not in r.text
    for p in student.get("/api/student/plans").json["items"]:
        assert MARK not in student.get(f"/api/student/plans/{p['id']}").text


def test_an_exam_question_is_not_put_in_a_test_and_keeps_its_purpose(app_db, leak):
    teacher = app_db.client("teacher")
    r = teacher.post("/api/quizzes", {"course_id": COURSE, "title": "Məşq", "question_ids": leak["ids"][:2]})
    assert r.status == 400
    assert teacher.put(f"/api/questions/{leak['ids'][0]}", {"purpose": "practice"}).status in (400, 409)   # 409 while an exam is open
    draft = q("SELECT id FROM questions WHERE course_id=? AND status='draft' ORDER BY id LIMIT 1", (COURSE,))
    if draft:
        assert teacher.put(f"/api/questions/{draft[0]['id']}", {"purpose": "elsewhere"}).status == 400


def test_the_export_holds_no_exam_question_and_the_score_only_after_release(app_db, leak):
    """Task 40: the student's own export, taken from an ordinary session next to the attempt, never holds the form, a
    question's text, options or key; the score and the answers appear only once the teacher releases the results."""
    eid, teacher = leak["exam"], app_db.client("teacher")
    s = app_db.client("student")
    assert s.post(f"/api/exams/{eid}/enter").status == 200
    qs = s.post(f"/api/exams/{eid}/start").json["questions"]
    assert qs and MARK in qs[0]["text"]                       # inside the attempt the question is there
    for x in qs:
        assert s.put(f"/api/exams/{eid}/answers/{x['id']}", {"value": 0}).status == 200
    assert s.post(f"/api/exams/{eid}/submit").status == 200
    plain = app_db.client("student")                          # an ordinary sign-in does not end the exam session (Task 27)

    def export():
        r = plain.get("/api/me/export")
        assert r.status == 200 and MARK not in r.text
        tables = r.json["tables"]
        assert "exam_forms" not in tables and "questions" not in tables
        return tables, next(a for a in tables["exam_attempts"] if a["exam_id"] == eid)

    for step in ("submitted", "closed"):
        tables, attempt = export()
        assert attempt["score"] is None and attempt["max_score"] is None, step
        assert not [x for x in tables["exam_answers"] if x["attempt_id"] == attempt["id"]], step
        assert not [x for x in tables["exam_events"] if x["exam_id"] == eid], step
        if step == "submitted":
            assert teacher.post(f"/api/exams/{eid}/close").status == 200
    assert teacher.post(f"/api/exams/{eid}/release").status == 200
    tables, attempt = export()
    assert attempt["score"] is not None and attempt["max_score"] == len(qs)
    answers = [x for x in tables["exam_answers"] if x["attempt_id"] == attempt["id"]]
    assert {x["qid"] for x in answers} == {x["id"] for x in qs}
    assert all(set(x) == {"attempt_id", "qid", "value", "saved_at"} for x in answers)      # the student's own answers only
    assert [x for x in tables["exam_events"] if x["exam_id"] == eid]
