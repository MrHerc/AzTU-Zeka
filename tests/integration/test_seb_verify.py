"""Safe Exam Browser verification on a real server (tasks/todo.md, Task 28): in SEB mode an attempt does not start with a
wrong or missing hash and an unverified session gets 403 on the attempt's question and answer routes; a hash caught in
one session is refused in another; with PUBLIC_URL different from the listening address (https://zeka.test) and a URL
with %2F and two parameters the right hash is accepted and one computed on http://127.0.0.1:port is refused."""
import hashlib
import re

import pytest

from zeka.legacy import common, store
from zeka.modules.exam import service

PUBLIC = "https://zeka.test"


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


@pytest.fixture
def public(monkeypatch):
    """The portal published at https://zeka.test while it listens on 127.0.0.1. Set after signing in: with an https
    address the session cookie is Secure and the test client, on http, would not send it back."""
    return lambda: monkeypatch.setitem(common.BASE_URL, "value", PUBLIC)


@pytest.fixture(scope="module")
def world(app_db):
    admin, teacher = app_db.client("admin"), app_db.client("teacher")
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    gid = q("SELECT group_id FROM users WHERE id=?", (app_db.client("student").user["id"],))[0]["group_id"]
    cid = admin.post("/api/directory/courses", {"code": "SB-101", "name": "SEB sınağı", "credits": 5, "term_id": term["id"],
                                                "teacher_id": teacher.user["id"]}).json["id"]
    sid = admin.post("/api/directory/users", {"username": "sb.a", "full_name": "SEB Tələbə", "role": "student", "group_id": gid,
                                              "student_no": "SB.A"}).json["id"]
    admin.post(f"/api/directory/courses/{cid}/enrollments", {"user_id": sid})
    for i in range(2):
        run("INSERT INTO questions(course_id,qtype,text,options,answer,unit,explanation,difficulty,topic,status,purpose,created_at) "
            "VALUES(?,'numeric',?,'[]',?,'','izah','Asan','Om','approved','exam','x')", (cid, f"seb sualı {i}", str(i)))
    r = teacher.post(f"/api/courses/{cid}/exams", {"title": "SEB imtahanı", "day": store.now().date().isoformat(), "start": "00:01",
                                                   "end": "23:59", "duration_min": 60, "plan": [{"count": 2}], "protection": "seb"})
    assert r.status == 200, r.text
    eid = r.json["id"]
    assert teacher.post(f"/api/exams/{eid}/open").status == 200
    return {"exam": eid, "teacher": teacher}


def key(eid):
    c = store.connect()
    try:
        return service.seb_settings(store.row(c, "SELECT * FROM exams WHERE id=?", (eid,)))
    finally:
        c.close()


def entered(app_db, eid):
    s = app_db.client()
    assert s.post("/api/auth/demo", {"role": "student", "user": "sb.a"}).status == 200
    r = s.post(f"/api/exams/{eid}/enter")
    assert r.status == 200 and r.json["seb"] is True, r.text
    return s, re.search(r"[?&]n=([^&]+)", r.json["url"]).group(1)


def header(base, target, k):
    return {"X-SafeExamBrowser-ConfigKeyHash": hashlib.sha256(f"{base}{target}{k}".encode()).hexdigest()}


def test_the_config_file_is_served_with_its_token_only(app_db, world, public):
    public()
    st = key(world["exam"])
    r = app_db.client().get(st["download"])
    assert r.status == 200 and r.headers["Content-Type"] == "application/seb" and b"<plist" in r.body
    from zeka.modules.exam import seb
    assert seb.config_key(seb.read(r.body)) == st["key"]
    assert app_db.client().get(f"/exam/{world['exam']}/config.seb?k=wrong").status == 404
    m = world["teacher"].get(f"/api/exams/{world['exam']}/manage").json["exam"]["seb"]
    assert m["link"].startswith("sebs://zeka.test/exam/") and len(m["quit_password"]) == 8 and m["key"] == st["key"]


def test_without_a_right_hash_nothing_starts_and_the_header_hash_opens_it(app_db, world, public):
    eid = world["exam"]
    s, nonce = entered(app_db, eid)
    public()
    assert s.get(f"/api/exams/{eid}").status == 403
    assert s.post(f"/api/exams/{eid}/start").status == 403
    target = f"/api/exams/{eid}/seb-verify?n={nonce}&dir=a%2Fb"
    k = key(eid)["key"]
    assert s.post(target).status == 403                                               # no hash at all
    assert s.post(target, headers={"X-SafeExamBrowser-ConfigKeyHash": "0" * 64}).status == 403
    port_base = app_db.url                                                            # http://127.0.0.1:port
    assert s.post(target, headers=header(port_base, target, k)).status == 403          # the listening address does not count
    assert q("SELECT COUNT(*) AS n FROM exam_events WHERE exam_id=? AND kind='seb.refused'", (eid,))[0]["n"] >= 3
    r = s.post(target, headers=header(PUBLIC, target, k))
    assert r.status == 200 and r.json["seb"] is True, r.text
    r = s.post(f"/api/exams/{eid}/start")
    assert r.status == 200 and len(r.json["questions"]) == 2


def test_a_hash_caught_in_one_session_is_refused_in_another(app_db, world, public):
    eid = world["exam"]
    s1, n1 = entered(app_db, eid)
    public()
    k = key(eid)["key"]
    t1 = f"/api/exams/{eid}/seb-verify?n={n1}"
    caught = header(PUBLIC, t1, k)
    assert s1.post(t1, headers=caught).status == 200
    common.BASE_URL["value"] = app_db.url                                              # sign in on the plain address ...
    s2, n2 = entered(app_db, eid)                                                      # entering again ends the first session
    public()                                                                           # ... and verify on the public one
    assert n2 != n1
    assert s2.post(t1, headers=caught).status == 403                                   # the old value is not this session's
    assert s2.post(f"/api/exams/{eid}/seb-verify?n={n2}", headers=caught).status == 403
    assert s2.get(f"/api/exams/{eid}").status == 403                                   # unverified: no questions
    page = f"{PUBLIC}/static/exam.html?exam={eid}&n={n2}"
    r = s2.post(f"/api/exams/{eid}/seb-verify", {"url": page, "config_key_hash": hashlib.sha256(f"{page}{k}".encode()).hexdigest()})
    assert r.status == 200, r.text                                                     # the JS API path
    assert s2.get(f"/api/exams/{eid}").status == 200


def test_an_open_exam_needs_no_seb(app_db, world):
    e = q("SELECT protection FROM exams WHERE id=?", (world["exam"],))[0]
    assert e["protection"] == "seb"
    assert app_db.client().get("/exam/999999/config.seb?k=x").status == 404
