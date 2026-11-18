"""University settings (tasks/todo.md, Task 17): the grading scheme, attendance rules, register prefix and profile are
settings, so a second (made-up) university runs on the same code, and the old constants are gone from the code."""
import re
from pathlib import Path

import pytest

from zeka.legacy import store

ROOT = Path(__file__).resolve().parents[2]


def db():
    return store.connect()


def q(sql, args=()):
    c = db()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


SCHEME = {"components": [{"name": "Kollokvium", "max": 30}, {"name": "Sərbəst iş", "max": 10},
                         {"name": "Davamiyyət", "max": 10, "attendance": True}],
          "exam": {"name": "İmtahan", "max": 50, "min": 17}, "pass_mark": 51,
          "scale": [["A", 91], ["B", 81], ["C", 71], ["D", 61], ["E", 51]]}


def put(admin, section, value):
    return admin.put(f"/api/admin/settings/{section}", {"value": value})


@pytest.fixture(scope="module")
def marks(app_db):
    """Aysel's points in her first course under the new scheme's component names."""
    sid = app_db.client("student").user["id"]
    cid = q("SELECT course_id FROM enrollments WHERE user_id=? ORDER BY course_id LIMIT 1", (sid,))[0]["course_id"]
    c = db()
    try:
        for comp, score, mx in (("Kollokvium", 28, 30), ("Sərbəst iş", 9, 10), ("İmtahan", 16, 50)):
            c.execute("INSERT OR REPLACE INTO grades(user_id,course_id,component,score,max,updated_at) VALUES(?,?,?,?,?,?)",
                      (sid, cid, comp, score, mx, store.iso(store.now())))
        c.commit()
    finally:
        c.close()
    return cid


def result(student, cid):
    return next(x for x in student.get("/api/grades").json["courses"] if x["id"] == cid)


def test_changing_the_scheme_changes_the_result_without_a_code_change(app_db, marks):
    admin, student = app_db.client("admin"), app_db.client("student")
    before = result(student, marks)
    assert [i["name"] for i in before["items"]][:2] == ["Davamiyyət", "Sərbəst iş 1"], "the university's own scheme"
    assert put(admin, "grading", SCHEME).status == 200
    now = result(student, marks)
    assert [i["name"] for i in now["items"]] == ["Kollokvium", "Sərbəst iş", "Davamiyyət"]
    assert now["result"]["exam"] == 16 and now["result"]["letter"] == "F" and now["result"]["reason"] == "exam_min"
    assert now["result"] != before["result"]
    assert put(admin, "grading", {**SCHEME, "exam": {**SCHEME["exam"], "min": 15}}).status == 200
    passed = result(student, marks)["result"]
    assert passed["passed"] is (passed["total"] >= 51) and passed["reason"] in (None, "pass_mark")
    assert app_db.client().get("/api/bootstrap").json["app"]["grading"]["pass_mark"] == 51


def test_a_scheme_that_does_not_add_up_is_refused(app_db):
    admin = app_db.client("admin")
    assert put(admin, "grading", {**SCHEME, "exam": {**SCHEME["exam"], "max": 40}}).status == 400, "90 points in all"
    assert put(admin, "grading", {**SCHEME, "scale": [["A", 91], ["B", 81]]}).status == 400, "the scale must end at the pass mark"
    assert put(admin, "grading", {**SCHEME, "exam": {**SCHEME["exam"], "min": 60}}).status == 400
    assert put(admin, "attendance", {"limit_percent": 0}).status == 400
    assert put(admin, "calendar", {"lesson_times": [["10:00", "09:00"]]}).status == 400
    assert put(admin, "registry", {"prefix": "X"}).status == 400
    assert put(admin, "sso", {"enabled": True, "issuer": "http://idp.example", "client_id": "x"}).status == 400
    assert put(admin, "planets", {}).status == 404
    assert put(app_db.client("teacher"), "registry", {"prefix": "ABC"}).status == 403
    assert app_db.client("office").get("/api/admin/settings").status == 403


def test_the_attendance_rule_gives_the_points(app_db, marks):
    admin, student = app_db.client("admin"), app_db.client("student")
    assert put(admin, "grading", SCHEME).status == 200
    assert put(admin, "attendance", {"limit_percent": 30, "excused_counts_toward_limit": False,
                                     "points_rule": [[0, 10], [10, 8], [25, 5]]}).status == 200
    att = next(i for i in result(student, marks)["items"] if i["name"] == "Davamiyyət")
    assert att["score"] in (10, 8, 5, 0)
    a = student.get("/api/attendance").json
    assert a["limit_percent"] == 30 and all(x["limit_percent"] == 30 and x["counted"] == x["absent"] for x in a["courses"])


def test_a_second_made_up_university_runs_on_the_same_code(app_db):
    admin = app_db.client("admin")
    profile = {"name": "Xəzər Texnologiya Universiteti", "name_en": "Khazar Technology University", "short": "XTU",
               "platform": "Zəka", "semester": "2027 yaz semestri", "address": "Atatürk prospekti 1, Gəncə", "site": "xtu.example",
               "city": "Gəncə", "city_en": "Ganja"}
    assert put(admin, "university", profile).status == 200
    assert put(admin, "registry", {"prefix": "XTU"}).status == 200
    assert put(admin, "calendar", {"lesson_times": [["08:30", "09:50"], ["10:00", "11:20"]], "holidays": ["2027-03-21"]}).status == 200
    assert put(admin, "journal", {"cutover_date": "2027-02-15"}).status == 200
    assert app_db.client().get("/api/bootstrap").json["app"]["university"]["short"] == "XTU"
    c = db()
    try:
        sid = store.row(c, "SELECT id FROM users WHERE username='aysel'")["id"]
        office = store.row(c, "SELECT id FROM users WHERE username=?", (store.setting(c, "demo_logins")["office"],))["id"]
        doc = store.issue_document(c, "request", sid, "Transkript", {"type": "transcript", "lang": "Azərbaycan dili"}, office, "TR")
        c.commit()
    finally:
        c.close()
    assert doc["reg_no"].startswith("XTU-TR-")
    page = app_db.client("office").get(f"/doc/{doc['id']}").text
    assert "Gəncə" in page and 'alt="XTU"' in page and "XƏZƏR TEXNOLOGIYA" in page.upper()
    assert "Qiymət şkalası: A 91–100" in page and "51 baldan aşağı" in page
    verify = app_db.client().get(f"/verify/{doc['verify_code']}").text
    assert "XTU" in verify and "AzTU" not in verify
    s = admin.get("/api/admin/settings").json
    assert s["calendar"]["holidays"] == ["2027-03-21"] and s["journal"]["cutover_date"] == "2027-02-15"
    assert any(r["detail"] == "registry" for r in q("SELECT detail FROM audit WHERE action='settings_change'"))


FILES = ["backend/zeka/legacy/r_academy.py", "backend/zeka/legacy/docs.py", "backend/zeka/legacy/r_learning.py",
         "backend/zeka/legacy/store.py", "backend/zeka/legacy/radar.py", "frontend/js/student.js"]
OLD = [r"SEM_WEEKS", r"\bPREREQ\b", r"setting\(c, \"semester_start\"\)", r"\"semester_start\"", r"f\"AzTU-", r"\* 0\.25\b", r"rate / 0\.25",
       r"91–100", r"score >= 91", r"alt=\"AzTU\"", r"'Bakı'", r"\(25%\)", r">= 81\b", r"25%-ni", r"\"AzTU kampus"]


@pytest.mark.parametrize("path", FILES)
def test_the_old_constants_are_gone(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    found = [p for p in OLD if re.search(p, text)]
    assert not found, found
