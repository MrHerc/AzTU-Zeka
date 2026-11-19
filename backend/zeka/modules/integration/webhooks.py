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
import ipaddress
import json
import secrets
import socket
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from ...core import clock, config, jobs
from ...core.i18n import E, T3
from ...legacy.store import audit, iso, notify, now, row, rows
from ..comms.domain import backoff

EVENTS = ("grade.published", "attendance.barred", "exam.released")
MAX_ATTEMPTS = 12
BATCH = 50
BUDGET_S = 20
TIMEOUT_S = 10                       # a socket read
POST_LIMIT_S = 15                    # a whole delivery, however slowly the receiver drips (Checkpoint E, TM-E7)
LOOPBACK = ("127.0.0.1", "localhost", "::1")
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="webhook")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A 3xx is the receiver's answer, not a new address to send to (Checkpoint E, SF-E2): it becomes an HTTPError."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _url_ok(url: str) -> bool:
    """https to a named host, or http to this machine outside prod; no spaces, credentials or bad port."""
    if len(url) > 500 or any(ch.isspace() or ord(ch) < 32 for ch in url):
        return False
    try:
        u = urlsplit(url)
        _ = u.port                                          # raises ValueError for a port that is not a number in range
    except ValueError:
        return False
    if not u.hostname or u.username or u.password:
        return False
    return u.scheme == "https" or (u.scheme == "http" and u.hostname in LOOPBACK and not config.prod())


def _address_ok(url: str) -> bool:
    """At send time: every address the host resolves to is public (loopback only outside prod), so a webhook cannot
    reach the metadata service or the internal network (Checkpoint E, SEC-E6)."""
    host = urlsplit(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return True                                         # the post itself fails and is retried with the reason
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not (ip.is_global or (ip.is_loopback and not config.prod())):
            return False
    return True


def hook_input(body) -> tuple[dict, dict | None]:
    v = {"url": body.text("url", 600), "events": body.array("events")}
    if not _url_ok(v["url"]):
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
    with _OPENER.open(req, timeout=TIMEOUT_S) as r:            # nosec B310: https, or http to this machine outside prod (_url_ok)
        return r.status


def send_due(c, t: datetime | None = None) -> str:
    """The job: due deliveries, oldest first; no write transaction is open while a request is in flight."""
    t = t or now()
    due = rows(c, "SELECT d.*, w.url, w.secret, w.active FROM webhook_deliveries d JOIN webhooks w ON w.id=d.webhook_id "
                  "WHERE d.status='pending' AND d.next_at<=? ORDER BY d.next_at, d.id LIMIT ?", (iso(t), BATCH))
    c.commit()
    sent = failed = waiting = 0
    started = time.monotonic()
    down: set[int] = set()                                     # webhooks that timed out in this run (AR-E3)
    for d in due:
        if time.monotonic() - started > BUDGET_S:
            break
        if not d["active"] or not _url_ok(d["url"]):
            c.execute("UPDATE webhook_deliveries SET status='failed', last_error='the webhook was deactivated or its address is refused' "
                      "WHERE id=?", (d["id"],))
            c.commit()
            continue
        if d["webhook_id"] in down:
            continue                                            # its next run tries again; the others go now
        n = d["attempts"] + 1
        code: int | None = None
        try:
            if not _address_ok(d["url"]):
                raise PermissionError("the address is not public")
            code = _POOL.submit(_post, d["url"], d["secret"], d["event"], d["id"], d["payload"].encode()).result(timeout=POST_LIMIT_S)
            err = None if 200 <= code < 300 else f"HTTP {code}"
        except urllib.error.HTTPError as ex:
            code, err = ex.code, f"HTTP {ex.code}"
            ex.close()
        except Exception as ex:                                 # noqa: BLE001  any failure of one delivery is that delivery's (SF-E1)
            err = f"{type(ex).__name__}: {ex}"[:300]
            if isinstance(ex, (TimeoutError, FutureTimeout, ConnectionError)):
                down.add(d["webhook_id"])
        if err is None:
            c.execute("UPDATE webhook_deliveries SET status='sent', attempts=?, last_status=?, last_error=NULL, sent_at=? WHERE id=?",
                      (n, code, iso(now()), d["id"]))
            sent += 1
        elif n >= MAX_ATTEMPTS:
            c.execute("UPDATE webhook_deliveries SET status='failed', attempts=?, last_status=?, last_error=? WHERE id=?", (n, code, err, d["id"]))
            owner = row(c, "SELECT created_by FROM webhooks WHERE id=?", (d["webhook_id"],))
            if owner:                                           # the administrator who added it hears (SF-E15)
                notify(c, owner["created_by"], "message", T3("Webhook çatdırılmadı: {url}", url=d["url"][:80]), err, "/admin/integration")
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
    if not any("attendance.barred" in json.loads(w["events"]) for w in rows(c, "SELECT events FROM webhooks WHERE active=1")):
        return "no webhook wants attendance.barred"            # like the other events, nothing is replayed to a later hook (SF-E3)
    courses = rows(c, "SELECT DISTINCT l.course_id, co.code FROM attendance a JOIN lessons l ON l.id=a.lesson_id JOIN courses co ON co.id=l.course_id "
                      "WHERE a.marked_at>=?", (iso(since),))
    barred = [(co, s) for co in courses for s in journal.course_standing(c, co["course_id"]) if s["status"] == "not_admitted"]
    found = 0                                                  # computed first: the write lock is taken only for the writes (AR-E2)
    for co, s in barred:
        if c.execute("INSERT OR IGNORE INTO reminders_sent(kind,obj_id,threshold,sent_at) VALUES(?,?,?,?)",
                     ("barred", s["student_id"], str(co["course_id"]), iso(now()))).rowcount:
            emit(c, "attendance.barred", {"course_id": co["course_id"], "course_code": co["code"], "student_id": s["student_id"],
                                          "student_no": s["student_no"]})
            found += 1
    return f"barred {found}"


jobs.periodic("webhooks.send", timedelta(minutes=1), send_due)
jobs.periodic("attendance.barred", timedelta(minutes=15), barred_scan)
