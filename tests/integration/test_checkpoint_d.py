"""Checkpoint D (review of Tasks 23, 25-30 and 36): regression tests for the confirmed findings, by the ids of
docs/review/checkpoint-d-2026-11-19.md (CR-, AR-, TM-, SEC-, SF-, PY-, T-). Each fails on the code before its fix."""
import hashlib
import json
import threading
import time
from datetime import timedelta

import pytest

from zeka.core import clock, jobs
from zeka.legacy import common, store
from zeka.modules.exam import domain, service


def db():
    return store.connect()


def q(sql, args=()):
    c = db()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def run(sql, args=()):
    c = db()
    try:
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def one(sql, args=()):
    r = q(sql, args)
    return r[0] if r else None


@pytest.fixture(scope="module")
def world(app_db):
    admin, teacher = app_db.client("admin"), app_db.client("teacher")
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    gid = q("SELECT group_id FROM users WHERE id=?", (app_db.client("student").user["id"],))[0]["group_id"]
    cid = admin.post("/api/directory/courses", {"code": "CD-101", "name": "Yoxlama D", "credits": 5, "term_id": term["id"],
                                                "teacher_id": teacher.user["id"]}).json["id"]
    ids = {}
    for n in ("cd.a", "cd.b", "cd.c"):
        ids[n] = admin.post("/api/directory/users", {"username": n, "full_name": f"Yoxlama {n}", "role": "student", "group_id": gid,
                                                     "student_no": n.upper()}).json["id"]
        admin.post(f"/api/directory/courses/{cid}/enrollments", {"user_id": ids[n]})
    qids = [run("INSERT INTO questions(course_id,qtype,text,options,answer,unit,explanation,difficulty,topic,status,purpose,created_at) "
                "VALUES(?,'numeric',?,'[]',?,'','izah','Asan','Om','approved','exam','x')", (cid, f"yoxlama sualı {i}", str(i))) for i in range(4)]
    return {"course": cid, "ids": ids, "teacher": teacher, "admin": admin, "group": gid, "qids": qids}


def new_exam(world, kind="main", count=3, **kw):
    t = world["teacher"]
    r = t.post(f"/api/courses/{world['course']}/exams", {"title": f"Yoxlama ({kind})", "kind": kind, "day": store.now().date().isoformat(),
                                                         "start": "00:01", "end": "23:59", "duration_min": 60, "plan": [{"count": count}], **kw})
    assert r.status == 200, r.text
    eid = r.json["id"]
    assert t.post(f"/api/exams/{eid}/open").status == 200, eid
    return eid


def sit(app_db, eid, name, right=True, submit=True):
    s = app_db.client()
    assert s.post("/api/auth/demo", {"role": "student", "user": name}).status == 200
    assert s.post(f"/api/exams/{eid}/enter").status == 200
    qs = s.post(f"/api/exams/{eid}/start").json["questions"]
    for x in qs:
        ans = one("SELECT answer FROM questions WHERE id=?", (x["id"],))["answer"]
        assert s.put(f"/api/exams/{eid}/answers/{x['id']}", {"value": ans if right else "99"}).status == 200
    if submit:
        assert s.post(f"/api/exams/{eid}/submit").status == 200
    return s


def user_row(uid):
    return one("SELECT * FROM users WHERE id=?", (uid,))


def verify(eid, root=None):
    c = db()
    try:
        return service.verify(c, eid, root)
    finally:
        c.close()


# ---------------------------------------------------------------- A. attempt state and the write lock
def test_cr1_a_submit_racing_close_does_not_turn_a_graded_attempt_back(app_db, world):
    eid = new_exam(world)
    sid = world["ids"]["cd.a"]
    sit(app_db, eid, "cd.a", submit=False)
    a, b = db(), db()
    try:
        assert service.close(a, user_row(world["teacher"].user["id"]), eid)[0] == "ok"     # holds the write lock, not committed
        done: dict = {}
        t = threading.Thread(target=lambda: done.setdefault("r", service.submit(b, user_row(sid), eid)))
        t.start()
        time.sleep(0.4)                      # the old code read "in_progress" here, then waited for the lock to write
        a.commit()
        t.join(10)
        b.commit()
    finally:
        a.close()
        b.close()
    assert one("SELECT status FROM exam_attempts WHERE exam_id=? AND student_id=?", (eid, sid))["status"] == "graded"
    assert world["teacher"].post(f"/api/exams/{eid}/close").status == 400               # and a second close is refused
    assert verify(eid)["problems"] == []


def test_ar2_close_and_release_of_300_students_keep_the_write_lock_short(app_db, world):
    """The suite's guard (ZEKA_TX_GUARD) fails a request that holds the write lock over 200 ms."""
    eid = new_exam(world)
    c = db()
    try:
        e = store.row(c, "SELECT * FROM exams WHERE id=?", (eid,))
        pool = [store.row(c, "SELECT * FROM questions WHERE id=?", (qid,)) for qid in world["qids"]]
        at = clock.now().isoformat(timespec="seconds")
        for n in range(300):
            uid = c.execute("INSERT INTO users(username,full_name,role,group_id,status) VALUES(?,?,'student',?,'active')",
                            (f"cd.load{n}", f"Yük {n}", world["group"])).lastrowid
            c.execute("INSERT INTO enrollments(user_id,course_id) VALUES(?,?)", (uid, world["course"]))
            c.execute("INSERT INTO exam_roster(exam_id,student_id,status,added_at,group_id) VALUES(?,?,'eligible',?,?)", (eid, uid, at, world["group"]))
            seed = domain.seed(e["secret"], eid, uid)
            items = domain.build_form(pool, [{"difficulty": None, "topic": None, "count": 3}], seed)
            c.execute("INSERT INTO exam_forms(exam_id,student_id,seed,items,created_at) VALUES(?,?,?,?,?)", (eid, uid, seed, json.dumps(items), at))
            aid = c.execute("INSERT INTO exam_attempts(exam_id,student_id,started_at,deadline_at) VALUES(?,?,?,?)",
                            (eid, uid, at, "2999-01-01T00:00:00+00:00")).lastrowid
            for x in items:
                c.execute("INSERT INTO exam_answers(attempt_id,qid,value,saved_at) VALUES(?,?,?,?)", (aid, x["qid"], '"1"', at))
        c.commit()
    finally:
        c.close()
    t = world["teacher"]
    r = t.post(f"/api/exams/{eid}/close")
    assert r.status == 200, r.text
    r = t.post(f"/api/exams/{eid}/release")
    assert r.status == 200 and r.json["released"] == 300, r.text
    assert one("SELECT COUNT(*) AS n FROM grades WHERE exam_id=?", (eid,))["n"] == 300


# ---------------------------------------------------------------- B. the chain and exam-verify
def append_link(eid, kind, student_id, data):
    """What someone with the database can do: append a correctly linked event."""
    c = db()
    try:
        h = c.execute("SELECT seq, hash FROM exam_events WHERE exam_id=? ORDER BY seq DESC LIMIT 1", (eid,)).fetchone()
        at = clock.now().isoformat(timespec="seconds")
        new = domain.link(h[1], domain.canonical_event(eid, h[0] + 1, kind, None, student_id, data, at))
        c.execute("INSERT INTO exam_events(exam_id,seq,kind,actor_id,student_id,data,at,prev_hash,hash) VALUES(?,?,?,?,?,?,?,?,?)",
                  (eid, h[0] + 1, kind, None, student_id, json.dumps(data, sort_keys=True), at, h[1], new))
        c.commit()
    finally:
        c.close()


def closed(app_db, world):
    eid = new_exam(world)
    sit(app_db, eid, "cd.b", right=False)
    assert world["teacher"].post(f"/api/exams/{eid}/close").status == 200
    a = one("SELECT * FROM exam_attempts WHERE exam_id=? AND student_id=?", (eid, world["ids"]["cd.b"]))
    return eid, a


def test_tm1_events_appended_after_the_close_fail_even_with_the_e_mailed_root(app_db, world):
    eid, a = closed(app_db, world)
    root = q("SELECT hash FROM exam_events WHERE exam_id=? ORDER BY seq DESC LIMIT 1", (eid,))[0]["hash"]
    run("UPDATE exam_attempts SET score=max_score WHERE id=?", (a["id"],))
    append_link(eid, "attempt.graded", a["student_id"], {"attempt_id": a["id"], "score": a["max_score"], "max_score": a["max_score"]})
    assert "grading_after_close" in {x["problem"] for x in verify(eid, root)["problems"]}


@pytest.mark.parametrize("change, problem", [
    ("UPDATE exam_attempts SET max_score=1 WHERE id=?", "score_changed"),
    ("UPDATE exam_attempts SET status='in_progress' WHERE id=?", "status_changed"),
    ("DELETE FROM exam_attempts WHERE id=?", "attempt_missing"),
])
def test_tm2_the_attempt_row_is_checked_against_its_events(app_db, world, change, problem):
    eid, a = closed(app_db, world)
    run(change, (a["id"],))
    assert problem in {x["problem"] for x in verify(eid)["problems"]}


def test_tm2_tm5_a_swapped_owner_or_a_changed_form_fails(app_db, world):
    eid, a = closed(app_db, world)
    run("UPDATE exam_forms SET items=? WHERE exam_id=? AND student_id=?", (json.dumps([{"qid": world["qids"][0], "order": []}]), eid, a["student_id"]))
    assert "form_changed" in {x["problem"] for x in verify(eid)["problems"]}
    eid, a = closed(app_db, world)
    run("UPDATE exam_attempts SET student_id=? WHERE id=?", (world["ids"]["cd.c"], a["id"]))
    assert "student_changed" in {x["problem"] for x in verify(eid)["problems"]}


def test_release_never_puts_more_than_the_component_maximum(app_db, world):
    eid, a = closed(app_db, world)
    run("UPDATE exam_attempts SET score=4, max_score=1 WHERE id=?", (a["id"],))
    assert world["teacher"].post(f"/api/exams/{eid}/release").status == 200
    assert one("SELECT score FROM grades WHERE exam_id=? AND user_id=?", (eid, a["student_id"]))["score"] <= 50


def test_tm16_sf11_an_anchor_is_read_from_its_hashed_payload_and_must_exist(app_db, world, capsys):
    import manage
    eid, _ = closed(app_db, world)
    pid = one("SELECT protocol_id FROM exams WHERE id=?", (eid,))["protocol_id"]
    run("UPDATE documents SET payload=replace(payload, '\"root\":', '\"root_\":') WHERE id=?", (pid,))   # the hash no longer fits
    assert {"what": "anchor", "document": "protocol", "seq": None, "problem": "anchor_unreadable"} in verify(eid)["problems"]
    assert manage.main(["exam-verify", str(eid)]) == 1
    assert "ANCHOR protocol" in capsys.readouterr().out                      # PY-1: printed, not a KeyError
    run("UPDATE exams SET protocol_id=NULL WHERE id=?", (eid,))
    assert "anchor_missing" in {x["problem"] for x in verify(eid)["problems"]}


def test_tm3_tm12_every_stage_mails_the_new_head_and_none_mailed_is_recorded(app_db, world, monkeypatch):
    run("UPDATE users SET email='teacher@aztu.test' WHERE id=?", (world["teacher"].user["id"],))
    eid, _ = closed(app_db, world)
    assert q("SELECT 1 FROM audit WHERE action='exam_root_not_mailed' AND detail LIKE ?", (f"#{eid} · close%",))   # no relay: on record
    monkeypatch.setenv("ZEKA_SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("ZEKA_SMTP_TLS", "none")
    run("DELETE FROM outbox")
    assert world["teacher"].post(f"/api/exams/{eid}/release").status == 200
    head = q("SELECT hash FROM exam_events WHERE exam_id=? ORDER BY seq DESC LIMIT 1", (eid,))[0]["hash"]
    mails = [json.loads(m["params"]) for m in q("SELECT params FROM outbox WHERE template='exam.root'")]
    assert any(m["what"] == "release" and m["root"] == head for m in mails)


def test_cr11_nothing_is_added_to_a_closed_exam_s_chain(app_db, world):
    eid = new_exam(world)
    s = sit(app_db, eid, "cd.a", submit=False)
    assert world["teacher"].post(f"/api/exams/{eid}/close").status == 200
    before = one("SELECT COUNT(*) AS n FROM exam_events WHERE exam_id=?", (eid,))["n"]
    assert s.post(f"/api/exams/{eid}/signals", {"kind": "blur"}).json["kept"] is False
    app_db.client("student").post(f"/api/exams/{eid}/enter")
    assert one("SELECT COUNT(*) AS n FROM exam_events WHERE exam_id=?", (eid,))["n"] == before


# ---------------------------------------------------------------- C. release, the statement lock, who reads results
def test_tm6_cr7_a_later_release_respects_a_closed_statement_and_a_newer_exam(app_db, world):
    office, t = app_db.client("office"), world["teacher"]
    sid = world["ids"]["cd.c"]
    first = new_exam(world)
    sit(app_db, first, "cd.c", right=True)
    assert t.post(f"/api/exams/{first}/close").status == 200 and t.post(f"/api/exams/{first}/release").status == 200
    assert office.post(f"/api/exams/{first}/statements/{world['group']}/close").status == 200
    other = new_exam(world, kind="individual")                     # same attempt number: may not replace a closed statement
    sit(app_db, other, "cd.c", right=False)
    assert t.post(f"/api/exams/{other}/close").status == 200
    r = t.post(f"/api/exams/{other}/release")
    assert {"student_id": sid, "reason": "statement_closed", "exam_id": first} in r.json["skipped"]
    cell = one("SELECT * FROM grades WHERE user_id=? AND course_id=? AND exam_id IS NOT NULL", (sid, world["course"]))
    assert (cell["exam_id"], cell["score"]) == (first, 50.0)
    retake = new_exam(world, kind="retake")                        # a retake (attempt 2) is a new result: it goes in
    sit(app_db, retake, "cd.c", right=False)
    assert t.post(f"/api/exams/{retake}/close").status == 200 and t.post(f"/api/exams/{retake}/release").status == 200
    assert one("SELECT exam_id FROM grades WHERE user_id=? AND course_id=? AND exam_id IS NOT NULL", (sid, world["course"]))["exam_id"] == retake
    r = office.put(f"/api/exams/{first}/scores/{sid}", {"score": 45, "reason": "apellyasiya", "order_no": "12/4"})
    assert r.status == 409                                         # CR-7: the journal holds the retake's score now


def test_sec6_py9_an_appeal_counts_once_and_a_hand_score_is_rounded(app_db, world):
    office, t = app_db.client("office"), world["teacher"]
    sid = world["ids"]["cd.a"]
    eid = new_exam(world)
    sit(app_db, eid, "cd.a", right=False)
    assert t.post(f"/api/exams/{eid}/close").status == 200 and t.post(f"/api/exams/{eid}/release").status == 200
    assert office.post(f"/api/exams/{eid}/statements/{world['group']}/close").status == 200
    rejected = run("INSERT INTO requests(type_code,student_id,data,status,created_at) VALUES('grade_appeal',?,'{}','rejected','x')", (sid,))
    good = run("INSERT INTO requests(type_code,student_id,data,status,created_at) VALUES('grade_appeal',?,'{}','submitted','x')", (sid,))
    assert office.put(f"/api/exams/{eid}/scores/{sid}", {"score": 20, "reason": "apellyasiya", "appeal_id": rejected}).status == 400
    assert office.put(f"/api/exams/{eid}/scores/{sid}", {"score": 20, "reason": "apellyasiya", "order_no": "yox"}).status == 400
    r = office.put(f"/api/exams/{eid}/scores/{sid}", {"score": 16.94, "reason": "apellyasiya", "appeal_id": good})
    assert r.status == 200 and r.json["score"] == 16.9
    assert office.put(f"/api/exams/{eid}/scores/{sid}", {"score": 30, "reason": "yenə", "appeal_id": good}).status == 400   # used


def test_sec4_a_department_head_outside_the_course_sees_no_results(app_db, world):
    admin = world["admin"]
    fac = one("SELECT id FROM faculties LIMIT 1")["id"]
    other = run("INSERT INTO departments(faculty_id,code,name,created_at,updated_at) VALUES(?,'CD-DEP','Başqa kafedra','x','x')", (fac,))
    run("UPDATE courses SET department_id=NULL WHERE id=?", (world["course"],))
    leader = app_db.client("leader").user["id"]
    admin.post(f"/api/admin/users/{leader}/roles", {"role": "dept_head", "scope_type": "department", "scope_id": other})
    head = app_db.client("leader")
    assert head.post("/api/me/role", {"role": "dept_head"}).status == 200
    eid = new_exam(world)
    assert world["teacher"].post(f"/api/exams/{eid}/close").status == 200
    assert head.get(f"/api/exams/{eid}/results").status == 404
    assert head.get(f"/api/courses/{world['course']}/exam-results").status == 404
    assert head.get(f"/api/exams/{eid}/manage").status == 404, "the roster and the raw scores before release (security review)"
    assert head.get(f"/api/courses/{world['course']}/exams").status == 404


def test_tm19_moving_the_student_keeps_the_statement_lock(app_db, world):
    office, t = app_db.client("office"), world["teacher"]
    sid = world["ids"]["cd.b"]
    eid = new_exam(world)
    sit(app_db, eid, "cd.b")
    assert t.post(f"/api/exams/{eid}/close").status == 200 and t.post(f"/api/exams/{eid}/release").status == 200
    assert office.post(f"/api/exams/{eid}/statements/{world['group']}/close").status == 200
    other = one("SELECT id FROM study_groups WHERE id<>? AND faculty_id=(SELECT faculty_id FROM study_groups WHERE id=?) LIMIT 1",
                (world["group"], world["group"]))
    run("UPDATE users SET group_id=? WHERE id=?", (other["id"], sid))
    try:
        key = one("SELECT component FROM grades WHERE user_id=? AND exam_id=?", (sid, eid))["component"]
        r = t.put(f"/api/journal/courses/{world['course']}/grades", {"cells": [{"student_id": sid, "component": key, "score": 10}], "reason": "köçdü"})
        assert r.status == 403
    finally:
        run("UPDATE users SET group_id=? WHERE id=?", (world["group"], sid))


# ---------------------------------------------------------------- D. questions in use, the pool, exceptions, refusals
def test_cr3_tm4_an_exam_question_is_frozen_while_its_exam_is_open(app_db, world):
    t = world["teacher"]
    eid = new_exam(world, count=2)
    qid = world["qids"][0]
    assert t.put(f"/api/questions/{qid}", {"answer": "7"}).status == 409
    assert t.delete(f"/api/questions/{qid}").status == 409
    assert t.post(f"/api/exams/{eid}/close").status == 200
    assert t.put(f"/api/questions/{qid}", {"status": "draft"}).status == 400        # never back to draft: the purpose stays
    assert t.put(f"/api/questions/{qid}", {"text": "yoxlama sualı 0 (düzəliş)"}).status == 200
    assert q("SELECT 1 FROM audit WHERE action='exam_question_changed' AND detail LIKE ?", (f"#{qid}%",))


def test_tm4_opening_checks_the_pool_again(app_db, world):
    t = world["teacher"]
    r = t.post(f"/api/courses/{world['course']}/exams", {"title": "Böyük plan", "day": store.now().date().isoformat(), "start": "00:01",
                                                         "end": "23:59", "duration_min": 60, "plan": [{"count": 4}]})
    eid = r.json["id"]
    run("UPDATE questions SET status='draft' WHERE id=?", (world["qids"][3],))
    try:
        assert t.post(f"/api/exams/{eid}/open").status == 400
    finally:
        run("UPDATE questions SET status='approved' WHERE id=?", (world["qids"][3],))


def test_cr4_tm11_an_exception_needs_an_open_exam_and_refusals_are_capped(app_db, world):
    office, t = app_db.client("office"), world["teacher"]
    r = t.post(f"/api/courses/{world['course']}/exams", {"title": "Qaralama", "day": store.now().date().isoformat(), "start": "00:01",
                                                         "end": "23:59", "duration_min": 60, "plan": [{"count": 2}]})
    draft = r.json["id"]
    assert office.post(f"/api/exams/{draft}/roster/{world['ids']['cd.a']}/exception", {"reason": "xəstə idi"}).status == 409
    eid = new_exam(world)
    outsider = app_db.client("student")
    for _ in range(15):
        assert outsider.post(f"/api/exams/{eid}/enter").status == 403
    assert one("SELECT COUNT(*) AS n FROM exam_events WHERE exam_id=? AND kind='session.refused'", (eid,))["n"] == domain.REFUSAL_CAP


# ---------------------------------------------------------------- E. sessions and SEB
def test_tm7_leaving_is_refused_while_the_attempt_runs(app_db, world):
    eid = new_exam(world)
    s = sit(app_db, eid, "cd.a", submit=False)
    assert s.post(f"/api/exams/{eid}/leave").status == 409
    assert s.post(f"/api/exams/{eid}/submit").status == 200
    assert s.post(f"/api/exams/{eid}/leave").status == 200


def test_tm18_an_extended_attempt_comes_back_in_after_the_window(app_db, world):
    eid = new_exam(world)
    sid = world["ids"]["cd.b"]
    sit(app_db, eid, "cd.b", submit=False)
    run("UPDATE exams SET closes_at='2000-01-01T00:00:00+00:00' WHERE id=?", (eid,))
    run("UPDATE exam_attempts SET deadline_at='2999-01-01T00:00:00+00:00' WHERE exam_id=? AND student_id=?", (eid, sid))
    s = app_db.client()
    assert s.post("/api/auth/demo", {"role": "student", "user": "cd.b"}).status == 200
    assert s.post(f"/api/exams/{eid}/enter").status == 200


def test_py7_sec8_a_non_ascii_hash_is_a_logged_refusal_and_unlock_needs_an_open_exam(app_db, world):
    t = world["teacher"]
    eid = new_exam(world, protection="seb")
    s = app_db.client()
    assert s.post("/api/auth/demo", {"role": "student", "user": "cd.c"}).status == 200
    nonce = s.post(f"/api/exams/{eid}/enter").json["url"].split("n=")[1]
    r = s.post(f"/api/exams/{eid}/seb-verify?n={nonce}", {"url": "https://x.test/?n=" + nonce, "config_key_hash": "ə" * 64})
    assert r.status == 403
    assert one("SELECT COUNT(*) AS n FROM exam_events WHERE exam_id=? AND kind='seb.refused'", (eid,))["n"] == 1
    assert app_db.client().get(f"/exam/{eid}/config.seb?k=%C9%99").status == 404           # "ə": 404, not a 400
    assert t.post(f"/api/exams/{eid}/close").status == 200
    assert t.post(f"/api/exams/{eid}/students/{world['ids']['cd.c']}/unlock", {"reason": "bağlıdan sonra"}).status == 409


def test_tm9_an_ordinary_browser_does_not_end_a_verified_seb_session(app_db, world):
    eid = new_exam(world, protection="seb")
    inside = app_db.client()
    assert inside.post("/api/auth/demo", {"role": "student", "user": "cd.a"}).status == 200
    nonce = inside.post(f"/api/exams/{eid}/enter").json["url"].split("n=")[1]
    c = db()
    try:
        key = service.seb_settings(store.row(c, "SELECT * FROM exams WHERE id=?", (eid,)))["key"]
    finally:
        c.close()
    target = f"/api/exams/{eid}/seb-verify?n={nonce}"
    sig = hashlib.sha256(f"{common.BASE_URL['value']}{target}{key}".encode()).hexdigest()
    assert inside.post(target, headers={"X-SafeExamBrowser-ConfigKeyHash": sig}).status == 200
    outside = app_db.client()
    assert outside.post("/api/auth/demo", {"role": "student", "user": "cd.a"}).status == 200
    assert outside.post(f"/api/exams/{eid}/enter").status == 200
    assert inside.post(f"/api/exams/{eid}/start").status == 200                     # the SEB session still works


# ---------------------------------------------------------------- F. the job runner
def test_py2_a_failed_cycle_does_not_wedge_the_runner(app_db, monkeypatch):
    c = db()
    calls: list = []
    monkeypatch.setattr(jobs, "REGISTRY", {"t.cd.ok": jobs.Job("t.cd.ok", timedelta(minutes=1), lambda c_: calls.append(1))})
    c.execute("BEGIN")
    c.execute("UPDATE job_lease SET holder=holder")                                 # a transaction left open by a failure
    stop = iter([False] * 4 + [True] * 10)                                          # the first wait, then three cycles
    jobs.loop(lambda: c, "t.cd", every=0.0, stop=lambda: next(stop), log=lambda m: None)
    assert calls, "a later cycle ran"


def test_cr8_a_run_left_running_by_a_dead_runner_does_not_block(app_db):
    c = db()
    jobs.periodic("t.cd.stale", timedelta(minutes=1), lambda c_: "ok")
    try:
        c.execute("INSERT INTO job_runs(name, started_at, status, holder) VALUES('t.cd.stale', ?, 'running', 'dead:1')",
                  (clock.now().isoformat(timespec="seconds"),))
        c.commit()
        assert jobs.run_due(c, "alive:2", names=["t.cd.stale"]) == [("t.cd.stale", "ok")]
    finally:
        jobs.REGISTRY.pop("t.cd.stale", None)
        c.close()
