"""The periodic jobs Zəka registers (tasks/todo.md, Task 36, slice 1): the expected list, each running once when the
clock passes its interval and not before, and the SLA reminders sent once per threshold. They run on a copy of the test
database: the Radar snapshot and the lessons they write stay out of the other tests."""
import sqlite3
from datetime import timedelta

import pytest

from zeka.core import clock, jobs
from zeka.legacy import periodic, store  # noqa: F401  periodic registers the jobs

EXPECTED = ["exam.autosubmit", "lessons.generate", "outbox.send", "radar.snapshot", "reminders.sla", "retention.purge"]


@pytest.fixture
def copy(app_db, tmp_path):
    src = store.connect()
    path = tmp_path / "periodic.db"
    dst = sqlite3.connect(path)
    src.backup(dst)
    src.close()
    dst.close()
    c = sqlite3.connect(path, timeout=15)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_the_registry_holds_the_expected_jobs():
    assert sorted(n for n in jobs.REGISTRY if not n.startswith("t.")) == EXPECTED


def test_each_job_runs_once_when_its_interval_passes_and_not_before(copy):
    t0 = clock.now()
    first = jobs.run_due(copy, "test", t0, names=EXPECTED)
    assert first == [(n, "ok") for n in EXPECTED], first
    assert jobs.run_due(copy, "test", t0 + timedelta(seconds=30), names=EXPECTED) == [], "the shortest interval is a minute"
    later = jobs.run_due(copy, "test", t0 + timedelta(days=8), names=EXPECTED)
    assert later == [(n, "ok") for n in EXPECTED], "every interval has passed once more: each runs once"
    assert all(copy.execute("SELECT COUNT(*) FROM job_runs WHERE name=? AND status='ok'", (n,)).fetchone()[0] == 2 for n in EXPECTED)


def test_an_overdue_request_reminds_the_dean_s_office_once(copy):
    r = copy.execute("SELECT r.id, r.student_id FROM requests r WHERE r.status IN ('submitted','in_progress') ORDER BY r.id LIMIT 1").fetchone()
    copy.execute("UPDATE requests SET due_at=? WHERE id=?", (store.iso(store.now() - timedelta(hours=1)), r["id"]))
    copy.commit()
    before = copy.execute("SELECT COUNT(*) FROM notifications WHERE link=?", (f"/office/requests/{r['id']}",)).fetchone()[0]
    periodic.reminders_sla(copy)
    periodic.reminders_sla(copy)
    after = copy.execute("SELECT COUNT(*) FROM notifications WHERE link=?", (f"/office/requests/{r['id']}",)).fetchone()[0]
    assert after > before and copy.execute("SELECT COUNT(*) FROM reminders_sent WHERE kind='request' AND obj_id=? AND threshold='overdue'",
                                           (r["id"],)).fetchone()[0] == 1


def test_lessons_are_made_from_tomorrow_never_into_the_past(copy):
    today = store.now().date().isoformat()
    before = copy.execute("SELECT COUNT(*) FROM lessons WHERE day<=?", (today,)).fetchone()[0]
    periodic.lessons_generate(copy)
    assert copy.execute("SELECT COUNT(*) FROM lessons WHERE day<=?", (today,)).fetchone()[0] == before
