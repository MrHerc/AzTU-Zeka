"""Access control, redirects, one-time links and HTML escaping."""
import json
import re

import pytest

from app import common


# ---------------------------------------------------------------- authentication
@pytest.mark.parametrize("method, path", [
    ("GET", "/api/me"), ("GET", "/api/courses"), ("GET", "/api/notifications"), ("POST", "/api/tutor/1/ask"),
    ("GET", "/api/requests"), ("GET", "/api/support/tickets"), ("GET", "/doc/1"), ("GET", "/api/files/1"), ("GET", "/syllabus/1"),
])
def test_protected_routes_need_a_session(anon, method, path):
    assert anon.request(method, path, {} if method == "POST" else None).status == 401


@pytest.mark.parametrize("path", ["/api/bootstrap", "/api/achievements", "/api/contact", "/verify/AAAA-BBBB"])
def test_public_routes(anon, path):
    assert anon.get(path).status == 200


def test_session_token_header_works_like_the_cookie(app_db):
    token = app_db.client().post("/api/auth/demo", {"role": "teacher"}).json["token"]
    r = app_db.client().get("/api/me", headers={"X-Session": token})
    assert r.status == 200 and r.json["role"] == "teacher"


def test_logout_invalidates_the_session(app_db):
    c = app_db.client("student")
    assert c.get("/api/me").status == 200
    r = c.post("/api/auth/logout")
    assert r.status == 200 and "Max-Age=0" in r.headers["Set-Cookie"]
    assert c.get("/api/me").status == 401


@pytest.mark.parametrize("role", [None, "", "superuser", ["student"], {"r": 1}, 5])
def test_unknown_demo_roles_are_rejected(anon, role):
    # a list or dict used to crash the "role in logins" lookup (unhashable) with a 500
    assert anon.post("/api/auth/demo", {"role": role}).status == 400


def test_session_cookie_flags(app_db, monkeypatch):
    r = app_db.client().post("/api/auth/demo", {"role": "student"})
    ck = r.headers["Set-Cookie"]
    assert "HttpOnly" in ck and "SameSite=Lax" in ck and "Path=/" in ck and "Secure" not in ck
    monkeypatch.setitem(common.BASE_URL, "value", "https://zeka.example.az")
    assert "; Secure" in common.session_cookie("abc")[1]
    assert "Max-Age=0" in common.session_cookie(expire=True)[1]


# ---------------------------------------------------------------- roles
@pytest.mark.parametrize("role, path", [
    ("student", "/api/analytics"), ("teacher", "/api/analytics"), ("office", "/api/analytics"),
    ("student", "/api/admin/status"), ("leader", "/api/admin/status"), ("teacher", "/api/office/summary"),
    ("student", "/api/academy"), ("office", "/api/academy"), ("student", "/api/tools"), ("teacher", "/api/attendance"),
    ("student", "/api/feedback/summary"), ("teacher", "/api/support/summary"), ("student", "/api/news/manage"),
    ("teacher", "/api/documents"),
])
def test_role_guards(app_db, role, path):
    assert app_db.client(role).get(path).status == 403


def test_students_and_teachers_only_reach_their_own_courses(app_db, admin):
    # a course the demo teacher does not teach
    other = next(co for co in admin.get("/api/courses").json if co["teacher"] != app_db.client("teacher").get("/api/me").json["full_name"])
    assert app_db.client("teacher").get(f"/api/courses/{other['id']}").status == 403
    assert app_db.client("teacher").post(f"/api/tutor/{other['id']}/ask", {"message": "Salam"}).status == 403
    assert app_db.client("student").get("/api/courses/999").status == 404


def test_a_student_cannot_see_another_students_request(app_db, office):
    other = next(r for r in office.get("/api/requests?status=all").json if r["student"] != "Aysel Məmmədova")
    assert app_db.client("student").get(f"/api/requests/{other['id']}").status == 404
    assert app_db.client("teacher").get(f"/api/requests/{other['id']}").status == 404


# ---------------------------------------------------------------- demo login redirect
@pytest.mark.parametrize("nxt, expected", [
    ("/#/student/services", "/#/student/services"),
    ("//evil.example", "/"), ("/\\evil.example", "/"), ("https://evil.example", "/"), ("evil.example", "/"),
    ("/\t/evil.example", "/"),              # browsers drop TAB: "/\t/evil" becomes "//evil"
    ("/\n/evil.example", "/"),
    ("/x\r\nSet-Cookie: zeka_sid=attacker", "/"),   # CR/LF would have been written into the Location header
    ("/ə", "/"),                            # non-Latin-1 text crashed the header writer
])
def test_demo_login_redirect_only_to_safe_local_paths(app_db, nxt, expected):
    import http.client
    import urllib.parse

    conn = http.client.HTTPConnection("127.0.0.1", app_db.port, timeout=5)
    try:
        conn.request("GET", "/demo/login?role=student&next=" + urllib.parse.quote(nxt, safe=""))
        r = conn.getresponse()
        r.read()
        assert r.status == 302
        assert r.getheader("Location") == expected
        assert all("attacker" not in v for k, v in r.getheaders() if k.lower() == "set-cookie")
    finally:
        conn.close()


def test_demo_login_default_redirect_goes_to_the_role_home(app_db):
    import http.client

    conn = http.client.HTTPConnection("127.0.0.1", app_db.port, timeout=5)
    try:
        conn.request("GET", "/demo/login?role=office")
        r = conn.getresponse()
        r.read()
        assert r.status == 302 and r.getheader("Location") == "/#/office" and "zeka_sid=" in r.getheader("Set-Cookie")
    finally:
        conn.close()


# ---------------------------------------------------------------- syllabus page escaping
SYL_XSS = "<img src=x onerror=alert(1)>"


def test_syllabus_page_escapes_every_saved_value(app_db, teacher):
    syl = teacher.post("/api/syllabus/1/generate", {"weeks": 15}).json
    syl["plan"][0]["week"] = SYL_XSS
    syl["course"]["credits"] = SYL_XSS
    syl["workload"]["total"] = SYL_XSS
    syl["outcomes"][0] = SYL_XSS
    syl["assessment"][0][1] = 10
    assert teacher.put("/api/syllabus/1", {"data": syl}).status == 200
    page = teacher.get("/syllabus/1").text
    # regression: week, credits and workload numbers were interpolated into the HTML unescaped
    assert SYL_XSS not in page and "&lt;img src=x onerror=alert(1)&gt;" in page


@pytest.mark.parametrize("mutate", [
    lambda s: s.pop("plan"),
    lambda s: s.update(plan="not a list"),
    lambda s: s["plan"].append({"week": 16}),
    lambda s: s["assessment"].append(["x", "<b>50</b>"]),
    lambda s: s.pop("workload"),
    lambda s: s["course"].pop("name"),
])
def test_syllabus_save_rejects_incomplete_data(teacher, mutate):
    syl = teacher.post("/api/syllabus/1/generate", {"weeks": 15}).json
    mutate(syl)
    # regression: only the "course" key was checked, and a partial object broke the editor and the printable page
    assert teacher.put("/api/syllabus/1", {"data": syl}).status == 400
    assert teacher.get("/syllabus/1").status == 200


def test_syllabus_page_for_an_unknown_course_is_404(admin, leader):
    # regression: admin/leader skip the course-access check and the page crashed on None with a 500
    assert admin.get("/syllabus/999999").status == 404
    assert leader.get("/syllabus/999999").status == 404
    assert admin.get("/syllabus/1").status == 200


# ---------------------------------------------------------------- one-time keys
def test_one_time_document_link_is_single_use_and_scoped(app_db, student):
    reqs = student.get("/api/requests").json
    doc = next(r["document"] for r in reqs if r.get("document"))
    url = student.post(f"/api/documents/{doc['id']}/link").json["url"]
    assert re.fullmatch(rf"/doc/{doc['id']}\?k=[\w-]+", url)
    other_id = doc["id"] + 1
    assert app_db.client().get(url.replace(f"/doc/{doc['id']}", f"/doc/{other_id}")).status == 401   # key bound to its id
    assert app_db.client().get(url).status == 401                                                       # …and consumed by that try
    url = student.post(f"/api/documents/{doc['id']}/link").json["url"]
    assert app_db.client().get(url).status == 200
    assert app_db.client().get(url).status == 401


def test_one_time_keys_expire(app_db, monkeypatch):
    from datetime import timedelta

    key = common.make_key("doc", 1, 1)
    entry = common._DOC_KEYS[key]
    entry["exp"] = entry["exp"] - timedelta(minutes=10)
    assert app_db.client().get(f"/doc/1?k={key}").status == 401


def test_a_document_link_for_someone_elses_document_is_404(app_db, student, office):
    docs = office.get("/api/documents").json
    foreign = next(d for d in docs if d["holder"] != "Aysel Məmmədova")
    assert student.post(f"/api/documents/{foreign['id']}/link").status == 404
    assert student.get(f"/doc/{foreign['id']}").status == 403


def test_teachers_cannot_open_student_files(app_db, office):
    files = [a for r in office.get("/api/requests?status=all").json if r["files"]
             for a in office.get(f"/api/requests/{r['id']}").json["attachments"]]
    assert files
    assert app_db.client("teacher").get(f"/api/files/{files[0]['id']}").status == 403
    assert office.get(f"/api/files/{files[0]['id']}").status == 200


def test_json_responses_never_echo_raw_html_unescaped_in_html_pages(app_db, student):
    # user text is returned as JSON data (rendered by the client with escaping), not as server-rendered HTML
    r = student.post("/api/support/tickets", {"category": "other", "subject": "<script>x</script>", "body": "<b>body</b> text here"})
    assert r.status == 200 and r.headers["Content-Type"].startswith("application/json")
    assert json.loads(r.body)["subject"] == "<script>x</script>"
