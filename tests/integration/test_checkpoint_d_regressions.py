"""Checkpoint D: the regression tests the review report still owed ("Fixed without a dedicated regression test" in
docs/review/checkpoint-d-2026-11-19.md), by finding id. Each fails on the code before the fixes (823bc4d) unless its
docstring says otherwise. The exam helpers and the ``world`` fixture come from test_checkpoint_d.py."""
import email
import email.policy
import json
import os
import smtplib
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

from tests.integration import test_checkpoint_d
from tests.integration.test_checkpoint_d import new_exam, one, run, sit
from zeka.core import clock, mail
from zeka.legacy import periodic, store
from zeka.modules.comms import service as comms
from zeka.modules.exam import repo as exam_repo
from zeka.modules.journal import repo as journal_repo
from zeka.modules.journal import service as journal

ROOT = Path(__file__).resolve().parents[2]
world = test_checkpoint_d.world                     # a fixture: the exam course, its questions and three students


def db():
    return store.connect()


def released(app_db, world, name):
    eid = new_exam(world)
    sit(app_db, eid, name)
    t = world["teacher"]
    assert t.post(f"/api/exams/{eid}/close").status == 200 and t.post(f"/api/exams/{eid}/release").status == 200
    return eid


# ---------------------------------------------------------------- A. statements (CR-10, AR-5)
def test_cr10_two_concurrent_statement_closes_give_one_200_and_one_409(app_db, world, monkeypatch):
    eid = released(app_db, world, "cd.a")
    meet, calls, real = threading.Barrier(2, timeout=1), [], exam_repo.statements

    def statements(c, exam_id):
        calls.append(exam_id)
        if len(calls) <= 2:                  # the two closes' "already closed?" checks meet here, later reads pass
            try:
                meet.wait()
            except threading.BrokenBarrierError:
                pass                         # the other close never got here: it waits for the write lock (the fix)
        return real(c, exam_id)
    monkeypatch.setattr(exam_repo, "statements", statements)
    clients = [app_db.client("office"), app_db.client("admin")]
    codes: list = [None, None]

    def close(i):
        codes[i] = clients[i].post(f"/api/exams/{eid}/statements/{world['group']}/close").status
    threads = [threading.Thread(target=close, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert sorted(codes) == [200, 409]
    assert one("SELECT COUNT(*) AS n FROM exam_statements WHERE exam_id=?", (eid,))["n"] == 1


def test_ar5_the_office_lists_its_own_released_exam_behind_200_others(app_db, world):
    eid = released(app_db, world, "cd.b")
    later = "2999-01-01T00:00:00+00:00"                # newer than the office's exam: first in "newest first"
    c = db()
    try:
        c.executemany("INSERT INTO exams(course_id,title,opens_at,closes_at,duration_min,plan,status,secret,created_at) "
                      "VALUES(?,'AR-5 başqa',?,?,60,'[]','released','x',?)", [(world["course"], later, later, later)] * 201)
        c.commit()
        assert eid in [e["id"] for e in app_db.client("office").get("/api/exam-statements").json]
    finally:
        c.execute("DELETE FROM exams WHERE title='AR-5 başqa'")
        c.commit()
        c.close()


# ---------------------------------------------------------------- G. the page's own submit (NEW-G1)
def attempt_status(eid, sid):
    return one("SELECT status FROM exam_attempts WHERE exam_id=? AND student_id=?", (eid, sid))["status"]


def test_new_g1_the_page_s_auto_submit_waits_for_the_server_s_deadline_and_a_pause(app_db, world):
    eid, sid, t = new_exam(world), world["ids"]["cd.c"], world["teacher"]
    s = sit(app_db, eid, "cd.c", submit=False)
    assert s.post(f"/api/exams/{eid}/submit", {"auto": True}).status == 409 and attempt_status(eid, sid) == "in_progress"
    assert t.post(f"/api/exams/{eid}/students/{sid}/pause", {"reason": "otaqda səs-küy"}).status == 200
    assert s.post(f"/api/exams/{eid}/submit", {"auto": True}).status == 409 and attempt_status(eid, sid) == "paused"
    assert t.post(f"/api/exams/{eid}/students/{sid}/resume", {"reason": "səs-küy kəsildi"}).status == 200
    run("UPDATE exam_attempts SET deadline_at=? WHERE exam_id=? AND student_id=?",
        ((clock.now() - timedelta(seconds=1)).isoformat(timespec="seconds"), eid, sid))
    assert s.post(f"/api/exams/{eid}/submit", {"auto": True}).status == 200 and attempt_status(eid, sid) == "submitted"


def test_new_g1_a_manual_submit_before_the_deadline_still_works(app_db, world):
    """The counterpart of the rule above: passes on the old code too."""
    eid = new_exam(world)
    s = sit(app_db, eid, "cd.a", submit=False)
    assert s.post(f"/api/exams/{eid}/submit").status == 200 and attempt_status(eid, world["ids"]["cd.a"]) == "submitted"


# ---------------------------------------------------------------- F. the e-mail outbox (SEC-2, SF-6, PY-3, CR-6, AR-6, PY-6)
class Relay:
    """A scripted SMTP relay on 127.0.0.1. ``replies`` answers a verb its own way ("HELLO" is the greeting), ``ext`` adds
    EHLO extensions, ``slow`` seconds pass before each message is accepted; ``eof`` is set when a client hangs up."""

    def __init__(self, replies=None, ext=(), slow=0.0):
        self.replies, self.ext, self.slow = replies or {}, ext, slow
        self.messages, self.conns, self.eof = [], [], threading.Event()
        self.sock = socket.create_server(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.conns.append(conn)
            threading.Thread(target=self._talk, args=(conn,), daemon=True).start()

    def _talk(self, conn):
        f = conn.makefile("rb")
        say = lambda s: conn.sendall(s.encode() + b"\r\n")      # noqa: E731
        try:
            say(self.replies.get("HELLO", "220 relay ESMTP"))
            while line := f.readline():
                verb = line.split(b" ", 1)[0].strip().upper().decode()
                if verb in self.replies:
                    say(self.replies[verb])
                elif verb == "EHLO":
                    for x in ("relay", *self.ext):
                        say("250-" + x)
                    say("250 8BITMIME")
                elif verb == "AUTH":
                    say("235 ok")
                elif verb == "DATA":
                    say("354 go on")
                    data = b""
                    while not data.endswith(b"\r\n.\r\n"):
                        chunk = f.readline()
                        if not chunk:
                            return
                        data += chunk
                    time.sleep(self.slow)
                    self.messages.append(email.message_from_bytes(data[:-5], policy=email.policy.default))
                    say("250 queued")
                elif verb == "QUIT":
                    say("221 bye")
                    return
                else:
                    say("250 ok")
            self.eof.set()
        except OSError:
            pass
        finally:
            f.close()
            conn.close()

    def close(self):
        for s in (self.sock, *self.conns):
            try:
                s.shutdown(socket.SHUT_RDWR)              # wakes a blocked accept() or readline()
            except OSError:
                pass
            s.close()


@pytest.fixture
def relay(monkeypatch):
    made = []

    def start(user="", password="", **kw):
        r = Relay(**kw)
        made.append(r)
        for k, v in {"HOST": "127.0.0.1", "PORT": str(r.port), "TLS": "none", "FROM": "zeka@aztu.test", "USER": user, "PASSWORD": password}.items():
            monkeypatch.setenv(f"ZEKA_SMTP_{k}", v)
        run("DELETE FROM outbox")
        return r
    yield start
    for r in made:
        r.close()


def queue(*addresses):
    c = db()
    try:
        at = clock.now().isoformat(timespec="seconds")
        for a in addresses:
            c.execute("INSERT INTO outbox(address,kind,template,params,next_at,created_at) VALUES(?,'request','notification',?,?,?)",
                      (a, json.dumps({"title": "Arayışınız hazırdır"}), at, at))
        c.commit()
    finally:
        c.close()


def outbox():
    c = db()
    try:
        return store.rows(c, "SELECT * FROM outbox ORDER BY id")
    finally:
        c.close()


def send():
    c = db()
    try:
        return comms.send_due(c)
    finally:
        c.close()


def test_sec2_a_line_break_in_a_ticket_subject_is_no_header_and_the_next_message_goes(app_db, relay):
    server = relay()
    desk = app_db.client("admin").user["id"]
    run("UPDATE users SET email='desk@aztu.test', prefs=json_remove(prefs, '$.email') WHERE id=?", (desk,))
    r = app_db.client("student").post("/api/support/tickets", {"subject": "Printer işləmir\nBcc: x@aztu.test",
                                                               "body": "Kitabxanadakı printer çap etmir."})
    assert r.status == 200, r.text
    run("UPDATE support_tickets SET assignee_id=?, created_at=? WHERE id=?", (desk, store.iso(store.now() - timedelta(days=3)), r.json["id"]))
    run("DELETE FROM outbox")
    c = db()
    try:
        periodic.reminders_sla(c)                     # the ticket's subject goes into the title, the title is the e-mail's subject
        c.commit()
    finally:
        c.close()
    queue("next@aztu.test")
    assert "failed 0" in send()
    reminder = next(m for m in server.messages if "Printer" in str(m["Subject"]))
    assert str(reminder["Subject"]).endswith("Printer işləmir Bcc: x@aztu.test") and reminder["Bcc"] is None
    assert "next@aztu.test" in [m["To"] for m in server.messages]


def test_sf6_a_message_that_cannot_be_written_fails_alone_and_the_next_is_sent(app_db, relay):
    server = relay()
    queue("bad@aztu.test\nBcc: x@aztu.test", "next@aztu.test")         # a header with a line break raises ValueError
    assert send().startswith("sent 1, waiting 0, failed 1")
    assert [r["status"] for r in outbox()] == ["failed", "sent"] and [m["To"] for m in server.messages] == ["next@aztu.test"]


def test_py3_a_non_ascii_smtp_password_does_not_crash_the_run(app_db, relay):
    relay(ext=("AUTH PLAIN",), user="zeka", password="şifrə-test")
    queue("a@aztu.test", "b@aztu.test")
    assert send().startswith("sent 0")                                  # the old code raised UnicodeEncodeError here


def test_py3_a_non_ascii_smtp_password_leaves_every_message_waiting(app_db, relay):
    relay(ext=("AUTH PLAIN",), user="zeka", password="şifrə-test")
    queue("a@aztu.test", "b@aztu.test")
    send()
    assert {r["status"] for r in outbox()} == {"pending"}


def test_py3_a_non_ascii_recipient_address_does_not_hold_back_the_next_message(app_db, relay):
    server = relay()
    queue("şəhla@aztu.test", "next@aztu.test")
    send()
    assert [m["To"] for m in server.messages] == ["next@aztu.test"]


@pytest.mark.parametrize("setup", [
    {"replies": {"MAIL": "550 5.7.1 sender not allowed"}},
    {"replies": {"HELLO": "554 5.3.2 no service here"}},
    {"replies": {"AUTH": "535 5.7.8 bad credentials"}, "ext": ("AUTH PLAIN",), "user": "zeka", "password": "test-only"},
], ids=["mail-from", "greeting", "login"])
def test_cr6_a_5xx_about_the_relay_s_settings_leaves_every_message_pending(app_db, relay, setup):
    """The login case passes on the old code too: it already left an authentication error waiting."""
    relay(**setup)
    queue("a@aztu.test", "b@aztu.test")
    assert "failed 0" in send()
    assert [(r["status"], r["attempts"]) for r in outbox()] == [("pending", 1), ("pending", 0)]


def test_ar6_one_run_stops_at_its_time_budget_and_the_rest_wait_for_the_next(app_db, relay, monkeypatch):
    server = relay(slow=0.3)                                             # each message takes longer than the budget
    monkeypatch.setattr(comms, "BUDGET_S", 0.1, raising=False)
    queue("a@aztu.test", "b@aztu.test", "c@aztu.test")
    assert send().startswith("sent 1, waiting 2")
    assert [(r["status"], r["attempts"]) for r in outbox()] == [("sent", 1), ("pending", 0), ("pending", 0)]
    server.slow = 0
    assert send().startswith("sent 2") and len(server.messages) == 3


@pytest.mark.parametrize("setup, cfg", [
    ({"ext": ("STARTTLS",), "replies": {"STARTTLS": "454 4.7.0 TLS not available"}}, {"tls": "starttls"}),
    ({"ext": ("AUTH PLAIN",), "replies": {"AUTH": "535 5.7.8 bad credentials"}}, {"user": "zeka", "password": "test-only"}),
], ids=["starttls", "login"])
def test_py6_a_refused_starttls_or_login_closes_the_connection(setup, cfg):
    r = Relay(**setup)
    try:
        with pytest.raises(smtplib.SMTPResponseException) as refused:     # held: the old code's socket stays referenced
            mail.connect({"host": "127.0.0.1", "port": r.port, "tls": "none", "user": "", "password": "", "sender": "zeka@aztu.test", **cfg})
        assert refused.value.smtp_code in (454, 535)
        assert r.eof.wait(2), "the client left the refused connection open"
    finally:
        r.close()


# ---------------------------------------------------------------- F. start-up checks (SF-5, PY-14)
def start(tmp_path, **env) -> tuple[int, str]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    base = {k: v for k, v in os.environ.items() if not k.startswith(("ZEKA_", "AZTU_LLM_")) and k not in ("PORT", "HOST", "PUBLIC_URL")}
    p = subprocess.run([sys.executable, str(ROOT / "backend" / "run.py"), "--port", str(port)], capture_output=True, timeout=20, cwd=tmp_path,
                       env={**base, "ZEKA_DATA": str(tmp_path / "data"), "ZEKA_JOBS": "0", "PYTHONIOENCODING": "utf-8", **env})
    return p.returncode, p.stderr.decode("utf-8", "replace")


@pytest.mark.slow
@pytest.mark.parametrize("env, name", [
    ({"ZEKA_SMTP_HOST": "127.0.0.1", "ZEKA_SMTP_PORT": "abc"}, "ZEKA_SMTP_PORT"),
    ({"ZEKA_SMTP_HOST": "127.0.0.1", "ZEKA_SMTP_TLS": "bogus"}, "ZEKA_SMTP_TLS"),
], ids=["port", "tls"])
def test_sf5_a_bad_smtp_setting_stops_the_start_with_its_name(tmp_path, env, name):
    code, err = start(tmp_path, **env)                                   # the old code started and served (timeout here)
    assert code != 0 and name in err and "Traceback" not in err, err[-500:]


@pytest.mark.slow
def test_py14_a_bad_jobs_delay_is_a_clear_message_not_a_traceback(tmp_path):
    code, err = start(tmp_path, ZEKA_JOBS_DELAY="abc")
    assert code != 0 and "ZEKA_JOBS_DELAY" in err and "Traceback" not in err, err[-500:]


# ---------------------------------------------------------------- F. periodic jobs (SF-8, AR-13), on a copy of the database
@pytest.fixture
def copy(app_db, tmp_path):
    src, dst = db(), sqlite3.connect(tmp_path / "copy.db")
    src.backup(dst)
    src.close()
    dst.close()
    c = sqlite3.connect(tmp_path / "copy.db", timeout=15)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_sf8_a_request_with_no_office_to_tell_is_reminded_once_there_is_one(copy):
    r = copy.execute("SELECT id, student_id FROM requests WHERE status IN ('submitted','in_progress') ORDER BY id LIMIT 1").fetchone()
    gid = copy.execute("SELECT group_id FROM users WHERE id=?", (r["student_id"],)).fetchone()[0]
    assert gid is not None
    copy.execute("UPDATE requests SET due_at=? WHERE id=?", (store.iso(store.now() - timedelta(hours=1)), r["id"]))
    copy.execute("UPDATE users SET group_id=NULL WHERE id=?", (r["student_id"],))        # no dean's office covers the student
    marked = lambda: copy.execute("SELECT COUNT(*) FROM reminders_sent WHERE kind='request' AND obj_id=?", (r["id"],)).fetchone()[0]  # noqa: E731
    told = lambda: copy.execute("SELECT COUNT(*) FROM notifications WHERE link=?", (f"/office/requests/{r['id']}",)).fetchone()[0]  # noqa: E731
    before = told()
    periodic.reminders_sla(copy)
    assert marked() == 0
    copy.execute("UPDATE users SET group_id=? WHERE id=?", (gid, r["student_id"]))
    periodic.reminders_sla(copy)
    assert marked() == 1 and told() > before


def test_ar13_retention_purge_drops_finished_runs_and_mail_older_than_90_days(copy):
    old, recent = [(clock.now() - timedelta(days=d)).isoformat(timespec="seconds") for d in (91, 89)]
    copy.executemany("INSERT INTO job_runs(name,started_at,status) VALUES('t.ar13',?,?)",
                     [(old, "ok"), (old, "error"), (old, "running"), (recent, "ok")])
    copy.executemany("INSERT INTO outbox(address,kind,template,params,status,next_at,created_at) VALUES(?,'request','notification','{}',?,?,?)",
                     [(f"{s}.{age}@ar13.test", s, t, t) for age, t in (("old", old), ("new", recent)) for s in ("sent", "failed", "skipped", "pending")])
    periodic.retention_purge(copy)
    runs = sorted((r["started_at"] == old, r["status"]) for r in copy.execute("SELECT * FROM job_runs WHERE name='t.ar13'"))
    assert runs == [(False, "ok"), (True, "running")]
    mails = sorted(r[0] for r in copy.execute("SELECT address FROM outbox WHERE address LIKE '%@ar13.test'"))
    assert mails == ["failed.new@ar13.test", "pending.new@ar13.test", "pending.old@ar13.test", "sent.new@ar13.test", "skipped.new@ar13.test"]


# ---------------------------------------------------------------- AR-4: results in a fixed number of queries
def test_ar4_published_results_match_student_grades_for_every_student(app_db, world):
    """New code (``published_results``): it does not exist before the fix, so this cannot fail on the old code for the
    right reason. The results endpoint part passes on the old code, which called ``student_grades`` per student."""
    c = db()
    try:
        cid = c.execute("SELECT course_id FROM grades WHERE status='published' GROUP BY course_id ORDER BY COUNT(*) DESC LIMIT 1").fetchone()[0]
        co = journal_repo.course(c, cid)
        uids = [r[0] for r in c.execute("SELECT user_id FROM enrollments WHERE course_id=? ORDER BY user_id", (cid,))]
        cols = journal.columns(c, co)
        exam, comp = (next(x for x in cols if x["kind"] == k) for k in ("exam", "component"))
        at = store.iso(store.now())
        for uid, score in zip(uids[:4], (45, 10, 30, 0), strict=True):                 # exam scores: totals, letters, a fail
            journal_repo.put_grade(c, uid, cid, exam["key"], score, exam["max"], "published", 1, at)
        journal_repo.put_grade(c, uids[4], cid, comp["key"], 7, comp["max"], "draft", 1, at)   # a draft is not counted
        c.execute("DELETE FROM grades WHERE course_id=? AND user_id=?", (cid, uids[5]))        # nothing at all
        got = journal.published_results(c, co, uids)
        want = {uid: journal.student_grades(c, uid, co)["result"] for uid in uids}
        assert {uid: res for uid, (_, res) in got.items()} == want
        assert {r["total"] is None for r in want.values()} == {True, False} and any(att is not None for att, _ in got.values())
    finally:
        c.rollback()
        c.close()
    eid = released(app_db, world, "cd.c")
    shown = world["teacher"].get(f"/api/exams/{eid}/results").json["rows"]
    c = db()
    try:
        co = journal_repo.course(c, world["course"])
        for r in (x for x in shown if x["raw"] is not None):
            res = journal.student_grades(c, r["student_id"], co)["result"]
            assert (r["semester"], r["total"], r["letter"]) == (res["semester"], res["total"], res["letter"])
    finally:
        c.close()
