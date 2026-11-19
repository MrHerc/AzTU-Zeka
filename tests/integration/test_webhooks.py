"""Signed webhooks (tasks/todo.md, Task 37): a delivery is signed with the webhook's secret, a failure is tried again
after a growing wait and gives up after MAX_ATTEMPTS, every try is in the delivery log; grade publishing and the
attendance scan emit their events."""
import hashlib
import hmac
import json
import threading
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
    assert len(made["secret"]) == 64 and "secret" not in json.dumps(admin.get("/api/integration/webhooks").json)


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
