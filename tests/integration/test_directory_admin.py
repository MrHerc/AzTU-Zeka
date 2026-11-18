"""The university's structure and terms (tasks/todo.md, Task 15, slice 1): create, change, deactivate; never delete."""
import pytest

from zeka.legacy import store


def audits(action):
    c = store.connect()
    try:
        return [r["detail"] for r in store.rows(c, "SELECT detail FROM audit WHERE action=?", (action,))]
    finally:
        c.close()


def test_the_demo_structure_links_groups_to_a_faculty(admin):
    faculties = admin.get("/api/directory/faculties").json
    assert faculties["total"] >= 1 and faculties["items"][0]["code"] == "İTT"
    groups = admin.get("/api/directory/groups").json["items"]
    assert groups and all(g["faculty_id"] == faculties["items"][0]["id"] for g in groups)


def test_a_faculty_is_created_changed_deactivated_and_never_deleted(admin):
    r = admin.post("/api/directory/faculties", {"code": "ENR", "name": "Energetika fakültəsi"})
    assert r.status == 200 and r.json["active"] == 1
    fid = r.json["id"]
    assert admin.put(f"/api/directory/faculties/{fid}", {"name": "Energetika və avtomatika fakültəsi"}).json["name"].startswith("Energetika və")
    assert admin.post(f"/api/directory/faculties/{fid}/deactivate").json["active"] == 0
    assert admin.post(f"/api/directory/faculties/{fid}/activate").json["active"] == 1
    assert admin.delete(f"/api/directory/faculties/{fid}").status == 405
    assert any(d.startswith(f"{fid} ·") for d in audits("directory_create"))
    assert any("Energetika və avtomatika" in d for d in audits("directory_update"))
    assert str(fid) in audits("directory_deactivate")


def test_references_must_exist(admin):
    assert admin.post("/api/directory/departments", {"faculty_id": 999999, "code": "XX-1", "name": "Heç yerdə"}).status == 400
    fid = admin.post("/api/directory/faculties", {"code": "MEX", "name": "Mexanika fakültəsi"}).json["id"]
    dep = admin.post("/api/directory/departments", {"faculty_id": fid, "code": "MEX-1", "name": "Tətbiqi mexanika"})
    assert dep.status == 200 and dep.json["faculty_id"] == fid


@pytest.mark.parametrize("body", [
    {"code": "a", "name": "Qısa kod"},
    {"code": "OK", "name": "x"},
    {"code": "OK2", "name": 5},
    {"code": "boşluqlu kod", "name": "Boşluq kodda olmaz"},
])
def test_fields_are_validated_with_a_translated_reason(admin, body):
    r = admin.post("/api/directory/faculties", body, lang="en")
    assert r.status == 400 and r.json["error"] and "sahə" not in r.json["error"]


def test_a_term_whose_teaching_does_not_end_before_the_exams_is_refused(admin):
    good = {"code": "2026-PAYIZ", "name": "2026/2027 payız", "teaching_start": "2026-09-15", "teaching_end": "2026-12-27",
            "exam_start": "2027-01-04", "exam_end": "2027-01-31"}
    r = admin.post("/api/directory/terms", {**good, "exam_start": "2026-12-20"}, lang="en")
    assert r.status == 400 and "exam" in r.json["error"].lower()
    assert admin.post("/api/directory/terms", {**good, "teaching_end": "2026-09-01"}).status == 400
    tid = admin.post("/api/directory/terms", good).json["id"]
    assert admin.put(f"/api/directory/terms/{tid}", {"teaching_end": "2027-01-10"}).status == 400     # checked on the merged record
    assert admin.post("/api/directory/terms", {**good, "code": "Bad date", "teaching_start": "15.09.2026"}).status == 400


def test_a_code_is_unique(admin):
    assert admin.post("/api/directory/faculties", {"code": "TKS", "name": "Telekommunikasiya"}).status == 200
    assert admin.post("/api/directory/faculties", {"code": "TKS", "name": "Başqa"}).status == 409
    other = admin.post("/api/directory/faculties", {"code": "TKS2", "name": "Başqa"}).json["id"]
    assert admin.put(f"/api/directory/faculties/{other}", {"code": "TKS"}).status == 409


def test_lists_are_paged_on_the_server_and_searched_there(admin):
    fid = admin.post("/api/directory/faculties", {"code": "PAGE", "name": "Səhifələmə fakültəsi"}).json["id"]
    for i in range(55):
        assert admin.post("/api/directory/departments", {"faculty_id": fid, "code": f"PG-{i:02d}", "name": f"Kafedra {i:02d}"}).status == 200
    first = admin.get("/api/directory/departments?q=PG-").json
    assert first["total"] >= 55 and len(first["items"]) == 50 and first["pages"] >= 2 and first["page_size"] == 50
    second = admin.get("/api/directory/departments?q=PG-&page=2").json
    assert len(second["items"]) == first["total"] - 50
    assert [d["code"] for d in admin.get("/api/directory/departments?q=PG-07").json["items"]] == ["PG-07"]
    assert admin.get("/api/directory/departments?q=%25").json["total"] == 0       # LIKE wildcards are plain text


def test_only_admin_and_academic_affairs_change_the_structure(app_db):
    for role in ("teacher", "office", "leader"):
        c = app_db.client(role)
        assert c.get("/api/directory/faculties").status == 200, role
        assert c.post("/api/directory/faculties", {"code": f"R-{role}", "name": "Rol yoxlaması"}).status == 403, role
    assert app_db.client("student").get("/api/directory/faculties").status == 403
    assert app_db.client("admin").get("/api/directory/planets").status == 404


# ---------------------------------------------------------------- slice 2: people, courses, teaching units, enrolments
def _q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def test_users_are_created_changed_and_deactivated_and_a_deactivated_user_cannot_sign_in(app_db, admin, monkeypatch):
    from zeka.modules.identity import domain as identity
    monkeypatch.setattr(identity, "N", 2 ** 4)
    gid = admin.get("/api/directory/groups").json["items"][0]["id"]
    r = admin.post("/api/directory/users", {"username": "Yeni.Telebe", "full_name": "Yeni Tələbə", "role": "student",
                                            "group_id": gid, "student_no": "S-55501", "email": "Yeni@aztu.edu.az"})
    assert r.status == 200, r.text
    u = r.json
    assert u["username"] == "yeni.telebe" and u["email"] == "yeni@aztu.edu.az" and u["active"] == 1
    assert "password_hash" not in u and "totp_secret" not in u
    listed = admin.get("/api/directory/users?q=yeni.telebe").json["items"]
    assert [x["id"] for x in listed] == [u["id"]] and "password_hash" not in listed[0]
    assert admin.post("/api/directory/users", {"username": "yeni.telebe", "full_name": "Başqa", "role": "student"}).status == 409
    assert admin.post("/api/directory/users", {"username": "x2", "full_name": "Başqa", "role": "student"}).status == 400
    assert admin.post("/api/directory/users", {"username": "muellim2", "full_name": "Müəllim", "role": "teacher",
                                               "student_no": "S-1"}).status == 400, "a student number is for students"
    assert admin.put(f"/api/directory/users/{u['id']}", {"full_name": "Yeni Tələbə Oğlu"}).json["full_name"] == "Yeni Tələbə Oğlu"
    password = admin.post(f"/api/admin/users/{u['id']}/temp-password").json["password"]
    signed = app_db.client()
    assert signed.post("/api/auth/login", {"login": "yeni.telebe", "password": password}).status == 200
    assert admin.post(f"/api/directory/users/{u['id']}/deactivate").json["active"] == 0
    assert signed.get("/api/bootstrap").json["user"] is None, "the session ended"
    assert app_db.client().post("/api/auth/login", {"login": "yeni.telebe", "password": password}).status == 401
    assert _q("SELECT status FROM users WHERE id=?", (u["id"],))[0]["status"] == "disabled", "the account and its history stay"
    assert admin.post(f"/api/directory/users/{u['id']}/activate").json["active"] == 1


def test_an_administrator_cannot_lock_themselves_out(admin):
    me = admin.user["id"]
    assert admin.post(f"/api/directory/users/{me}/deactivate").status == 409
    assert admin.put(f"/api/directory/users/{me}", {"role": "student"}).status == 409


def test_only_the_administrator_manages_accounts(app_db):
    office = app_db.client("office")
    admin = app_db.client("admin")
    admin.post(f"/api/admin/users/{office.user['id']}/roles", {"role": "academic_office"})
    assert office.post("/api/me/role", {"role": "academic_office"}).status == 200
    assert office.get("/api/directory/users?role=student").status == 200, "the academic office reads the register"
    assert office.post("/api/directory/users", {"username": "kimse", "full_name": "Kimsə", "role": "admin"}).status == 403
    assert app_db.client("teacher").get("/api/directory/users").status == 403


def test_courses_and_teaching_units_with_groups(admin, app_db):
    teacher_id = app_db.client("teacher").user["id"]
    student_id = app_db.client("student").user["id"]
    term = admin.post("/api/directory/terms", {"code": "2027-P", "name": "2027 payız", "teaching_start": "2027-09-15",
                                              "teaching_end": "2027-12-28", "exam_start": "2028-01-05", "exam_end": "2028-01-30"}).json["id"]
    assert admin.post("/api/directory/courses", {"code": "ALQ-101", "name": "Alqoritmlər", "teacher_id": student_id,
                                                 "credits": 5}).status == 400, "the lead teacher must be a teacher"
    co = admin.post("/api/directory/courses", {"code": "ALQ-101", "name": "Alqoritmlər", "teacher_id": teacher_id, "credits": 5,
                                               "term_id": term})
    assert co.status == 200 and co.json["active"] == 1 and co.json["term_id"] == term
    assert [x["id"] for x in admin.get(f"/api/directory/courses?term_id={term}").json["items"]] == [co.json["id"]]
    assert admin.post("/api/directory/courses", {"code": "ALQ-101", "name": "x", "credits": 99}).status == 400
    unit = admin.post("/api/directory/units", {"course_id": co.json["id"], "kind": "lab", "teacher_id": teacher_id, "subgroup": 2})
    assert unit.status == 200 and unit.json["kind"] == "lab"
    assert admin.post("/api/directory/units", {"course_id": co.json["id"], "kind": "party"}).status == 400
    groups = [g["id"] for g in admin.get("/api/directory/groups").json["items"][:2]]
    assert admin.put(f"/api/directory/units/{unit.json['id']}/groups", {"group_ids": groups}).json["group_ids"] == sorted(groups)
    assert admin.put(f"/api/directory/units/{unit.json['id']}/groups", {"group_ids": [999999]}).status == 400
    assert admin.get(f"/api/directory/units?course_id={co.json['id']}").json["total"] == 1
    assert admin.post(f"/api/directory/courses/{co.json['id']}/deactivate").json["active"] == 0


def test_enrolments_are_added_ended_and_never_deleted(admin, app_db):
    teacher = app_db.client("teacher")
    co = admin.post("/api/directory/courses", {"code": "ENR-1", "name": "Qeydiyyat fənni", "teacher_id": teacher.user["id"],
                                               "credits": 3}).json["id"]
    sid = app_db.client("student").user["id"]
    path = f"/api/directory/courses/{co}/enrollments"
    assert admin.post(path, {"user_id": teacher.user["id"]}).status == 400, "only a student"
    assert admin.post(path, {"user_id": sid, "subgroup": 1, "begin_date": "2026-09-15"}).status == 200
    assert admin.post(path, {"user_id": sid}).status == 409
    e = admin.get(path).json[0]
    assert e["user_id"] == sid and e["group_id"] and e["subgroup"] == 1 and e["end_date"] is None
    roster = teacher.get(f"/api/courses/{co}/roster?day=2026-10-01").json
    assert [s["id"] for s in roster["students"]] == [sid]
    assert teacher.get(f"/api/courses/{co}/roster?day=2026-09-01").json["students"] == [], "before it begins"
    assert admin.post(f"{path}/{sid}/end", {"end_date": "2026-09-01"}).status == 400, "ends after it begins"
    assert admin.post(f"{path}/{sid}/end", {"end_date": "2026-11-01"}).status == 200
    assert teacher.get(f"/api/courses/{co}/roster?day=2026-11-01").json["students"] == []
    assert [x["end_date"] for x in admin.get(path).json] == ["2026-11-01"], "the row stays"
    assert teacher.get(f"/api/courses/{co}/roster?day=31.10.2026").status == 400
    other = _q("SELECT id FROM courses WHERE teacher_id<>? LIMIT 1", (teacher.user["id"],))[0]["id"]
    assert teacher.get(f"/api/courses/{other}/roster").status == 403, "a teacher sees their own courses only"
    assert app_db.client("student").get(f"/api/courses/{co}/roster").status == 403
