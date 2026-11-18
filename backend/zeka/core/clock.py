"""The university's clock (tasks/todo.md, Task 5; plan A19).

``now()`` is the moment, timezone-aware UTC. ``local()`` is the naive wall-clock time in ``ZEKA_TZ`` (default
Asia/Baku), the form the legacy code stores. The server's own timezone never matters: a container in UTC and a
laptop in Los Angeles both see Baku time. Without a tz database (Windows without the tzdata package) ``ZONE`` is
None: demo mode falls back to the OS time, prod mode refuses to start (backend/run.py).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TZ_NAME = (os.environ.get("ZEKA_TZ") or "Asia/Baku").strip()


def _zone(name: str) -> ZoneInfo | None:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


ZONE = _zone(TZ_NAME)


def now() -> datetime:
    return datetime.now(timezone.utc)


def local() -> datetime:
    """Naive wall-clock time of the university."""
    if ZONE is None:
        return datetime.now()  # noqa: DTZ005  shortcut: OS time without a tz database, demo mode only
    return now().astimezone(ZONE).replace(tzinfo=None)
