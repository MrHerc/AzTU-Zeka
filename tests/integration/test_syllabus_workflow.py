"""The syllabus's approval chain and what publication configures (tasks/todo.md, Task 25): only the next role moves a
version on, a return carries a comment, publication writes the course's components, attendance limit and tutor modes,
a course with scores needs the academic office's explicit and audited permission, and students see only the published
version."""
from datetime import timedelta

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
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


@pytest.fixture(scope="module")
def actors(app_db):
    """The demo teacher (the course's head), the same person acting as its department head, and the academic office."""
    admin = app_db.client("admin")
    teacher = app_db.client("teacher")
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    cid = admin.post("/api/directory/courses", {"code": "SW-101", "name": "Zəncir sınağı", "credits": 4, "term_id": term["id"],
                                                "teacher_id": teacher.user["id"]}).json["id"]
    admin.post(f"/api/admin/users/{teacher.user['id']}/roles", {"role": "dept_head", "scope_type": "course", "scope_id": cid})
    head = app_db.client("teacher")
    assert head.post("/api/me/role", {"role": "dept_head"}).status == 200
    office_user = app_db.client("office").user["id"]
    admin.post(f"/api/admin/users/{office_user}/roles", {"role": "academic_office"})
    registrar = app_db.client("office")
    assert registrar.post("/api/me/role", {"role": "academic_office"}).status == 200
    return {"course": cid, "teacher": teacher, "head": head, "registrar": registrar, "admin": admin, "term": term}


def version(actors, change=None):
    """A new saved version of the course's syllabus, with AI forbidden and a 20% attendance limit."""
    t, cid = actors["teacher"], actors["course"]
    d = t.post(f"/api/syllabi/{cid}/draft").json["data"]
    d["outcomes"] = [{"id": "N1", "text": "Dövrəni təhlil edir və hesablayır", "bloom": "analyze"}]
    d["plan"] = [{"week": 1, "topic": "Giriş mövzusu", "outcomes": ["N1"], "activity": ""}]
    d["assessment"] = [{"name": "Davamiyyət", "kind": "attendance", "weight": 10}, {"name": "Layihə işi", "kind": "component", "weight": 40},
                       {"name": "İmtahan", "kind": "exam", "weight": 50}]
    d["rules"].update(attendance_limit=20, ai_policy="forbidden")
    if change:
        change(d)
    st = t.put(f"/api/syllabi/{cid}", {"data": d}).json
    return st["latest"]["id"]


def step(client, actors, vid, action, **body):
    return client.post(f"/api/syllabi/{actors['course']}/versions/{vid}/{action}", body)


def test_only_the_next_role_moves_a_version_on_and_a_return_needs_a_comment(app_db, actors):
    t, head, reg = actors["teacher"], actors["head"], actors["registrar"]
    vid = version(actors)
    assert step(head, actors, vid, "approve").status == 403, "not submitted yet"
    assert step(t, actors, vid, "submit").status == 200
    assert step(t, actors, vid, "approve").status == 403 and step(reg, actors, vid, "publish").status == 403
    assert step(reg, actors, vid, "approve").status == 403, "the department head's step"
    assert step(head, actors, vid, "return").status == 400, "a return needs a comment"
    r = step(head, actors, vid, "return", note="Nəticələri ölçülə bilən edin")
    assert r.status == 200 and r.json["latest"]["status"] == "returned"
    assert step(t, actors, vid, "submit").status == 403, "a returned version is not sent again: a new one is saved"
    assert q("SELECT note FROM syllabus_steps WHERE version_id=? AND action='return'", (vid,))[0]["note"] == "Nəticələri ölçülə bilən edin"


def test_publication_writes_the_components_the_tutor_and_the_limit_the_journal_applies(app_db, actors):
    t, head, reg, cid = actors["teacher"], actors["head"], actors["registrar"], actors["course"]
    student = app_db.client("student")
    sid = student.user["id"]
    actors["admin"].post(f"/api/directory/courses/{cid}/enrollments", {"user_id": sid})
    unit = actors["admin"].post("/api/directory/units", {"course_id": cid, "kind": "lecture", "teacher_id": t.user["id"]}).json["id"]
    gid = q("SELECT group_id FROM users WHERE id=?", (sid,))[0]["group_id"]
    actors["admin"].put(f"/api/directory/units/{unit}/groups", {"group_ids": [gid]})
    start = store.now().date() - timedelta(days=40)
    for k in range(100):                                                 # 100 one-hour lessons held; the student missed 21
        d = (start + timedelta(days=k % 35)).isoformat()
        lid = run("INSERT INTO lessons(course_id,day,start,end,kind,unit_id,teacher_id,academic_hours,slot_day,slot_start) "
                  "VALUES(?,?,?,?,'Mühazirə',?,?,1,?,?)", (cid, d, f"0{k // 35}:{(k % 35):02d}"[:5], "23:59", unit, t.user["id"], d,
                                                           f"0{k // 35}:{(k % 35):02d}"[:5]))
        run("INSERT INTO attendance(lesson_id,user_id,status) VALUES(?,?,?)", (lid, sid, "absent" if k < 21 else "present"))

    def status():
        return next(x for x in actors["admin"].get(f"/api/journal/courses/{cid}/standing").json if x["student_id"] == sid)
    assert status()["status"] != "not_admitted", "21% is under the university's 25%"
    vid = version(actors)
    for client, action in ((t, "submit"), (head, "approve"), (reg, "publish")):
        assert step(client, actors, vid, action).status == 200, action
    assert status()["status"] == "not_admitted", "the syllabus's 20% applies: min(25, 20)"
    cols = [(x["key"], x["max"], x["kind"]) for x in actors["admin"].get(f"/api/journal/courses/{cid}/grades").json["columns"]]
    assert cols == [("Davamiyyət", 10.0, "attendance"), ("Layihə işi", 40.0, "component"), ("İmtahan", 50.0, "exam")]
    co = q("SELECT tutor_modes, tutor_locked, attendance_limit FROM courses WHERE id=?", (cid,))[0]
    assert co == {"tutor_modes": '["socratic"]', "tutor_locked": 1, "attendance_limit": 20.0}, "AI forbidden: the Socratic mode only"
    page = student.get(f"/syllabus/{cid}")
    assert page.status == 200 and "Layihə işi" in page.text


def test_a_course_with_scores_is_published_only_with_the_office_s_audited_permission(app_db, actors):
    t, head, reg, cid = actors["teacher"], actors["head"], actors["registrar"], actors["course"]
    sid = app_db.client("student").user["id"]
    run("INSERT INTO grades(user_id,course_id,component,score,max,status,source) VALUES(?,?,'Layihə işi',30,40,'published','zeka') "
        "ON CONFLICT(user_id,course_id,component) DO UPDATE SET score=30", (sid, cid))
    vid = version(actors, lambda d: d["assessment"][1].update(name="Kurs işi"))
    assert step(t, actors, vid, "submit").status == 200 and step(head, actors, vid, "approve").status == 200
    assert step(reg, actors, vid, "publish").status == 409
    assert step(reg, actors, vid, "publish", override=True).status == 409, "a reason too"
    r = step(reg, actors, vid, "publish", override=True, note="Kafedranın qərarı №12")
    assert r.status == 200 and r.json["published"]["id"] == vid
    assert q("SELECT 1 FROM audit WHERE action='syllabus_publish_override' AND detail LIKE ?", ("%Kafedranın qərarı №12%",))


def test_a_student_sees_only_the_published_version(app_db, actors):
    t, cid = actors["teacher"], actors["course"]
    student = app_db.client("student")
    pub = student.get(f"/api/courses/{cid}/syllabus").json["published"]
    draft = version(actors, lambda d: d.update(description="Hələ dərc olunmamış qaralama"))
    assert student.get(f"/api/courses/{cid}/syllabus").json["published"]["id"] == pub["id"]
    assert "Hələ dərc olunmamış qaralama" not in student.get(f"/syllabus/{cid}").text
    assert "Hələ dərc olunmamış qaralama" not in student.get(f"/syllabus/{cid}?v={draft}").text, "?v= is staff only"
    assert student.get(f"/api/syllabi/{cid}").status == 403
    assert t.get(f"/api/syllabi/{cid}/diff?a={pub['id']}&b={draft}").json[0]["section"] == "description"


def test_the_queues_hold_what_waits_for_each_role(app_db, actors):
    t, head, reg = actors["teacher"], actors["head"], actors["registrar"]
    vid = version(actors, lambda d: d.update(description="Növbə üçün"))
    assert step(t, actors, vid, "submit").status == 200
    assert vid in [x["id"] for x in head.get("/api/syllabi/queue").json]
    assert vid not in [x["id"] for x in reg.get("/api/syllabi/queue").json]
    assert step(head, actors, vid, "approve").status == 200
    assert vid in [x["id"] for x in reg.get("/api/syllabi/queue").json]
    other = app_db.client("teacher")
    assert other.get("/api/syllabi/queue").status == 403
