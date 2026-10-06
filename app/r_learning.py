"""Learning routes: courses, tutor, quizzes, schedule, attendance, grades, teacher tools."""
from __future__ import annotations

import base64
import json
import random
import re
from datetime import date, datetime, timedelta

from . import engine, store, tutor
from .common import (R, check_limit, cite_list, course_access, history, holder, kb_cite_list, msg_out, q_load,
                     save_msg, search_chunks, usage, week_index)
from .i18n import S, S_, T3
from .store import J, audit, iso, notify, now, row, rows, setting
from .web import HTTPError

WEEKDAYS = ["", S_("Bazar ertəsi"), S_("Çərşənbə axşamı"), S_("Çərşənbə"), S_("Cümə axşamı"), S_("Cümə"), S_("Şənbə"), S_("Bazar")]
SEM_WEEKS = 15


# ---------------------------------------------------------------- courses
def my_courses(c, u):
    if u["role"] == "student":
        return rows(c, "SELECT co.* FROM courses co JOIN enrollments e ON e.course_id=co.id WHERE e.user_id=? ORDER BY co.id", (u["id"],))
    if u["role"] == "teacher":
        return rows(c, "SELECT * FROM courses WHERE teacher_id=? ORDER BY id", (u["id"],))
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


def att_summary(c, uid, course_id):
    r = row(c, "SELECT COUNT(*) total, SUM(a.status='present') present, SUM(a.status='late') late, SUM(a.status='absent') absent, "
               "SUM(a.status='excused') excused FROM attendance a JOIN lessons l ON l.id=a.lesson_id WHERE a.user_id=? AND l.course_id=?",
            (uid, course_id))
    weekly = row(c, "SELECT COUNT(*) n FROM timetable WHERE course_id=?", (course_id,))["n"]
    planned = weekly * SEM_WEEKS
    out = {k: r[k] or 0 for k in ("total", "present", "late", "absent", "excused")}
    out["planned"] = planned
    out["limit"] = int(planned * 0.25)
    out["rate"] = round(100 * (out["present"] + out["late"]) / out["total"]) if out["total"] else 100
    return out


def course_card(c, co, user=None):
    out = {k: co[k] for k in ("id", "code", "name", "credits", "color", "description", "tutor_locked")}
    t = row(c, "SELECT full_name, title FROM users WHERE id=?", (co["teacher_id"],))
    out["teacher"], out["teacher_title"] = (t["full_name"], t["title"]) if t else ("", "")
    out["suggestions"] = J(co["suggestions"], [])
    out["modes"] = J(co["tutor_modes"], ["socratic"])
    out["materials"] = row(c, "SELECT COUNT(*) n FROM materials WHERE course_id=?", (co["id"],))["n"]
    out["students"] = row(c, "SELECT COUNT(*) n FROM enrollments WHERE course_id=?", (co["id"],))["n"]
    out["next"] = next_lesson(c, co["id"])
    if user and user["role"] == "student":
        best = rows(c, "SELECT MAX(a.score*1.0/a.max_score) p FROM attempts a JOIN quizzes q ON q.id=a.quiz_id "
                       "WHERE q.course_id=? AND a.user_id=? AND a.finished_at IS NOT NULL GROUP BY a.quiz_id", (co["id"], user["id"]))
        nq = row(c, "SELECT COUNT(*) n FROM quizzes WHERE course_id=? AND published=1", (co["id"],))["n"]
        out["progress"] = round(100 * sum(b["p"] or 0 for b in best) / nq) if nq else 0
        out["attendance"] = att_summary(c, user["id"], co["id"])
    return out


@R("GET", "/api/courses")
def courses(req):
    return [course_card(req.db, co, req.user) for co in my_courses(req.db, req.user)]


@R("GET", "/api/courses/{id:int}")
def course_detail(req):
    c, u = req.db, req.user
    co = course_access(req, req.params["id"])
    out = course_card(c, co, u)
    out["tutor_rules"] = co["tutor_rules"] or ""
    out["materials_list"] = rows(c, "SELECT m.id, m.title, m.filename, m.chunk_count, m.term_count, m.created_at, LENGTH(m.text) chars, "
                                    "u.full_name uploaded_by FROM materials m LEFT JOIN users u ON u.id=m.uploaded_by WHERE course_id=? ORDER BY m.id", (co["id"],))
    out["schedule"] = [{**x, "weekday_name": WEEKDAYS[x["weekday"]]} for x in rows(c, "SELECT * FROM timetable WHERE course_id=? ORDER BY weekday, start", (co["id"],))]
    out["tools"] = [{**t, "areas": J(t["areas"], [])} for t in rows(c, "SELECT t.key, t.name, t.type, t.pricing, t.url, t.summary, t.areas FROM course_tools ct "
                                                                         "JOIN tools t ON t.key=ct.tool_key WHERE ct.course_id=? ORDER BY t.seq", (co["id"],))]
    out["quizzes"] = [quiz_out(c, q, u["id"] if u["role"] == "student" else None)
                      for q in rows(c, "SELECT * FROM quizzes WHERE course_id=? AND published=1 ORDER BY id DESC", (co["id"],))]
    if u["role"] in ("teacher", "admin", "leader"):
        out["insights"] = course_insights(c, co["id"])
    return out


@R("GET", "/api/materials/{id:int}")
def material_get(req):
    m = row(req.db, "SELECT * FROM materials WHERE id=?", (req.params["id"],))
    if not m:
        raise HTTPError(404, "Material tapılmadı")
    course_access(req, m["course_id"])
    m["chunks"] = rows(req.db, "SELECT id, seq, heading, text FROM chunks WHERE material_id=? ORDER BY seq", (m["id"],))
    m["glossary"] = [{"term": t, "definition": d} for t, d in engine.glossary(m["text"])]
    return m


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
    days = []
    for i in range(5):
        d = monday + timedelta(days=i)
        items = []
        for x in rows(c, "SELECT * FROM timetable WHERE weekday=? ORDER BY start", (i + 1,)):
            if x["course_id"] in cs:
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
    return {"courses": out, "records": records, "semester_start": setting(c, "semester_start")}


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
    c, u = req.db, req.user
    comps = [("Davamiyyət", 10), ("Sərbəst iş 1", 5), ("Sərbəst iş 2", 5), ("Laboratoriya / məşğələ", 10), ("Kollokvium 1", 10), ("Kollokvium 2", 10)]
    out = []
    for co in my_courses(c, u):
        got = {g["component"]: g for g in rows(c, "SELECT * FROM grades WHERE user_id=? AND course_id=?", (u["id"], co["id"]))}
        a = att_summary(c, u["id"], co["id"])
        items = []
        for name, mx in comps:
            if name == "Davamiyyət":
                score = round(mx * (a["present"] + a["late"] + a["excused"]) / a["total"], 1) if a["total"] else None
                items.append({"name": name, "max": mx, "score": score, "note": "cari göstərici"})
            else:
                g = got.get(name)
                items.append({"name": name, "max": mx, "score": g["score"] if g else None, "note": "" if g else "hələ keçirilməyib"})
        cur = sum(i["score"] or 0 for i in items)
        out.append({"id": co["id"], "name": co["name"], "code": co["code"], "color": co["color"], "credits": co["credits"],
                    "items": items, "semester": round(cur, 1), "exam": None})
    past = store.transcript_rows(c, u["id"])
    flat = [r for s in past for r in s["courses"]]
    gpa = round(sum(r["score"] * r["credits"] for r in flat) / sum(r["credits"] for r in flat), 1) if flat else None
    return {"courses": out, "past": past, "average": gpa, "credits": sum(r["credits"] for r in flat)}


@R("GET", "/api/courses/{id:int}/attendance", roles=("teacher", "admin", "leader"))
def course_attendance(req):
    c = req.db
    co = course_access(req, req.params["id"])
    lessons = rows(c, "SELECT l.*, SUM(a.status='present') present, SUM(a.status='late') late, SUM(a.status='absent') absent, "
                      "SUM(a.status='excused') excused FROM lessons l LEFT JOIN attendance a ON a.lesson_id=l.id WHERE l.course_id=? "
                      "GROUP BY l.id ORDER BY l.day DESC, l.start DESC LIMIT 12", (co["id"],))
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
    for x in rows(c, "SELECT * FROM timetable WHERE weekday=? ORDER BY start", (t.isoweekday(),)):
        co = next((k for k in cs if k["id"] == x["course_id"]), None)
        if co:
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
    approved = [r["id"] for r in rows(c, "SELECT id FROM questions WHERE course_id=? AND status='approved'", (course["id"],))]
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


@R("POST", "/api/tutor/{cid:int}/ask", roles=("student", "teacher"))
def tutor_ask(req):
    c, u = req.db, req.user
    course = course_access(req, req.params["cid"])
    body = req.json()
    msg = (body.get("message") or "").strip()[:2000]
    if not msg:
        raise HTTPError(400, "Sual boşdur")
    if course["tutor_locked"] and u["role"] == "student":
        raise HTTPError(423, "Müəllim bu fənn üzrə tutoru müvəqqəti bağlayıb (məsələn, test davam edir).")
    modes = J(course["tutor_modes"], ["socratic"])
    mode = body.get("mode") if body.get("mode") in modes else modes[0]
    used, lim = check_limit(c, u)
    masked, pii = engine.mask_pii(msg) if setting(c, "limits", {}).get("pii_masking", True) else (msg, [])
    hist = history(c, u["id"], course["id"], "tutor", 12)
    note = None
    if mode == "practice":
        result = practice_turn(c, course, masked, hist, req.lang)
    else:
        hits = search_chunks(course["id"], masked)
        result = None
        if engine.llm_config()["enabled"] and hits and hits[0]["score"] >= 1.2:
            try:
                result = tutor.llm_tutor(mode, masked, hits, hist, course, req.lang)
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
    r = int(req.json().get("rating") or 0)
    req.db.execute("UPDATE messages SET rating=? WHERE id=? AND user_id=?", (r if r in (1, -1) else None, req.params["id"], req.user["id"]))
    return {"ok": True}


@R("POST", "/api/tutor/{cid:int}/forward", roles=("student",))
def forward(req):
    c = req.db
    course = course_access(req, req.params["cid"])
    b = req.json()
    q = (b.get("question") or "").strip()
    if not q:
        raise HTTPError(400, "Sual boşdur")
    c.execute("INSERT INTO teacher_questions(course_id,student_id,anonymous,question,context,status,created_at) VALUES(?,?,?,?,?,'open',?)",
              (course["id"], req.user["id"], 1 if b.get("anonymous") else 0, q[:2000], (b.get("context") or "")[:1500], iso(now())))
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
    msg = (req.json().get("message") or "").strip()[:1500]
    if not msg:
        raise HTTPError(400, "Sual boşdur")
    used, lim = check_limit(c, u)
    masked, pii = engine.mask_pii(msg)
    result = tutor.compose_campus(masked, engine.INDEX["campus"].search(tutor.expand_query(masked), k=3), req.lang)
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
    answers = req.json().get("answers") or {}
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
    audit(c, u["id"], "quiz_submit", "quiz", f"{qz['title']}: {score}/{len(details)}")
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
    b = req.json()
    name = (b.get("filename") or "material.txt")[:200]
    try:
        data = base64.b64decode(b.get("content_b64") or "", validate=False)
    except ValueError:
        raise HTTPError(400, "Fayl oxunmadı")
    if not data:
        raise HTTPError(400, "Fayl boşdur")
    try:
        text = engine.extract_text(name, data)
    except ValueError as ex:
        raise HTTPError(400, str(ex))
    except Exception:
        raise HTTPError(400, "Fayldan mətn çıxarmaq mümkün olmadı")
    if len(text.strip()) < 40:
        raise HTTPError(400, "Fayldan kifayət qədər mətn çıxarılmadı")
    title = (b.get("title") or re.sub(r"\.[^.]+$", "", name)).strip()[:200]
    if not text.lstrip().startswith("#"):
        text = f"# {title}\n\n" + text
    info = store.add_material(c, co["id"], title, name, text, req.user["id"])
    audit(c, req.user["id"], "material_upload", "course", f"{co['code']}: {title}")
    return {"ok": True, **info, "title": title}


@R("DELETE", "/api/materials/{id:int}", roles=("teacher",))
def material_delete(req):
    m = row(req.db, "SELECT * FROM materials WHERE id=?", (req.params["id"],))
    if not m:
        raise HTTPError(404, "Material tapılmadı")
    course_access(req, m["course_id"])
    store.delete_material(req.db, m["id"])
    audit(req.db, req.user["id"], "material_delete", "material", m["title"])
    return {"ok": True}


@R("PUT", "/api/courses/{id:int}/tutor", roles=("teacher",))
def tutor_settings(req):
    co = course_access(req, req.params["id"])
    b = req.json()
    modes = [m for m in b.get("modes", []) if m in tutor.MODES] or ["socratic"]
    req.db.execute("UPDATE courses SET tutor_modes=?, tutor_rules=?, tutor_locked=? WHERE id=?",
                   (json.dumps(modes), (b.get("rules") or "")[:2000], 1 if b.get("locked") else 0, co["id"]))
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
    a = (req.json().get("answer") or "").strip()
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
    b = req.json()
    co = course_access(req, int(b.get("course_id") or 0))
    count = max(1, min(int(b.get("count") or 6), 15))
    types = [t for t in (b.get("types") or ["mcq", "tf", "numeric"]) if t in ("mcq", "tf", "numeric")] or ["mcq"]
    if b.get("material_id"):
        chunks = rows(c, "SELECT id, heading, text FROM chunks WHERE material_id=? AND course_id=? ORDER BY seq", (int(b["material_id"]), co["id"]))
    else:
        chunks = rows(c, "SELECT id, heading, text FROM chunks WHERE course_id=? ORDER BY material_id, seq", (co["id"],))
    if not chunks:
        raise HTTPError(400, "Əvvəlcə material yükləyin")
    course_gl = [g for m in rows(c, "SELECT text FROM materials WHERE course_id=?", (co["id"],)) for g in engine.glossary(m["text"])]
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
        out.append(q_out(c, q))
    audit(c, u["id"], "ai_generate", "course", f"{co['code']}: {len(out)} sual")
    return {"questions": out, "engine": engine.engine_info()}


@R("GET", "/api/questions", roles=("teacher",))
def questions(req):
    co = course_access(req, int(req.query.get("course_id") or 0))
    st = req.query.get("status")
    sql = "SELECT * FROM questions WHERE course_id=?" + (" AND status=?" if st else "") + " ORDER BY status='approved', id DESC"
    return [q_out(req.db, q) for q in rows(req.db, sql, (co["id"], st) if st else (co["id"],))]


@R("PUT", "/api/questions/{id:int}", roles=("teacher",))
def question_update(req):
    c = req.db
    q = q_load(c, req.params["id"])
    course_access(req, q["course_id"])
    b = req.json()
    fields = {k: str(b[k])[:3000] for k in ("text", "explanation", "topic", "bloom", "difficulty", "unit") if k in b}
    if "options" in b:
        fields["options"] = json.dumps([str(o)[:300] for o in b["options"]][:6], ensure_ascii=False)
    if "answer" in b:
        fields["answer"] = json.dumps(b["answer"])
    if b.get("status") in ("draft", "approved"):
        fields["status"] = b["status"]
    if fields:
        c.execute(f"UPDATE questions SET {', '.join(k + '=?' for k in fields)} WHERE id=?", (*fields.values(), q["id"]))
    nq = row(c, "SELECT * FROM questions WHERE id=?", (q["id"],))
    store.index_question(nq)
    return q_out(c, nq)


@R("DELETE", "/api/questions/{id:int}", roles=("teacher",))
def question_delete(req):
    q = q_load(req.db, req.params["id"])
    course_access(req, q["course_id"])
    req.db.execute("DELETE FROM questions WHERE id=?", (q["id"],))
    engine.INDEX["questions"].remove(q["id"])
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
    co = course_access(req, int(b.get("course_id") or 0))
    ids = [int(i) for i in b.get("question_ids") or []]
    if not ids:
        raise HTTPError(400, "Ən azı bir sual seçin")
    ok = {r["id"] for r in rows(c, f"SELECT id FROM questions WHERE course_id=? AND status='approved' AND id IN ({','.join('?' * len(ids))})", (co["id"], *ids))}
    if len(ok) != len(ids):
        raise HTTPError(400, "Yalnız təsdiqlənmiş suallar testə əlavə oluna bilər")
    title = (b.get("title") or "Yeni test").strip()[:200]
    kind = "graded" if b.get("kind") == "graded" else "practice"
    qid = c.execute("INSERT INTO quizzes(course_id,title,kind,question_ids,time_limit,attempts,show_explanations,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (co["id"], title, kind, json.dumps(ids), max(1, min(int(b.get("time_limit") or 15), 180)),
                     max(1, min(int(b.get("attempts") or (3 if kind == "practice" else 1)), 10)), 1, iso(now()))).lastrowid
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
    buckets, per_q = [0] * 6, {}
    for a in ats:
        p = 100 * a["score"] / a["max_score"] if a["max_score"] else 0
        buckets[0 if p <= 50 else min(5, int((p - 51) // 10) + 1)] += 1
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
            "buckets": buckets, "labels": ["0–50", "51–60", "61–70", "71–80", "81–90", "91–100"], "questions": qs}
