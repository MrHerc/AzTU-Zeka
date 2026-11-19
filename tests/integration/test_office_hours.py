"""Office hours (tasks/todo.md, Task 34): a slot is booked once even by two requests at the same moment, the meeting is
in both iCal feeds, a cancel tells the other side, a reminder goes once, and the assistant answers with the hours."""
import threading
from datetime import datetime, timedelta, timezone

import pytest

from zeka.core import clock
from zeka.legacy import periodic, store
from zeka.modules.qa import office_hours


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


@pytest.fixture(scope="module")
def oh(app_db):
    admin, teacher = app_db.client("admin"), app_db.client("teacher")
    cid = q("SELECT id FROM courses WHERE code='ELM-2105'")[0]["id"]
    gid = q("SELECT group_id FROM users WHERE username='aysel'")[0]["group_id"]
    names = {}
    for n in ("oh.peer", "oh.out"):
        uid = admin.post("/api/directory/users", {"username": n, "full_name": f"Sınaq {n}", "role": "student", "group_id": gid,
                                                  "student_no": n.upper()}).json["id"]
        names[n] = uid
    admin.post(f"/api/directory/courses/{cid}/enrollments", {"user_id": names["oh.peer"]})

    def student(n):
        s = app_db.client()
        r = s.post("/api/auth/demo", {"role": "student", "user": n})
        assert r.status == 200
        s.user = r.json["user"]
        return s
    tomorrow = (store.now().date() + timedelta(days=1))
    return {"teacher": teacher, "aysel": app_db.client("student"), "peer": student("oh.peer"), "out": student("oh.out"),
            "weekday": tomorrow.isoweekday() if tomorrow.isoweekday() < 7 else 1, "day": tomorrow.isoformat()}


def test_a_teacher_sets_weekly_hours_and_bad_ranges_are_refused(oh):
    t = oh["teacher"]
    base = {"weekday": oh["weekday"], "start": "14:00", "end": "15:00", "slot_min": 15, "place": "EK-305"}
    for bad in ({"weekday": 7}, {"start": "15:00", "end": "14:00"}, {"end": "23:00"}, {"slot_min": 7}, {"place": "", "online_url": ""},
                {"place": "", "online_url": "http://meet.example/x"}, {"start": "1400"}, {"start": "+9:00"}, {"start": "٠٩:٠٠"}):
        assert t.post("/api/office-hours", {**base, **bad}).status == 400, bad
    assert oh["aysel"].post("/api/office-hours", base).status == 403
    hours = t.post("/api/office-hours", base).json
    assert [(h["start"], h["end"], h["slot_min"]) for h in hours] == [("14:00", "15:00", 15)]


def test_a_student_of_the_teacher_sees_free_slots_and_an_outsider_does_not(oh):
    tid = oh["teacher"].user["id"]
    assert tid in [x["id"] for x in oh["aysel"].get("/api/office-hours/teachers").json]
    free = oh["aysel"].get(f"/api/office-hours/teachers/{tid}/free").json
    assert [s["start"] for s in free if s["day"] == oh["day"]] == ["14:00", "14:15", "14:30", "14:45"]
    assert oh["out"].get(f"/api/office-hours/teachers/{tid}/free").status == 404
    h = free[0]
    assert oh["out"].post("/api/office-hours/book", {"hours_id": h["hours_id"], "day": h["day"], "start": h["start"]}).status == 404


def test_two_students_booking_the_same_slot_at_once_get_one_200_and_one_409(oh):
    tid = oh["teacher"].user["id"]
    slot = next(s for s in oh["aysel"].get(f"/api/office-hours/teachers/{tid}/free").json if s["start"] == "14:00")
    body = {"hours_id": slot["hours_id"], "day": slot["day"], "start": "14:00", "topic": "Laboratoriya hesabatı"}
    go, codes = threading.Barrier(2), []

    def book(client):
        go.wait()
        codes.append(client.post("/api/office-hours/book", body).status)
    threads = [threading.Thread(target=book, args=(oh[n],)) for n in ("aysel", "peer")]
    for x in threads:
        x.start()
    for x in threads:
        x.join()
    assert sorted(codes) == [200, 409], codes
    assert len(q("SELECT 1 FROM office_bookings WHERE day=? AND start='14:00' AND status='booked'", (slot["day"],))) == 1
    assert "14:00" not in [s["start"] for s in oh["peer"].get(f"/api/office-hours/teachers/{tid}/free").json if s["day"] == slot["day"]]


def _feed(app_db, client) -> str:
    url = client.post("/api/me/calendar").json["url"]
    return app_db.client().get("/" + url.split("/", 3)[3]).text


def test_the_meeting_is_in_both_feeds_and_a_cancel_tells_the_other_side(app_db, oh):
    b = q("SELECT id, student_id FROM office_bookings WHERE start='14:00' AND status='booked'")[0]
    owner = oh["aysel"] if b["student_id"] == oh["aysel"].user["id"] else oh["peer"]
    for who in (owner, oh["teacher"]):
        feed = _feed(app_db, who)
        block = feed.split(f"UID:office-{b['id']}@")[1].split("END:VEVENT")[0]
        assert "STATUS:CONFIRMED" in block and "Qəbul saatı" in block and "EK-305" in block
    assert oh["out"].post(f"/api/office-hours/bookings/{b['id']}/cancel").status == 404
    assert owner.post(f"/api/office-hours/bookings/{b['id']}/cancel").json["status"] == "cancelled"
    assert owner.post(f"/api/office-hours/bookings/{b['id']}/cancel").status == 400, "once"
    told = q("SELECT title FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 1", (oh["teacher"].user["id"],))[0]["title"]
    assert "ləğv olundu" in told
    assert "STATUS:CANCELLED" in _feed(app_db, oh["teacher"]).split(f"UID:office-{b['id']}@")[1].split("END:VEVENT")[0]


def test_a_teacher_s_cancel_tells_the_student_and_a_student_holds_at_most_two(oh):
    tid = oh["teacher"].user["id"]
    free = oh["aysel"].get(f"/api/office-hours/teachers/{tid}/free").json
    made = [oh["aysel"].post("/api/office-hours/book", {"hours_id": s["hours_id"], "day": s["day"], "start": s["start"]}) for s in free[:3]]
    assert [m.status for m in made] == [200, 200, 400]
    bid = made[0].json["id"]
    assert oh["teacher"].post(f"/api/office-hours/bookings/{bid}/cancel").status == 200
    told = q("SELECT title FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 1", (oh["aysel"].user["id"],))[0]["title"]
    assert "ləğv olundu" in told


def test_the_reminder_goes_once_to_both_sides(oh, monkeypatch):
    b = next(x for x in oh["aysel"].get("/api/office-hours/bookings").json if x["status"] == "booked")
    at = datetime.fromisoformat(f"{b['day']}T{b['start']}").replace(tzinfo=clock.ZONE) - timedelta(hours=1)
    monkeypatch.setattr(clock, "now", lambda: at.astimezone(timezone.utc))
    c = store.connect()
    try:
        assert office_hours.remind(c, periodic._once) == 1
        assert office_hours.remind(c, periodic._once) == 0, "once"
        c.commit()
    finally:
        c.close()
    for uid in (oh["aysel"].user["id"], oh["teacher"].user["id"]):
        assert "yaxınlaşır" in q("SELECT title FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,))[0]["title"]


def test_the_assistant_answers_with_the_teacher_s_office_hours(oh):
    a = oh["aysel"].post("/api/campus/ask", {"message": f"{oh['teacher'].user['full_name'].split()[0]} müəllimin qəbul saatı nə vaxtdır?"}).json["answer"]
    assert a["meta"]["source"] == "office_hours" and "14:00–15:00" in a["content"] and "EK-305" in a["content"]
    assert a["meta"]["actions"][0]["href"] == "/office-hours"


def test_overlapping_ranges_are_refused_and_an_adjacent_one_is_taken(oh):
    """Checkpoint E (CR-E5): two ranges sharing a minute would double-book the teacher."""
    t = oh["teacher"]
    base = {"weekday": oh["weekday"], "slot_min": 15, "place": "EK-305"}
    assert t.post("/api/office-hours", {**base, "start": "14:30", "end": "15:30"}).status == 400
    assert t.post("/api/office-hours", {**base, "start": "14:00", "end": "15:00"}).status == 400, "the same range again"
    made = t.post("/api/office-hours", {**base, "start": "15:00", "end": "15:30"})
    assert made.status == 200
    t.post(f"/api/office-hours/{max(h['id'] for h in made.json)}/end")


def test_the_teacher_s_feed_names_no_student_and_carries_no_topic(app_db, oh):
    """Checkpoint E (TM-E10): an external calendar service reads the teacher's feed."""
    tid = oh["teacher"].user["id"]
    s = oh["peer"]
    slot = next(x for x in s.get(f"/api/office-hours/teachers/{tid}/free").json if x["start"] == "14:45")
    b = s.post("/api/office-hours/book", {**{k: slot[k] for k in ("hours_id", "day", "start")}, "topic": "psixoloji problem"}).json
    teacher_block = _feed(app_db, oh["teacher"]).split(f"UID:office-{b['id']}@")[1].split("END:VEVENT")[0]
    assert "Sınaq oh.peer" not in teacher_block and "psixoloji" not in teacher_block and "Qəbul saatı" in teacher_block
    student_block = _feed(app_db, s).split(f"UID:office-{b['id']}@")[1].split("END:VEVENT")[0]
    assert "psixoloji problem" in student_block, "the student's own feed keeps the topic"
    s.post(f"/api/office-hours/bookings/{b['id']}/cancel")


def test_two_parallel_bookings_cannot_pass_the_cap_together(app_db, oh, monkeypatch):
    """Checkpoint E (TM-E9): both requests read the count before either writes; the write lock makes the second wait."""
    from zeka.modules.qa import repo
    t = oh["teacher"]
    tid = t.user["id"]
    hours = t.post("/api/office-hours", {"weekday": oh["weekday"], "start": "17:00", "end": "18:00", "slot_min": 15, "place": "EK-305"}).json
    hid = max(h["id"] for h in hours)
    s = oh["peer"]
    for b in q("SELECT id FROM office_bookings WHERE student_id=? AND teacher_id=? AND status='booked'", (s.user["id"], tid)):
        s.post(f"/api/office-hours/bookings/{b['id']}/cancel")
    free = [x for x in s.get(f"/api/office-hours/teachers/{tid}/free").json if x["hours_id"] == hid][:3]
    orig, meet = repo.open_bookings_with, threading.Barrier(2, timeout=2)

    def slow(c, *a):
        n = orig(c, *a)
        if not c.in_transaction:             # counted without the write lock: wait for the other request to count too
            try:
                meet.wait()
            except threading.BrokenBarrierError:
                pass
        return n
    monkeypatch.setattr(repo, "open_bookings_with", slow)
    first = free.pop(0)
    assert s.post("/api/office-hours/book", {k: first[k] for k in ("hours_id", "day", "start")}).status == 200
    codes: list = []
    clients = []
    for _ in range(2):                                            # one session per request: a client is not shared by threads
        other = app_db.client()
        other.post("/api/auth/demo", {"role": "student", "user": "oh.peer"})
        clients.append(other)
    threads = [threading.Thread(target=lambda x=x, cl=cl: codes.append(cl.post("/api/office-hours/book", {k: x[k] for k in ("hours_id", "day", "start")}).status))
               for x, cl in zip(free[:2], clients, strict=True)]
    for x in threads:
        x.start()
    for x in threads:
        x.join()
    n = q("SELECT COUNT(*) AS n FROM office_bookings WHERE student_id=? AND teacher_id=? AND status='booked'", (s.user["id"], tid))[0]["n"]
    assert n == 2, (n, codes)


def test_a_meeting_that_took_place_today_is_neither_cancelled_nor_counted(app_db, oh, monkeypatch):
    """Checkpoint E (CR-E4): ending a range at 14:00 leaves this morning's meetings as they were, and they no longer
    count toward the cap of two upcoming meetings."""
    admin, t = app_db.client("admin"), oh["teacher"]
    cid = q("SELECT id FROM courses WHERE code='ELM-2105'")[0]["id"]
    gid = q("SELECT group_id FROM users WHERE username='aysel'")[0]["group_id"]
    uid = admin.post("/api/directory/users", {"username": "oh.past", "full_name": "Sınaq oh.past", "role": "student", "group_id": gid,
                                              "student_no": "OHPAST"}).json["id"]
    admin.post(f"/api/directory/courses/{cid}/enrollments", {"user_id": uid})
    today = store.now().date()
    morning = datetime.combine(today, datetime.min.time()).replace(hour=7, tzinfo=clock.ZONE)
    monkeypatch.setattr(clock, "now", lambda: morning.astimezone(timezone.utc))
    hours = t.post("/api/office-hours", {"weekday": today.isoweekday(), "start": "08:00", "end": "09:00", "slot_min": 30, "place": "EK-305"}).json
    hid = max(h["id"] for h in hours)
    s = app_db.client()
    s.user = s.post("/api/auth/demo", {"role": "student", "user": "oh.past"}).json["user"]
    for start in ("08:00", "08:30"):
        assert s.post("/api/office-hours/book", {"hours_id": hid, "day": today.isoformat(), "start": start}).status == 200
    afternoon = morning.replace(hour=14)
    monkeypatch.setattr(clock, "now", lambda: afternoon.astimezone(timezone.utc))
    later = next(x for x in s.get(f"/api/office-hours/teachers/{t.user['id']}/free").json if x["day"] > today.isoformat() and x["hours_id"] != hid)
    assert s.post("/api/office-hours/book", {k: later[k] for k in ("hours_id", "day", "start")}).status == 200, "past meetings do not count"
    before = q("SELECT COUNT(*) AS n FROM notifications WHERE user_id=?", (uid,))[0]["n"]
    t = app_db.client("teacher")                                  # the morning session is past its idle limit
    assert t.post(f"/api/office-hours/{hid}/end").status == 200
    assert [r["status"] for r in q("SELECT status FROM office_bookings WHERE hours_id=? ORDER BY start", (hid,))] == ["booked", "booked"]
    assert q("SELECT COUNT(*) AS n FROM notifications WHERE user_id=?", (uid,))[0]["n"] == before


def test_a_person_s_bookings_are_read_through_an_index_on_both_sides():
    """Checkpoint E (AR-E5): the calendar feed and the bookings page do not scan office_bookings."""
    c = store.connect()
    try:
        plan = " ".join(r[3] for r in c.execute("EXPLAIN QUERY PLAN SELECT b.id FROM office_bookings b WHERE (b.student_id=? OR b.teacher_id=?) "
                                                "AND b.day BETWEEN ? AND ?", (1, 1, "2026-01-01", "2026-12-31")))
    finally:
        c.close()
    assert "SCAN b" not in plan, plan
