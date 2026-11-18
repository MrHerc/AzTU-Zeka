"""A dean's office sees its own faculty; reading another person's data is audited (tasks/todo.md, Task 13, slice 2)."""
import pytest

from zeka.legacy import store


def db():
    return store.connect()


@pytest.fixture(scope="module")
def setting(app_db):
    """Aysel moves to a second faculty B; her request, document and file are what the dean's office of A must not see."""
    admin = app_db.client("admin")
    fb = admin.post("/api/directory/faculties", {"code": "FB", "name": "B fakültəsi"}).json["id"]
    gb = admin.post("/api/directory/groups", {"name": "B-25-1", "year": 2025, "faculty_id": fb}).json["id"]
    c = db()
    try:
        aysel = store.row(c, "SELECT id FROM users WHERE username='aysel'")["id"]
        c.execute("UPDATE users SET group_id=? WHERE id=?", (gb, aysel))
        c.commit()
        rid = store.row(c, "SELECT id FROM requests WHERE student_id=? ORDER BY id LIMIT 1", (aysel,))["id"]
        did = store.row(c, "SELECT id FROM documents WHERE holder_id=? ORDER BY id LIMIT 1", (aysel,))["id"]
        office = store.row(c, "SELECT id FROM users WHERE username=?", (store.setting(c, "demo_logins")["office"],))["id"]
    finally:
        c.close()
    student = app_db.client("student")
    fid = student.post("/api/files", {"filename": "arayis.txt", "content_b64": "YXJheWlz"})
    return {"faculty_b": fb, "aysel": aysel, "request": rid, "document": did, "office": office,
            "file": fid.json["id"] if fid.status == 200 else None}


def test_a_dean_s_office_gets_404_for_another_faculty_s_student(app_db, setting):
    office = app_db.client("office")
    assert office.get(f"/api/requests/{setting['request']}").status == 404
    assert setting["request"] not in {r["id"] for r in office.get("/api/requests?status=all").json}
    assert office.get(f"/doc/{setting['document']}").status == 404
    assert setting["document"] not in {d["id"] for d in office.get("/api/documents").json}
    if setting["file"]:
        assert office.get(f"/api/files/{setting['file']}").status == 404
    assert office.get("/api/requests?status=all").json, "its own faculty's requests are still there"


def test_a_grant_for_the_other_faculty_opens_it(app_db, setting):
    admin = app_db.client("admin")
    gid = admin.post(f"/api/admin/users/{setting['office']}/roles",
                     {"role": "office", "scope_type": "faculty", "scope_id": setting["faculty_b"]}).json["id"]
    office = app_db.client("office")
    try:
        assert office.get(f"/api/requests/{setting['request']}").status == 200
        assert office.get(f"/doc/{setting['document']}").status == 200
    finally:
        admin.delete(f"/api/admin/users/{setting['office']}/roles/{gid}")


def test_leadership_and_admin_still_see_the_whole_university(app_db, setting):
    for role in ("leader", "admin"):
        assert app_db.client(role).get(f"/api/requests/{setting['request']}").status == 200, role


def test_an_office_account_without_a_faculty_sees_no_request(app_db, setting):
    c = db()
    grants = store.rows(c, "SELECT * FROM role_grants WHERE user_id=?", (setting["office"],))
    c.execute("DELETE FROM role_grants WHERE user_id=?", (setting["office"],))
    c.commit()
    c.close()
    try:
        office = app_db.client("office")
        assert office.get("/api/requests?status=all").json == []
        assert office.get("/api/documents").json == []
    finally:
        c = db()
        c.executemany("INSERT INTO role_grants(user_id,role,scope_type,scope_id,granted_at) VALUES(?,?,?,?,?)",
                      [(g["user_id"], g["role"], g["scope_type"], g["scope_id"], g["granted_at"]) for g in grants])
        c.commit()
        c.close()


def reads(kind):
    c = db()
    try:
        return store.rows(c, "SELECT user_id, detail FROM audit WHERE action=?", (f"read_{kind}",))
    finally:
        c.close()


def test_reading_another_person_s_data_is_audited_and_one_s_own_is_not(app_db, setting):
    before = len(reads("request"))
    me = app_db.client("student")                     # Aysel reads her own request: not written
    assert me.get(f"/api/requests/{setting['request']}").status == 200
    assert len(reads("request")) == before
    admin = app_db.client("admin")
    assert admin.get(f"/api/requests/{setting['request']}").status == 200
    entry = reads("request")[-1]
    assert len(reads("request")) == before + 1 and f"#{setting['request']}" in entry["detail"] and f"#{setting['aysel']}" in entry["detail"]
    assert admin.get(f"/doc/{setting['document']}").status == 200 and reads("document")
    teacher = app_db.client("teacher")
    radar = teacher.get("/api/radar").json["rows"]
    assert teacher.get(f"/api/radar/student/{radar[0]['id']}").status == 200
    assert any(f"#{radar[0]['id']}" in r["detail"] for r in reads("risk_profile"))
