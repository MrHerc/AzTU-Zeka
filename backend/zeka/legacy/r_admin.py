"""Leadership analytics and platform administration."""
from __future__ import annotations

import json

from . import engine, radar, store
from .common import R, session_cookie, week_index
from ..core.i18n import T3
from .r_learning import course_insights
from .r_services import office_summary
from .store import audit, row, rows, setting
from ..core.web import json_resp
from ..modules.insight import service as insight

LABELS = [{"az": f"{i}-{'ci' if i in (1, 2, 5, 7, 8) else 'cü' if i in (3, 4) else 'cı'} h.", "en": f"Wk {i}", "ru": f"Нед. {i}"} for i in range(1, 9)]


@R("GET", "/api/analytics", roles=("leader", "admin"))
def analytics(req):
    """The leadership dashboard. Its tiles are the measured indicators of the insight module (Task 39); every other
    number here is a count of rows."""
    c = req.db
    q_weeks, by_course = [0] * 8, {}
    for m in rows(c, "SELECT course_id, created_at FROM messages WHERE channel='tutor' AND role='user'"):
        w = week_index(m["created_at"])
        if 0 <= w < 8:
            q_weeks[7 - w] += 1
            by_course[m["course_id"]] = by_course.get(m["course_id"], 0) + 1
    rated = [m["rating"] for m in rows(c, "SELECT rating FROM messages WHERE channel='tutor' AND role='assistant' AND rating IS NOT NULL")]
    answers = row(c, "SELECT COUNT(*) n FROM messages WHERE channel='tutor' AND role='assistant'")["n"]
    hours = row(c, "SELECT COALESCE(SUM(m.minutes),0) mins FROM academy_progress p JOIN academy_modules m ON m.id=p.module_id WHERE p.status='completed'")["mins"]
    summary = office_summary(req)
    cs = []
    att_all = {"n": 0, "a": 0, "e": 0}           # Task 42: the campus totals are the courses' sums, not a scan of attendance
    for co in rows(c, "SELECT * FROM courses ORDER BY id"):
        # Task 42: averaged in SQL; a dict per attempt (100 000 on a university's data) took most of a second
        qa = row(c, "SELECT AVG(100.0 * a.score / a.max_score) avg FROM attempts a JOIN quizzes q ON q.id=a.quiz_id "
                    "WHERE q.course_id=? AND a.finished_at IS NOT NULL", (co["id"],))
        ins = course_insights(c, co["id"])
        att = row(c, "SELECT COUNT(*) n, SUM(a.status IN ('present','late')) p, SUM(a.status='absent') a, SUM(a.status='excused') e "
                     "FROM attendance a JOIN lessons l ON l.id=a.lesson_id WHERE l.course_id=?", (co["id"],))
        for k in att_all:
            att_all[k] += att[k] or 0
        cs.append({"id": co["id"], "name": co["name"], "color": co["color"], "questions": by_course.get(co["id"], 0),
                   "quiz_avg": round(qa["avg"]) if qa["avg"] is not None else None,
                   "no_source_rate": ins["no_source_rate"], "positive_rate": ins["positive_rate"],
                   "attendance": round(100 * (att["p"] or 0) / att["n"]) if att["n"] else None})
    req_by_type = rows(c, "SELECT t.name, COUNT(r.id) n FROM request_types t LEFT JOIN requests r ON r.type_code=t.code GROUP BY t.code ORDER BY n DESC, t.seq LIMIT 8")
    news = rows(c, "SELECT n.id, n.title, n.kind, (SELECT COUNT(*) FROM news_reads r WHERE r.news_id=n.id) reads, "
                   "(SELECT COUNT(*) FROM news_rsvp v WHERE v.news_id=n.id) rsvp FROM news n ORDER BY reads DESC LIMIT 5")
    students = row(c, "SELECT COUNT(*) n FROM users WHERE role='student'")["n"]
    teachers = row(c, "SELECT COUNT(*) n FROM users WHERE role='teacher'")["n"]
    kpis = insight.tiles(c)
    tile = {k["key"]: k for k in kpis}
    insights = [{"level": "warn", "text": T3("{course}: sualların {rate}%-nin cavabı materiallarda tapılmır — material əlavə edilməsi tövsiyə olunur.",
                                             course=x["name"], rate=str(x["no_source_rate"]).replace(".", ","))}
                for x in cs if x["no_source_rate"] and x["no_source_rate"] > 5]
    acad = tile["academy"]
    if acad["ok"] is False:
        insights.append({"level": "warn", "text": T3("Müəllimlərin {n}%-i AI Akademiyada ən azı 3 modulu keçib (hədəf {target}%). Kafedralar üzrə təlim sessiyası planlaşdırın.",
                                                     n=round(acad["value"]), target=acad["target"])})
    if summary["overdue"]:
        insights.append({"level": "warn", "text": T3("{n} müraciətin icra müddəti keçib — tədris hissəsinə xatırlatma göndərilib.", n=summary["overdue"])})
    from .r_radar import leader_insight
    insights.insert(0, leader_insight(c))
    return {"labels": LABELS, "wau_students": tile["wau_student"]["series"], "wau_teachers": tile["wau_teacher"]["series"],
            "active_by_role": insight.active_roles(c), "tutor_questions": q_weeks, "request_hours": tile["request_hours"]["series"],
            "kpis": kpis, "courses": cs, "insights": insights, "office": summary, "requests_by_type": req_by_type, "news": news,
            "radar": radar.summary(c),          # the Radar card: the same summary as its line above (Task 42, F1)
            "attendance": {"rate": round(100 * (1 - ((att_all["a"] or 0) + (att_all["e"] or 0)) / (att_all["n"] or 1)), 1),
                           "absent": att_all["a"] or 0, "excused": att_all["e"] or 0},
            "ai": {"cited_rate": tile["cited"]["value"], "positive_rate": round(100 * sum(r == 1 for r in rated) / len(rated)) if rated else None,
                   "messages": answers},
            "totals": {"students": students, "teachers": teachers, "documents": row(c, "SELECT COUNT(*) n FROM documents")["n"],
                       "questions_bank": row(c, "SELECT COUNT(*) n FROM questions WHERE status='approved'")["n"],
                       "requests": row(c, "SELECT COUNT(*) n FROM requests")["n"], "academy_hours": round(hours / 60),
                       "certificates": row(c, "SELECT COUNT(*) n FROM documents WHERE kind='certificate'")["n"]}}


@R("GET", "/api/admin/status", roles=("admin",))
def admin_status(req):
    c = req.db
    cfg = engine.llm_config()
    tables = ("users", "courses", "materials", "chunks", "questions", "messages", "requests", "files", "documents", "news", "notifications", "lessons")
    return {"engine": engine.engine_info(), "llm": {"provider": cfg.get("provider", "—"), "model": cfg.get("model", "—"),
                                                    "base_url": cfg.get("base_url", "—"), "configured": cfg["enabled"]},
            "limits": setting(c, "limits", {}), "counts": {t: row(c, f"SELECT COUNT(*) n FROM {t}")["n"] for t in tables},
            # Relative to the project folder: the UI must not reveal the host's absolute paths (user name, drive layout).
            "db_path": _rel(store.DB_PATH), "uploads": _rel(store.UPLOADS)}


def _rel(p):
    try:
        return p.resolve().relative_to(store.DATA.resolve().parent).as_posix()
    except ValueError:
        return p.name


@R("PUT", "/api/admin/settings", roles=("admin",))
def admin_settings(req):
    b = req.json()
    lim = setting(req.db, "limits", {})
    if "daily_messages" in b:
        lim["daily_messages"] = b.integer("daily_messages", lim.get("daily_messages", 50), 5, 500)
    for k in ("pii_masking", "socratic_default"):
        if k in b:
            lim[k] = bool(b[k])
    if "retention_days" in b:
        lim["retention_days"] = b.integer("retention_days", lim.get("retention_days", 180), 30, 3650)
    store.set_setting(req.db, "limits", lim)
    purged = store.purge_expired(req.db, batched=False)    # the daily retention job purges a large backlog in batches
    audit(req.db, req.user["id"], "settings_update", "settings", json.dumps(lim) + (f" · {purged} köhnə mesaj silindi" if purged else ""))
    return lim


def cfg_key() -> str:
    return engine.llm_config().get("api_key") or "\0"


@R("POST", "/api/admin/test-llm", roles=("admin",), slow=True)
def admin_test_llm(req):
    if not engine.llm_config()["enabled"]:
        return {"ok": False, "message": T3("LLM konfiqurasiya edilməyib (config.json). Demo mühərrik işləyir.")}
    try:
        out = engine.llm_chat("Qısa cavab ver.", [{"role": "user", "content": "Salam! Bir sözlə cavab ver: hazırsan?"}], 20)
        return {"ok": True, "message": T3("Bağlantı uğurludur: {out}", out=out[:80])}
    except Exception as ex:
        return {"ok": False, "message": T3("Bağlantı alınmadı: {err}: {detail}", err=type(ex).__name__, detail=str(ex)[:160].replace(cfg_key(), "***"))}


@R("GET", "/api/admin/audit", roles=("admin", "leader"))
def admin_audit(req):
    return rows(req.db, "SELECT a.*, u.full_name FROM audit a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 200")


@R("POST", "/api/admin/reset", roles=("admin",), demo=True)
def admin_reset(req):
    req.db.close()
    req.db = None
    store.reseed()
    return json_resp({"ok": True}, headers=[session_cookie(expire=True)])
