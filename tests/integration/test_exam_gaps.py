"""Gaps the Checkpoint D test review found (docs/review/checkpoint-d-2026-11-19.md, T-2, T-3, T-6, T-7, T-12, T-13,
T-18, T-25): multiple-choice and true/false answers graded end to end by the shown index, the autosubmit leaving an
attempt with time left, a teacher of another course managing nothing, a long relay outage losing no mail, the student's
view holding only the public keys, release writing nothing for an absent student, and scaling end to end."""
import json
from datetime import timedelta

import pytest

from zeka.core import clock, jobs
from zeka.legacy import periodic, store  # noqa: F401
from zeka.modules.exam import domain, service


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


def student(app_db, name):
    s = app_db.client()
    assert s.post("/api/auth/demo", {"role": "student", "user": name}).status == 200
    return s


@pytest.fixture(scope="module")
def world(app_db):
    admin, teacher = app_db.client("admin"), app_db.client("teacher")
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    gid = q("SELECT group_id FROM users WHERE id=?", (app_db.client("student").user["id"],))[0]["group_id"]
    cid = admin.post("/api/directory/courses", {"code": "PR-101", "name": "Probe", "credits": 5, "term_id": term["id"],
                                                "teacher_id": teacher.user["id"]}).json["id"]
    ids = {}
    for n in ("pr.a", "pr.b", "pr.c"):
        ids[n] = admin.post("/api/directory/users", {"username": n, "full_name": f"Probe {n}", "role": "student", "group_id": gid,
                                                     "student_no": n.upper()}).json["id"]
        admin.post(f"/api/directory/courses/{cid}/enrollments", {"user_id": ids[n]})
    for i in range(4):
        run("INSERT INTO questions(course_id,qtype,text,options,answer,unit,explanation,difficulty,topic,status,purpose,created_at) "
            "VALUES(?,'mcq',?,'[\"alfa\",\"beta\",\"qamma\",\"delta\"]','2','','izah','Asan','Om','approved','exam','x')", (cid, f"mcq {i}"))
    for i in range(2):
        run("INSERT INTO questions(course_id,qtype,text,options,answer,unit,explanation,difficulty,topic,status,purpose,created_at) "
            "VALUES(?,'tf',?,'[\"Doğru\",\"Yanlış\"]','true','','izah','Asan','Om','approved','exam','x')", (cid, f"tf {i}"))
    other = q("SELECT username FROM users WHERE role='teacher' AND id<>? ORDER BY id LIMIT 1", (teacher.user["id"],))[0]["username"]
    logins = q("SELECT value FROM settings WHERE key='demo_logins'")[0]["value"]
    run("UPDATE settings SET value=? WHERE key='demo_logins'", (json.dumps({**json.loads(logins), "teacher": other}),))
    stranger = app_db.client("teacher")                  # the demo's teacher login pointed at another course teacher
    run("UPDATE settings SET value=? WHERE key='demo_logins'", (logins,))
    assert stranger.user["id"] != teacher.user["id"] and stranger.user["role"] == "teacher"
    assert stranger.user["id"] != teacher.user["id"]
    return {"course": cid, "ids": ids, "teacher": teacher, "stranger": stranger}


def new_exam(world, duration=60):
    t = world["teacher"]
    r = t.post(f"/api/courses/{world['course']}/exams", {"title": "Probe", "day": store.now().date().isoformat(), "start": "00:01",
                                                         "end": "23:59", "duration_min": duration, "plan": [{"count": 6}]})
    assert r.status == 200, r.text
    assert t.post(f"/api/exams/{r.json['id']}/open").status == 200
    return r.json["id"]


def test_t2_right_mcq_and_tf_answers_by_shown_index_score_full_marks(app_db, world):
    eid = new_exam(world)
    s = student(app_db, "pr.a")
    assert s.post(f"/api/exams/{eid}/enter").status == 200
    qs = s.post(f"/api/exams/{eid}/start").json["questions"]
    for x in qs:
        value = x["options"].index("qamma") if x["qtype"] == "mcq" else "Doğru"       # what exam.js sends: the shown index / the text
        assert s.put(f"/api/exams/{eid}/answers/{x['id']}", {"value": value}).status == 200
    assert any(x["options"] != ["alfa", "beta", "gamma", "delta"] for x in qs if x["qtype"] == "mcq")
    assert s.post(f"/api/exams/{eid}/submit").status == 200
    assert world["teacher"].post(f"/api/exams/{eid}/close").status == 200
    a = q("SELECT score, max_score FROM exam_attempts WHERE exam_id=? AND student_id=?", (eid, world["ids"]["pr.a"]))[0]
    assert a == {"score": 6.0, "max_score": 6.0}, a


def test_t3_autosubmit_leaves_an_attempt_with_time_left(app_db, world, monkeypatch):
    eid = new_exam(world, duration=30)
    early, late = student(app_db, "pr.b"), student(app_db, "pr.c")
    assert early.post(f"/api/exams/{eid}/enter").status == 200 and early.post(f"/api/exams/{eid}/start").status == 200
    t = clock.now() + timedelta(minutes=20)
    monkeypatch.setattr(clock, "now", lambda: t)
    assert late.post(f"/api/exams/{eid}/enter").status == 200 and late.post(f"/api/exams/{eid}/start").status == 200
    t2 = t + timedelta(minutes=11)                       # early is past its 30 minutes, late has 19 left
    monkeypatch.setattr(clock, "now", lambda: t2)
    c = store.connect()
    try:
        c.execute("DELETE FROM job_runs WHERE name='exam.autosubmit'")
        c.commit()
        assert jobs.run_due(c, "test", t2, names=["exam.autosubmit"]) == [("exam.autosubmit", "ok")]
    finally:
        c.close()
    got = {r["student_id"]: r["status"] for r in q("SELECT student_id, status FROM exam_attempts WHERE exam_id=?", (eid,))}
    assert got == {world["ids"]["pr.b"]: "submitted", world["ids"]["pr.c"]: "in_progress"}, got
    assert world["teacher"].post(f"/api/exams/{eid}/close").status == 200


def test_t6_a_teacher_of_another_course_manages_nothing(app_db, world):
    eid = new_exam(world)
    s = student(app_db, "pr.a")
    assert s.post(f"/api/exams/{eid}/enter").status == 200 and s.post(f"/api/exams/{eid}/start").status == 200
    x = world["stranger"]
    codes = {"create": x.post(f"/api/courses/{world['course']}/exams", {"title": "X", "day": store.now().date().isoformat(), "start": "00:01",
                                                                       "end": "23:59", "duration_min": 60, "plan": [{"count": 1}]}).status,
             "manage": x.get(f"/api/exams/{eid}/manage").status,
             "board": x.get(f"/api/exams/{eid}/board").status,
             "close": x.post(f"/api/exams/{eid}/close").status}
    assert world["teacher"].post(f"/api/exams/{eid}/close").status == 200
    codes.update(release=x.post(f"/api/exams/{eid}/release").status, analysis=x.get(f"/api/exams/{eid}/analysis").status)
    assert all(v in (403, 404) for v in codes.values()), codes


def test_t18_a_form_changed_after_submission_is_seen_by_exam_verify(app_db, world):
    eid = new_exam(world)
    s = student(app_db, "pr.b")
    assert s.post(f"/api/exams/{eid}/enter").status == 200
    qs = s.post(f"/api/exams/{eid}/start").json["questions"]
    for x in qs:                                          # every answer wrong: the shown index of "alfa", and "Yanlış"
        assert s.put(f"/api/exams/{eid}/answers/{x['id']}", {"value": x["options"].index("alfa") if x["qtype"] == "mcq" else "Yanlış"}).status == 200
    assert s.post(f"/api/exams/{eid}/submit").status == 200
    sid = world["ids"]["pr.b"]
    f = q("SELECT items FROM exam_forms WHERE exam_id=? AND student_id=?", (eid, sid))[0]
    items = json.loads(f["items"])
    for it in items:                                      # tamper: the option shown where "alfa" was is now "qamma" (index 2)
        if len(it["order"]) == 4:
            i = it["order"].index(0)
            j = it["order"].index(2)
            it["order"][i], it["order"][j] = it["order"][j], it["order"][i]
    run("UPDATE exam_forms SET items=? WHERE exam_id=? AND student_id=?", (json.dumps(items), eid, sid))
    assert world["teacher"].post(f"/api/exams/{eid}/close").status == 200
    score = q("SELECT score FROM exam_attempts WHERE exam_id=? AND student_id=?", (eid, sid))[0]["score"]
    c = store.connect()
    try:
        problems = service.verify(c, eid)["problems"]
    finally:
        c.close()
    assert score == 4.0                                   # the tampered form lifts the grade ...
    assert "form_changed" in {p["problem"] for p in problems}   # ... and exam-verify says so (Checkpoint D, TM-5)


def test_t12_the_student_sees_only_the_public_keys_of_a_question(app_db, world):
    eid = new_exam(world)
    s = student(app_db, "pr.c")
    assert s.post(f"/api/exams/{eid}/enter").status == 200
    view = s.post(f"/api/exams/{eid}/start").json
    assert view["questions"] and all(set(x) == set(domain.PUBLIC) for x in view["questions"])
    assert set(view["attempt"]) == {"status", "started_at", "deadline_at", "submitted_at", "remaining_s", "answers"}
    assert world["teacher"].post(f"/api/exams/{eid}/close").status == 200


def test_t13_t25_release_scales_end_to_end_and_writes_nothing_for_an_absent_student(app_db, world):
    eid = new_exam(world)
    s = student(app_db, "pr.a")
    assert s.post(f"/api/exams/{eid}/enter").status == 200
    qs = s.post(f"/api/exams/{eid}/start").json["questions"]
    for n, x in enumerate(qs):                            # 4 of 6 right
        right = x["options"].index("qamma") if x["qtype"] == "mcq" else "Doğru"
        wrong = x["options"].index("alfa") if x["qtype"] == "mcq" else "Yanlış"
        assert s.put(f"/api/exams/{eid}/answers/{x['id']}", {"value": right if n < 4 else wrong}).status == 200
    assert s.post(f"/api/exams/{eid}/submit").status == 200
    t = world["teacher"]
    assert t.post(f"/api/exams/{eid}/close").status == 200 and t.post(f"/api/exams/{eid}/release").status == 200
    got = {r["user_id"]: r["score"] for r in q("SELECT user_id, score FROM grades WHERE exam_id=?", (eid,))}
    assert got == {world["ids"]["pr.a"]: domain.scale(4, 6, 50)} and got[world["ids"]["pr.a"]] == 33.3


def test_t7_a_three_hour_outage_loses_no_mail(app_db, monkeypatch):
    import socket
    from zeka.modules.comms import service as comms
    with socket.socket() as sk:                               # a port nobody listens on: connection refused
        sk.bind(("127.0.0.1", 0))
        port = sk.getsockname()[1]
    monkeypatch.setenv("ZEKA_SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("ZEKA_SMTP_PORT", str(port))
    monkeypatch.setenv("ZEKA_SMTP_TLS", "none")
    c = store.connect()
    try:
        c.execute("DELETE FROM outbox")
        assert comms.queue_to(c, "teacher@aztu.test", "exam.root", "exam.root", {"title": "Yekun", "root": "ab" * 32, "exam_id": 1})
        c.commit()
        t0 = clock.now()
        for minute in range(0, 181):
            comms.send_due(c, t0 + timedelta(minutes=minute))
        row = store.rows(c, "SELECT status, attempts FROM outbox")[0]
        assert row["status"] == "pending" and row["attempts"] >= 8, row      # still waiting after three hours
    finally:
        c.close()
