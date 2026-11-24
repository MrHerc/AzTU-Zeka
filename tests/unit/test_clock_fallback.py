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


def test_baku_without_a_tz_database_keeps_its_summer_time_of_1996_to_2015(no_tz_database):
    """WF27F-4: a fixed +04 put the summers of 1996-2015 an hour early (an old export's --since, a migrated record)."""
    zone = clock._zone("Asia/Baku")
    at = lambda *a: datetime(*a, tzinfo=timezone.utc).astimezone(zone).replace(tzinfo=None)   # noqa: E731
    assert at(2015, 7, 1, 12) == datetime(2015, 7, 1, 17), "summer of 2015: +05"
    assert at(2010, 1, 15, 12) == datetime(2010, 1, 15, 16) and at(2016, 7, 1, 12) == datetime(2016, 7, 1, 16)
    assert at(2015, 3, 28, 23, 59) == datetime(2015, 3, 29, 3, 59) and at(2015, 3, 29, 0) == datetime(2015, 3, 29, 5)
    assert at(2015, 10, 24, 23, 59) == datetime(2015, 10, 25, 4, 59) and at(2015, 10, 25, 0) == datetime(2015, 10, 25, 4)
    assert at(1996, 3, 31, 1) == datetime(1996, 3, 31, 6), "1996 followed the EU's 01:00 UTC"
    assert datetime(2015, 7, 1, 17, tzinfo=zone).utcoffset() == timedelta(hours=5)


def test_the_fallback_equals_the_tz_database_from_1993_on():
    try:
        from zoneinfo import ZoneInfo
        real = ZoneInfo("Asia/Baku")
    except ZoneInfoNotFoundError:
        pytest.skip("no tz database here")
    mine = clock.BAKU
    t, end, wrong = datetime(1993, 1, 1, tzinfo=timezone.utc), datetime(2045, 1, 1, tzinfo=timezone.utc), []
    while t < end and len(wrong) < 5:
        if t.astimezone(real).replace(tzinfo=None) != t.astimezone(mine).replace(tzinfo=None):
            wrong.append(t)
        wall = t.astimezone(real).replace(tzinfo=None)
        for fold in (0, 1):
            if wall.replace(fold=fold, tzinfo=real).utcoffset() != wall.replace(fold=fold, tzinfo=mine).utcoffset():
                wrong.append((wall, fold))
        t += timedelta(hours=1)                    # every change is on a whole UTC hour
    assert wrong == []


def test_an_export_without_a_zone_is_refused_rather_than_in_the_host_s_time(monkeypatch):
    from zeka.modules.integration import export
    monkeypatch.setattr(clock, "ZONE", None)
    with pytest.raises(ZoneInfoNotFoundError):
        export._wall(datetime(2026, 11, 19, 6, tzinfo=timezone.utc))


def test_utc_needs_no_tz_database(no_tz_database):
    assert clock._zone("UTC") == clock._zone("Etc/UTC") == timezone.utc
