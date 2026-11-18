"""HTTP routes of the integration module (tasks/todo.md, Task 16): the admin import screen, activation codes, activation.

The screen takes at most 20 000 rows; a larger file goes through ``manage.py import``. A refused activation is
returned, not raised, so its failure count commits (as a refused sign-in, Task 10).
"""
from __future__ import annotations

import base64
import binascii
import csv
import io

from ...core.i18n import S
from ...core.web import HTTPError, json_resp
from ...legacy.common import R, ROLE_HOME, pub_user, start_session
from ..directory import repo as directory
from ..identity.routes import _blocked, _password
from . import importer, tables


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
    w.writerows([[x["student_no"], x["full_name"], x["group"], x["username"], x["code"], x["expires_at"]] for x in items])
    return {"count": len(items), "csv": out.getvalue()}


@R("POST", "/api/auth/activate", auth=False)
def activate(req):
    b = req.json()
    status, value = importer.activate(req.db, b.text("student_no", 64), b.text("code", 40), _password(b, "password"), req.ip)
    if status == "blocked":
        return _blocked(req, value)
    if status == "wrong":            # an unknown code, another student's code, a spent or expired one: the same answer
        return json_resp({"error": S("Tələbə bileti nömrəsi və ya aktivləşdirmə kodu yanlışdır", req.lang)}, 401)
    if status == "weak":
        raise HTTPError(400, value)
    _, headers = start_session(req, value, "aktivləşdirmə")
    return json_resp({"user": pub_user(value), "home": ROLE_HOME.get(value["role"], "/")}, headers=headers)
