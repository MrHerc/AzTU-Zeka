"""Periodic jobs (tasks/todo.md, Task 36, slice 1).

Nothing in Zəka used to run by itself: time-bound work happened only when a request came or the server started. A job
is registered with ``periodic(name, interval, fn)``; ``run_due`` runs every job whose interval has passed since its
last successful run, each in its own transaction, and writes a ``job_runs`` row with the result. A runner that was down
runs a missed interval once, not once per interval missed. A failing job stays in ``job_runs`` with its reason, does
not stop the others, and is tried again on the next cycle.

One runner works at a time: ``acquire`` takes a lease row in the database, renewed every cycle, so two runner
processes (or a restarted one while the old is still alive) never run the same job twice. The claim of a job is checked
again inside the write lock, so even two runners that both hold a stale idea of the lease cannot both run it.

This module is core: it knows nothing of the jobs themselves. They register from the layers that own them
(``legacy/periodic.py``); the runner process (``run.py``) imports that module before it starts.
"""
from __future__ import annotations

import sqlite3
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import clock


@dataclass(frozen=True)
class Job:
    name: str
    interval: timedelta
    fn: Callable[[sqlite3.Connection], object]


REGISTRY: dict[str, Job] = {}
LEASE = "runner"
LEASE_TTL = timedelta(minutes=3)        # a runner renews it every cycle; a dead one's lease runs out
STALE_RUN = timedelta(minutes=30)       # a 'running' row older than this is a runner that died mid-job
RETRY_CAP = timedelta(minutes=30)       # the longest wait of a failing job before its next try


def periodic(name: str, interval: timedelta, fn: Callable[[sqlite3.Connection], object]) -> Job:
    job = Job(name, interval, fn)
    REGISTRY[name] = job
    return job


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def acquire(c: sqlite3.Connection, holder: str, now: datetime | None = None) -> bool:
    """Take or renew the runner's lease; False while another holder's lease is in force."""
    t = now or clock.now()
    c.execute("BEGIN IMMEDIATE")
    try:
        c.execute("INSERT OR IGNORE INTO job_lease(name, holder, expires_at) VALUES(?, '', ?)", (LEASE, _iso(t)))
        got = c.execute("UPDATE job_lease SET holder=?, expires_at=? WHERE name=? AND (holder=? OR expires_at<=?)",
                        (holder, _iso(t + LEASE_TTL), LEASE, holder, _iso(t))).rowcount == 1
        c.commit()
        return got
    except BaseException:
        c.rollback()
        raise


def release(c: sqlite3.Connection, holder: str):
    c.execute("UPDATE job_lease SET expires_at=? WHERE name=? AND holder=?", (_iso(clock.now()), LEASE, holder))
    c.commit()


def _claim(c: sqlite3.Connection, job: Job, holder: str, t: datetime) -> int | None:
    """A 'running' row for the job when it is due, inside the write lock; None when it is not due (or another runner
    is on it)."""
    c.execute("BEGIN IMMEDIATE")
    try:
        last_ok = c.execute("SELECT MAX(started_at) FROM job_runs WHERE name=? AND status='ok'", (job.name,)).fetchone()[0]
        # Checkpoint D (CR-8, SF-20): only a run of another holder that still holds the lease is in progress; a row left
        # 'running' by a runner that died (its lease is gone) or by this one (a failed bookkeeping write) blocks nothing
        busy = c.execute("SELECT 1 FROM job_runs r JOIN job_lease l ON l.name=? AND l.holder=r.holder AND l.expires_at>? "
                         "WHERE r.name=? AND r.status='running' AND r.started_at>? AND r.holder<>?",
                         (LEASE, _iso(t), job.name, _iso(t - STALE_RUN), holder)).fetchone()
        # Checkpoint D (SF-7): after a failure the job waits 1, 2, 4 … minutes (at most its interval and RETRY_CAP), not
        # one runner cycle, so a broken job neither runs twice as often as a healthy one nor floods job_runs
        fails, last_fail = c.execute("SELECT COUNT(*), MAX(started_at) FROM job_runs WHERE name=? AND status='error' AND started_at>?",
                                     (job.name, last_ok or "")).fetchone()
        due: datetime | None = None
        if fails:
            due = datetime.fromisoformat(last_fail) + min(job.interval, RETRY_CAP, timedelta(minutes=2 ** min(fails - 1, 10)))
        elif last_ok:
            due = datetime.fromisoformat(last_ok) + job.interval
        if busy or (due and due > t):
            c.rollback()
            return None
        c.execute("UPDATE job_runs SET status='error', detail='the runner stopped during this run' WHERE name=? AND status='running'",
                  (job.name,))
        rid = c.execute("INSERT INTO job_runs(name, started_at, status, holder) VALUES(?,?,'running',?)",
                        (job.name, _iso(t), holder)).lastrowid
        c.commit()
        return rid
    except BaseException:
        c.rollback()
        raise


def run_due(c: sqlite3.Connection, holder: str, now: datetime | None = None, names: list[str] | None = None) -> list[tuple[str, str]]:
    """Run every registered job that is due; [(name, 'ok' | 'error')] of those that ran."""
    t = now or clock.now()
    done = []
    for name in sorted(names or REGISTRY):
        job = REGISTRY[name]
        rid = _claim(c, job, holder, t)
        if rid is None:
            continue
        started = time.monotonic()
        try:
            detail = job.fn(c)
            c.commit()
            status, text = "ok", "" if detail is None else str(detail)[:500]
        except Exception as ex:                       # noqa: BLE001  one job's failure must not stop the others
            c.rollback()
            status, text = "error", f"{type(ex).__name__}: {ex}"[:500] + " | " + traceback.format_exc(limit=3)[-400:]
        c.execute("UPDATE job_runs SET status=?, finished_at=?, detail=?, ms=? WHERE id=?",
                  (status, _iso(clock.now()), text, round((time.monotonic() - started) * 1000), rid))
        c.commit()
        done.append((name, status))
    return done


def status(c: sqlite3.Connection) -> list[dict]:
    """Each registered job with its last run (``manage.py jobs status``)."""
    out = []
    for name in sorted(REGISTRY):
        r = c.execute("SELECT started_at, finished_at, status, detail, ms FROM job_runs WHERE name=? ORDER BY id DESC LIMIT 1",
                      (name,)).fetchone()
        last_ok = c.execute("SELECT MAX(started_at) FROM job_runs WHERE name=? AND status='ok'", (name,)).fetchone()[0]
        out.append({"name": name, "interval_s": int(REGISTRY[name].interval.total_seconds()),
                    "last": dict(r) if r else None, "last_ok": last_ok})
    return out


def loop(connect: Callable[[], sqlite3.Connection], holder: str, every: float = 30.0, stop: Callable[[], bool] = lambda: False,
         log: Callable[[str], None] = print, first_delay: float = 0.0):
    """The runner: take the lease, run what is due, sleep; until ``stop()``. A cycle's error is logged, not fatal."""
    deadline = time.monotonic() + first_delay
    while not stop() and time.monotonic() < deadline:
        time.sleep(min(1.0, every))
    c = connect()
    try:
        while not stop():
            try:
                if acquire(c, holder):
                    for name, result in run_due(c, holder):
                        if result != "ok":
                            log(f"job {name} failed; see job_runs")
            except Exception as ex:                   # noqa: BLE001  the runner outlives a bad cycle (a locked database, a full disk)
                log(f"job runner cycle failed: {type(ex).__name__}: {ex}")
                try:
                    c.rollback()                      # Checkpoint D (PY-2): a half-open transaction would refuse every next cycle
                except sqlite3.Error:
                    pass
            for _ in range(int(every)):
                if stop():
                    break
                time.sleep(1)
    finally:
        try:
            release(c, holder)
        finally:
            c.close()
