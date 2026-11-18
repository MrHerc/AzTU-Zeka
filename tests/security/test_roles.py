"""More than one role per person (tasks/todo.md, Task 13, slice 1): grants, the active role of a session, switching."""
import re

import pytest

from zeka.legacy import store


@pytest.fixture
def db_user():
    def find(role):
        c = store.connect()
        try:
            name = store.setting(c, "demo_logins")[role]
            return store.row(c, "SELECT id, username FROM users WHERE username=?", (name,))
        finally:
            c.close()
    yield find
    c = store.connect()
    c.execute("DELETE FROM role_grants")
    c.commit()
    c.close()


def sid_of(r):
    return re.search(r"zeka_sid=([^;]+)", r.headers["Set-Cookie"]).group(1)


def audits(action):
    c = store.connect()
    try:
        return [r["detail"] for r in store.rows(c, "SELECT detail FROM audit WHERE action=?", (action,))]
    finally:
        c.close()


def test_a_granted_role_can_be_switched_to_with_a_new_session_id(app_db, db_user):
    teacher = db_user("teacher")
    admin = app_db.client("admin")
    assert admin.post(f"/api/admin/users/{teacher['id']}/roles", {"role": "dept_head", "scope_type": "department", "scope_id": 1}).status == 200
    me = app_db.client()
    first = sid_of(me.post("/api/auth/demo", {"role": "teacher"}))
    roles = me.get("/api/me/roles").json
    assert roles["active"] == "teacher" and {r["role"] for r in roles["roles"]} == {"teacher", "dept_head"}
    r = me.post("/api/me/role", {"role": "dept_head"})
    assert r.status == 200 and r.json["home"] == "/teacher" and sid_of(r) != first
    assert me.get("/api/me").json["role"] == "dept_head"
    assert app_db.client().get("/api/me", headers={"Cookie": f"zeka_sid={first}"}).status == 401
    assert any("teacher → dept_head" in d for d in audits("role_switched"))
    assert me.get("/api/teacher/home").status == 403          # legacy teacher routes do not include the new role
    assert me.post("/api/me/role", {"role": "teacher"}).status == 200 and me.get("/api/teacher/home").status == 200


def test_a_role_that_is_not_held_cannot_be_taken(app_db):
    me = app_db.client("teacher")
    assert me.post("/api/me/role", {"role": "admin"}).status == 403
    assert me.get("/api/me").json["role"] == "teacher"


def test_a_revoked_grant_ends_acting_in_that_role(app_db, db_user):
    office = db_user("office")
    admin = app_db.client("admin")
    gid = admin.post(f"/api/admin/users/{office['id']}/roles", {"role": "academic_office"}).json["id"]
    me = app_db.client("office")
    assert me.post("/api/me/role", {"role": "academic_office"}).status == 200
    assert admin.delete(f"/api/admin/users/{office['id']}/roles/{gid}").status == 200
    assert me.get("/api/me").json["role"] == "office"         # back to the primary role on the next request
    assert any("academic_office" in d for d in audits("role_revoked"))


def test_a_student_needs_a_second_factor_to_act_in_a_staff_role(app_db, db_user):
    student = db_user("student")
    app_db.client("admin").post(f"/api/admin/users/{student['id']}/roles", {"role": "proctor"})
    me = app_db.client("student")
    r = me.post("/api/me/role", {"role": "proctor"}, lang="en")
    assert r.status == 403 and "two-step" in r.json["error"].lower()


@pytest.mark.parametrize("body, status", [
    ({"role": "superuser"}, 400),
    ({"role": "office", "scope_type": "planet", "scope_id": 1}, 400),
    ({"role": "office", "scope_type": "faculty"}, 400),
    ({"role": "teacher"}, 409),                                # already the primary role
])
def test_grants_are_validated(app_db, db_user, body, status):
    teacher = db_user("teacher")
    assert app_db.client("admin").post(f"/api/admin/users/{teacher['id']}/roles", body).status == status


def test_only_an_admin_grants_roles_and_twice_is_a_conflict(app_db, db_user):
    teacher = db_user("teacher")
    for role in ("student", "teacher", "office", "leader"):
        assert app_db.client(role).post(f"/api/admin/users/{teacher['id']}/roles", {"role": "proctor"}).status == 403, role
    admin = app_db.client("admin")
    assert admin.post(f"/api/admin/users/{teacher['id']}/roles", {"role": "proctor"}).status == 200
    assert admin.post(f"/api/admin/users/{teacher['id']}/roles", {"role": "proctor"}).status == 409
    assert any("proctor" in d for d in audits("role_granted"))
