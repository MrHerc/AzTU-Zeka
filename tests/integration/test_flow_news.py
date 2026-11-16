"""News portal: feed, filters, reading, bookmarks, event registration, calendar export and the editor."""
from datetime import datetime, timedelta

import pytest


@pytest.fixture(scope="module")
def feed(student):
    return student.get("/api/news").json


def test_feed(feed):
    assert len(feed["items"]) >= 12 and feed["upcoming"] and feed["kinds"] and feed["unread"] >= 1
    pinned = [n["pinned"] for n in feed["items"]]
    assert pinned == sorted(pinned, reverse=True)                       # pinned first
    starts = [n["event_start"] for n in feed["upcoming"]]
    assert starts == sorted(starts) and all(not n["past"] for n in feed["upcoming"])


def test_filters(student, feed):
    ev = student.get("/api/news?kind=event").json["items"]
    assert ev and all(n["kind"] == "event" for n in ev)
    assert student.get("/api/news?kind=bogus").json["items"] == feed["items"]
    tag = feed["items"][0]["tags"][0] if feed["items"][0]["tags"] else feed["items"][0]["title"][:5]
    assert student.get("/api/news?q=" + __import__("urllib.parse").parse.quote(tag)).json["items"]


def test_detail_marks_as_read(student, feed):
    n = next(x for x in feed["items"] if not x["read"])
    d = student.get(f"/api/news/{n['id']}").json
    assert d["body"] and d["author"] and d["reads"] >= 1 and isinstance(d["related"], list)
    assert next(x for x in student.get("/api/news").json["items"] if x["id"] == n["id"])["read"] is True
    assert student.get("/api/news/999999").status == 404


def test_save_toggle(student, feed):
    nid = feed["items"][1]["id"]
    assert student.post(f"/api/news/{nid}/save").json["saved"] is True
    assert [n["id"] for n in student.get("/api/news?saved=1").json["items"]] == [nid]
    assert student.post(f"/api/news/{nid}/save").json["saved"] is False


def test_rsvp_toggle_schedule_and_ics(student, feed):
    ev = next(n for n in feed["items"] if n["registration"] and not n["registered"] and not n["past"])
    r = student.post(f"/api/news/{ev['id']}/rsvp").json
    assert r["registered"] is True and r["registered_count"] == ev["registered_count"] + 1
    assert any(n["id"] == ev["id"] for n in student.get("/api/news?mine=1").json["items"])
    assert any(e["id"] == ev["id"] for e in student.get("/api/schedule").json["events"])
    assert any("qeydiyyatınız" in n["title"] for n in student.get("/api/notifications").json["items"])
    ics = student.get(f"/api/news/{ev['id']}/ics")
    assert ics.headers["Content-Type"].startswith("text/calendar") and "BEGIN:VEVENT" in ics.text and "\r\n" in ics.text
    assert "DTSTART;TZID=Asia/Baku:" in ics.text and "attachment" in ics.headers["Content-Disposition"]
    assert student.post(f"/api/news/{ev['id']}/rsvp").json["registered"] is False


def test_rsvp_rules(student, teacher, office, feed):
    plain = next(n for n in feed["items"] if not n["registration"])
    assert student.post(f"/api/news/{plain['id']}/rsvp").status == 400
    if not plain["event_start"]:
        assert student.get(f"/api/news/{plain['id']}/ics").status == 400
    start = (datetime.now() + timedelta(days=3)).replace(microsecond=0).isoformat()
    tiny = office.post("/api/news", {"title": "Kiçik seminar: 1 yer", "summary": "Bir nəfərlik", "kind": "event", "event_start": start,
                                     "capacity": 1, "registration": True, "audience": "all"}).json
    assert student.post(f"/api/news/{tiny['id']}/rsvp").json["registered"] is True
    assert teacher.post(f"/api/news/{tiny['id']}/rsvp").status == 409                            # full
    past = (datetime.now() - timedelta(days=3)).replace(microsecond=0).isoformat()
    old = office.post("/api/news", {"title": "Keçmiş tədbir nümunəsi", "summary": "Bitib", "event_start": past, "duration_h": 1,
                                    "registration": True, "capacity": 10}).json
    assert old["past"] is True and student.post(f"/api/news/{old['id']}/rsvp").status == 409


def test_editor_validation_and_audience(student, teacher, office):
    assert office.post("/api/news", {"title": "Qısa", "summary": "x"}).status == 400
    assert office.post("/api/news", {"title": "Kifayət qədər uzun", "summary": ""}).status == 400
    assert office.post("/api/news", {"title": "Kifayət qədər uzun", "summary": "x", "event_start": "sabah"}).status == 400
    n = office.post("/api/news", {"title": "Yalnız müəllimlər üçün elan", "summary": "Kafedra iclası", "audience": "teachers",
                                  "important": True, "kind": "announcement", "tags": "iclas, kafedra", "tone": "neon"}).json
    assert n["tags"] == ["iclas", "kafedra"] and n["cover"]["tone"] == "navy" and n["kind"] == "announcement"
    assert student.get(f"/api/news/{n['id']}").status == 404
    assert teacher.get(f"/api/news/{n['id']}").status == 200
    assert any("müəllimlər üçün" in x["title"] for x in teacher.get("/api/notifications").json["items"])
    assert not any("müəllimlər üçün" in x["title"] for x in student.get("/api/notifications").json["items"])


def test_draft_publish_update_and_delete(student, office, leader, admin):
    d = office.post("/api/news", {"title": "Qaralama: imtahan cədvəli", "summary": "Tezliklə", "draft": True, "important": True}).json
    assert d["status"] == "draft"
    assert not any(x["id"] == d["id"] for x in student.get("/api/news").json["items"])
    assert student.get(f"/api/news/{d['id']}").status == 404
    assert any(x["id"] == d["id"] for x in office.get("/api/news/manage").json["items"])
    up = office.put(f"/api/news/{d['id']}", {"title": "İmtahan cədvəli dərc olundu", "summary": "Cədvəl hazırdır", "important": True}).json
    assert up["status"] == "published" and any("İmtahan cədvəli dərc" in x["title"] for x in student.get("/api/notifications").json["items"])
    assert office.put("/api/news/999999", {"title": "Mövcud olmayan", "summary": "x"}).status == 404
    assert office.delete(f"/api/news/{d['id']}").status == 403
    assert leader.delete(f"/api/news/{d['id']}").json == {"ok": True}
    assert student.get(f"/api/news/{d['id']}").status == 404
    assert admin.delete(f"/api/news/{d['id']}").status == 200                                       # idempotent
