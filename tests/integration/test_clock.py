"""The university clock (tasks/todo.md, Task 5): Baku wall-clock time whatever the server's own timezone."""
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from zeka.core import clock
from zeka.legacy import r_learning, store

ROOT = Path(__file__).resolve().parents[2]
TUESDAY_0600Z = datetime(2026, 11, 17, 6, 0, tzinfo=timezone.utc)       # 10:00 in Baku, Monday 22:00 in Los Angeles


@pytest.fixture
def los_angeles_server_at_0600z(monkeypatch):
    if not hasattr(time, "tzset") or clock.ZONE is None:
        pytest.skip("needs a POSIX timezone switch and a tz database")
    old = os.environ.get("TZ")
    os.environ["TZ"] = "America/Los_Angeles"
    time.tzset()
    monkeypatch.setattr(clock, "now", lambda: TUESDAY_0600Z)
    yield
    if old is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = old
    time.tzset()


def test_local_time_is_baku_time(los_angeles_server_at_0600z):
    assert time.tzname[0] in ("PST", "PDT")                              # the OS believes it is in Los Angeles
    assert store.now() == datetime(2026, 11, 17, 10, 0)


def test_next_lesson_follows_the_university_clock(seeded, los_angeles_server_at_0600z):
    c = seeded()
    cid = {r["code"]: r["id"] for r in store.rows(c, "SELECT id, code FROM courses")}
    physics = r_learning.next_lesson(c, cid["FİZ-1103"])                 # Tuesday 10:30-11:50
    maths = r_learning.next_lesson(c, cid["RİY-1101"])                   # Tue 09:00 is over at 10:00; next: Wed 12:00
    assert (physics["date"], physics["start"]) == ("2026-11-17", "10:30")
    assert (maths["date"], maths["start"]) == ("2026-11-18", "12:00")   # Los Angeles time would say Tue 09:00


@pytest.mark.slow
@pytest.mark.parametrize("mode", ["prod", "demo"])       # the demo too: no silent fall back to the OS time (2026-11-24)
def test_an_unknown_timezone_is_refused(mode, tmp_path):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "ZEKA_MODE": mode, "ZEKA_TZ": "Mars/Olympus_Mons",
           "ZEKA_DATA": str(tmp_path)}
    p = subprocess.run([sys.executable, str(ROOT / "backend" / "run.py")], env=env, capture_output=True, timeout=120)
    assert p.returncode == 2 and "ZEKA_TZ=Mars/Olympus_Mons" in p.stderr.decode("utf-8", "replace")
