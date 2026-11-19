"""The closing protocol and the group statement (tasks/todo.md, Task 30): closing issues a QR protocol whose verification
page shows the same root as the chain and as the e-mail to the teacher and the dean's office; after release the office
closes a group's statement (a QR document); from then on only the office changes an exam score, with a reason and a
grade appeal or an order number, in the grade journal, while the attempt itself stays as graded."""
import json

import pytest

from zeka.legacy import store
from zeka.modules.exam import service


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
    admin, teacher, office = app_db.client("admin"), app_db.client("teacher"), app_db.client("office")
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    gid = q("SELECT group_id FROM users WHERE id=?", (app_db.client("student").user["id"],))[0]["group_id"]
    cid = admin.post("/api/directory/courses", {"code": "ST-101", "name": "Cədvəl sınağı", "credits": 5, "term_id": term["id"],
                                                "teacher_id": teacher.user["id"]}).json["id"]
    ids = {}
    for n in ("st.a", "st.b"):
        ids[n] = admin.post("/api/directory/users", {"username": n, "full_name": f"Cədvəl {n}", "role": "student", "group_id": gid,
                                                     "student_no": n.upper()}).json["id"]
        admin.post(f"/api/directory/courses/{cid}/enrollments", {"user_id": ids[n]})
    for i in range(3):
        run("INSERT INTO questions(course_id,qtype,text,options,answer,unit,explanation,difficulty,topic,status,purpose,created_at) "
            "VALUES(?,'numeric',?,'[]',?,'','izah','Asan','Om','approved','exam','x')", (cid, f"cədvəl sualı {i}", str(i)))
    run("UPDATE users SET email='teacher@aztu.test' WHERE id=?", (teacher.user["id"],))
    run("UPDATE users SET email='office@aztu.test' WHERE id=?", (office.user["id"],))
    return {"course": cid, "ids": ids, "teacher": teacher, "office": office, "group": gid}


def closed_exam(app_db, world):
    t = world["teacher"]
    eid = t.post(f"/api/courses/{world['course']}/exams", {"title": "Cədvəlli imtahan", "day": store.now().date().isoformat(), "start": "00:01",
                                                           "end": "23:59", "duration_min": 60, "plan": [{"count": 3}]}).json["id"]
    assert t.post(f"/api/exams/{eid}/open").status == 200
    for n in ("st.a", "st.b"):
        s = app_db.client()
        assert s.post("/api/auth/demo", {"role": "student", "user": n}).status == 200
        assert s.post(f"/api/exams/{eid}/enter").status == 200
        for x in s.post(f"/api/exams/{eid}/start").json["questions"]:
            assert s.put(f"/api/exams/{eid}/answers/{x['id']}", {"value": "1"}).status == 200
        assert s.post(f"/api/exams/{eid}/submit").status == 200
    assert t.post(f"/api/exams/{eid}/close").status == 200
    return eid


def head(eid):
    return q("SELECT seq, hash FROM exam_events WHERE exam_id=? ORDER BY seq DESC LIMIT 1", (eid,))[0]


def test_the_protocol_verifies_and_shows_the_root_that_was_e_mailed(app_db, world, monkeypatch):
    monkeypatch.setenv("ZEKA_SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("ZEKA_SMTP_TLS", "none")
    run("DELETE FROM outbox")
    eid = closed_exam(app_db, world)
    root = head(eid)["hash"]
    doc = q("SELECT d.* FROM documents d JOIN exams e ON e.protocol_id=d.id WHERE e.id=?", (eid,))[0]
    data = json.loads(doc["data"])
    assert (doc["kind"], data["root"], data["seq"]) == ("exam_protocol", root, head(eid)["seq"])
    assert data["attempts"]["started"] == 2 and data["roster"]["eligible"] == 2
    page = app_db.client().get(f"/verify/{doc['verify_code']}")
    assert page.status == 200 and root in page.text
    mails = q("SELECT * FROM outbox WHERE template='exam.root' ORDER BY address")
    assert [m["address"] for m in mails] == ["office@aztu.test", "teacher@aztu.test"]
    assert all(json.loads(m["params"])["root"] == root for m in mails)
    link = world["teacher"].post(f"/api/documents/{doc['id']}/link")
    assert link.status == 200 and world["teacher"].get(link.json["url"]).status == 200
    assert app_db.client("student").post(f"/api/documents/{doc['id']}/link").status == 404


def test_after_the_office_closes_the_statement_only_the_office_changes_a_score(app_db, world):
    eid = closed_exam(app_db, world)
    t, office = world["teacher"], world["office"]
    assert t.post(f"/api/exams/{eid}/release").status == 200
    sid, gid = world["ids"]["st.a"], world["group"]
    key = q("SELECT component FROM grades WHERE user_id=? AND course_id=? AND exam_id=?", (sid, world["course"], eid))[0]["component"]
    # before the statement is closed the teacher still corrects the exam cell in the journal, with a reason
    assert t.put(f"/api/journal/courses/{world['course']}/grades", {"cells": [{"student_id": sid, "component": key, "score": 30}],
                                                                   "reason": "yoxlamada səhv"}).status == 200
    assert office.put(f"/api/exams/{eid}/scores/{sid}", {"score": 40, "reason": "apellyasiya", "order_no": "15/3"}).status == 409

    assert t.post(f"/api/exams/{eid}/statements/{gid}/close").status == 403            # the office closes it
    r = office.post(f"/api/exams/{eid}/statements/{gid}/close")
    assert r.status == 200, r.text
    g = next(x for x in r.json["groups"] if x["group_id"] == gid)
    assert g["closed"] and g["reg_no"]
    assert office.post(f"/api/exams/{eid}/statements/{gid}/close").status == 409
    doc = q("SELECT * FROM documents WHERE id=?", (g["document_id"],))[0]
    assert json.loads(doc["data"])["root"] in app_db.client().get(f"/verify/{doc['verify_code']}").text

    r = t.put(f"/api/journal/courses/{world['course']}/grades", {"cells": [{"student_id": sid, "component": key, "score": 20}], "reason": "yenə"})
    assert r.status == 403                                                               # locked for the teacher
    assert t.put(f"/api/exams/{eid}/scores/{sid}", {"score": 40, "reason": "x", "order_no": "1"}).status == 403
    assert office.put(f"/api/exams/{eid}/scores/{sid}", {"score": 40, "order_no": "15/3"}).status == 400          # no reason
    assert office.put(f"/api/exams/{eid}/scores/{sid}", {"score": 40, "reason": "apellyasiya"}).status == 400     # no basis
    assert office.put(f"/api/exams/{eid}/scores/{sid}", {"score": 40, "reason": "apellyasiya", "appeal_id": 999999}).status == 400
    assert office.put(f"/api/exams/{eid}/scores/{sid}", {"score": 99, "reason": "apellyasiya", "order_no": "15/3"}).status == 400
    raw = q("SELECT score FROM exam_attempts WHERE exam_id=? AND student_id=?", (eid, sid))[0]["score"]
    r = office.put(f"/api/exams/{eid}/scores/{sid}", {"score": 40, "reason": "apellyasiya komissiyası", "order_no": "15/3"})
    assert r.status == 200, r.text
    cell = q("SELECT * FROM grades WHERE user_id=? AND course_id=? AND component=?", (sid, world["course"], key))[0]
    assert (cell["score"], cell["source"], cell["status"]) == (40.0, "appeal", "published")
    log = q("SELECT * FROM grade_changes WHERE user_id=? AND course_id=? ORDER BY id DESC", (sid, world["course"]))[0]
    assert (log["old_score"], log["new_score"], log["changed_by"]) == (30.0, 40.0, office.user["id"]) and "əmr № 15/3" in log["reason"]
    assert q("SELECT score FROM exam_attempts WHERE exam_id=? AND student_id=?", (eid, sid))[0]["score"] == raw
    c = store.connect()
    try:
        assert service.verify(c, eid)["problems"] == []
    finally:
        c.close()
