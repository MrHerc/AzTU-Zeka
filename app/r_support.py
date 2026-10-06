"""Support desk, feedback, system status, AzTU achievements and contacts."""
from __future__ import annotations

import time
from datetime import datetime, timedelta

from . import engine, store, support
from .common import R
from .i18n import S_, T3
from .store import audit, iso, notify, now, row, rows
from .web import HTTPError

STARTED = time.time()
DESK = ("office", "admin")          # who works the support queue
INSIGHT = ("office", "admin", "leader")


def ticket_out(c, t, me=None):
    u = row(c, "SELECT full_name, role, color FROM users WHERE id=?", (t["user_id"],)) or {}
    a = row(c, "SELECT full_name FROM users WHERE id=?", (t["assignee_id"],)) if t["assignee_id"] else None
    created = datetime.fromisoformat(t["created_at"])
    due = created + timedelta(hours=support.SLA_HOURS.get(t["priority"], 24))
    first = row(c, "SELECT MIN(m.created_at) ts FROM support_messages m WHERE m.ticket_id=? AND m.internal=0 AND m.author_id<>?",
                (t["id"], t["user_id"]))["ts"]
    out = {k: t[k] for k in ("id", "category", "priority", "subject", "body", "page", "status", "rating", "created_at", "updated_at", "closed_at")}
    out.update({"user": u.get("full_name", ""), "user_role": u.get("role", ""), "user_color": u.get("color", "#64748b"),
                "assignee": a["full_name"] if a else "", "assignee_id": t["assignee_id"], "mine": bool(me and t["user_id"] == me["id"]),
                "due_at": iso(due), "first_response_at": first,
                "overdue": t["status"] in support.OPEN and not first and now() > due,
                "messages": row(c, "SELECT COUNT(*) n FROM support_messages WHERE ticket_id=? AND internal=0", (t["id"],))["n"]})
    return out


def _ticket_for(req, tid):
    t = row(req.db, "SELECT * FROM support_tickets WHERE id=?", (tid,))
    if not t or (req.user["role"] not in DESK + ("leader",) and t["user_id"] != req.user["id"]):
        raise HTTPError(404, "Sorğu tapılmadı")
    return t


def _desk_ids(c):
    return [r["id"] for r in rows(c, "SELECT id FROM users WHERE role IN ('office','admin') AND synthetic=0")]


@R("GET", "/api/support/meta")
def support_meta(req):
    return {"categories": [{"key": k, "icon": i, "name": n} for k, i, n in support.CATEGORIES],
            "priorities": [{"key": k, "name": n, "sla_hours": support.SLA_HOURS[k]} for k, n in support.PRIORITIES],
            "statuses": [{"key": k, "name": n} for k, n in support.STATUSES],
            "areas": [{"key": k, "name": n} for k, n in support.AREAS],
            "score_labels": support.SCORE_LABELS, "desk": req.user["role"] in DESK}


@R("GET", "/api/support/tickets")
def tickets(req):
    c, u = req.db, req.user
    staff_view = u["role"] in DESK + ("leader",) and req.query.get("scope") == "all"
    sql, args = "SELECT * FROM support_tickets WHERE 1=1", []
    if not staff_view:
        sql += " AND user_id=?"
        args.append(u["id"])
    st = req.query.get("status")
    if st == "open":
        sql += " AND status IN ('open','in_progress','waiting')"
    elif st == "done":
        sql += " AND status IN ('resolved','closed')"
    elif st in support.CODES["status"]:
        sql += " AND status=?"
        args.append(st)
    if req.query.get("category") in support.CODES["category"]:
        sql += " AND category=?"
        args.append(req.query["category"])
    if req.query.get("mine") == "1" and staff_view:
        sql += " AND assignee_id=?"
        args.append(u["id"])
    sql += (" ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'in_progress' THEN 1 WHEN 'waiting' THEN 2 ELSE 3 END,"
            " CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, id DESC")
    out = [ticket_out(c, t, u) for t in rows(c, sql, tuple(args))]
    q = (req.query.get("q") or "").strip().lower()
    if q:
        out = [t for t in out if q in t["subject"].lower() or q in t["user"].lower() or q == str(t["id"])]
    return out


@R("POST", "/api/support/tickets")
def ticket_create(req):
    c, u = req.db, req.user
    b = req.json()
    cat = b.get("category") if b.get("category") in support.CODES["category"] else "other"
    prio = b.get("priority") if b.get("priority") in support.CODES["priority"] else "normal"
    subject = (b.get("subject") or "").strip()[:140]
    body = (b.get("body") or "").strip()[:4000]
    if len(subject) < 4:
        raise HTTPError(400, "Mövzunu qısa şəkildə yazın (ən azı 4 simvol)")
    if len(body) < 10:
        raise HTTPError(400, "Problemi bir-iki cümlə ilə təsvir edin")
    t = iso(now())
    tid = c.execute("INSERT INTO support_tickets(user_id,category,priority,subject,body,page,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (u["id"], cat, prio, subject, body, str(b.get("page") or "")[:200], "open", t, t)).lastrowid
    fid = b.get("file_id")
    if fid:
        f = row(c, "SELECT id FROM files WHERE id=? AND owner_id=? AND request_id IS NULL", (int(fid), u["id"]))
        if f:
            c.execute("INSERT INTO support_messages(ticket_id,author_id,text,internal,file_id,created_at) VALUES(?,?,?,?,?,?)",
                      (tid, u["id"], "", 0, f["id"], t))
    notify(c, _desk_ids(c), "support", T3("Yeni dəstək sorğusu № {id}", id=tid), f"{u['full_name']}: {subject[:90]}", f"/staff/support/{tid}")
    audit(c, u["id"], "support_create", "ticket", f"#{tid} {cat}/{prio}")
    return ticket_get_by_id(req, tid)


def ticket_get_by_id(req, tid):
    c, u = req.db, req.user
    t = _ticket_for(req, tid)
    out = ticket_out(c, t, u)
    staff = u["role"] in DESK
    out["thread"] = rows(c, "SELECT m.id, m.text, m.internal, m.created_at, m.file_id, f.filename, f.mime, f.size, u.full_name author, u.role author_role, u.color "
                            "FROM support_messages m JOIN users u ON u.id=m.author_id LEFT JOIN files f ON f.id=m.file_id "
                            "WHERE m.ticket_id=? " + ("" if staff else "AND m.internal=0 ") + "ORDER BY m.id", (t["id"],))
    out["can_reply"] = t["status"] != "closed" and (staff or t["user_id"] == u["id"])
    out["can_manage"] = staff
    out["can_rate"] = t["user_id"] == u["id"] and t["status"] in ("resolved", "closed") and not t["rating"]
    out["can_reopen"] = t["user_id"] == u["id"] and t["status"] in ("resolved", "closed")
    return out


@R("GET", "/api/support/tickets/{id:int}")
def ticket_get(req):
    return ticket_get_by_id(req, req.params["id"])


@R("POST", "/api/support/tickets/{id:int}/messages")
def ticket_reply(req):
    c, u = req.db, req.user
    t = _ticket_for(req, req.params["id"])
    b = req.json()
    text = (b.get("text") or "").strip()[:4000]
    staff = u["role"] in DESK
    if not text:
        raise HTTPError(400, "Mesaj boşdur")
    if t["status"] == "closed":
        raise HTTPError(409, "Sorğu bağlanıb. Yenidən açaraq yaza bilərsiniz.")
    if not staff and t["user_id"] != u["id"]:
        raise HTTPError(403, "Bu sorğuya cavab yaza bilməzsiniz")
    internal = bool(b.get("internal")) and staff
    ts = iso(now())
    c.execute("INSERT INTO support_messages(ticket_id,author_id,text,internal,created_at) VALUES(?,?,?,?,?)", (t["id"], u["id"], text, int(internal), ts))
    status = t["status"]
    if staff and not internal:
        status = b.get("status") if b.get("status") in ("in_progress", "waiting", "resolved") else ("in_progress" if status == "open" else status)
        notify(c, t["user_id"], "support", T3("Dəstək xidməti sorğunuza cavab verdi"), f"№ {t['id']} · {t['subject'][:80]}", f"/support/{t['id']}")
    elif not staff:
        status = "in_progress" if status in ("waiting", "resolved") else status
        if t["assignee_id"]:
            notify(c, t["assignee_id"], "support", T3("Sorğuya yeni mesaj (№ {id})", id=t["id"]), f"{u['full_name']}: {text[:80]}", f"/staff/support/{t['id']}")
    c.execute("UPDATE support_tickets SET status=?, updated_at=?, assignee_id=COALESCE(assignee_id, ?), closed_at=? WHERE id=?",
              (status, ts, u["id"] if staff else None, ts if status in ("resolved", "closed") else None, t["id"]))
    return ticket_get_by_id(req, t["id"])


@R("POST", "/api/support/tickets/{id:int}/status", roles=DESK)
def ticket_status(req):
    c, u = req.db, req.user
    t = _ticket_for(req, req.params["id"])
    b = req.json()
    st = b.get("status")
    ts = iso(now())
    if b.get("assign") == "me":
        c.execute("UPDATE support_tickets SET assignee_id=?, updated_at=? WHERE id=?", (u["id"], ts, t["id"]))
    if b.get("priority") in support.CODES["priority"]:
        c.execute("UPDATE support_tickets SET priority=?, updated_at=? WHERE id=?", (b["priority"], ts, t["id"]))
    if st:
        if st not in support.CODES["status"]:
            raise HTTPError(400, "Naməlum status")
        c.execute("UPDATE support_tickets SET status=?, updated_at=?, closed_at=?, assignee_id=COALESCE(assignee_id, ?) WHERE id=?",
                  (st, ts, ts if st in ("resolved", "closed") else None, u["id"], t["id"]))
        if st in ("resolved", "closed", "waiting"):
            title = {"resolved": T3("Sorğunuz həll olundu"), "closed": T3("Sorğunuz bağlandı"),
                     "waiting": T3("Sorğunuz üzrə cavabınız gözlənilir")}[st]
            notify(c, t["user_id"], "support", title, f"№ {t['id']} · {t['subject'][:80]}", f"/support/{t['id']}")
    audit(c, u["id"], "support_update", "ticket", f"#{t['id']} {st or ''}")
    return ticket_get_by_id(req, t["id"])


@R("POST", "/api/support/tickets/{id:int}/rate")
def ticket_rate(req):
    c, u = req.db, req.user
    t = _ticket_for(req, req.params["id"])
    r = int(req.json().get("rating") or 0)
    if t["user_id"] != u["id"] or t["status"] not in ("resolved", "closed"):
        raise HTTPError(409, "Yalnız həll olunmuş sorğunu qiymətləndirmək olar")
    if not 1 <= r <= 5:
        raise HTTPError(400, "Qiymət 1-dən 5-ə qədər olmalıdır")
    c.execute("UPDATE support_tickets SET rating=? WHERE id=?", (r, t["id"]))
    return ticket_get_by_id(req, t["id"])


@R("POST", "/api/support/tickets/{id:int}/reopen")
def ticket_reopen(req):
    c, u = req.db, req.user
    t = _ticket_for(req, req.params["id"])
    if t["user_id"] != u["id"] or t["status"] not in ("resolved", "closed"):
        raise HTTPError(409, "Bu sorğunu yenidən açmaq mümkün deyil")
    c.execute("UPDATE support_tickets SET status='open', closed_at=NULL, rating=NULL, updated_at=? WHERE id=?", (iso(now()), t["id"]))
    if t["assignee_id"]:
        notify(c, t["assignee_id"], "support", T3("Sorğu yenidən açıldı (№ {id})", id=t["id"]), t["subject"][:90], f"/staff/support/{t['id']}")
    return ticket_get_by_id(req, t["id"])


@R("GET", "/api/support/summary", roles=INSIGHT)
def support_summary(req):
    c = req.db
    ts = rows(c, "SELECT * FROM support_tickets")
    outs = [ticket_out(c, t) for t in ts]
    resp = [(datetime.fromisoformat(o["first_response_at"]) - datetime.fromisoformat(o["created_at"])).total_seconds() / 3600
            for o in outs if o["first_response_at"]]
    rated = [t["rating"] for t in ts if t["rating"]]
    by_cat = {}
    for t in ts:
        by_cat[t["category"]] = by_cat.get(t["category"], 0) + 1
    return {"total": len(ts), "open": sum(t["status"] == "open" for t in ts), "in_progress": sum(t["status"] == "in_progress" for t in ts),
            "waiting": sum(t["status"] == "waiting" for t in ts), "resolved": sum(t["status"] in ("resolved", "closed") for t in ts),
            "overdue": sum(o["overdue"] for o in outs), "avg_first_response_h": round(sum(resp) / len(resp), 1) if resp else None,
            "csat": round(sum(rated) / len(rated), 2) if rated else None,
            "by_category": [{"key": k, "name": n, "n": by_cat.get(k, 0)} for k, _, n in support.CATEGORIES]}


# ---------------------------------------------------------------- feedback
@R("POST", "/api/feedback")
def feedback_create(req):
    c, u = req.db, req.user
    b = req.json()
    try:
        score = int(b.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    if not 1 <= score <= 5:
        raise HTTPError(400, "Qiymət seçin")
    nps = b.get("nps")
    nps = int(nps) if isinstance(nps, (int, float)) and 0 <= int(nps) <= 10 else None
    area = b.get("area") if b.get("area") in support.CODES["area"] else "overall"
    c.execute("INSERT INTO feedback(user_id,role,area,score,nps,comment,page,lang,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
              (u["id"], u["role"], area, score, nps, (b.get("comment") or "").strip()[:2000], str(b.get("page") or "")[:200], req.lang, iso(now())))
    audit(c, u["id"], "feedback", "feedback", f"{area}:{score}")
    return {"ok": True}


@R("GET", "/api/feedback/summary", roles=INSIGHT)
def feedback_summary(req):
    c = req.db
    fb = rows(c, "SELECT f.*, u.full_name FROM feedback f LEFT JOIN users u ON u.id=f.user_id ORDER BY f.created_at DESC")
    n = len(fb)
    dist = [sum(f["score"] == s for f in fb) for s in range(1, 6)]
    npsv = [f["nps"] for f in fb if f["nps"] is not None]
    nps = round(100 * (sum(v >= 9 for v in npsv) - sum(v <= 6 for v in npsv)) / len(npsv)) if npsv else None
    weeks = []
    t0 = now()
    for w in range(7, -1, -1):
        a, b_ = t0 - timedelta(days=7 * (w + 1)), t0 - timedelta(days=7 * w)
        sel = [f["score"] for f in fb if iso(a) <= f["created_at"] < iso(b_)]
        weeks.append({"n": len(sel), "avg": round(sum(sel) / len(sel), 2) if sel else None})
    by_area = []
    for k, name in support.AREAS:
        sel = [f["score"] for f in fb if f["area"] == k]
        if sel:
            by_area.append({"key": k, "name": name, "n": len(sel), "avg": round(sum(sel) / len(sel), 2)})
    recent = [{"score": f["score"], "area": f["area"], "area_name": dict(support.AREAS).get(f["area"], ""), "comment": f["comment"],
               "role": f["role"], "created_at": f["created_at"], "synthetic": f["synthetic"]} for f in fb if f["comment"]][:12]
    return {"count": n, "avg": round(sum(f["score"] for f in fb) / n, 2) if n else None, "distribution": dist, "nps": nps,
            "nps_responses": len(npsv), "weekly": weeks, "by_area": sorted(by_area, key=lambda x: -x["avg"]), "recent": recent,
            "labels": support.SCORE_LABELS}


# ---------------------------------------------------------------- system status
@R("GET", "/api/system/status")
def system_status(req):
    c = req.db
    up = int(time.time() - STARTED)
    eng = engine.engine_info()
    db_ok = bool(row(c, "SELECT 1 ok"))
    comps = [
        {"key": "portal", "status": "operational", "name": S_("Portal və e-xidmətlər"), "note": T3("Fasiləsiz iş: {h} saat {m} dəq", h=up // 3600, m=up % 3600 // 60)},
        {"key": "db", "status": "operational" if db_ok else "down", "name": S_("Verilənlər bazası"), "note": T3("Əlaqə normaldır") if db_ok else T3("Əlaqə yoxdur")},
        {"key": "ai", "status": "operational" if eng["mode"] == "llm" else "degraded", "name": S_("AI mühərriki"),
         "note": T3("Xarici LLM qoşulub") if eng["mode"] == "llm" else T3("Demo rejimi: oflayn mühərrik işləyir")},
        {"key": "notify", "status": "operational", "name": S_("Bildirişlər"), "note": T3("Platformadaxili bildirişlər aktivdir")},
        {"key": "sso", "status": "planned", "name": S_("Universitet hesabı ilə giriş (SSO)"), "note": T3("Pilot mərhələsində qoşulacaq")},
        {"key": "lms", "status": "planned", "name": S_("LMS və tələbə reyestri inteqrasiyası"), "note": T3("Pilot mərhələsində qoşulacaq")},
    ]
    return {"components": comps, "checked_at": iso(now()), "uptime_s": up,
            "overall": "degraded" if any(x["status"] in ("degraded", "down") for x in comps) else "operational"}


# ---------------------------------------------------------------- AzTU achievements & contacts (real, sourced)
@R("GET", "/api/achievements", auth=False)
def achievements(req):
    data = store._load("achievements.json")
    dated = sorted([i for i in data["items"] if i["date"]], key=lambda x: x["date"], reverse=True)
    undated = [i for i in data["items"] if not i["date"]]
    counts = {}
    for i in data["items"]:
        counts[i["category"]] = counts.get(i["category"], 0) + 1
    cats = [{**k, "n": counts.get(k["key"], 0)} for k in data["categories"]]
    return {"categories": cats, "stats": data["stats"], "items": dated + undated, "checked": "2026-10-02",
            "sources": ["https://aztu.edu.az/news", "https://edu.gov.az"]}


@R("GET", "/api/contact", auth=False)
def contact(req):
    return store._load("contacts.json")
