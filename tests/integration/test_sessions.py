"""Session hardening (tasks/todo.md, Task 11): hashed ids, idle and absolute limits per role, rotation, the list.

The clock is moved by patching ``clock.now``; every timestamp of the server (``store.now``) follows it.
"""
import hashlib
import json
import re
from datetime import timedelta

import pytest

from zeka.core import clock, security
from zeka.legacy import store
from zeka.modules.identity import domain


@pytest.fixture
def later(monkeypatch):
    """later(hours=...) moves the server's clock forward from the real time of the test."""
    base, shift = clock.now(), [timedelta()]
    monkeypatch.setattr(clock, "now", lambda: base + shift[0])

    def move(**kw):
        shift[0] += timedelta(**kw)
    return move


def sid_of(response) -> str:
    return re.search(r"zeka_sid=([^;]+)", response.headers["Set-Cookie"]).group(1)


def demo_client(app_db, role):
    c = app_db.client()
    r = c.post("/api/auth/demo", {"role": role})
    assert r.status == 200
    return c, sid_of(r)


def test_a_copy_of_the_database_holds_no_usable_session(app_db):
    _, sid = demo_client(app_db, "teacher")
    db = store.connect()
    try:
        dump = json.dumps([dict(r) for r in store.rows(db, "SELECT * FROM sessions")])
        stored = [r["id_hash"] for r in store.rows(db, "SELECT id_hash FROM sessions")]
    finally:
        db.close()
    assert sid not in dump and hashlib.sha256(sid.encode()).hexdigest() in stored
    for h in stored:                                    # what the copy holds does not sign anyone in
        assert app_db.client().get("/api/me", headers={"Cookie": f"zeka_sid={h}"}).status == 401


@pytest.mark.parametrize("role, idle_h, absolute_h, step_h", [("student", 8, 30 * 24, 7), ("teacher", 1, 24, 0.8)])
def test_idle_and_absolute_limits_follow_the_role(app_db, later, role, idle_h, absolute_h, step_h):
    c, _ = demo_client(app_db, role)
    later(hours=idle_h - 0.05)
    assert c.get("/api/me").status == 200                # active just before the idle limit
    later(hours=idle_h + 0.05)
    assert c.get("/api/me").status == 401                # idle for longer than the limit
    c, _ = demo_client(app_db, role)
    used = 0.0
    while used + step_h < absolute_h:                   # always active, never idle for long ...
        later(hours=step_h)
        used += step_h
        assert c.get("/api/me").status == 200, used
    later(hours=absolute_h - used + 0.1)
    assert c.get("/api/me").status == 401                # ... but older than the absolute limit


def test_a_tenant_setting_overrides_the_limits(app_db, later):
    db = store.connect()
    db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('session_limits', ?)",
               (json.dumps({"student": {"idle_minutes": 30, "absolute_hours": 2}}),))
    db.commit()
    db.close()
    try:
        c, _ = demo_client(app_db, "student")
        later(minutes=31)
        assert c.get("/api/me").status == 401
    finally:
        db = store.connect()
        db.execute("DELETE FROM settings WHERE key='session_limits'")
        db.commit()
        db.close()


def test_the_id_changes_at_sign_in_and_the_old_one_stops_working(app_db):
    c, first = demo_client(app_db, "student")
    second = sid_of(c.post("/api/auth/demo", {"role": "student"}))
    assert first != second
    assert app_db.client().get("/api/me", headers={"Cookie": f"zeka_sid={first}"}).status == 401
    assert c.get("/api/me").status == 200


def test_a_password_change_renews_the_id_and_ends_the_other_sessions(app_db, monkeypatch):
    monkeypatch.setattr(domain, "N", 2 ** 4)
    monkeypatch.setattr(security.CFG, "proxy_hops", 0)
    other, _ = demo_client(app_db, "office")
    me, old = demo_client(app_db, "office")
    r = me.post("/api/auth/password", {"current": "", "new": "dekanlığın yeni uzun parolu"})
    assert r.status == 200 and sid_of(r) != old
    assert app_db.client().get("/api/me", headers={"Cookie": f"zeka_sid={old}"}).status == 401
    assert me.get("/api/me").status == 200 and other.get("/api/me").status == 401


def test_the_session_list_shows_only_ones_own_and_ends_them(app_db):
    phone, _ = demo_client(app_db, "leader")
    laptop, _ = demo_client(app_db, "leader")
    stranger, _ = demo_client(app_db, "admin")
    mine = laptop.get("/api/me/sessions").json
    assert len(mine) >= 2 and sum(s["current"] for s in mine) == 1 and {"id", "last_seen", "ip", "agent"} <= set(mine[0])
    theirs = stranger.get("/api/me/sessions").json
    assert not {s["id"] for s in theirs} & {s["id"] for s in mine}
    assert stranger.delete(f"/api/me/sessions/{mine[0]['id']}").status == 404          # not their session
    other = next(s for s in mine if not s["current"])
    assert laptop.delete(f"/api/me/sessions/{other['id']}").status == 200
    assert phone.get("/api/me").status == 401 and laptop.get("/api/me").status == 200
    demo_client(app_db, "leader")
    assert laptop.post("/api/me/sessions/end-others").json["ended"] >= 1
    current = next(s for s in laptop.get("/api/me/sessions").json if s["current"])
    r = laptop.delete(f"/api/me/sessions/{current['id']}")
    assert r.status == 200 and "Max-Age=0" in r.headers["Set-Cookie"] and laptop.get("/api/me").status == 401
