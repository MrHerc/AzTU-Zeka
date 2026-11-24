"""The single server's warning signs (docs/runbooks/backup.md, "Xəbərdarlıqlar"): the newest backup older than its
allowed age, too little free disk, a periodic job that failed again and again, a job runner whose lease ran out.

``checks`` only reads: the hourly job ``ops.check`` (legacy/periodic.py) tells the administrators of each problem, the
admin's status page shows the list, and ``manage.py jobs check`` runs it from the host's cron, so a dead runner (which
also stops the e-mail outbox) is still reported there. Limits are environment settings with defaults:

    ZEKA_ALERT_BACKUP_HOURS   26   the newest backup set may be this old (2 with hourly backups)
    ZEKA_ALERT_DISK_PCT       20   free space of the data and backup disks below this percentage
    ZEKA_ALERT_JOB_FAILS      3    a job's failures in a row since its last success
    ZEKA_ALERT_LEASE_MINUTES  10   minutes since the runner's lease ran out (it renews it every 30 s)

No path, file name or host name leaves this module: the admin's page must not reveal the host's layout.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from . import backup, clock, config, jobs

ROOT = Path(__file__).resolve().parents[3]          # backend/zeka/core/ -> repo


def limit(name: str, default: float) -> float:
    try:
        v = float(os.environ.get(name, "") or default)
    except ValueError:
        return default
    return v if v > 0 else default


def backup_dir() -> Path:
    return Path(os.environ.get("BACKUP_DIR") or ROOT / "backups")          # the default of manage.py backup --dest


def _backup(now_local: datetime) -> dict:
    hours = limit("ZEKA_ALERT_BACKUP_HOURS", 26)
    try:
        found = backup.sets(backup_dir()) if backup_dir().is_dir() else {}
    except OSError:                                  # an unreadable folder counts as no backup, never as a failed page
        found = {}
    if not found:                                    # a demo without backups has nothing to warn about; prod must have one
        return {"key": "backup", "ok": False if config.prod() else None, "newest": None, "age_h": None, "limit": hours}
    newest = max(found)
    age = round((now_local - newest).total_seconds() / 3600, 1)
    return {"key": "backup", "ok": age <= hours, "newest": newest.isoformat(timespec="minutes"), "age_h": age, "limit": hours}


def _disk(data: Path) -> dict:
    pct = limit("ZEKA_ALERT_DISK_PCT", 20)
    seen, worst = set(), None
    for p in (data, backup_dir()):
        try:
            dev = p.stat().st_dev
            if dev in seen:
                continue
            seen.add(dev)
            u = shutil.disk_usage(p)
        except OSError:
            continue
        free = {"free_pct": round(100 * u.free / u.total, 1), "free_gb": round(u.free / 2**30, 1)}
        if worst is None or free["free_pct"] < worst["free_pct"]:
            worst = free
    if worst is None:
        return {"key": "disk", "ok": None, "free_pct": None, "free_gb": None, "limit": pct}
    return {"key": "disk", "ok": worst["free_pct"] >= pct, **worst, "limit": pct}


def _jobs(c: sqlite3.Connection) -> dict:
    n = int(limit("ZEKA_ALERT_JOB_FAILS", 3))
    failing = []
    for name in sorted(jobs.REGISTRY):
        last_ok = c.execute("SELECT MAX(started_at) FROM job_runs WHERE name=? AND status='ok'", (name,)).fetchone()[0]
        fails = c.execute("SELECT COUNT(*) FROM job_runs WHERE name=? AND status='error' AND started_at>?", (name, last_ok or "")).fetchone()[0]
        if fails >= n:
            failing.append({"name": name, "fails": fails})
    return {"key": "jobs", "ok": not failing, "failing": failing, "limit": n}


def _runner(c: sqlite3.Connection, now: datetime) -> dict:
    minutes = limit("ZEKA_ALERT_LEASE_MINUTES", 10)
    if os.environ.get("ZEKA_JOBS") == "0":          # the runner is turned off on purpose (tests, a cron-only setup)
        return {"key": "runner", "ok": None, "expired_min": None, "limit": minutes}
    r = c.execute("SELECT expires_at FROM job_lease WHERE name=?", (jobs.LEASE,)).fetchone()
    if r is None:
        return {"key": "runner", "ok": False, "expired_min": None, "limit": minutes}
    late = (now - datetime.fromisoformat(r[0])).total_seconds() / 60
    return {"key": "runner", "ok": late <= minutes, "expired_min": max(0, round(late)), "limit": minutes}


def checks(c: sqlite3.Connection, data: Path) -> list[dict]:
    """Each check: ``ok`` True (fine), False (a problem) or None (nothing to check here), its measured value and limit."""
    return [_backup(clock.local()), _disk(data), _jobs(c), _runner(c, clock.now())]


def problems(c: sqlite3.Connection, data: Path) -> list[dict]:
    return [x for x in checks(c, data) if x["ok"] is False]
