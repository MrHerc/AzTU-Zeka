"""Shared helpers for all route modules."""
from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime, timedelta

from . import engine, store
from ..core.i18n import E
from ..core.security import CFG
from .store import J, iso, now, row, rows, setting
from ..core.web import HTTPError, Router

R = Router()
COOKIE = "zeka_sid"
BASE_URL = {"value": "http://127.0.0.1:5070"}
ROLE_HOME = {"student": "/student", "teacher": "/teacher", "office": "/office", "leader": "/leader", "admin": "/admin"}
STAFF = ("office", "admin", "leader")

# Tests (ZEKA_TX_GUARD=1): a request may hold SQLite's single write lock for at most 200 ms (Task 7).
_TX_GUARD = os.environ.get("ZEKA_TX_GUARD") == "1"
TX_GUARD_EXEMPT = ("/api/admin/reset",)


def _sid(req):
    return req.cookies.get(COOKIE) or req.headers.get("X-Session")


def session_cutoff() -> str:
    """Sessions created before this moment have expired (absolute lifetime, ZEKA_SESSION_HOURS)."""
    return iso(now() - timedelta(hours=CFG.session_hours))


def session_cookie(value: str = "", expire: bool = False) -> tuple:
    """Session cookie header; Secure when the portal is published over HTTPS (run.py --public-url https://...)."""
    attrs = "; Max-Age=0" if expire else f"; Max-Age={CFG.session_hours * 3600}"
    if BASE_URL["value"].startswith("https://"):
        attrs += "; Secure"
    return ("Set-Cookie", f"{COOKIE}={value}; HttpOnly; SameSite=Lax; Path=/{attrs}")


def _note_write(req, sql: str):
    if req.first_write is None and sql.lstrip()[:7].upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")):
        req.first_write = time.monotonic()


def before(req, roles, auth):
    req.db = store.connect()
    if _TX_GUARD:
        req.first_write = None
        req.db.set_trace_callback(lambda sql: _note_write(req, sql))
    store.sync_indexes(req.db)
    sid = _sid(req)
    if sid:
        req.user = row(req.db, "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.sid=? AND s.created_at>=?",
                       (sid, session_cutoff()))
    if not req.user and req.path.startswith(("/doc/", "/api/files/", "/syllabus/")) and req.query.get("k"):
        req.user = _key_user(req)
    if auth and not req.user:
        raise HTTPError(401, "Daxil olmamısınız")
    if roles and req.user["role"] not in roles:
        raise HTTPError(403, "Bu bölməyə giriş icazəniz yoxdur")


def after(req, ok):
    if req.db is not None:
        held = _TX_GUARD and ok and req.first_write is not None and time.monotonic() - req.first_write
        if held and held > 0.2 and not req.path.startswith(TX_GUARD_EXEMPT):
            raise AssertionError(f"{req.path} held the write lock for {held * 1000:.0f} ms (limit 200)")
        if ok:
            req.db.commit()
        else:
            req.db.rollback()
        req.db.close()
        req.db = None


def make_key(c, kind: str, obj_id: int, user_id: int) -> str:
    """One-time, 5-minute link key, stored in the database so that any worker process can accept it (once)."""
    key = secrets.token_urlsafe(18)
    c.execute("DELETE FROM doc_keys WHERE expires_at<?", (iso(now()),))
    c.execute("INSERT INTO doc_keys(key,kind,obj_id,user_id,expires_at) VALUES(?,?,?,?,?)",
              (key, kind, obj_id, user_id, iso(now() + timedelta(minutes=5))))
    return key


def _key_user(req):
    kind = "doc" if req.path.startswith("/doc/") else "syl" if req.path.startswith("/syllabus/") else "file"
    # DELETE ... RETURNING: of two processes holding the same key, only one gets the row back
    entry = req.db.execute("DELETE FROM doc_keys WHERE key=? RETURNING kind, obj_id, user_id, expires_at", (req.query.get("k"),)).fetchone()
    req.db.commit()                                 # the key is spent even if this request fails later
    if not entry or entry["expires_at"] < iso(now()) or entry["kind"] != kind or str(entry["obj_id"]) != req.path.rstrip("/").rsplit("/", 1)[-1]:
        return None
    return row(req.db, "SELECT * FROM users WHERE id=?", (entry["user_id"],))


def ctx(c):
    uni = setting(c, "university")
    return {"university": uni, "faculty": setting(c, "faculty"), "specialty": setting(c, "specialty"),
            "semester": uni["semester"], "base_url": BASE_URL["value"]}


def pub_user(u):
    if not u:
        return None
    out = {k: u[k] for k in ("id", "username", "full_name", "role", "title", "color", "consent_at")}
    out["prefs"] = J(u.get("prefs"), {}) or {}
    return out


def holder(c, uid):
    h = row(c, "SELECT u.*, g.name grp, g.year FROM users u LEFT JOIN study_groups g ON g.id=u.group_id WHERE u.id=?", (uid,))
    if h:
        h["group"] = h.get("grp")
    return h


def course_access(req, cid):
    c, u = req.db, req.user
    course = row(c, "SELECT * FROM courses WHERE id=?", (cid,))
    if not course:
        raise HTTPError(404, "Fənn tapılmadı")
    if u["role"] == "student" and not row(c, "SELECT 1 FROM enrollments WHERE user_id=? AND course_id=?", (u["id"], cid)):
        raise HTTPError(403, "Bu fənnə qeydiyyatınız yoxdur")
    if u["role"] == "teacher" and course["teacher_id"] != u["id"]:
        raise HTTPError(403, "Bu fənn sizə aid deyil")
    return course


def week_index(ts: str) -> int:
    return (now() - datetime.fromisoformat(ts)).days // 7


def usage(c, u):
    lim = setting(c, "limits", {}).get("daily_messages", 50)
    start = now().replace(hour=0, minute=0, second=0).isoformat()
    n = row(c, "SELECT COUNT(*) n FROM messages WHERE user_id=? AND role='user' AND created_at>=?", (u["id"], start))["n"]
    return {"used": n, "limit": lim}


def check_limit(c, u):
    us = usage(c, u)
    if u["role"] == "student" and us["used"] >= us["limit"]:
        raise HTTPError(429, E("Gündəlik sual limitinə çatdınız ({n}). Sabah yenidən cəhd edin.", n=us["limit"]))
    return us["used"] + 1, us["limit"]


def save_msg(c, uid, course_id, channel, role, content, cites=None, meta=None):
    return c.execute("INSERT INTO messages(user_id,course_id,channel,role,content,cites,meta,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (uid, course_id, channel, role, content, json.dumps(cites or []),
                      json.dumps(meta or {}, ensure_ascii=False), iso(now()))).lastrowid


def history(c, uid, course_id, channel, limit=12):
    hs = rows(c, "SELECT * FROM messages WHERE user_id=? AND channel=? AND COALESCE(course_id,0)=? ORDER BY id DESC LIMIT ?",
              (uid, channel, course_id or 0, limit))
    for m in hs:
        m["meta"] = J(m["meta"], {}) or {}
        m["cites"] = J(m["cites"], []) or []
    return list(reversed(hs))


def cite_list(ids):
    out = []
    for i, cid in enumerate(ids or []):
        d = engine.INDEX["chunks"].docs.get(cid)
        if d:
            m = d[2]
            out.append({"n": i + 1, "id": cid, "kind": "chunk", "material": m["material"], "heading": m["heading"],
                        "snippet": engine.plain(m["text"])[:160]})
    return out


def kb_cite_list(ids):
    out = []
    for i, kid in enumerate(ids or []):
        d = engine.INDEX["campus"].docs.get(kid)
        if d:
            m = d[2]
            out.append({"n": i + 1, "id": kid, "kind": "kb", "material": m["material"], "heading": m["heading"], "snippet": m["text"][:160]})
    return out


def msg_out(m, kb=False):
    cites = m["cites"] if isinstance(m["cites"], list) else J(m["cites"], [])
    meta = m["meta"] if isinstance(m["meta"], dict) else J(m["meta"], {})
    return {"id": m["id"], "role": m["role"], "content": m["content"], "meta": meta, "rating": m.get("rating"),
            "created_at": m["created_at"], "cites": kb_cite_list(cites) if kb else cite_list(cites)}


def search_chunks(course_id, q, k=4):
    return engine.INDEX["chunks"].search(q, k=k, where=lambda m: m["course_id"] == course_id)


def q_load(c, qid):
    q = row(c, "SELECT * FROM questions WHERE id=?", (qid,))
    if not q:
        raise HTTPError(404, "Sual tapılmadı")
    q["options"] = J(q["options"], [])
    q["answer"] = J(q["answer"])
    q["flags"] = J(q["flags"], [])
    return q
