"""The structured syllabus (tasks/todo.md, Task 23): a first draft from the assistant and Forma №3, the university's
rules on save, a new version on every save, a published version that never changes, an escaped printable page."""
import copy

import pytest

from zeka.legacy import store

XSS = "<img src=x onerror=alert(1)>"


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
def course(app_db):
    """A course of the demo teacher with Forma №3 hours on its units: lecture 30, seminar 15 (two groups), lab 15."""
    admin, teacher = app_db.client("admin"), app_db.client("teacher")
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    cid = admin.post("/api/directory/courses", {"code": "SY-101", "name": "Sillabus sınağı", "credits": 5, "term_id": term["id"],
                                                "teacher_id": teacher.user["id"]}).json["id"]
    for kind, hours in (("lecture", 30), ("seminar", 15), ("seminar", 15), ("lab", 15)):
        uid = admin.post("/api/directory/units", {"course_id": cid, "kind": kind, "teacher_id": teacher.user["id"]}).json["id"]
        run("UPDATE teaching_units SET hours=?, students=25 WHERE id=?", (hours, uid))     # as the teaching-load import writes them
    return cid


@pytest.fixture(scope="module")
def first(app_db, course):
    teacher = app_db.client("teacher")
    d = teacher.post(f"/api/syllabi/{course}/draft").json["data"]
    d["outcomes"] = [{"id": "N1", "text": "Om qanununu izah edir və tətbiq edir", "bloom": "apply"}]
    d["plan"] = [{"week": 1, "topic": "Om qanunu", "outcomes": ["N1"], "activity": "Mühazirə"}]
    return d


def save(client, course, data, base=None):
    body = {"data": data} if base is None else {"data": data, "base": base}
    return client.put(f"/api/syllabi/{course}", body)


def test_the_first_draft_takes_its_hours_from_forma3(app_db, course, first):
    assert {k: first["workload"][k] for k in ("lecture", "seminar", "lab")} == {"lecture": 30.0, "seminar": 15.0, "lab": 15.0}
    assert app_db.client("teacher").get(f"/api/syllabi/{course}").json["imported"] == {"lecture": 30.0, "seminar": 15.0, "lab": 15.0}


def test_changed_hours_are_shown_to_the_department_head_as_a_difference(app_db, course, first):
    teacher, admin = app_db.client("teacher"), app_db.client("admin")
    d = copy.deepcopy(first)
    d["workload"]["lecture"] = 24
    assert save(teacher, course, d).status == 200
    head = app_db.client("teacher")
    admin.post(f"/api/admin/users/{head.user['id']}/roles", {"role": "dept_head", "scope_type": "course", "scope_id": course})
    try:
        assert head.post("/api/me/role", {"role": "dept_head"}).status == 200
        assert head.get(f"/api/syllabi/{course}").json["diff"] == [{"kind": "lecture", "imported": 30.0, "syllabus": 24.0}]
    finally:
        gid = q("SELECT id FROM role_grants WHERE user_id=? AND role='dept_head' AND scope_type='course' AND scope_id=?", (head.user["id"], course))
        if gid:
            admin.delete(f"/api/admin/users/{head.user['id']}/roles/{gid[0]['id']}")


@pytest.mark.parametrize("change,why", [
    (lambda d: d["assessment"][1].update(weight=d["assessment"][1]["weight"] + 1), "the weights must add up to 100"),
    (lambda d: (d["assessment"][-1].update(weight=40), d["assessment"][1].update(weight=d["assessment"][1]["weight"] + 10)), "the exam weighs 50"),
    (lambda d: d["rules"].update(attendance_limit=30), "only lower than the university's 25%"),
])
def test_a_syllabus_against_the_university_s_rules_is_not_saved(app_db, course, first, change, why):
    teacher = app_db.client("teacher")
    before = len(q("SELECT id FROM syllabus_versions WHERE course_id=?", (course,)))
    d = copy.deepcopy(first)
    change(d)
    r = save(teacher, course, d)
    assert r.status == 400, why
    assert len(q("SELECT id FROM syllabus_versions WHERE course_id=?", (course,))) == before


def test_every_save_is_a_new_draft_and_a_published_version_never_changes(app_db, course, first):
    teacher = app_db.client("teacher")
    n = len(q("SELECT id FROM syllabus_versions WHERE course_id=?", (course,)))
    d = copy.deepcopy(first)
    d["description"] = "Birinci mətn"
    st = save(teacher, course, d).json
    pub = st["latest"]["id"]
    run("UPDATE syllabus_versions SET status='published' WHERE id=?", (pub,))           # Task 25 publishes through its chain
    kept = q("SELECT data FROM syllabus_versions WHERE id=?", (pub,))[0]["data"]
    d["description"] = "İkinci mətn"
    st = save(teacher, course, d, base=st["latest"]["version"]).json
    assert st["latest"]["status"] == "draft" and st["latest"]["version"] == n + 2 and st["published"]["id"] == pub
    assert q("SELECT data FROM syllabus_versions WHERE id=?", (pub,))[0]["data"] == kept
    assert save(teacher, course, d, base=1).status == 409, "an editor working on an old version is told"
    assert len(q("SELECT id FROM syllabus_versions WHERE course_id=?", (course,))) == n + 2


def test_only_the_course_s_head_writes_and_its_readers_read(app_db, course, first):
    other = q("SELECT id FROM courses WHERE teacher_id<>? ORDER BY id LIMIT 1", (app_db.client("teacher").user["id"],))[0]["id"]
    teacher = app_db.client("teacher")
    assert save(teacher, other, first).status in (403, 404)
    assert teacher.get(f"/api/syllabi/{other}").status == 404
    assert app_db.client("student").get(f"/api/syllabi/{course}").status == 403
    assert app_db.client("admin").get(f"/api/syllabi/{course}").status == 200


def test_the_printable_page_escapes_every_value(app_db, course, first):
    teacher = app_db.client("teacher")
    d = copy.deepcopy(first)
    d["description"] = XSS
    d["outcomes"][0]["text"] = XSS + " izah edir"
    d["plan"][0]["topic"] = XSS
    d["plan"][0]["activity"] = XSS
    d["assessment"][1]["name"] = XSS
    d["rules"]["late_policy"] = XSS
    d["rules"]["ai_note"] = XSS
    d["prerequisites"] = [XSS]
    d["literature"] = [{"title": XSS, "kind": "main"}]
    assert save(teacher, course, d).status == 200
    page = teacher.get(f"/syllabus/{course}").text
    assert XSS not in page and "&lt;img src=x onerror=alert(1)&gt;" in page
    v1 = q("SELECT id FROM syllabus_versions WHERE course_id=? ORDER BY version LIMIT 1", (course,))[0]["id"]
    assert "Versiya 1" in teacher.get(f"/syllabus/{course}?v={v1}").text


def test_a_course_without_a_saved_syllabus_prints_its_first_draft(app_db):
    teacher = app_db.client("teacher")
    cid = teacher.get("/api/courses").json[0]["id"]
    if q("SELECT 1 FROM syllabus_versions WHERE course_id=?", (cid,)):
        pytest.skip("already saved")
    page = teacher.get(f"/syllabus/{cid}")
    assert page.status == 200 and "Saxlanmamış ilk layihə" in page.text


def test_the_draft_is_not_translated_into_the_page_s_language(app_db, course):
    """The syllabus is the teacher's text: an English page must not turn the assistant's Azerbaijani into English."""
    en = app_db.client("teacher", lang="en")
    d = en.post(f"/api/syllabi/{course}/draft").json["data"]
    names = [a["name"] for a in d["assessment"]]
    assert "Davamiyyət" in names and "İmtahan" in names and "Attendance" not in names
