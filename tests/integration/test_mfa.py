"""Second factor for staff (tasks/todo.md, Task 12): enrolment first, then a code at every sign-in.

Codes are computed from the account's secret at the real time, exactly as an authenticator app would.
"""
import re
import types

import pytest

from zeka.core import security
from zeka.legacy import store
from zeka.modules.identity import domain, service

GOOD = "müəllimin uzun və yaxşı parolu"


NOW = [1_900_000_005.0]          # the service's clock (time.time()); codes are computed for it, as an app would


@pytest.fixture(autouse=True)
def setup(app_db, monkeypatch):
    NOW[0] += 3600
    monkeypatch.setattr(service, "time", types.SimpleNamespace(time=lambda: NOW[0]))
    monkeypatch.setattr(domain, "N", 2 ** 4)
    monkeypatch.setattr(security.CFG, "proxy_hops", 1)
    c = store.connect()
    try:
        c.execute("DELETE FROM login_blocks")
        c.execute("DELETE FROM recovery_codes")
        c.execute("UPDATE users SET password_hash=NULL, must_change=0, failed_count=0, locked_until=NULL, status='active', "
                  "totp_secret=NULL, totp_last=NULL, totp_enabled_at=NULL")
        c.commit()
    finally:
        c.close()


def account(role):
    c = store.connect()
    try:
        name = store.setting(c, "demo_logins")[role]
        c.execute("UPDATE users SET password_hash=? WHERE username=?", (domain.hash_password(GOOD), name))
        c.commit()
        return name
    finally:
        c.close()


def secret_of(name):
    c = store.connect()
    try:
        return store.row(c, "SELECT totp_secret FROM users WHERE username=?", (name,))["totp_secret"]
    finally:
        c.close()


def code(secret, shift=0):
    return domain.hotp(domain.totp_key(secret), int(NOW[0]) // 30 + shift)


def sign_in(app_db, name, ip="10.2.0.1"):
    client = app_db.client()
    r = client.post("/api/auth/login", {"login": name, "password": GOOD}, headers={"X-Forwarded-For": ip})
    assert r.status == 200, r.json
    return client, r


def sid_of(r):
    return re.search(r"zeka_sid=([^;]+)", r.headers["Set-Cookie"]).group(1)


def enrolled(app_db, role="teacher"):
    """A staff account with its second factor; returns (name, secret, recovery codes)."""
    name = account(role)
    client, r = sign_in(app_db, name)
    assert r.json["user"]["scope"] == "mfa_enroll"
    secret = client.post("/api/auth/mfa/enroll").json["secret"]
    done = client.post("/api/auth/mfa/confirm", {"code": code(secret)})
    assert done.status == 200
    return name, secret, done.json["recovery_codes"]


def wait_for_next_step():
    NOW[0] += 30


def test_staff_without_a_second_factor_reach_only_the_enrolment(app_db):
    name = account("teacher")
    client, r = sign_in(app_db, name)
    assert r.json["user"]["scope"] == "mfa_enroll"
    assert client.get("/api/teacher/home").status == 403
    assert client.get("/api/bootstrap").json["user"]["scope"] == "mfa_enroll"
    enrol = client.post("/api/auth/mfa/enroll")
    assert enrol.status == 200 and enrol.json["uri"].startswith("otpauth://totp/") and "<svg" in enrol.json["qr"]
    assert client.post("/api/auth/mfa/confirm", {"code": "000000"}).status == 401
    done = client.post("/api/auth/mfa/confirm", {"code": code(enrol.json["secret"])})
    assert done.status == 200 and len(done.json["recovery_codes"]) == 10 and done.json["user"]["scope"] == "full"
    assert client.get("/api/teacher/home").status == 200
    assert client.post("/api/auth/mfa/enroll").status == 409


def test_a_signed_in_staff_member_needs_the_code_and_gets_a_new_session_id(app_db):
    name, secret, _ = enrolled(app_db)
    client, r = sign_in(app_db, name)
    assert r.json["user"]["scope"] == "mfa"
    assert client.get("/api/teacher/home").status == 403
    before = sid_of(r)
    wait_for_next_step()                                    # the step used at enrolment is spent
    ok = client.post("/api/auth/mfa/verify", {"code": code(secret)})
    assert ok.status == 200 and sid_of(ok) != before
    assert client.get("/api/teacher/home").status == 200
    assert app_db.client().get("/api/me", headers={"Cookie": f"zeka_sid={before}"}).status == 401


def test_a_code_is_accepted_only_once_in_its_window(app_db):
    name, secret, _ = enrolled(app_db)
    wait_for_next_step()
    now = code(secret)
    first, _ = sign_in(app_db, name)
    assert first.post("/api/auth/mfa/verify", {"code": now}).status == 200
    second, _ = sign_in(app_db, name, ip="10.2.0.2")
    replay = second.post("/api/auth/mfa/verify", {"code": now})
    assert replay.status == 401 and "Qalan" in replay.json["error"] or "left" in replay.json["error"]


def test_a_recovery_code_works_once(app_db):
    name, _, codes = enrolled(app_db, "office")
    client, _ = sign_in(app_db, name)
    r = client.post("/api/auth/mfa/verify", {"code": codes[0].upper()})
    assert r.status == 200 and r.json["recovery_left"] == 9
    again, _ = sign_in(app_db, name, ip="10.2.0.3")
    assert again.post("/api/auth/mfa/verify", {"code": codes[0]}).status == 401


def test_five_wrong_codes_cancel_the_pending_sign_in(app_db):
    name, secret, _ = enrolled(app_db, "leader")
    client, _ = sign_in(app_db, name, ip="10.2.0.9")
    for left in (4, 3, 2, 1):
        r = client.post("/api/auth/mfa/verify", {"code": "000000"})
        assert r.status == 401 and str(left) in r.json["error"]
    r = client.post("/api/auth/mfa/verify", {"code": "000000"})
    assert r.status == 401 and "Max-Age=0" in r.headers["Set-Cookie"]
    wait_for_next_step()
    assert client.post("/api/auth/mfa/verify", {"code": code(secret)}).status == 401     # even the right code: start again
    fresh, r = sign_in(app_db, name, ip="10.2.0.10")
    assert fresh.post("/api/auth/mfa/verify", {"code": code(secret)}).status == 200


def test_wrong_codes_count_with_wrong_passwords_for_that_address(app_db):
    name, secret, _ = enrolled(app_db, "admin")
    for _round in range(2):                                 # 2 pending sign-ins x 5 wrong codes = 10 failures
        client, _ = sign_in(app_db, name, ip="10.3.0.1")
        for _ in range(5):                                  # the proxy sends the client's address with every request
            client.post("/api/auth/mfa/verify", {"code": "000000"}, headers={"X-Forwarded-For": "10.3.0.1"})
    blocked = app_db.client().post("/api/auth/login", {"login": name, "password": GOOD}, headers={"X-Forwarded-For": "10.3.0.1"})
    assert blocked.status == 429 and "Retry-After" in blocked.headers


def test_a_student_may_turn_the_second_factor_on_and_off(app_db):
    name = account("student")
    client, r = sign_in(app_db, name)
    assert r.json["user"]["scope"] == "full"                # optional for students
    secret = client.post("/api/auth/mfa/enroll").json["secret"]
    assert client.post("/api/auth/mfa/confirm", {"code": code(secret)}).status == 200
    other, r = sign_in(app_db, name, ip="10.2.0.4")
    assert r.json["user"]["scope"] == "mfa"
    wait_for_next_step()
    assert client.post("/api/auth/mfa/disable", {"code": code(secret)}).status == 200
    assert sign_in(app_db, name, ip="10.2.0.5")[1].json["user"]["scope"] == "full"


def test_staff_cannot_turn_it_off_but_an_admin_can_reset_a_lost_device(app_db):
    name, secret, _ = enrolled(app_db, "teacher")
    wait_for_next_step()
    client, _ = sign_in(app_db, name)
    client.post("/api/auth/mfa/verify", {"code": code(secret)})
    assert client.post("/api/auth/mfa/disable", {"code": code(secret, 1)}).status == 403
    admin = app_db.client("admin")
    c = store.connect()
    uid = store.row(c, "SELECT id FROM users WHERE username=?", (name,))["id"]
    c.close()
    assert admin.post(f"/api/admin/users/{uid}/mfa-reset", {"reason": ""}).status == 400
    assert admin.post(f"/api/admin/users/{uid}/mfa-reset", {"reason": "Telefon itib, şəxsən yoxlanıldı"}).status == 200
    assert client.get("/api/me").status == 401                                  # its sessions ended
    assert sign_in(app_db, name)[1].json["user"]["scope"] == "mfa_enroll"
    assert secret_of(name) is None


def test_with_a_second_factor_eight_characters_are_enough(app_db):
    name = account("student")
    client, _ = sign_in(app_db, name)
    assert client.post("/api/auth/password", {"current": GOOD, "new": "dörd söz"}).status == 400     # 8 alone is short
    secret = client.post("/api/auth/mfa/enroll").json["secret"]
    client.post("/api/auth/mfa/confirm", {"code": code(secret)})
    assert client.post("/api/auth/password", {"current": GOOD, "new": "dörd söz"}).status == 200
