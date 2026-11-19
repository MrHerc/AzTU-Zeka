"""E-service honesty (tasks/todo.md, Task 46): each step of a request is done only by the role it is assigned to, within that
role's scope; `issue` completes only the last step and runs the type's effect in the same transaction; a type without an
effect answers from one factual template; prod offers only the types the administrator opened."""
import base64
import json
import sqlite3
import urllib.parse
from datetime import date, timedelta

import pytest

from zeka.core import config, i18n, migrate, perms
from zeka.legacy import store
from zeka.legacy.r_services import EFFECTS, UNITS

SEED = json.loads((store.CONTENT / "seed.json").read_text(encoding="utf-8"))
TYPES = {t["code"]: t for t in SEED["request_types"]}
SEARCH = "/api/search?q=" + urllib.parse.quote("ərizə")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
LEAVE_ORDER = {"order_no": "46-AM", "order_date": (store.now().date() - timedelta(days=1)).isoformat()}


def b64(data):
    return base64.b64encode(data).decode()


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


def uid(username):
    return q("SELECT id FROM users WHERE username=?", (username,))[0]["id"]


def demo_student(app_db, nth):
    """The nth synthetic student of the demo, signed in through the demo storyline login."""
    username = q("SELECT username FROM users WHERE role='student' AND synthetic=1 ORDER BY id LIMIT 1 OFFSET ?", (nth,))[0]["username"]
    c = app_db.client()
    assert c.post("/api/auth/demo", {"role": "student", "user": username}).status == 200
    c.user = {"id": uid(username)}
    return c


def acting(app_db, role):
    """The demo teacher acting in a role granted to it (a department head of one course, or another office)."""
    c = app_db.client("teacher")
    assert c.post("/api/me/role", {"role": role}).status == 200, role
    return c


@pytest.fixture(scope="module")
def course(app_db):
    sid = app_db.client("student").user["id"]
    return q("SELECT course_id FROM enrollments WHERE user_id=? ORDER BY course_id LIMIT 1", (sid,))[0]["course_id"]


@pytest.fixture(scope="module")
def actors(app_db, registrar, course):
    """A client for each step role: the dean's office, the academic office (the same person, another role) and the head of
    the department of the course the requests name (the demo teacher with a grant scoped to that course)."""
    admin = app_db.client("admin")
    admin.post(f"/api/admin/users/{uid('rauf')}/roles", {"role": "dept_head", "scope_type": "course", "scope_id": course})
    admin.post(f"/api/admin/users/{uid('rauf')}/roles", {"role": "proctor"})              # a role with no step at all
    return {"office": app_db.client("office"), "academic_office": registrar, "dept_head": acting(app_db, "dept_head"),
            "proctor": acting(app_db, "proctor")}


def attach(client, rt, pdf):
    if not rt.get("attachments"):
        return []
    image = rt["attachments"]["accept"] == "image"
    f = client.post("/api/files", {"filename": "a.png" if image else "a.pdf", "content_b64": b64(PNG if image else pdf)})
    assert f.status == 200, f.text
    return [f.json["id"]]


def form(client, rt, course):
    """A valid form for the type, built from its fields (synthetic values)."""
    today = store.now().date()
    data = {}
    for f in rt["fields"]:
        kind = f["type"]
        if kind in ("radio", "select"):
            data[f["name"]] = f["options"][0]
        elif kind in ("text", "textarea"):
            data[f["name"]] = "Sınaq mətni"
        elif kind == "number":
            data[f["name"]] = "62"
        elif kind == "date":
            data[f["name"]] = (today + timedelta(days=3)).isoformat()
        elif kind == "course":
            data[f["name"]] = course
        elif kind == "courses":
            data[f["name"]] = [course]
        elif kind == "daterange" and f.get("future"):
            data[f["name"]] = {"from": (today + timedelta(days=5)).isoformat(), "to": (today + timedelta(days=6)).isoformat()}
        elif kind == "daterange":                               # an absence period: the student's absences of the last 60 days
            days = sorted({r["day"] for r in client.get("/api/attendance").json["records"] if r["status"] == "absent"})
            days = [d for d in days if date.fromisoformat(d) >= date.fromisoformat(days[-1]) - timedelta(days=59)]
            data[f["name"]] = {"from": days[0], "to": days[-1]}
        elif kind == "absences":
            p = data["period"]
            data[f["name"]] = [a["lesson_id"] for a in client.get(f"/api/me/absences?from={p['from']}&to={p['to']}").json]
            assert data[f["name"]], "the demo student has absences to excuse"
    return data


def file_request(client, code, course, pdf):
    rt = TYPES[code]
    r = client.post("/api/requests", {"type_code": code, "data": form(client, rt, course), "files": attach(client, rt, pdf)})
    assert r.status == 200, (code, r.text)
    return r.json


def counts(student_id):
    """The records a request's effect could change, for one student: nothing else may change for an effect `none`."""
    return {"documents": q("SELECT COUNT(*) n FROM documents WHERE holder_id=?", (student_id,))[0]["n"],
            "status_events": q("SELECT COUNT(*) n FROM student_status_events WHERE student_id=?", (student_id,))[0]["n"],
            "excused": q("SELECT COUNT(*) n FROM attendance WHERE user_id=? AND status='excused'", (student_id,))[0]["n"],
            "finals": q("SELECT COUNT(*) n, COALESCE(SUM(score), 0) s FROM final_grades WHERE user_id=?", (student_id,))[0]}


# ---------------------------------------------------------------- the content
def test_every_type_names_a_role_for_each_step_and_a_registered_effect():
    assert len(TYPES) == 13
    for code, rt in TYPES.items():
        assert len(rt["step_roles"]) == len(rt["steps"]), code
        assert all(r in perms.ROLES and r in UNITS and r not in ("admin", "student") for r in rt["step_roles"]), code
        assert rt["effect"] == "none" or rt["effect"] in EFFECTS, code
        assert bool(rt.get("document")) == (rt["effect"] in ("document.issue", "student_status.leave")), code
        if rt["effect"] == "none":
            assert not rt.get("answer"), f"{code}: a type without an effect must not carry a free answer text"


# ---------------------------------------------------------------- 1. the step's actor
def test_academic_leave_is_moved_on_only_by_each_step_s_role(app_db, actors, pdf_bytes):
    student = demo_student(app_db, 10)
    rid = file_request(student, "academic_leave", None, pdf_bytes)["id"]
    others = {"admin": app_db.client("admin"), "leader": app_db.client("leader"), "teacher": app_db.client("teacher"),
              "student": student, "proctor": actors["proctor"]}
    assert TYPES["academic_leave"]["step_roles"] == ["office", "academic_office", "academic_office"]
    assert actors["office"].post(f"/api/requests/{rid}/action", {"action": "issue"}).status == 409        # step 1 of 3
    for step, role in enumerate(TYPES["academic_leave"]["step_roles"]):
        wrong = {**others, **{r: c for r, c in actors.items() if r in ("office", "academic_office") and r != role}}
        for name, client in wrong.items():
            for action in ("approve", "issue", "reject"):
                r = client.post(f"/api/requests/{rid}/action", {"action": action, "note": "x"})
                assert r.status == 403, (step, name, action, r.status)
        # a department head has no step in this type: the request is not even visible to it (Task 13: 404)
        assert actors["dept_head"].post(f"/api/requests/{rid}/action", {"action": "approve"}).status == 404
        assert q("SELECT step FROM requests WHERE id=?", (rid,))[0]["step"] == step, "a refused act changes nothing"
        if step < 2:
            if step == 1:
                assert actors[role].post(f"/api/requests/{rid}/action", {"action": "issue"}).status == 409   # not the last step
            assert actors[role].post(f"/api/requests/{rid}/action", {"action": "approve"}).status == 200
    done = actors["academic_office"].post(f"/api/requests/{rid}/action", {"action": "issue", **LEAVE_ORDER,
                                                                             "effective_date": LEAVE_ORDER["order_date"]})
    assert done.status == 200 and done.json["status"] == "ready", done.text


def test_the_history_shows_each_step_s_actor_act_and_time(app_db, actors, pdf_bytes):
    student = demo_student(app_db, 11)
    rid = file_request(student, "academic_leave", None, pdf_bytes)["id"]
    actors["office"].post(f"/api/requests/{rid}/action", {"action": "approve"})
    actors["academic_office"].post(f"/api/requests/{rid}/action", {"action": "approve"})
    actors["academic_office"].post(f"/api/requests/{rid}/action", {"action": "issue", **LEAVE_ORDER, "effective_date": LEAVE_ORDER["order_date"]})
    seen = student.get(f"/api/requests/{rid}").json
    nigar = q("SELECT full_name FROM users WHERE username='nigar'")[0]["full_name"]
    assert [(e["action"], e["actor_role"]) for e in seen["events"]] == [("submitted", "student"), ("approved", "office"),
                                                                        ("approved", "academic_office"), ("issued", "academic_office")]
    assert all(e["actor"] and e["created_at"] for e in seen["events"]) and {e["actor"] for e in seen["events"][1:]} == {nigar}
    assert seen["step_roles"] == ["office", "academic_office", "academic_office"]


def test_a_step_s_notice_goes_only_to_that_role_within_its_scope(app_db, actors, pdf_bytes):
    admin = app_db.client("admin")
    faculty = q("SELECT id FROM faculties ORDER BY id LIMIT 1")[0]["id"]
    leyla, elcin, nigar = uid("leyla"), uid("elcin"), uid("nigar")
    g1 = admin.post(f"/api/admin/users/{leyla}/roles", {"role": "office", "scope_type": "faculty", "scope_id": faculty}).json["id"]
    g2 = admin.post(f"/api/admin/users/{elcin}/roles", {"role": "academic_office", "scope_type": "faculty", "scope_id": 9999}).json["id"]
    try:
        student = demo_student(app_db, 12)
        mark = q("SELECT COALESCE(MAX(id), 0) n FROM notifications")[0]["n"]
        rid = file_request(student, "academic_leave", None, pdf_bytes)["id"]

        def told(since):
            return {r["user_id"] for r in q("SELECT user_id FROM notifications WHERE link=? AND id>?", (f"/office/request/{rid}", since))}
        assert told(mark) == {nigar, leyla}                      # step 1: the faculty's dean's offices
        mark = q("SELECT MAX(id) n FROM notifications")[0]["n"]
        assert actors["office"].post(f"/api/requests/{rid}/action", {"action": "approve"}).status == 200
        assert told(mark) == {nigar}, "step 2 is the academic office's: not the dean's office, not another faculty's office"
    finally:
        admin.delete(f"/api/admin/users/{leyla}/roles/{g1}")
        admin.delete(f"/api/admin/users/{elcin}/roles/{g2}")


def test_a_dean_s_office_acts_only_for_its_faculty(app_db, actors, pdf_bytes):
    student = app_db.client("student")
    rid = file_request(student, "dormitory", None, pdf_bytes)["id"]
    keep = q("SELECT scope_id FROM role_grants WHERE user_id=? AND role='office'", (uid("nigar"),))[0]["scope_id"]
    run("UPDATE role_grants SET scope_id=9999 WHERE user_id=? AND role='office'", (uid("nigar"),))
    try:
        assert app_db.client("office").post(f"/api/requests/{rid}/action", {"action": "approve"}).status == 404
    finally:
        run("UPDATE role_grants SET scope_id=? WHERE user_id=? AND role='office'", (keep, uid("nigar")))
    assert app_db.client("office").post(f"/api/requests/{rid}/action", {"action": "approve"}).status == 200


# ---------------------------------------------------------------- 2. the effect
ORDER = [c for c in TYPES if c != "academic_leave"] + ["academic_leave"]       # the leave last: it ends the enrolments later


def test_every_type_leaves_its_effect_or_answers_from_the_factual_template(app_db, actors, course, pdf_bytes):
    student = app_db.client("student")
    sid = student.user["id"]
    for code in ORDER:
        rt = TYPES[code]
        req = file_request(student, code, course, pdf_bytes)
        rid, data = req["id"], req["data"]
        for step, role in enumerate(rt["step_roles"][:-1]):
            assert actors[role].post(f"/api/requests/{rid}/action", {"action": "approve"}).status == 200, (code, step, role)
        before = counts(sid)
        body = {"action": "issue", **LEAVE_ORDER, "effective_date": (store.now().date() + timedelta(days=60)).isoformat()} \
            if rt["effect"] == "student_status.leave" else {"action": "issue"}
        done = actors[rt["step_roles"][-1]].post(f"/api/requests/{rid}/action", body)
        assert done.status == 200 and done.json["status"] == "ready", (code, done.text)
        after = counts(sid)
        row = q("SELECT * FROM requests WHERE id=?", (rid,))[0]
        if rt["effect"] == "none":
            assert not rt.get("answer"), f"{code}: effect none still has a free answer text"
            expected = i18n.T3("Müraciətiniz qeydə alınıb. Baxan bölmə: {unit}. Qərar: təmin edilib. Zəka-da başqa heç bir qeyd dəyişməyib.",
                               unit=UNITS[rt["step_roles"][-1]])
            assert json.loads(row["answer"]) == expected and done.json["answer"] == expected["az"], code
            assert after == before, f"{code}: an effect `none` changed a record"
            assert row["document_id"] is None
        elif rt["effect"] == "document.issue":
            doc = q("SELECT * FROM documents WHERE id=?", (row["document_id"],))[0]
            assert doc["request_id"] == rid and store.payload_state(doc) == "ok", code       # Task 45's stored payload
            assert after["documents"] == before["documents"] + 1
        elif rt["effect"] == "attendance.excuse":
            marks = q("SELECT status, request_id FROM attendance WHERE user_id=? AND lesson_id IN "
                      f"({','.join('?' * len(data['absences']))})", (sid, *data["absences"]))  # nosec B608
            assert marks and all(m["status"] == "excused" and m["request_id"] == rid for m in marks), code
            assert row["answer"] == rt["answer"]
        elif rt["effect"] == "student_status.leave":
            ev = q("SELECT * FROM student_status_events WHERE student_id=? AND order_no=?", (sid, LEAVE_ORDER["order_no"]))
            assert len(ev) == 1 and ev[0]["kind"] == "academic_leave", code
            doc = q("SELECT * FROM documents WHERE id=?", (row["document_id"],))[0]
            assert store.payload_state(doc) == "ok" and LEAVE_ORDER["order_no"] in doc["payload"]
        else:
            pytest.fail(f"{code}: effect {rt['effect']} has no check")


# ---------------------------------------------------------------- 3. the offer in prod
@pytest.fixture
def all_open():
    yield
    run("UPDATE request_types SET enabled=1")
    run("UPDATE request_types SET effect=? WHERE code='grade_appeal'", (TYPES["grade_appeal"]["effect"],))


def test_a_prod_database_offers_no_type_until_one_is_opened(tmp_path):
    c = sqlite3.connect(tmp_path / "prod.db")
    c.row_factory = sqlite3.Row
    try:
        migrate.apply(c)
        store.seed_catalog(c)                  # what store.init does in prod: migrations, then the catalogue, no people
        assert c.execute("SELECT COUNT(*), SUM(enabled) FROM request_types").fetchone()[:] == (13, 0)
    finally:
        c.close()


def test_in_prod_a_closed_type_is_nowhere_and_an_opened_one_is_offered(app_db, student, office, leader, admin, monkeypatch, all_open):
    monkeypatch.setattr(config, "MODE", "prod")                            # signed in before: prod has no demo login
    run("UPDATE request_types SET enabled=0")                              # a prod database before the administrator opened any
    free = {"type_code": "free_application", "data": {"to": "Dekanlıq", "subject": "Mövzu", "body": "Mətn"}}
    assert student.get("/api/services").json["types"] == []
    assert student.post("/api/requests", free).status == 404
    assert not [x for x in student.get(SEARCH).json["results"] if x["group"] == "E-xidmətlər"]
    asked = student.post("/api/campus/ask", {"message": "Kosmik gəmi biletini haradan alım?"}).json["answer"]["meta"]
    assert not [a for a in asked["actions"] if a["type"] == "request"], "no action button for a closed type"
    r = admin.put("/api/admin/request-types/free_application", {"enabled": True})
    assert r.status == 200 and next(x for x in r.json if x["code"] == "free_application")["enabled"] is True
    assert [t["code"] for t in student.get("/api/services").json["types"]] == ["free_application"]
    assert student.post("/api/requests", free).status == 200
    assert [x["title"] for x in student.get(SEARCH).json["results"] if x["group"] == "E-xidmətlər"]
    audits = q("SELECT user_id, entity, detail FROM audit WHERE action='request_type_open' ORDER BY id DESC LIMIT 1")
    assert audits == [{"user_id": admin.user["id"], "entity": "request_type", "detail": "free_application"}]
    assert admin.put("/api/admin/request-types/free_application", {"enabled": False}).status == 200
    assert q("SELECT detail FROM audit WHERE action='request_type_close' ORDER BY id DESC LIMIT 1")[0]["detail"] == "free_application"
    assert student.post("/api/requests", free).status == 404
    for who in (student, office, leader):
        assert who.put("/api/admin/request-types/free_application", {"enabled": True}).status == 403, who.user["role"]
    assert admin.put("/api/admin/request-types/free_application", {"enabled": "1"}).status == 400
    assert admin.put("/api/admin/request-types/nope", {"enabled": True}).status == 404


def test_in_demo_every_type_is_open(app_db):
    assert config.MODE == "demo"
    assert len(app_db.client("student").get("/api/services").json["types"]) == 13
    assert q("SELECT COUNT(*) n FROM request_types WHERE enabled=1")[0]["n"] == 13


def test_a_type_whose_effect_is_not_registered_cannot_be_opened(app_db, all_open):
    run("UPDATE request_types SET effect='grades.change', enabled=0 WHERE code='grade_appeal'")
    r = app_db.client("admin").put("/api/admin/request-types/grade_appeal", {"enabled": True})
    assert r.status == 400 and "grades.change" in r.json["error"]
    assert q("SELECT enabled FROM request_types WHERE code='grade_appeal'")[0]["enabled"] == 0
    listed = next(x for x in app_db.client("admin").get("/api/admin/request-types").json if x["code"] == "grade_appeal")
    assert listed["registered"] is False and listed["enabled"] is False


def test_0461_has_the_names_and_answers_of_content_seed_json(tmp_path):
    c = sqlite3.connect(tmp_path / "fresh.db")
    c.row_factory = sqlite3.Row
    try:
        migrate.apply(c)
        got = {r["code"]: dict(r) for r in c.execute("SELECT * FROM request_types")}
    finally:
        c.close()
    assert set(got) == set(TYPES)
    for code, rt in TYPES.items():
        g = got[code]
        assert g["name"] == rt["name"] and g["answer"] == rt.get("answer", ""), code
        assert (g["description"], g["outcome"], g["document"]) == (rt["description"], rt.get("outcome", ""), rt.get("document")), code
        assert json.loads(g["steps"]) == rt["steps"] and json.loads(g["fields"]) == rt["fields"], code
        assert json.loads(g["step_roles"]) == rt["step_roles"] and g["effect"] == rt["effect"] and g["enabled"] == 0, code
