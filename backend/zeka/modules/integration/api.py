"""HTTP routes of the integration hub (tasks/todo.md, Task 37): API keys, webhooks and the apps page for the
administrator; the key routes under /api/v1/ that external systems call with ``Authorization: Bearer``. The exports
behind /api/v1/ are the same functions the screen and ``manage.py export`` call (``export.py``)."""
from __future__ import annotations

from datetime import datetime

from ...core.i18n import E, S_
from ...core.web import HTTPError, Response
from ...legacy.common import R
from ...legacy.store import audit, setting, set_setting
from . import domain, tokens, webhooks

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
    # the setting is overwritten, so the audit keeps what was saved (Checkpoint E, TM-E14)
    audit(req.db, req.user["id"], "apps_saved", "settings", (f"{len(items)} tiles: " + " ".join(i["url"] for i in items))[:1500])
    return {"apps": items, "all": items}


# ---------------------------------------------------------------- key routes (external systems)
def _since(req) -> datetime | None:
    try:
        return domain.moment(req.query.get("since"))                # the same reading as the screen and manage.py
    except ValueError:
        raise HTTPError(400, E("«since» ISO 8601 formatında vaxt olmalıdır, məsələn, 2026-12-01T00:00:00+04:00")) from None


def _v1(req, kind: str) -> Response:
    """The key routes go through the same export as the screen and manage.py (export.run, audited)."""
    from . import export
    try:
        name, ctype, body = export.run(req.db, kind, since=_since(req), cap=export.HTTP_CAP)
    except ValueError as ex:
        raise HTTPError(400, ex.args[0]) from None
    return Response(body, 200, ctype, [("Content-Disposition", f'attachment; filename="{name}"')])


@R("GET", "/api/v1/grades", scope="token:grades.read", slow=True)       # a long export: the slow slots (AR-E1)
def v1_grades(req):
    return _v1(req, "grades")


@R("GET", "/api/v1/attendance", scope="token:attendance.read", slow=True)
def v1_attendance(req):
    return _v1(req, "attendance")


@R("GET", "/api/v1/oneroster.zip", scope="token:registry.read", slow=True)
def v1_oneroster(req):
    return _v1(req, "oneroster")


@R("GET", "/api/v1/status-changes", scope="token:status.read")
def v1_status_changes(req):
    return _v1(req, "status-changes")
