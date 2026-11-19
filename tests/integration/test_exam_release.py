"""Releasing an exam's results to the journal (tasks/todo.md, Task 30): the scaled score is published in the exam
component with its exam and attempt number and the release is audited; the similar-answers list is the teacher's
only; a retake's result does not erase the first one, and both are shown to the teacher and the dean's office."""
import pytest

from zeka.legacy import store


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def run(sql, args=()):
    c = store.connect()
    try:
        c.execute(sql, args)
        c.commit()
    finally:
        c.close()


@pytest.fixture(scope="module")
def world(app_db):
    admin, teacher = app_db.client("admin"), app_db.client("teacher")
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    gid = q("SELECT group_id FROM users WHERE id=?", (app_db.client("student").user["id"],))[0]["group_id"]
    cid = admin.post("/api/directory/courses", {"code": "RL-101", "name": "Açıqlama sınağı", "credits": 5, "term_id": term["id"],
                                                "teacher_id": teacher.user["id"]}).json["id"]
    ids = {}
    for n in ("rl.a", "rl.b", "rl.c"):
        ids[n] = admin.post("/api/directory/users", {"username": n, "full_name": f"Açıqlama {n}", "role": "student", "group_id": gid,
                                                     "student_no": n.upper()}).json["id"]
        admin.post(f"/api/directory/courses/{cid}/enrollments", {"user_id": ids[n]})
    for i in range(3):
        run("INSERT INTO questions(course_id,qtype,text,options,answer,unit,explanation,difficulty,topic,status,purpose,created_at) "
            "VALUES(?,'numeric',?,'[]',?,'','izah','Asan','Om','approved','exam','x')", (cid, f"açıqlama sualı {i}", str(10 + i)))
    return {"course": cid, "ids": ids, "teacher": teacher}


def exam(app_db, world, answers: dict, kind="main"):
    """An exam sat by the students in ``answers`` (name -> 'right' | 'wrong'), closed by the teacher."""
    t = world["teacher"]
    eid = t.post(f"/api/courses/{world['course']}/exams", {"title": f"Yekun ({kind})", "kind": kind, "day": store.now().date().isoformat(),
                                                           "start": "00:01", "end": "23:59", "duration_min": 60, "plan": [{"count": 3}]}).json["id"]
    assert t.post(f"/api/exams/{eid}/open").status == 200
    for name, how in answers.items():
        s = app_db.client()
        assert s.post("/api/auth/demo", {"role": "student", "user": name}).status == 200
        assert s.post(f"/api/exams/{eid}/enter").status == 200
        for x in s.post(f"/api/exams/{eid}/start").json["questions"]:
            right = q("SELECT answer FROM questions WHERE id=?", (x["id"],))[0]["answer"]
            assert s.put(f"/api/exams/{eid}/answers/{x['id']}", {"value": right if how == "right" else "99"}).status == 200
        assert s.post(f"/api/exams/{eid}/submit").status == 200
    assert t.post(f"/api/exams/{eid}/close").status == 200
    return eid


def cell(world, name):
    rows = q("SELECT * FROM grades WHERE user_id=? AND course_id=? AND exam_id IS NOT NULL", (world["ids"][name], world["course"]))
    return rows[0] if rows else None


def test_released_scores_reach_the_journal_and_the_release_is_audited(app_db, world):
    eid = exam(app_db, world, {"rl.a": "right", "rl.b": "wrong", "rl.c": "wrong"})
    t = world["teacher"]
    assert cell(world, "rl.a") is None, "nothing reaches the journal before the release"
    office = app_db.client("office")
    assert office.post(f"/api/exams/{eid}/release").status == 403
    r = t.post(f"/api/exams/{eid}/release")
    assert r.status == 200, r.text
    assert t.post(f"/api/exams/{eid}/release").status == 400                  # once
    a, b = cell(world, "rl.a"), cell(world, "rl.b")
    assert (a["score"], a["status"], a["exam_id"], a["attempt_no"], a["source"]) == (50.0, "published", eid, 1, "exam")
    assert (b["score"], b["exam_id"]) == (0.0, eid)
    rows = {x["full_name"]: x for x in r.json["rows"]}
    assert rows["Açıqlama rl.a"]["points"] == 50.0 and rows["Açıqlama rl.b"]["status"] in ("exam_min", "pass_mark")
    assert q("SELECT 1 FROM audit WHERE action='exam_released' AND detail LIKE ?", (f"#{eid}%",))
    assert q("SELECT 1 FROM notifications WHERE user_id=? AND kind='exam'", (world["ids"]["rl.a"],))
    assert [e["kind"] for e in q("SELECT kind FROM exam_events WHERE exam_id=? ORDER BY seq", (eid,))][-1] == "exam.released"


def test_only_the_teacher_sees_the_similar_answers(app_db, world):
    eid = exam(app_db, world, {"rl.a": "right", "rl.b": "wrong", "rl.c": "wrong"})
    r = world["teacher"].get(f"/api/exams/{eid}/analysis")
    assert r.status == 200, r.text
    pair = r.json["pairs"][0]
    assert {pair["a_name"], pair["b_name"]} == {"Açıqlama rl.b", "Açıqlama rl.c"} and pair["same"] == 3
    assert all(x["rate"] is not None for x in r.json["questions"]) and r.json["questions"][0]["wrong"][0]["value"] == '"99"'
    for role in ("office", "leader", "admin", "student"):
        assert app_db.client(role).get(f"/api/exams/{eid}/analysis").status == 403, role


def test_a_retake_keeps_the_first_result_and_both_are_shown(app_db, world):
    first = exam(app_db, world, {"rl.c": "wrong"})
    t = world["teacher"]
    assert t.post(f"/api/exams/{first}/release").status == 200
    assert cell(world, "rl.c")["score"] == 0.0
    retake = exam(app_db, world, {"rl.c": "right"}, kind="retake")
    assert t.post(f"/api/exams/{retake}/release").status == 200
    c = cell(world, "rl.c")
    assert (c["score"], c["exam_id"], c["attempt_no"]) == (50.0, retake, 2)
    log = q("SELECT * FROM grade_changes WHERE user_id=? AND course_id=? ORDER BY id DESC", (world["ids"]["rl.c"], world["course"]))[0]
    assert (log["old_score"], log["new_score"]) == (0.0, 50.0) and f"#{retake}" in log["reason"]
    assert q("SELECT score FROM exam_attempts WHERE exam_id=? AND student_id=?", (first, world["ids"]["rl.c"]))[0]["score"] == 0.0
    for who in (t, app_db.client("office")):
        shown = {r["exam"]["id"]: r for r in who.get(f"/api/courses/{world['course']}/exam-results").json}
        assert {first, retake} <= set(shown)
        points = [next(x["points"] for x in shown[eid]["rows"] if x["student_id"] == world["ids"]["rl.c"]) for eid in (first, retake)]
        assert points == [0.0, 50.0]
