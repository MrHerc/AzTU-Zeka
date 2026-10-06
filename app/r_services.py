"""E-services: catalog, requests with attachments and messages, office workflow, documents."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from . import docs, store
from .common import R, STAFF, ctx, holder, make_key
from .i18n import E, T3, canon
from .store import J, audit, iso, notify, now, row, rows
from .web import HTTPError, html_resp

OPEN = ("submitted", "in_progress", "returned")
DONE = ("ready", "rejected", "cancelled")


def type_out(t):
    out = dict(t)
    for k, d in (("fields", []), ("steps", []), ("needs", []), ("attachments", None)):
        out[k] = J(t[k], d)
    return out


def get_type(c, code):
    t = row(c, "SELECT * FROM request_types WHERE code=?", (code,))
    if not t:
        raise HTTPError(400, "Müraciət növü tapılmadı")
    return type_out(t)


@R("GET", "/api/services")
def services(req):
    c = req.db
    cats = rows(c, "SELECT * FROM service_categories ORDER BY seq")
    types = [type_out(t) for t in rows(c, "SELECT * FROM request_types ORDER BY seq")]
    return {"categories": cats, "types": types}


# ---------------------------------------------------------------- validation & display
def _date(v, label):
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise HTTPError(400, E("“{label}”: tarix düzgün deyil", label=label))


def _visible(f, data):
    cond = f.get("show_if")
    return not cond or all(data.get(k) == v for k, v in cond.items())


def validate(c, u, rt, raw: dict) -> dict:
    data = {}
    enrolled = {r["course_id"] for r in rows(c, "SELECT course_id FROM enrollments WHERE user_id=?", (u["id"],))}
    for f in rt["fields"]:
        if f["type"] in ("radio", "select"):
            v = str(raw.get(f["name"], "") or "").strip()
            v = canon(v, f["options"])
            if v and v not in f["options"]:
                raise HTTPError(400, E("“{label}” üçün yanlış seçim", label=f["label"]))
            data[f["name"]] = v or ("" if f.get("required") else f["options"][0])
    for f in rt["fields"]:
        name, typ, req_ = f["name"], f["type"], f.get("required") and _visible(f, {**raw, **data})
        v = raw.get(name)
        if typ in ("radio", "select"):
            if req_ and not data[name]:
                raise HTTPError(400, E("“{label}” seçilməlidir", label=f["label"]))
            continue
        if not _visible(f, data):
            data[name] = ""
            continue
        if typ in ("text", "textarea"):
            v = str(v or "").strip()[:3000]
            if req_ and not v:
                raise HTTPError(400, E("“{label}” sahəsi mütləqdir", label=f["label"]))
            data[name] = v
        elif typ == "number":
            if v in (None, ""):
                if req_:
                    raise HTTPError(400, E("“{label}” sahəsi mütləqdir", label=f["label"]))
                data[name] = ""
                continue
            try:
                n = float(str(v).replace(",", "."))
            except ValueError:
                raise HTTPError(400, E("“{label}”: rəqəm daxil edin", label=f["label"]))
            if ("min" in f and n < f["min"]) or ("max" in f and n > f["max"]):
                raise HTTPError(400, E("“{label}”: {lo}–{hi} aralığında olmalıdır", label=f["label"], lo=f.get("min"), hi=f.get("max")))
            data[name] = f"{n:g}"
        elif typ == "date":
            if not v:
                if req_:
                    raise HTTPError(400, E("“{label}” seçilməlidir", label=f["label"]))
                data[name] = ""
                continue
            data[name] = _date(v, f["label"]).isoformat()
        elif typ == "daterange":
            v = v or {}
            if not v.get("from") or not v.get("to"):
                if req_:
                    raise HTTPError(400, E("“{label}”: başlanğıc və son tarixi seçin", label=f["label"]))
                data[name] = {}
                continue
            d1, d2 = _date(v["from"], f["label"]), _date(v["to"], f["label"])
            if d2 < d1:
                raise HTTPError(400, E("“{label}”: son tarix başlanğıcdan əvvəl ola bilməz", label=f["label"]))
            if f.get("future") and d1 < now().date():
                raise HTTPError(400, E("“{label}”: əvvəlcədən icazə yalnız gələcək tarixlər üçün verilir", label=f["label"]))
            if not f.get("future") and d2 > now().date():
                raise HTTPError(400, E("“{label}”: gələcək tarixlər üçün “Dərslərdən icazə” xidmətindən istifadə edin", label=f["label"]))
            if (d2 - d1).days > 60:
                raise HTTPError(400, E("“{label}”: dövr 60 gündən uzun ola bilməz", label=f["label"]))
            data[name] = {"from": d1.isoformat(), "to": d2.isoformat()}
        elif typ == "course":
            try:
                cid = int(v)
            except (TypeError, ValueError):
                cid = 0
            if cid not in enrolled:
                if req_:
                    raise HTTPError(400, E("“{label}” seçilməlidir", label=f["label"]))
                data[name] = ""
                continue
            data[name] = cid
        elif typ == "courses":
            ids = sorted({int(x) for x in (v or []) if str(x).isdigit() and int(x) in enrolled})
            if req_ and not ids:
                raise HTTPError(400, E("“{label}”: ən azı bir fənn seçin", label=f["label"]))
            data[name] = ids
        elif typ == "absences":
            ids = sorted({int(x) for x in (v or []) if str(x).isdigit()})
            period = data.get("period") or {}
            ok = {r["lesson_id"] for r in rows(c, "SELECT a.lesson_id FROM attendance a JOIN lessons l ON l.id=a.lesson_id WHERE a.user_id=? "
                                                  "AND a.status='absent' AND l.day>=? AND l.day<=?",
                                               (u["id"], period.get("from", "0000"), period.get("to", "9999")))}
            if any(i not in ok for i in ids):
                raise HTTPError(400, "Seçilmiş dərslərdən bəziləri seçilmiş dövrə aid qayıb deyil")
            if req_ and not ids:
                raise HTTPError(400, "Üzrlü hesab ediləcək ən azı bir dərs seçin")
            data[name] = ids
    return data


def attach_files(c, u, rt, file_ids, rid, existing=0):
    spec = rt.get("attachments")
    ids = [int(i) for i in (file_ids or [])][:10]
    if not spec:
        return 0
    if spec.get("required") and not ids and not existing:
        raise HTTPError(400, E("“{label}” yüklənməlidir", label=spec["label"]))
    if len(ids) + existing > spec.get("max", 3):
        raise HTTPError(400, E("Ən çox {n} fayl əlavə etmək olar", n=spec.get("max", 3)))
    for fid in ids:
        f = row(c, "SELECT * FROM files WHERE id=? AND owner_id=? AND request_id IS NULL", (fid, u["id"]))
        if not f:
            raise HTTPError(400, "Fayl tapılmadı və ya artıq istifadə olunub")
        if spec.get("accept") == "image" and not f["mime"].startswith("image/"):
            raise HTTPError(400, "Bu sahə üçün yalnız şəkil faylı (JPG, PNG) qəbul olunur")
        c.execute("UPDATE files SET request_id=? WHERE id=?", (rid, fid))
    return len(ids)


def fmt_day(s):
    return datetime.fromisoformat(s).strftime("%d.%m.%Y")


def display_data(c, rt, data):
    out = []
    for f in rt["fields"]:
        v = data.get(f["name"])
        if v in (None, "", [], {}):
            continue
        if f["type"] == "daterange":
            v = f"{fmt_day(v['from'])} – {fmt_day(v['to'])}"
        elif f["type"] == "date":
            v = fmt_day(v)
        elif f["type"] == "course":
            co = row(c, "SELECT name FROM courses WHERE id=?", (v,))
            v = co["name"] if co else "—"
        elif f["type"] == "courses":
            v = ", ".join(r["name"] for r in rows(c, f"SELECT name FROM courses WHERE id IN ({','.join('?' * len(v))})", tuple(v)))
        elif f["type"] == "absences":
            ls = rows(c, f"SELECT l.day, l.start, l.kind, co.name FROM lessons l JOIN courses co ON co.id=l.course_id WHERE l.id IN ({','.join('?' * len(v))}) "
                         "ORDER BY l.day, l.start", tuple(v))
            v = [f"{fmt_day(x['day'])} {x['start']} · {x['name']} ({x['kind'].lower()})" for x in ls]
        out.append({"label": f["label"], "value": v})
    return out


def summary_of(rt, data):
    for k in ("purpose", "reason", "subject", "category", "to"):
        if data.get(k):
            return data[k]
    return ""


def req_out(c, r, rt=None):
    rt = rt or get_type(c, r["type_code"])
    st = row(c, "SELECT u.full_name, u.color, g.name grp FROM users u LEFT JOIN study_groups g ON g.id=u.group_id WHERE u.id=?", (r["student_id"],))
    due = datetime.fromisoformat(r["due_at"])
    is_open = r["status"] in OPEN
    data = J(r["data"], {}) or {}
    out = {**r, "data": data, "type_name": rt["name"], "icon": rt["icon"], "category": rt["category"], "steps": rt["steps"],
           "has_document": bool(rt.get("document")), "student": st["full_name"] if st else "", "group": st["grp"] if st else "",
           "student_color": st["color"] if st else "#64748b", "sla_hours": rt["sla_hours"], "summary": summary_of(rt, data),
           "overdue": is_open and r["status"] != "returned" and now() > due,
           "hours_left": round((due - now()).total_seconds() / 3600, 1) if is_open else None,
           "files": row(c, "SELECT COUNT(*) n FROM files WHERE request_id=?", (r["id"],))["n"],
           "messages": row(c, "SELECT COUNT(*) n FROM request_messages WHERE request_id=?", (r["id"],))["n"]}
    if r["document_id"]:
        out["document"] = row(c, "SELECT id, reg_no, verify_code, status FROM documents WHERE id=?", (r["document_id"],))
    return out


def _req_for(req, rid):
    r = row(req.db, "SELECT * FROM requests WHERE id=?", (rid,))
    if not r or (req.user["role"] == "student" and r["student_id"] != req.user["id"]) or req.user["role"] == "teacher":
        raise HTTPError(404, "Müraciət tapılmadı")
    return r


def office_ids(c):
    return [r["id"] for r in rows(c, "SELECT id FROM users WHERE role='office'")]


# ---------------------------------------------------------------- requests
@R("GET", "/api/requests")
def list_requests(req):
    c, u = req.db, req.user
    if u["role"] == "student":
        rs = rows(c, "SELECT * FROM requests WHERE student_id=? ORDER BY id DESC", (u["id"],))
    elif u["role"] in STAFF:
        status = req.query.get("status", "open")
        cond = {"open": f"status IN {OPEN}", "done": f"status IN {DONE}"}.get(status, "1=1")
        args = []
        if req.query.get("type"):
            cond += " AND type_code=?"
            args.append(req.query["type"])
        rs = rows(c, f"SELECT * FROM requests WHERE {cond} ORDER BY CASE status WHEN 'submitted' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END, due_at", tuple(args))
    else:
        raise HTTPError(403, "İcazə yoxdur")
    types = {t["code"]: type_out(t) for t in rows(c, "SELECT * FROM request_types")}
    out = [req_out(c, r, types[r["type_code"]]) for r in rs]
    if req.query.get("category"):
        out = [r for r in out if r["category"] == req.query["category"]]
    q = (req.query.get("q") or "").strip().lower()
    if q:
        out = [r for r in out if q in r["student"].lower() or q in str(r["id"]) or q in r["type_name"].lower()]
    return out


@R("POST", "/api/requests", roles=("student",))
def create_request(req):
    c, u = req.db, req.user
    b = req.json()
    rt = get_type(c, b.get("type_code"))
    data = validate(c, u, rt, b.get("data") or {})
    t = now()
    rid = c.execute("INSERT INTO requests(type_code,student_id,data,status,step,created_at,updated_at,due_at) VALUES(?,?,?,?,0,?,?,?)",
                    (rt["code"], u["id"], json.dumps(data, ensure_ascii=False), "submitted", iso(t), iso(t),
                     iso(t + timedelta(hours=rt["sla_hours"])))).lastrowid
    attach_files(c, u, rt, b.get("files"), rid)
    c.execute("INSERT INTO request_events(request_id,actor_id,action,note,created_at) VALUES(?,?,?,?,?)", (rid, u["id"], "submitted", "", iso(t)))
    notify(c, office_ids(c), "request", T3("Yeni müraciət: {type}", type=rt["name"]), f"{u['full_name']} · № {rid}", f"/office/request/{rid}")
    audit(c, u["id"], "request_create", "request", f"#{rid} {rt['name']}")
    return req_out(c, row(c, "SELECT * FROM requests WHERE id=?", (rid,)), rt)


@R("GET", "/api/requests/{id:int}")
def get_request(req):
    c = req.db
    r = _req_for(req, req.params["id"])
    rt = get_type(c, r["type_code"])
    out = req_out(c, r, rt)
    out["type"] = rt
    out["data_view"] = display_data(c, rt, out["data"])
    out["events"] = rows(c, "SELECT e.*, u.full_name actor, u.role actor_role FROM request_events e LEFT JOIN users u ON u.id=e.actor_id "
                            "WHERE request_id=? ORDER BY e.id", (r["id"],))
    out["thread"] = rows(c, "SELECT m.*, u.full_name author, u.role author_role, u.color FROM request_messages m JOIN users u ON u.id=m.author_id "
                            "WHERE request_id=? ORDER BY m.id", (r["id"],))
    out["attachments"] = rows(c, "SELECT id, filename, mime, size, created_at FROM files WHERE request_id=? ORDER BY id", (r["id"],))
    return out


@R("POST", "/api/requests/{id:int}/messages")
def post_message(req):
    c, u = req.db, req.user
    r = _req_for(req, req.params["id"])
    text = (req.json().get("text") or "").strip()[:2000]
    if not text:
        raise HTTPError(400, "Mesaj boşdur")
    c.execute("INSERT INTO request_messages(request_id,author_id,text,created_at) VALUES(?,?,?,?)", (r["id"], u["id"], text, iso(now())))
    rt = get_type(c, r["type_code"])
    if u["role"] == "student":
        notify(c, office_ids(c), "message", T3("Müraciətə yeni mesaj (№ {id})", id=r["id"]), f"{u['full_name']}: {text[:80]}", f"/office/request/{r['id']}")
    else:
        notify(c, r["student_id"], "message", T3("Dekanlıqdan yeni mesaj"), T3("{type}: {text}", type=rt["name"], text=text[:80]), f"/student/requests/{r['id']}")
    return get_request(req)


@R("POST", "/api/requests/{id:int}/resubmit", roles=("student",))
def resubmit(req):
    c, u = req.db, req.user
    r = _req_for(req, req.params["id"])
    if r["status"] != "returned":
        raise HTTPError(409, "Yalnız düzəlişə qaytarılmış müraciət yenidən göndərilə bilər")
    rt = get_type(c, r["type_code"])
    b = req.json()
    data = validate(c, u, rt, {**(J(r["data"], {}) or {}), **(b.get("data") or {})})
    existing = row(c, "SELECT COUNT(*) n FROM files WHERE request_id=?", (r["id"],))["n"]
    attach_files(c, u, rt, b.get("files"), r["id"], existing)
    c.execute("UPDATE requests SET data=?, status='submitted', step=0, updated_at=? WHERE id=?", (json.dumps(data, ensure_ascii=False), iso(now()), r["id"]))
    c.execute("INSERT INTO request_events(request_id,actor_id,action,note,created_at) VALUES(?,?,?,?,?)", (r["id"], u["id"], "resubmitted", "", iso(now())))
    notify(c, office_ids(c), "request", T3("Müraciət yenidən göndərildi (№ {id})", id=r["id"]), T3("{name} · {service}", name=u["full_name"], service=rt["name"]), f"/office/request/{r['id']}")
    return get_request(req)


@R("POST", "/api/requests/{id:int}/cancel", roles=("student",))
def cancel(req):
    c, u = req.db, req.user
    r = _req_for(req, req.params["id"])
    if r["status"] not in ("submitted", "returned"):
        raise HTTPError(409, "Bu mərhələdə müraciəti ləğv etmək mümkün deyil")
    c.execute("UPDATE requests SET status='cancelled', updated_at=? WHERE id=?", (iso(now()), r["id"]))
    c.execute("INSERT INTO request_events(request_id,actor_id,action,note,created_at) VALUES(?,?,?,?,?)", (r["id"], u["id"], "cancelled", "", iso(now())))
    return get_request(req)


def _apply_outcome(c, r, rt, data, actor):
    """Side effects of a fulfilled request (attendance, teacher notifications)."""
    student = row(c, "SELECT full_name FROM users WHERE id=?", (r["student_id"],))
    if rt["code"] == "absence_excuse":
        ids = data.get("absences") or []
        if ids:
            c.execute(f"UPDATE attendance SET status='excused', request_id=? WHERE user_id=? AND status='absent' AND lesson_id IN ({','.join('?' * len(ids))})",
                      (r["id"], r["student_id"], *ids))
            by_teacher = {}
            for x in rows(c, f"SELECT l.day, co.teacher_id, co.name FROM lessons l JOIN courses co ON co.id=l.course_id WHERE l.id IN ({','.join('?' * len(ids))})", tuple(ids)):
                by_teacher.setdefault(x["teacher_id"], []).append(f"{fmt_day(x['day'])} ({x['name']})")
            for tid, items in by_teacher.items():
                notify(c, tid, "attendance", T3("{student}: qayıb üzrlü hesab edildi", student=student["full_name"]),
                       T3("Dekanlıq təsdiqi · {items}", items=", ".join(items[:4])), "/teacher")
    elif rt["code"] == "leave_permission":
        p = data.get("period") or {}
        for x in rows(c, f"SELECT DISTINCT teacher_id FROM courses WHERE id IN ({','.join('?' * len(data.get('courses') or [0]))})", tuple(data.get("courses") or [0])):
            notify(c, x["teacher_id"], "attendance", T3("{student}: dərslərdən icazə verilib", student=student["full_name"]),
                   T3("{from_d} – {to_d} · dekanlıq təsdiqi", from_d=fmt_day(p["from"]), to_d=fmt_day(p["to"])), "/teacher")
    elif rt["code"] == "exam_reschedule" and data.get("course"):
        co = row(c, "SELECT teacher_id, name FROM courses WHERE id=?", (data["course"],))
        if co:
            notify(c, co["teacher_id"], "exam", T3("{student}: imtahanın vaxtı dəyişdirilir", student=student["full_name"]),
                   T3("{course} · yeni tarixi kafedra ilə razılaşdırın", course=co["name"]), "/teacher")


@R("POST", "/api/requests/{id:int}/action", roles=("office", "admin"))
def request_action(req):
    c, u = req.db, req.user
    r = _req_for(req, req.params["id"])
    b = req.json()
    action, note = b.get("action"), (b.get("note") or "").strip()[:1500]
    rt = get_type(c, r["type_code"])
    steps = rt["steps"]
    if r["status"] in DONE:
        raise HTTPError(409, "Müraciət artıq bağlanıb")
    t = iso(now())
    data = J(r["data"], {}) or {}
    link = f"/student/requests/{r['id']}"
    if action in ("return", "reject"):
        if not note:
            raise HTTPError(400, "Səbəbi qeyd edin")
        st = "returned" if action == "return" else "rejected"
        c.execute("UPDATE requests SET status=?, updated_at=? WHERE id=?", (st, t, r["id"]))
        c.execute("INSERT INTO request_events(request_id,actor_id,action,note,created_at) VALUES(?,?,?,?,?)", (r["id"], u["id"], st, note, t))
        notify(c, r["student_id"], "request", "Müraciətiniz düzəlişə qaytarıldı" if st == "returned" else "Müraciətiniz rədd edildi",
               T3("{type}: {note}", type=rt["name"], note=note[:90]), link)
    elif action == "approve":
        if r["status"] == "returned":
            raise HTTPError(409, "Müraciət tələbəyə qaytarılıb")
        if r["step"] >= len(steps) - 1:
            raise HTTPError(409, "Son mərhələdə “Təsdiqlə və tamamla” istifadə edin")
        c.execute("UPDATE requests SET status='in_progress', step=step+1, updated_at=? WHERE id=?", (t, r["id"]))
        c.execute("INSERT INTO request_events(request_id,actor_id,action,note,created_at) VALUES(?,?,?,?,?)", (r["id"], u["id"], "approved", steps[r["step"]], t))
        notify(c, r["student_id"], "request", "Müraciətiniz növbəti mərhələyə keçdi", T3("{type}: {step}", type=rt["name"], step=steps[r["step"] + 1]), link)
    elif action == "issue":
        if r["status"] == "returned":
            raise HTTPError(409, "Müraciət tələbəyə qaytarılıb")
        if rt.get("document"):
            st = row(c, "SELECT * FROM users WHERE id=?", (r["student_id"],))
            title = rt["document"]
            doc = store.issue_document(c, "request", st["id"], title, {"type": rt["code"], **data, "student": st["full_name"]}, u["id"], rt["prefix"], r["id"])
            c.execute("UPDATE requests SET status='ready', step=?, document_id=?, updated_at=? WHERE id=?", (len(steps) - 1, doc["id"], t, r["id"]))
            msg = "Sənədiniz hazırdır"
        else:
            answer = note or rt.get("answer") or "Müraciətiniz təmin edildi."
            c.execute("UPDATE requests SET status='ready', step=?, answer=?, updated_at=? WHERE id=?", (len(steps) - 1, answer, t, r["id"]))
            msg = "Müraciətiniz təmin edildi"
        _apply_outcome(c, r, rt, data, u)
        c.execute("INSERT INTO request_events(request_id,actor_id,action,note,created_at) VALUES(?,?,?,?,?)", (r["id"], u["id"], "issued", note, t))
        notify(c, r["student_id"], "request", msg, rt["name"], link)
        audit(c, u["id"], "document_issue" if rt.get("document") else "request_complete", "request", f"#{r['id']} {rt['name']}")
    else:
        raise HTTPError(400, "Naməlum əməliyyat")
    return get_request(req)


@R("GET", "/api/requests/{id:int}/preview", roles=("office", "admin"))
def request_preview(req):
    c = req.db
    r = _req_for(req, req.params["id"])
    rt = get_type(c, r["type_code"])
    if not rt.get("document"):
        raise HTTPError(400, "Bu müraciət üçün sənəd yaradılmır")
    data = {"type": rt["code"], **(J(r["data"], {}) or {})}
    fake = {"kind": "request", "title": rt["document"], "reg_no": f"AzTU-{rt['prefix']}-{now().year}-••••••", "verify_code": "••••-••••",
            "data": json.dumps(data, ensure_ascii=False), "hash": "0" * 64, "issued_at": iso(now()), "status": "valid"}
    tr = store.transcript_rows(c, r["student_id"]) if rt["code"] == "transcript" else None
    page = docs.render_document(fake, holder(c, r["student_id"]), req.user, ctx(c), tr, req.lang)
    return html_resp(page.replace('<div class="toolbar no-print">', '<div class="toolbar no-print" hidden>'))


@R("GET", "/api/office/summary", roles=STAFF)
def office_summary(req):
    c = req.db
    types = {t["code"]: type_out(t) for t in rows(c, "SELECT * FROM request_types")}
    allr = [req_out(c, r, types[r["type_code"]]) for r in rows(c, "SELECT * FROM requests")]
    week_ago = now() - timedelta(days=7)
    done = [r for r in allr if r["status"] == "ready"]
    hours = [(datetime.fromisoformat(r["updated_at"]) - datetime.fromisoformat(r["created_at"])).total_seconds() / 3600 for r in done]
    by_cat = {}
    for r in allr:
        if r["status"] in OPEN:
            by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
    return {"new": sum(r["status"] == "submitted" for r in allr), "in_progress": sum(r["status"] == "in_progress" for r in allr),
            "returned": sum(r["status"] == "returned" for r in allr), "overdue": sum(bool(r["overdue"]) for r in allr),
            "issued_week": sum(1 for r in done if datetime.fromisoformat(r["updated_at"]) >= week_ago),
            "avg_hours": round(sum(hours) / len(hours), 1) if hours else None, "by_category": by_cat,
            "categories": rows(c, "SELECT * FROM service_categories ORDER BY seq")}


# ---------------------------------------------------------------- documents
@R("GET", "/api/documents", roles=STAFF)
def documents(req):
    q = f"%{(req.query.get('q') or '').strip()}%"
    return rows(req.db, "SELECT d.id, d.kind, d.title, d.reg_no, d.verify_code, d.issued_at, d.status, d.revoked_reason, u.full_name holder "
                        "FROM documents d JOIN users u ON u.id=d.holder_id WHERE d.reg_no LIKE ? OR u.full_name LIKE ? OR d.title LIKE ? "
                        "ORDER BY d.id DESC LIMIT 200", (q, q, q))


@R("POST", "/api/documents/{id:int}/revoke", roles=("office", "admin"))
def revoke(req):
    reason = (req.json().get("reason") or "").strip()
    if not reason:
        raise HTTPError(400, "Ləğv səbəbini yazın")
    req.db.execute("UPDATE documents SET status='revoked', revoked_reason=?, revoked_at=? WHERE id=?", (reason[:500], iso(now()), req.params["id"]))
    audit(req.db, req.user["id"], "document_revoke", "document", f"#{req.params['id']}: {reason[:80]}")
    return {"ok": True}


def _doc_allowed(req, d):
    return req.user["role"] in STAFF or d["holder_id"] == req.user["id"]


@R("POST", "/api/documents/{id:int}/link")
def doc_link(req):
    d = row(req.db, "SELECT id, holder_id FROM documents WHERE id=?", (req.params["id"],))
    if not d or not _doc_allowed(req, d):
        raise HTTPError(404, "Sənəd tapılmadı")
    return {"url": f"/doc/{d['id']}?k={make_key('doc', d['id'], req.user['id'])}"}


@R("GET", "/doc/{id:int}")
def doc_page(req):
    c = req.db
    d = row(c, "SELECT * FROM documents WHERE id=?", (req.params["id"],))
    if not d:
        raise HTTPError(404, "Sənəd tapılmadı")
    if not _doc_allowed(req, d):
        raise HTTPError(403, "Bu sənədə baxmaq icazəniz yoxdur")
    h = holder(c, d["holder_id"])
    issuer = row(c, "SELECT * FROM users WHERE id=?", (d["issued_by"],)) or {"full_name": "—"}
    tr = store.transcript_rows(c, d["holder_id"]) if (J(d["data"], {}) or {}).get("type") == "transcript" else None
    page = docs.render_document(d, h, issuer, ctx(c), tr, req.lang)
    if req.query.get("embed") == "1":
        page = page.replace('<div class="toolbar no-print">', '<div class="toolbar no-print" hidden>')
    return html_resp(page)


@R("GET", "/verify/{code}", auth=False)
def verify_page(req):
    c = req.db
    d = row(c, "SELECT * FROM documents WHERE verify_code=?", (str(req.params["code"]).upper(),))
    return html_resp(docs.render_verify(d, holder(c, d["holder_id"]) if d else None, ctx(c), req.lang))
