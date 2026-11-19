"""``manage.py exam-verify`` (tasks/todo.md, Task 30): any stored event changed or removed (the last one included) fails
it with the first broken link; answers changed after a submission and a score changed after grading fail it with the
attempt; a submission after a proctor's reopen does not; a chain rewritten consistently in the database passes on its
own but fails against the root kept outside the database."""
import hashlib
import json

import pytest

import manage
from zeka.legacy import store
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
        c.execute(sql, args)
        c.commit()
    finally:
        c.close()


TRIGGERS = ("CREATE TRIGGER IF NOT EXISTS exam_events_no_update BEFORE UPDATE ON exam_events "
            "BEGIN SELECT RAISE(ABORT, 'exam_events is append-only'); END",
            "CREATE TRIGGER IF NOT EXISTS exam_events_no_delete BEFORE DELETE ON exam_events "
            "BEGIN SELECT RAISE(ABORT, 'exam_events is append-only'); END")


def tamper(sql, args=()):
    """What someone with the database file can do: drop the append-only triggers (0301), change the log, put them back."""
    c = store.connect()
    try:
        c.execute("DROP TRIGGER exam_events_no_update")
        c.execute("DROP TRIGGER exam_events_no_delete")
        c.execute(sql, args)
        for t in TRIGGERS:
            c.execute(t)
        c.commit()
    finally:
        c.close()


def verify(eid, root=None):
    c = store.connect()
    try:
        return service.verify(c, eid, root)
    finally:
        c.close()


@pytest.fixture(scope="module")
def world(app_db):
    admin, teacher = app_db.client("admin"), app_db.client("teacher")
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    gid = q("SELECT group_id FROM users WHERE id=?", (app_db.client("student").user["id"],))[0]["group_id"]
    cid = admin.post("/api/directory/courses", {"code": "CV-101", "name": "Zəncir sınağı", "credits": 5, "term_id": term["id"],
                                                "teacher_id": teacher.user["id"]}).json["id"]
    ids = {}
    for n in ("cv.a", "cv.b"):
        ids[n] = admin.post("/api/directory/users", {"username": n, "full_name": f"Zəncir {n}", "role": "student", "group_id": gid,
                                                     "student_no": n.upper()}).json["id"]
        admin.post(f"/api/directory/courses/{cid}/enrollments", {"user_id": ids[n]})
    for i in range(4):
        run("INSERT INTO questions(course_id,qtype,text,options,answer,unit,explanation,difficulty,topic,status,purpose,created_at) "
            "VALUES(?,'numeric',?,'[]',?,'','izah','Asan','Om','approved','exam','x')", (cid, f"zəncir sualı {i}", str(i)))
    return {"course": cid, "ids": ids, "teacher": teacher}


def sitting(app_db, world, close=True):
    """An exam both students sat and submitted (and, with ``close``, that the teacher closed and graded)."""
    t = world["teacher"]
    r = t.post(f"/api/courses/{world['course']}/exams", {"title": "Zəncirli imtahan", "day": store.now().date().isoformat(), "start": "00:01",
                                                          "end": "23:59", "duration_min": 60, "plan": [{"count": 3}]})
    eid = r.json["id"]
    assert t.post(f"/api/exams/{eid}/open").status == 200
    students = {}
    for n in ("cv.a", "cv.b"):
        s = app_db.client()
        assert s.post("/api/auth/demo", {"role": "student", "user": n}).status == 200
        assert s.post(f"/api/exams/{eid}/enter").status == 200
        qs = s.post(f"/api/exams/{eid}/start").json["questions"]
        for x in qs:
            assert s.put(f"/api/exams/{eid}/answers/{x['id']}", {"value": "1"}).status == 200
        assert s.post(f"/api/exams/{eid}/submit").status == 200
        students[n] = (s, qs)
    if close:
        assert t.post(f"/api/exams/{eid}/close").status == 200
    return eid, students


def events(eid):
    return q("SELECT * FROM exam_events WHERE exam_id=? ORDER BY seq", (eid,))


def test_an_untouched_exam_verifies_and_its_events_are_complete(app_db, world, capsys):
    eid, _ = sitting(app_db, world)
    r = verify(eid)
    assert r["problems"] == [] and r["events"] == len(events(eid)) and r["head"] == events(eid)[-1]["hash"]
    kinds = [e["kind"] for e in events(eid)]
    assert kinds.count("attempt.submitted") == 2 and kinds.count("attempt.graded") == 2 and kinds[-1] == "exam.closed"
    sub = json.loads(next(e for e in events(eid) if e["kind"] == "attempt.submitted")["data"])
    assert set(sub) == {"attempt_id", "auto", "form_seed", "form_sha256", "answers_sha256"} and len(sub["answers_sha256"]) == 64
    assert manage.main(["exam-verify", str(eid), "--root", r["head"]]) == 0
    assert "OK (root matches)" in capsys.readouterr().out
    assert manage.main(["exam-verify", "999999"]) == 2


@pytest.mark.parametrize("where", ["first", "middle", "last"])
def test_a_changed_event_fails_at_its_link(app_db, world, where, capsys):
    eid, _ = sitting(app_db, world)
    evs = events(eid)
    target = {"first": evs[0], "middle": evs[len(evs) // 2], "last": evs[-1]}[where]
    tamper("UPDATE exam_events SET data=? WHERE id=?", (json.dumps({"forged": True}), target["id"]))
    assert verify(eid)["problems"][0] == {"what": "chain", "seq": target["seq"], "problem": "hash"}
    assert manage.main(["exam-verify", str(eid)]) == 1
    assert f"BROKEN chain at seq {target['seq']}" in capsys.readouterr().out


def test_a_removed_event_fails_and_the_removed_last_one_fails_against_the_root(app_db, world):
    eid, _ = sitting(app_db, world)
    evs = events(eid)
    tamper("DELETE FROM exam_events WHERE id=?", (evs[3]["id"],))
    assert verify(eid)["problems"][0] == {"what": "chain", "seq": 4, "problem": "missing"}

    eid, _ = sitting(app_db, world)
    last = events(eid)[-1]
    tamper("DELETE FROM exam_events WHERE id=?", (last["id"],))
    # the shorter chain is consistent in itself, but the closing protocol printed the removed link ...
    assert verify(eid)["problems"] == [{"what": "anchor", "document": "protocol", "seq": last["seq"], "problem": "root_differs"}]
    # ... and so did the e-mail
    assert verify(eid, last["hash"])["problems"][-1]["what"] == "root"


def test_answers_changed_after_a_submission_fail_and_a_resubmission_after_reopen_does_not(app_db, world):
    eid, students = sitting(app_db, world, close=False)
    a = q("SELECT * FROM exam_attempts WHERE exam_id=? AND student_id=?", (eid, world["ids"]["cv.a"]))[0]
    run("UPDATE exam_answers SET value='\"42\"' WHERE attempt_id=? AND qid=?", (a["id"], students["cv.a"][1][0]["id"]))
    p = verify(eid)["problems"]
    assert p == [{"what": "attempt", "attempt_id": a["id"], "student_id": a["student_id"], "problem": "answers_changed"}]

    t = world["teacher"]
    assert t.post(f"/api/exams/{eid}/students/{a['student_id']}/reopen", {"reason": "səhvən təslim", "minutes": 10}).status == 200
    s, qs = students["cv.a"]
    assert s.put(f"/api/exams/{eid}/answers/{qs[1]['id']}", {"value": "2"}).status == 200
    assert s.post(f"/api/exams/{eid}/submit").status == 200
    assert verify(eid)["problems"] == []


def test_a_score_changed_after_grading_fails(app_db, world):
    eid, _ = sitting(app_db, world)
    a = q("SELECT * FROM exam_attempts WHERE exam_id=? AND student_id=?", (eid, world["ids"]["cv.b"]))[0]
    run("UPDATE exam_attempts SET score=score+1 WHERE id=?", (a["id"],))
    assert verify(eid)["problems"] == [{"what": "attempt", "attempt_id": a["id"], "student_id": a["student_id"], "problem": "score_changed"}]


def test_a_chain_rewritten_in_the_database_fails_against_the_root(app_db, world):
    eid, _ = sitting(app_db, world)
    root = events(eid)[-1]["hash"]
    evs = events(eid)
    evs[2]["data"] = json.dumps({"forged": True})
    prev = domain.GENESIS
    c = store.connect()
    try:
        c.execute("DROP TRIGGER exam_events_no_update")
        for e in evs:                                          # an attacker with the database recomputes every link
            h = domain.link(prev, domain.canonical_event(e["exam_id"], e["seq"], e["kind"], e["actor_id"], e["student_id"],
                                                         json.loads(e["data"]), e["at"]))
            c.execute("UPDATE exam_events SET data=?, prev_hash=?, hash=? WHERE id=?", (e["data"], prev, h, e["id"]))
            prev = h
        pid = c.execute("SELECT protocol_id FROM exams WHERE id=?", (eid,)).fetchone()[0]
        payload = json.loads(c.execute("SELECT payload FROM documents WHERE id=?", (pid,)).fetchone()[0])
        payload["data"]["root"] = prev                                  # and the protocol's line, its payload hash too
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        c.execute("UPDATE documents SET payload=?, hash=? WHERE id=?", (text, hashlib.sha256(text.encode()).hexdigest(), pid))
        c.execute(TRIGGERS[0])
        c.commit()
    finally:
        c.close()
    assert verify(eid)["problems"] == []
    assert manage.main(["exam-verify", str(eid), "--root", root]) == 1


def test_the_log_refuses_an_update_or_a_delete_in_the_database(app_db, world):
    # Checkpoint D (TM-21): a mistaken statement fails at once; only someone who drops the triggers can change the log
    import sqlite3
    eid, _ = sitting(app_db, world, close=False)
    for sql in ("UPDATE exam_events SET data='{}' WHERE exam_id=?", "DELETE FROM exam_events WHERE exam_id=?"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            run(sql, (eid,))
    assert verify(eid)["problems"] == []
