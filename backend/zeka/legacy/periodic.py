"""The periodic jobs of Zəka (tasks/todo.md, Task 36, slice 1), registered on import with ``core.jobs.periodic``.

- ``retention.purge``, daily: AI conversations, club messages, notifications, the audit log and the technical logs past
  their retention periods (university settings, Task 40), spent one-time keys, rate-limit events, old sign-in blocks,
  sessions past every idle limit and events older than a year (Task 39).
- ``reminders.sla``, every 15 minutes: a request about to pass its SLA and one past it (to the dean's office), a support
  ticket past its SLA (to whoever holds it), an assignment due within a day (to its students who have not submitted);
  each threshold once per object.
- ``lessons.generate``, daily: the current term's lessons from tomorrow on, as Task 19 makes them (idempotent).
- ``radar.snapshot``, weekly: this week's Zəka Radar counts, which only the demo seed wrote before.

Task 26 adds ``exam.autosubmit`` from the exam module.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

from ..core import clock, jobs
from ..core.i18n import T3
from . import radar, store, support
from .common import step_actors
from .store import J, iso, notify, now, rows
from ..modules.identity import domain as identity
from ..modules.identity import privacy
from ..modules.comms import service as _comms  # noqa: F401  registers outbox.send (Task 36, slice 2)

DAY = timedelta(days=1)


def retention_purge(c) -> str:
    """Every period is a university setting (Task 40, privacy.RETENTION; docs/privacy/data-inventory.md)."""
    t = now()
    keep = privacy.retention(c)
    logs = timedelta(days=keep["logs_days"])
    purge = store.purge                  # batches of store.PURGE_BATCH, each its own transaction (Checkpoint F, AR-F5)
    chats = store.purge_expired(c)
    keys = purge(c, "doc_keys", "expires_at<?", (iso(t),))
    hits = purge(c, "rate_hits", "ts<?", (time.time() - 86400,))        # the longest window is minutes
    blocks = purge(c, "login_blocks", "COALESCE(until, first)<?", (time.time() - 86400,))
    sessions = purge(c, "sessions", "last_seen<?", (iso(t - timedelta(seconds=identity.MAX_IDLE)),))
    old = (clock.now() - logs).isoformat(timespec="seconds")   # job and outbox times are aware UTC (Checkpoint D, AR-13)
    runs = purge(c, "job_runs", "started_at<? AND status<>'running'", (old,))
    mails = purge(c, "outbox", "created_at<? AND status IN ('sent','failed','skipped')", (old,))
    from ..modules.community import service as community     # club messages past their retention period (Task 35)
    club = community.purge(c)
    hooks = purge(c, "webhook_deliveries", "status IN ('sent','failed') AND created_at<?", (iso(t - logs),))   # Checkpoint E (AR-E7)
    notes = purge(c, "notifications", "created_at<?", (iso(t - timedelta(days=keep["notifications_days"])),))
    logged = purge(c, "audit", "ts<?", (iso(t - timedelta(days=keep["audit_days"])),))
    events = purge(c, "events", "created_at<?", (iso(t - KEEP_EVENTS),))
    return (f"chats {chats} · keys {keys} · rate hits {hits} · sign-in blocks {blocks} · sessions {sessions} · job runs {runs} · mails {mails}"
            f" · club messages {club} · webhook deliveries {hooks} · notifications {notes} · audit {logged} · events {events}")


KEEP_EVENTS = timedelta(days=365)       # Task 39: one academic year of activity for the measured indicators and the evidence


def _once(c, kind: str, obj_id: int, threshold: str) -> bool:
    """True the first time this reminder is due (and records it), False afterwards."""
    return c.execute("INSERT OR IGNORE INTO reminders_sent(kind,obj_id,threshold,sent_at) VALUES(?,?,?,?)",
                     (kind, obj_id, threshold, iso(now()))).rowcount == 1


def reminders_sla(c) -> str:
    t = now()
    sent = 0
    for r in rows(c, "SELECT r.id, r.student_id, r.due_at, r.step, r.data, rt.name, rt.step_roles FROM requests r JOIN request_types rt "
                     "ON rt.code=r.type_code WHERE r.status IN ('submitted','in_progress') AND r.due_at IS NOT NULL AND r.due_at<?",
                  (iso(t + DAY),)):
        due = datetime.fromisoformat(r["due_at"])
        threshold = "overdue" if due <= t else "soon"
        roles = J(r["step_roles"], []) or ["office"]
        office = step_actors(c, roles[min(r["step"], len(roles) - 1)], r["student_id"], J(r["data"], {}) or {})   # the step's role (Task 46)
        # once per threshold and step: the role of a later step hears about it too (TE46-9)
        if not office or not _once(c, "request", r["id"], f"{threshold}:{r['step']}"):   # nobody to tell yet: try again next run (SF-8)
            continue
        title = (T3("Müraciətin müddəti keçdi: {name}", name=r["name"]) if threshold == "overdue"
                 else T3("Müraciətin müddəti bir gündən az qalıb: {name}", name=r["name"]))
        notify(c, office, "request", title, r["due_at"].replace("T", " ")[:16], f"/office/request/{r['id']}")   # the page's route (OLD-2)
        sent += 1
    for k in rows(c, "SELECT id, subject, priority, created_at, assignee_id FROM support_tickets WHERE status IN ('open','in_progress') "
                     "AND assignee_id IS NOT NULL"):
        due = datetime.fromisoformat(k["created_at"]) + timedelta(hours=support.SLA_HOURS.get(k["priority"], 24))
        if due <= t and _once(c, "ticket", k["id"], "overdue"):
            notify(c, [k["assignee_id"]], "support", T3("Dəstək sorğusunun müddəti keçdi: {subject}", subject=k["subject"]), "",
                   f"/staff/support/{k['id']}")
            sent += 1
    for a in rows(c, "SELECT a.id, a.course_id, a.title, a.due_at FROM assignments a WHERE a.due_at>? AND a.due_at<=?",
                  (t.strftime("%Y-%m-%dT%H:%M"), (t + DAY).strftime("%Y-%m-%dT%H:%M"))):
        if not _once(c, "assignment", a["id"], "soon"):
            continue
        waiting = [x["user_id"] for x in rows(c, "SELECT e.user_id FROM enrollments e WHERE e.course_id=? AND NOT EXISTS "
                                                 "(SELECT 1 FROM submissions s WHERE s.assignment_id=? AND s.student_id=e.user_id)",
                                              (a["course_id"], a["id"]))]
        if waiting:
            notify(c, waiting, "assignment", T3("Tapşırığın son tarixi sabahdır: {title}", title=a["title"]), a["due_at"].replace("T", " "),
                   f"/student/course/{a['course_id']}")
            sent += 1
    from ..modules.qa import office_hours                     # here: that module imports the legacy layer
    sent += office_hours.remind(c, _once)                     # office hours within two hours (Task 34)
    return f"reminders {sent}"


def lessons_generate(c) -> str:
    from ..modules.timetable import service as timetable     # here: that module imports the legacy layer
    t = timetable.term(c, None)
    if not t:
        return "no current term"
    made = timetable.make_lessons(c, timetable.term_rows(c, t["id"]), t, now().date() + DAY)   # never into the past
    return f"{t['code']} · lessons {made}"


def radar_snapshot(c) -> str:
    return f"week {radar.snapshot_week(c)}"


jobs.periodic("retention.purge", DAY, retention_purge)
jobs.periodic("reminders.sla", timedelta(minutes=15), reminders_sla)
jobs.periodic("lessons.generate", DAY, lessons_generate)
jobs.periodic("radar.snapshot", timedelta(days=7), radar_snapshot)
from ..modules.integration import webhooks as _webhooks  # noqa: E402,F401  (Task 37: webhooks.send, attendance.barred)
from ..modules.exam import service as _exam  # noqa: E402,F401  registers exam.autosubmit (Task 26)
