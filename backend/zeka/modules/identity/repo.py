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


def signed_in(c, account: str, client: str, uid: int, new_hash: str | None):
    c.execute("DELETE FROM login_blocks WHERE account=? AND client=?", (account, client))
    if new_hash:
        c.execute("UPDATE users SET password_hash=?, failed_count=0, locked_until=NULL WHERE id=?", (new_hash, uid))
    else:
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
