"""Clubs and channels (tasks/todo.md, Task 35): approval, membership, the code of conduct, announcement channels,
polling, reports and moderation (audited), muting with its end time, removal, the retention purge and the limits."""
from datetime import datetime, timedelta, timezone

import pytest

from zeka.core import clock
from zeka.legacy import periodic, store


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def build_club(app_db, prefix: str) -> dict:
    """An approved club led by a fresh student, a member let in, an outsider; ids of its channels."""
    admin = app_db.client("admin")
    gid = q("SELECT group_id FROM users WHERE username='aysel'")[0]["group_id"]
    people = {}
    for role in ("lead", "member", "out"):
        name = f"{prefix}.{role}"
        admin.post("/api/directory/users", {"username": name, "full_name": f"Klub {name}", "role": "student", "group_id": gid,
                                            "student_no": name.upper().replace(".", "")})
        s = app_db.client()
        r = s.post("/api/auth/demo", {"role": "student", "user": name})
        assert r.status == 200
        s.user = r.json["user"]
        people[role] = s
    lead, member = people["lead"], people["member"]
    cid = lead.post("/api/clubs", {"name": f"Robototexnika {prefix}", "description": "Robotlar quran tələbələrin klubu"}).json["id"]
    office = app_db.client("office")
    assert office.post(f"/api/clubs/{cid}/decide", {"approve": True}).status == 200
    assert member.post(f"/api/clubs/{cid}/join").status == 200
    assert lead.post(f"/api/clubs/{cid}/members/{member.user['id']}/approve").status == 200
    channels = {ch["kind"]: ch["id"] for ch in lead.get(f"/api/clubs/{cid}").json["channels"]}
    for s in (lead, member):
        assert s.post(f"/api/clubs/{cid}/conduct").status == 200
    mid = lead.post(f"/api/channels/{channels['chat']}/messages", {"text": "Xoş gəldiniz!"}).json["id"]
    return {**people, "office": office, "club": cid, "chat": channels["chat"], "announce": channels["announce"], "message": mid}


@pytest.fixture(scope="module")
def club(app_db):
    return build_club(app_db, "kb1")


def test_a_club_is_approved_by_a_dean_s_office_and_gets_its_channels(app_db):
    s = app_db.client("student")
    cid = s.post("/api/clubs", {"name": "Şahmat klubu", "description": "Həftədə iki dəfə şahmat oyunları"}).json["id"]
    assert s.post("/api/clubs", {"name": "Ab", "description": "Həftədə iki dəfə"}).status == 400
    assert app_db.client("leader").post(f"/api/clubs/{cid}/decide", {"approve": True}).status == 403
    assert s.post(f"/api/clubs/{cid}/decide", {"approve": True}).status == 403
    office = app_db.client("office")
    assert cid in [x["id"] for x in office.get("/api/clubs/pending").json]
    assert office.post(f"/api/clubs/{cid}/decide", {"approve": "yes"}).status == 400
    assert office.post(f"/api/clubs/{cid}/decide", {"approve": True}).status == 200
    assert office.post(f"/api/clubs/{cid}/decide", {"approve": True}).status == 404, "decided once"
    got = s.get(f"/api/clubs/{cid}").json
    assert [ch["kind"] for ch in got["channels"]] == ["chat", "announce"] and got["membership"]["role"] == "leader"
    assert q("SELECT 1 FROM audit WHERE action='club_decide' AND detail LIKE ?", (f"#{cid} approved",))


def test_conduct_first_announcements_by_the_leader_and_polling_since_an_id(app_db, club):
    m = club["member"]
    fresh = build_club(app_db, "kb2")
    newcomer = fresh["out"]
    assert newcomer.post(f"/api/clubs/{fresh['club']}/join").status == 200
    assert fresh["lead"].post(f"/api/clubs/{fresh['club']}/members/{newcomer.user['id']}/approve").status == 200
    assert newcomer.post(f"/api/channels/{fresh['chat']}/messages", {"text": "Salam"}).status == 409, "the code of conduct first"
    assert newcomer.post(f"/api/clubs/{fresh['club']}/conduct").status == 200
    assert newcomer.post(f"/api/channels/{fresh['chat']}/messages", {"text": "Salam"}).status == 200
    assert m.post(f"/api/channels/{club['announce']}/messages", {"text": "Elan"}).status == 403
    assert club["lead"].post(f"/api/channels/{club['announce']}/messages", {"text": "Cümə toplantı var"}).status == 200
    assert m.post(f"/api/channels/{club['chat']}/messages", {"text": "x" * 2001}).status == 400
    first = m.get(f"/api/channels/{club['chat']}/messages").json["messages"]
    last = first[-1]["id"]
    new = m.post(f"/api/channels/{club['chat']}/messages", {"text": "Mən gəlirəm"}).json["id"]
    assert [x["id"] for x in m.get(f"/api/channels/{club['chat']}/messages?since_id={last}").json["messages"]] == [new]
    assert m.get(f"/api/channels/{club['chat']}/messages?since_id=abc").status == 400


def test_a_report_reaches_the_moderators_and_each_step_is_audited(app_db, club):
    bad = club["member"].post(f"/api/channels/{club['chat']}/messages", {"text": "Kontrol işinin cavablarını satıram"}).json["id"]
    assert club["lead"].post(f"/api/club-messages/{bad}/report", {"reason": "Akademik dürüstlüyə ziddir"}).status == 200
    assert club["out"].post(f"/api/club-messages/{bad}/report", {"reason": "Akademik dürüstlüyə ziddir"}).status == 403
    office_queue = club["office"].get("/api/community/reports").json
    report = next(x for x in office_queue if x["message_id"] == bad)
    assert report["author"] == club["member"].user["full_name"] and "satıram" in report["text"]
    assert bad in [x["message_id"] for x in club["lead"].get("/api/community/reports").json], "the leader sees the club's reports"
    assert club["member"].get("/api/community/reports").status == 403
    assert club["member"].post(f"/api/community/reports/{report['id']}/resolve", {"action": "hide"}).status == 403
    assert club["office"].post(f"/api/community/reports/{report['id']}/resolve", {"action": "hide"}).status == 200
    assert club["office"].post(f"/api/community/reports/{report['id']}/resolve", {"action": "hide"}).status == 404, "resolved once"
    assert bad not in [x["id"] for x in club["member"].get(f"/api/channels/{club['chat']}/messages").json["messages"]]
    assert [x["hidden"] for x in club["lead"].get(f"/api/channels/{club['chat']}/messages").json["messages"] if x["id"] == bad] == [1]
    assert q("SELECT 1 FROM audit WHERE action='club_report' AND detail LIKE ?", (f"#{bad} %",))
    assert q("SELECT 1 FROM audit WHERE action='club_message_hide' AND detail LIKE ?", (f"#{bad} %",))


def test_a_muted_member_is_told_until_when_and_writes_again_after(app_db, club, monkeypatch):
    m, lead = club["member"], club["lead"]
    assert lead.post(f"/api/clubs/{club['club']}/members/{m.user['id']}/mute", {"minutes": 2, "reason": "spam"}).status == 400
    assert m.post(f"/api/clubs/{club['club']}/members/{lead.user['id']}/mute", {"minutes": 30, "reason": "spam"}).status == 403
    assert lead.post(f"/api/clubs/{club['club']}/members/{m.user['id']}/mute", {"minutes": 30, "reason": "Təkrar reklam"}).status == 200
    until = q("SELECT muted_until FROM club_members WHERE club_id=? AND user_id=?", (club["club"], m.user["id"]))[0]["muted_until"]
    r = m.post(f"/api/channels/{club['chat']}/messages", {"text": "Niyə?"})
    assert r.status == 403 and until.replace("T", " ")[:16] in r.json["error"]
    assert q("SELECT 1 FROM audit WHERE action='club_mute' AND detail LIKE ?", (f"#{club['club']} user #{m.user['id']} until%",))
    later = datetime.fromisoformat(until).replace(tzinfo=clock.ZONE) + timedelta(minutes=1)
    monkeypatch.setattr(clock, "now", lambda: later.astimezone(timezone.utc))
    assert m.post(f"/api/channels/{club['chat']}/messages", {"text": "Bağışlayın"}).status == 200


def test_a_removed_member_reaches_no_channel_and_cannot_ask_again(app_db):
    w = build_club(app_db, "kb3")
    m = w["member"]
    assert w["lead"].post(f"/api/clubs/{w['club']}/members/{m.user['id']}/remove").status == 200
    assert m.get(f"/api/channels/{w['chat']}/messages").status == 403
    assert m.post(f"/api/clubs/{w['club']}/join").status == 403
    assert w["lead"].post(f"/api/clubs/{w['club']}/members/{w['lead'].user['id']}/remove").status == 404, "never the leader"


def test_the_retention_purge_deletes_old_messages_and_their_reports(app_db, club):
    old = (store.now() - timedelta(days=181)).isoformat(timespec="seconds")
    c = store.connect()
    try:
        mid = c.execute("INSERT INTO club_messages(channel_id,author_id,text,created_at) VALUES(?,?,?,?)",
                        (club["chat"], club["lead"].user["id"], "köhnə mesaj", old)).lastrowid
        c.execute("INSERT INTO club_reports(message_id,reporter_id,reason,created_at) VALUES(?,?,?,?)", (mid, club["member"].user["id"], "köhnə", old))
        c.commit()
        assert "club messages 1" in periodic.retention_purge(c)
        c.commit()
    finally:
        c.close()
    assert not q("SELECT 1 FROM club_messages WHERE id=?", (mid,)) and not q("SELECT 1 FROM club_reports WHERE message_id=?", (mid,))
    assert q("SELECT 1 FROM club_messages WHERE id=?", (club["message"],)), "a new one stays"


def test_a_member_writes_at_most_twenty_messages_a_minute(app_db, rate_limits):
    w = build_club(app_db, "kb4")
    codes = [w["member"].post(f"/api/channels/{w['chat']}/messages", {"text": f"mesaj {i}"}).status for i in range(21)]
    assert codes.count(200) == 20 and codes[-1] == 429
