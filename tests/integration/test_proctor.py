"""The proctor panel (tasks/todo.md, Task 29): the exam's network list at entry and on every exam request (behind one
trusted proxy the right-most X-Forwarded-For address counts; without a proxy the header is ignored), the proctor's
actions (each needs a reason and is in the exam's log, only for a student on the exam's roster), who reaches the board,
and a student's change of state on the board at the next poll."""
import time

import pytest

from zeka.core import security
from zeka.legacy import store
from zeka.modules.exam import domain


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


def student_as(app_db, username):
    s = app_db.client()
    assert s.post("/api/auth/demo", {"role": "student", "user": username}).status == 200
    return s


def events(eid, kind):
    return [e for e in q("SELECT * FROM exam_events WHERE exam_id=? ORDER BY seq", (eid,)) if e["kind"] == kind]


@pytest.fixture(scope="module")
def world(app_db):
    admin, teacher = app_db.client("admin"), app_db.client("teacher")
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    gid = q("SELECT group_id FROM users WHERE id=?", (app_db.client("student").user["id"],))[0]["group_id"]
    cid = admin.post("/api/directory/courses", {"code": "PX-101", "name": "Nəzarət sınağı", "credits": 5, "term_id": term["id"],
                                                "teacher_id": teacher.user["id"]}).json["id"]
    ids = {}
    for n in ("px.a", "px.b", "px.c", "px.d", "px.out"):
        ids[n] = admin.post("/api/directory/users", {"username": n, "full_name": f"Nəzarət {n}", "role": "student", "group_id": gid,
                                                     "student_no": n.upper()}).json["id"]
        if n != "px.out":
            admin.post(f"/api/directory/courses/{cid}/enrollments", {"user_id": ids[n]})
    for i in range(6):
        run("INSERT INTO questions(course_id,qtype,text,options,answer,unit,explanation,difficulty,topic,status,purpose,created_at) "
            "VALUES(?,'numeric',?,'[]',?,'','izah','Asan','Om','approved','exam','x')", (cid, f"nəzarət sualı {i}", str(i)))
    return {"course": cid, "ids": ids, "teacher": teacher, "admin": admin}


def open_exam(world, **kw):
    body = {"title": "Nəzarətli imtahan", "day": store.now().date().isoformat(), "start": "00:01", "end": "23:59", "duration_min": 60,
            "plan": [{"count": 3}], **kw}
    r = world["teacher"].post(f"/api/courses/{world['course']}/exams", body)
    assert r.status == 200, r.text
    eid = r.json["id"]
    assert world["teacher"].post(f"/api/exams/{eid}/open").status == 200
    return eid


def started(app_db, world, username, eid):
    s = student_as(app_db, username)
    assert s.post(f"/api/exams/{eid}/enter").status == 200
    r = s.post(f"/api/exams/{eid}/start")
    assert r.status == 200, r.text
    return s, r.json["questions"][0]["id"]


def attempt(eid, sid):
    return q("SELECT * FROM exam_attempts WHERE exam_id=? AND student_id=?", (eid, sid))[0]


def test_network_list_at_entry_and_on_every_exam_request(app_db, world, monkeypatch):
    eid = open_exam(world, allowed_cidrs=["10.0.0.0/24"])
    s = student_as(app_db, "px.a")                                     # signed in before the proxy is configured
    monkeypatch.setattr(security.CFG, "proxy_hops", 1)
    xff = lambda ip: {"X-Forwarded-For": ip}                          # noqa: E731

    r = s.post(f"/api/exams/{eid}/enter", headers=xff("203.0.113.9"))
    assert r.status == 403
    assert events(eid, "session.refused")[-1]["data"] == '{"ip": "203.0.113.9", "reason": "network"}'

    assert s.post(f"/api/exams/{eid}/enter", headers=xff("10.0.0.5")).status == 200
    r = s.post(f"/api/exams/{eid}/start", headers=xff("10.0.0.5"))
    assert r.status == 200, r.text
    qid = r.json["questions"][0]["id"]
    put = lambda ip: s.put(f"/api/exams/{eid}/answers/{qid}", {"value": "1"}, headers=xff(ip))  # noqa: E731

    assert put("10.0.0.5").status == 200                              # on the list: allowed
    assert put("203.0.113.9").status == 403                           # off the list: refused and logged
    assert '"ip": "203.0.113.9"' in events(eid, "net.refused")[-1]["data"]
    assert put("10.0.0.7, 203.0.113.9").status == 403                 # a forged inner address: the right-most one counts
    assert '"ip": "203.0.113.9"' in events(eid, "net.refused")[-1]["data"]
    assert len(events(eid, "net.refused")) == 2

    assert put("10.0.0.9").status == 200                              # a change on the list: a board event, not a refusal
    assert events(eid, "net.changed")[-1]["data"] == '{"from": "10.0.0.5", "to": "10.0.0.9"}'
    assert put("10.0.0.9").status == 200 and len(events(eid, "net.changed")) == 1

    monkeypatch.setattr(security.CFG, "proxy_hops", 0)                 # no proxy: the header is ignored, the peer counts
    assert put("10.0.0.9").status == 403
    assert '"ip": "127.0.0.1"' in events(eid, "net.refused")[-1]["data"]


def test_every_action_needs_a_reason_is_logged_and_works(app_db, world):
    eid = open_exam(world)
    sid = world["ids"]["px.b"]
    s, qid = started(app_db, world, "px.b", eid)
    t = world["teacher"]
    act = lambda action, **b: t.post(f"/api/exams/{eid}/students/{sid}/{action}", b)  # noqa: E731

    for action in ("extend", "pause", "resume", "end", "reopen", "unlock"):
        assert act(action, minutes=5).status == 400, action          # no reason
    assert act("extend", reason="kompüter donub").status == 400       # minutes required
    assert act("extend", reason="kompüter donub", minutes=0).status == 400
    assert act("explode", reason="niyə də yox").status == 400
    assert act("resume", reason="dayanmayıb").status == 409            # wrong state

    before = attempt(eid, sid)
    assert act("pause", reason="otaqda səs-küy").status == 200
    a = attempt(eid, sid)
    assert a["status"] == "paused" and a["paused_at"]
    r = s.put(f"/api/exams/{eid}/answers/{qid}", {"value": "1"})
    assert r.status == 409 and "dayandırılıb" in r.json["error"]     # no answers while paused, and the page is told why
    left = s.get(f"/api/exams/{eid}").json["attempt"]["remaining_s"]
    time.sleep(1.2)
    assert s.get(f"/api/exams/{eid}").json["attempt"]["remaining_s"] == left, "a paused clock stands still"

    assert act("resume", reason="səs-küy kəsildi").status == 200
    a = attempt(eid, sid)
    assert a["status"] == "in_progress" and a["paused_at"] is None and a["deadline_at"] > before["deadline_at"]
    assert s.put(f"/api/exams/{eid}/answers/{qid}", {"value": "1"}).status == 200

    deadline = a["deadline_at"]
    assert act("extend", reason="elektrik kəsildi", minutes=10).status == 200
    from datetime import datetime, timedelta
    assert datetime.fromisoformat(attempt(eid, sid)["deadline_at"]) == datetime.fromisoformat(deadline) + timedelta(minutes=10)

    assert act("end", reason="kənar material").status == 200
    assert attempt(eid, sid)["status"] == "submitted"
    assert s.put(f"/api/exams/{eid}/answers/{qid}", {"value": "2"}).status == 409

    assert act("reopen", reason="səhvən bitirilib", minutes=15).status == 200
    a = attempt(eid, sid)
    assert a["status"] == "in_progress" and a["submitted_at"] is None

    username = "px.b"
    run("INSERT INTO login_blocks(account,client,failures,first,until) VALUES(?,'*',9,0,9999999999)", (username,))
    run("UPDATE users SET failed_count=7, locked_until='2999-01-01T00:00:00' WHERE id=?", (sid,))
    assert act("unlock", reason="parolu səhv yazıb").status == 200
    assert not q("SELECT 1 FROM login_blocks WHERE account=?", (username,))
    assert q("SELECT failed_count, locked_until FROM users WHERE id=?", (sid,))[0] == {"failed_count": 0, "locked_until": None}

    for kind in ("pause", "resume", "extend", "end", "reopen", "unlock"):
        ev = events(eid, f"proctor.{kind}")
        assert len(ev) == 1 and ev[0]["actor_id"] == t.user["id"] and ev[0]["student_id"] == sid, kind
        assert '"reason": ' in ev[0]["data"], kind

    # a student who is not on this exam's roster: nothing happens to them
    out = world["ids"]["px.out"]
    assert t.post(f"/api/exams/{eid}/students/{out}/unlock", {"reason": "kənar tələbə"}).status == 404


def test_only_assigned_proctors_reach_the_board(app_db, world):
    eid = open_exam(world)
    admin, teacher = world["admin"], world["teacher"]
    office = app_db.client("office")
    assert admin.post(f"/api/admin/users/{office.user['id']}/roles", {"role": "proctor"}).status == 200
    assert office.post("/api/me/role", {"role": "proctor"}).status == 200
    assert office.get(f"/api/exams/{eid}/board").status == 404           # not assigned yet
    assert office.post(f"/api/exams/{eid}/students/{world['ids']['px.c']}/unlock", {"reason": "kilid açılsın"}).status == 404
    assert eid not in [e["id"] for e in office.get("/api/proctor/exams").json]

    name = q("SELECT username FROM users WHERE id=?", (office.user["id"],))[0]["username"]
    assert teacher.put(f"/api/exams/{eid}/proctors", {"usernames": ["px.c"]}).status == 400   # a student is not a proctor
    r = teacher.put(f"/api/exams/{eid}/proctors", {"usernames": [name]})
    assert r.status == 200, r.text
    assert [p["username"] for p in r.json["proctors"]] == [name]
    assert events(eid, "proctors.set")
    assert eid in [e["id"] for e in office.get("/api/proctor/exams").json]
    b = office.get(f"/api/exams/{eid}/board")
    assert b.status == 200 and {x["student_id"] for x in b.json["students"]} >= {world["ids"]["px.c"]}
    assert office.post(f"/api/exams/{eid}/students/{world['ids']['px.c']}/unlock", {"reason": "kilid açılsın"}).status == 200
    assert app_db.client("student").get(f"/api/exams/{eid}/board").status == 403
    # the course's teacher and the administrator see the open exam on their proctor page without an assignment
    assert eid in [e["id"] for e in teacher.get("/api/proctor/exams").json]
    assert eid in [e["id"] for e in admin.get("/api/proctor/exams").json]


def test_a_change_of_state_is_on_the_board_at_the_next_poll(app_db, world, monkeypatch):
    eid = open_exam(world)
    sid = world["ids"]["px.d"]
    t = world["teacher"]
    seq = t.get(f"/api/exams/{eid}/board").json["seq"]
    s, _ = started(app_db, world, "px.d", eid)
    t0 = time.monotonic()
    s.post(f"/api/exams/{eid}/signals", {"kind": "blur"})
    s.post(f"/api/exams/{eid}/signals", {"kind": "fullscreen_exit"})
    assert s.post(f"/api/exams/{eid}/signals", {"kind": "screenshot"}).status == 400
    assert s.post(f"/api/exams/{eid}/submit").status == 200
    b = t.get(f"/api/exams/{eid}/board?after={seq}").json
    assert time.monotonic() - t0 < 10
    me = next(x for x in b["students"] if x["student_id"] == sid)
    assert me["attempt"] == "submitted" and me["online"] and me["seen_s"] is not None
    assert me["flags"] == {"client.blur": 1, "client.fullscreen_exit": 1}
    kinds = [e["kind"] for e in b["events"]]
    assert {"session.entered", "attempt.started", "client.blur", "attempt.submitted"} <= set(kinds)
    assert all(e["seq"] > seq for e in b["events"]) and b["seq"] == b["events"][-1]["seq"]
    assert t.get(f"/api/exams/{eid}/board?after={b['seq']}").json["events"] == []

    monkeypatch.setattr(domain, "SIGNAL_CAP", 2)                         # a looping page cannot flood the log
    assert s.post(f"/api/exams/{eid}/signals", {"kind": "reconnect"}).json["kept"] is False
