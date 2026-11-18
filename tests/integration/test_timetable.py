"""Timetable management (tasks/todo.md, Task 19): rows of teaching units with their clashes, the lessons made from
them, a cancelled or moved lesson, and each person's calendar feed.

New rows go on Saturdays, a day the demo timetable leaves free; the demo's own lessons serve the feed tests."""
from datetime import date, timedelta

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
        c.execute(sql, args)
        c.commit()
    finally:
        c.close()


@pytest.fixture(scope="module")
def world(app_db):
    """Three new groups, a course of the current term with a stream lecture, three seminars of a second teacher and a lab
    in two subgroups of group A; one student per group (the student of A in subgroup 1)."""
    admin = app_db.client("admin")
    fid = admin.get("/api/directory/faculties").json["items"][0]["id"]
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    g = {n: admin.post("/api/directory/groups", {"name": n, "year": 2025, "faculty_id": fid}).json["id"] for n in ("TT-A", "TT-B", "TT-C")}
    t = {n: admin.post("/api/directory/users", {"username": n, "full_name": f"Müəllim {n}", "role": "teacher"}).json["id"]
         for n in ("tt.lek", "tt.sem", "tt.lab1", "tt.lab2")}
    course = admin.post("/api/directory/courses", {"code": "TT-101", "name": "Cədvəl sınağı", "credits": 5, "term_id": term["id"]}).json["id"]

    def unit(kind, teacher, groups, subgroup=None):
        uid = admin.post("/api/directory/units", {"course_id": course, "kind": kind, "teacher_id": t[teacher], "subgroup": subgroup}).json["id"]
        assert admin.put(f"/api/directory/units/{uid}/groups", {"group_ids": [g[x] for x in groups]}).status == 200
        return uid

    units = {"lecture": unit("lecture", "tt.lek", ["TT-A", "TT-B", "TT-C"]),
             "sem-A": unit("seminar", "tt.sem", ["TT-A"]), "sem-B": unit("seminar", "tt.sem", ["TT-B"]),
             "sem-C": unit("seminar", "tt.sem", ["TT-C"]),
             "lab-1": unit("lab", "tt.lab1", ["TT-A"], 1), "lab-2": unit("lab", "tt.lab2", ["TT-A"], 2)}
    s = {}
    for n, grp, sub in (("tt.s.a", "TT-A", 1), ("tt.s.b", "TT-B", None), ("tt.s.c", "TT-C", None)):
        s[n] = admin.post("/api/directory/users", {"username": n, "full_name": f"Tələbə {n}", "role": "student", "group_id": g[grp],
                                                   "student_no": n.upper()}).json["id"]
        assert admin.post(f"/api/directory/courses/{course}/enrollments", {"user_id": s[n], "subgroup": sub}).status == 200
    return {"term": term, "groups": g, "teachers": t, "course": course, "units": units, "students": s}


def row(admin, unit, start, end, room, weekday=6, weeks="all", hours=2):
    return admin.post("/api/timetable", {"unit_id": unit, "weekday": weekday, "start": start, "end": end, "room": room,
                                         "weeks": weeks, "academic_hours": hours})


@pytest.fixture(scope="module")
def rows(app_db, world):
    admin, u = app_db.client("admin"), world["units"]
    made = {"lecture": row(admin, u["lecture"], "09:00", "10:20", "EK-220"),
            "sem-A": row(admin, u["sem-A"], "10:30", "11:50", "EK-224"), "sem-B": row(admin, u["sem-B"], "12:00", "13:20", "EK-224"),
            "sem-C": row(admin, u["sem-C"], "13:50", "15:10", "EK-224"),
            "lab-1": row(admin, u["lab-1"], "15:20", "16:40", "EK-316"), "lab-2": row(admin, u["lab-2"], "15:20", "16:40", "EK-121")}
    assert {k: r.status for k, r in made.items()} == {k: 200 for k in made}, {k: r.text[:200] for k, r in made.items()}
    return {k: r.json for k, r in made.items()}


def test_a_stream_three_seminars_and_a_lab_in_two_subgroups_are_saved(rows):
    assert rows["lecture"]["groups"] == ["TT-A", "TT-B", "TT-C"] and rows["lecture"]["kind"] == "Mühazirə"
    assert rows["lab-1"]["room_id"] and rows["lab-1"]["room_id"] != rows["lab-2"]["room_id"]
    assert rows["sem-A"]["teacher"] == "Müəllim tt.sem"


def test_the_same_group_at_the_same_time_is_refused_with_what_it_meets(app_db, world, rows):
    r = row(app_db.client("admin"), world["units"]["sem-A"], "09:30", "10:50", "EK-305")
    assert r.status == 409
    clash = r.json["conflicts"]
    assert {"what": "group", "groups": ["TT-A"], "course": "Cədvəl sınağı", "start": "09:00"}.items() <= clash[0].items()
    assert any(x["what"] == "teacher" for x in clash), "the seminar teacher is already at 10:30"


def test_a_room_or_a_teacher_taken_at_that_time_is_refused(app_db, world, rows):
    admin = app_db.client("admin")
    other = admin.post("/api/directory/units", {"course_id": world["course"], "kind": "seminar", "teacher_id": world["teachers"]["tt.lab1"]}).json["id"]
    r = row(admin, other, "09:30", "10:00", "Əsas korpus, 220")
    assert r.status == 409 and [x["what"] for x in r.json["conflicts"]] == ["room"], "the same room under another name"
    r = row(admin, world["units"]["lab-1"], "15:00", "15:30", "EK-512")
    assert r.status == 409 and "teacher" in [x["what"] for x in r.json["conflicts"]]
    assert row(admin, other, "09:00", "10:20", "EK-220", weekday=7).status == 200, "another day is free"


def test_bad_rows_are_refused(app_db, world):
    admin = app_db.client("admin")
    u = world["units"]["sem-B"]
    for body in ({"weekday": 8}, {"start": "10:00", "end": "09:00"}, {"start": "25:00"}, {"weeks": "every"}, {"academic_hours": 0},
                 {"academic_hours": True}, {"unit_id": 999999}):
        full = {"unit_id": u, "weekday": 6, "start": "17:00", "end": "18:20", "room": "EK-305", "weeks": "all", "academic_hours": 2, **body}
        assert admin.post("/api/timetable", full).status == 400, body
    assert app_db.client("teacher").post("/api/timetable", {"unit_id": u}).status == 403
    assert app_db.client("student").get("/api/timetable").status == 403


def saturdays(term):
    d, last = date.fromisoformat(term["teaching_start"]), term["teaching_end"]
    d += timedelta(days=(6 - d.isoweekday()) % 7)
    out = []
    while d.isoformat() <= last:
        out.append(d.isoformat())
        d += timedelta(days=7)
    return out


def test_lessons_are_made_once_per_slot_in_the_teaching_period(app_db, world, rows):
    admin = app_db.client("admin")
    term = world["term"]
    holiday = saturdays(term)[1]
    settings = admin.get("/api/admin/settings").json["calendar"]
    assert admin.put("/api/admin/settings/calendar", {"value": {**settings, "holidays": [holiday]}}).status == 200
    rep = admin.post("/api/timetable/generate", {"term_id": term["id"]}).json
    assert rep["created"] > 0 and rep["term"]["id"] == term["id"]
    days = [r["day"] for r in q("SELECT day FROM lessons WHERE timetable_id=? ORDER BY day", (rows["lecture"]["id"],))]
    assert days == [d for d in saturdays(term) if d != holiday]
    assert all(term["teaching_start"] <= d <= term["teaching_end"] for d in days)
    les = q("SELECT * FROM lessons WHERE timetable_id=? LIMIT 1", (rows["lab-1"]["id"],))[0]
    assert les["unit_id"] == world["units"]["lab-1"] and les["teacher_id"] == world["teachers"]["tt.lab1"] and les["academic_hours"] == 2
    again = admin.post("/api/timetable/generate", {"term_id": term["id"]}).json
    assert again["created"] == 0
    assert q("SELECT unit_id, slot_day, slot_start, COUNT(*) n FROM lessons WHERE unit_id IS NOT NULL "
             "GROUP BY unit_id, slot_day, slot_start HAVING n > 1") == []


def test_an_odd_week_row_holds_lessons_every_other_week(app_db, world, rows):
    admin = app_db.client("admin")
    odd = admin.post("/api/directory/units", {"course_id": world["course"], "kind": "lab", "teacher_id": world["teachers"]["tt.lab2"]}).json["id"]
    r = row(admin, odd, "17:00", "18:20", "EK-316", weeks="odd")
    assert r.status == 200
    admin.post("/api/timetable/generate", {"term_id": world["term"]["id"]})
    days = [date.fromisoformat(x["day"]) for x in q("SELECT day FROM lessons WHERE timetable_id=? ORDER BY day", (r.json["id"],))]
    assert days and all((b - a).days == 14 for a, b in zip(days, days[1:]))


def future_lesson(timetable_id):
    today = store.now().date().isoformat()
    return q("SELECT * FROM lessons WHERE timetable_id=? AND day>? AND status='scheduled' ORDER BY day LIMIT 1", (timetable_id, today))[0]


def notes(uid, title_part):
    return [n for n in q("SELECT title, body FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 20", (uid,)) if title_part in n["title"]]


def test_a_cancelled_lesson_tells_only_its_own_students(app_db, world, rows):
    admin = app_db.client("admin")
    les = future_lesson(rows["lab-2"]["id"])                       # subgroup 2 of group A: none of the three students
    assert admin.post(f"/api/lessons/{les['id']}/cancel", {"reason": "Laborant xəstədir"}).json["status"] == "cancelled"
    assert not notes(world["students"]["tt.s.a"], "ləğv")
    les = future_lesson(rows["sem-B"]["id"])
    assert admin.post(f"/api/lessons/{les['id']}/cancel", {"reason": "x"}).status == 400
    assert admin.post(f"/api/lessons/{les['id']}/cancel", {"reason": "Müəllim konfransdadır"}).status == 200
    assert admin.post(f"/api/lessons/{les['id']}/cancel", {"reason": "Yenə"}).status == 409
    assert notes(world["students"]["tt.s.b"], "ləğv") and not notes(world["students"]["tt.s.c"], "ləğv")


def test_a_moved_lesson_is_checked_and_announced(app_db, world, rows):
    admin = app_db.client("admin")
    les = future_lesson(rows["sem-C"]["id"])
    clash = admin.post(f"/api/lessons/{les['id']}/move", {"day": les["day"], "start": "09:30", "end": "10:50"})
    assert clash.status == 409 and clash.json["conflicts"][0]["what"] in ("group", "room")
    assert admin.post(f"/api/lessons/{les['id']}/move", {"day": "2000-01-01", "start": "09:30", "end": "10:50"}).status == 400
    moved = admin.post(f"/api/lessons/{les['id']}/move", {"day": les["day"], "start": "16:50", "end": "18:10", "room": "EK-402"})
    assert moved.status == 200 and moved.json["start"] == "16:50" and moved.json["slot_start"] == les["start"]
    assert notes(world["students"]["tt.s.c"], "vaxtı dəyişdi")
    assert admin.post("/api/timetable/generate", {"term_id": world["term"]["id"]}).json["created"] == 0, "the slot keeps its lesson"


def test_a_changed_row_moves_its_future_lessons(app_db, world, rows):
    admin = app_db.client("admin")
    rid = rows["sem-A"]["id"]
    r = admin.put(f"/api/timetable/{rid}", {"start": "10:40", "end": "12:00"})
    assert r.status == 200 and r.json["start"] == "10:40"
    today = store.now().date().isoformat()
    future = q("SELECT DISTINCT start FROM lessons WHERE timetable_id=? AND day>?", (rid, today))
    assert future == [{"start": "10:40"}]
    assert notes(world["students"]["tt.s.a"], "cədvəli dəyişdi")
    assert admin.put(f"/api/timetable/{rid}", {"start": "09:10"}).status == 409, "into the stream lecture of group A"


def test_a_removed_row_takes_its_future_lessons_with_it(app_db, world, rows):
    admin = app_db.client("admin")
    rid = rows["lab-1"]["id"]
    assert admin.post(f"/api/timetable/{rid}/deactivate").status == 200
    today = store.now().date().isoformat()
    assert q("SELECT 1 FROM lessons WHERE timetable_id=? AND day>?", (rid, today)) == []
    assert rid not in [x["id"] for x in admin.get(f"/api/timetable?group_id={world['groups']['TT-A']}").json["rows"]]


def test_a_day_s_lessons_are_listed(app_db, world, rows):
    les = future_lesson(rows["lecture"]["id"])
    listed = app_db.client("office").get(f"/api/lessons?day={les['day']}&group_id={world['groups']['TT-B']}").json
    assert les["id"] in [x["id"] for x in listed]
    assert app_db.client("admin").get("/api/lessons?day=2026-W01-1").status == 400


# ---------------------------------------------------------------- calendar feed
def test_a_student_s_calendar_feed(app_db):
    student = app_db.client("student")
    assert student.get("/api/me/calendar").json == {"active": False}
    url = student.post("/api/me/calendar").json["url"]
    path = url[url.index("/ical/"):]
    feed = app_db.client().get(path)
    assert feed.status == 200 and feed.headers["Content-Type"].startswith("text/calendar")
    text = feed.text.replace("\r\n ", "")
    assert text.startswith("BEGIN:VCALENDAR\r\n") and "TZID:Asia/Baku" in text and "DTSTART;TZID=Asia/Baku:" in text
    assert text.count("BEGIN:VEVENT") >= 20 and "SUMMARY:Ali riyaziyyat I · Mühazirə" in text
    les = q("SELECT l.* FROM lessons l JOIN courses co ON co.id=l.course_id WHERE co.code='RİY-1101' AND l.day>? AND l.status='scheduled' "
            "ORDER BY l.day LIMIT 1", (store.now().date().isoformat(),))[0]
    assert app_db.client("admin").post(f"/api/lessons/{les['id']}/cancel", {"reason": "Bayram tədbiri"}).status == 200
    after = app_db.client().get(path).text.replace("\r\n ", "")
    event = after[after.index(f"UID:lesson-{les['id']}@"):].split("END:VEVENT")[0]
    assert "STATUS:CANCELLED" in event and "Bayram tədbiri" in event, "the feed follows the change"
    assert notes(student.user["id"], "ləğv")
    new = student.post("/api/me/calendar").json["url"]
    assert app_db.client().get(path).status == 404, "a new address replaces the old"
    assert student.delete("/api/me/calendar").json == {"active": False}
    assert app_db.client().get(new[new.index("/ical/"):]).status == 404
    assert q("SELECT token_hash FROM ical_feeds") == [] and "/ical/" not in str(q("SELECT * FROM audit WHERE action='calendar_feed'"))


def test_a_teacher_s_feed_holds_the_lessons_they_teach(app_db):
    teacher = app_db.client("teacher")
    url = teacher.post("/api/me/calendar").json["url"]
    text = app_db.client().get(url[url.index("/ical/"):]).text
    mine = q("SELECT COUNT(*) n FROM lessons WHERE teacher_id=? AND day BETWEEN ? AND ?",
             (teacher.user["id"], (store.now().date() - timedelta(days=60)).isoformat(), (store.now().date() + timedelta(days=200)).isoformat()))
    assert text.count("BEGIN:VEVENT") == mine[0]["n"] > 0


def test_unknown_feeds_and_the_rate_limit(app_db, rate_limits):
    anon = app_db.client()
    assert anon.get("/ical/" + "x" * 32).status == 404
    for _ in range(29):
        anon.get("/ical/yox")
    assert anon.get("/ical/yox").status == 429
