"""The suite's write-lock guard (ZEKA_TX_GUARD, Task 7) counts the handler's own work, not a loaded machine (Checkpoint F,
TE-F10, TE-F11): a request descheduled for half a second after its first write is not a long hold; one that works under
the lock for over 200 ms, or waits under it for over a second, still fails."""
import time
from types import SimpleNamespace

import pytest

from zeka.legacy import common


class Db:
    total_changes = 0

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def req(wall_ago: float, cpu_ago: float):
    return SimpleNamespace(db=Db(), path="/api/x", user=None, changes_from=None, audit_kind=None,
                           first_write=time.monotonic() - wall_ago, first_cpu=time.thread_time() - cpu_ago)


@pytest.fixture(autouse=True)
def guard(monkeypatch):
    monkeypatch.setattr(common, "_TX_GUARD", True)


def test_time_the_thread_did_not_run_is_not_a_held_lock():
    common.after(req(wall_ago=0.5, cpu_ago=0.01), ok=True)


def test_work_under_the_lock_over_200_ms_fails():
    with pytest.raises(AssertionError, match="held the write lock"):
        common.after(req(wall_ago=0.3, cpu_ago=0.25), ok=True)


def test_a_wait_under_the_lock_over_a_second_fails():
    with pytest.raises(AssertionError, match="held the write lock"):
        common.after(req(wall_ago=1.5, cpu_ago=0.01), ok=True)
