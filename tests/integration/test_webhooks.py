"""Signed webhooks (tasks/todo.md, Task 37): a delivery is signed with the webhook's secret, a failure is tried again
after a growing wait and gives up after MAX_ATTEMPTS, every try is in the delivery log; grade publishing and the
attendance scan emit their events."""
import hashlib
import hmac
import json
import threading
import time
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from zeka.legacy import store
from zeka.modules.integration import webhooks


class Receiver:
    """A local endpoint that records each POST and answers with the next scripted status (200 when none is left)."""

    def __init__(self):
        self.got, self.codes = [], []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                outer.got.append({"headers": dict(self.headers), "body": body})
                self.send_response(outer.codes.pop(0) if outer.codes else 200)
                self.end_headers()

            def log_message(self, *a):
                pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/hook"


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


@pytest.fixture(scope="module")
def recv():
    r = Receiver()
    yield r
    r.server.shutdown()
    r.server.server_close()


def send(t):
    c = store.connect()
    try:
        return webhooks.send_due(c, t)
    finally:
        c.close()


def test_only_the_administrator_adds_a_webhook_and_its_address_and_events_are_checked(app_db, recv):
    admin = app_db.client("admin")
    assert app_db.client("office").post("/api/integration/webhooks", {"url": recv.url, "events": ["grade.published"]}).status == 403
    for bad in ({"url": "ftp://x.az/h", "events": ["grade.published"]}, {"url": "http://example.org/h", "events": ["grade.published"]},
                {"url": recv.url, "events": ["grade.deleted"]}, {"url": recv.url, "events": []}):
        assert admin.post("/api/integration/webhooks", bad).status == 400, bad
    made = admin.post("/api/integration/webhooks", {"url": recv.url, "events": ["grade.published", "exam.released"]}).json
    assert len(made["secret"]) == 64 and made["secret"] not in json.dumps(admin.get("/api/integration/webhooks").json)   # T-E17: the value


def test_a_published_grade_is_delivered_signed_retried_after_a_failure_and_logged(app_db, recv):
    admin, teacher = app_db.client("admin"), app_db.client("teacher")
    hook = admin.post("/api/integration/webhooks", {"url": recv.url, "events": ["grade.published"]}).json
    cid = q("SELECT id FROM courses WHERE code='ELM-2105'")[0]["id"]
    table = teacher.get(f"/api/journal/courses/{cid}/grades").json
    col = next(x["key"] for x in table["columns"] if x["kind"] == "component")
    sid = table["students"][0]["id"]
    assert teacher.put(f"/api/journal/courses/{cid}/grades", {"cells": [{"student_id": sid, "component": col, "score": 3}],
                                                                  "reason": "Webhook sınağı"}).status == 200
    assert teacher.post(f"/api/journal/courses/{cid}/grades/publish").status == 200
    d = q("SELECT * FROM webhook_deliveries WHERE webhook_id=? AND event='grade.published'", (hook["id"],))
    assert len(d) == 1 and json.loads(d[0]["payload"])["data"]["course_id"] == cid
    t0 = store.now()
    recv.got.clear()
    recv.codes[:] = [500] * 10                                    # every other hook of this module fails first too
    send(t0)
    mine = [g for g in recv.got if g["headers"]["X-Zeka-Delivery"] == str(d[0]["id"])]
    assert len(mine) == 1
    sig = dict(p.split("=", 1) for p in mine[0]["headers"]["X-Zeka-Signature"].split(","))
    expected = hmac.new(hook["secret"].encode(), sig["t"].encode() + b"." + mine[0]["body"], hashlib.sha256).hexdigest()
    assert hmac.compare_digest(sig["v1"], expected) and mine[0]["headers"]["X-Zeka-Event"] == "grade.published"
    row = q("SELECT status, attempts, last_status, next_at FROM webhook_deliveries WHERE id=?", (d[0]["id"],))[0]
    assert (row["status"], row["attempts"], row["last_status"]) == ("pending", 1, 500)
    recv.codes.clear()
    recv.got.clear()
    send(t0 + timedelta(seconds=30))
    assert not [g for g in recv.got if g["headers"]["X-Zeka-Delivery"] == str(d[0]["id"])], "not before its wait"
    send(t0 + timedelta(minutes=2))
    row = q("SELECT status, attempts, last_status, sent_at FROM webhook_deliveries WHERE id=?", (d[0]["id"],))[0]
    assert (row["status"], row["attempts"], row["last_status"]) == ("sent", 2, 200) and row["sent_at"]
    log = admin.get(f"/api/integration/webhooks/{hook['id']}/deliveries").json
    assert log[0]["status"] == "sent" and log[0]["attempts"] == 2


def test_a_delivery_that_keeps_failing_gives_up_after_max_attempts(app_db, recv):
    admin = app_db.client("admin")
    hook = admin.post("/api/integration/webhooks", {"url": recv.url, "events": ["exam.released"]}).json
    c = store.connect()
    try:
        webhooks.emit(c, "exam.released", {"exam_id": 999})
        c.commit()
    finally:
        c.close()
    did = q("SELECT id FROM webhook_deliveries WHERE webhook_id=?", (hook["id"],))[0]["id"]
    t = store.now()
    for _ in range(webhooks.MAX_ATTEMPTS):
        recv.codes[:] = [503] * 20
        send(t)
        t += timedelta(hours=7)                                     # past the longest wait
    row = q("SELECT status, attempts, last_status FROM webhook_deliveries WHERE id=?", (did,))[0]
    assert (row["status"], row["attempts"], row["last_status"]) == ("failed", webhooks.MAX_ATTEMPTS, 503)
    told = q("SELECT title FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 1", (app_db.client("admin").user["id"],))[0]["title"]
    assert "Webhook çatdırılmadı" in told, "the administrator hears when a delivery is given up (SF-E15)"


def test_the_attendance_scan_emits_barred_once_per_student_and_course(app_db, recv, monkeypatch):
    admin = app_db.client("admin")
    hook = admin.post("/api/integration/webhooks", {"url": recv.url, "events": ["attendance.barred"]}).json
    cid = q("SELECT id FROM courses WHERE code='ELM-2105'")[0]["id"]
    lid = q("SELECT id FROM lessons WHERE course_id=? AND status<>'cancelled' ORDER BY day LIMIT 1", (cid,))[0]["id"]
    sid = q("SELECT user_id FROM enrollments WHERE course_id=? LIMIT 1", (cid,))[0]["user_id"]
    c = store.connect()
    try:
        c.execute("UPDATE attendance SET marked_at=? WHERE lesson_id=?", (store.iso(store.now()), lid))
        c.commit()
        from zeka.modules.journal import service as journal
        monkeypatch.setattr(journal, "course_standing", lambda c, course_id, uid=None: [
            {"student_id": sid, "student_no": "S-1", "status": "not_admitted"}] if course_id == cid else [])
        assert webhooks.barred_scan(c) == "barred 1"
        assert webhooks.barred_scan(c) == "barred 0", "once"
        c.commit()
    finally:
        c.close()
    d = q("SELECT payload FROM webhook_deliveries WHERE webhook_id=? AND event='attendance.barred'", (hook["id"],))
    assert len(d) == 1 and json.loads(d[0]["payload"])["data"] == {"course_id": cid, "course_code": "ELM-2105", "student_id": sid, "student_no": "S-1"}


# ---------------------------------------------------------------- Checkpoint E (area C)
def raw_server(answer: bytes):
    """A local endpoint that answers every connection with ``answer`` as raw bytes (a bad status line, a redirect)."""
    import socket
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)

    def serve():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            with conn:
                conn.recv(65536)
                conn.sendall(answer)
                # close only after the client has: closing with its body unread resets the connection, and Windows then
                # drops the answer it had already received (ConnectionResetError instead of BadStatusLine)
                conn.shutdown(socket.SHUT_WR)
                conn.settimeout(5)
                try:
                    while conn.recv(65536):
                        pass
                except OSError:
                    pass
    threading.Thread(target=serve, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.getsockname()[1]}/hook"


def hook(app_db, url, events=("exam.released",)):
    r = app_db.client("admin").post("/api/integration/webhooks", {"url": url, "events": list(events)})
    assert r.status == 200, r.text
    return r.json


def emit_one(event="exam.released"):
    c = store.connect()
    try:
        webhooks.emit(c, event, {"exam_id": 1})
        c.commit()
    finally:
        c.close()


def delivery(hid):
    return q("SELECT * FROM webhook_deliveries WHERE webhook_id=? ORDER BY id DESC LIMIT 1", (hid,))[0]


def test_a_receiver_that_breaks_http_fails_its_own_delivery_and_the_others_still_go(app_db, recv):
    """SF-E1: an exception outside OSError (BadStatusLine) used to stop the run and starve every delivery behind it."""
    srv, url = raw_server(b"NOT HTTP AT ALL\r\n\r\n")
    try:
        bad, good = hook(app_db, url), hook(app_db, recv.url)
        emit_one()
        recv.codes.clear()
        send(store.now())
        b, g = delivery(bad["id"]), delivery(good["id"])
        assert b["status"] == "pending" and b["attempts"] == 1 and "BadStatusLine" in b["last_error"]
        assert g["status"] == "sent"
    finally:
        srv.close()
        for h in (bad, good):
            app_db.client("admin").post(f"/api/integration/webhooks/{h['id']}/deactivate")


def test_a_redirect_is_not_followed_and_the_delivery_waits(app_db):
    """SF-E2: a 302 used to be followed as a GET without the body and logged as sent."""
    srv, url = raw_server(b"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:9/internal\r\nContent-Length: 0\r\n\r\n")
    try:
        h = hook(app_db, url)
        emit_one()
        send(store.now())
        d = delivery(h["id"])
        assert (d["status"], d["last_status"]) == ("pending", 302)
    finally:
        srv.close()
        app_db.client("admin").post(f"/api/integration/webhooks/{h['id']}/deactivate")


def test_an_address_with_spaces_credentials_a_bad_port_or_loopback_in_prod_is_refused(app_db, monkeypatch):
    admin = app_db.client("admin")
    for url in ("http://127.0.0.1:9/my hook", "https://user:pw@hooks.example.org/h", "https://hooks.example.org:abc/h",
                "https://hooks.example.org:99999/h", "https://[abc/h"):
        assert admin.post("/api/integration/webhooks", {"url": url, "events": ["exam.released"]}).status == 400, url
    from zeka.core import config
    monkeypatch.setattr(config, "prod", lambda: True)
    assert admin.post("/api/integration/webhooks", {"url": "http://127.0.0.1:9/h", "events": ["exam.released"]}).status == 400


def test_in_prod_a_delivery_to_a_non_public_address_is_never_sent(app_db, recv, monkeypatch):
    """SEC-E6: the address is checked when the delivery goes, so a name that resolves inside the network is refused."""
    h = hook(app_db, recv.url.replace("http://127.0.0.1", "https://127.0.0.1"))
    emit_one()
    from zeka.core import config
    monkeypatch.setattr(config, "prod", lambda: True)
    send(store.now())
    assert "PermissionError" in delivery(h["id"])["last_error"]
    monkeypatch.undo()                                          # demo sign-in is off in prod mode
    app_db.client("admin").post(f"/api/integration/webhooks/{h['id']}/deactivate")


def test_a_slow_receiver_costs_one_try_per_run_and_does_not_hold_the_others(app_db, recv, monkeypatch):
    """AR-E3 / TM-E7: a delivery has an overall limit; the rest of that webhook's deliveries wait for the next run."""
    slow, good = hook(app_db, recv.url + "/slow"), hook(app_db, recv.url)
    emit_one()
    emit_one()
    real = webhooks._post

    def post(url, *a):
        if url.endswith("/slow"):
            time.sleep(1.5)
        return real(url, *a)
    monkeypatch.setattr(webhooks, "_post", post)
    monkeypatch.setattr(webhooks, "POST_LIMIT_S", 0.3)
    recv.codes.clear()
    t0 = time.monotonic()
    send(store.now())
    assert time.monotonic() - t0 < 1.5
    tried = q("SELECT attempts FROM webhook_deliveries WHERE webhook_id=? ORDER BY id", (slow["id"],))
    assert sorted(x["attempts"] for x in tried) == [0, 1], "one try, the other waits for the next run"
    assert [x["status"] for x in q("SELECT status FROM webhook_deliveries WHERE webhook_id=?", (good["id"],))] == ["sent", "sent"]
    for h in (slow, good):
        app_db.client("admin").post(f"/api/integration/webhooks/{h['id']}/deactivate")


def test_finished_deliveries_are_purged_after_ninety_days(app_db):
    from zeka.legacy import periodic
    old = (store.now() - timedelta(days=91)).isoformat(timespec="seconds")
    c = store.connect()
    try:
        ids = [c.execute("INSERT INTO webhook_deliveries(webhook_id,event,payload,status,next_at,created_at) VALUES(1,'exam.released','{}',?,?,?)",
                         (st, old, old)).lastrowid for st in ("sent", "failed", "pending")]
        c.commit()
        assert "webhook deliveries 2" in periodic.retention_purge(c)
        c.commit()
    finally:
        c.close()
    assert [r["id"] for r in q("SELECT id FROM webhook_deliveries WHERE id IN (?,?,?)", tuple(ids))] == [ids[2]], "pending stays"


def test_the_scan_writes_nothing_when_no_webhook_wants_barred(app_db, monkeypatch):
    """SF-E3: no marker is spent while nobody listens (a webhook added later hears about later barrings)."""
    for h in app_db.client("admin").get("/api/integration/webhooks").json:
        if "attendance.barred" in h["events"] and h["active"]:
            app_db.client("admin").post(f"/api/integration/webhooks/{h['id']}/deactivate")
    before = q("SELECT COUNT(*) AS n FROM reminders_sent WHERE kind='barred'")[0]["n"]
    c = store.connect()
    try:
        assert webhooks.barred_scan(c) == "no webhook wants attendance.barred"
    finally:
        c.close()
    assert q("SELECT COUNT(*) AS n FROM reminders_sent WHERE kind='barred'")[0]["n"] == before


def test_a_deactivated_webhook_gets_nothing_more(app_db, recv):
    """T-E8: its pending deliveries fail instead of going out, and a later event queues nothing for it."""
    admin = app_db.client("admin")
    hook = admin.post("/api/integration/webhooks", {"url": recv.url, "events": ["exam.released"]}).json
    c = store.connect()
    try:
        webhooks.emit(c, "exam.released", {"exam_id": 998})
        c.commit()
    finally:
        c.close()
    assert app_db.client("office").post(f"/api/integration/webhooks/{hook['id']}/deactivate").status == 403
    assert admin.post(f"/api/integration/webhooks/{hook['id']}/deactivate").json["active"] == 0
    assert admin.post(f"/api/integration/webhooks/{hook['id']}/deactivate").status == 404, "once"
    recv.got.clear()
    recv.codes.clear()
    send(store.now() + timedelta(days=1))
    did = q("SELECT id FROM webhook_deliveries WHERE webhook_id=?", (hook["id"],))[0]["id"]
    assert not [g for g in recv.got if g["headers"]["X-Zeka-Delivery"] == str(did)]
    d = q("SELECT status, last_error FROM webhook_deliveries WHERE id=?", (did,))[0]
    assert d["status"] == "failed" and d["last_error"]
    c = store.connect()
    try:
        webhooks.emit(c, "exam.released", {"exam_id": 997})
        c.commit()
    finally:
        c.close()
    assert len(q("SELECT 1 FROM webhook_deliveries WHERE webhook_id=?", (hook["id"],))) == 1
    assert q("SELECT 1 FROM audit WHERE action='webhook_deactivate' AND detail=?", (f"#{hook['id']}",))
