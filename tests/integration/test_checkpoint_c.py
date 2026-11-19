"""Checkpoint C (review of Tasks 18-22 and 45): one regression test per confirmed finding, each failing on the code
before its fix (19e3ff8). The ids (D1 ...) are those of docs/review/checkpoint-c-2026-11-19.md."""
import json
import time
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit

import pytest

from zeka.core import security
from zeka.legacy import store


def db():
    return store.connect()


def q(sql, args=()):
    c = db()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def run(sql, args=()):
    c = db()
    try:
        c.execute(sql, args)
        c.commit()
    finally:
        c.close()


@pytest.fixture(scope="module")
def issued(app_db):
    """A certificate of enrolment issued to the demo student through the office's flow."""
    student, office = app_db.client("student"), app_db.client("office")
    rid = student.post("/api/requests", {"type_code": "enrollment_certificate", "data": {"purpose": "Bank", "lang": "Azərbaycan dili",
                                                                                         "copies": "1", "delivery": "Elektron (QR kodlu PDF)"}}).json["id"]
    office.post(f"/api/requests/{rid}/action", {"action": "approve"})
    doc = office.post(f"/api/requests/{rid}/action", {"action": "issue"}).json["document"]
    return q("SELECT * FROM documents WHERE id=?", (doc["id"],))[0]


# ---------------------------------------------------------------- D. documents
def test_d1_verify_shows_the_university_as_it_was_at_issue(app_db, issued):
    c = db()
    keep = store.setting(c, "university")
    store.set_setting(c, "university", {**keep, "name": "Başqa Universitet", "short": "BMU"})
    c.commit()
    try:
        page = app_db.client().get(f"/verify/{issued['verify_code']}").text
        assert "etibarlıdır" in page and "BMU" not in page and "Başqa Universitet" not in page
    finally:
        store.set_setting(c, "university", keep)
        c.commit()
        c.close()


def test_d3_a_non_ascii_hash_is_reported_changed_not_a_400(app_db, issued):
    run("UPDATE documents SET hash=? WHERE id=?", ("ə" * 64, issued["id"]))
    try:
        r = app_db.client().get(f"/verify/{issued['verify_code']}")
        assert r.status == 200 and "Sənəd dəyişdirilib" in r.text
        assert app_db.client("office").get(f"/doc/{issued['id']}").status == 200
    finally:
        run("UPDATE documents SET hash=? WHERE id=?", (issued["hash"], issued["id"]))


def test_d1_the_stored_payload_names_the_university(issued):
    assert json.loads(issued["payload"])["ctx"]["university"]["name"]


# ---------------------------------------------------------------- R. timetable, rooms, calendar
def _next_room_lesson():
    """The next lesson held in a room, within the page's two weeks."""
    t = store.now()
    today, hhmm = t.date().isoformat(), t.strftime("%H:%M")
    last = (t.date() + timedelta(days=14)).isoformat()
    first = q("SELECT l.room_id FROM lessons l WHERE l.room_id IS NOT NULL AND l.status<>'cancelled' AND (l.day>? OR (l.day=? AND l.start>?)) "
              "AND l.day<=? ORDER BY l.day, l.start LIMIT 1", (today, today, hhmm, last))
    if not first:
        pytest.skip("no lesson in a room in the next two weeks")
    return q("SELECT l.id, l.day, l.start, l.end, r.code FROM lessons l JOIN rooms r ON r.id=l.room_id WHERE l.room_id=? AND l.status<>'cancelled' "
             "AND (l.day>? OR (l.day=? AND l.start>?)) ORDER BY l.day, l.start LIMIT 1", (first[0]["room_id"], today, today, hhmm))[0]


def test_r1_the_room_page_leaves_out_a_cancelled_lesson(app_db):
    les = _next_room_lesson()
    shown = app_db.client().get(f"/r/{les['code']}").text
    assert les["day"] in shown and f"{les['start']}–{les['end']}" in shown
    assert app_db.client("admin").post(f"/api/lessons/{les['id']}/cancel", {"reason": "Otaq təmirdədir"}).status == 200
    try:
        after = app_db.client().get(f"/r/{les['code']}").text
        assert not (les["day"] in after and f"{les['start']}–{les['end']}" in after)
    finally:
        run("UPDATE lessons SET status='scheduled', note=NULL WHERE id=?", (les["id"],))


def test_r1_a_moved_lesson_shows_where_and_when_it_is_held(app_db):
    les = _next_room_lesson()
    admin = app_db.client("admin")
    day = (date.fromisoformat(les["day"]) + timedelta(days=(6 - date.fromisoformat(les["day"]).isoweekday()) % 7)).isoformat()
    moved = admin.post(f"/api/lessons/{les['id']}/move", {"day": day, "start": "19:00", "end": "20:20", "room": les["code"]})
    assert moved.status == 200, moved.text
    try:
        page = app_db.client().get(f"/r/{les['code']}").text
        assert f"{les['start']}–{les['end']}" not in page or les["day"] not in page
    finally:
        run("UPDATE lessons SET day=?, start=?, end=? WHERE id=?", (les["day"], les["start"], les["end"], les["id"]))


@pytest.fixture
def demo_row():
    """A demo timetable row with at least three future lessons nobody recorded; put back as it was afterwards."""
    today = store.now().date().isoformat()
    found = q("SELECT t.* FROM timetable t WHERE t.active=1 AND t.unit_id IS NOT NULL AND (SELECT COUNT(*) FROM lessons l WHERE "
              "l.timetable_id=t.id AND l.day>? AND l.status='scheduled') >= 3 ORDER BY t.id DESC LIMIT 1", (today,))
    if not found:
        pytest.skip("no row with future lessons")
    r = found[0]
    yield r
    run("UPDATE timetable SET start=?, end=?, academic_hours=? WHERE id=?", (r["start"], r["end"], r["academic_hours"], r["id"]))


def test_r2_editing_a_row_keeps_a_moved_and_a_substituted_lesson(app_db, demo_row):
    admin = app_db.client("admin")
    today = store.now().date().isoformat()
    rid = demo_row["id"]
    fut = q("SELECT id, day, teacher_id FROM lessons WHERE timetable_id=? AND day>? AND status='scheduled' ORDER BY day", (rid, today))
    a, b = fut[0], fut[1]
    sat = date.fromisoformat(a["day"]) + timedelta(days=(6 - date.fromisoformat(a["day"]).isoweekday()) % 7)
    assert admin.post(f"/api/lessons/{a['id']}/move", {"day": sat.isoformat(), "start": "19:00", "end": "20:20"}).status == 200
    other = q("SELECT id FROM users WHERE role='teacher' AND id<>? ORDER BY id LIMIT 1", (b["teacher_id"],))[0]["id"]
    assert admin.post(f"/api/journal/lessons/{b['id']}/teacher", {"teacher_id": other, "reason": "Müəllim ezamiyyətdədir"}).status == 200
    notes = q("SELECT COUNT(*) n FROM notifications")[0]["n"]
    assert admin.put(f"/api/timetable/{rid}", {"academic_hours": 3}).status == 200
    assert q("SELECT day, start FROM lessons WHERE id=?", (a["id"],))[0] == {"day": sat.isoformat(), "start": "19:00"}, "the move stays"
    assert q("SELECT teacher_id, academic_hours FROM lessons WHERE id=?", (b["id"],))[0] == {"teacher_id": other, "academic_hours": 3}
    assert q("SELECT COUNT(*) n FROM notifications")[0]["n"] == notes, "hours alone are not announced"
    later = (datetime.strptime(demo_row["start"], "%H:%M") + timedelta(minutes=5)).strftime("%H:%M")
    assert admin.put(f"/api/timetable/{rid}", {"start": later}).status == 200
    assert q("SELECT day FROM lessons WHERE id=?", (a["id"],))[0]["day"] == sat.isoformat(), "a moved lesson keeps its own time"
    week = q("SELECT teacher_id, start FROM lessons WHERE timetable_id=? AND slot_day=? AND status='scheduled'", (rid, b["day"]))
    assert week == [{"teacher_id": other, "start": later}], "the substitute stays on the lesson of that week"


def test_r3_a_row_with_no_teaching_unit_can_be_edited(app_db):
    cid = q("SELECT t.course_id FROM timetable t WHERE t.weekday=1 AND t.unit_id IS NOT NULL AND t.active=1 LIMIT 1")[0]["course_id"]
    c = db()
    try:
        rid = c.execute("INSERT INTO timetable(course_id,weekday,start,end,kind,room,active,academic_hours,weeks) "
                        "VALUES(?,1,'19:00','20:20','Mühazirə','EK-999',1,2,'all')", (cid,)).lastrowid
        c.commit()
    finally:
        c.close()
    try:
        r = app_db.client("admin").put(f"/api/timetable/{rid}", {"start": "19:10"})
        assert r.status == 200, r.text
    finally:
        run("DELETE FROM timetable WHERE id=?", (rid,))


def test_r4_a_cut_timetable_list_says_so(app_db):
    admin = app_db.client("admin")
    assert admin.get("/api/timetable").json["more"] is False
    cid = q("SELECT t.course_id FROM timetable t WHERE t.active=1 LIMIT 1")[0]["course_id"]
    c = db()
    try:
        c.executemany("INSERT INTO timetable(course_id,weekday,start,end,kind,room,active,academic_hours,weeks) "
                      "VALUES(?,7,'20:00','20:30','Mühazirə','CC-R4',1,2,'all')", [(cid,)] * 1001)
        c.commit()
        got = admin.get("/api/timetable").json
        assert got["more"] is True and len(got["rows"]) == 1000
    finally:
        c.execute("DELETE FROM timetable WHERE room='CC-R4'")
        c.commit()
        c.close()


def test_r5_relinking_rooms_ignores_rows_taken_off_the_timetable(app_db):
    cid = q("SELECT course_id FROM timetable WHERE active=1 LIMIT 1")[0]["course_id"]
    run("INSERT INTO timetable(course_id,weekday,start,end,kind,room,active) VALUES(?,7,'08:00','09:20','Mühazirə','Yox bina, 999',0)", (cid,))
    try:
        r = app_db.client("admin").post("/api/facilities/link-rooms")
        assert r.status == 200 and "Yox bina, 999" not in str(r.json)
    finally:
        run("DELETE FROM timetable WHERE room='Yox bina, 999'")


def test_r7_the_access_log_does_not_hold_a_calendar_token(app_db, monkeypatch, capsys):
    url = app_db.client("student").post("/api/me/calendar").json["url"]
    token = url.rsplit("/", 1)[1]
    monkeypatch.setattr(security.CFG, "access_log", True)
    assert app_db.client().get(urlsplit(url).path).status == 200
    out = ""
    for _ in range(50):                                   # the line is written after the answer is sent
        out += capsys.readouterr().out
        if "/ical/" in out:
            break
        time.sleep(0.02)
    assert "/ical/" in out and token not in out


@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/timetable", {"unit_id": 2 ** 70, "weekday": 6, "start": "10:00", "end": "11:20", "room": "EK-118"}),
    ("post", "/api/journal/lessons/1/teacher", {"teacher_id": 2 ** 70, "reason": "Səbəb yazılıb"}),
    ("post", "/api/assignments/1/submit", {"file_id": 2 ** 70, "text": "x"}),
])
def test_r11_an_id_beyond_64_bits_is_a_400(app_db, method, path, body):
    who = "student" if "submit" in path else "admin"
    r = getattr(app_db.client(who), method)(path, body)
    assert r.status in (400, 404), r.text


# ---------------------------------------------------------------- L. materials and assignments
def _docx(paras) -> bytes:
    import io
    import zipfile
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paras)
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                                        f"<w:body>{body}</w:body></w:document>")
    return b.getvalue()


def _upload(teacher, course, paras, **kw):
    import base64
    return teacher.post(f"/api/courses/{course}/materials", {"filename": "m.docx", "content_b64": base64.b64encode(_docx(paras)).decode(), **kw})


@pytest.fixture(scope="module")
def own_course(app_db):
    teacher, student = app_db.client("teacher"), app_db.client("student")
    return q("SELECT c.id FROM courses c JOIN enrollments e ON e.course_id=c.id WHERE c.teacher_id=? AND e.user_id=? ORDER BY c.id LIMIT 1",
             (teacher.user["id"], student.user["id"]))[0]["id"]


V1 = ["# Rezistorlar", "Rezistor — elektrik müqavimətini təmin edən passiv elementdir və Om qanununa tabe olur.",
      "Rezistorun müqaviməti Om ilə ölçülür və rəng kodları ilə işarələnir."]
V2 = ["# Rezistorlar (yeni)", "Termistor — müqaviməti temperaturla dəyişən rezistordur və sensor kimi işlədilir.",
      "Fotorezistor işığın təsiri ilə müqavimətini dəyişir və avtomatik işıqlandırmada istifadə olunur."]


def test_l1_deleting_the_current_version_brings_the_earlier_one_back_with_its_sections(app_db, own_course):
    from zeka.legacy import engine
    teacher = app_db.client("teacher")
    v1 = _upload(teacher, own_course, V1).json["id"]
    v2 = _upload(teacher, own_course, V2, replaces=v1).json["id"]
    assert teacher.delete(f"/api/materials/{v2}").status == 200
    back = {r["id"] for r in q("SELECT id FROM chunks WHERE material_id=?", (v1,))}
    assert back, "the earlier version is current again and has its sections"
    hits = {h["id"] for h in engine.INDEX["chunks"].search("rezistor müqavimət Om rəng kodları", k=50)}
    assert hits & back
    listed = [m["id"] for m in app_db.client("student").get(f"/api/courses/{own_course}").json["materials_list"]]
    assert v1 in listed


def test_l2_a_new_version_never_takes_the_old_version_s_section_ids(app_db, own_course):
    teacher = app_db.client("teacher")
    v1 = _upload(teacher, own_course, V1).json["id"]
    old = {r["id"] for r in q("SELECT id FROM chunks WHERE material_id=?", (v1,))}
    v2 = _upload(teacher, own_course, V2, replaces=v1).json["id"]
    new = {r["id"] for r in q("SELECT id FROM chunks WHERE material_id=?", (v2,))}
    assert old and new and not old & new


def test_l3_the_syllabus_and_the_studio_read_the_current_version_only(app_db, own_course):
    teacher = app_db.client("teacher")
    v1 = _upload(teacher, own_course, V1).json["id"]
    _upload(teacher, own_course, V2, replaces=v1)
    gen = teacher.post(f"/api/syllabus/{own_course}/generate", {}).json
    assert len(gen["outcomes"]) == len(set(gen["outcomes"]))
    assert not any("Rezistorlar" == m for m in gen["materials"]), "the replaced version is not listed"


def test_l3_a_course_without_a_description_gets_a_syllabus(app_db):
    teacher, admin = app_db.client("teacher"), app_db.client("admin")
    cid = admin.post("/api/directory/courses", {"code": "CC-L3", "name": "Təsvirsiz fənn", "credits": 3, "teacher_id": teacher.user["id"]}).json["id"]
    assert teacher.post(f"/api/syllabus/{cid}/generate", {}).status == 200


def test_l4_grading_after_the_component_left_the_scheme_is_a_400(app_db, own_course):
    teacher, student = app_db.client("teacher"), app_db.client("student")
    due = (store.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
    a = teacher.post(f"/api/courses/{own_course}/assignments", {"title": "Sxem dəyişir", "body": "Həll edin.", "due_at": due, "max_score": 3,
                                                                "component": "Sərbəst iş 1", "late_rule": "mark"}).json
    sid = student.post(f"/api/assignments/{a['id']}/submit", {"text": "cavab"}).json["id"]
    run("UPDATE assignments SET component='Silinmiş komponent' WHERE id=?", (a["id"],))
    r = teacher.post(f"/api/submissions/{sid}/grade", {"score": 2})
    assert r.status == 400 and "Silinmiş komponent" in r.json["error"]


@pytest.mark.parametrize("due", ["٢٠٢٦-٠١-٠١T10:00", "2026-02-31T10:00", "2026-13-45T10:00"])
def test_l6_an_impossible_due_date_is_refused(due):
    from zeka.modules.learning import domain
    _, problem = domain.assignment_input({"title": "Ad yazılıb", "body": "Mətn", "due_at": due, "max_score": 3, "component": "A",
                                          "late_rule": "mark"}, {"A": 5})
    assert problem


def test_l7_a_graded_submission_is_not_replaced_by_a_late_write(app_db, own_course):
    from zeka.modules.learning import repo
    teacher, student = app_db.client("teacher"), app_db.client("student")
    due = (store.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
    a = teacher.post(f"/api/courses/{own_course}/assignments", {"title": "Yarış", "body": "Həll edin.", "due_at": due, "max_score": 3,
                                                                "component": "Sərbəst iş 1", "late_rule": "mark"}).json
    sid = student.post(f"/api/assignments/{a['id']}/submit", {"text": "qiymətlənən"}).json["id"]
    assert teacher.post(f"/api/submissions/{sid}/grade", {"score": 2}).status == 200
    c = db()
    try:
        assert repo.save_submission(c, a["id"], student.user["id"], "sonradan", None, "2026-01-01T00:00:00", False) is False
        c.commit()
    finally:
        c.close()
    assert q("SELECT text FROM submissions WHERE id=?", (sid,))[0]["text"] == "qiymətlənən"


def test_l8_a_missing_upload_file_is_a_404(app_db, own_course):
    teacher = app_db.client("teacher")
    mid = _upload(teacher, own_course, V1).json["id"]
    path = store.UPLOADS / q("SELECT f.path FROM materials m JOIN files f ON f.id=m.file_id WHERE m.id=?", (mid,))[0]["path"]
    hidden = path.with_suffix(".gone")
    path.rename(hidden)
    try:
        assert teacher.get(f"/api/materials/{mid}/file").status == 404
    finally:
        hidden.rename(path)


# ---------------------------------------------------------------- J. journal, final grades, imports
def ins(sql, args=()):
    c = db()
    try:
        rid = c.execute(sql, args).lastrowid
        c.commit()
        return rid
    finally:
        c.close()


@pytest.fixture(scope="module")
def cc(app_db):
    """A course of the demo teacher: one lecture unit, students cc.a and cc.b, ten held lectures (cc.b missed two)."""
    admin, teacher = app_db.client("admin"), app_db.client("teacher")
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    fid = admin.get("/api/directory/faculties").json["items"][0]["id"]
    gid = admin.post("/api/directory/groups", {"name": "CC-1", "year": 2025, "faculty_id": fid}).json["id"]
    course = admin.post("/api/directory/courses", {"code": "CC-101", "name": "Yoxlama sınağı", "credits": 5, "term_id": term["id"],
                                                   "teacher_id": teacher.user["id"]}).json["id"]
    other = admin.post("/api/directory/courses", {"code": "CC-102", "name": "Başqa sınaq", "credits": 5, "term_id": term["id"],
                                                  "teacher_id": teacher.user["id"]}).json["id"]
    unit = admin.post("/api/directory/units", {"course_id": course, "kind": "lecture", "teacher_id": teacher.user["id"]}).json["id"]
    admin.put(f"/api/directory/units/{unit}/groups", {"group_ids": [gid]})
    students = {}
    for name in ("cc.a", "cc.b"):
        students[name] = admin.post("/api/directory/users", {"username": name, "full_name": f"Yoxlama {name}", "role": "student",
                                                             "group_id": gid, "student_no": name.upper()}).json["id"]
        admin.post(f"/api/directory/courses/{course}/enrollments", {"user_id": students[name]})
    today = store.now().date()
    lessons = []
    for k in range(1, 11):
        d = (today - timedelta(days=k + 3)).isoformat()                  # outside the teacher's 48-hour window
        lid = ins("INSERT INTO lessons(course_id,day,start,end,kind,unit_id,teacher_id,academic_hours,slot_day,slot_start) "
                  "VALUES(?,?,'00:00','00:30','Mühazirə',?,?,2,?,'00:00')", (course, d, unit, teacher.user["id"], d))
        lessons.append(lid)
        for name, sid in students.items():
            run("INSERT INTO attendance(lesson_id,user_id,status) VALUES(?,?,?)", (lid, sid, "absent" if name == "cc.b" and k <= 2 else "present"))
    return {"course": course, "other": other, "students": students, "lessons": lessons, "term": term, "group": gid}


def _grant(admin, uid, scope_type, scope_id):
    assert admin.post(f"/api/admin/users/{uid}/roles", {"role": "dept_head", "scope_type": scope_type, "scope_id": scope_id}).status == 200
    return q("SELECT id FROM role_grants WHERE user_id=? AND role='dept_head' AND scope_type=? AND scope_id=?", (uid, scope_type, scope_id))[0]["id"]


def test_j1_a_department_head_scoped_to_another_course_does_not_correct_this_one(app_db, cc):
    admin, head = app_db.client("admin"), app_db.client("office")
    uid = head.user["id"]
    elsewhere = _grant(admin, uid, "course", cc["other"])
    assert head.post("/api/me/role", {"role": "dept_head"}).status == 200
    lid = cc["lessons"][5]
    try:
        assert head.get(f"/api/journal/lessons/{lid}").status == 404
        assert head.put(f"/api/journal/lessons/{lid}/attendance", {"marks": {}, "reason": "Kafedra yoxlaması"}).status == 404
        here = _grant(admin, uid, "course", cc["course"])
        try:
            assert head.get(f"/api/journal/lessons/{lid}").status == 200
            assert head.put(f"/api/journal/lessons/{lid}/attendance", {"marks": {}, "reason": "Kafedra yoxlaması"}).status == 200
        finally:
            admin.delete(f"/api/admin/users/{uid}/roles/{here}")
    finally:
        admin.delete(f"/api/admin/users/{uid}/roles/{elsewhere}")


def test_j2_no_final_grade_without_attendance_to_count(app_db, cc):
    from zeka.core import tenant
    from zeka.modules.journal import service as journal
    admin = app_db.client("admin")
    cid = admin.post("/api/directory/courses", {"code": "CC-103", "name": "Dərssiz fənn", "credits": 3, "term_id": cc["term"]["id"],
                                                "teacher_id": app_db.client("teacher").user["id"]}).json["id"]
    sid = cc["students"]["cc.a"]
    admin.post(f"/api/directory/courses/{cid}/enrollments", {"user_id": sid})
    c = db()
    try:
        g = tenant.load(c)["grading"]
        for x in [x for x in g["components"] if not x.get("attendance")] + [g["exam"]]:
            c.execute("INSERT INTO grades(user_id,course_id,component,score,max,status,source) VALUES(?,?,?,?,?,'published','zeka')",
                      (sid, cid, x["name"], x["max"], x["max"]))
        journal.refresh_finals(c, cid, [sid])
        c.commit()
    finally:
        c.close()
    assert q("SELECT 1 FROM final_grades WHERE user_id=? AND course_id=?", (sid, cid)) == [], "missing attendance is not 0 points"


def _publish_all(app_db, cc, sid):
    from zeka.core import tenant
    c = db()
    try:
        g = tenant.load(c)["grading"]
    finally:
        c.close()
    admin = app_db.client("admin")
    cells = [{"student_id": sid, "component": x["name"], "score": x["max"]} for x in g["components"] if not x.get("attendance")]
    cells.append({"student_id": sid, "component": g["exam"]["name"], "score": g["exam"]["max"]})
    assert admin.put(f"/api/journal/courses/{cc['course']}/grades", {"cells": cells}).status == 200
    assert admin.post(f"/api/journal/courses/{cc['course']}/grades/publish").status == 200


def test_j3_a_correction_of_attendance_moves_the_final_grade(app_db, cc):
    admin, sid = app_db.client("admin"), cc["students"]["cc.a"]
    _publish_all(app_db, cc, sid)
    before = q("SELECT score FROM final_grades WHERE user_id=? AND course_id=?", (sid, cc["course"]))[0]["score"]
    for lid in cc["lessons"][:6]:
        assert admin.put(f"/api/journal/lessons/{lid}/attendance", {"marks": {str(sid): "absent"}, "reason": "Kağız jurnalla tutuşdurma"}).status == 200
    after = q("SELECT score FROM final_grades WHERE user_id=? AND course_id=?", (sid, cc["course"]))[0]["score"]
    table = admin.get(f"/api/journal/courses/{cc['course']}/grades").json
    total = next(s for s in table["students"] if s["id"] == sid)["result"]["total"]
    assert after < before and after == total, "the transcript follows the journal"


def test_j4_a_transcript_is_not_issued_when_the_history_is_not_reconciled_at_issue(app_db):
    student, office = app_db.client("student"), app_db.client("office")
    order = {"purpose": "Magistraturaya qəbul", "lang": "Azərbaycan dili", "scope": "Bütün semestrlər", "delivery": "Elektron (QR kodlu PDF)"}
    rid = student.post("/api/requests", {"type_code": "transcript", "data": order}).json["id"]
    office.post(f"/api/requests/{rid}/action", {"action": "approve"})
    sid = student.user["id"]
    keep = q("SELECT admission_year, history_reconciled_at FROM users WHERE id=?", (sid,))[0]
    run("UPDATE users SET history_reconciled_at=NULL, admission_year=2020 WHERE id=?", (sid,))
    try:
        r = office.post(f"/api/requests/{rid}/action", {"action": "issue"})
        assert r.status == 400 and "Transkript hələ verilmir" in r.json["error"]
    finally:
        run("UPDATE users SET history_reconciled_at=?, admission_year=? WHERE id=?", (keep["history_reconciled_at"], keep["admission_year"], sid))


def _grades_import(admin, rows, prefer=False):
    import base64
    import csv
    import io
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["courseSourcedId", "userSourcedId", "component", "score", "max", "asOf"])
    w.writerows(rows)
    return admin.post("/api/admin/import", {"kind": "grades", "source": "cc-sis", "filename": "cc.csv", "dry_run": False,
                                            "prefer_source": prefer, "content_b64": base64.b64encode(out.getvalue().encode()).decode()}).json


def test_j5_a_grade_import_refuses_a_course_not_taken_and_logs_a_changed_published_score(app_db, cc):
    admin = app_db.client("admin")
    stranger = app_db.client("student").user["id"]
    for kind, src, rid in (("courses", "CC", cc["course"]), ("users", "CB", cc["students"]["cc.b"]), ("users", "ST", stranger)):
        run("INSERT INTO import_links(kind,source_system,source_id,row_id,source_hash,imported_at) VALUES(?,?,?,?,'-','x')", (kind, "cc-sis", src, rid))
    rep = _grades_import(admin, [["CC", "ST", "Kollokvium 1", "7", "10", ""]])
    assert [e["row"] for e in rep["errors"]] == [2] and not rep["written"], "not enrolled"
    first = _grades_import(admin, [["CC", "CB", "Kollokvium 1", "6", "10", ""]])
    assert first["written"] and not first["conflicts"]
    again = _grades_import(admin, [["CC", "CB", "Kollokvium 1", "6", "10", ""]])
    assert again["unchanged"] == 1 and not again["conflicts"], "the same file changes nothing"
    changed = _grades_import(admin, [["CC", "CB", "Kollokvium 1", "4", "10", ""]], prefer=True)
    assert changed["written"]
    log = q("SELECT old_score, new_score, reason FROM grade_changes WHERE user_id=? AND course_id=? AND component='Kollokvium 1'",
            (cc["students"]["cc.b"], cc["course"]))
    assert log and log[-1]["new_score"] == 4 and log[-1]["reason"].startswith("import:cc.csv:")


def test_j6_one_cell_sent_twice_keeps_the_last_value(app_db, cc):
    teacher, sid = app_db.client("teacher"), cc["students"]["cc.b"]
    url = f"/api/journal/courses/{cc['course']}/grades"
    assert teacher.put(url, {"cells": [{"student_id": sid, "component": "Kollokvium 2", "score": 5}]}).status == 200
    cells = [{"student_id": sid, "component": "Kollokvium 2", "score": 8}, {"student_id": sid, "component": "Kollokvium 2", "score": 5}]
    assert teacher.put(url, {"cells": cells}).status == 200
    assert q("SELECT score FROM grades WHERE user_id=? AND course_id=? AND component='Kollokvium 2'", (sid, cc["course"]))[0]["score"] == 5


def test_j7_a_lesson_before_the_cut_over_takes_no_new_row(app_db, cc):
    from zeka.core import tenant
    admin = app_db.client("admin")
    c = db()
    try:
        keep = tenant.load(c)["journal"]
    finally:
        c.close()
    lid = cc["lessons"][9]                                              # the oldest
    day = q("SELECT day FROM lessons WHERE id=?", (lid,))[0]["day"]
    assert admin.put("/api/admin/settings/journal", {"value": {**keep, "cutover_date": day}}).status == 200
    try:
        sid = cc["students"]["cc.a"]
        r = admin.put(f"/api/journal/lessons/{lid}/attendance", {"marks": {str(sid): "absent"}, "reason": "Köhnə jurnal"})
        assert r.status == 403
        assert q("SELECT status FROM attendance WHERE lesson_id=? AND user_id=?", (lid, sid))[0]["status"] == "present"
    finally:
        admin.put("/api/admin/settings/journal", {"value": keep})


def test_j8_an_opening_dated_in_the_future_is_refused(app_db, cc):
    import base64
    import csv
    import io
    admin = app_db.client("admin")
    run("INSERT INTO import_links(kind,source_system,source_id,row_id,source_hash,imported_at) VALUES('terms','cc-sis','T',?,'-','x')", (cc["term"]["id"],))
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["termSourcedId", "courseSourcedId", "userSourcedId", "heldHours", "unexcusedHours", "excusedHours", "asOf"])
    w.writerow(["T", "CC", "CB", "10", "0", "0", (store.now().date() + timedelta(days=200)).isoformat()])
    rep = admin.post("/api/admin/import", {"kind": "attendance-opening", "source": "cc-sis", "filename": "q.csv", "dry_run": True,
                                           "prefer_source": False, "content_b64": base64.b64encode(out.getvalue().encode()).decode()}).json
    assert [e["row"] for e in rep["errors"]] == [2]


def test_j9_a_lesson_with_an_excused_student_saves_as_the_screen_sends_it(app_db, cc):
    teacher, sid = app_db.client("teacher"), cc["students"]["cc.b"]
    today = store.now().date().isoformat()
    lid = ins("INSERT INTO lessons(course_id,day,start,end,kind,unit_id,teacher_id,academic_hours,slot_day,slot_start) "
              "SELECT course_id,?,'00:00','00:01',kind,unit_id,teacher_id,2,?,'00:00' FROM lessons WHERE id=?", (today, today, cc["lessons"][0]))
    run("INSERT INTO attendance(lesson_id,user_id,status,request_id) VALUES(?,?,'excused',999999)", (lid, sid))
    a = cc["students"]["cc.a"]
    r = teacher.put(f"/api/journal/lessons/{lid}/attendance", {"marks": {str(a): "absent", str(sid): "excused"}})
    assert r.status == 200, r.text
    assert q("SELECT status FROM attendance WHERE lesson_id=? AND user_id=?", (lid, sid))[0]["status"] == "excused"
    assert teacher.put(f"/api/journal/lessons/{lid}/attendance", {"marks": {str(a): "excused"}}).status == 400, "excused comes from a request"


def test_l5_a_unit_teacher_grades_a_submission_before_any_lesson(app_db, cc):
    admin, teacher, student = app_db.client("admin"), app_db.client("teacher"), app_db.client("student")
    leyla = q("SELECT id FROM users WHERE username='leyla'")[0]["id"]
    cid = admin.post("/api/directory/courses", {"code": "CC-104", "name": "Vahid müəllimi", "credits": 3, "term_id": cc["term"]["id"],
                                                "teacher_id": leyla}).json["id"]
    unit = admin.post("/api/directory/units", {"course_id": cid, "kind": "seminar", "teacher_id": teacher.user["id"]}).json["id"]
    gid = q("SELECT group_id FROM users WHERE id=?", (student.user["id"],))[0]["group_id"]
    admin.put(f"/api/directory/units/{unit}/groups", {"group_ids": [gid]})
    admin.post(f"/api/directory/courses/{cid}/enrollments", {"user_id": student.user["id"]})
    assert cid in [x["id"] for x in teacher.get("/api/courses").json], "the course is on the unit teacher's list (P6)"
    assert teacher.get(f"/api/courses/{cid}").status == 200
    due = (store.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
    a = teacher.post(f"/api/courses/{cid}/assignments", {"title": "Vahid tapşırığı", "body": "Həll edin.", "due_at": due, "max_score": 3,
                                                         "component": "Sərbəst iş 1", "late_rule": "mark"}).json
    sub = student.post(f"/api/assignments/{a['id']}/submit", {"text": "cavab"}).json["id"]
    assert teacher.post(f"/api/submissions/{sub}/grade", {"score": 2}).status == 200


# ---------------------------------------------------------------- P. performance and reach
def _traced(fn):
    c = db()
    seen: list[str] = []
    c.set_trace_callback(seen.append)
    try:
        fn(c)
    finally:
        c.set_trace_callback(None)
        c.rollback()
        c.close()
    return seen


def test_p1_the_course_list_does_not_read_the_journal_per_course(app_db):
    from zeka.legacy import r_learning
    u = q("SELECT * FROM users WHERE id=?", (app_db.client("student").user["id"],))[0]
    seen = _traced(lambda c: [r_learning.course_card(c, co, u) for co in r_learning.my_courses(c, u)])
    assert not [s for s in seen if "attendance_opening" in s], "the standing is read on the attendance page and a course's page"


def test_p2_final_grades_of_many_students_read_the_journal_once(cc):
    from zeka.modules.journal import service as journal
    seen = _traced(lambda c: journal.refresh_finals(c, cc["course"], list(cc["students"].values())))
    assert len([s for s in seen if "FROM attendance_opening" in s]) == 1


def test_p3_a_course_s_grades_are_read_through_an_index(cc):
    c = db()
    try:
        plan = " ".join(str(r[3]) for r in c.execute("EXPLAIN QUERY PLAN SELECT * FROM grades WHERE course_id=?", (cc["course"],)))
    finally:
        c.close()
    assert "SCAN grades" not in plan, plan


def test_p4_an_import_keys_a_table_once():
    from zeka.modules.integration.importer import Context
    c = db()
    try:
        ctx = Context(c, "cc-sis", ())
        assert ctx.keyed("grades", ("user_id", "course_id", "component"), "rowid") is ctx.keyed("grades", ("user_id", "course_id", "component"), "rowid")
    finally:
        c.close()


def test_p5_the_debts_come_in_pages(app_db):
    got = app_db.client("admin").get("/api/journal/debts").json
    assert set(got) >= {"items", "total", "page", "pages"} and len(got["items"]) <= 200 and got["total"] >= len(got["items"])


def test_p7_a_department_head_finds_an_upcoming_lesson_to_substitute(app_db):
    les = q("SELECT course_id FROM lessons WHERE day>? AND status='scheduled' ORDER BY day LIMIT 1", (store.now().date().isoformat(),))
    if not les:
        pytest.skip("no upcoming lesson")
    got = app_db.client("admin").get(f"/api/journal/courses/{les[0]['course_id']}/lessons").json
    assert any(x["day"] > store.now().date().isoformat() for x in got)
