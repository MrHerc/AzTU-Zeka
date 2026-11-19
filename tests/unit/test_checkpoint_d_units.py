"""Checkpoint D: pure-logic regression tests by finding id (docs/review/checkpoint-d-2026-11-19.md). Each fails on the
code before the fixes (823bc4d)."""
import os
import time
from datetime import date, datetime, timezone

import pytest

from zeka.modules.exam import domain


@pytest.fixture
def computer_at_utc_plus_4():
    """The computer's own zone is UTC+4, given as a POSIX TZ string, so no zone database is needed."""
    before = os.environ.get("TZ")
    os.environ["TZ"] = "AZT-4"
    time.tzset()
    yield
    if before is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = before
    time.tzset()


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="time.tzset is POSIX only")
def test_cr12_without_a_zone_database_the_wall_time_is_the_computer_s_not_utc(computer_at_utc_plus_4):
    assert domain.to_utc(date(2026, 11, 19), "10:00", None) == datetime(2026, 11, 19, 6, 0, tzinfo=timezone.utc)
