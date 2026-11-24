"""The single server's warning signs (core/ops.py, job ops.check): a backup older than its allowed age, too little free
disk, a job failing in a row, a stale runner lease; the administrators hear of each once a day, in the portal and by
e-mail; the admin's status page shows them without a path; the public /healthz shows none of it."""
import os
import sqlite3
import subprocess
import sys
from collections import namedtuple
from datetime import timedelta

import pytest

from zeka.core import clock, config, jobs, ops
from zeka.legacy import periodic, store

ROOT = store.ROOT
Usage = namedtuple("Usage", "total used free")


@pytest.fixture
def copy(app_db, tmp_path):
    src = store.connect()
    path = tmp_path / "ops.db"
    dst = sqlite3.connect(path)
    src.backup(dst)
    src.close()
    dst.close()
    c = sqlite3.connect(path, timeout=15)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture
def backups(tmp_path, monkeypatch):
    d = tmp_path / "backups"
    d.mkdir()
    monkeypatch.setenv("BACKUP_DIR", str(d))
    monkeypatch.delenv("ZEKA_JOBS", raising=False)
    monkeypatch.setattr(ops.shutil, "disk_usage", lambda p: Usage(100 * 2**30, 50 * 2**30, 50 * 2**30))   # never this host's own disk
    return d


def _set(d, hours_ago: float):
    stamp = f"{clock.local() - timedelta(hours=hours_ago):%Y%m%d-%H%M%S}"
    for ext in ("enc", "json"):
        (d / f"zeka-{stamp}.{ext}").write_text("{}")


def _check(c, key):
    return next(x for x in ops.checks(c, store.DATA) if x["key"] == key)


def _lease(c, minutes_ago: float):
    c.execute("INSERT OR REPLACE INTO job_lease(name, holder, expires_at) VALUES(?,?,?)",
              (jobs.LEASE, "t", (clock.now() - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")))
    c.commit()


def test_the_newest_backup_must_be_younger_than_its_limit(copy, backups, monkeypatch):
    assert _check(copy, "backup")["ok"] is None, "a demo without any backup has nothing to warn about"
    monkeypatch.setattr(config, "MODE", "prod")
    assert _check(copy, "backup")["ok"] is False, "prod without any backup is a problem"
    _set(backups, 30)
    x = _check(copy, "backup")
    assert x["ok"] is False and x["age_h"] == 30.0 and x["limit"] == 26
    _set(backups, 0.5)
    assert _check(copy, "backup")["ok"] is True
    monkeypatch.setenv("ZEKA_ALERT_BACKUP_HOURS", "0.25")
    assert _check(copy, "backup")["ok"] is False, "the limit is a setting (2 with hourly backups)"


def test_free_disk_under_the_threshold_is_a_problem(copy, backups, monkeypatch):
    assert _check(copy, "disk")["ok"] is True
    monkeypatch.setattr(ops.shutil, "disk_usage", lambda p: Usage(100 * 2**30, 85 * 2**30, 15 * 2**30))
    x = _check(copy, "disk")
    assert x["ok"] is False and x["free_pct"] == 15.0 and x["free_gb"] == 15.0 and x["limit"] == 20


def test_a_job_that_failed_three_times_in_a_row_is_a_problem(copy, backups):
    t = clock.now()
    copy.execute("INSERT INTO job_runs(name, started_at, status, holder) VALUES('radar.summary', ?, 'ok', 't')",
                 ((t - timedelta(hours=2)).isoformat(timespec="seconds"),))
    for i in range(2):
        copy.execute("INSERT INTO job_runs(name, started_at, status, holder) VALUES('radar.summary', ?, 'error', 't')",
                     ((t - timedelta(minutes=50 - i)).isoformat(timespec="seconds"),))
    copy.commit()
    assert _check(copy, "jobs")["ok"] is True, "two failures are not yet a problem"
    copy.execute("INSERT INTO job_runs(name, started_at, status, holder) VALUES('radar.summary', ?, 'error', 't')", (t.isoformat(timespec="seconds"),))
    copy.commit()
    x = _check(copy, "jobs")
    assert x["ok"] is False and x["failing"] == [{"name": "radar.summary", "fails": 3}]


def test_a_lease_that_ran_out_long_ago_means_the_runner_stopped(copy, backups, monkeypatch):
    copy.execute("DELETE FROM job_lease")
    copy.commit()
    assert _check(copy, "runner") == {"key": "runner", "ok": False, "expired_min": None, "limit": 10}
    _lease(copy, -2)                       # renewed: it runs out in two minutes
    assert _check(copy, "runner")["ok"] is True
    _lease(copy, 25)
    assert _check(copy, "runner")["ok"] is False and _check(copy, "runner")["expired_min"] == 25
    monkeypatch.setenv("ZEKA_JOBS", "0")
    assert _check(copy, "runner")["ok"] is None, "a runner turned off on purpose is not a problem"


def test_the_administrators_are_told_once_a_day_in_the_portal_and_by_e_mail(copy, backups, monkeypatch):
    monkeypatch.setenv("ZEKA_SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(config, "MODE", "prod")
    _set(backups, 40)
    _lease(copy, -2)
    admins = periodic.admins(copy)
    assert admins
    out = periodic.ops_check(copy)
    assert out.startswith("problems 1 · told 1") and out.endswith("backup"), out
    notes = copy.execute("SELECT user_id, title, link FROM notifications WHERE kind='ops'").fetchall()
    assert sorted(n["user_id"] for n in notes) == admins and all(n["link"] == "/admin" for n in notes)
    assert "40" in notes[0]["title"] and "26" in notes[0]["title"]
    mails = copy.execute("SELECT COUNT(*) FROM outbox WHERE kind='ops'").fetchone()[0]
    assert mails == sum(1 for u in admins if copy.execute("SELECT email FROM users WHERE id=?", (u,)).fetchone()[0])
    assert periodic.ops_check(copy).startswith("problems 1 · told 0"), "the same problem is told once a day"
    assert copy.execute("SELECT COUNT(*) FROM notifications WHERE kind='ops'").fetchone()[0] == len(notes)


def test_ops_check_is_an_hourly_job():
    assert jobs.REGISTRY["ops.check"].interval == timedelta(hours=1)


def test_the_admin_status_page_shows_the_checks_without_paths_and_healthz_shows_none(app_db, admin, student, backups):
    _set(backups, 1)
    s = admin.get("/api/admin/status").json
    assert [x["key"] for x in s["ops"]] == ["backup", "disk", "jobs", "runner"]
    assert s["ops"][0]["ok"] is True and s["ops"][0]["age_h"] == 1.0
    assert str(backups) not in str(s["ops"]) and str(store.DATA) not in str(s["ops"])
    assert student.get("/api/admin/status").status == 403
    h = app_db.client().get("/healthz").json
    assert set(h) == {"ok", "worker", "server_time", "tz"}, "the public liveness answer names no check"


def test_manage_jobs_check_exits_1_on_a_problem(app_db, tmp_path):
    data = tmp_path / "data"
    _db_copy(data / "campus.db")
    env = {**os.environ, "ZEKA_DATA": str(data), "BACKUP_DIR": str(tmp_path / "none"), "PYTHONIOENCODING": "utf-8",
           "ZEKA_ALERT_DISK_PCT": "0.001"}       # this host's own disk must not decide the test
    env.pop("ZEKA_JOBS", None)
    r = subprocess.run([sys.executable, str(ROOT / "backend" / "manage.py"), "jobs", "check"], env=env, capture_output=True,
                       text=True, timeout=600)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "runner  PROBLEM" in r.stdout and "problems 1" in r.stdout, r.stdout


def _db_copy(target):
    """The demo database at ``target`` (manage.py jobs check reads a database that exists, it never makes one)."""
    target.parent.mkdir(parents=True)
    src, dst = store.connect(), sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()


def test_manage_jobs_check_never_creates_migrates_or_indexes_a_database(tmp_path):
    """SEC-27F-1: the host's hourly cron ran a whole store.init() (migrations, the search indexes: 20 s of CPU and
    0.8 GB at university scale) in the app's container for a check that takes no time."""
    data = tmp_path / "data"
    env = {**os.environ, "ZEKA_DATA": str(data), "BACKUP_DIR": str(tmp_path / "none"), "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, str(ROOT / "backend" / "manage.py"), "jobs", "check"], env=env, capture_output=True,
                       text=True, timeout=600)
    assert r.returncode == 2 and "campus.db" in r.stderr, r.stdout + r.stderr
    assert not (data / "campus.db").exists(), "a missing database is reported, never created and seeded"


def test_manage_jobs_check_exits_0_when_nothing_is_wrong_and_reads_no_index(app_db, backups, monkeypatch, capsys):
    import manage
    monkeypatch.setenv("ZEKA_JOBS", "0")                    # the runner is off: nothing to check there (ok None)
    monkeypatch.setattr(store, "init", lambda *a, **k: pytest.fail("jobs check must not run store.init()"))
    assert _check_all(store.connect()) == {"backup": None, "disk": True, "jobs": True, "runner": None}
    assert manage.run_jobs("check") == 0, capsys.readouterr().out
    assert "problems 0 · told 0" in capsys.readouterr().out


def _check_all(c):
    try:
        return {x["key"]: x["ok"] for x in ops.checks(c, store.DATA)}
    finally:
        c.close()


def test_a_lasting_problem_is_told_again_the_next_day(copy, backups, monkeypatch):
    monkeypatch.setattr(config, "MODE", "prod")
    _set(backups, 40)
    _lease(copy, -2)
    assert periodic.ops_check(copy).startswith("problems 1 · told 1")
    assert periodic.ops_check(copy).startswith("problems 1 · told 0")
    later = periodic.now() + timedelta(days=1)
    monkeypatch.setattr(periodic, "now", lambda: later)
    assert periodic.ops_check(copy).startswith("problems 1 · told 1"), "once a day, not once ever"


def _fail(c, name, n):
    t = clock.now()
    for i in range(n):
        c.execute("INSERT INTO job_runs(name, started_at, status, holder) VALUES(?, ?, 'error', 't')",
                  (name, (t - timedelta(minutes=10 - i)).isoformat(timespec="seconds")))
    c.commit()


def test_a_second_failing_job_the_same_day_is_told_too(copy, backups, monkeypatch):
    """WF27F-3: the day's mark was the check's key alone, so a job that began to fail after the first one was not told."""
    _lease(copy, -2)
    _fail(copy, "radar.snapshot", 3)
    assert periodic.ops_check(copy) == "problems 1 · told 1 · jobs"
    assert periodic.ops_check(copy) == "problems 1 · told 0 · jobs"
    _fail(copy, "outbox.send", 3)
    assert periodic.ops_check(copy) == "problems 1 · told 1 · jobs", "outbox.send is a new problem"
    titles = [r[0] for r in copy.execute("SELECT title FROM notifications WHERE kind='ops' ORDER BY id")]
    assert any("outbox.send (3)" in t for t in titles), titles


def test_no_backup_and_an_old_backup_are_two_problems(copy, backups, monkeypatch):
    monkeypatch.setattr(config, "MODE", "prod")
    _lease(copy, -2)
    assert periodic.ops_check(copy) == "problems 1 · told 1 · backup"           # none at all
    _set(backups, 40)
    assert periodic.ops_check(copy) == "problems 1 · told 1 · backup", "a set appeared, but it is too old: a new problem"


def test_the_backup_disk_counts_too(copy, backups, monkeypatch):
    """The data disk is 90% free, the backup disk (another device) 5%: the worse one decides."""
    data_dev = store.DATA.stat().st_dev
    real_stat = type(backups).stat

    def stat(self, *a, **k):
        st = real_stat(self, *a, **k)
        return os.stat_result((*st[:2], data_dev + 1, *st[3:])) if self == backups else st
    monkeypatch.setattr(type(backups), "stat", stat)
    monkeypatch.setattr(ops.shutil, "disk_usage", lambda p: Usage(100, 95, 5) if str(p) == str(backups) else Usage(100, 10, 90))
    x = _check(copy, "disk")
    assert x["ok"] is False and x["free_pct"] == 5.0, x


def test_a_blocked_administrator_is_not_told(copy, backups):
    uid = periodic.admins(copy)[0]
    copy.execute("UPDATE users SET status='blocked' WHERE id=?", (uid,))
    copy.commit()
    assert uid not in periodic.admins(copy)


def test_the_default_backup_folder_is_manage_py_s_and_a_zero_limit_falls_back(monkeypatch):
    monkeypatch.delenv("BACKUP_DIR", raising=False)
    assert ops.backup_dir() == store.ROOT / "backups", "manage.py backup --dest without BACKUP_DIR"
    for bad in ("0", "-5", "x"):
        monkeypatch.setenv("ZEKA_ALERT_DISK_PCT", bad)
        assert ops.limit("ZEKA_ALERT_DISK_PCT", 20) == 20, bad


def test_a_value_at_its_limit_is_still_fine(copy, backups, monkeypatch):
    stamp = clock.local().replace(microsecond=0) - timedelta(hours=26)
    monkeypatch.setattr(clock, "local", lambda: stamp + timedelta(hours=26))
    for ext in ("enc", "json"):
        (backups / f"zeka-{stamp:%Y%m%d-%H%M%S}.{ext}").write_text("{}")
    assert _check(copy, "backup")["age_h"] == 26.0 and _check(copy, "backup")["ok"] is True
    at = clock.now().replace(microsecond=0)
    monkeypatch.setattr(clock, "now", lambda: at)
    _lease(copy, 10)
    assert _check(copy, "runner")["expired_min"] == 10 and _check(copy, "runner")["ok"] is True
