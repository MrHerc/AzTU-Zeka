"""E-services: catalog, requests with attachments and messages, office workflow, documents."""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta

from . import docs, store
from .common import ACTORS, BASE_URL, R, STAFF, covers, ctx, holder, make_key, may_read_request, scope_sql, serves, step_actors
from ..core.i18n import E, S_, T3, canon
from ..core.security import LIMITS
from .store import J, audit, iso, notify, now, row, rows
from ..core.web import HTTPError, html_resp
from ..modules.journal import service as journal
from ..modules.directory import domain as directory_rules, service as directory

OPEN = ("submitted", "in_progress", "returned")
DONE = ("ready", "rejected", "cancelled")
UNITS = {"office": S_("Dekanlıq"), "academic_office": S_("Tədris hissəsi"), "dept_head": S_("Kafedra müdiri")}   # who a step's role is


def type_out(t):
    out = dict(t)
    for k, d in (("fields", []), ("steps", []), ("needs", []), ("attachments", None), ("step_roles", [])):
        out[k] = J(t[k], d)
    return out


def get_type(c, code):
    t = row(c, "SELECT * FROM request_types WHERE code=?", (code,)) if isinstance(code, str) else None
    if not t:
        raise HTTPError(400, "Müraciət növü tapılmadı")
    return type_out(t)


@R("GET", "/api/services")
def services(req):
    """The e-services on offer: only the types the administrator opened (Task 46; the demo opens every one)."""
    c = req.db
    cats = rows(c, "SELECT * FROM service_categories ORDER BY seq")
    types = [type_out(t) for t in rows(c, "SELECT * FROM request_types WHERE enabled=1 ORDER BY seq")]
    return {"categories": cats, "types": types}


# ---------------------------------------------------------------- effects of the last step (Task 46)
def _issue_doc(c, actor, r, rt, data, body):
    """``document.issue``: the type's document through Task 45's issue path (a stored payload and its hash)."""
    st = row(c, "SELECT * FROM users WHERE id=?", (r["student_id"],))
    return store.issue_document(c, "request", st["id"], rt["document"], {"type": rt["code"], **data, "student": st["full_name"]},
                                actor["id"], rt["prefix"], r["id"])


def _excuse(c, actor, r, rt, data, body):
    """``attendance.excuse``: the chosen absences that are still absences are excused in the journal; ``data["excused"]``
    names those lessons, so the answer and the teachers' notices claim no more (TE46-8)."""
    data["excused"] = journal.excuse(c, actor["id"], r["id"], r["student_id"], data.get("absences") or [])


def _leave(c, actor, r, rt, data, body):
    """``student_status.leave``: the rector's order on the leave is a status event (Task 15); the certificate is the extract
    from that order and prints its number and dates."""
    order, problem = directory_rules.status_event({"kind": "academic_leave", "order_no": body.get("order_no"), "order_date": body.get("order_date"),
                                                   "effective_date": body.get("effective_date"), "note": f"#{r['id']}"})
    if problem:
        raise HTTPError(400, problem)
    status, problem = directory.record_status(c, actor, row(c, "SELECT * FROM users WHERE id=?", (r["student_id"],)), order)
    if status != "ok":
        raise HTTPError(400, problem)
    return _issue_doc(c, actor, r, rt, {**data, **{k: order[k] for k in ("order_no", "order_date", "effective_date")}}, body)


# A type's `effect` names one of these, or is "none"; a type whose effect is not here cannot be opened.
EFFECTS = {"document.issue": _issue_doc, "attendance.excuse": _excuse, "student_status.leave": _leave}


def registered(effect) -> bool:
    return effect == "none" or effect in EFFECTS


def answer_of(rt, changed: bool = True):
    """The answer of a completed request that has no document. A type with an effect says what the effect did (its
    `answer`); a type whose effect is `none`, or whose effect changed nothing, gets the one factual template: no free text
    claims a change Zəka did not make."""
    if rt["effect"] != "none" and changed:
        return rt["answer"]
    return T3("Müraciətiniz qeydə alınıb. Baxan bölmə: {unit}. Qərar: təmin edilib. Zəka platformasında başqa heç bir qeyd dəyişdirilməyib.",
              unit=UNITS[rt["step_roles"][-1]])


@R("GET", "/api/admin/request-types", roles=("admin",))
def admin_request_types(req):
    """Every type with its flag, its effect and whether that effect is registered in code: the administrator's offer switch."""
    return [{**{k: t[k] for k in ("code", "name", "icon", "category", "effect")}, "enabled": bool(t["enabled"]),
             "registered": registered(t["effect"])} for t in rows(req.db, "SELECT * FROM request_types ORDER BY seq")]


@R("PUT", "/api/admin/request-types/{code}", roles=("admin",))
def set_offered(req):
    """Opens or closes a type: a flag only, audited (Task 46). A type whose effect is not registered in code is not opened."""
    c = req.db
    on = req.json().get("enabled")
    if not isinstance(on, bool):
        raise HTTPError(400, E("Yanlış dəyər: {field}", field="enabled"))
    t = row(c, "SELECT code, name, effect FROM request_types WHERE code=?", (str(req.params["code"]),))
    if not t:
        raise HTTPError(404, "Müraciət növü tapılmadı")
    if on and not registered(t["effect"]):
        raise HTTPError(400, E("Bu xidmətin təsiri ({effect}) kodda qeydiyyatda deyil: onu açmaq mümkün deyil", effect=t["effect"]))
    c.execute("UPDATE request_types SET enabled=? WHERE code=?", (int(on), t["code"]))
    audit(c, req.user["id"], "request_type_open" if on else "request_type_close", "request_type", t["code"])
    return admin_request_types(req)


# ---------------------------------------------------------------- validation & display
def _date(v, label):
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise HTTPError(400, E("«{label}»: tarix düzgün deyil", label=label)) from None


def _visible(f, data):
    cond = f.get("show_if")
    return not cond or all(data.get(k) == v for k, v in cond.items())


def validate(c, u, rt, raw: dict) -> dict:
    data: dict = {}
    enrolled = {r["course_id"] for r in rows(c, "SELECT course_id FROM enrollments WHERE user_id=?", (u["id"],))}
    for f in rt["fields"]:
        if f["type"] in ("radio", "select"):
            choice = canon(str(raw.get(f["name"], "") or "").strip(), f["options"])
            if choice and choice not in f["options"]:
                raise HTTPError(400, E("«{label}» üçün yanlış seçim", label=f["label"]))
            data[f["name"]] = choice or ("" if f.get("required") else f["options"][0])
    for f in rt["fields"]:
        name, typ, req_ = f["name"], f["type"], f.get("required") and _visible(f, {**raw, **data})
        v = raw.get(name)
        if typ in ("radio", "select"):
            if req_ and not data[name]:
                raise HTTPError(400, E("«{label}» seçilməlidir", label=f["label"]))
            continue
        if not _visible(f, data):
            data[name] = ""
            continue
        if typ in ("text", "textarea"):
            if isinstance(v, (list, dict)):
                raise HTTPError(400, E("Yanlış dəyər: {field}", field=name))
            v = str(v or "").strip()[:3000]
            if req_ and not v:
                raise HTTPError(400, E("«{label}» sahəsi doldurulmalıdır", label=f["label"]))
            data[name] = v
        elif typ == "number":
            if v in (None, ""):
                if req_:
                    raise HTTPError(400, E("«{label}» sahəsi doldurulmalıdır", label=f["label"]))
                data[name] = ""
                continue
            try:
                n = float(str(v).replace(",", "."))
            except ValueError:
                n = math.nan
            if not math.isfinite(n):
                raise HTTPError(400, E("«{label}»: ədəd daxil edin", label=f["label"]))
            if ("min" in f and n < f["min"]) or ("max" in f and n > f["max"]):
                raise HTTPError(400, E("«{label}»: {lo}–{hi} aralığında olmalıdır", label=f["label"], lo=f.get("min"), hi=f.get("max")))
            data[name] = f"{n:g}"
        elif typ == "date":
            if not v:
                if req_:
                    raise HTTPError(400, E("«{label}» seçilməlidir", label=f["label"]))
                data[name] = ""
                continue
            data[name] = _date(v, f["label"]).isoformat()
        elif typ == "daterange":
            rng: dict = v if isinstance(v, dict) else {}
            if not rng.get("from") or not rng.get("to"):
                if req_:
                    raise HTTPError(400, E("«{label}»: başlanğıc və son tarixi seçin", label=f["label"]))
                data[name] = {}
                continue
            d1, d2 = _date(rng["from"], f["label"]), _date(rng["to"], f["label"])
            if d2 < d1:
                raise HTTPError(400, E("«{label}»: son tarix başlanğıc tarixindən əvvəl ola bilməz", label=f["label"]))
            if f.get("future") and d1 < now().date():
                raise HTTPError(400, E("«{label}»: əvvəlcədən icazə yalnız gələcək tarixlər üçün verilir", label=f["label"]))
            if not f.get("future") and d2 > now().date():
                raise HTTPError(400, E("«{label}»: gələcək tarixlər üçün «Dərslərdən icazə» xidmətindən istifadə edin", label=f["label"]))
            if (d2 - d1).days > 60:
                raise HTTPError(400, E("«{label}»: dövr 60 gündən uzun ola bilməz", label=f["label"]))
            data[name] = {"from": d1.isoformat(), "to": d2.isoformat()}
        elif typ == "course":
            try:
                cid = int(v)  # type: ignore[arg-type]   # any JSON value; non-numbers fall through to 0
            except (TypeError, ValueError, OverflowError):
                cid = 0
            if cid not in enrolled:
                if req_:
                    raise HTTPError(400, E("«{label}» seçilməlidir", label=f["label"]))
                data[name] = ""
                continue
            data[name] = cid
        elif typ == "courses":
            given: list = v if isinstance(v, list) else []
            ids = sorted({int(x) for x in given if str(x).isascii() and str(x).isdigit() and int(x) in enrolled})
            if req_ and not ids:
                raise HTTPError(400, E("«{label}»: ən azı bir fənn seçin", label=f["label"]))
            data[name] = ids
        elif typ == "absences":
            picked: list = v if isinstance(v, list) else []
            ids = sorted({int(x) for x in picked if str(x).isascii() and str(x).isdigit()})
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
        raise HTTPError(400, E("«{label}» yüklənməlidir", label=spec["label"]))
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
           "step_roles": rt["step_roles"], "step_role": rt["step_roles"][min(r["step"], len(rt["step_roles"]) - 1)],   # who acts now (Task 46)
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
    if not r or not may_read_request(req.db, req.user, r):   # a dean's office: its faculty (Task 13); a step's role: its scope (Task 46)
        raise HTTPError(404, "Müraciət tapılmadı")
    return r


def _lock(c):
    """A request's status and step are read under the write lock, so two acts at once run one after the other: no skipped
    step, no second document, no rejected request with a valid one (TE46-1, TE46-2)."""
    if not c.in_transaction:
        c.execute("BEGIN IMMEDIATE")


def _event(c, rid, u, action, note=""):
    """One act in the request's history: who, in which role (a person may hold several), what and when."""
    c.execute("INSERT INTO request_events(request_id,actor_id,action,note,created_at,role) VALUES(?,?,?,?,?,?)",
              (rid, u["id"], action, note, iso(now()), u["role"]))


QUEUE_ORDER = "ORDER BY CASE status WHEN 'submitted' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END, due_at"


def _queue(c, u, cond: str, args) -> list[dict]:
    """The requests a staff user works with: a registry office's by its scope (Task 13); an academic office's or a
    department head's, of the types it has a step in, within its scope (Task 46)."""
    if u["role"] in STAFF:
        where, scope_args = scope_sql(u, "student_id")
        return rows(c, f"SELECT * FROM requests WHERE {cond} AND {where} {QUEUE_ORDER}", (*args, *scope_args))  # nosec B608
    codes = [t["code"] for t in rows(c, "SELECT code, step_roles FROM request_types") if u["role"] in (J(t["step_roles"], []) or [])]
    rs = rows(c, f"SELECT * FROM requests WHERE type_code IN ({','.join('?' * len(codes))}) AND {cond} {QUEUE_ORDER}",  # nosec B608
              (*codes, *args))
    seen: dict = {}            # shortcut: one scope check per student and course in Python; SQL when queues reach thousands
    out = []
    for r in rs:
        data = J(r["data"], {}) or {}
        key = (r["student_id"], data.get("course"))
        if key not in seen:
            seen[key] = covers(c, u, u["role"], r["student_id"], data)
        if seen[key]:
            out.append(r)
    return out


# ---------------------------------------------------------------- requests
@R("GET", "/api/requests")
def list_requests(req):
    c, u = req.db, req.user
    if u["role"] == "student":
        rs = rows(c, "SELECT * FROM requests WHERE student_id=? ORDER BY id DESC", (u["id"],))
    elif u["role"] in STAFF or u["role"] in ACTORS:
        status = req.query.get("status", "open")
        cond = {"open": f"status IN {OPEN}", "done": f"status IN {DONE}"}.get(status, "1=1")
        args = []
        if req.query.get("type"):
            cond += " AND type_code=?"
            args.append(req.query["type"])
        rs = _queue(c, u, cond, args)
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
    if not rt["enabled"]:                                   # a closed type is not offered (Task 46)
        raise HTTPError(404, "Müraciət növü tapılmadı")
    if rt["code"] == "transcript" and not journal.transcript_ready(c, u["id"]):     # Task 21: only from reconciled history
        raise HTTPError(400, "Transkript hələ verilmir: əvvəlki semestrlərin qiymətləri dekanlıqda yoxlanır. Dekanlığa müraciət edin.")
    data = validate(c, u, rt, b.obj("data"))
    t = now()
    rid = c.execute("INSERT INTO requests(type_code,student_id,data,status,step,created_at,updated_at,due_at) VALUES(?,?,?,?,0,?,?,?)",
                    (rt["code"], u["id"], json.dumps(data, ensure_ascii=False), "submitted", iso(t), iso(t),
                     iso(t + timedelta(hours=rt["sla_hours"])))).lastrowid
    attach_files(c, u, rt, b.ids("files", 10), rid)
    _event(c, rid, u, "submitted")
    notify(c, step_actors(c, rt["step_roles"][0], u["id"], data), "request", T3("Yeni müraciət: {type}", type=rt["name"]),
           f"{u['full_name']} · № {rid}", f"/office/request/{rid}")
    audit(c, u["id"], "request_create", "request", f"#{rid} {rt['name']}")
    return req_out(c, row(c, "SELECT * FROM requests WHERE id=?", (rid,)), rt)


@R("GET", "/api/requests/{id:int}", audit_read="request")
def get_request(req):
    c = req.db
    r = _req_for(req, req.params["id"])
    req.read_owner, req.read_object = r["student_id"], r["id"]
    rt = get_type(c, r["type_code"])
    out = req_out(c, r, rt)
    out["type"] = rt
    out["data_view"] = display_data(c, rt, out["data"])
    out["events"] = rows(c, "SELECT e.*, u.full_name actor, COALESCE(e.role, u.role) actor_role FROM request_events e "
                            "LEFT JOIN users u ON u.id=e.actor_id WHERE request_id=? ORDER BY e.id", (r["id"],))
    out["thread"] = rows(c, "SELECT m.*, u.full_name author, u.role author_role, u.color FROM request_messages m JOIN users u ON u.id=m.author_id "
                            "WHERE request_id=? ORDER BY m.id", (r["id"],))
    out["attachments"] = rows(c, "SELECT id, filename, mime, size, created_at FROM files WHERE request_id=? ORDER BY id", (r["id"],))
    return out


@R("POST", "/api/requests/{id:int}/messages", audit_read="request")
def post_message(req):
    c, u = req.db, req.user
    r = _req_for(req, req.params["id"])
    req.read_owner, req.read_object = r["student_id"], r["id"]
    text = req.json().text("text", 2000)
    if not text:
        raise HTTPError(400, "Mesaj boşdur")
    c.execute("INSERT INTO request_messages(request_id,author_id,text,created_at) VALUES(?,?,?,?)", (r["id"], u["id"], text, iso(now())))
    rt = get_type(c, r["type_code"])
    if u["role"] == "student":                      # to whoever holds the current step (Task 46)
        role = rt["step_roles"][min(r["step"], len(rt["step_roles"]) - 1)]
        notify(c, step_actors(c, role, r["student_id"], J(r["data"], {}) or {}), "message", T3("Müraciətə yeni mesaj (№ {id})", id=r["id"]),
               f"{u['full_name']}: {text[:80]}", f"/office/request/{r['id']}")
    else:
        title = T3("Dekanlıqdan yeni mesaj") if u["role"] == "office" else T3("Müraciətə yeni mesaj (№ {id})", id=r["id"])
        notify(c, r["student_id"], "message", title, T3("{type}: {text}", type=rt["name"], text=text[:80]), f"/student/requests/{r['id']}")
    return get_request(req)


@R("POST", "/api/requests/{id:int}/resubmit", roles=("student",))
def resubmit(req):
    c, u = req.db, req.user
    _lock(c)
    r = _req_for(req, req.params["id"])
    if r["status"] != "returned":
        raise HTTPError(409, "Yalnız düzəlişə qaytarılmış müraciət yenidən göndərilə bilər")
    rt = get_type(c, r["type_code"])
    b = req.json()
    data = validate(c, u, rt, {**(J(r["data"], {}) or {}), **b.obj("data")})
    existing = row(c, "SELECT COUNT(*) n FROM files WHERE request_id=?", (r["id"],))["n"]
    attach_files(c, u, rt, b.ids("files", 10), r["id"], existing)
    c.execute("UPDATE requests SET data=?, status='submitted', step=0, updated_at=? WHERE id=?", (json.dumps(data, ensure_ascii=False), iso(now()), r["id"]))
    _event(c, r["id"], u, "resubmitted")
    notify(c, step_actors(c, rt["step_roles"][0], r["student_id"], data), "request", T3("Müraciət yenidən göndərildi (№ {id})", id=r["id"]),
           T3("{name} · {service}", name=u["full_name"], service=rt["name"]), f"/office/request/{r['id']}")
    return get_request(req)


@R("POST", "/api/requests/{id:int}/cancel", roles=("student",))
def cancel(req):
    c, u = req.db, req.user
    _lock(c)
    r = _req_for(req, req.params["id"])
    if r["status"] not in ("submitted", "returned"):
        raise HTTPError(409, "Bu mərhələdə müraciəti ləğv etmək mümkün deyil")
    c.execute("UPDATE requests SET status='cancelled', updated_at=? WHERE id=?", (iso(now()), r["id"]))
    _event(c, r["id"], u, "cancelled")
    return get_request(req)


def _apply_outcome(c, r, rt, data, actor):
    """The teachers' notices of a fulfilled request (an excuse, a leave, a moved exam); the change itself is the effect."""
    student = row(c, "SELECT full_name FROM users WHERE id=?", (r["student_id"],))
    if rt["code"] == "absence_excuse":
        ids = data.get("excused", data.get("absences")) or []
        if ids:
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


@R("POST", "/api/requests/{id:int}/action", roles=ACTORS, audit_read="request")
def request_action(req):
    """Moves the current step on, returns or rejects the request: only in the role that step is assigned to and within
    that role's scope (Task 46); `issue` completes the last step and runs the type's effect in this transaction."""
    c, u = req.db, req.user
    b = req.json()
    action, note = b.get("action"), b.text("note", 1500)
    _lock(c)
    r = _req_for(req, req.params["id"])              # outside the role's scope: as if it did not exist (Task 13)
    req.read_owner, req.read_object = r["student_id"], r["id"]
    if r["student_id"] == u["id"]:                   # a student holding a staff grant decides no request of their own (SR46-1)
        raise HTTPError(403, "Öz müraciətiniz üzrə qərar verə bilməzsiniz")
    rt = get_type(c, r["type_code"])
    steps, roles = rt["steps"], rt["step_roles"]
    role = roles[min(r["step"], len(roles) - 1)]
    if u["role"] != role:
        raise HTTPError(403, E("Bu mərhələni {unit} icra edir", unit=UNITS[role]))
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
        _event(c, r["id"], u, st, note)
        notify(c, r["student_id"], "request", "Müraciətiniz düzəlişə qaytarıldı" if st == "returned" else "Müraciətiniz rədd edildi",
               T3("{type}: {note}", type=rt["name"], note=note[:90]), link)
    elif action == "approve":
        if r["status"] == "returned":
            raise HTTPError(409, "Müraciət tələbəyə qaytarılıb")
        if r["step"] >= len(steps) - 1:
            raise HTTPError(409, "Son mərhələdə «Təsdiqlə və tamamla» düyməsindən istifadə edin")
        nxt = step_actors(c, roles[r["step"] + 1], r["student_id"], data)
        if not nxt:                                  # nobody holds the next step: it stays here, where it can be returned (TE46-3)
            raise HTTPError(409, E("Növbəti mərhələni icra edən yoxdur ({unit}): administrator bu rolu təyin etməlidir",
                                   unit=UNITS[roles[r["step"] + 1]]))
        c.execute("UPDATE requests SET status='in_progress', step=step+1, updated_at=? WHERE id=?", (t, r["id"]))
        _event(c, r["id"], u, "approved", steps[r["step"]])
        notify(c, r["student_id"], "request", "Müraciətiniz növbəti mərhələyə keçdi", T3("{type}: {step}", type=rt["name"], step=steps[r["step"] + 1]), link)
        student = row(c, "SELECT full_name FROM users WHERE id=?", (r["student_id"],))      # only the next step's role, in its scope
        notify(c, nxt, "request", T3("Yeni müraciət: {type}", type=rt["name"]),
               T3("{name} · {service}", name=f"{student['full_name']} · № {r['id']}", service=steps[r["step"] + 1]), f"/office/request/{r['id']}")
    elif action == "issue":
        if r["status"] == "returned":
            raise HTTPError(409, "Müraciət tələbəyə qaytarılıb")
        if r["step"] < len(steps) - 1:
            raise HTTPError(409, "Müraciət hələ son mərhələdə deyil: əvvəlcə mərhələləri təsdiqləyin")
        if rt["code"] == "transcript" and not journal.transcript_ready(c, r["student_id"]):   # readiness can change after the request
            raise HTTPError(400, "Transkript hələ verilmir: əvvəlki semestrlərin qiymətləri dekanlıqda yoxlanır. Dekanlığa müraciət edin.")
        if not registered(rt["effect"]):
            raise HTTPError(400, E("Bu xidmətin təsiri ({effect}) kodda qeydiyyatda deyil: onu açmaq mümkün deyil", effect=rt["effect"]))
        doc = EFFECTS[rt["effect"]](c, u, r, rt, data, b) if rt["effect"] != "none" else None
        if doc:
            c.execute("UPDATE requests SET status='ready', document_id=?, updated_at=? WHERE id=?", (doc["id"], t, r["id"]))
            msg = "Sənədiniz hazırdır"
        else:
            changed = rt["effect"] != "attendance.excuse" or bool(data.get("excused"))
            c.execute("UPDATE requests SET status='ready', answer=?, updated_at=? WHERE id=?", (store._txt(answer_of(rt, changed)), t, r["id"]))
            msg = "Müraciətiniz təmin edildi"
        _apply_outcome(c, r, rt, data, u)
        _event(c, r["id"], u, "issued", note)
        notify(c, r["student_id"], "request", msg, rt["name"], link)
        audit(c, u["id"], "document_issue" if doc else "request_complete", "request", f"#{r['id']} {rt['name']}")
    else:
        raise HTTPError(400, "Naməlum əməliyyat")
    return get_request(req)


@R("GET", "/api/requests/{id:int}/preview", roles=("office", "academic_office", "admin"), audit_read="document")
def request_preview(req):
    c = req.db
    r = _req_for(req, req.params["id"])
    req.read_owner, req.read_object = r["student_id"], r["id"]
    rt = get_type(c, r["type_code"])
    if not rt.get("document"):
        raise HTTPError(400, "Bu müraciət üçün sənəd yaradılmır")
    data = {"type": rt["code"], **(J(r["data"], {}) or {})}
    fake = {"kind": "request", "title": rt["document"], "reg_no": f"AzTU-{rt['prefix']}-{now().year}-••••••", "verify_code": "••••-••••",
            "data": json.dumps(data, ensure_ascii=False), "hash": "0" * 64, "issued_at": iso(now()), "status": "valid"}
    tr = journal.transcript(c, r["student_id"]) if rt["code"] == "transcript" else None
    page = docs.render_document(fake, holder(c, r["student_id"]), req.user, ctx(c), tr, req.lang)
    return html_resp(page.replace('<div class="toolbar no-print">', '<div class="toolbar no-print" hidden>'))


@R("GET", "/api/office/summary", roles=(*STAFF, "academic_office", "dept_head"))
def office_summary(req):
    c = req.db
    types = {t["code"]: type_out(t) for t in rows(c, "SELECT * FROM request_types")}
    allr = [req_out(c, r, types[r["type_code"]]) for r in _queue(c, req.user, "1=1", ())]
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
    where, scope_args = scope_sql(req.user, "d.holder_id")
    return rows(req.db, "SELECT d.id, d.kind, d.title, d.reg_no, d.verify_code, d.issued_at, d.status, d.revoked_reason, u.full_name holder, "
                        "d.holder_id FROM documents d JOIN users u ON u.id=d.holder_id WHERE (d.reg_no LIKE ? OR u.full_name LIKE ? "
                        f"OR d.title LIKE ?) AND {where} ORDER BY d.id DESC LIMIT 200", (q, q, q, *scope_args))  # nosec B608


@R("POST", "/api/documents/{id:int}/revoke", roles=("office", "admin"))
def revoke(req):
    reason = req.json().text("reason")
    if not reason:
        raise HTTPError(400, "Ləğv səbəbini yazın")
    d = row(req.db, "SELECT holder_id FROM documents WHERE id=?", (req.params["id"],))
    if not d or not serves(req.db, req.user, d["holder_id"]):        # a dean's office: its own faculty only (Task 13)
        raise HTTPError(404, "Sənəd tapılmadı")
    req.db.execute("UPDATE documents SET status='revoked', revoked_reason=?, revoked_at=? WHERE id=?", (reason[:500], iso(now()), req.params["id"]))
    audit(req.db, req.user["id"], "document_revoke", "document", f"#{req.params['id']}: {reason[:80]}")
    return {"ok": True}


def _doc_allowed(req, d):
    if d["kind"] in ("exam_protocol", "exam_statement"):         # Task 30: a course's exam documents, not a person's
        from ..modules.exam import service as exam
        return exam.may_read_doc(req.db, req.user, d)
    if d["holder_id"] == req.user["id"] or req.user["role"] in STAFF and serves(req.db, req.user, d["holder_id"]):
        return True
    r = row(req.db, "SELECT * FROM requests WHERE id=?", (d["request_id"],)) if d.get("request_id") and req.user["role"] in ACTORS else None
    return bool(r) and may_read_request(req.db, req.user, r)        # the role that issued it from a request (Task 46)


@R("POST", "/api/documents/{id:int}/link")
def doc_link(req):
    if not LIMITS["link"].hit(f"u{req.user['id']}"):
        raise HTTPError(429, "Çox sayda sorğu. Bir az sonra yenidən cəhd edin.")
    d = row(req.db, "SELECT id, holder_id, kind, data, request_id FROM documents WHERE id=?", (req.params["id"],))
    if not d or not _doc_allowed(req, d):
        raise HTTPError(404, "Sənəd tapılmadı")
    return {"url": f"/doc/{d['id']}?k={make_key(req.db, 'doc', d['id'], req.user['id'])}"}


@R("GET", "/doc/{id:int}", audit_read="document")
def doc_page(req):
    c = req.db
    d = row(c, "SELECT * FROM documents WHERE id=?", (req.params["id"],))
    if not d:
        raise HTTPError(404, "Sənəd tapılmadı")
    if not _doc_allowed(req, d):
        if req.user["role"] in STAFF:                                   # another faculty's student: not even its existence
            raise HTTPError(404, "Sənəd tapılmadı")
        raise HTTPError(403, "Bu sənədə baxmaq icazəniz yoxdur")
    req.read_owner, req.read_object = d["holder_id"], d["id"]
    state = store.payload_state(d)
    if state != "ok":                                  # Task 45: never rebuilt from live rows
        return html_resp(docs.render_unverified(d, ctx(c), req.lang, state))
    doc, p = _stored(d)
    page = docs.render_document(doc, p["holder"], p["issuer"], _stored_ctx(p), p["transcript"], req.lang)
    if req.query.get("embed") == "1":
        page = page.replace('<div class="toolbar no-print">', '<div class="toolbar no-print" hidden>')
    return html_resp(page)


@R("GET", "/verify/{code}", auth=False)
def verify_page(req):
    c = req.db
    if not LIMITS["verify"].hit(req.ip):
        raise HTTPError(429, "Çox sayda sorğu. Bir az sonra yenidən cəhd edin.")
    d = row(c, "SELECT * FROM documents WHERE verify_code=?", (str(req.params["code"]).upper(),))
    state = store.payload_state(d) if d else "ok"
    if d and state == "ok":
        shown, p = _stored(d)
        return html_resp(docs.render_verify(shown, p["holder"], _stored_ctx(p), req.lang, state))
    return html_resp(docs.render_verify(d, None, ctx(c), req.lang, state))


def _stored(d: dict) -> tuple[dict, dict]:
    """The document as it was issued: its fields from the stored payload; status and revocation stay the registry's."""
    p = json.loads(d["payload"])
    return {**d, **{k: p[k] for k in ("kind", "title", "reg_no", "verify_code", "issued_at")},
            "data": json.dumps(p["data"], ensure_ascii=False)}, p


def _stored_ctx(p: dict) -> dict:
    return {**p["ctx"], "semester": p["ctx"]["university"]["semester"], "base_url": BASE_URL["value"]}   # the address is the deployment's
