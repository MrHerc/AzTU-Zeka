"""SQL of the e-mail outbox (tasks/todo.md, Task 36, slice 2)."""
from __future__ import annotations

import json

from ...legacy.store import row, rows


def recipients(c, uids: list[int]) -> list[dict]:
    if not uids:
        return []
    return rows(c, f"SELECT id, email, prefs, status FROM users WHERE id IN ({','.join('?' * len(uids))})", tuple(uids))  # nosec B608


def user(c, uid: int):
    return row(c, "SELECT id, email, prefs, status FROM users WHERE id=?", (uid,))


def set_prefs(c, uid: int, prefs: dict):
    c.execute("UPDATE users SET prefs=? WHERE id=?", (json.dumps(prefs, ensure_ascii=False), uid))


def enqueue(c, user_id: int | None, address: str, kind: str, template: str, params: dict, lang: str, at: str):
    c.execute("INSERT INTO outbox(user_id,address,kind,template,params,lang,next_at,created_at) VALUES(?,?,?,?,?,?,?,?)",
              (user_id, address, kind, template, json.dumps(params, ensure_ascii=False), lang, at, at))


def due(c, at: str, limit: int) -> list[dict]:
    return rows(c, "SELECT * FROM outbox WHERE status='pending' AND next_at<=? ORDER BY next_at, id LIMIT ?", (at, limit))


def mark_sent(c, oid: int, at: str):
    c.execute("UPDATE outbox SET status='sent', sent_at=?, attempts=attempts+1, last_error=NULL WHERE id=?", (at, oid))


def mark_retry(c, oid: int, attempts: int, next_at: str, error: str):
    c.execute("UPDATE outbox SET attempts=?, next_at=?, last_error=? WHERE id=?", (attempts, next_at, error[:500], oid))


def mark_final(c, oid: int, status: str, attempts: int, error: str):
    c.execute("UPDATE outbox SET status=?, attempts=?, last_error=? WHERE id=?", (status, attempts, error[:500], oid))
