"""SQL of the identity module (Task 10). Only this file talks to the database."""
from __future__ import annotations

from datetime import datetime, timedelta

from ...legacy.store import iso, now, row, rows
from . import domain


def find_login(c, login: str):
    """The account for a typed login: the user name or the e-mail address (both stored in lower case)."""
    return row(c, "SELECT * FROM users WHERE username=? OR email=?", (login, login))


def user(c, uid: int):
    return row(c, "SELECT * FROM users WHERE id=?", (uid,))


def block_wait(c, account: str, client: str, t: float) -> float:
    r = row(c, "SELECT until FROM login_blocks WHERE account=? AND client=?", (account, client))
    return max(0.0, (r["until"] or 0) - t) if r else 0.0


def lock_wait(u) -> float:
    if not u or not u["locked_until"]:
        return 0.0
    return max(0.0, (datetime.fromisoformat(u["locked_until"]) - now()).total_seconds())


def record_failure(c, account: str, client: str, t: float) -> bool:
    """Count one failure of this client for this account; True when it starts a block."""
    c.execute("DELETE FROM login_blocks WHERE first<? AND (until IS NULL OR until<?)", (t - domain.WINDOW, t))
    r = row(c, "SELECT failures, first FROM login_blocks WHERE account=? AND client=?", (account, client))
    failures, first = (r["failures"] + 1, r["first"]) if r and r["first"] >= t - domain.WINDOW else (1, t)
    blocked = failures >= domain.CLIENT_LIMIT
    if blocked:                                  # the block runs from now; counting starts again after it
        failures, first = 0, t
    c.execute("INSERT INTO login_blocks(account,client,failures,first,until) VALUES(?,?,?,?,?) ON CONFLICT(account,client) "
              "DO UPDATE SET failures=excluded.failures, first=excluded.first, until=excluded.until",
              (account, client, failures, first, t + domain.BLOCK if blocked else None))
    return blocked


def account_failure(c, uid: int) -> bool:
    """Count one consecutive failure of the account; True when it locks the account."""
    c.execute("UPDATE users SET failed_count=failed_count+1 WHERE id=?", (uid,))
    if row(c, "SELECT failed_count FROM users WHERE id=?", (uid,))["failed_count"] < domain.ACCOUNT_LIMIT:
        return False
    c.execute("UPDATE users SET failed_count=0, locked_until=? WHERE id=?",
              (iso(now() + timedelta(seconds=domain.BLOCK)), uid))
    return True


def unknown_failure(c, account: str, t: float):
    """A failure for a name no account has: counted in a row of its own ("*") and locked after as many as a real
    account, so the answer to a locked name is the same whether it exists or not."""
    r = row(c, "SELECT failures FROM login_blocks WHERE account=? AND client='*'", (account,))
    n = (r["failures"] if r else 0) + 1
    locked = n >= domain.ACCOUNT_LIMIT
    c.execute("INSERT INTO login_blocks(account,client,failures,first,until) VALUES(?,'*',?,?,?) ON CONFLICT(account,client) "
              "DO UPDATE SET failures=excluded.failures, first=excluded.first, until=excluded.until",
              (account, 0 if locked else n, t, t + domain.BLOCK if locked else None))


def signed_in(c, account: str, client: str, uid: int, new_hash: str | None, complete: bool = True):
    """The password was right. Failure counts clear only when the sign-in is complete: while a second factor is
    pending they stay, or every correct password would buy five more code guesses (Task 12)."""
    if new_hash:
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, uid))
    if complete:
        clear_failures(c, account, client, uid)


def clear_failures(c, account: str, client: str, uid: int):
    c.execute("DELETE FROM login_blocks WHERE account=? AND client=?", (account, client))
    c.execute("UPDATE users SET failed_count=0, locked_until=NULL WHERE id=?", (uid,))


def set_password(c, uid: int, password_hash: str, must_change: bool):
    c.execute("UPDATE users SET password_hash=?, must_change=?, failed_count=0, locked_until=NULL WHERE id=?",
              (password_hash, int(must_change), uid))


def unlock(c, u):
    c.execute("UPDATE users SET failed_count=0, locked_until=NULL WHERE id=?", (u["id"],))
    c.execute("DELETE FROM login_blocks WHERE account IN (?, ?)", (u["username"], u["email"] or u["username"]))


# ---------------------------------------------------------------- sessions (Task 11)
def sessions_of(c, uid: int) -> list:
    return rows(c, "SELECT id, created_at, last_seen, ip, agent FROM sessions WHERE user_id=? ORDER BY last_seen DESC", (uid,))


def end_session(c, uid: int, session_id: int) -> bool:
    return c.execute("DELETE FROM sessions WHERE id=? AND user_id=?", (session_id, uid)).rowcount == 1


def end_sessions(c, uid: int, keep: int | None = None) -> int:
    """End every session of the account except ``keep``; returns how many ended."""
    return c.execute("DELETE FROM sessions WHERE user_id=? AND id IS NOT ?", (uid, keep)).rowcount


# ---------------------------------------------------------------- second factor (Task 12)
def set_session_scope(c, session_id: int, scope: str):
    c.execute("UPDATE sessions SET scope=?, mfa_at=?, mfa_failures=0 WHERE id=?",
              (scope, iso(now()) if scope == "full" else None, session_id))


def mfa_failure(c, session_id: int) -> int:
    c.execute("UPDATE sessions SET mfa_failures=mfa_failures+1 WHERE id=?", (session_id,))
    r = row(c, "SELECT mfa_failures FROM sessions WHERE id=?", (session_id,))
    return r["mfa_failures"] if r else 0


def start_totp(c, uid: int, secret: str):
    c.execute("UPDATE users SET totp_secret=?, totp_last=NULL, totp_enabled_at=NULL WHERE id=?", (secret, uid))


def enable_totp(c, uid: int, step: int, code_hashes: list[str]):
    c.execute("UPDATE users SET totp_last=?, totp_enabled_at=? WHERE id=?", (step, iso(now()), uid))
    c.execute("DELETE FROM recovery_codes WHERE user_id=?", (uid,))
    c.executemany("INSERT INTO recovery_codes(user_id,code_hash) VALUES(?,?)", [(uid, h) for h in code_hashes])


def accept_step(c, uid: int, step: int) -> bool:
    """Record the accepted 30-second step; False when another request used this or a later step first."""
    return c.execute("UPDATE users SET totp_last=? WHERE id=? AND (totp_last IS NULL OR totp_last<?)",
                     (step, uid, step)).rowcount == 1


def use_recovery_code(c, uid: int, code_hash: str) -> bool:
    return c.execute("UPDATE recovery_codes SET used_at=? WHERE user_id=? AND code_hash=? AND used_at IS NULL",
                     (iso(now()), uid, code_hash)).rowcount == 1


def recovery_left(c, uid: int) -> int:
    return row(c, "SELECT COUNT(*) n FROM recovery_codes WHERE user_id=? AND used_at IS NULL", (uid,))["n"]


def reset_totp(c, uid: int):
    c.execute("UPDATE users SET totp_secret=NULL, totp_last=NULL, totp_enabled_at=NULL WHERE id=?", (uid,))
    c.execute("DELETE FROM recovery_codes WHERE user_id=?", (uid,))


# ---------------------------------------------------------------- roles (Task 13)
def roles_of(c, u) -> list[dict]:
    """The primary role first, then every granted role with its scope."""
    primary = u.get("primary_role") or u["role"]
    return [{"id": None, "role": primary, "scope_type": None, "scope_id": None, "primary": True}] + [
        {**g, "primary": False} for g in rows(c, "SELECT id, role, scope_type, scope_id FROM role_grants WHERE user_id=? "
                                                 "ORDER BY role, scope_type, scope_id", (u["id"],))]


def set_session_role(c, session_id: int, role: str | None):
    c.execute("UPDATE sessions SET role=? WHERE id=?", (role, session_id))


def grant_role(c, uid: int, role: str, scope_type: str | None, scope_id: int | None, by: int) -> int:
    return c.execute("INSERT INTO role_grants(user_id,role,scope_type,scope_id,granted_by,granted_at) VALUES(?,?,?,?,?,?)",
                     (uid, role, scope_type, scope_id, by, iso(now()))).lastrowid


def grant(c, uid: int, grant_id: int):
    return row(c, "SELECT * FROM role_grants WHERE id=? AND user_id=?", (grant_id, uid))


# ---------------------------------------------------------------- single sign-on (Task 14)
def add_pending(c, state: str, browser_hash: str, nonce: str, verifier: str, link_user_id: int | None, t: float):
    c.execute("DELETE FROM sso_pending WHERE created_at<?", (t - domain.SSO_PENDING,))
    c.execute("INSERT INTO sso_pending(state,browser_hash,nonce,verifier,link_user_id,created_at) VALUES(?,?,?,?,?,?)",
              (state, browser_hash, nonce, verifier, link_user_id, t))


def take_pending(c, state: str):
    """The started sign-in for ``state``, removed in the same statement: only one callback in any worker gets it."""
    return c.execute("DELETE FROM sso_pending WHERE state=? RETURNING *", (state,)).fetchone()


def sso_user(c, iss: str, sub: str):
    return row(c, "SELECT u.* FROM sso_identities i JOIN users u ON u.id=i.user_id WHERE i.iss=? AND i.sub=?", (iss, sub))


def students_by_number(c, number: str) -> list:
    return rows(c, "SELECT * FROM users WHERE student_no=? AND role='student'", (number,))


def by_email(c, email: str):
    return row(c, "SELECT * FROM users WHERE email=?", (email,))


def granted_roles(c, uid: int) -> set[str]:
    return {r["role"] for r in rows(c, "SELECT DISTINCT role FROM role_grants WHERE user_id=?", (uid,))}


def add_identity(c, uid: int, iss: str, sub: str, email: str | None, linked_by: str) -> bool:
    """False when this (iss, sub) is bound already, or the account already has a binding with this issuer."""
    return c.execute("INSERT OR IGNORE INTO sso_identities(user_id,iss,sub,email,linked_by,linked_at) VALUES(?,?,?,?,?,?)",
                     (uid, iss, sub, email, linked_by, iso(now()))).rowcount == 1


def identity_seen(c, iss: str, sub: str, email: str | None):
    c.execute("UPDATE sso_identities SET last_login=?, email=? WHERE iss=? AND sub=?", (iso(now()), email, iss, sub))


def identities_of(c, uid: int) -> list:
    return rows(c, "SELECT id, iss, sub, email, linked_by, linked_at, last_login FROM sso_identities WHERE user_id=? "
                   "ORDER BY id", (uid,))


def remove_identity(c, uid: int, identity_id: int):
    """The removed binding, or None."""
    return c.execute("DELETE FROM sso_identities WHERE id=? AND user_id=? RETURNING iss, sub", (identity_id, uid)).fetchone()
