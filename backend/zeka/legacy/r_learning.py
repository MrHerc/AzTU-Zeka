"""Learning routes: courses, tutor, quizzes, schedule, attendance, grades, teacher tools."""
from __future__ import annotations

import base64
import urllib.parse
import json
import math
import random
import re
from datetime import datetime, timedelta

from . import engine, refs, store, tutor
from .common import (R, check_limit, cite_list, course_access, history, kb_cite_list, msg_out, q_load,
                     save_msg, search_chunks, usage, week_index)
from ..core import tenant
from ..core.i18n import E, S, S_, T3
from ..modules.directory import service as directory
from ..modules.journal import domain as journal_rules
from ..modules.journal import service as journal
from ..core.security import LIMITS
from .store import J, audit, iso, notify, now, row, rows, setting
from ..core.web import HTTPError, Response

QUIZ_GRACE = timedelta(minutes=2)       # network / clock slack after a quiz time limit


def _ai_quota(u):
    if not LIMITS["ai"].hit(f"u{u['id']}"):
        raise HTTPError(429, "Çox sayda sorğu. Bir az sonra yenidən cəhd edin.")


def external_ai_allowed(u) -> bool:
    """Students' questions go to an external LLM only after the optional "external AI service" consent."""
    if u["role"] != "student":
        return True
    return bool(((J(u.get("prefs"), {}) or {}).get("consent") or {}).get("external"))


def _masked_history(hist, enabled):
    if not enabled:
        return hist
    return [{**m, "content": engine.mask_pii(m["content"])[0]} if m["role"] == "user" else m for m in hist]

WEEKDAYS = ["", S_("Bazar ertəsi"), S_("Çərşənbə axşamı"), S_("Çərşənbə"), S_("Cümə axşamı"), S_("Cümə"), S_("Şənbə"), S_("Bazar")]


# ---------------------------------------------------------------- courses
def my_courses(c, u):
    if u["role"] == "student":
        return rows(c, "SELECT co.* FROM courses co JOIN enrollments e ON e.course_id=co.id WHERE e.user_id=? ORDER BY co.id", (u["id"],))
    if u["role"] == "teacher":
        return rows(c, "SELECT * FROM courses WHERE teacher_id=? OR id IN (SELECT course_id FROM teaching_units WHERE teacher_id=? AND active=1) "
                       "ORDER BY id", (u["id"], u["id"]))            # the head of the course or a teacher of one of its units (Task 13)
    return rows(c, "SELECT * FROM courses ORDER BY id")


def next_lesson(c, course_id):
    t = now()
    tt = rows(c, "SELECT * FROM timetable WHERE course_id=? ORDER BY weekday, start", (course_id,))
    for add in range(0, 8):
        d = t.date() + timedelta(days=add)
        for x in tt:
            if x["weekday"] == d.isoweekday() and (add > 0 or x["start"] > t.strftime("%H:%M")):
                return {"date": d.isoformat(), "weekday": WEEKDAYS[x["weekday"]], **x}
    return None


def week_timetable(c, course_ids):
    """Timetable rows of these courses by weekday and start: one indexed lookup per course, never the whole table."""
    tt = [x for cid in course_ids for x in rows(c, "SELECT * FROM timetable WHERE course_id=?", (cid,))]
    return sorted(tt, key=lambda x: (x["weekday"], x["start"], x["id"]))


def att_summary(c, uid, course_id, standing: bool = True):
    """Lesson counts of the student's records, and the journal's standing (Task 20): planned and missed academic hours,
    the share, the effective limit and the status; the lessons-based ``limit`` and ``counted`` stay for older screens.
    Without ``standing`` (the course list and the home page show only the counts) the journal is not read: it costs a
    handful of queries per course on the busiest routes (Checkpoint C, P1)."""
    r = row(c, "SELECT COUNT(*) total, SUM(a.status='present') present, SUM(a.status='late') late, SUM(a.status='absent') absent, "
               "SUM(a.status='excused') excused FROM attendance a JOIN lessons l ON l.id=a.lesson_id WHERE a.user_id=? AND l.course_id=?",
            (uid, course_id))
    rules = tenant.load(c)["attendance"]
    out = {k: r[k] or 0 for k in ("total", "present", "late", "absent", "excused")}
    out["counted"] = out["absent"] + (out["excused"] if rules["excused_counts_toward_limit"] else 0)
    out["rate"] = round(100 * (out["present"] + out["late"]) / out["total"]) if out["total"] else 100
    if not standing:                                    # counts only: no standing is claimed that was not read
        return out
    st = next(iter(journal.course_standing(c, course_id, uid)), None)
    planned = st["planned_lessons"] if st else 0
    out.update(st or {"planned_hours": 0, "missed_hours": 0, "allowed_hours": 0, "percent": 0.0, "status": "normal", "as_of": None,
                      "limit_percent": rules["limit_percent"], "unexcused_hours": 0, "excused_hours": 0})
    out["planned"] = planned
    out["limit"] = int(planned * out["limit_percent"] / 100) if planned else None     # no term yet: unknown, not 0
    for k in ("student_id", "full_name", "student_no", "group", "planned_lessons", "opening_id", "held_hours"):
        out.pop(k, None)
    return out


def course_card(c, co, user=None, standing: bool = False):
    out = {k: co[k] for k in ("id", "code", "name", "credits", "color", "description", "tutor_locked")}
    t = row(c, "SELECT full_name, title FROM users WHERE id=?", (co["teacher_id"],))
    out["teacher"], out["teacher_title"] = (t["full_name"], t["title"]) if t else ("", "")
    out["suggestions"] = J(co["suggestions"], [])
    out["modes"] = J(co["tutor_modes"], ["socratic"])
    out["materials"] = row(c, f"SELECT COUNT(*) n FROM materials m WHERE course_id=? AND {CURRENT}", (co["id"],))["n"]  # nosec B608
    out["students"] = row(c, "SELECT COUNT(*) n FROM enrollments WHERE course_id=?", (co["id"],))["n"]
    out["next"] = next_lesson(c, co["id"])
    if user and user["role"] == "student":
        best = rows(c, "SELECT MAX(a.score*1.0/a.max_score) p FROM attempts a JOIN quizzes q ON q.id=a.quiz_id "
                       "WHERE q.course_id=? AND a.user_id=? AND a.finished_at IS NOT NULL GROUP BY a.quiz_id", (co["id"], user["id"]))
        nq = row(c, "SELECT COUNT(*) n FROM quizzes WHERE course_id=? AND published=1", (co["id"],))["n"]
        out["progress"] = round(100 * sum(b["p"] or 0 for b in best) / nq) if nq else 0
        out["attendance"] = att_summary(c, user["id"], co["id"], standing)
    return out


@R("GET", "/api/courses")
def courses(req):
    return [course_card(req.db, co, req.user) for co in my_courses(req.db, req.user)]


@R("GET", "/api/courses/{id:int}")
def course_detail(req):
    c, u = req.db, req.user
    co = course_access(req, req.params["id"])
    out = course_card(c, co, u, standing=True)
    from ..modules.syllabus import service as syllabus
    pub = syllabus.published_for(c, u, co["id"])
    out["syllabus_id"] = co["id"] if pub else None          # the published syllabus (Task 25): what a student reads
    out["tutor_rules"] = co["tutor_rules"] or ""
    out["materials_list"] = rows(c, "SELECT m.id, m.title, m.filename, m.chunk_count, m.term_count, m.created_at, LENGTH(m.text) chars, "
                                    "m.file_id, m.replaces_id, NOT " + CURRENT + " replaced, u.full_name uploaded_by FROM materials m "
                                    "LEFT JOIN users u ON u.id=m.uploaded_by WHERE course_id=? ORDER BY m.id", (co["id"],))
    if u["role"] == "student":                         # Task 22: a student sees the current version of each material
        out["materials_list"] = [m for m in out["materials_list"] if not m["replaced"]]
    out["schedule"] = [{**x, "weekday_name": WEEKDAYS[x["weekday"]]} for x in rows(c, "SELECT * FROM timetable WHERE course_id=? ORDER BY weekday, start", (co["id"],))]
    out["tools"] = [{**t, "areas": J(t["areas"], [])} for t in rows(c, "SELECT t.key, t.name, t.type, t.pricing, t.url, t.summary, t.areas FROM course_tools ct "
                                                                         "JOIN tools t ON t.key=ct.tool_key WHERE ct.course_id=? ORDER BY t.seq", (co["id"],))]
    out["quizzes"] = [quiz_out(c, q, u["id"] if u["role"] == "student" else None)
                      for q in rows(c, "SELECT * FROM quizzes WHERE course_id=? AND published=1 ORDER BY id DESC", (co["id"],))]
    out["references"], out["references_checked"] = refs.for_course(co["code"]), refs.checked()
    for m in out["materials_list"]:
        m["refs"] = len(refs.for_material(m["filename"]))
    if u["role"] in ("teacher", "admin", "leader"):
        out["insights"] = course_insights(c, co["id"])
    return out


CURRENT = "NOT EXISTS (SELECT 1 FROM materials n WHERE n.replaces_id=m.id)"     # not replaced by a newer version (Task 22)


def _material(req, mid: int):
    """The material if the user reaches its course; a replaced version only for staff."""
    m = row(req.db, f"SELECT m.*, NOT {CURRENT} replaced FROM materials m WHERE m.id=?", (mid,))  # nosec B608 (constant SQL)
    if not m:
        raise HTTPError(404, "Material tapılmadı")
    try:
        course_access(req, m["course_id"])
    except HTTPError as ex:
        if ex.status != 403:
            raise
        raise HTTPError(404, "Material tapılmadı") from None       # another course's material: as if it were not there
    if m["replaced"] and req.user["role"] == "student":
        raise HTTPError(404, "Material tapılmadı")
    return m


@R("GET", "/api/materials/{id:int}")
def material_get(req):
    m = _material(req, req.params["id"])
    m["chunks"] = rows(req.db, "SELECT id, seq, heading, text FROM chunks WHERE material_id=? ORDER BY seq", (m["id"],))
    m["glossary"] = [{"term": t, "definition": d} for t, d in engine.glossary(m["text"])]
    m["references"], m["references_checked"] = refs.for_material(m["filename"]), refs.checked()
    return m


@R("GET", "/api/materials/{id:int}/file")
def material_file(req):
    """The material's original file, as the teacher uploaded it (Task 22)."""
    m = _material(req, req.params["id"])
    f = row(req.db, "SELECT * FROM files WHERE id=?", (m["file_id"],)) if m["file_id"] else None
    if not f:
        raise HTTPError(404, "Bu materialın orijinal faylı yoxdur")
    fname = urllib.parse.quote(f["filename"])
    try:
        data = (store.UPLOADS / f["path"]).read_bytes()
    except OSError:                                     # a restore without the uploads folder
        raise HTTPError(404, "Bu materialın orijinal faylı yoxdur") from None
    return Response(data, 200, f["mime"],
                    [("Content-Disposition", f"attachment; filename*=UTF-8''{fname}"), ("Cache-Control", "private, no-store")])


@R("GET", "/api/source/chunk/{id:int}")
def source_chunk(req):
    ch = row(req.db, "SELECT ch.*, m.title material, co.name course FROM chunks ch JOIN materials m ON m.id=ch.material_id "
                     "JOIN courses co ON co.id=ch.course_id WHERE ch.id=?", (req.params["id"],))
    if not ch:
        raise HTTPError(404, "Mənbə tapılmadı")
    if req.user["role"] in ("student", "teacher"):
        course_access(req, ch["course_id"])
    return ch


@R("GET", "/api/source/kb/{id:int}")
def source_kb(req):
    kb = row(req.db, "SELECT id, heading, text, source material FROM campus_kb WHERE id=?", (req.params["id"],))
    if not kb:
        raise HTTPError(404, "Mənbə tapılmadı")
    return kb


# ---------------------------------------------------------------- schedule, attendance, grades
@R("GET", "/api/schedule")
def schedule(req):
    c, u = req.db, req.user
    cs = {co["id"]: co for co in my_courses(c, u)}
    t = now()
    monday = t.date() - timedelta(days=t.isoweekday() - 1)
    tt = week_timetable(c, cs)
    days = []
    for i in range(5):
        d = monday + timedelta(days=i)
        items = []
        for x in tt:
            if x["weekday"] == i + 1:
                co = cs[x["course_id"]]
                tch = row(c, "SELECT full_name FROM users WHERE id=?", (co["teacher_id"],))
                items.append({**x, "course": co["name"], "code": co["code"], "color": co["color"], "teacher": tch["full_name"] if tch else ""})
        days.append({"date": d.isoformat(), "name": WEEKDAYS[i + 1], "today": d == t.date(), "items": items})
    events = rows(c, "SELECT n.id, n.title, n.event_start, n.event_end, n.location FROM news n JOIN news_rsvp r ON r.news_id=n.id "
                     "WHERE r.user_id=? AND n.event_start>=? ORDER BY n.event_start LIMIT 6", (u["id"], iso(t)))
    return {"days": days, "events": events, "now": t.strftime("%H:%M"), "week_start": monday.isoformat()}


@R("GET", "/api/attendance", roles=("student",))
def attendance(req):
    c, u = req.db, req.user
    out = []
    for co in my_courses(c, u):
        out.append({"id": co["id"], "name": co["name"], "code": co["code"], "color": co["color"], **att_summary(c, u["id"], co["id"])})
    records = rows(c, "SELECT a.status, a.request_id, l.id lesson_id, l.day, l.start, l.end, l.kind, l.topic, co.name course, co.color, co.id course_id "
                      "FROM attendance a JOIN lessons l ON l.id=a.lesson_id JOIN courses co ON co.id=l.course_id "
                      "WHERE a.user_id=? AND a.status IN ('absent','excused','late') ORDER BY l.day DESC, l.start DESC", (u["id"],))
    pending = {}
    for r in rows(c, "SELECT id, data, status FROM requests WHERE student_id=? AND type_code='absence_excuse' AND status IN ('submitted','in_progress','returned')", (u["id"],)):
        for lid in (J(r["data"], {}) or {}).get("absences", []):
            pending[int(lid)] = r["id"]
    for r in records:
        r["pending_request"] = pending.get(r["lesson_id"])
    term = directory.current_term(c)
    return {"courses": out, "records": records, "limit_percent": tenant.load(c)["attendance"]["limit_percent"],
            "term": {k: term[k] for k in ("code", "name", "teaching_start", "teaching_end")} if term else None}


@R("GET", "/api/me/absences", roles=("student",))
def my_absences(req):
    c, u = req.db, req.user
    f, t = req.query.get("from") or "0000", req.query.get("to") or "9999"
    pend = set()
    for r in rows(c, "SELECT data FROM requests WHERE student_id=? AND type_code='absence_excuse' AND status IN ('submitted','in_progress','returned')", (u["id"],)):
        pend.update(int(x) for x in (J(r["data"], {}) or {}).get("absences", []))
    recs = rows(c, "SELECT l.id lesson_id, l.day, l.start, l.end, l.kind, co.name course, co.color FROM attendance a JOIN lessons l ON l.id=a.lesson_id "
                   "JOIN courses co ON co.id=l.course_id WHERE a.user_id=? AND a.status='absent' AND l.day>=? AND l.day<=? ORDER BY l.day, l.start",
                (u["id"], f, t))
    return [r for r in recs if r["lesson_id"] not in pend]


@R("GET", "/api/grades", roles=("student",))
def grades(req):
    """Published scores only (Task 21); the attendance component from the journal; past terms from the final grades."""
    c, u = req.db, req.user
    out = []
    for co in my_courses(c, u):
        g = journal.student_grades(c, u["id"], co)
        grading = journal.course_grading(c, co)              # the course's published syllabus, else the university's (Task 25)
        result = g["result"]
        out.append({"id": co["id"], "name": co["name"], "code": co["code"], "color": co["color"], "credits": co["credits"],
                    "items": g["items"], "semester": round(result["semester"], 1), "exam": result["exam"], "result": result,
                    "exam_max": grading["exam"]["max"], "exam_min": grading["exam"]["min"]})
    past = journal.transcript(c, u["id"])
    totals = journal_rules.transcript_totals([r for t in past for r in t["courses"]])
    return {"courses": out, "past": past, **totals}


@R("GET", "/api/courses/{id:int}/attendance", roles=("teacher", "admin", "leader"))
def course_attendance(req):
    c = req.db
    co = course_access(req, req.params["id"])
    lessons = rows(c, "SELECT l.*, SUM(a.status='present') present, SUM(a.status='late') late, SUM(a.status='absent') absent, "
                      "SUM(a.status='excused') excused FROM lessons l LEFT JOIN attendance a ON a.lesson_id=l.id WHERE l.course_id=? "
                      "AND l.day<=? GROUP BY l.id ORDER BY l.day DESC, l.start DESC LIMIT 12", (co["id"], now().date().isoformat()))
    excused = rows(c, "SELECT u.full_name student, l.day, l.kind, a.request_id FROM attendance a JOIN lessons l ON l.id=a.lesson_id "
                      "JOIN users u ON u.id=a.user_id WHERE l.course_id=? AND a.status='excused' ORDER BY l.day DESC LIMIT 20", (co["id"],))
    return {"lessons": lessons, "excused": excused}


# ---------------------------------------------------------------- student home
@R("GET", "/api/student/home", roles=("student",))
def student_home(req):
    c, u = req.db, req.user
    cs = courses(req)
    t = now()
    week_ago = iso(t - timedelta(days=7))
    attempts = rows(c, "SELECT a.*, q.title, q.course_id FROM attempts a JOIN quizzes q ON q.id=a.quiz_id "
                       "WHERE a.user_id=? AND a.finished_at IS NOT NULL ORDER BY a.finished_at DESC", (u["id"],))
    weak = {}
    for a in attempts:
        for d in J(a["details"], []):
            if not d.get("correct") and d.get("topic"):
                weak.setdefault(d["topic"], {"topic": d["topic"], "course_id": a["course_id"], "n": 0})["n"] += 1
    today = []
    by_id = {k["id"]: k for k in cs}
    for x in week_timetable(c, by_id):
        co = by_id[x["course_id"]]
        if x["weekday"] == t.isoweekday():
            state = "done" if x["end"] < t.strftime("%H:%M") else "now" if x["start"] <= t.strftime("%H:%M") <= x["end"] else "next"
            today.append({**x, "course": co["name"], "color": co["color"], "teacher": co["teacher"], "state": state, "course_id": co["id"]})
    reqs = rows(c, "SELECT r.id, r.status, r.created_at, r.updated_at, t.name type_name, t.icon FROM requests r JOIN request_types t ON t.code=r.type_code "
                   "WHERE r.student_id=? ORDER BY r.id DESC LIMIT 4", (u["id"],))
    news = rows(c, "SELECT id, kind, title, summary, cover, published_at, event_start, pinned, important FROM news WHERE status='published' "
                   "AND audience IN ('all','students') ORDER BY pinned DESC, published_at DESC LIMIT 4")
    unexcused = row(c, "SELECT COUNT(*) n FROM attendance a WHERE a.user_id=? AND a.status='absent'", (u["id"],))["n"]
    qz = [q for q in student_quizzes(req) if q["can_start"]][:4]
    return {
        "user": {"full_name": u["full_name"]}, "courses": cs, "today": today, "requests": reqs, "news": news, "quizzes": qz,
        "weak_topics": sorted(weak.values(), key=lambda w: -w["n"])[:3], "unexcused": unexcused,
        "stats": {"tutor_week": row(c, "SELECT COUNT(*) n FROM messages WHERE user_id=? AND role='user' AND created_at>=?", (u["id"], week_ago))["n"],
                  "quizzes_done": len(attempts),
                  "avg_score": round(100 * sum(a["score"] / a["max_score"] for a in attempts) / len(attempts)) if attempts else None,
                  "active_requests": sum(1 for r in reqs if r["status"] not in ("ready", "rejected"))},
    }


# ---------------------------------------------------------------- tutor
def practice_turn(c, course, msg, hist, lang="az"):
    s = lambda text, **k: S(text, lang, **k)  # noqa: E731
    pending = None
    for m in reversed(hist):
        if m["role"] == "assistant":
            if m["meta"].get("practice_qid") and not m["meta"].get("graded"):
                pending = m["meta"]["practice_qid"]
            break
    f = engine.fold(msg)
    wants_next = bool(tutor.NEXT_RX.search(f))
    if pending and not wants_next:
        q = q_load(c, pending)
        ok, given = engine.grade(q, msg)
        if ok is None:
            hint = (s("Variantın hərfini yazın (A, B, C və ya D).") if q["qtype"] == "mcq"
                    else s("**Doğru** və ya **Yanlış** yazın.") if q["qtype"] == "tf" else s("Cavabı ədəd kimi yazın."))
            return {"text": s("Cavabınızı tanıya bilmədim.") + " " + hint, "cites": [], "meta": {"mode": "practice", "practice_qid": pending}}
        cites = [q["chunk_id"]] if q["chunk_id"] else []
        ref = " [1]" if cites else ""
        if ok:
            text = s("**Düzdür!** {explanation}{ref}\n\nNövbəti suala keçmək üçün **Davam** yazın.", explanation=q["explanation"], ref=ref)
        else:
            text = s("Bu dəfə alınmadı. Sizin cavabınız: {given}. Düzgün cavab: **{answer}**.\n\n{explanation}{ref}\n\n"
                     "Mövzunu **İzah** rejimində təkrarlaya və ya **Davam** yazıb yeni sual ala bilərsiniz.",
                     given=s(given), answer=s(engine.answer_display(q)), explanation=q["explanation"], ref=ref)
        return {"text": text, "cites": cites, "meta": {"mode": "practice", "practice_qid": pending, "graded": True, "correct": ok, "topic": q["topic"]}}
    asked = {m["meta"].get("practice_qid") for m in hist if m["role"] == "assistant"}
    approved = [r["id"] for r in rows(c, "SELECT id FROM questions WHERE course_id=? AND status='approved' AND purpose='practice'", (course["id"],))]
    if not approved:
        return {"text": s("Bu fənn üzrə hələ təsdiqlənmiş məşq sualı yoxdur."), "cites": [], "meta": {"mode": "practice"}}
    hits = [] if wants_next else engine.INDEX["questions"].search(msg, k=8, where=lambda m: m["course_id"] == course["id"] and m["status"] == "approved")
    ids = [h["id"] for h in hits if h["id"] not in asked]
    if not ids:
        rest = [i for i in approved if i not in asked] or approved
        ids = [random.choice(rest)]
    q = q_load(c, ids[0])
    intro = s("Biliyinizi yoxlayaq.") + "\n\n" if not any(m["meta"].get("practice_qid") for m in hist if m["role"] == "assistant") else ""
    return {"text": intro + tutor.format_practice(q, lang), "cites": [], "meta": {"mode": "practice", "practice_qid": q["id"], "topic": q["topic"]}}


@R("GET", "/api/tutor/{cid:int}/history")
def tutor_history(req):
    course = course_access(req, req.params["cid"])
    hs = history(req.db, req.user["id"], course["id"], "tutor", 40)
    return {"course": course_card(req.db, course), "messages": [msg_out(m) for m in hs], "usage": usage(req.db, req.user), "engine": engine.engine_info()}


@R("POST", "/api/tutor/{cid:int}/ask", roles=("student", "teacher"), slow=True)
def tutor_ask(req):
    c, u = req.db, req.user
    course = course_access(req, req.params["cid"])
    body = req.json()
    msg = body.text("message", 2000)
    if not msg:
        raise HTTPError(400, "Sual boşdur")
    if course["tutor_locked"] and u["role"] == "student":
        raise HTTPError(423, "Müəllim bu fənn üzrə tutoru müvəqqəti bağlayıb (məsələn, test davam edir).")
    modes = J(course["tutor_modes"], ["socratic"])
    mode = body.get("mode") if body.get("mode") in modes else modes[0]
    used, lim = check_limit(c, u)
    _ai_quota(u)
    masking = setting(c, "limits", {}).get("pii_masking", True)
    masked, pii = engine.mask_pii(msg) if masking else (msg, [])
    hist = history(c, u["id"], course["id"], "tutor", 12)
    note = None
    if mode == "practice":
        result = practice_turn(c, course, masked, hist, req.lang)
    else:
        hits = search_chunks(course["id"], masked)
        result = None
        if engine.llm_config()["enabled"] and hits and hits[0]["score"] >= 1.2:
            if not external_ai_allowed(u):
                note = T3("Xarici AI xidmətinə razılıq verilmədiyi üçün demo mühərrik istifadə edildi.")
            else:
                try:   # earlier turns are stored as typed; they are masked again before leaving the platform
                    result = tutor.llm_tutor(mode, masked, hits, _masked_history(hist, masking), course, req.lang)
                except Exception as ex:  # network/proxy/auth errors -> offline engine
                    note = T3("LLM əlçatan olmadı ({err}); demo mühərrik istifadə edildi.", err=type(ex).__name__)
        if result is None:
            result = tutor.compose_tutor(mode, masked, hits, hist, course, req.lang)
    um = save_msg(c, u["id"], course["id"], "tutor", "user", msg, meta={"mode": mode, "pii": pii})
    meta = {**result["meta"], **({"note": note} if note else {})}
    am = save_msg(c, u["id"], course["id"], "tutor", "assistant", result["text"], result["cites"], meta)
    return {"user": {"id": um, "role": "user", "content": msg, "meta": {"mode": mode, "pii": pii}, "cites": []},
            "answer": {"id": am, "role": "assistant", "content": result["text"], "meta": meta, "cites": cite_list(result["cites"])},
            "usage": {"used": used, "limit": lim}}


@R("POST", "/api/tutor/{cid:int}/clear")
def tutor_clear(req):
    course_access(req, req.params["cid"])
    req.db.execute("DELETE FROM messages WHERE user_id=? AND course_id=? AND channel='tutor'", (req.user["id"], req.params["cid"]))
    return {"ok": True}


@R("POST", "/api/messages/{id:int}/rate")
def rate(req):
    r = req.json().integer("rating", 0)
    req.db.execute("UPDATE messages SET rating=? WHERE id=? AND user_id=?", (r if r in (1, -1) else None, req.params["id"], req.user["id"]))
    return {"ok": True}


@R("POST", "/api/tutor/{cid:int}/forward", roles=("student",))
def forward(req):
    c = req.db
    course = course_access(req, req.params["cid"])
    b = req.json()
    q = b.text("question", 2000)
    if not q:
        raise HTTPError(400, "Sual boşdur")
    c.execute("INSERT INTO teacher_questions(course_id,student_id,anonymous,question,context,status,created_at) VALUES(?,?,?,?,?,'open',?)",
              (course["id"], req.user["id"], 1 if b.get("anonymous") else 0, q, b.text("context", 1500), iso(now())))
    notify(c, course["teacher_id"], "question", "Yeni tələbə sualı", T3("{course}: {text}", course=course["name"], text=q[:90]), "/teacher/questions")
    audit(c, req.user["id"], "forward_question", "course", course["code"])
    return {"ok": True}


# ---------------------------------------------------------------- campus assistant
@R("GET", "/api/campus/history")
def campus_history(req):
    return {"messages": [msg_out(m, kb=True) for m in history(req.db, req.user["id"], None, "campus", 40)]}


@R("POST", "/api/campus/ask")
def campus_ask(req):
    c, u = req.db, req.user
    msg = req.json().text("message", 1500)
    if not msg:
        raise HTTPError(400, "Sual boşdur")
    used, lim = check_limit(c, u)
    _ai_quota(u)
    masked, pii = engine.mask_pii(msg)
    from ..modules.assistant import service as assistant      # here: that module imports this one
    result = assistant.campus_answer(c, u, masked, req.lang)    # rooms and the next lesson (Task 31), then the knowledge base
    um = save_msg(c, u["id"], None, "campus", "user", msg, meta={"pii": pii})
    meta = {**result["meta"], "actions": result["actions"]}
    am = save_msg(c, u["id"], None, "campus", "assistant", result["text"], result["cites"], meta)
    return {"user": {"id": um, "role": "user", "content": msg, "meta": {"pii": pii}, "cites": []},
            "answer": {"id": am, "role": "assistant", "content": result["text"], "meta": meta, "cites": kb_cite_list(result["cites"])},
            "usage": {"used": used, "limit": lim}}


@R("POST", "/api/campus/clear")
def campus_clear(req):
    req.db.execute("DELETE FROM messages WHERE user_id=? AND channel='campus'", (req.user["id"],))
    return {"ok": True}


# ---------------------------------------------------------------- quizzes
def quiz_out(c, qz, uid=None):
    out = {k: qz[k] for k in ("id", "course_id", "title", "kind", "time_limit", "attempts", "created_at", "show_explanations")}
    out["questions"] = len(J(qz["question_ids"], []))
    co = row(c, "SELECT name, color FROM courses WHERE id=?", (qz["course_id"],))
    out["course"], out["color"] = co["name"], co["color"]
    if uid:
        ats = rows(c, "SELECT * FROM attempts WHERE quiz_id=? AND user_id=? AND finished_at IS NOT NULL ORDER BY id DESC", (qz["id"], uid))
        out["used"] = len(ats)
        out["best"] = round(100 * max(a["score"] / a["max_score"] for a in ats)) if ats else None
        out["last_attempt"] = ats[0]["id"] if ats else None
        out["can_start"] = len(ats) < qz["attempts"]
    return out


@R("GET", "/api/quizzes", roles=("student",))
def student_quizzes(req):
    c, u = req.db, req.user
    qs = rows(c, "SELECT q.* FROM quizzes q JOIN enrollments e ON e.course_id=q.course_id WHERE e.user_id=? AND q.published=1 ORDER BY q.id DESC", (u["id"],))
    return [quiz_out(c, q, u["id"]) for q in qs]


def q_public(q):
    return {"id": q["id"], "qtype": q["qtype"], "text": q["text"], "options": q["options"], "unit": q.get("unit") or "", "topic": q["topic"], "bloom": q["bloom"]}


@R("POST", "/api/quizzes/{id:int}/start", roles=("student",))
def quiz_start(req):
    c, u = req.db, req.user
    qz = row(c, "SELECT * FROM quizzes WHERE id=? AND published=1", (req.params["id"],))
    if not qz:
        raise HTTPError(404, "Test tapılmadı")
    course_access(req, qz["course_id"])
    info = quiz_out(c, qz, u["id"])
    if not info["can_start"]:
        raise HTTPError(409, "Cəhd limiti bitib")
    aid = c.execute("INSERT INTO attempts(quiz_id,user_id,answers,details,score,max_score,started_at) VALUES(?,?,?,?,?,?,?)",
                    (qz["id"], u["id"], "{}", "[]", 0, info["questions"], iso(now()))).lastrowid
    qs = [q_public(q_load(c, qid)) for qid in J(qz["question_ids"], [])]
    return {"attempt_id": aid, "quiz": info, "questions": qs, "deadline": iso(now() + timedelta(minutes=qz["time_limit"]))}


def attempt_result(c, a):
    qz = row(c, "SELECT * FROM quizzes WHERE id=?", (a["quiz_id"],))
    return {"id": a["id"], "quiz": quiz_out(c, qz), "score": a["score"], "max_score": a["max_score"],
            "percent": round(100 * a["score"] / a["max_score"]) if a["max_score"] else 0,
            "details": J(a["details"], []), "finished_at": a["finished_at"], "started_at": a["started_at"]}


@R("POST", "/api/attempts/{id:int}/submit", roles=("student",))
def attempt_submit(req):
    c, u = req.db, req.user
    a = row(c, "SELECT * FROM attempts WHERE id=? AND user_id=?", (req.params["id"], u["id"]))
    if not a:
        raise HTTPError(404, "Cəhd tapılmadı")
    if a["finished_at"]:
        return attempt_result(c, a)
    qz = row(c, "SELECT * FROM quizzes WHERE id=?", (a["quiz_id"],))
    answers = req.json().obj("answers")
    late = now() > datetime.fromisoformat(a["started_at"]) + timedelta(minutes=qz["time_limit"] or 0) + QUIZ_GRACE
    if late:        # the time limit is enforced here, not only by the browser timer: late answers are not graded
        answers = {}
    details, score = [], 0
    for qid in J(qz["question_ids"], []):
        q = q_load(c, qid)
        given = answers.get(str(qid))
        ok, shown = (engine.grade(q, given) if given not in (None, "") else (False, "—"))
        ok = bool(ok)
        score += ok
        cite = cite_list([q["chunk_id"]]) if q["chunk_id"] else []
        details.append({"qid": qid, "text": q["text"], "qtype": q["qtype"], "options": q["options"], "given": shown, "correct": ok,
                        "answer": engine.answer_display(q), "explanation": q["explanation"], "topic": q["topic"], "source": cite[0] if cite else None})
    c.execute("UPDATE attempts SET answers=?, details=?, score=?, finished_at=? WHERE id=?",
              (json.dumps(answers), json.dumps(details, ensure_ascii=False), score, iso(now()), a["id"]))
    audit(c, u["id"], "quiz_submit", "quiz", f"{qz['title']}: {score}/{len(details)}" + (" (vaxt bitib)" if late else ""))
    return attempt_result(c, row(c, "SELECT * FROM attempts WHERE id=?", (a["id"],)))


@R("GET", "/api/attempts/{id:int}", roles=("student",))
def attempt_get(req):
    a = row(req.db, "SELECT * FROM attempts WHERE id=? AND user_id=?", (req.params["id"], req.user["id"]))
    if not a:
        raise HTTPError(404, "Cəhd tapılmadı")
    return attempt_result(req.db, a)


# ---------------------------------------------------------------- teacher
def course_insights(c, cid):
    weeks = [0] * 8
    for m in rows(c, "SELECT created_at FROM messages WHERE course_id=? AND channel='tutor' AND role='user'", (cid,)):
        w = week_index(m["created_at"])
        if 0 <= w < 8:
            weeks[7 - w] += 1
    ams = rows(c, "SELECT meta, cites, rating FROM messages WHERE course_id=? AND channel='tutor' AND role='assistant'", (cid,))
    topics, rated, pos, cited, nosrc = {}, 0, 0, 0, 0
    for m in ams:
        meta = J(m["meta"], {}) or {}
        if meta.get("topic"):
            topics[meta["topic"]] = topics.get(meta["topic"], 0) + 1
        if m["rating"]:
            rated += 1
            pos += m["rating"] == 1
        cited += bool(J(m["cites"], []))
        nosrc += bool(meta.get("no_source"))
    gaps = rows(c, "SELECT DISTINCT u.content q FROM messages u JOIN messages a ON a.id=(SELECT MIN(id) FROM messages WHERE id>u.id "
                   "AND user_id=u.user_id AND channel='tutor' AND role='assistant') WHERE u.course_id=? AND u.role='user' AND "
                   "a.meta LIKE '%\"no_source\": true%' LIMIT 6", (cid,))
    total = len(ams) or 1
    return {"questions_total": sum(weeks), "weekly": weeks, "this_week": weeks[-1],
            "top_topics": sorted(({"topic": k, "n": v} for k, v in topics.items()), key=lambda x: -x["n"])[:6],
            "positive_rate": round(100 * pos / rated) if rated else None, "cited_rate": round(100 * cited / total, 1),
            "no_source_rate": round(100 * nosrc / total, 1), "gaps": [g["q"] for g in gaps]}


@R("GET", "/api/teacher/home", roles=("teacher",))
def teacher_home(req):
    c, u = req.db, req.user
    cs = courses(req)
    for co in cs:
        co["insights"] = course_insights(c, co["id"])
    qs = teacher_questions(req)
    done = row(c, "SELECT COUNT(*) n, COALESCE(SUM(m.minutes),0) mins FROM academy_progress p JOIN academy_modules m ON m.id=p.module_id "
                  "WHERE p.user_id=? AND p.status='completed'", (u["id"],))
    total = row(c, "SELECT COUNT(*) n FROM academy_modules")["n"]
    t = now()
    today = []
    for x in rows(c, "SELECT * FROM timetable WHERE weekday=? ORDER BY start", (t.isoweekday(),)):
        co = next((k for k in cs if k["id"] == x["course_id"]), None)
        if co:
            today.append({**x, "course": co["name"], "color": co["color"], "course_id": co["id"]})
    excused = rows(c, "SELECT u.full_name student, l.day, co.name course FROM attendance a JOIN lessons l ON l.id=a.lesson_id JOIN courses co ON co.id=l.course_id "
                      "JOIN users u ON u.id=a.user_id WHERE co.teacher_id=? AND a.status='excused' ORDER BY l.day DESC LIMIT 5", (u["id"],))
    return {"user": {"full_name": u["full_name"], "title": u["title"]}, "courses": cs, "questions": [q for q in qs if q["status"] == "open"][:4],
            "open_questions": sum(q["status"] == "open" for q in qs), "today": today, "excused": excused,
            "academy": {"done": done["n"], "total": total, "hours": round(done["mins"] / 60, 1)},
            "drafts": row(c, "SELECT COUNT(*) n FROM questions q JOIN courses co ON co.id=q.course_id WHERE co.teacher_id=? AND q.status='draft'", (u["id"],))["n"]}


@R("POST", "/api/courses/{id:int}/materials", roles=("teacher",))
def upload_material(req):
    c = req.db
    co = course_access(req, req.params["id"])
    if not LIMITS["upload"].hit(f"u{req.user['id']}"):
        raise HTTPError(429, "Çox sayda sorğu. Bir az sonra yenidən cəhd edin.")
    b = req.json()
    name = b.text("filename", 200) or "material.txt"
    try:
        data = base64.b64decode(b.text("content_b64"), validate=False)
    except ValueError:
        raise HTTPError(400, "Fayl oxunmadı") from None
    if not data:
        raise HTTPError(400, "Fayl boşdur")
    if len(data) > store.MAX_FILE:
        raise HTTPError(413, "Fayl 10 MB-dan böyükdür")
    try:
        text = engine.extract_text(name, data)
    except ValueError as ex:
        raise HTTPError(400, str(ex)) from None
    except Exception:
        raise HTTPError(400, "Fayldan mətn çıxarmaq mümkün olmadı") from None
    if len(text.strip()) < 40:
        raise HTTPError(400, "Fayldan kifayət qədər mətn çıxarılmadı")
    title = (b.text("title") or re.sub(r"\.[^.]+$", "", name)).strip()[:200]
    if not text.lstrip().startswith("#"):
        text = f"# {title}\n\n" + text
    replaces = b.integer("replaces", None, lo=1)
    if replaces is not None:
        if not c.in_transaction:
            c.execute("BEGIN IMMEDIATE")                # two uploads replacing one version: the second sees the first
        old = row(c, f"SELECT m.uploaded_by FROM materials m WHERE m.id=? AND m.course_id=? AND {CURRENT}", (replaces, co["id"]))  # nosec B608
        if not old:
            raise HTTPError(404, "Material tapılmadı")
        if co["teacher_id"] != req.user["id"] and old["uploaded_by"] != req.user["id"]:
            raise HTTPError(403, "Bu fənn sizə aid deyil")
    try:
        original = store.save_file(c, req.user["id"], name, data, accept="material")      # Task 22: the file itself is kept
    except ValueError as ex:
        raise HTTPError(400, str(ex)) from None
    info = store.add_material(c, co["id"], title, name, text, req.user["id"], file_id=original["id"], replaces_id=replaces)
    audit(c, req.user["id"], "material_upload", "course", f"{co['code']}: {title}")
    return {"ok": True, **info, "title": title}


@R("DELETE", "/api/materials/{id:int}", roles=("teacher",))
def material_delete(req):
    m = row(req.db, "SELECT * FROM materials WHERE id=?", (req.params["id"],))
    if not m:
        raise HTTPError(404, "Material tapılmadı")
    co = course_access(req, m["course_id"])
    if co["teacher_id"] != req.user["id"] and m["uploaded_by"] != req.user["id"]:
        raise HTTPError(403, "Bu fənn sizə aid deyil")             # a unit's teacher removes only what that teacher uploaded
    store.delete_material(req.db, m["id"])
    audit(req.db, req.user["id"], "material_delete", "material", m["title"])
    return {"ok": True}


@R("PUT", "/api/courses/{id:int}/tutor", roles=("teacher",))
def tutor_settings(req):
    co = course_access(req, req.params["id"], head=True)
    b = req.json()
    modes = [m for m in b.array("modes") if isinstance(m, str) and m in tutor.MODES] or ["socratic"]
    req.db.execute("UPDATE courses SET tutor_modes=?, tutor_rules=?, tutor_locked=? WHERE id=?",
                   (json.dumps(modes), b.text("rules", 2000), 1 if b.get("locked") else 0, co["id"]))
    audit(req.db, req.user["id"], "tutor_settings", "course", co["code"])
    return course_detail(req)


@R("GET", "/api/teacher/questions", roles=("teacher",))
def teacher_questions(req):
    qs = rows(req.db, "SELECT tq.*, co.name course, co.color, u.full_name student FROM teacher_questions tq JOIN courses co ON co.id=tq.course_id "
                      "JOIN users u ON u.id=tq.student_id WHERE co.teacher_id=? ORDER BY tq.status='answered', tq.id DESC", (req.user["id"],))
    for q in qs:
        if q["anonymous"]:
            q["student"] = "Anonim tələbə"
    return qs


@R("POST", "/api/teacher/questions/{id:int}/answer", roles=("teacher",))
def answer_question(req):
    c = req.db
    a = req.json().text("answer")
    if not a:
        raise HTTPError(400, "Cavab boşdur")
    q = row(c, "SELECT tq.*, co.name course FROM teacher_questions tq JOIN courses co ON co.id=tq.course_id WHERE tq.id=? AND co.teacher_id=?",
            (req.params["id"], req.user["id"]))
    if not q:
        raise HTTPError(404, "Sual tapılmadı")
    c.execute("UPDATE teacher_questions SET answer=?, status='answered', answered_at=? WHERE id=?", (a[:3000], iso(now()), q["id"]))
    notify(c, q["student_id"], "answer", "Müəllim sualınıza cavab verdi", T3("{course}: {text}", course=q["course"], text=a[:90]), f"/student/tutor/{q['course_id']}")
    return {"ok": True}


# ---------------------------------------------------------------- studio
def q_out(c, q):
    q = dict(q)
    for k, d in (("options", []), ("answer", None), ("flags", [])):
        if isinstance(q.get(k), str):
            q[k] = J(q[k], d)
    src = cite_list([q["chunk_id"]]) if q.get("chunk_id") else []
    q["source"] = src[0] if src else None
    return q


@R("POST", "/api/studio/generate", roles=("teacher",))
def studio_generate(req):
    c, u = req.db, req.user
    _ai_quota(u)
    b = req.json()
    co = course_access(req, b.integer("course_id", 0))
    count = b.integer("count", 6, 1, 15)
    types = [t for t in (b.array("types") or ["mcq", "tf", "numeric"]) if t in ("mcq", "tf", "numeric")] or ["mcq"]
    material_id = b.integer("material_id")
    if material_id:
        chunks = rows(c, "SELECT id, heading, text FROM chunks WHERE material_id=? AND course_id=? ORDER BY seq", (material_id, co["id"]))
    else:
        chunks = rows(c, "SELECT id, heading, text FROM chunks WHERE course_id=? ORDER BY material_id, seq", (co["id"],))
    if not chunks:
        raise HTTPError(400, "Əvvəlcə material yükləyin")
    course_gl = [g for m in rows(c, f"SELECT text FROM materials m WHERE course_id=? AND {CURRENT}", (co["id"],))  # nosec B608
                 for g in engine.glossary(m["text"])]
    gen = engine.generate_questions(chunks, course_gl, count, types, seed=random.randint(1, 10 ** 6))
    if not gen:
        raise HTTPError(422, "Materialdan sual yaratmaq mümkün olmadı. Materialda “Termin — tərif” formatında anlayışlar olmalıdır.")
    existing = rows(c, "SELECT text FROM questions WHERE course_id=? AND status='approved'", (co["id"],))
    out = []
    for g in gen:
        flags = ["source_ok"] + (["similar"] if any(engine.similarity(g["text"], x["text"]) > 0.55 for x in existing) else [])
        qid = c.execute("INSERT INTO questions(course_id,chunk_id,qtype,text,options,answer,unit,explanation,bloom,difficulty,topic,status,origin,flags,created_by,created_at)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?,?,'draft','ai',?,?,?)",
                        (co["id"], g["chunk_id"], g["qtype"], g["text"], json.dumps(g["options"], ensure_ascii=False), json.dumps(g["answer"]),
                         g.get("unit", ""), g["explanation"], g["bloom"], g["difficulty"], g["topic"], json.dumps(flags), u["id"], iso(now()))).lastrowid
        q = row(c, "SELECT * FROM questions WHERE id=?", (qid,))
        store.index_question(q)
        store.log_index(c, "questions", [qid])
        out.append(q_out(c, q))
    audit(c, u["id"], "ai_generate", "course", f"{co['code']}: {len(out)} sual")
    return {"questions": out, "engine": engine.engine_info()}


@R("GET", "/api/questions", roles=("teacher",))
def questions(req):
    co = course_access(req, req.qint("course_id", 0))
    st = req.query.get("status")
    sql = "SELECT * FROM questions WHERE course_id=?" + (" AND status=?" if st else "") + " ORDER BY status='approved', id DESC"
    return [q_out(req.db, q) for q in rows(req.db, sql, (co["id"], st) if st else (co["id"],))]


def _own_question(req, q):
    """A question is changed by the course's head teacher or by the teacher who made it (Checkpoint C, S1)."""
    co = course_access(req, q["course_id"])
    if co["teacher_id"] != req.user["id"] and q["created_by"] != req.user["id"]:
        raise HTTPError(403, "Bu fənn sizə aid deyil")
    return co


@R("PUT", "/api/questions/{id:int}", roles=("teacher",))
def question_update(req):
    c = req.db
    q = q_load(c, req.params["id"])
    _own_question(req, q)
    _exam_question_free(c, q)
    b = req.json()
    fields = {k: str(b[k])[:3000] for k in ("text", "explanation", "topic", "bloom", "difficulty", "unit") if k in b}
    options = [str(o)[:300] for o in b.array("options")][:6] if "options" in b else q["options"]
    answer = b["answer"] if "answer" in b else q["answer"]
    _check_answer(q["qtype"], options, answer)
    if "options" in b:
        fields["options"] = json.dumps(options, ensure_ascii=False)
    if "answer" in b:
        fields["answer"] = json.dumps(answer)
    if b.get("status") in ("draft", "approved"):
        if q.get("purpose") == "exam" and q["status"] == "approved" and b["status"] == "draft":
            raise HTTPError(400, "Təsdiqlənmiş imtahan sualı qaralamaya qaytarılmır")   # its purpose would come loose (Checkpoint D)
        fields["status"] = b["status"]
    if "purpose" in b:                                  # chosen by the time the question is first approved, then fixed (Task 26)
        if b["purpose"] not in ("practice", "exam"):
            raise HTTPError(400, "Sualın təyinatı məşq və ya imtahan olmalıdır")
        if q["status"] == "approved" and b["purpose"] != (q.get("purpose") or "practice"):
            raise HTTPError(400, "Təsdiqlənmiş sualın təyinatı dəyişdirilə bilməz")
        fields["purpose"] = b["purpose"]
    if fields:
        # bandit B608: column names from a fixed whitelist
        c.execute(f"UPDATE questions SET {', '.join(k + '=?' for k in fields)} WHERE id=?", (*fields.values(), q["id"]))  # nosec B608
    nq = row(c, "SELECT * FROM questions WHERE id=?", (q["id"],))
    store.index_question(nq)
    store.log_index(c, "questions", [nq["id"]])
    if (q.get("purpose") or "practice") == "exam" and fields:
        store.audit(c, req.user["id"], "exam_question_changed", "question", f"#{q['id']} · {', '.join(sorted(fields))}")
    return q_out(c, nq)


def _exam_question_free(c, q):
    from ..modules.exam import service as exam
    if exam.question_locked(c, q):
        raise HTTPError(409, "İmtahan açıq ikən onun sualı dəyişdirilmir və silinmir")


def _check_answer(qtype, options, answer):
    """A stored answer must be gradable: an edited question with an answer outside its options broke every quiz submit."""
    if qtype == "mcq":
        ok = isinstance(answer, int) and not isinstance(answer, bool) and len(options) >= 2 and 0 <= answer < len(options)
    elif qtype == "tf":
        ok = isinstance(answer, bool)
    else:
        try:
            ok = not isinstance(answer, bool) and math.isfinite(float(answer))
        except (TypeError, ValueError):
            ok = False
    if not ok:
        raise HTTPError(400, E("Yanlış dəyər: {field}", field="answer"))


@R("DELETE", "/api/questions/{id:int}", roles=("teacher",))
def question_delete(req):
    q = q_load(req.db, req.params["id"])
    _own_question(req, q)
    _exam_question_free(req.db, q)
    if (q.get("purpose") or "practice") == "exam":
        store.audit(req.db, req.user["id"], "exam_question_deleted", "question", f"#{q['id']}")
    req.db.execute("DELETE FROM questions WHERE id=?", (q["id"],))
    engine.INDEX["questions"].remove(q["id"])
    store.log_index(req.db, "questions", [q["id"]], "delete")
    return {"ok": True}


@R("GET", "/api/teacher/quizzes", roles=("teacher",))
def teacher_quizzes(req):
    c = req.db
    out = []
    for qz in rows(c, "SELECT q.* FROM quizzes q JOIN courses co ON co.id=q.course_id WHERE co.teacher_id=? ORDER BY q.id DESC", (req.user["id"],)):
        o = quiz_out(c, qz)
        ats = rows(c, "SELECT score, max_score FROM attempts WHERE quiz_id=? AND finished_at IS NOT NULL", (qz["id"],))
        o["attempts_count"] = len(ats)
        o["avg"] = round(100 * sum(a["score"] / a["max_score"] for a in ats) / len(ats)) if ats else None
        out.append(o)
    return out


@R("POST", "/api/quizzes", roles=("teacher",))
def quiz_create(req):
    c = req.db
    b = req.json()
    co = course_access(req, b.integer("course_id", 0))
    ids = list(dict.fromkeys(b.ids("question_ids", 200)))
    if not ids:
        raise HTTPError(400, "Ən azı bir sual seçin")
    ok = {r["id"] for r in rows(c, f"SELECT id FROM questions WHERE course_id=? AND status='approved' AND purpose='practice' "  # nosec B608
                                   f"AND id IN ({','.join('?' * len(ids))})", (co["id"], *ids))}
    if len(ok) != len(ids):                             # an exam question never goes into a practice test (Task 26)
        raise HTTPError(400, "Yalnız təsdiqlənmiş məşq sualları testə əlavə oluna bilər")
    title = b.text("title", 200) or "Yeni test"
    kind = "graded" if b.get("kind") == "graded" else "practice"
    qid = c.execute("INSERT INTO quizzes(course_id,title,kind,question_ids,time_limit,attempts,show_explanations,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (co["id"], title, kind, json.dumps(ids), b.integer("time_limit", 15, 1, 180),
                     b.integer("attempts", 3 if kind == "practice" else 1, 1, 10), 1, iso(now()))).lastrowid
    studs = [r["user_id"] for r in rows(c, "SELECT user_id FROM enrollments WHERE course_id=?", (co["id"],))]
    notify(c, studs, "quiz", T3("Yeni test: {title}", title=title), T3("{course} · {n} sual", course=co["name"], n=len(ids)), "/student/quizzes")
    audit(c, req.user["id"], "quiz_publish", "quiz", title)
    return quiz_out(c, row(c, "SELECT * FROM quizzes WHERE id=?", (qid,)))


@R("GET", "/api/quizzes/{id:int}/results", roles=("teacher",))
def quiz_results(req):
    c = req.db
    qz = row(c, "SELECT * FROM quizzes WHERE id=?", (req.params["id"],))
    if not qz:
        raise HTTPError(404, "Test tapılmadı")
    course_access(req, qz["course_id"])
    ats = rows(c, "SELECT * FROM attempts WHERE quiz_id=? AND finished_at IS NOT NULL", (qz["id"],))
    lows, labels = tenant.bands(tenant.load(c)["grading"]["scale"])
    buckets, per_q = [0] * len(labels), {}
    for a in ats:
        p = 100 * a["score"] / a["max_score"] if a["max_score"] else 0
        buckets[tenant.band(p, lows)] += 1
        for d in J(a["details"], []):
            s = per_q.setdefault(d["qid"], [0, 0])
            s[0] += 1
            s[1] += bool(d.get("correct"))
    qs = []
    for qid in J(qz["question_ids"], []):
        q = q_load(c, qid)
        n, k = per_q.get(qid, [0, 0])
        qs.append({"id": qid, "text": q["text"], "topic": q["topic"], "bloom": q["bloom"], "n": n, "correct_rate": round(100 * k / n) if n else None})
    return {"quiz": quiz_out(c, qz), "attempts": len(ats), "avg": round(sum(100 * a["score"] / a["max_score"] for a in ats) / len(ats)) if ats else None,
            "buckets": buckets, "labels": labels, "questions": qs}
