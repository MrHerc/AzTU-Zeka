"""HTTP routes of the integration module (tasks/todo.md, Task 16): the admin import screen, activation codes, activation;
Task 37: the exports and the "Tələbə-məzun" change list, which call ``export`` only.

The screen takes at most 20 000 rows; a larger file goes through ``manage.py import``. A refused activation is
returned, not raised, so its failure count commits (as a refused sign-in, Task 10).
"""
from __future__ import annotations

import base64
import binascii
import csv
import io

from ...core.i18n import E, S
from ...core.web import HTTPError, Response, json_resp
from ...legacy.common import R, ROLE_HOME, blocked_response, password_field, pub_user, serves, start_session
from ..directory import service as directory
from ..identity import service as identity
from . import domain, export, importer, tables


@R("POST", "/api/admin/import", roles=("admin",))
def run_import(req):
    b = req.json()
    try:
        data = base64.b64decode(b.text("content_b64"), validate=True)
    except (ValueError, binascii.Error):
        raise HTTPError(400, "Fayl oxunmadı") from None
    try:
        return importer.run(req.db, b.text("kind", 40), b.text("source", 64), b.text("filename", 160), data,
                            dry_run=b.get("dry_run") is not False, prefer_source=b.get("prefer_source") is True,
                            user_id=req.user["id"], max_rows=importer.MAX_SCREEN_ROWS)
    except tables.TableError as ex:
        raise HTTPError(400, str(ex)) from None


@R("POST", "/api/admin/activation-codes", roles=("admin",))
def activation_codes(req):
    """New codes for a faculty's students without a password, as CSV for the dean's office; shown once."""
    fid = req.json().integer("faculty_id", 0, lo=1)
    if not directory.get(req.db, "faculties", fid):
        raise HTTPError(404, "Tapılmadı")
    items = importer.issue_codes(req.db, req.user["id"], fid)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["student_no", "full_name", "group", "username", "code", "expires_at"])
    w.writerows([[domain.csv_cell(x[k]) for k in ("student_no", "full_name", "group", "username", "code", "expires_at")] for x in items])
    return {"count": len(items), "csv": out.getvalue()}


@R("POST", "/api/auth/activate", auth=False)
def activate(req):
    b = req.json()
    status, value = importer.activate(req.db, b.text("student_no", 64), b.text("code", 40), password_field(b, "password"), req.ip)
    if status == "blocked":
        return blocked_response(req, value)
    if status == "wrong":            # an unknown code, another student's code, a spent or expired one: the same answer
        return json_resp({"error": S("Tələbə bileti nömrəsi və ya aktivləşdirmə kodu yanlışdır", req.lang)}, 401)
    if status == "weak":
        raise HTTPError(400, value)
    scope = identity.scope_after_password(value)                       # what a password sign-in of this account needs
    _, headers = start_session(req, value, "aktivləşdirmə", scope=scope)
    return json_resp({"user": {**pub_user(value), "scope": scope}, "home": ROLE_HOME.get(value["role"], "/")}, headers=headers)


# ---------------------------------------------------------------- exports (Task 37)
def _since(req):
    try:
        return domain.moment(req.query.get("since"))
    except ValueError:
        raise HTTPError(400, E("«{field}» sahəsində vaxt ISO 8601 formatında olmalıdır, məsələn 2026-12-01T00:00:00+04:00",
                               field="since")) from None


@R("GET", "/api/integration/export/{kind}", perm="integration.manage")
def export_file(req):
    """A file: ``grades`` and ``attendance`` (``?since=``), ``oneroster`` (zip), ``registry`` (``?registry=students|users``,
    ``?columns=a,b``), ``status-changes`` (``?since=``). The same service as ``manage.py export``."""
    kind = req.params["kind"]
    if kind not in export.KINDS:
        raise HTTPError(404, "Tapılmadı")
    columns = [x.strip() for x in (req.query.get("columns") or "").split(",") if x.strip()]
    try:
        name, ctype, body = export.run(req.db, kind, since=_since(req), registry=req.query.get("registry") or "students",
                                       columns=columns or None, user_id=req.user["id"])
    except ValueError as ex:
        raise HTTPError(400, ex.args[0]) from None
    return Response(body, 200, ctype, [("Content-Disposition", f'attachment; filename="{name}"'), ("Cache-Control", "private, no-store")])


@R("GET", "/api/integration/status-changes", perm="students.status.read")
def status_changes(req):
    """Status orders entered after ``?since=``, each with ``deadline``, ``days_left`` and ``reported_at``."""
    items = export.status_changes(req.db, _since(req))
    if req.user["role"] == "office":                   # a dean's office: its own faculty's students
        items = [x for x in items if serves(req.db, req.user, x["student_id"])]
    return {"items": items, "days": export.REPORT_DAYS}


@R("POST", "/api/integration/status-changes/{id:int}/reported", perm="students.status")
def status_reported(req):
    hit = export.mark_reported(req.db, req.user, req.params["id"])
    if not hit:
        raise HTTPError(404, "Tapılmadı")
    return hit
