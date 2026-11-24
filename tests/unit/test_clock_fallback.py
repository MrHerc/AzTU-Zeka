"""The university clock without a tz database (Windows without the tzdata package; CI windows-latest, 2026-11-24)."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfoNotFoundError

import pytest

from zeka.core import clock


@pytest.fixture
def no_tz_database(monkeypatch):
    def missing(name):
        raise ZoneInfoNotFoundError(f"No time zone found with key {name}")
    monkeypatch.setattr(clock, "ZoneInfo", missing)


def test_baku_keeps_its_fixed_offset_without_a_tz_database(no_tz_database, monkeypatch):
    zone = clock._zone("Asia/Baku")
    assert zone is not None and zone.utcoffset(None) == timedelta(hours=4)
    monkeypatch.setattr(clock, "ZONE", zone)
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 7, 1, 20, 30, tzinfo=timezone.utc))   # summer: no DST since 2016
    assert clock.local() == datetime(2026, 7, 2, 0, 30)


def test_a_zone_with_daylight_saving_time_is_refused_clearly(no_tz_database, monkeypatch):
    assert clock._zone("Europe/Berlin") is None
    monkeypatch.setattr(clock, "ZONE", None)
    monkeypatch.setattr(clock, "TZ_NAME", "Europe/Berlin")
    with pytest.raises(ZoneInfoNotFoundError, match="ZEKA_TZ=Europe/Berlin.*tzdata"):
        clock.local()


def test_with_a_tz_database_baku_is_the_database_zone():
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo("Asia/Baku")
    except ZoneInfoNotFoundError:
        pytest.skip("no tz database here")
    assert type(clock._zone("Asia/Baku")).__name__ == "ZoneInfo"
