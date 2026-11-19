"""Clubs and channels (tasks/todo.md, Task 35): approval, membership, the code of conduct, announcement channels,
polling, reports and moderation (audited), muting with its end time, removal, the retention purge and the limits."""
import json
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
        kept = c.execute("INSERT INTO club_messages(channel_id,author_id,text,created_at) VALUES(?,?,?,?)",   # T-E14: inside 180 days
                         (club["chat"], club["lead"].user["id"], "179 günlük", (store.now() - timedelta(days=179)).isoformat(timespec="seconds"))).lastrowid
        c.commit()
        assert "club messages 1" in periodic.retention_purge(c)
        c.commit()
    finally:
        c.close()
    assert not q("SELECT 1 FROM club_messages WHERE id=?", (mid,)) and not q("SELECT 1 FROM club_reports WHERE message_id=?", (mid,))
    assert q("SELECT 1 FROM club_messages WHERE id=?", (club["message"],)), "a new one stays"
    assert q("SELECT 1 FROM club_messages WHERE id=?", (kept,)), "179 days old stays"


def test_a_member_writes_at_most_twenty_messages_a_minute(app_db, rate_limits):
    w = build_club(app_db, "kb4")
    codes = [w["member"].post(f"/api/channels/{w['chat']}/messages", {"text": f"mesaj {i}"}).status for i in range(21)]
    assert codes.count(200) == 20 and codes[-1] == 429


# ---------------------------------------------------------------- Checkpoint E (area B)
def test_leaving_and_asking_again_keeps_a_mute_and_never_undoes_a_removal(app_db):
    """SEC-E5: leave deleted the row, so leave + join cleared a removal and a mute."""
    w = build_club(app_db, "kb5")
    m, lead, cid = w["member"], w["lead"], w["club"]
    assert lead.post(f"/api/clubs/{cid}/members/{m.user['id']}/mute", {"minutes": 60, "reason": "Təkrar reklam"}).status == 200
    assert m.post(f"/api/clubs/{cid}/leave").status == 200
    assert q("SELECT 1 FROM audit WHERE action='club_leave' AND user_id=? AND detail=?", (m.user["id"], f"#{cid}"))
    assert m.post(f"/api/clubs/{cid}/join").json["membership"]["status"] == "requested"
    assert lead.post(f"/api/clubs/{cid}/members/{m.user['id']}/approve").status == 200
    assert m.post(f"/api/channels/{w['chat']}/messages", {"text": "Yenə buradayam"}).status == 403, "still muted"
    assert lead.post(f"/api/clubs/{cid}/members/{m.user['id']}/remove").status == 200
    assert m.post(f"/api/clubs/{cid}/leave").status == 200
    assert q("SELECT status FROM club_members WHERE club_id=? AND user_id=?", (cid, m.user["id"])) == [{"status": "removed"}]
    assert m.post(f"/api/clubs/{cid}/join").status == 403


def test_a_leader_neither_learns_who_reported_nor_closes_a_report_on_their_own_message(app_db):
    """TM-E4: the leader saw the reporter and kept the report on their own message out of the office's queue."""
    w = build_club(app_db, "kb6")
    on_leader = w["member"].post(f"/api/club-messages/{w['message']}/report", {"reason": "Təhqiramiz ifadə"}).json["id"]
    theirs = w["member"].post(f"/api/channels/{w['chat']}/messages", {"text": "Bu da mənim mesajım"}).json["id"]
    assert w["lead"].post(f"/api/club-messages/{theirs}/report", {"reason": "Mövzudan kənar"}).status == 200
    led = w["lead"].get("/api/community/reports").json
    assert [r["message_id"] for r in led if r["club_id"] == w["club"]] == [theirs]
    assert all("reporter" not in r for r in led)
    office = {r["id"]: r for r in w["office"].get("/api/community/reports").json}
    assert office[on_leader]["reporter"] == w["member"].user["full_name"], "the office sees it, with the reporter"
    assert w["lead"].post(f"/api/community/reports/{on_leader}/resolve", {"action": "keep"}).status == 403
    assert w["office"].post(f"/api/community/reports/{on_leader}/resolve", {"action": "keep"}).status == 200


def test_one_open_report_per_person_and_ten_asks_in_ten_minutes(app_db, rate_limits):
    """TM-E17: 60 reports of one message, 60 proposals and a leave/join loop flooding the leader all went through."""
    w = build_club(app_db, "kb7")
    a = w["member"].post(f"/api/club-messages/{w['message']}/report", {"reason": "Spam"}).json["id"]
    assert w["member"].post(f"/api/club-messages/{w['message']}/report", {"reason": "Spam yenə"}).json["id"] == a
    assert len(q("SELECT 1 FROM club_reports WHERE message_id=? AND reporter_id=?", (w["message"], w["member"].user["id"]))) == 1
    out, cid = w["out"], w["club"]

    def asks():
        return q("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND title LIKE '%Kluba üzvlük sorğusu%'", (w["lead"].user["id"],))[0]["n"]
    before = asks()
    codes = []
    for _ in range(11):
        codes.append(out.post(f"/api/clubs/{cid}/join").status)
        out.post(f"/api/clubs/{cid}/leave")
    assert codes[:10] == [200] * 10 and codes[10] == 429, codes
    assert asks() - before == 10, "the leader is told at most ten times"


@pytest.mark.parametrize("bad", ["abc", -1, 0, True, None])
def test_a_bad_retention_setting_keeps_the_default(app_db, club, bad):
    """SF-E13: "abc" rolled the whole purge job back; -1 deleted every message."""
    c = store.connect()
    try:
        limits = store.setting(c, "limits") or {}
        c.execute("UPDATE settings SET value=? WHERE key='limits'", (json.dumps({**limits, "community_retention_days": bad}),))
        mid = c.execute("INSERT INTO club_messages(channel_id,author_id,text,created_at) VALUES(?,?,?,?)",
                        (club["chat"], club["lead"].user["id"], "100 günlük", (store.now() - timedelta(days=100)).isoformat(timespec="seconds"))).lastrowid
        c.commit()
        try:
            periodic.retention_purge(c)
            c.commit()
        finally:
            c.execute("UPDATE settings SET value=? WHERE key='limits'", (json.dumps(limits),))
            c.commit()
    finally:
        c.close()
    assert q("SELECT 1 FROM club_messages WHERE id=?", (mid,)), "inside the default 180 days"


def test_a_member_s_poll_names_the_messages_hidden_since(app_db):
    """SF-E8: a message hidden after the page loaded stayed on a member's screen."""
    w = build_club(app_db, "kb8")
    mid = w["member"].post(f"/api/channels/{w['chat']}/messages", {"text": "Gizlənəcək"}).json["id"]
    assert w["lead"].post(f"/api/club-messages/{mid}/hide").status == 200
    assert mid in w["member"].get(f"/api/channels/{w['chat']}/messages?since_id={mid}").json["hidden"]
    assert w["lead"].get(f"/api/channels/{w['chat']}/messages?since_id={mid}").json["hidden"] == [], "a moderator keeps seeing it"
