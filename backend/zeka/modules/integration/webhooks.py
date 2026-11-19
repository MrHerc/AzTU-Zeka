"""Signed webhooks (tasks/todo.md, Task 37): grade.published, attendance.barred, exam.released.

``emit`` queues one delivery per subscribed webhook in the caller's transaction; the job ``webhooks.send`` (every
minute) POSTs each due delivery outside any write transaction, ``urlopen(timeout=10)``, with
``X-Zeka-Signature: t=<unix time>,v1=<hex HMAC-SHA256(secret, "<t>.<body>")>``; a failure waits 1, 2, 4 … minutes
(at most 6 h) and is tried again up to MAX_ATTEMPTS times; every try is written to the delivery row. The job
``attendance.barred`` finds students the attendance limit newly bars (courses with marks since its last run) and emits
the event once per student and course.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from ...core import clock, jobs
from ...core.i18n import E
from ...legacy.store import audit, iso, now, row, rows
from ..comms.domain import backoff

EVENTS = ("grade.published", "attendance.barred", "exam.released")
MAX_ATTEMPTS = 12
BATCH = 50
BUDGET_S = 20
LOOPBACK = ("127.0.0.1", "localhost", "::1")


def hook_input(body) -> tuple[dict, dict | None]:
    v = {"url": body.text("url", 600), "events": body.array("events")}
    u = urlsplit(v["url"])
    if not (u.scheme == "https" or (u.scheme == "http" and u.hostname in LOOPBACK)) or not u.hostname or len(v["url"]) > 500:
        return v, E("Ünvan https:// ilə başlamalıdır")
    if not v["events"] or not all(isinstance(e, str) and e in EVENTS for e in v["events"]):
        return v, E("Hadisələr: {events}", events=", ".join(EVENTS))
    v["events"] = sorted(set(v["events"]))
    return v, None


def create(c, user, body) -> tuple[str, object]:
    v, problem = hook_input(body)
    if problem:
        return "invalid", problem
    secret = secrets.token_hex(32)
    hid = c.execute("INSERT INTO webhooks(url,secret,events,created_by,created_at) VALUES(?,?,?,?,?)",
                    (v["url"], secret, json.dumps(v["events"]), user["id"], iso(now()))).lastrowid
    audit(c, user["id"], "webhook_create", "webhook", f"#{hid} {v['url'][:120]} · {','.join(v['events'])}")
    return "ok", {**listed(c, hid), "secret": secret}           # shown once: the receiver checks signatures with it


def listed(c, hid: int | None = None):
    sql = ("SELECT w.id, w.url, w.events, w.active, w.created_at, (SELECT COUNT(*) FROM webhook_deliveries d WHERE d.webhook_id=w.id "
           "AND d.status='pending') AS pending, (SELECT COUNT(*) FROM webhook_deliveries d WHERE d.webhook_id=w.id AND d.status='failed') AS failed "
           "FROM webhooks w")
    out = [{**r, "events": json.loads(r["events"])} for r in (rows(c, sql + " WHERE w.id=?", (hid,)) if hid else rows(c, sql + " ORDER BY w.id DESC"))]
    return out[0] if hid else out


def deactivate(c, user, hid: int) -> tuple[str, object]:
    if not row(c, "SELECT 1 FROM webhooks WHERE id=? AND active=1", (hid,)):
        return "missing", None
    c.execute("UPDATE webhooks SET active=0 WHERE id=?", (hid,))
    audit(c, user["id"], "webhook_deactivate", "webhook", f"#{hid}")
    return "ok", listed(c, hid)


def deliveries(c, hid: int) -> list[dict]:
    return rows(c, "SELECT id, event, status, attempts, last_status, last_error, created_at, sent_at, next_at FROM webhook_deliveries "
                   "WHERE webhook_id=? ORDER BY id DESC LIMIT 100", (hid,))


def emit(c, event: str, payload: dict):
    """One delivery per active webhook that wants ``event``, in the caller's transaction (nothing is sent if it rolls back)."""
    at = iso(now())
    body = json.dumps({"event": event, "at": at, "data": payload}, ensure_ascii=False, sort_keys=True)
    for w in rows(c, "SELECT id, events FROM webhooks WHERE active=1"):
        if event in json.loads(w["events"]):
            c.execute("INSERT INTO webhook_deliveries(webhook_id,event,payload,next_at,created_at) VALUES(?,?,?,?,?)", (w["id"], event, body, at, at))


def signature(secret: str, stamp: int, body: bytes) -> str:
    return f"t={stamp},v1=" + hmac.new(secret.encode(), str(stamp).encode() + b"." + body, hashlib.sha256).hexdigest()


def _post(url: str, secret: str, event: str, delivery_id: int, body: bytes) -> int:
    stamp = int(time.time())
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json; charset=utf-8", "User-Agent": "Zeka-Webhooks/1", "X-Zeka-Event": event,
        "X-Zeka-Delivery": str(delivery_id), "X-Zeka-Signature": signature(secret, stamp, body)})
    with urllib.request.urlopen(req, timeout=10) as r:          # nosec B310: https, or http to this machine only (hook_input)
        return r.status


def send_due(c, t: datetime | None = None) -> str:
    """The job: due deliveries, oldest first; no write transaction is open while a request is in flight."""
    t = t or now()
    due = rows(c, "SELECT d.*, w.url, w.secret, w.active FROM webhook_deliveries d JOIN webhooks w ON w.id=d.webhook_id "
                  "WHERE d.status='pending' AND d.next_at<=? ORDER BY d.next_at, d.id LIMIT ?", (iso(t), BATCH))
    c.commit()
    sent = failed = waiting = 0
    started = time.monotonic()
    for d in due:
        if time.monotonic() - started > BUDGET_S:
            break
        if not d["active"]:
            c.execute("UPDATE webhook_deliveries SET status='failed', last_error='the webhook was deactivated' WHERE id=?", (d["id"],))
            c.commit()
            continue
        n = d["attempts"] + 1
        try:
            code = _post(d["url"], d["secret"], d["event"], d["id"], d["payload"].encode())
            err = None if 200 <= code < 300 else f"HTTP {code}"
        except urllib.error.HTTPError as ex:
            code, err = ex.code, f"HTTP {ex.code}"
        except (OSError, ValueError) as ex:                     # refused, timed out, bad TLS: try again later
            code, err = None, f"{type(ex).__name__}: {ex}"[:300]
        if err is None:
            c.execute("UPDATE webhook_deliveries SET status='sent', attempts=?, last_status=?, last_error=NULL, sent_at=? WHERE id=?",
                      (n, code, iso(now()), d["id"]))
            sent += 1
        elif n >= MAX_ATTEMPTS:
            c.execute("UPDATE webhook_deliveries SET status='failed', attempts=?, last_status=?, last_error=? WHERE id=?", (n, code, err, d["id"]))
            failed += 1
        else:
            c.execute("UPDATE webhook_deliveries SET attempts=?, last_status=?, last_error=?, next_at=? WHERE id=?",
                      (n, code, err, iso(t + backoff(n)), d["id"]))
            waiting += 1
        c.commit()
    return f"sent {sent} · waiting {waiting} · failed {failed}"


def barred_scan(c) -> str:
    """The job: students the attendance limit newly bars in courses with marks since the last run; once each."""
    from ..journal import service as journal                   # here: journal imports this module to emit
    last = row(c, "SELECT MAX(started_at) AS t FROM job_runs WHERE name='attendance.barred' AND status='ok'")["t"]
    # job times are aware UTC, attendance times the naive wall clock of ZEKA_TZ; five minutes of overlap miss nothing
    since = (datetime.fromisoformat(last).astimezone(clock.ZONE).replace(tzinfo=None) - timedelta(minutes=5)) if last else now() - timedelta(days=1)
    courses = rows(c, "SELECT DISTINCT l.course_id, co.code FROM attendance a JOIN lessons l ON l.id=a.lesson_id JOIN courses co ON co.id=l.course_id "
                      "WHERE a.marked_at>=?", (iso(since),))
    found = 0
    for co in courses:
        for s in journal.course_standing(c, co["course_id"]):
            if s["status"] == "not_admitted" and c.execute("INSERT OR IGNORE INTO reminders_sent(kind,obj_id,threshold,sent_at) VALUES(?,?,?,?)",
                                                           ("barred", s["student_id"], str(co["course_id"]), iso(now()))).rowcount:
                emit(c, "attendance.barred", {"course_id": co["course_id"], "course_code": co["code"], "student_id": s["student_id"],
                                              "student_no": s["student_no"]})
                found += 1
    return f"barred {found}"


jobs.periodic("webhooks.send", timedelta(minutes=1), send_due)
jobs.periodic("attendance.barred", timedelta(minutes=15), barred_scan)
