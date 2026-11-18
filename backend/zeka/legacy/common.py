"""Shared helpers for all route modules."""
from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime, timedelta

from . import engine, store
from ..modules.identity import domain as identity
from ..core.i18n import E
from .store import J, iso, now, row, rows, setting
from ..core.web import HTTPError, Router

R = Router()
COOKIE = "zeka_sid"
BASE_URL = {"value": "http://127.0.0.1:5070"}
ROLE_HOME = {"student": "/student", "teacher": "/teacher", "office": "/office", "leader": "/leader", "admin": "/admin",
             # new roles (Task 13) start from the closest existing home until their own pages arrive
             "dept_head": "/teacher", "academic_office": "/admin/directory", "proctor": "/teacher"}
STAFF = ("office", "admin", "leader")

# Tests (ZEKA_TX_GUARD=1): a request may hold SQLite's single write lock for at most 200 ms (Task 7).
_TX_GUARD = os.environ.get("ZEKA_TX_GUARD") == "1"
TX_GUARD_EXEMPT = ("/api/admin/reset", "/api/admin/import")     # the import reports its own lock time (Task 16)


def _sid(req):
    """The session id, from the HttpOnly cookie only (Task 11: no header, never in a response body)."""
    return req.cookies.get(COOKIE)


def session_limits(c, role: str) -> tuple[int, int]:
    """(idle, absolute) seconds for a role; the tenant setting ``session_limits`` overrides the defaults."""
    return identity.session_limits(role, setting(c, "session_limits", {}) or {})


def session_cookie(value: str = "", expire: bool = False, max_age: int = 0) -> tuple:
    """Session cookie header; Secure when the portal is published over HTTPS (run.py --public-url https://...)."""
    attrs = "; Max-Age=0" if expire else f"; Max-Age={max_age}" if max_age else ""
    if BASE_URL["value"].startswith("https://"):
        attrs += "; Secure"
    return ("Set-Cookie", f"{COOKIE}={value}; HttpOnly; SameSite=Lax; Path=/{attrs}")


def start_session(req, u, how: str, scope: str = "full") -> tuple[str, list]:
    """A new session for ``u`` (the browser's previous one ends); returns the session id and its cookie header.
    Only the id's SHA-256 is stored."""
    c = req.db
    old = _sid(req)
    if old:                                   # no parallel sessions per browser; a sign-in always gets a fresh id
        c.execute("DELETE FROM sessions WHERE id_hash=?", (identity.session_hash(old),))
    t = now()
    c.execute("DELETE FROM sessions WHERE last_seen<?", (iso(t - timedelta(seconds=identity.MAX_IDLE)),))
    sid = identity.new_session_id()
    c.execute("INSERT INTO sessions(id_hash,user_id,created_at,last_seen,scope,ip,agent) VALUES(?,?,?,?,?,?,?)",
              (identity.session_hash(sid), u["id"], iso(t), iso(t), scope, req.ip, (req.headers.get("User-Agent") or "")[:200]))
    store.audit(c, u["id"], "login", "session", how)
    return sid, [session_cookie(sid, max_age=session_limits(c, u["role"])[1])]


def rotate_session(req) -> list:
    """A new id for the current session after a privilege change (second factor, role, password): the old id stops
    working at once. Returns the cookie header."""
    sid = identity.new_session_id()
    req.db.execute("UPDATE sessions SET id_hash=? WHERE id=?", (identity.session_hash(sid), req.user["session_id"]))
    return [session_cookie(sid, max_age=session_limits(req.db, req.user["role"])[1])]


def _own_commit(req):
    """Commit a bookkeeping write at once (session use, a spent key): the request itself may stay a reader."""
    req.db.commit()
    if _TX_GUARD:
        req.first_write = None


def _session_user(req, sid: str):
    u = row(req.db, "SELECT u.*, s.id AS session_id, s.created_at AS session_created, s.last_seen AS session_seen, "
                    "s.scope AS session_scope, s.mfa_at AS session_mfa, s.role AS session_role FROM sessions s "
                    "JOIN users u ON u.id=s.user_id WHERE s.id_hash=?", (identity.session_hash(sid),))
    if not u:
        return None
    u["primary_role"] = u["role"]
    if u["session_role"] and u["session_role"] != u["role"] and \
            row(req.db, "SELECT 1 FROM role_grants WHERE user_id=? AND role=? LIMIT 1", (u["id"], u["session_role"])):
        u["role"] = u["session_role"]            # the role this session acts in (Task 13); a revoked grant falls back
    t, seen = now(), datetime.fromisoformat(u["session_seen"])
    idle, absolute = session_limits(req.db, u["role"])
    if (t - seen).total_seconds() > idle or (t - datetime.fromisoformat(u["session_created"])).total_seconds() > absolute:
        req.db.execute("DELETE FROM sessions WHERE id=?", (u["session_id"],))
        _own_commit(req)
        return None
    if (t - seen).total_seconds() > identity.SEEN_EVERY:
        req.db.execute("UPDATE sessions SET last_seen=? WHERE id=?", (iso(t), u["session_id"]))
        _own_commit(req)
    return u


# A session of an account that must change its (temporary) password reaches only these paths.
MUST_CHANGE_OPEN = ("/api/auth/", "/api/bootstrap")


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
        req.user = _session_user(req, sid)
    if req.user and req.user["status"] != "active":             # a disabled account's sessions end at once
        req.user = None
    if not req.user and req.path.startswith(("/doc/", "/api/files/", "/syllabus/")) and req.query.get("k"):
        req.user = _key_user(req)
    scope = req.user.get("session_scope") if req.user else None
    if scope in identity.SCOPE_OPEN and not req.path.startswith(identity.SCOPE_OPEN[scope]):
        raise HTTPError(403, "Əvvəlcə ikinci addımı tamamlayın")
    if req.user and req.user["must_change"] and not req.path.startswith(MUST_CHANGE_OPEN):
        raise HTTPError(403, "Əvvəlcə müvəqqəti parolu dəyişin")
    if auth and not req.user:
        raise HTTPError(401, "Daxil olmamısınız")
    if roles and req.user["role"] not in roles:
        raise HTTPError(403, "Bu bölməyə giriş icazəniz yoxdur")


def after(req, ok):
    if req.db is not None:
        held = _TX_GUARD and ok and req.first_write is not None and time.monotonic() - req.first_write
        if held and held > 0.2 and not req.path.startswith(TX_GUARD_EXEMPT):
            raise AssertionError(f"{req.path} held the write lock for {held * 1000:.0f} ms (limit 200)")
        if ok and req.audit_kind and req.read_owner and req.user and req.read_owner != req.user["id"]:
            # Task 13: someone else's document, file, request or risk profile was read; written last, so briefly locked
            store.audit(req.db, req.user["id"], f"read_{req.audit_kind}", req.audit_kind,
                        f"#{req.read_object} · sahibi #{req.read_owner}")
        if ok:
            req.db.commit()
        else:
            req.db.rollback()
        req.db.close()
        req.db = None


# ---------------------------------------------------------------- dean's office scope (Task 13, slice 2)
def faculty_students(c, u) -> set[int] | None:
    """The students an ``office`` user serves: those of the faculties in its grants. None: no limit (leader, admin)."""
    if u["role"] != "office":
        return None
    return {r["id"] for r in rows(c, "SELECT u.id FROM users u JOIN study_groups g ON g.id=u.group_id WHERE g.faculty_id IN "
                                     "(SELECT scope_id FROM role_grants WHERE user_id=? AND role='office' AND scope_type='faculty')",
                                  (u["id"],))}


def serves(c, u, student_id) -> bool:
    """Whether a staff user may see this student's requests, documents and files."""
    scope = faculty_students(c, u)
    return scope is None or student_id in scope


def office_for(c, student_id) -> list[int]:
    """The office users whose faculty scope covers the student (who is told about a new request)."""
    return [r["user_id"] for r in rows(c, "SELECT DISTINCT g.user_id FROM role_grants g JOIN users u ON u.id=g.user_id "
                                          "JOIN study_groups sg ON sg.faculty_id=g.scope_id JOIN users s ON s.group_id=sg.id "
                                          "WHERE g.role='office' AND g.scope_type='faculty' AND s.id=? AND u.status='active'",
                                       (student_id,))]


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
    _own_commit(req)                                # the key is spent even if this request fails later
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
    out["must_change"] = bool(u.get("must_change"))
    out["scope"] = u.get("session_scope") or "full"            # mfa / mfa_enroll: the second factor comes first (Task 12)
    out["mfa_enabled"] = bool(u.get("totp_enabled_at"))
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
