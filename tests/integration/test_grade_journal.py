"""The grade journal (tasks/todo.md, Task 21): cell checks, who writes whose scores, the attendance component from the
journal, drafts and publishing, the log of changes after publishing, final grades, the grades import and the debts.

Course GJ-101 of the current term: the demo teacher's lecture for group GJ-1 (the demo student Aysel joins it here) and
another teacher's seminar for group GJ-2."""
import base64
import csv
import io
from datetime import timedelta

import pytest

from zeka.legacy import store

SCHEME = ["Davamiyyət", "Sərbəst iş 1", "Sərbəst iş 2", "Laboratoriya / məşğələ", "Kollokvium 1", "Kollokvium 2", "İmtahan"]


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
def world(app_db):
    admin, teacher, student = app_db.client("admin"), app_db.client("teacher"), app_db.client("student")
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    fid = admin.get("/api/directory/faculties").json["items"][0]["id"]
    g1 = admin.post("/api/directory/groups", {"name": "GJ-1", "year": 2025, "faculty_id": fid}).json["id"]
    g2 = admin.post("/api/directory/groups", {"name": "GJ-2", "year": 2025, "faculty_id": fid}).json["id"]
    leyla = q("SELECT id FROM users WHERE username='leyla'")[0]["id"]
    course = admin.post("/api/directory/courses", {"code": "GJ-101", "name": "Qiymət sınağı", "credits": 6, "term_id": term["id"],
                                                   "teacher_id": teacher.user["id"]}).json["id"]
    lec = admin.post("/api/directory/units", {"course_id": course, "kind": "lecture", "teacher_id": teacher.user["id"]}).json["id"]
    sem = admin.post("/api/directory/units", {"course_id": course, "kind": "seminar", "teacher_id": leyla}).json["id"]
    admin.put(f"/api/directory/units/{lec}/groups", {"group_ids": [g1]})
    admin.put(f"/api/directory/units/{sem}/groups", {"group_ids": [g2]})
    students = {}
    for name, grp in (("gj.a", g1), ("gj.b", g1), ("gj.c", g2)):
        students[name] = admin.post("/api/directory/users", {"username": name, "full_name": f"Qiymət {name}", "role": "student", "group_id": grp,
                                                             "student_no": name.upper()}).json["id"]
        admin.post(f"/api/directory/courses/{course}/enrollments", {"user_id": students[name]})
    students["aysel"] = student.user["id"]
    admin.post(f"/api/directory/courses/{course}/enrollments", {"user_id": student.user["id"], "group_id": g1})
    today = store.now().date()
    for k in range(1, 11):                                                   # 10 held lectures of 2 hours: 20 hours
        d = (today - timedelta(days=k)).isoformat()
        lid = run("INSERT INTO lessons(course_id,day,start,end,kind,unit_id,teacher_id,academic_hours,slot_day,slot_start) "
                  "VALUES(?,?,'00:00','00:30','Mühazirə',?,?,2,?,'00:00')", (course, d, lec, teacher.user["id"], d))
        for sid in (students["gj.a"], students["gj.b"], students["aysel"]):
            run("INSERT INTO attendance(lesson_id,user_id,status) VALUES(?,?,?)", (lid, sid, "absent" if sid == students["gj.b"] and k <= 2 else "present"))
    return {"course": course, "students": students, "term": term, "lec": lec, "sem": sem}


def put(client, world, cells, reason=None, lang=None):
    body = {"cells": [{"student_id": s, "component": c, "score": v} for s, c, v in cells]}
    if reason is not None:
        body["reason"] = reason
    return client.put(f"/api/journal/courses/{world['course']}/grades", body, lang=lang)


def row_of(table, sid):
    return next(s for s in table["students"] if s["id"] == sid)


def test_the_table_has_the_scheme_and_the_teacher_s_own_students(app_db, world):
    t = app_db.client("teacher").get(f"/api/journal/courses/{world['course']}/grades").json
    assert [c["key"] for c in t["columns"]] == SCHEME
    s = world["students"]
    assert row_of(t, s["gj.a"])["writable"] and not row_of(t, s["gj.c"])["writable"]


def test_a_cell_out_of_range_or_not_a_number_is_refused_with_its_reason(app_db, world):
    teacher, s = app_db.client("teacher"), world["students"]
    r = put(teacher, world, [(s["gj.a"], "Sərbəst iş 1", 7), (s["gj.a"], "Kollokvium 1", "on"), (s["gj.a"], "Sərbəst iş 2", 3)], lang="en")
    assert r.status == 400
    bad = {x["component"]: x["reason"] for x in r.json["cells"]}
    assert set(bad) == {"Sərbəst iş 1", "Kollokvium 1"} and "between 0 and 5" in bad["Sərbəst iş 1"] and "number" in bad["Kollokvium 1"]
    assert not q("SELECT 1 FROM grades WHERE user_id=? AND course_id=?", (s["gj.a"], world["course"])), "nothing of a refused save is written"


def test_a_teacher_writes_only_the_students_of_their_own_units(app_db, world):
    assert put(app_db.client("teacher"), world, [(world["students"]["gj.c"], "Sərbəst iş 1", 4)]).status == 403


def test_the_attendance_component_is_computed_and_follows_the_rule(app_db, world):
    teacher, admin, s = app_db.client("teacher"), app_db.client("admin"), world["students"]
    r = put(teacher, world, [(s["gj.a"], "Davamiyyət", 10)])
    assert r.status == 400 and r.json["cells"][0]["component"] == "Davamiyyət"
    table = teacher.get(f"/api/journal/courses/{world['course']}/grades").json
    assert row_of(table, s["gj.a"])["attendance"] == 10.0 and row_of(table, s["gj.b"])["attendance"] == 8.0    # 4 of 20 hours missed
    att = admin.get("/api/admin/settings").json["attendance"]
    assert admin.put("/api/admin/settings/attendance", {"value": {**att, "points_rule": [[10, 10], [30, 6]]}}).status == 200
    try:
        assert row_of(teacher.get(f"/api/journal/courses/{world['course']}/grades").json, s["gj.b"])["attendance"] == 6.0
    finally:
        admin.put("/api/admin/settings/attendance", {"value": att})


def test_imported_absences_before_the_cut_over_lower_the_attendance_component(app_db, world):
    teacher, s = app_db.client("teacher"), world["students"]
    as_of = (store.now().date() - timedelta(days=30)).isoformat()
    oid = run("INSERT INTO attendance_opening(student_id,course_id,term_id,held_hours,unexcused_hours,excused_hours,as_of,created_at,updated_at) "
              "VALUES(?,?,?,20,6,0,?,'x','x')", (s["gj.a"], world["course"], world["term"]["id"], as_of))
    try:
        assert row_of(teacher.get(f"/api/journal/courses/{world['course']}/grades").json, s["gj.a"])["attendance"] == 7.0    # 6 of 20 missed
    finally:
        run("DELETE FROM attendance_opening WHERE id=?", (oid,))


def aysel_items(app_db, world):
    g = next(x for x in app_db.client("student").get("/api/grades").json["courses"] if x["id"] == world["course"])
    return {i["name"]: i["score"] for i in g["items"]}, g["result"]


def test_a_draft_is_seen_by_the_student_only_once_published(app_db, world):
    teacher, s = app_db.client("teacher"), world["students"]
    assert put(teacher, world, [(s["aysel"], "Sərbəst iş 1", "4,5"), (s["aysel"], "Kollokvium 1", 9)]).status == 200
    assert aysel_items(app_db, world)[0]["Sərbəst iş 1"] is None, "a draft"
    r = teacher.post(f"/api/journal/courses/{world['course']}/grades/publish")
    assert r.status == 200 and r.json["drafts"] == 0
    items, _ = aysel_items(app_db, world)
    assert items["Sərbəst iş 1"] == 4.5 and items["Kollokvium 1"] == 9.0


def test_a_change_after_publishing_needs_a_reason_and_is_logged(app_db, world):
    teacher, s = app_db.client("teacher"), world["students"]
    assert put(teacher, world, [(s["aysel"], "Kollokvium 1", 7)]).status == 400
    assert put(teacher, world, [(s["aysel"], "Kollokvium 1", 7)], reason="Yenidən yoxlama").status == 200
    log = teacher.get(f"/api/journal/courses/{world['course']}/grades/log").json
    assert {k: log[0][k] for k in ("component", "old_score", "new_score", "reason")} == {"component": "Kollokvium 1", "old_score": 9.0,
                                                                                        "new_score": 7.0, "reason": "Yenidən yoxlama"}
    assert log[0]["changed_by"] == teacher.user["id"]
    assert aysel_items(app_db, world)[0]["Kollokvium 1"] == 7.0


def test_the_final_grade_follows_the_scheme_and_the_exam_minimum(app_db, world):
    teacher, admin, s = app_db.client("teacher"), app_db.client("admin"), world["students"]
    sid = s["gj.a"]
    cells = [(sid, "Sərbəst iş 1", 5), (sid, "Sərbəst iş 2", 5), (sid, "Laboratoriya / məşğələ", 9), (sid, "Kollokvium 1", 9),
             (sid, "Kollokvium 2", 8), (sid, "İmtahan", 40)]
    assert put(teacher, world, cells).status == 200
    assert not q("SELECT 1 FROM final_grades WHERE user_id=? AND course_id=?", (sid, world["course"])), "no final grade from drafts"
    teacher.post(f"/api/journal/courses/{world['course']}/grades/publish")
    f = q("SELECT * FROM final_grades WHERE user_id=? AND course_id=?", (sid, world["course"]))[0]
    assert f["score"] == 10 + 5 + 5 + 9 + 9 + 8 + 40 == 86 and f["letter"] == "B" and f["passed"] == 1 and f["credits"] == 6
    grading = admin.get("/api/admin/settings").json["grading"]
    assert admin.put("/api/admin/settings/grading", {"value": {**grading, "exam": {**grading["exam"], "min": 45}}}).status == 200
    try:
        assert put(teacher, world, [(sid, "İmtahan", 39)], reason="Apellyasiya").status == 200
        f = q("SELECT * FROM final_grades WHERE user_id=? AND course_id=?", (sid, world["course"]))[0]
        assert f["letter"] == "F" and f["passed"] == 0, "below the exam minimum"
        debts = app_db.client("office").get("/api/journal/debts").json
        assert any(x["user_id"] == sid and x["course_name"] == "Qiymət sınağı" for x in debts)
        csv_text = app_db.client("office").get("/api/journal/debts?format=csv").text
        assert "GJ.A" in csv_text and "Qiymət sınağı" in csv_text
        assert app_db.client("teacher").get("/api/journal/debts").status == 403
    finally:
        admin.put("/api/admin/settings/grading", {"value": grading})


def grades_csv(rows) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["courseSourcedId", "userSourcedId", "component", "score", "max", "asOf"])
    w.writerows(rows)
    return base64.b64encode(out.getvalue().encode()).decode()


def test_imported_scores_are_legacy_and_the_same_file_changes_nothing(app_db, world):
    admin, s = app_db.client("admin"), world["students"]
    for kind, sid_, rid in (("courses", "GJ", world["course"]), ("users", "GB", s["gj.b"])):
        run("INSERT INTO import_links(kind,source_system,source_id,row_id,source_hash,imported_at) VALUES(?,?,?,?,'-','x')", (kind, "kts", sid_, rid))
    body = {"kind": "grades", "source": "kts", "filename": "ballar.csv", "dry_run": False, "prefer_source": False,
            "content_b64": grades_csv([["GJ", "GB", "Kollokvium 1", "8", "10", "2026-10-01"], ["GJ", "GB", "Referat", "5", "5", ""]])}
    bad = admin.post("/api/admin/import", body).json
    assert [e["row"] for e in bad["errors"]] == [3] and not bad["written"], "a component the scheme does not have"
    body["content_b64"] = grades_csv([["GJ", "GB", "Kollokvium 1", "8", "10", "2026-10-01"]])
    assert admin.post("/api/admin/import", body).json["inserted"] == 1
    g = q("SELECT * FROM grades WHERE user_id=? AND course_id=? AND component='Kollokvium 1'", (s["gj.b"], world["course"]))[0]
    assert g["source"] == "legacy" and g["status"] == "published" and g["entered_by"] == admin.user["id"] and g["as_of"] == "2026-10-01"
    assert g["reason"].startswith("import:ballar.csv:") and len(g["reason"]) == len("import:ballar.csv:") + 64
    again = admin.post("/api/admin/import", body).json
    assert again["inserted"] == again["updated"] == 0
    cell = row_of(app_db.client("teacher").get(f"/api/journal/courses/{world['course']}/grades").json, s["gj.b"])["cells"]["Kollokvium 1"]
    assert cell == {"score": 8.0, "status": "published", "source": "legacy"}
