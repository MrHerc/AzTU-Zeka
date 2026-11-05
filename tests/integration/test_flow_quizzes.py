"""Quizzes: student attempts and limits; teacher Test Studio → approve → publish → results."""
from app import store


def correct_answers(qids):
    c = store.connect()
    try:
        out = {}
        for qid in qids:
            q = store.row(c, "SELECT answer FROM questions WHERE id=?", (qid,))
            out[str(qid)] = store.J(q["answer"])
        return out
    finally:
        c.close()


def test_student_quiz_list(student):
    qs = student.get("/api/quizzes").json
    assert len(qs) == 10 and all({"used", "best", "can_start", "questions"} <= set(q) for q in qs)
    done = [q for q in qs if q["used"]]
    assert len(done) == 3 and all(q["best"] is not None for q in done)


def test_start_hides_answers_and_submit_grades(student):
    qz = next(q for q in student.get("/api/quizzes").json if q["used"] == 0 and q["attempts"] >= 2)
    start = student.post(f"/api/quizzes/{qz['id']}/start").json
    assert start["deadline"] and start["quiz"]["id"] == qz["id"]
    assert all("answer" not in q and "explanation" not in q for q in start["questions"])
    answers = correct_answers([q["id"] for q in start["questions"]])
    res = student.post(f"/api/attempts/{start['attempt_id']}/submit", {"answers": answers}).json
    assert res["score"] == res["max_score"] == len(start["questions"]) and res["percent"] == 100
    assert all(d["correct"] and d["answer"] and d["explanation"] for d in res["details"])
    again = student.post(f"/api/attempts/{start['attempt_id']}/submit", {"answers": {}}).json
    assert again["score"] == res["score"]                       # a finished attempt is never re-graded
    assert student.get(f"/api/attempts/{start['attempt_id']}").json["percent"] == 100


def test_blank_answers_score_zero(student):
    qz = next(q for q in student.get("/api/quizzes").json if q["can_start"])
    start = student.post(f"/api/quizzes/{qz['id']}/start").json
    res = student.post(f"/api/attempts/{start['attempt_id']}/submit", {"answers": {}}).json
    assert res["score"] == 0 and all(d["given"] == "—" for d in res["details"])


def test_attempt_limit(student):
    qz = next(q for q in student.get("/api/quizzes").json if q["attempts"] == 1 and q["can_start"])
    a = student.post(f"/api/quizzes/{qz['id']}/start").json
    student.post(f"/api/attempts/{a['attempt_id']}/submit", {"answers": {}})
    assert student.post(f"/api/quizzes/{qz['id']}/start").status == 409


def test_attempts_are_private(student, app_db):
    assert student.get("/api/attempts/1").status == 404           # a synthetic student's attempt
    assert student.post("/api/quizzes/99999/start").status == 404


def test_studio_generate_approve_publish_and_results(teacher, student):
    gen = teacher.post("/api/studio/generate", {"course_id": 1, "count": 6, "types": ["mcq", "numeric", "tf"]}).json
    assert len(gen["questions"]) == 6 and all(q["status"] == "draft" and q["origin"] == "ai" and "source_ok" in q["flags"] for q in gen["questions"])
    assert all(q["source"] for q in gen["questions"])
    ids = [q["id"] for q in gen["questions"][:3]]
    assert teacher.post("/api/quizzes", {"course_id": 1, "question_ids": ids}).status == 400        # drafts cannot be published
    for qid in ids:
        assert teacher.put(f"/api/questions/{qid}", {"status": "approved", "topic": "Yoxlanılıb"}).json["status"] == "approved"
    qz = teacher.post("/api/quizzes", {"course_id": 1, "question_ids": ids + [ids[0]], "title": "Studiya testi", "kind": "graded",
                                       "time_limit": 500, "attempts": 0}).json
    assert qz["questions"] == 3 and qz["kind"] == "graded" and qz["time_limit"] == 180 and qz["attempts"] == 1
    assert any("Studiya testi" in n["title"] for n in student.get("/api/notifications").json["items"])
    mine = next(q for q in student.get("/api/quizzes").json if q["id"] == qz["id"])
    start = student.post(f"/api/quizzes/{mine['id']}/start").json
    student.post(f"/api/attempts/{start['attempt_id']}/submit", {"answers": correct_answers(ids)})
    res = teacher.get(f"/api/quizzes/{qz['id']}/results").json
    assert res["attempts"] == 1 and res["avg"] == 100 and sum(res["buckets"]) == 1 and res["buckets"][5] == 1
    assert all(q["correct_rate"] == 100 for q in res["questions"])
    listed = next(q for q in teacher.get("/api/teacher/quizzes").json if q["id"] == qz["id"])
    assert listed["attempts_count"] == 1 and listed["avg"] == 100


def test_question_bank_filters_update_and_delete(teacher):
    drafts = teacher.get("/api/questions?course_id=1&status=draft").json
    assert drafts and all(q["status"] == "draft" for q in drafts)
    q = drafts[0]
    if q["qtype"] == "mcq":
        bad = {"answer": len(q["options"])}
    elif q["qtype"] == "tf":
        bad = {"answer": "yes"}
    else:
        bad = {"answer": "many"}
    # regression: an answer that does not fit the question was stored and broke every later quiz submission
    assert teacher.put(f"/api/questions/{q['id']}", bad).status == 400
    if q["qtype"] == "mcq":
        assert teacher.put(f"/api/questions/{q['id']}", {"options": q["options"][:1]}).status == 400
    edited = teacher.put(f"/api/questions/{q['id']}", {"text": "Redaktə olunmuş sual"}).json
    assert edited["text"] == "Redaktə olunmuş sual"
    assert teacher.delete(f"/api/questions/{q['id']}").json == {"ok": True}
    assert teacher.put(f"/api/questions/{q['id']}", {"text": "x"}).status == 404


def test_teachers_only_manage_their_own_courses(teacher):
    assert teacher.post("/api/studio/generate", {"course_id": 2}).status == 403
    assert teacher.get("/api/questions?course_id=2").status == 403
    assert teacher.post("/api/quizzes", {"course_id": 2, "question_ids": [1]}).status == 403
