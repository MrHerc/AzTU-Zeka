"""HTTP routes of the identity module (tasks/todo.md, Task 10).

A refused sign-in is returned as a response, not raised: the request's transaction must commit the failure count.
"""
from __future__ import annotations

from ...core.i18n import S
from ...core.web import HTTPError, json_resp
from ...legacy.common import R, ROLE_HOME, pub_user, rotate_session, session_cookie, start_session
from ...legacy.qr import qr_svg
from ...legacy.store import audit
from . import domain, repo, service

PASSWORD_INPUT_MAX = 1024          # longer input is refused before any hashing


def _password(body, key: str) -> str:
    """The password exactly as typed: no trimming (spaces are allowed characters)."""
    v = body.get(key)
    if not isinstance(v, str) or len(v) > PASSWORD_INPUT_MAX:
        raise HTTPError(400, "Parol düzgün göndərilməyib")
    return v


def _blocked(req, seconds: int):
    return json_resp({"error": S("Çox sayda uğursuz cəhd. {n} saniyədən sonra yenidən cəhd edin.", req.lang, n=seconds)},
                     429, headers=[("Retry-After", str(seconds))])


@R("POST", "/api/auth/login", auth=False)
def login(req):
    b = req.json()
    status, value = service.sign_in(req.db, b.text("login", 254), _password(b, "password"), req.ip)
    if status == "blocked":
        return _blocked(req, value)
    if status == "wrong":       # the same answer for an unknown account, a wrong password and a disabled account
        return json_resp({"error": S("İstifadəçi adı və ya parol yanlışdır", req.lang)}, 401)
    scope = service.scope_after_password(value)       # the second factor, or its enrolment, comes next for staff
    _, headers = start_session(req, value, "parol", scope=scope)
    return json_resp({"user": {**pub_user(value), "scope": scope}, "home": ROLE_HOME.get(value["role"], "/")}, headers=headers)


@R("POST", "/api/auth/password")
def change_password(req):
    b = req.json()
    status, value = service.change_password(req.db, req.user, _password(b, "current"), _password(b, "new"), req.ip)
    if status == "blocked":
        return _blocked(req, value)
    if status == "wrong":
        return json_resp({"error": S("Hazırkı parol yanlışdır", req.lang)}, 403)
    if status == "weak":
        raise HTTPError(400, value)
    repo.end_sessions(req.db, req.user["id"], keep=req.user["session_id"])    # other devices sign in again
    user = {**pub_user(repo.user(req.db, req.user["id"])), "scope": req.user.get("session_scope") or "full"}   # enrolment may follow
    return json_resp({"ok": True, "user": user}, headers=rotate_session(req))


@R("GET", "/api/me/sessions")
def my_sessions(req):
    return [{**s, "current": s["id"] == req.user.get("session_id")} for s in repo.sessions_of(req.db, req.user["id"])]


@R("DELETE", "/api/me/sessions/{id:int}")
def end_session(req):
    if not repo.end_session(req.db, req.user["id"], req.params["id"]):       # only one's own sessions
        raise HTTPError(404, "Sessiya tapılmadı")
    audit(req.db, req.user["id"], "session_ended", "session", str(req.params["id"]))
    current = req.params["id"] == req.user.get("session_id")
    return json_resp({"ok": True, "current": current}, headers=[session_cookie(expire=True)] if current else [])


@R("POST", "/api/me/sessions/end-others")
def end_other_sessions(req):
    n = repo.end_sessions(req.db, req.user["id"], keep=req.user.get("session_id"))
    audit(req.db, req.user["id"], "sessions_ended", "session", str(n))
    return {"ended": n}


def _target(req):
    u = repo.user(req.db, req.params["id"])
    if not u:
        raise HTTPError(404, "İstifadəçi tapılmadı")
    return u


@R("POST", "/api/admin/users/{id:int}/temp-password", roles=("admin",))
def temporary_password(req):
    u = _target(req)
    return {"username": u["username"], "password": service.issue_temporary(req.db, req.user, u),
            "min_length": domain.MIN_ALONE}


@R("POST", "/api/admin/users/{id:int}/unlock", roles=("admin",))
def unlock(req):
    reason = req.json().text("reason", 500)
    if len(reason) < 3:
        raise HTTPError(400, "Kilidin açılma səbəbini yazın")
    u = _target(req)
    service.unlock(req.db, req.user, u, reason)
    return {"ok": True}


# ---------------------------------------------------------------- second factor (Task 12)
def _code(req) -> str:
    return req.json().text("code", 40)


@R("POST", "/api/auth/mfa/verify")
def mfa_verify(req):
    if req.user.get("session_scope") != "mfa":
        raise HTTPError(409, "İkinci addım tələb olunmur")
    status, value = service.verify_second_factor(req.db, req.user, req.user["session_id"], _code(req), req.ip)
    if status == "blocked":
        return _blocked(req, value)
    if status == "cancelled":
        return json_resp({"error": S("Çox sayda yanlış kod: giriş ləğv olundu. Parolu yenidən daxil edin.", req.lang)}, 401,
                         headers=[session_cookie(expire=True)])
    if status == "wrong":
        return json_resp({"error": S("Kod yanlışdır. Qalan cəhd: {n}", req.lang, n=value)}, 401)
    left = repo.recovery_left(req.db, req.user["id"]) if value == "recovery" else None
    return json_resp({"ok": True, "user": {**pub_user(repo.user(req.db, req.user["id"])), "scope": "full"}, "recovery_left": left},
                     headers=rotate_session(req))          # a new id once the second factor is in


@R("POST", "/api/auth/mfa/enroll")
def mfa_enroll(req):
    out = service.start_enrollment(req.db, req.user)
    if out is None:
        raise HTTPError(409, "İkinci addım artıq qoşulub")
    return {**out, "qr": qr_svg(out["uri"], scale=5)}


@R("POST", "/api/auth/mfa/confirm")
def mfa_confirm(req):
    status, value = service.confirm_enrollment(req.db, req.user, req.user.get("session_id"), _code(req), req.ip)
    if status == "blocked":
        return _blocked(req, value)
    if status == "none":
        raise HTTPError(409, "Əvvəlcə QR kodu yaradın")
    if status == "wrong":
        return json_resp({"error": S("Kod yanlışdır. Tətbiqdəki ən son kodu yazın.", req.lang)}, 401)
    headers = rotate_session(req) if req.user.get("session_id") else []
    return json_resp({"ok": True, "recovery_codes": value, "user": {**pub_user(repo.user(req.db, req.user["id"])), "scope": "full"}},
                     headers=headers)


@R("POST", "/api/auth/mfa/disable")
def mfa_disable(req):
    status = service.disable_second_factor(req.db, req.user, _code(req), req.ip)
    if status == "forbidden":
        raise HTTPError(403, "İşçi hesabında ikinci addım məcburidir")
    if status == "none":
        raise HTTPError(409, "İkinci addım qoşulmayıb")
    if status == "wrong":
        return json_resp({"error": S("Kod yanlışdır. Tətbiqdəki ən son kodu yazın.", req.lang)}, 401)
    return {"ok": True}


@R("POST", "/api/admin/users/{id:int}/mfa-reset", roles=("admin",))
def mfa_reset(req):
    reason = req.json().text("reason", 500)
    if len(reason) < 3:
        raise HTTPError(400, "Sıfırlamanın səbəbini yazın")
    service.reset_second_factor(req.db, req.user, _target(req), reason)
    return {"ok": True}
