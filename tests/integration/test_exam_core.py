"""The exam core (tasks/todo.md, Task 26): forms by seed, the server's clock, the automatic submission, the roster with
the journal's admission and the office's exception, what a student is answered, and the window in UTC."""
from datetime import timedelta

import pytest

from zeka.core import clock, jobs
from zeka.legacy import periodic, store  # noqa: F401  registers the jobs
from zeka.modules.exam import domain

MARK = "imtahan-sualı"


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def run(sql, args=()):
    c = store.connect()
    try:
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def student_as(app_db, username):
    s = app_db.client()
    assert s.post("/api/auth/demo", {"role": "student", "user": username}).status == 200
    return s


@pytest.fixture(scope="module")
def world(app_db):
    admin, teacher = app_db.client("admin"), app_db.client("teacher")
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    gid = q("SELECT group_id FROM users WHERE id=?", (app_db.client("student").user["id"],))[0]["group_id"]
    cid = admin.post("/api/directory/courses", {"code": "EX-101", "name": "İmtahan sınağı", "credits": 5, "term_id": term["id"],
                                                "teacher_id": teacher.user["id"]}).json["id"]
    names = {}
    for n in ("ex.a", "ex.b", "ex.c"):
        names[n] = admin.post("/api/directory/users", {"username": n, "full_name": f"İmtahan {n}", "role": "student", "group_id": gid,
                                                       "student_no": n.upper()}).json["id"]
    for n in ("ex.a", "ex.b"):
        admin.post(f"/api/directory/courses/{cid}/enrollments", {"user_id": names[n]})
    for i in range(12):
        qtype = ("mcq", "numeric", "tf")[i % 3]
        opts = '["0", "1", "2", "3"]' if qtype == "mcq" else '["Doğru", "Yanlış"]' if qtype == "tf" else "[]"
        ans = "2" if qtype == "mcq" else "true" if qtype == "tf" else str(i)
        run("INSERT INTO questions(course_id,qtype,text,options,answer,unit,explanation,difficulty,topic,status,purpose,created_at) "
            "VALUES(?,?,?,?,?,'','izah','Asan','Om','approved','exam','x')", (cid, qtype, f"{MARK} {i}: ?", opts, ans))
    return {"course": cid, "students": names, "teacher": teacher}


def make_exam(world, **kw):
    body = {"title": "Yekun imtahan", "day": store.now().date().isoformat(), "start": "00:01", "end": "23:59", "duration_min": 60,
            "plan": [{"difficulty": "Asan", "count": 6}], **kw}
    r = world["teacher"].post(f"/api/courses/{world['course']}/exams", body)
    assert r.status == 200, r.text
    return r.json["id"]


@pytest.fixture(scope="module")
def opened(world):
    eid = make_exam(world)
    assert world["teacher"].post(f"/api/exams/{eid}/open").status == 200
    return eid


def test_two_students_get_different_forms_and_a_second_start_returns_the_same_attempt(app_db, world, opened):
    a, b = student_as(app_db, "ex.a"), student_as(app_db, "ex.b")
    va, vb = a.post(f"/api/exams/{opened}/start").json, b.post(f"/api/exams/{opened}/start").json
    assert ([x["id"] for x in va["questions"]], [x["options"] for x in va["questions"]]) != \
        ([x["id"] for x in vb["questions"]], [x["options"] for x in vb["questions"]])
    again = a.post(f"/api/exams/{opened}/start").json
    assert [x["id"] for x in again["questions"]] == [x["id"] for x in va["questions"]]
    assert [x["options"] for x in again["questions"]] == [x["options"] for x in va["questions"]]
    assert len(q("SELECT id FROM exam_attempts WHERE exam_id=? AND student_id=?", (opened, world["students"]["ex.a"]))) == 1


def test_an_answer_after_the_deadline_is_refused_by_the_server_s_clock(app_db, world, opened, monkeypatch):
    a = student_as(app_db, "ex.a")
    v = a.get(f"/api/exams/{opened}").json
    qid = v["questions"][0]["id"]
    assert a.put(f"/api/exams/{opened}/answers/{qid}", {"value": 1}).status == 200
    late = clock.now() + timedelta(minutes=61)
    monkeypatch.setattr(clock, "now", lambda: late)
    assert a.put(f"/api/exams/{opened}/answers/{qid}", {"value": 2}).status == 409


def test_the_next_autosubmit_cycle_submits_an_attempt_past_its_deadline(app_db, world, opened, monkeypatch):
    sid = world["students"]["ex.b"]
    late = clock.now() + timedelta(minutes=61)
    monkeypatch.setattr(clock, "now", lambda: late)
    c = store.connect()
    try:
        c.execute("DELETE FROM job_runs WHERE name='exam.autosubmit'")
        c.commit()
        assert jobs.run_due(c, "test", late, names=["exam.autosubmit"]) == [("exam.autosubmit", "ok")]
    finally:
        c.close()
    att = q("SELECT status, auto FROM exam_attempts WHERE exam_id=? AND student_id=?", (opened, sid))[0]
    assert att == {"status": "submitted", "auto": 1}
    assert q("SELECT 1 FROM exam_events WHERE exam_id=? AND kind='attempt.submitted' AND student_id=?", (opened, sid))


def test_a_student_off_the_roster_is_refused_with_a_reason_and_the_office_can_let_them_in(app_db, world):
    eid = make_exam(world, title="Siyahı sınağı")
    sid = world["students"]["ex.a"]
    run("INSERT INTO lessons(course_id,day,start,end,kind,academic_hours,slot_day,slot_start) VALUES(?,?,'00:00','00:30','Mühazirə',4,?,'00:00')",
        (world["course"], store.now().date().isoformat(), store.now().date().isoformat()))
    lid = q("SELECT id FROM lessons WHERE course_id=? ORDER BY id DESC LIMIT 1", (world["course"],))[0]["id"]
    run("INSERT INTO attendance(lesson_id,user_id,status) VALUES(?,?,'absent')", (lid, sid))       # 4 of 4 hours missed: not admitted
    assert world["teacher"].post(f"/api/exams/{eid}/open").status == 200
    a = student_as(app_db, "ex.a")
    r = a.post(f"/api/exams/{eid}/start")
    assert r.status == 403 and "Davamiyyət" in r.json["error"]
    c = student_as(app_db, "ex.c")
    assert c.post(f"/api/exams/{eid}/start").status == 403, "not enrolled: not on the roster"
    assert q("SELECT COUNT(*) n FROM exam_events WHERE exam_id=? AND kind='attempt.refused'", (eid,))[0]["n"] == 2
    office = app_db.client("office")
    assert office.post(f"/api/exams/{eid}/roster/{sid}/exception", {"reason": ""}).status == 400
    assert office.post(f"/api/exams/{eid}/roster/{sid}/exception", {"reason": "Tibbi arayış təqdim edilib"}).status == 200
    assert q("SELECT 1 FROM audit WHERE action='exam_exception' AND detail LIKE ?", (f"%#{sid}%",))
    assert a.post(f"/api/exams/{eid}/start").status == 200


FORBIDDEN = {"answer", "explanation", "correct", "score", "max_score", "secret", "seed", "plan", "purpose"}


def _keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path + "." + k
            yield from _keys(v, path + "." + k)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v, path + "[]")


def test_every_student_exam_answer_holds_only_allowed_keys(app_db, world):
    eid = make_exam(world, title="Açar sınağı")
    assert world["teacher"].post(f"/api/exams/{eid}/open").status == 200
    b = student_as(app_db, "ex.b")
    answers = [b.post(f"/api/exams/{eid}/start").json, b.get(f"/api/exams/{eid}").json, b.get(f"/api/courses/{world['course']}/exams").json]
    qid = answers[0]["questions"][0]["id"]
    answers.append(b.put(f"/api/exams/{eid}/answers/{qid}", {"value": "1"}).json)
    answers.append(b.post(f"/api/exams/{eid}/submit").json)
    for body in answers:
        keys = {k.rsplit(".", 1)[-1] for k in _keys(body)}
        assert not keys & FORBIDDEN, keys & FORBIDDEN
    for qn in answers[0]["questions"]:
        assert set(qn) == set(domain.PUBLIC)


def test_a_window_entered_in_baku_time_is_kept_in_utc(world):
    eid = make_exam(world, title="Saat sınağı", day="2026-12-10", start="10:00", end="12:00", duration_min=90)
    e = q("SELECT opens_at, closes_at FROM exams WHERE id=?", (eid,))[0]
    assert e == {"opens_at": "2026-12-10T06:00:00+00:00", "closes_at": "2026-12-10T08:00:00+00:00"}


def test_closing_grades_the_attempts(app_db, world, opened):
    r = world["teacher"].post(f"/api/exams/{opened}/close")
    assert r.status == 200
    graded = q("SELECT status, score, max_score FROM exam_attempts WHERE exam_id=?", (opened,))
    assert graded and all(g["status"] == "graded" and g["max_score"] == 6 for g in graded)
