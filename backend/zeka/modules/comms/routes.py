"""HTTP routes of the e-mail settings (tasks/todo.md, Task 36, slice 2): each person turns e-mail on or off per kind."""
from __future__ import annotations

from ...core.web import HTTPError
from ...legacy.common import R
from . import service


@R("GET", "/api/me/notifications")
def my_prefs(req):
    return service.prefs(req.db, req.user)


@R("PUT", "/api/me/notifications")
def set_my_prefs(req):
    status, value = service.set_prefs(req.db, req.user, req.json())
    if status != "ok":
        raise HTTPError(400, value)
    return value
