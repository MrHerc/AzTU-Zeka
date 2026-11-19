"""HTTP routes of the integration hub (tasks/todo.md, Task 37): API keys, webhooks and the apps page for the
administrator; the key routes under /api/v1/ that external systems call with ``Authorization: Bearer``. The exports
behind /api/v1/ are the same functions the screen and ``manage.py export`` call (``export.py``)."""
from __future__ import annotations

from datetime import datetime

from ...core import clock
from ...core.i18n import E, S_
from ...core.web import HTTPError, Response
from ...legacy.common import R
from ...legacy.store import audit, setting, set_setting
from . import tokens, webhooks

APP_ROLES = ("student", "teacher", "dept_head", "office", "academic_office", "leader", "admin")
APP_ICONS = ("external", "book", "globe", "mail", "calendar", "wallet", "building", "cap", "grid", "link")


NOT_FOUND = S_("Tapılmadı")


def _answer(status, value, missing=NOT_FOUND):
    if status == "missing":
        raise HTTPError(404, missing)
    if status == "invalid":
        raise HTTPError(400, value)
    return value


@R("GET", "/api/integration/keys", perm="integration.manage")
def keys(req):
    return tokens.listed(req.db)


@R("POST", "/api/integration/keys", perm="integration.manage")
def key_create(req):
    return _answer(*tokens.create(req.db, req.user, req.json()))


@R("POST", "/api/integration/keys/{id:int}/revoke", perm="integration.manage")
def key_revoke(req):
    return _answer(*tokens.revoke(req.db, req.user, req.params["id"]))


@R("GET", "/api/integration/webhooks", perm="integration.manage")
def hooks(req):
    return webhooks.listed(req.db)


@R("POST", "/api/integration/webhooks", perm="integration.manage")
def hook_create(req):
    return _answer(*webhooks.create(req.db, req.user, req.json()))


@R("POST", "/api/integration/webhooks/{id:int}/deactivate", perm="integration.manage")
def hook_deactivate(req):
    return _answer(*webhooks.deactivate(req.db, req.user, req.params["id"]))


@R("GET", "/api/integration/webhooks/{id:int}/deliveries", perm="integration.manage")
def hook_deliveries(req):
    return webhooks.deliveries(req.db, req.params["id"])


# ---------------------------------------------------------------- the apps page
def apps_input(body) -> tuple[list, dict | None]:
    items = body.array("apps")
    out = []
    if len(items) > 30:
        return [], E("Ən çox 30 tətbiq")
    for x in items:
        if not isinstance(x, dict):
            return [], E("Tətbiq düzgün deyil")
        title, url = " ".join(str(x.get("title") or "").split()), str(x.get("url") or "").strip()
        roles = x.get("roles") if isinstance(x.get("roles"), list) else []
        if not 2 <= len(title) <= 60 or not url.startswith("https://") or len(url) > 300:
            return [], E("Hər tətbiqin adı (2–60 simvol) və https:// ünvanı olmalıdır")
        if not roles or not all(r in APP_ROLES for r in roles):
            return [], E("Tətbiqin rolları: {roles}", roles=", ".join(APP_ROLES))
        out.append({"title": title, "url": url, "roles": sorted(set(roles)), "icon": x.get("icon") if x.get("icon") in APP_ICONS else "external",
                    "note": " ".join(str(x.get("note") or "").split())[:120]})
    return out, None


@R("GET", "/api/apps")
def apps(req):
    """The tiles of the signed-in role (an administrator also gets every tile to edit)."""
    every = setting(req.db, "apps") or []
    return {"apps": [a for a in every if req.user["role"] in a["roles"]], "all": every if req.user["role"] == "admin" else None}


@R("PUT", "/api/apps", perm="integration.manage")
def apps_save(req):
    items, problem = apps_input(req.json())
    if problem:
        raise HTTPError(400, problem)
    set_setting(req.db, "apps", items)
    audit(req.db, req.user["id"], "apps_saved", "settings", f"{len(items)} tiles")
    return {"apps": items, "all": items}


# ---------------------------------------------------------------- key routes (external systems)
def _since(req) -> datetime | None:
    raw = (req.query.get("since") or "").strip()
    if not raw:
        return None
    try:
        t = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPError(400, E("«since» ISO 8601 vaxtı olmalıdır, məsələn 2026-12-01T00:00:00+04:00")) from None
    return t if t.tzinfo else t.replace(tzinfo=clock.ZONE)


def _csv(text: str, name: str) -> Response:
    return Response(text, 200, "text/csv; charset=utf-8", [("Content-Disposition", f'attachment; filename="{name}"')])


@R("GET", "/api/v1/grades", scope="token:grades.read")
def v1_grades(req):
    from . import export
    return _csv(export.grades_csv(req.db, _since(req)), "grades.csv")


@R("GET", "/api/v1/attendance", scope="token:attendance.read")
def v1_attendance(req):
    from . import export
    return _csv(export.attendance_csv(req.db, _since(req)), "attendance.csv")


@R("GET", "/api/v1/oneroster.zip", scope="token:registry.read")
def v1_oneroster(req):
    from . import export
    return Response(export.oneroster_zip(req.db), 200, "application/zip", [("Content-Disposition", 'attachment; filename="oneroster.zip"')])


@R("GET", "/api/v1/status-changes", scope="token:status.read")
def v1_status_changes(req):
    from . import export
    return export.status_changes(req.db, _since(req))
