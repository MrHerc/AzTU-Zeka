"""Buildings, rooms and the room page behind a QR code (tasks/todo.md, Task 18).

The demo seeds two buildings and twelve rooms, and every demo timetable row names one of them."""
import base64
import csv
import io
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from zeka.core import clock
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


def csv_bytes(header, rows) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    w.writerows(rows)
    return out.getvalue().encode()


@pytest.fixture
def tuesday_0930(monkeypatch):
    """A Tuesday of the demo term at 09:30 in Baku, when EK-220 holds Ali riyaziyyat I (09:00-10:20)."""
    term = q("SELECT * FROM academic_terms WHERE active=1 ORDER BY teaching_start DESC LIMIT 1")[0]
    d = max(date.fromisoformat(term["teaching_start"]), store.now().date())
    d += timedelta(days=(1 - d.isoweekday()) % 7 + 1)                  # the next Tuesday
    assert d.isoformat() <= term["teaching_end"]
    monkeypatch.setattr(clock, "now", lambda: datetime(d.year, d.month, d.day, 5, 30, tzinfo=timezone.utc))
    return d


def test_every_demo_timetable_row_is_in_a_room(app_db):
    assert q("SELECT room FROM timetable WHERE room_id IS NULL") == []


def test_the_room_page_shows_the_lesson_now_and_next_without_names(app_db, tuesday_0930):
    page = app_db.client().get("/r/ek-220")
    assert page.status == 200 and page.headers["Content-Type"].startswith("text/html")
    body = page.text
    assert "EK-220" in body and "Ali riyaziyyat I" in body and "09:00–10:20" in body
    names = [r["full_name"] for r in q("SELECT full_name FROM users WHERE full_name IS NOT NULL")]
    assert not [n for n in names if n in body], "no student's or teacher's name on a public page"
    nxt = app_db.client().get("/r/EK-224").text            # its next lesson is on Wednesday at 12:00
    assert "12:00–13:20" in nxt and (tuesday_0930 + timedelta(days=1)).isoformat() in nxt


def test_the_room_page_follows_the_language(app_db, tuesday_0930):
    en = app_db.client(lang="en").get("/r/EK-220").text
    assert "Now" in en and "Next class" in en and "Capacity: 120 seats" in en


def test_an_unknown_or_closed_room_is_404(app_db):
    assert app_db.client().get("/r/YOX-1").status == 404
    run("UPDATE buildings SET active=0 WHERE code='IT'")
    try:
        assert app_db.client().get("/r/IT-101").status == 404
    finally:
        run("UPDATE buildings SET active=1 WHERE code='IT'")


def test_the_room_page_is_rate_limited(app_db, rate_limits):
    anon = app_db.client()
    assert all(anon.get("/r/EK-118").status == 200 for _ in range(60))
    assert anon.get("/r/EK-118").status == 429


def test_a_building_s_qr_sheet_holds_every_room_s_address(app_db):
    admin = app_db.client("admin")
    ek = q("SELECT id FROM buildings WHERE code='EK'")[0]["id"]
    sheet = admin.get(f"/api/facilities/buildings/{ek}/qr")
    assert sheet.status == 200
    codes = [r["code"] for r in q("SELECT code FROM rooms WHERE building_id=? AND active=1", (ek,))]
    assert sheet.text.count("<svg") == len(codes) == 10 and all(code in sheet.text for code in codes)
    assert 'src="/static/js/print.js"' in sheet.text and "onclick" not in sheet.text
    for role in ("teacher", "student", "office"):
        assert app_db.client(role).get(f"/api/facilities/buildings/{ek}/qr").status == 403, role
    assert admin.get("/api/facilities/buildings/999999/qr").status == 404


def test_rooms_are_kept_in_the_directory(app_db):
    admin = app_db.client("admin")
    ek = q("SELECT id FROM buildings WHERE code='EK'")[0]["id"]
    r = admin.post("/api/directory/rooms", {"building_id": ek, "code": "ek-600", "number": "600", "kind": "classroom",
                                            "capacity": 25, "accessible": True})
    assert r.status == 200 and r.json["code"] == "EK-600" and r.json["accessible"] == 1
    assert admin.post("/api/directory/rooms", {"building_id": ek, "code": "EK-600", "number": "6", "kind": "lab"}).status == 409
    for bad in ({"kind": "hovuz"}, {"capacity": -1}, {"accessible": "bəlkə"}, {"number": ""}):
        body = {"building_id": ek, "code": "EK-601", "number": "601", "kind": "lab", **bad}
        assert admin.post("/api/directory/rooms", body).status == 400, bad
    assert app_db.client("teacher").post("/api/directory/rooms", {"building_id": ek, "code": "EK-602", "number": "602",
                                                                    "kind": "lab"}).status == 403


def test_linking_reports_the_texts_that_name_no_room(app_db):
    admin = app_db.client("admin")
    course = q("SELECT id FROM courses ORDER BY id LIMIT 1")[0]["id"]
    run("INSERT INTO timetable(course_id,weekday,start,end,kind,room) VALUES(?,?,?,?,?,?)", (course, 6, "09:00", "10:20", "Məşğələ", "Bağ evi, 7"))
    run("INSERT INTO timetable(course_id,weekday,start,end,kind,room) VALUES(?,?,?,?,?,?)", (course, 6, "10:30", "11:50", "Məşğələ", "ek-118"))
    try:
        rep = admin.post("/api/facilities/link-rooms").json
        assert rep["unmatched"] == [{"room": "Bağ evi, 7", "rows": 1}]
        assert rep["linked"] == len(q("SELECT 1 FROM timetable WHERE room_id IS NOT NULL"))
        assert q("SELECT r.code FROM timetable t JOIN rooms r ON r.id=t.room_id WHERE t.room='ek-118'") == [{"code": "EK-118"}]
        assert admin.post("/api/facilities/link-rooms").json["changed"] == 0, "linking again changes nothing"
        assert app_db.client("teacher").post("/api/facilities/link-rooms").status == 403
    finally:
        run("DELETE FROM timetable WHERE weekday=6")


def test_rooms_import_from_a_csv(app_db):
    admin = app_db.client("admin")
    header = ["sourcedId", "identifier", "number", "name", "building", "floor", "kind", "capacity", "accessible"]
    rows = [["r1", "it-301", "301", "Şəbəkə laboratoriyası", "it", "3", "Kompüter laboratoriyası", "24", "bəli"],
            ["r2", "XX-1", "1", "", "XX", "", "", "", ""]]
    data = base64.b64encode(csv_bytes(header, rows)).decode()
    body = {"kind": "rooms", "source": "rooms-sis", "filename": "rooms.csv", "content_b64": data, "dry_run": False, "prefer_source": False}
    bad = admin.post("/api/admin/import", body).json
    assert [e["row"] for e in bad["errors"]] == [3] and not bad["written"], "an unknown building refuses the file"
    body["content_b64"] = base64.b64encode(csv_bytes(header, rows[:1])).decode()
    ok = admin.post("/api/admin/import", body).json
    assert ok["inserted"] == 1, ok
    assert q("SELECT code, kind, capacity, accessible, floor FROM rooms WHERE code='IT-301'") == [
        {"code": "IT-301", "kind": "computer_lab", "capacity": 24, "accessible": 1, "floor": 3}]
    again = admin.post("/api/admin/import", body).json
    assert again["inserted"] == again["updated"] == 0


def test_the_directory_lists_rooms_by_building(app_db):
    admin = app_db.client("admin")
    it = q("SELECT id FROM buildings WHERE code='IT'")[0]["id"]
    items = admin.get(f"/api/directory/rooms?building_id={it}").json["items"]
    assert items and all(x["building_id"] == it for x in items)
    assert re.search(r"IT-101", str(items))
