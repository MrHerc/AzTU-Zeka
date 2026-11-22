"""The event log (tasks/todo.md, Task 39): who did what, when, in which module.

The request cycle (``legacy/common.py``) calls ``record`` for every signed-in request that changed something, for every
sign-in and for a session's first request of a day; the insight module counts the rows (active users, the accreditation
evidence). An event is written in the caller's transaction, with its day in ``active_days`` (Task 42).
"""
from __future__ import annotations

from datetime import datetime

from . import clock


def module_of(name: str) -> str:
    """A handler's module from its Python module: ``zeka.modules.exam.routes`` -> exam, ``zeka.legacy.r_services`` ->
    services."""
    parts = name.split(".")
    return parts[parts.index("modules") + 1] if "modules" in parts else parts[-1].removeprefix("r_")


def record(c, user_id: int | None, role: str, action: str, module: str, at: datetime | None = None) -> None:
    """``at``: the university's wall-clock time of the event (default now)."""
    t = (at or clock.local()).isoformat(timespec="seconds")
    c.execute("INSERT INTO events(user_id,role,action,module,created_at) VALUES(?,?,?,?,?)", (user_id, role, action, module, t))
    if user_id is not None:          # Task 42 (AR-F11): one row per person, role and day; the active-user tiles count these
        c.execute("INSERT OR IGNORE INTO active_days(day,role,user_id) VALUES(?,?,?)", (t[:10], role, user_id))
