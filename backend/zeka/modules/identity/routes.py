"""HTTP routes of the identity module (tasks/todo.md, Task 10).

A refused sign-in is returned as a response, not raised: the request's transaction must commit the failure count.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time

from ...core import perms
from ...core.security import LIMITS
from ...core.i18n import S
from ...core.web import HTTPError, json_resp, redirect
from ...legacy.common import (BASE_URL, R, ROLE_HOME, _own_commit, blocked_response, password_field, pub_user,
                             rotate_session, session_cookie, start_session)
from ...legacy.qr import qr_svg
from ...legacy.store import audit
from . import domain, privacy, repo, service, sso

_password, _blocked = password_field, blocked_response      # shared with the activation route (legacy.common)


@R("POST", "/api/auth/login", auth=False)
def login(req):
    b = req.json()
    login_name, password = b.text("login", 254), _password(b, "password")
    client = domain.client_key(req.ip)
    if LIMITS["password_fail"].blocked(client):        # checked before scrypt: a refused attempt costs nothing
        return _blocked(req, int(LIMITS["password_fail"].window))
    status, value = service.sign_in(req.db, login_name, password, req.ip)
    if status == "blocked":
        return _blocked(req, value)
    if status == "wrong":       # the same answer for an unknown account, a wrong password and a disabled account
        _own_commit(req)        # the failure count first: the limiter writes in a transaction of its own
        LIMITS["password_fail"].hit(client)
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


# ---------------------------------------------------------------- roles (Task 13)
@R("GET", "/api/me/roles")
def my_roles(req):
    return {"active": req.user["role"], "roles": repo.roles_of(req.db, req.user)}


@R("POST", "/api/me/role")
def switch_role(req):
    role = req.json().text("role", 40)
    if role not in {r["role"] for r in repo.roles_of(req.db, req.user)}:
        raise HTTPError(403, "Bu rol sizə verilməyib")
    primary = req.user["primary_role"]
    if role in domain.MFA_ROLES and primary not in domain.MFA_ROLES and not req.user["totp_enabled_at"]:
        raise HTTPError(403, "İşçi rolunda işləmək üçün əvvəlcə ikinci addımı qoşun")
    if role == req.user["role"]:
        return {"ok": True, "role": role, "home": ROLE_HOME.get(role, "/")}
    repo.set_session_role(req.db, req.user["session_id"], None if role == primary else role)
    audit(req.db, req.user["id"], "role_switched", "session", f"{req.user['role']} → {role}")
    return json_resp({"ok": True, "role": role, "home": ROLE_HOME.get(role, "/")}, headers=rotate_session(req))


@R("GET", "/api/admin/users/{id:int}/roles", perm="roles.grant")
def user_roles(req):
    return repo.roles_of(req.db, _target(req))


@R("POST", "/api/admin/users/{id:int}/roles", perm="roles.grant")
def grant_role(req):
    b = req.json()
    role, scope_type = b.text("role", 40), b.text("scope_type", 20) or None
    scope_id = b.integer("scope_id", None, lo=1)
    if role not in perms.ROLES:
        raise HTTPError(400, "Naməlum rol")
    if scope_type is not None and scope_type not in perms.SCOPE_TYPES or (scope_type is None) != (scope_id is None):
        raise HTTPError(400, "Əhatənin növü və identifikatoru birlikdə verilməlidir")
    u = _target(req)
    if u["id"] == req.user["id"]:                      # Checkpoint F (SA-F8): an administrator does not grant themselves a role
        raise HTTPError(403, "Özünüzə rol verə bilməzsiniz: bunu başqa administrator edir")
    if role == u["role"] and scope_type is None:
        raise HTTPError(409, "Bu, istifadəçinin əsas roludur")
    try:
        gid = repo.grant_role(req.db, u["id"], role, scope_type, scope_id, req.user["id"])
    except sqlite3.IntegrityError:
        raise HTTPError(409, "Bu rol artıq verilib") from None
    audit(req.db, req.user["id"], "role_granted", "user", f"{u['username']} · {role} · {scope_type or '-'}:{scope_id or '-'}")
    return {"id": gid}


@R("DELETE", "/api/admin/users/{id:int}/roles/{gid:int}", perm="roles.grant")
def revoke_role(req):
    u = _target(req)
    g = repo.grant(req.db, u["id"], req.params["gid"])
    if not g:
        raise HTTPError(404, "Rol tapılmadı")
    repo.drop_grant(req.db, g["id"])    # sessions acting in it fall back at once
    audit(req.db, req.user["id"], "role_revoked", "user", f"{u['username']} · {g['role']}")
    return {"ok": True}


# ---------------------------------------------------------------- single sign-on (Task 14)
SSO_COOKIE = "zeka_sso"           # binds a started sign-in to this browser: a callback link from elsewhere is refused


def _sso_cookie(value: str = "", expire: bool = False) -> tuple:
    attrs = "; Max-Age=0" if expire else f"; Max-Age={domain.SSO_PENDING}"
    if BASE_URL["value"].startswith("https://"):
        attrs += "; Secure"
    return ("Set-Cookie", f"{SSO_COOKIE}={value}; HttpOnly; SameSite=Lax; Path=/api/auth/sso{attrs}")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _begin(req, link_user_id: int | None) -> tuple[str, list]:
    """The provider's sign-in address for a new state, nonce and PKCE pair, and the browser cookie that goes with it."""
    cfg = sso.settings(req.db)
    if not cfg:
        raise HTTPError(404, "Vahid giriş qoşulmayıb")
    try:
        doc = sso.discover(cfg["issuer"])              # network first: no write transaction is open while it waits
    except sso.SSOError as ex:
        audit(req.db, None, "sso_refused", "session", f"discovery: {ex}"[:200])
        raise HTTPError(502, "Vahid giriş xidməti cavab vermir. Bir azdan yenidən cəhd edin.") from None
    verifier, challenge = domain.pkce_pair()
    state, nonce, browser = (secrets.token_urlsafe(32) for _ in range(3))
    repo.add_pending(req.db, state, _hash(browser), nonce, verifier, link_user_id, time.time())
    url = sso.authorization_url(cfg, doc, state, nonce, challenge, sso.redirect_uri(BASE_URL["value"]))
    return url, [_sso_cookie(browser)]


def _back(path: str, code: str, headers: list):
    return redirect(f"/#{path}?sso={code}", headers)


@R("GET", "/api/auth/sso/start", auth=False, slow=True)
def sso_start(req):
    if not LIMITS["sso"].hit(domain.client_key(req.ip)):
        return _back("/login", "failed", [])
    try:
        url, headers = _begin(req, None)
    except HTTPError as ex:                            # a browser navigation: back to the sign-in page, not JSON
        return _back("/login", "off" if ex.status == 404 else "failed", [])
    return redirect(url, headers)


@R("GET", "/api/auth/sso/callback", auth=False, slow=True)
def sso_callback(req):
    clear = [_sso_cookie(expire=True)]
    state = (req.query.get("state") or "")[:200]
    pending = repo.take_pending(req.db, state) if state else None
    _own_commit(req)                                   # spent at once, whatever happens next
    browser = req.cookies.get(SSO_COOKIE) or ""
    if not pending or not hmac.compare_digest(pending["browser_hash"], _hash(browser)) or \
            time.time() - pending["created_at"] > domain.SSO_PENDING:
        return _back("/login", "expired", clear)
    page = "/profile" if pending["link_user_id"] else "/login"
    cfg, code = sso.settings(req.db), (req.query.get("code") or "")[:2048]
    if not cfg:
        return _back(page, "off", clear)
    if req.query.get("error") or not code:            # the person cancelled, or the provider refused
        return _back(page, "cancelled", clear)
    try:
        claims = sso.exchange(cfg, sso.discover(cfg["issuer"]), code, pending["verifier"], pending["nonce"],
                              sso.redirect_uri(BASE_URL["value"]))
    except sso.SSOError as ex:
        audit(req.db, None, "sso_refused", "session", str(ex)[:200])
        return _back(page, "failed", clear)
    iss, sub, email = cfg["issuer"], claims["sub"], domain.verified_email(claims)
    if pending["link_user_id"]:                        # the owner links from a local session in this same browser
        if not req.user or req.user["id"] != pending["link_user_id"]:
            return _back(page, "expired", clear)
        ok = service.link_identity(req.db, req.user, req.user, iss, sub, email, "owner")
        return _back(page, "linked" if ok else "taken", clear)
    status, u = service.sso_account(req.db, cfg, claims)
    if status != "ok":
        return _back(page, "not_found", clear)
    repo.identity_seen(req.db, iss, sub, email)
    _, headers = start_session(req, u, "sso", scope=service.scope_after_sso(cfg, u, claims))
    return redirect("/", clear + headers)


@R("POST", "/api/auth/sso/link", slow=True)
def sso_link_start(req):
    if req.user.get("session_scope") != "full":
        raise HTTPError(403, "Əvvəlcə ikinci addımı tamamlayın")
    if service.has_staff_role(req.db, req.user) and not req.user.get("session_mfa"):
        raise HTTPError(403, "İşçi hesabını universitet hesabı ilə əlaqələndirmək üçün parol və ikinci addımla daxil olun")
    if not LIMITS["sso"].hit(domain.client_key(req.ip)):
        raise HTTPError(429, "Çox sayda sorğu. Bir az sonra yenidən cəhd edin.")
    try:
        url, headers = _begin(req, req.user["id"])
    except HTTPError as ex:                            # answered, not raised: the audit of a failed discovery commits
        return json_resp({"error": S(ex.message, req.lang)}, ex.status)
    return json_resp({"url": url}, headers=headers)


@R("GET", "/api/me/sso")
def my_sso(req):
    return [{k: x[k] for k in ("id", "iss", "email", "linked_at", "last_login")} for x in repo.identities_of(req.db, req.user["id"])]


@R("GET", "/api/admin/users/{id:int}/sso", roles=("admin",))
def user_sso(req):
    return repo.identities_of(req.db, _target(req)["id"])


@R("POST", "/api/admin/users/{id:int}/sso", roles=("admin",))
def admin_sso_link(req):
    sub = req.json().text("sub", 255)
    cfg = sso.settings(req.db)
    if not cfg:
        raise HTTPError(409, "Vahid giriş qoşulmayıb")
    if not sub:
        raise HTTPError(400, "Provayderdəki istifadəçi identifikatorunu (sub) yazın")
    if not service.link_identity(req.db, req.user, _target(req), cfg["issuer"], sub, None, "admin"):
        raise HTTPError(409, "Bu identifikator və ya hesab artıq əlaqələndirilib")
    return {"ok": True}


@R("DELETE", "/api/admin/users/{id:int}/sso/{iid:int}", roles=("admin",))
def admin_sso_unlink(req):
    u = _target(req)
    gone = repo.remove_identity(req.db, u["id"], req.params["iid"])
    if not gone:
        raise HTTPError(404, "Bağlantı tapılmadı")
    audit(req.db, req.user["id"], "sso_unlinked", "user", f"{u['username']} · {gone['iss']}")
    return {"ok": True}


# ---------------------------------------------------------------- privacy (Task 40)
@R("GET", "/api/privacy", auth=False)
def privacy_state(req):
    """The privacy notice's facts and the consent texts for anyone; a signed-in person's own choices and requests too."""
    return privacy.state(req.db, req.user)


@R("GET", "/api/me/export")
def my_export(req):
    """Everything the platform holds about the signed-in person (the data inventory's own rows), as a JSON file."""
    if not LIMITS["export"].hit(f"u{req.user['id']}"):
        raise HTTPError(429, "Məlumatlarınızı bir saat ərzində ən çox beş dəfə yükləyə bilərsiniz. Bir qədər sonra yenidən cəhd edin.")
    return json_resp(privacy.export(req.db, req.user),
                     headers=[("Content-Disposition", f'attachment; filename="zeka-export-{req.user["id"]}.json"')])


@R("POST", "/api/me/erase")
def my_erase(req):
    status, out = privacy.request_erase(req.db, req.user, req.json().text("reason", 1000))
    if status != "ok":
        raise HTTPError(409, out)
    return out


@R("GET", "/api/privacy/requests", perm="privacy.decide")
def privacy_requests(req):
    status = req.query.get("status") or None
    if status not in (None, "pending", "done", "rejected"):
        raise HTTPError(400, "Naməlum status")
    return {"items": privacy.requests(req.db, req.user, status)}


@R("POST", "/api/privacy/requests/{id:int}/decide", perm="privacy.decide")
def privacy_decide(req):
    b = req.json()
    approve = b.get("approve")
    if not isinstance(approve, bool):
        raise HTTPError(400, "Qərarı seçin: təsdiq və ya rədd")
    status, out = privacy.decide(req.db, req.user, req.params["id"], approve, b.text("note", 1000))
    if status == "missing":
        raise HTTPError(404, "Sorğu tapılmadı")
    if status != "ok":
        raise HTTPError(403 if status == "own" else 409, out)
    return out
