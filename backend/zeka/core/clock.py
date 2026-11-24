"""The university's clock (tasks/todo.md, Task 5; plan A19).

``now()`` is the moment, timezone-aware UTC. ``local()`` is the naive wall-clock time in ``ZEKA_TZ`` (default
Asia/Baku), the form the legacy code stores. The server's own timezone never matters: a container in UTC and a
laptop in Los Angeles both see Baku time. Without a tz database (Windows without the tzdata package) a zone whose
offset no longer changes still works (``FIXED``); any other zone leaves ``ZONE`` None: ``local()`` raises ZoneInfoNotFoundError and the
server refuses to start in either mode (backend/run.py).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TZ_NAME = (os.environ.get("ZEKA_TZ") or "Asia/Baku").strip()
# Usable without a tz database: Asia/Baku has been UTC+04:00 all year since it dropped daylight saving time in 2016.
FIXED: dict[str, tzinfo] = {"Asia/Baku": timezone(timedelta(hours=4), "+04"), "UTC": timezone.utc, "Etc/UTC": timezone.utc}


def _zone(name: str) -> tzinfo | None:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return FIXED.get(name)


ZONE = _zone(TZ_NAME)


def now() -> datetime:
    return datetime.now(timezone.utc)


def local() -> datetime:
    """Naive wall-clock time of the university."""
    if ZONE is None:
        raise ZoneInfoNotFoundError(f"ZEKA_TZ={TZ_NAME}: no tz database entry (install the tzdata package)")
    return now().astimezone(ZONE).replace(tzinfo=None)
