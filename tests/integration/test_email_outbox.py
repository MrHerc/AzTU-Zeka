"""E-mail through the outbox (tasks/todo.md, Task 36, slice 2), against a fake SMTP server in this process: a relay that
is down delays a message and never loses it (tried again after a growing wait); a relay that accepts and never answers
fails the attempt within the timeout and the other jobs go on; a kind the person turned off is not e-mailed; every
message is in the recipient's language; a killed web worker still comes back within 2 seconds."""
import email
import email.policy
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from zeka.core import clock, jobs, mail
from zeka.core.i18n import T3
from zeka.legacy import periodic, store  # noqa: F401  registers the jobs
from zeka.modules.comms import service as comms

ROOT = Path(__file__).resolve().parents[2]


class FakeSMTP:
    """A minimal SMTP server: ``ok`` answers and keeps each message; ``hang`` accepts and never says a word."""

    def __init__(self, mode="ok"):
        self.mode, self.messages, self.conns = mode, [], []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self.done = False
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while not self.done:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.conns.append(conn)
            if self.mode == "ok":
                threading.Thread(target=self._talk, args=(conn,), daemon=True).start()

    def _talk(self, conn):
        f = conn.makefile("rb")
        say = lambda s: conn.sendall(s.encode() + b"\r\n")      # noqa: E731
        say("220 fake ESMTP")
        rcpt = []
        try:
            while True:
                line = f.readline().decode("utf-8", "replace").strip()
                if not line:
                    return
                verb = line.split(" ", 1)[0].upper()
                if verb in ("EHLO", "HELO"):
                    say("250-fake")
                    say("250 8BITMIME")
                elif verb == "MAIL":
                    rcpt = []
                    say("250 ok")
                elif verb == "RCPT":
                    if "unknown" in line:
                        say("550 no such user")
                    else:
                        rcpt.append(line)
                        say("250 ok")
                elif verb == "DATA":
                    say("354 go on")
                    data = b""
                    while not data.endswith(b"\r\n.\r\n"):
                        data += f.readline()
                    self.messages.append(email.message_from_bytes(data[:-5], policy=email.policy.default))
                    say("250 queued")
                elif verb == "QUIT":
                    say("221 bye")
                    return
                else:
                    say("250 ok")
        except OSError:
            return
        finally:
            conn.close()

    def close(self):
        self.done = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)          # wakes the accept() and really closes the port
        except OSError:
            pass
        self.sock.close()
        for c in self.conns:
            c.close()


@pytest.fixture
def relay(monkeypatch):
    servers = []

    def start(mode="ok"):
        s = FakeSMTP(mode)
        servers.append(s)
        monkeypatch.setenv("ZEKA_SMTP_HOST", "127.0.0.1")
        monkeypatch.setenv("ZEKA_SMTP_PORT", str(s.port))
        monkeypatch.setenv("ZEKA_SMTP_TLS", "none")
        monkeypatch.setenv("ZEKA_SMTP_FROM", "zeka@aztu.test")
        return s
    yield start
    for s in servers:
        s.close()


def db():
    return store.connect()


def person(n, address, lang):
    """The n-th active synthetic student, with this address and language and no e-mail choices yet."""
    c = db()
    try:
        u = store.rows(c, "SELECT * FROM users WHERE role='student' AND status='active' AND username LIKE 's0%' ORDER BY id")[n]
        prefs = json.loads(u["prefs"] or "{}")
        prefs["lang"] = lang
        prefs.pop("email", None)
        c.execute("UPDATE users SET email=?, prefs=? WHERE id=?", (address, json.dumps(prefs), u["id"]))
        c.execute("DELETE FROM outbox")
        c.commit()
        return u["id"]
    finally:
        c.close()


def notify(uid, kind, title, body=""):
    c = db()
    try:
        store.notify(c, uid, kind, title, body, "/student/requests")
        c.commit()
    finally:
        c.close()


def outbox():
    c = db()
    try:
        return store.rows(c, "SELECT * FROM outbox ORDER BY id")
    finally:
        c.close()


def send(now=None):
    c = db()
    try:
        return comms.send_due(c, now)
    finally:
        c.close()


def text_of(m):
    return m.get_body(("plain",)).get_content()


def test_every_message_is_in_the_recipients_language(app_db, relay):
    server = relay()
    ru = person(0, "s001@aztu.test", "ru")
    en = person(1, "s002@aztu.test", "en")
    notify(ru, "request", T3("Arayışınız hazırdır"))
    notify(en, "message", T3("Dekanlıqdan yeni mesaj"))
    assert [r["lang"] for r in outbox()] == ["ru", "en"]
    assert send().startswith("sent 2")
    got = {m["To"]: m for m in server.messages}
    assert str(got["s001@aztu.test"]["Subject"]) == "Ваша справка готова" and got["s001@aztu.test"]["Content-Language"] == "ru"
    assert "Ваша справка готова" in text_of(got["s001@aztu.test"]) and "/#/student/requests" in text_of(got["s001@aztu.test"])
    assert str(got["s002@aztu.test"]["Subject"]) == "New message from the dean's office"
    assert {r["status"] for r in outbox()} == {"sent"}


def test_a_kind_turned_off_is_not_emailed(app_db, relay):
    relay()
    c = db()
    try:
        uid = store.row(c, "SELECT id FROM users WHERE username='aysel'")["id"]
        c.execute("UPDATE users SET email='aysel@aztu.test', prefs=json_remove(prefs, '$.email') WHERE id=?", (uid,))
        c.execute("DELETE FROM outbox")
        c.commit()
    finally:
        c.close()
    student = app_db.client("student")
    shown = {k["kind"]: k["email"] for k in student.get("/api/me/notifications").json["kinds"]}
    assert shown["request"] is True and shown["news"] is False            # the flooding kinds start off
    assert student.put("/api/me/notifications", {"email": {"request": False}}).status == 200
    assert student.put("/api/me/notifications", {"email": {"nonsense": True}}).status == 400
    notify(uid, "request", T3("Arayışınız hazırdır"))
    notify(uid, "news", "Xəbər")
    notify(uid, "message", T3("Dekanlıqdan yeni mesaj"))
    assert [r["kind"] for r in outbox()] == ["message"]
    # turned off after it was queued: skipped at sending time, not sent
    assert student.put("/api/me/notifications", {"email": {"message": False}}).status == 200
    assert send().endswith("skipped 1") and outbox()[0]["status"] == "skipped"


def test_a_relay_that_is_down_delays_a_message_and_never_loses_it(app_db, relay, monkeypatch):
    server = relay()
    uid = person(2, "s003@aztu.test", "az")
    server.close()                                                       # the relay is down: connection refused
    notify(uid, "request", T3("Arayışınız hazırdır"))
    t0 = clock.now()
    assert "waiting 1" in send(t0)
    r = outbox()[0]
    assert r["status"] == "pending" and r["attempts"] == 1 and r["last_error"]
    assert datetime.fromisoformat(r["next_at"]) == t0.replace(microsecond=0) + timedelta(minutes=1)
    assert send(t0 + timedelta(seconds=30)) == "nothing due"
    assert "waiting 1" in send(t0 + timedelta(minutes=1, seconds=1))
    assert outbox()[0]["attempts"] == 2                                   # the next wait is longer: 2 minutes
    back = relay()                                                       # the relay is back
    assert send(t0 + timedelta(minutes=4)).startswith("sent 1")
    assert outbox()[0]["status"] == "sent" and [m["To"] for m in back.messages] == ["s003@aztu.test"]


def test_a_silent_relay_fails_within_the_timeout_and_the_other_jobs_go_on(app_db, relay, monkeypatch, tmp_path):
    assert mail.TIMEOUT == 15
    monkeypatch.setattr(mail, "TIMEOUT", 1)                               # the test does not wait 15 seconds
    relay("hang")
    uid = person(3, "s004@aztu.test", "az")
    for _ in range(3):
        notify(uid, "request", T3("Arayışınız hazırdır"))
    src, path = db(), tmp_path / "jobs.db"
    copy = sqlite3.connect(path)
    src.backup(copy)
    src.close()
    copy.row_factory = sqlite3.Row
    try:
        started = time.monotonic()
        done = jobs.run_due(copy, "test", clock.now() + timedelta(days=30), names=["outbox.send", "retention.purge"])
        assert time.monotonic() - started < 5
        assert done == [("outbox.send", "ok"), ("retention.purge", "ok")]
        detail = copy.execute("SELECT detail FROM job_runs WHERE name='outbox.send' ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert detail.startswith("sent 0, waiting 3")
        assert [r[0] for r in copy.execute("SELECT attempts FROM outbox ORDER BY id")] == [1, 0, 0]   # one attempt, not three
    finally:
        copy.close()


def test_a_refused_recipient_fails_for_good_and_the_rest_are_sent(app_db, relay):
    server = relay()
    bad = person(4, "unknown@aztu.test", "az")
    good = person(5, "s006@aztu.test", "az")
    notify(bad, "request", T3("Arayışınız hazırdır"))
    notify(good, "request", T3("Arayışınız hazırdır"))
    assert send().startswith("sent 1, waiting 0, failed 1")
    assert [r["status"] for r in outbox()] == ["failed", "sent"] and [m["To"] for m in server.messages] == ["s006@aztu.test"]


def test_a_password_never_goes_in_clear_to_another_machine(monkeypatch):
    monkeypatch.setenv("ZEKA_SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("ZEKA_SMTP_TLS", "none")
    with pytest.raises(mail.MailConfigError):
        mail.settings()
    monkeypatch.setenv("ZEKA_SMTP_TLS", "starttls")
    assert mail.settings()["port"] == 587
    monkeypatch.delenv("ZEKA_SMTP_HOST")
    assert mail.settings() is None


@pytest.mark.slow
@pytest.mark.skipif(not hasattr(os, "fork"), reason="--workers needs fork")
def test_a_killed_web_worker_comes_back_within_two_seconds_while_the_relay_hangs(tmp_path):
    silent = FakeSMTP("hang")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "ZEKA_DATA": str(tmp_path), "PYTHONIOENCODING": "utf-8", "ZEKA_SMTP_HOST": "127.0.0.1",
           "ZEKA_SMTP_PORT": str(silent.port), "ZEKA_SMTP_TLS": "none", "ZEKA_JOBS_DELAY": "0"}
    for k in ("ZEKA_MODE", "ZEKA_TX_GUARD"):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, str(ROOT / "backend" / "run.py"), "--port", str(port), "--workers", "2"],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def worker():
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            c.request("GET", "/healthz")
            return json.loads(c.getresponse().read())["worker"]
        finally:
            c.close()
    try:
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                first = worker()
                break
            except OSError:
                time.sleep(0.2)
        c = sqlite3.connect(tmp_path / "campus.db")
        c.execute("INSERT INTO outbox(address,kind,template,params,next_at,created_at) VALUES('x@aztu.test','request','notification',"
                  "?, '2000-01-01T00:00:00+00:00', 'x')", (json.dumps({"title": "t"}),))
        c.commit()
        c.close()
        time.sleep(1.5)                                                   # the job runner is now stuck on the silent relay
        os.kill(first, signal.SIGKILL)
        killed = time.monotonic()
        while time.monotonic() - killed < 2:
            try:
                if worker() != first:
                    break
            except OSError:
                pass
            time.sleep(0.02)
        else:
            raise AssertionError("no worker answered within 2 seconds of the kill")
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.communicate(timeout=60)
        silent.close()
