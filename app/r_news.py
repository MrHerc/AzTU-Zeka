"""News portal: feed, events with registration, bookmarks, calendar export, editor."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from .common import R, STAFF
from .i18n import T3
from .store import J, audit, iso, notify, now, row, rows, setting
from .web import HTTPError, Response

KINDS = ("news", "event", "announcement", "opportunity", "career", "campus")
TONES = ("navy", "blue", "coral", "green", "amber", "violet", "teal")


def audience_for(u):
    return {"student": ("all", "students"), "teacher": ("all", "teachers")}.get(u["role"], ("all", "students", "teachers"))


def news_out(c, n, uid, full=False):
    out = {k: n[k] for k in ("id", "kind", "title", "summary", "audience", "published_at", "event_start", "event_end", "location", "capacity", "status")}
    out.update({"cover": J(n["cover"], {}), "tags": J(n["tags"], []), "pinned": bool(n["pinned"]), "important": bool(n["important"]),
                "registration": bool(n["registration"])})
    out["registered_count"] = row(c, "SELECT COUNT(*) n FROM news_rsvp WHERE news_id=?", (n["id"],))["n"]
    out["registered"] = bool(row(c, "SELECT 1 FROM news_rsvp WHERE news_id=? AND user_id=?", (n["id"], uid)))
    out["saved"] = bool(row(c, "SELECT 1 FROM news_saved WHERE news_id=? AND user_id=?", (n["id"], uid)))
    out["read"] = bool(row(c, "SELECT 1 FROM news_reads WHERE news_id=? AND user_id=?", (n["id"], uid)))
    out["past"] = bool(n["event_end"] and n["event_end"] < iso(now()))
    if full:
        out["body"] = n["body"]
        au = row(c, "SELECT full_name FROM users WHERE id=?", (n["author_id"],))
        out["author"] = au["full_name"] if au else ""
        out["reads"] = row(c, "SELECT COUNT(*) n FROM news_reads WHERE news_id=?", (n["id"],))["n"]
    return out


def _get(req, nid):
    n = row(req.db, "SELECT * FROM news WHERE id=?", (nid,))
    if not n or (n["audience"] not in audience_for(req.user)) or (n["status"] != "published" and req.user["role"] not in STAFF):
        raise HTTPError(404, "Xəbər tapılmadı")
    return n


@R("GET", "/api/news")
def news_list(req):
    c, u = req.db, req.user
    aud = audience_for(u)
    sql = f"SELECT * FROM news WHERE status='published' AND audience IN ({','.join('?' * len(aud))})"
    args = list(aud)
    if req.query.get("kind") in KINDS:
        sql += " AND kind=?"
        args.append(req.query["kind"])
    items = [news_out(c, n, u["id"]) for n in rows(c, sql + " ORDER BY pinned DESC, published_at DESC", tuple(args))]
    q = (req.query.get("q") or "").strip().lower()
    if q:
        items = [n for n in items if q in n["title"].lower() or q in n["summary"].lower() or any(q in t.lower() for t in n["tags"])]
    if req.query.get("saved"):
        items = [n for n in items if n["saved"]]
    if req.query.get("mine"):
        items = [n for n in items if n["registered"]]
    upcoming = sorted([n for n in items if n["event_start"] and not n["past"]], key=lambda n: n["event_start"])
    return {"items": items, "upcoming": upcoming[:6], "kinds": setting(c, "news_kinds", {}),
            "unread": sum(1 for n in items if not n["read"])}


@R("GET", "/api/news/{id:int}")
def news_detail(req):
    c, u = req.db, req.user
    n = _get(req, req.params["id"])
    c.execute("INSERT OR IGNORE INTO news_reads(news_id,user_id) VALUES(?,?)", (n["id"], u["id"]))
    out = news_out(c, n, u["id"], full=True)
    related = [news_out(c, x, u["id"]) for x in rows(c, "SELECT * FROM news WHERE status='published' AND kind=? AND id<>? ORDER BY published_at DESC LIMIT 3",
                                                       (n["kind"], n["id"])) if x["audience"] in audience_for(u)]
    return {**out, "related": related}


@R("POST", "/api/news/{id:int}/rsvp")
def news_rsvp(req):
    c, u = req.db, req.user
    n = _get(req, req.params["id"])
    if not n["registration"]:
        raise HTTPError(400, "Bu tədbir üçün qeydiyyat tələb olunmur")
    if n["event_end"] and n["event_end"] < iso(now()):
        raise HTTPError(409, "Tədbir artıq başa çatıb")
    if row(c, "SELECT 1 FROM news_rsvp WHERE news_id=? AND user_id=?", (n["id"], u["id"])):
        c.execute("DELETE FROM news_rsvp WHERE news_id=? AND user_id=?", (n["id"], u["id"]))
    else:
        cnt = row(c, "SELECT COUNT(*) n FROM news_rsvp WHERE news_id=?", (n["id"],))["n"]
        if n["capacity"] and cnt >= n["capacity"]:
            raise HTTPError(409, "Təəssüf ki, bütün yerlər tutulub")
        c.execute("INSERT INTO news_rsvp(news_id,user_id,created_at) VALUES(?,?,?)", (n["id"], u["id"], iso(now())))
        start = datetime.fromisoformat(n["event_start"]).strftime("%d.%m.%Y %H:%M") if n["event_start"] else ""
        notify(c, u["id"], "event", T3("Tədbirə qeydiyyatınız təsdiqləndi"), T3("{title} · {start}", title=n["title"], start=start), f"/news/{n['id']}")
    return news_out(c, n, u["id"])


@R("POST", "/api/news/{id:int}/save")
def news_save(req):
    c, u = req.db, req.user
    n = _get(req, req.params["id"])
    if row(c, "SELECT 1 FROM news_saved WHERE news_id=? AND user_id=?", (n["id"], u["id"])):
        c.execute("DELETE FROM news_saved WHERE news_id=? AND user_id=?", (n["id"], u["id"]))
    else:
        c.execute("INSERT INTO news_saved(news_id,user_id) VALUES(?,?)", (n["id"], u["id"]))
    return news_out(c, n, u["id"])


def _ics_esc(s):
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


@R("GET", "/api/news/{id:int}/ics")
def news_ics(req):
    n = _get(req, req.params["id"])
    if not n["event_start"]:
        raise HTTPError(400, "Bu xəbər tədbir deyil")
    fmt = lambda s: datetime.fromisoformat(s).strftime("%Y%m%dT%H%M%S")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ics = "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//AzTU//Zeka demo//AZ", "CALSCALE:GREGORIAN", "BEGIN:VEVENT",
                       f"UID:news-{n['id']}@zeka-demo.local", f"DTSTAMP:{stamp}", f"DTSTART;TZID=Asia/Baku:{fmt(n['event_start'])}",
                       f"DTEND;TZID=Asia/Baku:{fmt(n['event_end'] or n['event_start'])}", f"SUMMARY:{_ics_esc(n['title'])}",
                       f"LOCATION:{_ics_esc(n['location'])}", f"DESCRIPTION:{_ics_esc(n['summary'])}", "END:VEVENT", "END:VCALENDAR", ""])
    return Response(ics.encode("utf-8"), 200, "text/calendar; charset=utf-8", [("Content-Disposition", f"attachment; filename=tedbir-{n['id']}.ics")])


# ---------------------------------------------------------------- editor
@R("GET", "/api/news/manage", roles=STAFF)
def news_manage(req):
    c, u = req.db, req.user
    items = [news_out(c, n, u["id"], full=True) for n in rows(c, "SELECT * FROM news ORDER BY published_at DESC")]
    return {"items": items, "kinds": setting(c, "news_kinds", {})}


def _news_fields(b):
    title = (b.get("title") or "").strip()
    if len(title) < 5:
        raise HTTPError(400, "Başlıq ən azı 5 simvol olmalıdır")
    kind = b.get("kind") if b.get("kind") in KINDS else "news"
    f = {"kind": kind, "title": title[:200], "summary": (b.get("summary") or "").strip()[:400], "body": (b.get("body") or "").strip()[:8000],
         "audience": b.get("audience") if b.get("audience") in ("all", "students", "teachers") else "all",
         "pinned": 1 if b.get("pinned") else 0, "important": 1 if b.get("important") else 0,
         "cover": json.dumps({"icon": str(b.get("icon") or "news")[:20], "tone": b.get("tone") if b.get("tone") in TONES else "navy"}),
         "tags": json.dumps([t.strip()[:30] for t in str(b.get("tags") or "").split(",") if t.strip()][:6], ensure_ascii=False),
         "status": "draft" if b.get("draft") else "published"}
    if not f["summary"]:
        raise HTTPError(400, "Qısa məzmunu yazın")
    if b.get("event_start"):
        try:
            st = datetime.fromisoformat(b["event_start"])
        except ValueError:
            raise HTTPError(400, "Tədbirin tarixi düzgün deyil")
        dur = max(0.5, min(float(b.get("duration_h") or 2), 72))
        f.update({"event_start": iso(st), "event_end": iso(st + timedelta(hours=dur)), "location": (b.get("location") or "").strip()[:200],
                  "capacity": max(0, int(b.get("capacity") or 0)), "registration": 1 if b.get("registration") else 0})
    else:
        f.update({"event_start": None, "event_end": None, "location": None, "capacity": None, "registration": 0})
    return f


def _broadcast(c, nid, f):
    if f["status"] != "published" or not f["important"]:
        return
    roles = {"all": ("student", "teacher"), "students": ("student",), "teachers": ("teacher",)}[f["audience"]]
    ids = [r["id"] for r in rows(c, f"SELECT id FROM users WHERE role IN ({','.join('?' * len(roles))})", roles)]
    notify(c, ids, "news", f["title"], f["summary"][:120], f"/news/{nid}")


@R("POST", "/api/news", roles=STAFF)
def news_create(req):
    c, u = req.db, req.user
    f = _news_fields(req.json())
    cols = list(f) + ["author_id", "published_at"]
    nid = c.execute(f"INSERT INTO news({','.join(cols)}) VALUES({','.join('?' * len(cols))})", (*f.values(), u["id"], iso(now()))).lastrowid
    _broadcast(c, nid, f)
    audit(c, u["id"], "news_publish", "news", f["title"][:80])
    return news_out(c, row(c, "SELECT * FROM news WHERE id=?", (nid,)), u["id"], full=True)


@R("PUT", "/api/news/{id:int}", roles=STAFF)
def news_update(req):
    c, u = req.db, req.user
    n = row(c, "SELECT * FROM news WHERE id=?", (req.params["id"],))
    if not n:
        raise HTTPError(404, "Xəbər tapılmadı")
    f = _news_fields(req.json())
    c.execute(f"UPDATE news SET {', '.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), n["id"]))
    if n["status"] == "draft":
        _broadcast(c, n["id"], f)
    audit(c, u["id"], "news_update", "news", f["title"][:80])
    return news_out(c, row(c, "SELECT * FROM news WHERE id=?", (n["id"],)), u["id"], full=True)


@R("DELETE", "/api/news/{id:int}", roles=("leader", "admin"))
def news_delete(req):
    c = req.db
    for t in ("news_rsvp", "news_saved", "news_reads"):
        c.execute(f"DELETE FROM {t} WHERE news_id=?", (req.params["id"],))
    c.execute("DELETE FROM news WHERE id=?", (req.params["id"],))
    audit(c, req.user["id"], "news_delete", "news", f"#{req.params['id']}")
    return {"ok": True}
