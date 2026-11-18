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
    account, client = login.strip().lower()[:254], domain.client_key(ip)
    u = repo.find_login(c, account) if account else None
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
    repo.signed_in(c, account, client, u["id"], new_hash)
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
    problem = domain.policy_problem(new, mfa=False, context=context_words(u), blocklist=blocklist())
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


def unlock(c, admin, target, reason: str):
    repo.unlock(c, target)
    audit(c, admin["id"], "account_unlocked", "user", f"{target['username']} · {reason}")
