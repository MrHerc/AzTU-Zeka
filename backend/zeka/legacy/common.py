"""Shared helpers for all route modules."""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timedelta

from . import engine, store
from ..modules.identity import domain as identity
from ..core import events, tenant
from ..core.i18n import E, S
from .store import J, iso, now, row, rows, setting
from ..core.web import HTTPError, Router, json_resp

R = Router()
COOKIE = "zeka_sid"
BASE_URL = {"value": "http://127.0.0.1:5070"}
ROLE_HOME = {"student": "/student", "teacher": "/teacher", "office": "/office", "leader": "/leader", "admin": "/admin",
             # new roles (Task 13) start from the closest existing home until their own pages arrive
             "dept_head": "/teacher", "academic_office": "/admin/directory", "proctor": "/proctor"}
STAFF = ("office", "admin", "leader")

# Tests (ZEKA_TX_GUARD=1): a request may hold SQLite's single write lock for at most 200 ms (Task 7).
_TX_GUARD = os.environ.get("ZEKA_TX_GUARD") == "1"
TX_GUARD_EXEMPT = ("/api/admin/reset", "/api/admin/import",     # the import reports its own lock time (Task 16)
                   "/api/timetable/generate",                   # a term's lessons at once, a few times a term
                   "/api/admin/settings/")                      # new grading rules recompute every final grade


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
    events.record(c, u["id"], u["role"], "login", "identity")
    if not scope.startswith("exam:"):                  # Task 27: an ordinary sign-in while an exam session runs is an exam event
        exams = [r["scope"][5:] for r in rows(c, "SELECT DISTINCT scope FROM sessions WHERE user_id=? AND scope LIKE 'exam:%'", (u["id"],))]
        if exams:
            from ..modules.exam import service as exam
            for eid in exams:
                exam.note_session(c, int(eid), u["id"], "login.during_exam", {"ip": req.ip})
    return sid, [session_cookie(sid, max_age=session_limits(c, u["role"])[1])]


PASSWORD_INPUT_MAX = 1024          # longer input is refused before any hashing


def password_field(body, key: str) -> str:
    """A password exactly as typed: no trimming (spaces are allowed characters)."""
    v = body.get(key)
    if not isinstance(v, str) or len(v) > PASSWORD_INPUT_MAX:
        raise HTTPError(400, "Parol düzgün göndərilməyib")
    return v


def blocked_response(req, seconds: int):
    """429 with Retry-After for a throttled sign-in; returned, not raised, so the failure count commits."""
    return json_resp({"error": S("Çox sayda uğursuz cəhd. {n} saniyədən sonra yenidən cəhd edin.", req.lang, n=seconds)},
                     429, headers=[("Retry-After", str(seconds))])


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
    if req.changes_from is not None:            # Task 39: bookkeeping is not an event
        req.changes_from = req.db.total_changes


def _session_user(req, sid: str):
    u = row(req.db, "SELECT u.*, s.id AS session_id, s.created_at AS session_created, s.last_seen AS session_seen, "
                    "s.scope AS session_scope, s.mfa_at AS session_mfa, s.role AS session_role, s.ip AS session_ip, s.seb_ok AS session_seb_ok, "
                    "s.seb_nonce AS session_seb_nonce FROM sessions s "
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
        if seen.date() != t.date():              # Task 39: a session's first request of a day counts its user as active
            events.record(req.db, u["id"], u["role"], "visit", "identity")
        _own_commit(req)
    return u


# A session of an account that must change its (temporary) password reaches only these paths.
MUST_CHANGE_OPEN = ("/api/auth/", "/api/bootstrap")


def _note_write(req, sql: str):
    if req.first_write is None and sql.lstrip()[:7].upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")):
        req.first_write = time.monotonic()


def before(req, roles, auth):
    req.db = store.connect()
    req.changes_from = 0 if auth else None      # Task 39: rows changed past this count make an event (signed-in routes)
    if _TX_GUARD:
        req.first_write = None
        req.db.set_trace_callback(lambda sql: _note_write(req, sql))
    store.sync_indexes(req.db)
    if (req.route_scope or "").startswith("token:"):           # an API key route (Task 37): the key alone, never a cookie
        from ..modules.integration import tokens
        req.user = tokens.authenticate(req.db, req.headers.get("Authorization"), req.route_scope[6:], req.path)
        _own_commit(req)
        return
    sid = _sid(req)
    if sid:
        req.user = _session_user(req, sid)
    if req.user and req.user["status"] != "active":             # a disabled account's sessions end at once
        req.user = None
    if not req.user and req.path.startswith(("/doc/", "/api/files/", "/syllabus/")) and req.query.get("k"):
        req.user = _key_user(req)
    scope = req.user.get("session_scope") if req.user else None
    _exam_scope(req, scope)
    pending = scope in identity.SCOPE_OPEN and not req.path.startswith(identity.SCOPE_OPEN[scope])
    must_change = bool(req.user and req.user["must_change"] and not req.path.startswith(MUST_CHANGE_OPEN))
    if (pending or must_change) and not auth:
        req.user = None                         # a public page or sign-in: the half-finished session simply does not count
    elif pending:
        raise HTTPError(403, "Əvvəlcə ikinci addımı tamamlayın")
    elif must_change:
        raise HTTPError(403, "Əvvəlcə müvəqqəti parolu dəyişin")
    if auth and not req.user:
        raise HTTPError(401, "Daxil olmamısınız")
    if roles and req.user["role"] not in roles:
        raise HTTPError(403, "Bu bölməyə giriş icazəniz yoxdur")


def _exam_scope(req, scope: str | None):
    """Task 27: a session scoped to an exam reaches that exam's routes and nothing else; an exam's routes answer only a
    session scoped to that exam (an ordinary session, or another exam's, gets 403)."""
    in_exam = bool(scope and scope.startswith("exam:"))
    if req.route_scope == "exam":
        if not req.user:
            return                                          # 401 below
        if not in_exam or scope != f"exam:{req.params.get('id')}":
            raise HTTPError(403, "Bu imtahana imtahan səhifəsindən daxil olun")
        # Task 29: the exam's network list on every request; the refusal or the change of address is logged at once
        from ..modules.exam import service as exam
        problem = exam.check_request(req.db, int(req.params["id"]), req.user, req.ip, req.user.get("session_ip"), req.user["session_id"],
                                     req.path, bool(req.user.get("session_seb_ok")))
        _own_commit(req)
        if problem:
            raise HTTPError(403, problem)
    elif in_exam:
        raise HTTPError(403, "İmtahan sessiyası yalnız imtahan səhifəsinə açılır")


def after(req, ok):
    if req.db is not None:
        held = _TX_GUARD and ok and req.first_write is not None and time.monotonic() - req.first_write
        if held and held > 0.2 and not req.path.startswith(TX_GUARD_EXEMPT):
            raise AssertionError(f"{req.path} held the write lock for {held * 1000:.0f} ms (limit 200)")
        if ok and req.user and req.changes_from is not None and req.db.total_changes > req.changes_from:
            # Task 39: the request changed something; written last, so the write lock is held a moment longer at most
            try:
                events.record(req.db, req.user["id"], req.user["role"], req.endpoint.__name__, events.module_of(req.endpoint.__module__))
            except sqlite3.OperationalError as ex:
                # Checkpoint F (SF-F3): bookkeeping never fails the request it describes. Only a handler that committed its
                # own work (the screen import) needs a new write transaction here, and another writer may hold the lock
                print(f"event not recorded: {req.path}: {ex}", file=sys.stderr, flush=True)
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
OFFICE_SCOPE = ("{col} IN (SELECT s.id FROM users s JOIN study_groups sg ON sg.id=s.group_id WHERE sg.faculty_id IN "
                "(SELECT scope_id FROM role_grants WHERE user_id=? AND role='office' AND scope_type='faculty'))")


def scope_sql(u, col: str) -> tuple[str, tuple]:
    """A WHERE condition limiting ``col`` (a student id) to the students ``u`` serves, applied before any LIMIT."""
    if u["role"] != "office":
        return "1=1", ()
    return OFFICE_SCOPE.format(col=col), (u["id"],)


def serves(c, u, student_id) -> bool:
    """Whether a staff user may see this student's requests, documents and files (one indexed lookup)."""
    if u["role"] != "office":
        return True
    return row(c, "SELECT 1 FROM users s JOIN study_groups sg ON sg.id=s.group_id JOIN role_grants g ON g.scope_id=sg.faculty_id "
                  "WHERE s.id=? AND g.user_id=? AND g.role='office' AND g.scope_type='faculty' LIMIT 1", (student_id, u["id"])) is not None


def office_for(c, student_id) -> list[int]:
    """The office users whose faculty scope covers the student (who is told about a new request)."""
    return [r["user_id"] for r in rows(c, "SELECT DISTINCT g.user_id FROM role_grants g JOIN users u ON u.id=g.user_id "
                                          "JOIN study_groups sg ON sg.faculty_id=g.scope_id JOIN users s ON s.group_id=sg.id "
                                          "WHERE g.role='office' AND g.scope_type='faculty' AND s.id=? AND u.status='active'",
                                       (student_id,))]


# ---------------------------------------------------------------- e-service step actors (Task 46)
ACTORS = ("office", "academic_office", "dept_head")      # the roles a request type's step is assigned to; admin never is


def covers(c, u, role: str, student_id: int, data: dict) -> bool:
    """Whether ``u`` acting in ``role`` may act on this student's request: a dean's office on its faculty's students (Task
    13); a department head on the course the request names (its grants, as in the journal); an academic office on the
    whole university (its primary role or a grant without a scope) or on the faculties it was granted."""
    if role == "office":
        return serves(c, {**u, "role": "office"}, student_id)
    if role == "dept_head":
        course = data.get("course")
        co = row(c, "SELECT id, department_id FROM courses WHERE id=?", (course,)) if isinstance(course, int) else None
        from ..modules.journal import service as journal      # here: the journal's modules import this one
        return co is not None and journal.head_covers(c, u["id"], co["id"], co["department_id"])
    grants = rows(c, "SELECT scope_type, scope_id FROM role_grants WHERE user_id=? AND role=?", (u["id"], role))
    if u.get("primary_role", u["role"]) == role or any(g["scope_type"] is None for g in grants):
        return True
    fac = row(c, "SELECT sg.faculty_id FROM users s JOIN study_groups sg ON sg.id=s.group_id WHERE s.id=?", (student_id,))
    return bool(fac) and any(g["scope_type"] == "faculty" and g["scope_id"] == fac["faculty_id"] for g in grants)


def step_actors(c, role: str, student_id: int, data: dict) -> list[int]:
    """The active accounts holding ``role`` (as their primary role or a grant) whose scope covers this request: who is told
    that a step is theirs."""
    if role == "office":
        return office_for(c, student_id)
    held = rows(c, "SELECT id, role FROM users WHERE role=? AND status='active' UNION SELECT u.id, u.role FROM role_grants g "
                   "JOIN users u ON u.id=g.user_id WHERE g.role=? AND u.status='active'", (role, role))
    return [x["id"] for x in held if covers(c, {"id": x["id"], "role": role, "primary_role": x["role"]}, role, student_id, data)]


def may_read_request(c, u, r) -> bool:
    """A request is read by its student, the registry offices (a dean's office for its faculty, Task 13) and the roles its
    type's steps are assigned to, within their scope (Task 46)."""
    if u["role"] == "student":
        return r["student_id"] == u["id"]
    if u["role"] in STAFF:
        return serves(c, u, r["student_id"])
    t = row(c, "SELECT step_roles FROM request_types WHERE code=?", (r["type_code"],))
    return u["role"] in ACTORS and bool(t) and u["role"] in (J(t["step_roles"], []) or []) and \
        covers(c, u, u["role"], r["student_id"], J(r["data"], {}) or {})


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
    return row(req.db, "SELECT * FROM users WHERE id=? AND status='active'", (entry["user_id"],))


def ctx(c):
    uni = setting(c, "university")
    return {"university": uni, "faculty": setting(c, "faculty"), "specialty": setting(c, "specialty"),
            "semester": uni["semester"], "base_url": BASE_URL["value"], "grading": tenant.load(c)["grading"]}


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


def course_access(req, cid, head: bool = False):
    """The course, when the user may work in it: its students, the head teacher and the teachers of its active teaching
    units (Task 13), staff. ``head``: the course's own settings (tutor, tools), its head teacher only (Checkpoint C, S1)."""
    c, u = req.db, req.user
    course = row(c, "SELECT * FROM courses WHERE id=?", (cid,))
    if not course:
        raise HTTPError(404, "Fənn tapılmadı")
    if u["role"] == "student" and not row(c, "SELECT 1 FROM enrollments WHERE user_id=? AND course_id=?", (u["id"], cid)):
        raise HTTPError(403, "Bu fənnə qeydiyyatınız yoxdur")
    if u["role"] == "teacher" and course["teacher_id"] != u["id"] and (head or not row(
            c, "SELECT 1 FROM teaching_units WHERE course_id=? AND teacher_id=? AND active=1", (cid, u["id"]))):
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
