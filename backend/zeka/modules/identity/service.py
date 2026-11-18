"""Sign-in, password change and the administrator's password actions (tasks/todo.md, Task 10).

Every sign-in attempt that is not blocked costs exactly one scrypt, also for an unknown account or an account without
a password, so the answer and its timing do not reveal whether an account exists. scrypt always runs before the first
write of the request: no write transaction is open while it computes.
"""
from __future__ import annotations

import math
import time
from functools import lru_cache
from pathlib import Path

from ...legacy.store import ROOT, audit
from . import domain, repo

BLOCKLIST = ROOT / "content" / "password-blocklist.txt"
CONTEXT = ("aztu", "zəka", "zeka", "texniki", "universitet", "azerbaijan", "azərbaycan")


@lru_cache(maxsize=1)
def blocklist(path: Path = BLOCKLIST) -> frozenset[str]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return frozenset(domain.normalize(x).strip().lower() for x in lines if x.strip() and not x.startswith("#"))


@lru_cache(maxsize=1)
def _dummy() -> str:
    """Hash checked for unknown accounts: same cost, never matches (its password is thrown away)."""
    return domain.hash_password(domain.temporary_password() + domain.temporary_password())


def sign_in(c, login: str, password: str, ip: str, t: float | None = None):
    """('ok', user) | ('blocked', seconds to wait) | ('wrong', None)."""
    t = time.time() if t is None else t
    typed, client = login.strip().lower()[:254], domain.client_key(ip)
    u = repo.find_login(c, typed) if typed else None
    account = u["username"] if u else typed     # one counter per account, whether it was typed as name or e-mail
    wait = max(repo.block_wait(c, account, client, t), repo.lock_wait(u))
    if wait:                                   # checked before scrypt; a refused attempt is not counted
        return "blocked", math.ceil(wait)
    ok = domain.verify(password, (u["password_hash"] if u else None) or _dummy())
    if not (ok and u and u["password_hash"] and u["status"] == "active"):
        if repo.record_failure(c, account, client, t):
            audit(c, u["id"] if u else None, "login_blocked", "user", f"{account} · {client}")
        if u and repo.account_failure(c, u["id"]):
            audit(c, u["id"], "account_locked", "user", account)
        return "wrong", None
    new_hash = domain.hash_password(password) if domain.needs_rehash(u["password_hash"]) else None   # before the writes
    repo.signed_in(c, account, client, u["id"], new_hash, complete=scope_after_password(u) != "mfa")
    return "ok", repo.user(c, u["id"])


def context_words(u) -> list[str]:
    return [u["username"], (u["email"] or "").split("@")[0], *(u["full_name"] or "").split(), *CONTEXT]


def change_password(c, u, current: str, new: str, ip: str, t: float | None = None):
    """('ok', None) | ('blocked', seconds) | ('wrong', None) | ('weak', reason)."""
    t = time.time() if t is None else t
    account, client = u["username"], domain.client_key(ip)
    wait = repo.block_wait(c, account, client, t)
    if wait:
        return "blocked", math.ceil(wait)
    problem = domain.policy_problem(new, mfa=bool(u["totp_enabled_at"]), context=context_words(u), blocklist=blocklist())
    if u["password_hash"] and not domain.verify(current, u["password_hash"]):
        if repo.record_failure(c, account, client, t):
            audit(c, u["id"], "login_blocked", "user", f"{account} · {client}")
        return "wrong", None
    if problem:
        return "weak", problem
    repo.set_password(c, u["id"], domain.hash_password(new), must_change=False)
    audit(c, u["id"], "password_changed", "user", u["username"])
    return "ok", None


def issue_temporary(c, admin, target) -> str:
    """A one-time password the administrator hands over; the account must change it at its next sign-in."""
    password = domain.temporary_password()
    repo.set_password(c, target["id"], domain.hash_password(password), must_change=True)
    repo.unlock(c, target)
    repo.end_sessions(c, target["id"])                  # whoever was signed in with the old password is out
    audit(c, admin["id"], "temp_password", "user", target["username"])
    return password


def end_all_sessions(c, uid: int) -> int:
    """For other modules: the account signs in again (a changed role, a deactivated account)."""
    return repo.end_sessions(c, uid)


def unlock(c, admin, target, reason: str):
    repo.unlock(c, target)
    audit(c, admin["id"], "account_unlocked", "user", f"{target['username']} · {reason}")


# ---------------------------------------------------------------- second factor (Task 12)
def scope_after_password(u) -> str:
    """What a session reaches right after the right password: the second-factor step, its enrolment, or everything."""
    if u["totp_enabled_at"]:
        return "mfa"
    return "mfa_enroll" if u["role"] in domain.MFA_ROLES else "full"


def _count_failure(c, u, ip: str, t: float):
    account, client = u["username"], domain.client_key(ip)
    if repo.record_failure(c, account, client, t):            # the same counters as wrong passwords (Task 10)
        audit(c, u["id"], "login_blocked", "user", f"{account} · {client}")
    if repo.account_failure(c, u["id"]):
        audit(c, u["id"], "account_locked", "user", account)


def verify_second_factor(c, u, session_id: int, code: str, ip: str, t: float | None = None):
    """('ok', how) | ('blocked', seconds) | ('wrong', attempts left) | ('cancelled', None)."""
    t = time.time() if t is None else t
    wait = repo.block_wait(c, u["username"], domain.client_key(ip), t)
    if wait:
        return "blocked", math.ceil(wait)
    if domain.is_recovery_code(code):
        ok, how = repo.use_recovery_code(c, u["id"], domain.recovery_hash(code)), "recovery"
    else:
        step = domain.totp_match(u["totp_secret"] or "", code, t, u["totp_last"]) if u["totp_secret"] else None
        ok, how = step is not None and repo.accept_step(c, u["id"], step), "totp"
    if ok:
        repo.set_session_scope(c, session_id, "full")
        repo.clear_failures(c, u["username"], domain.client_key(ip), u["id"])     # the sign-in is complete only now
        audit(c, u["id"], "mfa_passed", "session", how)
        return "ok", how
    _count_failure(c, u, ip, t)
    failures = repo.mfa_failure(c, session_id)
    if failures >= domain.MFA_ATTEMPTS:                       # the pending sign-in ends: the password step starts again
        repo.end_session(c, u["id"], session_id)
        audit(c, u["id"], "mfa_cancelled", "session", str(failures))
        return "cancelled", None
    return "wrong", domain.MFA_ATTEMPTS - failures


def start_enrollment(c, u) -> dict | None:
    """A new secret, kept until it is confirmed with a code; None when a second factor is already active."""
    if u["totp_enabled_at"]:
        return None
    secret = domain.new_totp_secret()
    repo.start_totp(c, u["id"], secret)
    return {"secret": secret, "uri": domain.otpauth_uri(secret, u["username"])}


def confirm_enrollment(c, u, session_id: int | None, code: str, ip: str, t: float | None = None):
    """('ok', recovery codes) | ('none', None) | ('blocked', seconds) | ('wrong', None)."""
    t = time.time() if t is None else t
    if not u["totp_secret"] or u["totp_enabled_at"]:
        return "none", None
    wait = repo.block_wait(c, u["username"], domain.client_key(ip), t)
    if wait:
        return "blocked", math.ceil(wait)
    step = domain.totp_match(u["totp_secret"], code, t, None)
    if step is None:
        _count_failure(c, u, ip, t)
        return "wrong", None
    codes = domain.recovery_codes()
    repo.enable_totp(c, u["id"], step, [domain.recovery_hash(x) for x in codes])
    if session_id:
        repo.set_session_scope(c, session_id, "full")
    audit(c, u["id"], "mfa_enabled", "user", u["username"])
    return "ok", codes


def disable_second_factor(c, u, code: str, ip: str, t: float | None = None) -> str:
    """Students only (staff must keep one): 'ok' | 'forbidden' | 'wrong' | 'none'."""
    t = time.time() if t is None else t
    if u["role"] in domain.MFA_ROLES:
        return "forbidden"
    if not u["totp_enabled_at"]:
        return "none"
    step = domain.totp_match(u["totp_secret"], code, t, u["totp_last"])
    if step is None or not repo.accept_step(c, u["id"], step):
        _count_failure(c, u, ip, t)
        return "wrong"
    repo.reset_totp(c, u["id"])
    audit(c, u["id"], "mfa_disabled", "user", u["username"])
    return "ok"


def reset_second_factor(c, admin, target, reason: str):
    """A lost device: the account enrols again at its next sign-in; every session it has ends."""
    repo.reset_totp(c, target["id"])
    repo.end_sessions(c, target["id"])
    audit(c, admin["id"], "mfa_reset", "user", f"{target['username']} · {reason}")


# ---------------------------------------------------------------- single sign-on (Task 14)
def has_staff_role(c, u) -> bool:
    """A staff role as the primary role or in any grant: such an account is never linked automatically."""
    primary = u.get("primary_role") or u["role"]
    return primary in domain.MFA_ROLES or bool(repo.granted_roles(c, u["id"]) & set(domain.MFA_ROLES))


def _first_link(c, cfg: dict, claims: dict):
    """(account, how) for a provider identity seen for the first time, or (None, None). Only a student account is
    linked automatically: by the configured student-number claim, or by an e-mail the provider has verified."""
    number = domain.student_number(claims, cfg.get("student_claim"))
    found = repo.students_by_number(c, number) if number else []
    candidates = [(found[0], "student_no")] if len(found) == 1 else []      # two accounts with one number: none
    email = domain.verified_email(claims)
    u = repo.by_email(c, email) if email else None
    if u:
        candidates.append((u, "email"))
    for u, how in candidates:
        if u["status"] == "active" and not has_staff_role(c, u):
            return u, how
    return None, None


def sso_account(c, cfg: dict, claims: dict):
    """('ok', account) | ('not_found', None). A known (iss, sub) is the only way to an account after its first link,
    so a changed e-mail at the provider never moves a sign-in. No account is ever created here."""
    iss, sub = cfg["issuer"], claims["sub"]
    u = repo.sso_user(c, iss, sub)
    if u:
        return ("ok", u) if u["status"] == "active" else ("not_found", None)
    u, how = _first_link(c, cfg, claims)
    if not u or not repo.add_identity(c, u["id"], iss, sub, domain.verified_email(claims), how):
        audit(c, None, "sso_not_found", "user", f"{iss} · {sub[:64]}")
        return "not_found", None
    audit(c, u["id"], "sso_linked", "user", f"{how} · {iss}")
    return "ok", u


def scope_after_sso(cfg: dict, u, claims: dict) -> str:
    """The provider's second factor counts only when the tenant names the amr/acr values it trusts; otherwise the
    local TOTP step stays, exactly as after a password."""
    if domain.idp_mfa(claims, cfg.get("mfa_amr") or [], cfg.get("mfa_acr") or []):
        return "full"
    return scope_after_password(u)


def link_identity(c, by, target, iss: str, sub: str, email: str | None, how: str) -> bool:
    """The account owner (from a local session) or an administrator binds a provider identity; False when taken."""
    if not repo.add_identity(c, target["id"], iss, sub, email, how):
        return False
    audit(c, by["id"], "sso_linked", "user", f"{how} · {target['username']} · {iss}")
    return True
