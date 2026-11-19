"""An exam question never leaves its attempt (tasks/todo.md, Task 26): with exam questions that carry a marker in their
text, options and explanation, an enrolled student calls every GET route a student may call, practises with the tutor
until the pool runs out and opens a Radar plan; no answer holds the marker. An exam question is refused in a practice
test, and an approved question keeps its purpose."""
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
    assert teacher.put(f"/api/questions/{leak['ids'][0]}", {"purpose": "practice"}).status == 400
    draft = q("SELECT id FROM questions WHERE course_id=? AND status='draft' ORDER BY id LIMIT 1", (COURSE,))
    if draft:
        assert teacher.put(f"/api/questions/{draft[0]['id']}", {"purpose": "elsewhere"}).status == 400
