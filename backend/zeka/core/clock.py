"""The university's clock (tasks/todo.md, Task 5; plan A19).

``now()`` is the moment, timezone-aware UTC. ``local()`` is the naive wall-clock time in ``ZEKA_TZ`` (default
Asia/Baku), the form the legacy code stores. The server's own timezone never matters: a container in UTC and a
laptop in Los Angeles both see Baku time. Without a tz database (Windows without the tzdata package) Asia/Baku and UTC
still work (``FIXED``); any other zone leaves ``ZONE`` None: ``local()`` raises ZoneInfoNotFoundError and the server
refuses to start in either mode (backend/run.py).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TZ_NAME = (os.environ.get("ZEKA_TZ") or "Asia/Baku").strip()
_H4, _H5, _H1 = timedelta(hours=4), timedelta(hours=5), timedelta(hours=1)


def _last_sunday(year: int, month: int, hour: int) -> datetime:          # March and October have 31 days
    d = datetime(year, month, 31, hour)
    return d - timedelta(days=(d.weekday() + 1) % 7)


class _Baku(tzinfo):
    """Asia/Baku as the tz database has it since 1993 (WF27F-4): +04, and +05 from the last Sunday of March to the last
    Sunday of October in 1996 (the EU's 01:00 UTC) and 1997-2015 (00:00 UTC); no summer time since 2016.
    shortcut: before 1993 Baku was +03/+04 under the Soviet rules; no record of this system is that old."""

    def _summer(self, year: int) -> tuple[datetime, datetime] | None:          # naive UTC
        if not 1996 <= year <= 2015:
            return None
        h = 1 if year == 1996 else 0
        return _last_sunday(year, 3, h), _last_sunday(year, 10, h)

    def fromutc(self, dt: datetime) -> datetime:
        u = dt.replace(tzinfo=None)
        s = self._summer(u.year)
        return (u + (_H5 if s and s[0] <= u < s[1] else _H4)).replace(tzinfo=self)

    def utcoffset(self, dt: datetime | None) -> timedelta:
        if dt is None or not (s := self._summer(dt.year)):
            return _H4
        w, start, end = dt.replace(tzinfo=None, fold=0), s[0] + _H4, s[1] + _H5   # the wall clock skips, then repeats an hour
        lo, hi = (start, end - _H1) if dt.fold else (start + _H1, end)              # PEP 495: fold=1 is the later reading
        return _H5 if lo <= w < hi else _H4

    def dst(self, dt: datetime | None) -> timedelta:
        return self.utcoffset(dt) - _H4

    def tzname(self, dt: datetime | None) -> str:
        return "+05" if self.dst(dt) else "+04"

    def __repr__(self) -> str:
        return "clock.BAKU"


BAKU = _Baku()
FIXED: dict[str, tzinfo] = {"Asia/Baku": BAKU, "UTC": timezone.utc, "Etc/UTC": timezone.utc}


def _zone(name: str) -> tzinfo | None:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return FIXED.get(name)


ZONE = _zone(TZ_NAME)


def zone() -> tzinfo:
    """The university's zone; ZoneInfoNotFoundError when ZEKA_TZ has no tz database entry (never the host's own time)."""
    if ZONE is None:
        raise ZoneInfoNotFoundError(f"ZEKA_TZ={TZ_NAME}: no tz database entry (install the tzdata package)")
    return ZONE


def now() -> datetime:
    return datetime.now(timezone.utc)


def local() -> datetime:
    """Naive wall-clock time of the university."""
    return now().astimezone(zone()).replace(tzinfo=None)
