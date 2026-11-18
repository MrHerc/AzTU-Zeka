"""The attendance journal (tasks/todo.md, Task 20, slice 1): one request marks a lesson, subgroups, the edit window,
corrections and substitutes by a department head, and the share of missed hours with its status.

A course of the current term with a lecture for group JR-1 (30 students) and a lab for its subgroup 2; its lessons are
written here directly with fixed dates around today."""
from datetime import date, timedelta

import pytest

from zeka.legacy import store
from zeka.modules.journal import service


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


def today() -> date:
    return store.now().date()


@pytest.fixture(scope="module")
def world(app_db):
    admin = app_db.client("admin")
    teacher = app_db.client("teacher")
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    fid = admin.get("/api/directory/faculties").json["items"][0]["id"]
    dep = admin.post("/api/directory/departments", {"faculty_id": fid, "code": "JRD", "name": "Jurnal kafedrası"}).json["id"]
    gid = admin.post("/api/directory/groups", {"name": "JR-1", "year": 2025, "faculty_id": fid}).json["id"]
    course = admin.post("/api/directory/courses", {"code": "JR-101", "name": "Jurnal sınağı", "credits": 5, "term_id": term["id"],
                                                   "department_id": dep, "teacher_id": teacher.user["id"]}).json["id"]
    units = {}
    for name, kind, sub in (("lecture", "lecture", None), ("lab2", "lab", 2)):
        units[name] = admin.post("/api/directory/units", {"course_id": course, "kind": kind, "teacher_id": teacher.user["id"], "subgroup": sub}).json["id"]
        admin.put(f"/api/directory/units/{units[name]}/groups", {"group_ids": [gid]})
    students = []
    for i in range(30):
        sid = admin.post("/api/directory/users", {"username": f"jr.s{i:02d}", "full_name": f"Jurnal Tələbə {i:02d}", "role": "student",
                                                  "group_id": gid, "student_no": f"JR-{i:02d}"}).json["id"]
        admin.post(f"/api/directory/courses/{course}/enrollments", {"user_id": sid, "subgroup": 1 if i < 15 else 2})
        students.append(sid)

    def lesson(day: date, unit="lecture", status="scheduled", hours=2):
        return run("INSERT INTO lessons(course_id,day,start,end,kind,unit_id,teacher_id,academic_hours,slot_day,slot_start,status) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?)", (course, day.isoformat(), "00:00", "00:30", "Mühazirə" if unit == "lecture" else "Laboratoriya",
                                                   units[unit], teacher.user["id"], hours, day.isoformat(), "00:00", status))

    t0 = today()
    ls = {"today": lesson(t0), "old": lesson(t0 - timedelta(days=3)), "lab": lesson(t0, unit="lab2"),
          "cancelled": lesson(t0 - timedelta(days=5), status="cancelled"), "future": lesson(t0 + timedelta(days=2))}
    for k in range(6, 26):
        if (t0 - timedelta(days=k)).isoformat() >= term["teaching_start"]:
            lesson(t0 - timedelta(days=k))
    ls["after_term"] = lesson(date.fromisoformat(term["teaching_end"]) + timedelta(days=3))
    return {"term": term, "course": course, "units": units, "students": students, "lessons": ls, "group": gid, "department": dep}


def standing_of(client, course, sid):
    return {x["student_id"]: x for x in client.get(f"/api/journal/courses/{course}/standing").json}[sid]


def test_a_lesson_of_thirty_is_marked_with_one_request_and_again_changes_nothing(app_db, world):
    teacher = app_db.client("teacher")
    lid = world["lessons"]["today"]
    view = teacher.get(f"/api/journal/lessons/{lid}").json
    assert len(view["students"]) == 30 and view["can_mark"] and not view["needs_reason"]
    s = world["students"]
    body = {"marks": {str(s[0]): "absent", str(s[1]): "late"}}
    assert teacher.put(f"/api/journal/lessons/{lid}/attendance", body).status == 200
    got = {x["user_id"]: x["status"] for x in q("SELECT user_id, status FROM attendance WHERE lesson_id=?", (lid,))}
    assert len(got) == 30 and got[s[0]] == "absent" and got[s[1]] == "late" and got[s[2]] == "present"
    audits = len(q("SELECT 1 FROM audit WHERE action LIKE 'attendance_%'"))
    assert teacher.put(f"/api/journal/lessons/{lid}/attendance", body).status == 200
    assert {x["user_id"]: x["status"] for x in q("SELECT user_id, status FROM attendance WHERE lesson_id=?", (lid,))} == got
    assert len(q("SELECT 1 FROM audit WHERE action LIKE 'attendance_%'")) == audits, "the same marks again change nothing"


def test_bad_marks_are_refused(app_db, world):
    teacher = app_db.client("teacher")
    lid = world["lessons"]["today"]
    other = q("SELECT id FROM users WHERE username='aysel'")[0]["id"]
    for marks in ({str(other): "absent"}, {str(world["students"][0]): "excused"}, ["x"], {"abc": "absent"}):
        assert teacher.put(f"/api/journal/lessons/{lid}/attendance", {"marks": marks}).status == 400, marks


def test_subgroup_one_is_not_on_subgroup_two_s_lab_nor_in_its_plan(app_db, world):
    teacher = app_db.client("teacher")
    lab = world["lessons"]["lab"]
    s = world["students"]
    assert {x["id"] for x in teacher.get(f"/api/journal/lessons/{lab}").json["students"]} == set(s[15:]), "only subgroup 2"
    assert teacher.put(f"/api/journal/lessons/{lab}/attendance", {"marks": {str(s[0]): "absent"}}).status == 400
    assert teacher.put(f"/api/journal/lessons/{lab}/attendance", {}).status == 200
    assert not q("SELECT 1 FROM attendance WHERE lesson_id=? AND user_id=?", (lab, s[0]))
    assert standing_of(teacher, world["course"], s[15])["planned_hours"] == standing_of(teacher, world["course"], s[0])["planned_hours"] + 2


def test_after_the_window_only_a_department_head_corrects_with_a_reason(app_db, world):
    teacher, admin = app_db.client("teacher"), app_db.client("admin")
    old = world["lessons"]["old"]
    s = world["students"]
    view = teacher.get(f"/api/journal/lessons/{old}").json
    assert not view["can_mark"] and not view["window_open"]
    assert teacher.put(f"/api/journal/lessons/{old}/attendance", {"marks": {str(s[3]): "absent"}}).status == 403
    assert admin.put(f"/api/journal/lessons/{old}/attendance", {"marks": {str(s[3]): "absent"}}).status == 400, "a reason"
    r = admin.put(f"/api/journal/lessons/{old}/attendance", {"marks": {str(s[3]): "absent"}, "reason": "Müəllimin yazılı müraciəti"})
    assert r.status == 200
    last = q("SELECT detail FROM audit WHERE action='attendance_corrected' ORDER BY id DESC LIMIT 1")[0]["detail"]
    assert f"#{old}" in last and "Müəllimin yazılı müraciəti" in last


def test_a_department_head_of_another_department_cannot_correct(app_db, world):
    admin = app_db.client("admin")
    teacher_id = app_db.client("teacher").user["id"]
    other = admin.post("/api/directory/departments", {"faculty_id": admin.get("/api/directory/faculties").json["items"][0]["id"],
                                                     "code": "JRX", "name": "Başqa kafedra"}).json["id"]
    gid = admin.post(f"/api/admin/users/{teacher_id}/roles", {"role": "dept_head", "scope_type": "department", "scope_id": other}).json["id"]
    try:
        head = app_db.client("teacher")
        assert head.post("/api/me/role", {"role": "dept_head"}).status == 200
        r = head.put(f"/api/journal/lessons/{world['lessons']['old']}/attendance", {"marks": {}, "reason": "Başqa kafedradan"})
        assert r.status == 403
    finally:
        admin.delete(f"/api/admin/users/{teacher_id}/roles/{gid}")


def test_a_substitute_teacher_needs_a_reason_and_then_marks_the_lesson(app_db, world):
    admin, teacher = app_db.client("admin"), app_db.client("teacher")
    leyla = q("SELECT id FROM users WHERE username='leyla'")[0]["id"]
    lid = world["lessons"]["today"]
    run("UPDATE lessons SET teacher_id=? WHERE id=?", (leyla, lid))
    try:
        assert teacher.post(f"/api/journal/lessons/{lid}/teacher", {"teacher_id": teacher.user["id"], "reason": "özüm"}).status == 403
        assert admin.post(f"/api/journal/lessons/{lid}/teacher", {"teacher_id": teacher.user["id"]}).status == 400
        r = admin.post(f"/api/journal/lessons/{lid}/teacher", {"teacher_id": teacher.user["id"], "reason": "Leyla xanım xəstədir"})
        assert r.status == 200 and r.json["lesson"]["teacher_id"] == teacher.user["id"]
        detail = q("SELECT detail FROM audit WHERE action='lesson_substitute' ORDER BY id DESC LIMIT 1")[0]["detail"]
        assert f"#{leyla} → #{teacher.user['id']}" in detail and "xəstədir" in detail
        assert teacher.put(f"/api/journal/lessons/{lid}/attendance", {}).status == 200, "the new teacher writes it"
        assert admin.post(f"/api/journal/lessons/{world['lessons']['old']}/teacher",
                          {"teacher_id": teacher.user["id"], "reason": "keçmiş dərs"}).status == 400
    finally:
        run("UPDATE lessons SET teacher_id=? WHERE id=?", (teacher.user["id"], lid))


def test_future_and_cancelled_lessons_are_not_written(app_db, world):
    teacher = app_db.client("teacher")
    for k in ("future", "cancelled"):
        assert teacher.put(f"/api/journal/lessons/{world['lessons'][k]}/attendance", {}).status == 403, k
    assert app_db.client("student").get(f"/api/journal/lessons/{world['lessons']['today']}").status == 403


def test_an_excused_absence_is_not_overwritten_by_a_mark(app_db, world):
    teacher = app_db.client("teacher")
    lid, sid = world["lessons"]["today"], world["students"][5]
    rid = run("INSERT INTO requests(type_code,student_id,data,status,step,created_at,updated_at) VALUES('absence_excuse',?,'{}','done',0,'x','x')",
              (sid,))
    run("UPDATE attendance SET status='excused', request_id=? WHERE lesson_id=? AND user_id=?", (rid, lid, sid))
    assert teacher.put(f"/api/journal/lessons/{lid}/attendance", {"marks": {str(sid): "absent"}}).status == 200
    assert q("SELECT status FROM attendance WHERE lesson_id=? AND user_id=?", (lid, sid))[0]["status"] == "excused"


def lecture_count(world, first, last):
    return q("SELECT COUNT(*) n FROM lessons WHERE course_id=? AND unit_id=? AND status='scheduled' AND day BETWEEN ? AND ?",
             (world["course"], world["units"]["lecture"], first, last))[0]["n"]


def test_the_share_counts_only_planned_lessons_of_the_enrolment(app_db, world):
    teacher = app_db.client("teacher")
    term = world["term"]
    s0 = standing_of(teacher, world["course"], world["students"][0])
    assert s0["planned_hours"] == 2 * lecture_count(world, term["teaching_start"], term["teaching_end"]), "no cancelled lesson, none after the term"
    absent = q("SELECT COUNT(*) n FROM attendance a JOIN lessons l ON l.id=a.lesson_id WHERE l.course_id=? AND a.user_id=? AND a.status='absent'",
               (world["course"], world["students"][0]))[0]["n"]
    assert s0["missed_hours"] == 2 * absent and s0["status"] in ("normal", "warning")
    late = world["students"][2]
    run("UPDATE enrollments SET begin_date=? WHERE user_id=? AND course_id=?", (today().isoformat(), late, world["course"]))
    try:
        assert standing_of(teacher, world["course"], late)["planned_hours"] == 2 * lecture_count(world, today().isoformat(), term["teaching_end"])
    finally:
        run("UPDATE enrollments SET begin_date=NULL WHERE user_id=? AND course_id=?", (late, world["course"]))


def test_the_status_follows_the_limit_and_the_syllabus_may_only_lower_it(app_db, world):
    teacher = app_db.client("teacher")
    sid = world["students"][7]
    held = q("SELECT id FROM lessons WHERE course_id=? AND unit_id=? AND status='scheduled' AND day<? ORDER BY day",
             (world["course"], world["units"]["lecture"], today().isoformat()))
    for x in held[:6]:                                                              # 12 hours missed
        run("INSERT INTO attendance(lesson_id,user_id,status) VALUES(?,?,'absent') ON CONFLICT(lesson_id,user_id) DO UPDATE SET status='absent'",
            (x["id"], sid))
    base = standing_of(teacher, world["course"], sid)
    planned = base["planned_hours"]
    assert base["missed_hours"] == 12 and base["limit_percent"] == 25
    assert base["status"] == ("not_admitted" if 1200 > 25 * planned else "warning" if 1200 > 20 * planned else "normal")
    run("UPDATE courses SET attendance_limit=10 WHERE id=?", (world["course"],))
    try:
        low = standing_of(teacher, world["course"], sid)
        assert low["limit_percent"] == 10 and (low["status"] == "not_admitted") == (1200 > 10 * planned)
        run("UPDATE courses SET attendance_limit=90 WHERE id=?", (world["course"],))
        assert standing_of(teacher, world["course"], sid)["limit_percent"] == 25, "a syllabus cannot raise the university's limit"
    finally:
        run("UPDATE courses SET attendance_limit=NULL WHERE id=?", (world["course"],))


def test_the_standing_is_seen_by_the_student_the_teacher_and_the_dean_s_office(app_db, world):
    rows = app_db.client("office").get(f"/api/journal/courses/{world['course']}/standing").json
    assert {x["student_id"] for x in rows} == set(world["students"]), "the faculty of the demo dean's office"
    demo = app_db.client("student").get("/api/attendance").json["courses"][0]
    assert {"planned_hours", "missed_hours", "percent", "status", "limit_percent", "allowed_hours"} <= set(demo)
    assert app_db.client("student").get(f"/api/journal/courses/{world['course']}/standing").status == 403
    c = store.connect()
    try:
        leyla = store.row(c, "SELECT * FROM users WHERE username='leyla'")
        assert not service.can_read_course(c, leyla, world["course"]), "another teacher does not read this course"
    finally:
        c.close()


def test_the_edit_window_is_a_university_setting(app_db):
    admin = app_db.client("admin")
    journal = admin.get("/api/admin/settings").json["journal"]
    assert journal["edit_hours"] == 48
    for bad in (0, 721, True, "48"):
        assert admin.put("/api/admin/settings/journal", {"value": {**journal, "edit_hours": bad}}).status == 400, bad
    assert admin.put("/api/admin/settings/journal", {"value": {**journal, "edit_hours": 72}}).status == 200
    admin.put("/api/admin/settings/journal", {"value": journal})
