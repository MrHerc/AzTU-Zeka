"""Sign-in with a password (tasks/todo.md, Task 10): throttling, locks, temporary passwords, the prod mode.

scrypt runs with a small cost here (same code path); addresses are set through X-Forwarded-For with one trusted proxy.
"""
import time

import pytest

from zeka.core import config, security
from zeka.legacy import store
from zeka.modules.identity import domain

GOOD = "dəniz kənarında gəzinti 2026"


@pytest.fixture(autouse=True)
def setup(app_db, monkeypatch):
    monkeypatch.setattr(domain, "N", 2 ** 4)
    monkeypatch.setattr(security.CFG, "proxy_hops", 1)
    c = store.connect()
    try:
        c.execute("DELETE FROM login_blocks")
        c.execute("UPDATE users SET password_hash=NULL, must_change=0, failed_count=0, locked_until=NULL, status='active', email=NULL")
        c.commit()
    finally:
        c.close()


def account(role="student", password=GOOD, email=None):
    c = store.connect()
    try:
        username = store.setting(c, "demo_logins")[role]
        c.execute("UPDATE users SET password_hash=?, email=? WHERE username=?", (domain.hash_password(password), email, username))
        c.commit()
        return username
    finally:
        c.close()


def user_id(name):
    c = store.connect()
    try:
        return store.row(c, "SELECT id FROM users WHERE username=?", (name,))["id"]
    finally:
        c.close()


def sign_in(app_db, login, password, ip="10.0.0.1", client=None):
    client = client or app_db.client()
    return client, client.post("/api/auth/login", {"login": login, "password": password}, headers={"X-Forwarded-For": ip})


def audits(action):
    c = store.connect()
    try:
        return [r["detail"] for r in store.rows(c, "SELECT detail FROM audit WHERE action=?", (action,))]
    finally:
        c.close()


def block_until(name):
    c = store.connect()
    try:
        return store.row(c, "SELECT until FROM login_blocks WHERE account=?", (name,))["until"]
    finally:
        c.close()


def test_a_wrong_password_and_an_unknown_account_get_the_same_answer(app_db):
    name = account()
    _, wrong = sign_in(app_db, name, "tamamilə başqa bir parol")
    _, unknown = sign_in(app_db, "heç.kim.deyil", "tamamilə başqa bir parol")
    _, empty = sign_in(app_db, "", "tamamilə başqa bir parol")
    assert wrong.status == unknown.status == empty.status == 401
    assert wrong.json == unknown.json == empty.json


def test_the_right_password_signs_in_by_user_name_or_email(app_db):
    name = account(email="tələbə@aztu.edu.az")
    client, r = sign_in(app_db, name.upper(), GOOD)
    assert r.status == 200 and r.json["user"]["username"] == name and "token" not in r.json
    assert client.get("/api/bootstrap").json["user"]["username"] == name        # the session cookie works
    assert sign_in(app_db, "TƏLƏBƏ@aztu.edu.az", GOOD)[1].status == 200


def test_ten_failures_block_that_address_for_that_account_only(app_db):
    name = account()
    for _ in range(10):
        assert sign_in(app_db, name, "yanlış parol budur!", ip="10.0.0.5")[1].status == 401
    t = time.perf_counter()
    _, r = sign_in(app_db, name, GOOD, ip="10.0.0.5")                     # even the right password waits
    assert r.status == 429 and 890 <= int(r.headers["Retry-After"]) <= 900 and time.perf_counter() - t < 0.5
    until = block_until(name)
    for _ in range(5):                                                       # refused attempts are not counted
        assert sign_in(app_db, name, "yanlış parol budur!", ip="10.0.0.5")[1].status == 429
    assert block_until(name) == until
    assert sign_in(app_db, name, GOOD, ip="10.0.0.6")[1].status == 200       # another address
    assert any(name in d and "10.0.0.5" in d for d in audits("login_blocked"))


def test_fifty_failures_from_one_address_do_not_delay_another(app_db):
    name = account()
    for _ in range(50):
        assert sign_in(app_db, name, "yanlış parol budur!", ip="192.0.2.10")[1].status in (401, 429)
    t = time.perf_counter()
    assert sign_in(app_db, name, GOOD, ip="198.51.100.20")[1].status == 200
    assert time.perf_counter() - t < 0.5


def test_ipv6_addresses_of_one_64_network_share_a_block(app_db):
    name = account()
    for i in range(10):
        sign_in(app_db, name, "yanlış parol budur!", ip=f"2001:db8:7:7::{i + 1}")
    assert sign_in(app_db, name, GOOD, ip="2001:db8:7:7::ffff")[1].status == 429
    assert sign_in(app_db, name, GOOD, ip="2001:db8:7:8::1")[1].status == 200


def test_a_hundred_failures_lock_the_account_until_an_admin_unlocks_it(app_db):
    name = account()
    for i in range(100):                                                    # 10 addresses, 10 failures each
        assert sign_in(app_db, name, "yanlış parol budur!", ip=f"10.1.{i // 10}.1")[1].status == 401
    _, r = sign_in(app_db, name, GOOD, ip="10.9.9.9")
    assert r.status == 429 and int(r.headers["Retry-After"]) > 800
    assert name in audits("account_locked")
    admin, uid = app_db.client("admin"), user_id(name)
    assert admin.post(f"/api/admin/users/{uid}/unlock", {"reason": ""}).status == 400
    assert admin.post(f"/api/admin/users/{uid}/unlock", {"reason": "Tələbə zəng etdi, şəxsiyyəti yoxlandı"}).status == 200
    assert any("şəxsiyyəti yoxlandı" in d for d in audits("account_unlocked"))
    assert sign_in(app_db, name, GOOD, ip="10.9.9.9")[1].status == 200


def test_a_temporary_password_opens_only_the_password_change(app_db):
    name = account()
    temp = app_db.client("admin").post(f"/api/admin/users/{user_id(name)}/temp-password", {}).json["password"]
    assert name in audits("temp_password")
    client, r = sign_in(app_db, name, temp)
    assert r.status == 200 and r.json["user"]["must_change"] is True
    assert client.get("/api/student/home").status == 403
    weak = client.post("/api/auth/password", {"current": temp, "new": "qısa"}, lang="en")
    assert weak.status == 400 and "15" in weak.json["error"]
    assert client.post("/api/auth/password", {"current": temp, "new": "passwordpassword"}).status == 400
    assert client.post("/api/auth/password", {"current": "yanlış", "new": GOOD}).status == 403
    ok = client.post("/api/auth/password", {"current": temp, "new": "yeni uzun parol, özüm seçdim"})
    assert ok.status == 200 and ok.json["user"]["must_change"] is False
    assert client.get("/api/student/home").status == 200
    assert name in audits("password_changed")


def test_only_an_admin_issues_temporary_passwords(app_db):
    uid = user_id(account())
    for role in ("student", "teacher", "office", "leader"):
        assert app_db.client(role).post(f"/api/admin/users/{uid}/temp-password", {}).status == 403, role
    assert app_db.client("admin").post("/api/admin/users/999999/temp-password", {}).status == 404


def test_the_hash_is_upgraded_at_the_next_sign_in(app_db, monkeypatch):
    name = account()
    monkeypatch.setattr(domain, "N", 2 ** 5)
    assert sign_in(app_db, name, GOOD)[1].status == 200
    c = store.connect()
    stored = store.row(c, "SELECT password_hash FROM users WHERE username=?", (name,))["password_hash"]
    c.close()
    assert stored.startswith("scrypt$32$8$1$") and domain.verify(GOOD, stored)


def test_a_disabled_account_cannot_sign_in_and_loses_its_session(app_db):
    name = account()
    client, r = sign_in(app_db, name, GOOD)
    assert r.status == 200
    c = store.connect()
    c.execute("UPDATE users SET status='disabled' WHERE username=?", (name,))
    c.commit()
    c.close()
    assert client.get("/api/student/home").status == 401
    assert sign_in(app_db, name, GOOD)[1].status == 401


def test_prod_signs_in_with_a_password_and_has_no_demo_login(app_db, monkeypatch):
    name = account("admin")
    monkeypatch.setattr(config, "MODE", "prod")
    assert app_db.client().post("/api/auth/demo", {"role": "admin"}).status == 404
    client, r = sign_in(app_db, name, GOOD)
    assert r.status == 200 and client.get("/api/bootstrap").json["app"]["mode"] == "prod"
