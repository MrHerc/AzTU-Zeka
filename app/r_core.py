"""Core routes: auth, profile, notifications, search, guide, files."""
from __future__ import annotations

import base64
import json
import secrets
import urllib.parse

from . import engine, pdftext, store
from .common import R, ROLE_HOME, STAFF, ctx, holder, make_key, pub_user, session_cookie, _sid
from .i18n import L, norm_lang, tr
from .store import J, audit, iso, now, row, rows, setting
from .web import HTTPError, Response, json_resp, redirect


def _login(c, role):
    logins = setting(c, "demo_logins")
    if role not in logins:
        raise HTTPError(400, "Naməlum rol")
    u = row(c, "SELECT * FROM users WHERE username=?", (logins[role],))
    sid = secrets.token_urlsafe(24)
    c.execute("INSERT INTO sessions(sid,user_id,created_at) VALUES(?,?,?)", (sid, u["id"], iso(now())))
    audit(c, u["id"], "login", "session", f"demo rol: {role}")
    return u, sid, [session_cookie(sid)]


def unread(c, uid):
    return row(c, "SELECT COUNT(*) n FROM notifications WHERE user_id=? AND read_at IS NULL", (uid,))["n"]


@R("GET", "/api/bootstrap", auth=False)
def bootstrap(req):
    c, u = req.db, req.user
    ct = store._load("contacts.json")
    info = {**ctx(c), "engine": engine.engine_info(), "news_kinds": setting(c, "news_kinds", {}), "version": "0.3",
            "langs": ["az", "en", "ru"], "vendor": "Safarov Industries",
            "contact": {k: ct[k] for k in ("phone", "phone_href", "email", "website", "address")}}
    return {"user": pub_user(u), "app": info, "home": ROLE_HOME.get(u["role"]) if u else None, "unread": unread(c, u["id"]) if u else 0}


@R("POST", "/api/auth/demo", auth=False)
def demo_login(req):
    u, sid, headers = _login(req.db, req.json().get("role"))
    return json_resp({"user": pub_user(u), "home": ROLE_HOME[u["role"]], "token": sid}, headers=headers)


@R("GET", "/demo/login", auth=False)
def demo_login_get(req):
    u, _, headers = _login(req.db, req.query.get("role", "student"))
    nxt = req.query.get("next") or "/#" + ROLE_HOME[u["role"]]
    if not nxt.startswith("/") or nxt.startswith("//") or "\\" in nxt:
        nxt = "/"
    return redirect(nxt, headers)


@R("POST", "/api/auth/logout")
def logout(req):
    req.db.execute("DELETE FROM sessions WHERE sid=?", (_sid(req),))
    return json_resp({"ok": True}, headers=[session_cookie(expire=True)])


@R("POST", "/api/consent")
def consent(req):
    req.db.execute("UPDATE users SET consent_at=? WHERE id=?", (iso(now()), req.user["id"]))
    audit(req.db, req.user["id"], "consent", "user", json.dumps(req.json(), ensure_ascii=False))
    return {"ok": True, "consent_at": iso(now())}


# ---------------------------------------------------------------- profile
@R("GET", "/api/me")
def me(req):
    c, u = req.db, req.user
    h = holder(c, u["id"])
    out = pub_user(u)
    out.update({k: h.get(k) for k in ("patronymic", "student_no", "admission_year", "funding", "form", "dept", "group", "year")})
    out["university"] = setting(c, "university")
    out["faculty"] = setting(c, "faculty")
    out["specialty"] = setting(c, "specialty")
    return out


@R("PUT", "/api/me/prefs")
def me_prefs(req):
    c, u = req.db, req.user
    prefs = J(u.get("prefs"), {}) or {}
    b = req.json()
    if isinstance(b.get("tours"), list):
        prefs["tours"] = sorted({str(x)[:60] for x in b["tours"]})[:120]
    if b.get("theme") in ("light", "dark"):
        prefs["theme"] = b["theme"]
    if norm_lang(b.get("lang")):
        prefs["lang"] = norm_lang(b.get("lang"))
    if isinstance(b.get("sidebar"), str) and b["sidebar"] in ("open", "collapsed"):
        prefs["sidebar"] = b["sidebar"]
    c.execute("UPDATE users SET prefs=? WHERE id=?", (json.dumps(prefs, ensure_ascii=False), u["id"]))
    return {"prefs": prefs}


# ---------------------------------------------------------------- notifications
@R("GET", "/api/badges")
def badges(req):
    c, u = req.db, req.user
    out = {"notifications": unread(c, u["id"])}
    aud = ("all", "students") if u["role"] == "student" else ("all", "teachers") if u["role"] == "teacher" else ("all", "students", "teachers")
    out["news"] = row(c, f"SELECT COUNT(*) n FROM news n WHERE status='published' AND audience IN ({','.join('?' * len(aud))}) "
                         "AND NOT EXISTS (SELECT 1 FROM news_reads r WHERE r.news_id=n.id AND r.user_id=?)", (*aud, u["id"]))["n"]
    if u["role"] == "student":
        out["requests"] = row(c, "SELECT COUNT(*) n FROM requests WHERE student_id=? AND status IN ('submitted','in_progress','returned')", (u["id"],))["n"]
        out["absences"] = row(c, "SELECT COUNT(*) n FROM attendance WHERE user_id=? AND status='absent'", (u["id"],))["n"]
    elif u["role"] == "teacher":
        out["questions"] = row(c, "SELECT COUNT(*) n FROM teacher_questions tq JOIN courses co ON co.id=tq.course_id WHERE co.teacher_id=? AND tq.status='open'", (u["id"],))["n"]
    else:
        out["office"] = row(c, "SELECT COUNT(*) n FROM requests WHERE status='submitted'")["n"]
    if u["role"] in ("office", "admin"):
        out["support"] = row(c, "SELECT COUNT(*) n FROM support_tickets WHERE status='open'")["n"]
    else:
        out["support"] = row(c, "SELECT COUNT(*) n FROM support_tickets WHERE user_id=? AND status='waiting'", (u["id"],))["n"]
    return out


@R("GET", "/api/notifications")
def notifications(req):
    c, u = req.db, req.user
    items = rows(c, "SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 40", (u["id"],))
    return {"items": items, "unread": unread(c, u["id"])}


@R("POST", "/api/notifications/read")
def notifications_read(req):
    c, u = req.db, req.user
    b = req.json()
    if b.get("all"):
        c.execute("UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL", (iso(now()), u["id"]))
    else:
        ids = [int(i) for i in (b.get("ids") or [])][:100]
        if ids:
            c.execute(f"UPDATE notifications SET read_at=? WHERE user_id=? AND id IN ({','.join('?' * len(ids))})", (iso(now()), u["id"], *ids))
    return {"unread": unread(c, u["id"])}


# ---------------------------------------------------------------- guide
def guide_items(c, role):
    data = store._load("guide.json")
    return [a for a in data["articles"] if role in a["roles"]]


@R("GET", "/api/guide")
def guide(req):
    data = store._load("guide.json")
    return {"articles": guide_items(req.db, req.user["role"]), "faq": [f for f in data["faq"] if req.user["role"] in f["roles"]],
            "shortcuts": data["shortcuts"]}


# ---------------------------------------------------------------- search
def _hay(*parts):
    """Searchable text in all UI languages (content is stored in Azerbaijani)."""
    out = []
    for p in parts:
        if isinstance(p, dict):
            out.extend(str(v) for v in p.values())
        elif p:
            out.extend([str(p), str(tr(p, "en")), str(tr(p, "ru"))])
    return " ".join(out)


def _hit(text, words):
    t = engine.fold(text)
    return all(w in t for w in words)


@R("GET", "/api/search")
def search(req):
    c, u = req.db, req.user
    q = (req.query.get("q") or "").strip()
    words = [w for w in engine.fold(q).split() if len(w) >= 2]
    if not words:
        return {"results": []}
    out = []
    role = u["role"]
    if role in ("student",) + STAFF:
        for t in rows(c, "SELECT code, name, icon, description FROM request_types ORDER BY seq"):
            if _hit(_hay(t["name"], t["description"]), words):
                link = f"/student/services?new={t['code']}" if role == "student" else f"/office?type={t['code']}"
                out.append({"group": "E-xidmətlər", "title": t["name"], "sub": t["description"], "link": link, "icon": t["icon"]})
    for n in rows(c, "SELECT id, title, summary, kind FROM news WHERE status='published' AND (audience='all' OR audience=?) ORDER BY published_at DESC",
                  ("teachers" if role == "teacher" else "students",)):
        if _hit(_hay(n["title"], n["summary"]), words):
            out.append({"group": "Xəbərlər", "title": n["title"], "sub": n["summary"], "link": f"/news/{n['id']}", "icon": "news"})
    for a in store._load("achievements.json")["items"]:
        if _hit(_hay(a["title"], a["summary"], a["highlight"]), words):
            out.append({"group": "AzTU-nun nailiyyətləri", "title": a["title"], "sub": a["highlight"], "link": f"/achievements?id={a['id']}", "icon": a["icon"]})
    if role == "student":
        cs = rows(c, "SELECT co.* FROM courses co JOIN enrollments e ON e.course_id=co.id WHERE e.user_id=?", (u["id"],))
    elif role == "teacher":
        cs = rows(c, "SELECT * FROM courses WHERE teacher_id=?", (u["id"],))
    else:
        cs = rows(c, "SELECT * FROM courses")
    cids = {co["id"] for co in cs}
    for co in cs:
        if _hit(_hay(co["name"]) + " " + co["code"], words):
            out.append({"group": "Fənlər", "title": co["name"], "sub": co["code"], "icon": "book",
                        "link": f"/student/course/{co['id']}" if role == "student" else f"/teacher/course/{co['id']}"})
    if role in ("student", "teacher"):
        for h in engine.INDEX["chunks"].search(q, k=4, where=lambda m: m["course_id"] in cids):
            if h["score"] >= 1.5:
                link = f"/student/tutor/{h['course_id']}?q={urllib.parse.quote(h['heading'] + ' mövzusunu izah et')}&mode=explain" if role == "student" \
                    else f"/teacher/course/{h['course_id']}"
                # A section heading is course content: the same text in every language, never matched against the UI catalog
                heading = {lg: h["heading"] for lg in ("az", "en", "ru")}
                out.append({"group": "Fənn materialları", "title": heading, "sub": h["material"], "link": link, "icon": "file"})
    if role == "teacher":
        for m in rows(c, "SELECT m.id, m.title, t.title track FROM academy_modules m JOIN academy_tracks t ON t.key=m.track_key"):
            if _hit(_hay(m["title"], m["track"]), words):
                out.append({"group": "AI Akademiya", "title": m["title"], "sub": m["track"], "link": f"/teacher/academy/module/{m['id']}", "icon": "cap"})
        for t in rows(c, "SELECT key, name, summary FROM tools"):
            if _hit(_hay(t["summary"]) + " " + t["name"], words):
                out.append({"group": "Texnoloji həllər", "title": t["name"], "sub": t["summary"], "link": f"/teacher/tools?tool={t['key']}", "icon": "cpu"})
    for a in guide_items(c, role):
        if _hit(_hay(a["title"], a["summary"], " ".join(a.get("tags", []))), words):
            out.append({"group": "Bələdçi", "title": a["title"], "sub": a["summary"], "link": f"/guide/{a['id']}", "icon": "help"})
    return {"results": out[:24]}


# ---------------------------------------------------------------- files
@R("POST", "/api/files")
def upload_file(req):
    b = req.json()
    try:
        data = base64.b64decode(b.get("content_b64") or "", validate=False)
    except ValueError:
        raise HTTPError(400, "Fayl oxunmadı")
    try:
        f = store.save_file(req.db, req.user["id"], (b.get("filename") or "fayl")[:160], data, b.get("accept") or "doc")
    except ValueError as ex:
        raise HTTPError(400, str(ex))
    return {k: f[k] for k in ("id", "filename", "mime", "size")}


def file_access(req, fid):
    c, u = req.db, req.user
    f = row(c, "SELECT * FROM files WHERE id=?", (fid,))
    if not f:
        raise HTTPError(404, "Fayl tapılmadı")
    if f["owner_id"] != u["id"] and u["role"] not in ("office", "admin"):
        raise HTTPError(403, "Bu fayla baxmaq icazəniz yoxdur")
    return f


@R("POST", "/api/files/{id:int}/link")
def file_link(req):
    f = file_access(req, req.params["id"])
    return {"url": f"/api/files/{f['id']}?k={make_key('file', f['id'], req.user['id'])}"}


@R("GET", "/api/files/{id:int}")
def file_get(req):
    f = file_access(req, req.params["id"])
    data = (store.UPLOADS / f["path"]).read_bytes()
    fname = urllib.parse.quote(f["filename"])
    audit(req.db, req.user["id"], "file_view", "file", f"#{f['id']} {f['filename']}")
    disp = "attachment" if req.query.get("download") == "1" else "inline"
    return Response(data, 200, f["mime"], [("Content-Disposition", f"{disp}; filename*=UTF-8''{fname}"),
                                           ("Cache-Control", "private, no-store")])


@R("GET", "/api/files/{id:int}/preview")
def file_preview(req):
    """Text preview rendered inside the app (works where the browser has no PDF viewer)."""
    f = file_access(req, req.params["id"])
    data = (store.UPLOADS / f["path"]).read_bytes()
    out = {"id": f["id"], "filename": f["filename"], "mime": f["mime"], "size": f["size"], "created_at": f["created_at"], "pages": []}
    if f["mime"] == "application/pdf":
        out["kind"] = "pdf"
        try:
            out["pages"] = [p for p in pdftext.extract_pages(data) if p.strip()]
        except Exception:  # malformed PDFs fall back to "download"
            out["pages"] = []
    elif f["mime"].startswith("image/"):
        out["kind"] = "image"
    elif f["filename"].lower().endswith(".docx"):
        out["kind"] = "docx"
        try:
            out["pages"] = [engine.extract_text(f["filename"], data)]
        except Exception:
            out["pages"] = []
    else:
        out["kind"] = "other"
    audit(req.db, req.user["id"], "file_preview", "file", f"#{f['id']} {f['filename']}")
    return out
