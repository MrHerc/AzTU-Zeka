"""The event log (tasks/todo.md, Task 39): who did what, when, in which module.

The request cycle (``legacy/common.py``) calls ``record`` for every signed-in request that changed something, for every
sign-in and for a session's first request of a day; the insight module counts the rows (active users, the accreditation
evidence). An event is written in the caller's transaction.
"""
from __future__ import annotations

from . import clock


def module_of(name: str) -> str:
    """A handler's module from its Python module: ``zeka.modules.exam.routes`` -> exam, ``zeka.legacy.r_services`` ->
    services."""
    parts = name.split(".")
    return parts[parts.index("modules") + 1] if "modules" in parts else parts[-1].removeprefix("r_")


def record(c, user_id: int | None, role: str, action: str, module: str) -> None:
    c.execute("INSERT INTO events(user_id,role,action,module,created_at) VALUES(?,?,?,?,?)",
              (user_id, role, action, module, clock.local().isoformat(timespec="seconds")))
