"""API keys (tasks/todo.md, Task 37). A key reaches only the routes of its scopes (``@R(..., scope="token:<scope>")``),
only by ``Authorization: Bearer``; such a route ignores cookies, and no cookie route accepts a key. The key is shown
once and kept as its SHA-256; each key has its own per-minute limit; every call is audited."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets

from ...core.i18n import E, T3
from ...core.security import RateLimiter
from ...core.web import HTTPError
from ...legacy.store import audit, iso, now, row, rows

SCOPES = ("grades.read", "attendance.read", "registry.read", "status.read")
PREFIX = "zk_"
_LIMITERS: dict[int, RateLimiter] = {}      # one per limit value, not one per call (AR-E9); the key is the token's id


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def key_input(body) -> tuple[dict, dict | None]:
    v = {"name": " ".join(body.text("name", 200).split()), "scopes": body.array("scopes"), "per_minute": body.integer("per_minute", 60)}
    if not 3 <= len(v["name"]) <= 80:
        return v, E("Açarın adı 3–80 simvol olmalıdır")
    if not v["scopes"] or not all(isinstance(s, str) and s in SCOPES for s in v["scopes"]):
        return v, E("Əhatə: {scopes}", scopes=", ".join(SCOPES))
    if not 1 <= v["per_minute"] <= 600:
        return v, E("Dəqiqəlik limit 1–600 olmalıdır")
    v["scopes"] = sorted(set(v["scopes"]))
    return v, None


def create(c, user, body) -> tuple[str, object]:
    v, problem = key_input(body)
    if problem:
        return "invalid", problem
    token = PREFIX + secrets.token_urlsafe(32)
    tid = c.execute("INSERT INTO api_tokens(name,prefix,token_hash,scopes,per_minute,created_by,created_at) VALUES(?,?,?,?,?,?,?)",
                    (v["name"], token[:10], _hash(token), json.dumps(v["scopes"]), v["per_minute"], user["id"], iso(now()))).lastrowid
    audit(c, user["id"], "api_key_create", "api_token", f"#{tid} {v['name'][:60]} · {','.join(v['scopes'])}")
    return "ok", {**listed(c, tid), "token": token}              # the only time the key is shown


def listed(c, tid: int | None = None):
    sql = "SELECT id, name, prefix, scopes, per_minute, created_at, last_used_at, revoked_at FROM api_tokens"
    out = [{**r, "scopes": json.loads(r["scopes"])} for r in (rows(c, sql + " WHERE id=?", (tid,)) if tid else rows(c, sql + " ORDER BY id DESC"))]
    return out[0] if tid else out


def revoke(c, user, tid: int) -> tuple[str, object]:
    if not row(c, "SELECT 1 FROM api_tokens WHERE id=? AND revoked_at IS NULL", (tid,)):
        return "missing", None
    c.execute("UPDATE api_tokens SET revoked_at=? WHERE id=?", (iso(now()), tid))
    audit(c, user["id"], "api_key_revoke", "api_token", f"#{tid}")
    return "ok", listed(c, tid)


def authenticate(c, header: str | None, scope: str, path: str) -> dict:
    """The caller of a key route: 401 without a valid key, 403 outside its scopes, 429 over its own limit. The call is
    audited and the key's last use written (the caller commits these at once)."""
    raw = (header or "").strip()
    token = raw[7:].strip() if raw[:7].lower() == "bearer " else ""
    t = row(c, "SELECT * FROM api_tokens WHERE token_hash=? AND revoked_at IS NULL", (_hash(token),)) if token.startswith(PREFIX) else None
    if not t or not hmac.compare_digest(t["token_hash"], _hash(token)):
        old = row(c, "SELECT id FROM api_tokens WHERE token_hash=? AND revoked_at IS NOT NULL", (_hash(token),)) if token.startswith(PREFIX) else None
        if old:                                                 # a revoked key still in use is worth knowing (SF-E11); other 401s are not
            audit(c, None, "api_call_revoked", "api_token", f"#{old['id']} {path}")
            c.commit()
        raise HTTPError(401, T3("API açarı yoxdur və ya etibarsızdır"))
    if scope not in json.loads(t["scopes"]):
        audit(c, None, "api_call_refused", "api_token", f"#{t['id']} {path} · scope {scope}")
        c.commit()                                              # the refusal stays in the audit log
        raise HTTPError(403, T3("Bu marşrut açarın əhatə dairəsinə daxil deyil"))
    lim = _LIMITERS.get(t["per_minute"]) or _LIMITERS.setdefault(t["per_minute"], RateLimiter(t["per_minute"], 60, name="api_key"))
    if not lim.hit(f"t{t['id']}"):
        raise HTTPError(429, T3("Açarın dəqiqəlik limiti bitib"))
    c.execute("UPDATE api_tokens SET last_used_at=? WHERE id=?", (iso(now()), t["id"]))
    audit(c, None, "api_call", "api_token", f"#{t['id']} {path}")
    return {"id": None, "role": "api", "full_name": f"API · {t['name']}", "status": "active", "must_change": 0, "token_id": t["id"],
            "session_scope": None}
