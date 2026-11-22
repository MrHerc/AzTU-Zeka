"""The job runner (tasks/todo.md, Task 36, slice 1): a job runs once its interval has passed, a missed interval runs
once, a failing job stays in job_runs with its reason and the others go on, one runner holds the lease, and two
runner processes at the same moment still run a job once."""
import multiprocessing
import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from zeka.core import jobs
from zeka.legacy import store

T0 = datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc)
COUNT = {"n": 0}


@pytest.fixture
def db(app_db, tmp_path):
    """A copy of the test database: the runner's rows stay out of the other tests."""
    src = store.connect()
    path = tmp_path / "jobs.db"
    dst = sqlite3.connect(path)
    src.backup(dst)
    src.close()
    dst.close()
    c = sqlite3.connect(path, timeout=15)
    c.row_factory = sqlite3.Row
    yield c, path
    c.close()


@pytest.fixture
def registered():
    COUNT["n"] = 0

    def boom(c):
        raise RuntimeError("SMTP serveri cavab vermir")
    added = [jobs.periodic("t.count", timedelta(hours=1), lambda c: COUNT.__setitem__("n", COUNT["n"] + 1)),
             jobs.periodic("t.fail", timedelta(hours=1), boom),
             jobs.periodic("t.write", timedelta(hours=1), lambda c: c.execute("INSERT INTO reminders_sent VALUES('t',1,'x','y')"))]
    yield [j.name for j in added]
    for j in added:
        jobs.REGISTRY.pop(j.name, None)


def runs(c, name):
    return [dict(r) for r in c.execute("SELECT status, detail FROM job_runs WHERE name=? ORDER BY id", (name,))]


def test_a_job_runs_once_its_interval_has_passed_and_a_missed_interval_once(db, registered):
    c, _ = db
    assert ("t.count", "ok") in jobs.run_due(c, "a", T0, names=["t.count"])
    assert jobs.run_due(c, "a", T0 + timedelta(minutes=30), names=["t.count"]) == [], "the interval has not passed"
    assert jobs.run_due(c, "a", T0 + timedelta(hours=5), names=["t.count"]) == [("t.count", "ok")], "five missed hours: once"
    assert COUNT["n"] == 2 and [r["status"] for r in runs(c, "t.count")] == ["ok", "ok"]


def test_a_failing_job_keeps_its_reason_does_not_stop_the_others_and_is_tried_again(db, registered):
    c, _ = db
    done = dict(jobs.run_due(c, "a", T0, names=registered))
    assert done == {"t.count": "ok", "t.fail": "error", "t.write": "ok"}
    assert "SMTP serveri cavab vermir" in runs(c, "t.fail")[0]["detail"]
    assert c.execute("SELECT COUNT(*) FROM reminders_sent WHERE kind='t'").fetchone()[0] == 1, "the next job's write is kept"
    assert dict(jobs.run_due(c, "a", T0 + timedelta(minutes=1), names=registered)) == {"t.fail": "error"}, "tried again, alone"


def test_a_failing_job_waits_longer_after_each_failure(db, registered):
    """Checkpoint D (SF-7): 1, 2, 4 … minutes between tries, not every runner cycle; a success resets it."""
    c, _ = db
    tried = [m for m in range(0, 16) if jobs.run_due(c, "a", T0 + timedelta(minutes=m), names=["t.fail"])]
    assert tried == [0, 1, 3, 7, 15], tried
    jobs.REGISTRY["t.fail"] = jobs.Job("t.fail", timedelta(hours=1), lambda c: None)
    assert jobs.run_due(c, "a", T0 + timedelta(minutes=31), names=["t.fail"]) == [("t.fail", "ok")]
    assert jobs.run_due(c, "a", T0 + timedelta(minutes=40), names=["t.fail"]) == [], "healthy again: its interval"


def test_one_runner_holds_the_lease_until_it_runs_out(db):
    c, path = db
    other = sqlite3.connect(path, timeout=15)
    try:
        assert jobs.acquire(c, "a", T0) and jobs.acquire(c, "a", T0 + timedelta(minutes=1)), "renewed"
        assert not jobs.acquire(other, "b", T0 + timedelta(minutes=2))
        assert jobs.acquire(other, "b", T0 + timedelta(minutes=1) + jobs.LEASE_TTL), "a dead runner's lease runs out"
    finally:
        other.close()


def test_the_runner_loop_runs_nothing_while_another_runner_holds_the_lease(db, monkeypatch):
    """Checkpoint F (TE-F11): jobs.loop itself, not a copy of its lease logic: one cycle with another holder's lease live
    runs no job; the same cycle runs it once that lease is released."""
    c, path = db
    ran, logged = [], []
    monkeypatch.setattr(jobs, "REGISTRY", {"t.loop": jobs.Job("t.loop", timedelta(hours=1), lambda c: ran.append(1))})

    def one_cycle():
        calls = iter([False, False])          # the first-delay check, the cycle; then stop
        jobs.loop(lambda: sqlite3.connect(path, timeout=15), "a", every=0, stop=lambda: next(calls, True), log=logged.append)

    assert jobs.acquire(c, "b")                # another runner, alive
    one_cycle()
    assert ran == [] and runs(c, "t.loop") == [] and logged == []
    jobs.release(c, "b")
    one_cycle()
    assert ran == [1] and [r["status"] for r in runs(c, "t.loop")] == ["ok"] and logged == [], "the cycle really ran"


def _runner(path, holder, out):
    jobs.periodic("t.once", timedelta(hours=1), lambda c: None)
    c = sqlite3.connect(path, timeout=15)
    c.row_factory = sqlite3.Row
    try:   # as jobs.loop does: only the lease's holder runs jobs (a run without a lease blocks nothing since SF-20)
        out.put(jobs.run_due(c, holder, T0, names=["t.once"]) if jobs.acquire(c, holder, T0) else [])
    finally:
        c.close()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="two processes need fork")
def test_two_runner_processes_at_the_same_moment_run_a_job_once(db):
    c, path = db
    ctx = multiprocessing.get_context("fork")
    out = ctx.Queue()
    ps = [ctx.Process(target=_runner, args=(str(path), f"p{i}", out)) for i in range(2)]
    for p in ps:
        p.start()
    for p in ps:
        p.join(30)
    got = [out.get(timeout=5) for _ in ps]
    assert sorted(len(x) for x in got) == [0, 1]
    assert c.execute("SELECT COUNT(*) FROM job_runs WHERE name='t.once' AND status='ok'").fetchone()[0] == 1
