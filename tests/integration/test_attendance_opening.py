"""Opening balances and imported lesson rows (tasks/todo.md, Task 20, slice 2): a term that started in the old system.

Course JO-101: 50 lectures of 2 academic hours, one a day up to today (100 planned hours); the cut-over date is 20 days
ago, so 30 lessons (60 hours) are before it. The source system "kts" names the term, the course and the students; its
links are written here directly, as Task 16's imports of those kinds would."""
import base64
import csv
import io
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


HEADER = ["termSourcedId", "courseSourcedId", "userSourcedId", "heldHours", "unexcusedHours", "excusedHours", "asOf"]


def csv_b64(rows) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(HEADER)
    w.writerows(rows)
    return base64.b64encode(out.getvalue().encode()).decode()


def imp(admin, rows, dry_run=False, prefer=False):
    return admin.post("/api/admin/import", {"kind": "attendance-opening", "source": "kts", "filename": "qaliq.csv",
                                            "content_b64": csv_b64(rows), "dry_run": dry_run, "prefer_source": prefer})


@pytest.fixture(scope="module")
def world(app_db):
    admin, teacher = app_db.client("admin"), app_db.client("teacher")
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    fid = admin.get("/api/directory/faculties").json["items"][0]["id"]
    gid = admin.post("/api/directory/groups", {"name": "JO-1", "year": 2025, "faculty_id": fid}).json["id"]
    course = admin.post("/api/directory/courses", {"code": "JO-101", "name": "Qalıq sınağı", "credits": 5, "term_id": term["id"],
                                                   "teacher_id": teacher.user["id"]}).json["id"]
    unit = admin.post("/api/directory/units", {"course_id": course, "kind": "lecture", "teacher_id": teacher.user["id"]}).json["id"]
    admin.put(f"/api/directory/units/{unit}/groups", {"group_ids": [gid]})
    students = {}
    for i in range(1, 8):
        sid = admin.post("/api/directory/users", {"username": f"jo.s{i}", "full_name": f"Qalıq Tələbə {i}", "role": "student",
                                                  "group_id": gid, "student_no": f"JO-{i}"}).json["id"]
        admin.post(f"/api/directory/courses/{course}/enrollments", {"user_id": sid})
        students[i] = sid
    today = store.now().date()
    assert (today - timedelta(days=49)).isoformat() >= term["teaching_start"], "the demo term is long enough"
    lessons = []
    for k in range(49, -1, -1):
        d = (today - timedelta(days=k)).isoformat()
        lessons.append({"id": run("INSERT INTO lessons(course_id,day,start,end,kind,unit_id,teacher_id,academic_hours,slot_day,slot_start) "
                                  "VALUES(?,?,'00:00','00:30','Mühazirə',?,?,2,?,'00:00')", (course, d, unit, teacher.user["id"], d)), "day": d})
    as_of = (today - timedelta(days=20)).isoformat()
    for kind, sid_, rid in [("terms", "T-OP", term["id"]), ("courses", "C-OP", course)] + [("users", f"S-OP-{i}", students[i]) for i in students]:
        run("INSERT INTO import_links(kind,source_system,source_id,row_id,source_hash,imported_at) VALUES(?,?,?,?,?,?)",
            (kind, "kts", sid_, rid, "-", store.iso(store.now())))
    journal = admin.get("/api/admin/settings").json["journal"]
    assert admin.put("/api/admin/settings/journal", {"value": {**journal, "cutover_date": as_of}}).status == 200
    yield {"course": course, "students": students, "lessons": lessons, "as_of": as_of, "term": term}
    admin.put("/api/admin/settings/journal", {"value": journal})


def absent(world, sid, lessons):
    for x in lessons:
        run("INSERT INTO attendance(lesson_id,user_id,status) VALUES(?,?,'absent') ON CONFLICT(lesson_id,user_id) DO UPDATE SET status='absent'",
            (x["id"], sid))


def mine(app_db, world, i):
    rows = app_db.client("teacher").get(f"/api/journal/courses/{world['course']}/standing").json
    return {x["student_id"]: x for x in rows}[world["students"][i]]


def after(world):
    return [x for x in world["lessons"] if x["day"] > world["as_of"]]


def test_twenty_percent_imported_and_six_in_zeka_is_not_admitted(app_db, world):
    admin = app_db.client("admin")
    rep = imp(admin, [["T-OP", "C-OP", "S-OP-1", 60, 20, 0, world["as_of"]]]).json
    assert rep["written"] and rep["inserted"] == 1 and rep["warnings"] == [], rep
    absent(world, world["students"][1], after(world)[:3])                    # 6 hours after the cut-over
    s = mine(app_db, world, 1)
    assert (s["planned_hours"], s["missed_hours"], s["status"], s["as_of"]) == (100, 26, "not_admitted", world["as_of"])


def test_the_same_file_again_changes_nothing(app_db, world):
    rep = imp(app_db.client("admin"), [["T-OP", "C-OP", "S-OP-1", 60, 20, 0, world["as_of"]]]).json
    assert rep["inserted"] == rep["updated"] == 0 and rep["unchanged"] == 1 and not rep["conflicts"]


def test_a_later_cut_over_does_not_count_zeka_records_before_it_twice(app_db, world):
    admin = app_db.client("admin")
    sid = world["students"][2]
    assert imp(admin, [["T-OP", "C-OP", "S-OP-2", 60, 4, 0, world["as_of"]]]).json["inserted"] == 1
    absent(world, sid, after(world)[:5])                                     # 10 hours in Zəka, the first 5 days after the cut-over
    assert mine(app_db, world, 2)["missed_hours"] == 14
    later = after(world)[4]["day"]                                           # the old system kept going 5 more days and counted them
    rep = imp(admin, [["T-OP", "C-OP", "S-OP-2", 70, 14, 0, later]]).json
    assert rep["updated"] == 1, rep
    s = mine(app_db, world, 2)
    assert s["missed_hours"] == 14 and s["as_of"] == later, "the 10 hours are in the new balance, not counted again"


def test_imported_lesson_rows_and_an_opening_balance_give_the_same_standing(app_db, world):
    admin = app_db.client("admin")
    before = [x for x in world["lessons"] if x["day"] <= world["as_of"]]
    s3, s4 = world["students"][3], world["students"][4]
    for i, x in enumerate(before):                                           # 5 absences (10 hours), the rest present, as legacy rows
        run("INSERT INTO attendance(lesson_id,user_id,status,source,as_of) VALUES(?,?,?,'legacy',?)",
            (x["id"], s3, "absent" if i < 5 else "present", world["as_of"]))
    assert imp(admin, [["T-OP", "C-OP", "S-OP-4", 60, 10, 0, world["as_of"]]]).json["inserted"] == 1
    for sid in (s3, s4):
        absent(world, sid, after(world)[:2])
    keys = ("planned_hours", "missed_hours", "percent", "status")
    assert {k: mine(app_db, world, 3)[k] for k in keys} == {k: mine(app_db, world, 4)[k] for k in keys}


def test_nothing_imported_before_the_cut_over_is_incomplete(app_db, world):
    absent(world, world["students"][5], after(world)[:8])                    # 16 of 100 hours: would be a warning
    assert mine(app_db, world, 5)["status"] == "incomplete"


def test_a_teacher_changes_neither_an_opening_nor_an_imported_row(app_db, world):
    teacher, admin = app_db.client("teacher"), app_db.client("admin")
    oid = mine(app_db, world, 1)["opening_id"]
    assert teacher.put(f"/api/journal/openings/{oid}", {"unexcused_hours": 0, "reason": "səhv"}).status == 403
    legacy_lesson = [x for x in world["lessons"] if x["day"] <= world["as_of"]][0]["id"]
    assert teacher.put(f"/api/journal/lessons/{legacy_lesson}/attendance", {}).status == 403
    assert admin.put(f"/api/journal/openings/{oid}", {"unexcused_hours": 18}).status == 400, "a reason"
    assert admin.put(f"/api/journal/openings/{oid}", {"unexcused_hours": 70, "reason": "Köhnə sistemin hesabatı"}).status == 400
    r = admin.put(f"/api/journal/openings/{oid}", {"unexcused_hours": 18, "reason": "Köhnə sistemin kağız jurnalı"})
    assert r.status == 200 and mine(app_db, world, 1)["missed_hours"] == 24
    s3 = world["students"][3]
    r = admin.put(f"/api/journal/lessons/{legacy_lesson}/attendance", {"marks": {}, "reason": "Arayış təqdim edilib"})
    assert r.status == 200
    row = q("SELECT status, source FROM attendance WHERE lesson_id=? AND user_id=?", (legacy_lesson, s3))[0]
    assert row == {"status": "present", "source": "legacy"}, "a corrected imported row keeps its source"


def test_a_balance_changed_in_zeka_is_a_conflict_on_the_next_import(app_db, world):
    rep = imp(app_db.client("admin"), [["T-OP", "C-OP", "S-OP-1", 60, 20, 0, world["as_of"]]]).json
    assert rep["updated"] == 0 and len(rep["conflicts"]) == 1
    assert mine(app_db, world, 1)["unexcused_hours"] >= 18


def test_held_hours_other_than_zeka_s_plan_are_reported_by_row(app_db, world):
    rep = imp(app_db.client("admin"), [["T-OP", "C-OP", "S-OP-6", 60, 0, 0, world["as_of"]], ["T-OP", "C-OP", "S-OP-7", 50, 2, 0, world["as_of"]]],
              dry_run=True).json
    assert [w["row"] for w in rep["warnings"]] == [3] and "50" in str(rep["warnings"][0]["reason"])


def test_bad_rows_are_refused(app_db, world):
    admin = app_db.client("admin")
    for bad in (["T-OP", "C-OP", "S-OP-6", 10, 8, 4, world["as_of"]], ["T-OP", "C-OP", "S-OP-6", -1, 0, 0, world["as_of"]],
                ["T-OP", "C-OP", "S-OP-6", 10, 0, 0, "dünən"], ["T-OP", "YOX", "S-OP-6", 10, 0, 0, world["as_of"]],
                ["T-OP", "C-OP", "S OP", 10, 0, 0, world["as_of"]]):
        rep = imp(admin, [bad], dry_run=True).json
        assert rep["error_count"] == 1, bad
