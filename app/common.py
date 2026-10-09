"""Shared helpers for all route modules."""
from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime, timedelta

from . import engine, store
from .i18n import E, L
from .store import J, iso, now, row, rows, setting
from .web import HTTPError, Router

R = Router()
COOKIE = "zeka_sid"
BASE_URL = {"value": "http://127.0.0.1:5070"}
ROLE_HOME = {"student": "/student", "teacher": "/teacher", "office": "/office", "leader": "/leader", "admin": "/admin"}
STAFF = ("office", "admin", "leader")

# one-time document view keys (open /doc/{id} in a new tab even where cookies are unavailable)
_DOC_KEYS: dict = {}
_DOC_LOCK = threading.Lock()


def _sid(req):
    return req.cookies.get(COOKIE) or req.headers.get("X-Session")


def session_cookie(value: str = "", expire: bool = False) -> tuple:
    """Session cookie header; Secure when the portal is published over HTTPS (run.py --public-url https://...)."""
    attrs = "; Max-Age=0" if expire else ""
    if BASE_URL["value"].startswith("https://"):
        attrs += "; Secure"
    return ("Set-Cookie", f"{COOKIE}={value}; HttpOnly; SameSite=Lax; Path=/{attrs}")


def before(req, roles, auth):
    req.db = store.connect()
    sid = _sid(req)
    if sid:
        req.user = row(req.db, "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.sid=?", (sid,))
    if not req.user and req.path.startswith(("/doc/", "/api/files/", "/syllabus/")) and req.query.get("k"):
        req.user = _key_user(req)
    if auth and not req.user:
        raise HTTPError(401, "Daxil olmamısınız")
    if roles and req.user["role"] not in roles:
        raise HTTPError(403, "Bu bölməyə giriş icazəniz yoxdur")


def after(req, ok):
    if req.db is not None:
        if ok:
            req.db.commit()
        else:
            req.db.rollback()
        req.db.close()
        req.db = None


def make_key(kind: str, obj_id: int, user_id: int) -> str:
    key = secrets.token_urlsafe(18)
    with _DOC_LOCK:
        for k in [k for k, v in _DOC_KEYS.items() if v["exp"] < now()]:
            _DOC_KEYS.pop(k, None)
        _DOC_KEYS[key] = {"kind": kind, "id": obj_id, "user": user_id, "exp": now() + timedelta(minutes=5)}
    return key


def _key_user(req):
    with _DOC_LOCK:
        entry = _DOC_KEYS.pop(req.query.get("k"), None)
    kind = "doc" if req.path.startswith("/doc/") else "syl" if req.path.startswith("/syllabus/") else "file"
    if not entry or entry["exp"] < now() or entry["kind"] != kind or str(entry["id"]) != req.path.rstrip("/").rsplit("/", 1)[-1]:
        return None
    return row(req.db, "SELECT * FROM users WHERE id=?", (entry["user"],))


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
