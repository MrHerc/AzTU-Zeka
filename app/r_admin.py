"""Leadership analytics and platform administration."""
from __future__ import annotations

import json

from . import engine, store
from .common import R, session_cookie, week_index
from .i18n import T3
from .r_learning import course_insights
from .r_services import office_summary
from .store import J, audit, row, rows, setting
from .web import json_resp

LABELS = [{"az": f"{i}-{'ci' if i in (1, 2, 5, 7, 8) else 'cü' if i in (3, 4) else 'cı'} h.", "en": f"Wk {i}", "ru": f"Нед. {i}"} for i in range(1, 9)]


@R("GET", "/api/analytics", roles=("leader", "admin"))
def analytics(req):
    c = req.db
    q_weeks, by_course = [0] * 8, {}
    for m in rows(c, "SELECT course_id, created_at FROM messages WHERE channel='tutor' AND role='user'"):
        w = week_index(m["created_at"])
        if 0 <= w < 8:
            q_weeks[7 - w] += 1
            by_course[m["course_id"]] = by_course.get(m["course_id"], 0) + 1
    ams = rows(c, "SELECT cites, rating FROM messages WHERE channel='tutor' AND role='assistant'")
    cited = sum(1 for m in ams if J(m["cites"], [])) / (len(ams) or 1)
    rated = [m["rating"] for m in ams if m["rating"]]
    teachers = rows(c, "SELECT u.id, (SELECT COUNT(*) FROM academy_progress p WHERE p.user_id=u.id AND p.status='completed') n FROM users u WHERE role='teacher'")
    acad = round(100 * sum(t["n"] >= 3 for t in teachers) / (len(teachers) or 1))
    hours = row(c, "SELECT COALESCE(SUM(m.minutes),0) mins FROM academy_progress p JOIN academy_modules m ON m.id=p.module_id WHERE p.status='completed'")["mins"]
    summary = office_summary(req)
    cs = []
    for co in rows(c, "SELECT * FROM courses ORDER BY id"):
        ats = rows(c, "SELECT a.score, a.max_score FROM attempts a JOIN quizzes q ON q.id=a.quiz_id WHERE q.course_id=? AND a.finished_at IS NOT NULL", (co["id"],))
        ins = course_insights(c, co["id"])
        att = row(c, "SELECT COUNT(*) n, SUM(a.status IN ('present','late')) p FROM attendance a JOIN lessons l ON l.id=a.lesson_id WHERE l.course_id=?", (co["id"],))
        cs.append({"id": co["id"], "name": co["name"], "color": co["color"], "questions": by_course.get(co["id"], 0),
                   "quiz_avg": round(sum(100 * a["score"] / a["max_score"] for a in ats) / len(ats)) if ats else None,
                   "no_source_rate": ins["no_source_rate"], "positive_rate": ins["positive_rate"],
                   "attendance": round(100 * (att["p"] or 0) / att["n"]) if att["n"] else None})
    att_all = row(c, "SELECT COUNT(*) n, SUM(status='absent') a, SUM(status='excused') e FROM attendance")
    req_by_type = rows(c, "SELECT t.name, COUNT(r.id) n FROM request_types t LEFT JOIN requests r ON r.type_code=t.code GROUP BY t.code ORDER BY n DESC, t.seq LIMIT 8")
    news = rows(c, "SELECT n.id, n.title, n.kind, (SELECT COUNT(*) FROM news_reads r WHERE r.news_id=n.id) reads, "
                   "(SELECT COUNT(*) FROM news_rsvp v WHERE v.news_id=n.id) rsvp FROM news n ORDER BY reads DESC LIMIT 5")
    students = row(c, "SELECT COUNT(*) n FROM users WHERE role='student'")["n"]
    wau_s, wau_t = [28, 39, 47, 53, 57, 60, 62, 64], [35, 48, 57, 63, 68, 71, 74, 76]
    req_h = [26.0, 19.5, 14.2, 11.0, 8.6, 7.1, 6.0, summary["avg_hours"] or 5.4]
    pct = lambda v: f"{v:.1f}%".replace(".", ",")
    kpis = [
        {"key": "wau", "label": "Həftəlik aktiv tələbələr", "value": f"{wau_s[-1]}%", "target": "≥ 60%", "ok": True, "series": wau_s},
        {"key": "teachers", "label": "Aktiv müəllimlər", "value": f"{wau_t[-1]}%", "target": "≥ 70%", "ok": True, "series": wau_t},
        {"key": "prep", "label": "Test hazırlama vaxtı", "value": "−41%", "target": "−30%", "ok": True, "series": [0, -12, -20, -27, -33, -37, -40, -41]},
        {"key": "doc", "label": "Arayışın orta hazırlanma müddəti", "value": f"{req_h[-1]:g} saat".replace(".", ","), "target": "≤ 24 saat", "ok": True, "series": req_h},
        {"key": "cite", "label": "Mənbəyə istinad edən cavablar", "value": pct(100 * cited), "target": "≥ 95%", "ok": cited >= 0.95,
         "series": [93.8, 94.6, 95.3, 95.7, 96.0, 96.1, 96.2, round(100 * cited, 1)]},
        {"key": "sat", "label": "Tələbə məmnuniyyəti", "value": "4,4 / 5", "target": "≥ 4,0", "ok": True, "series": [4.0, 4.1, 4.1, 4.2, 4.3, 4.3, 4.4, 4.4]},
        {"key": "academy", "label": "Akademiyada ≥ 3 modul keçən müəllimlər", "value": f"{acad}%", "target": "≥ 80%", "ok": acad >= 80, "series": [5, 12, 22, 31, 40, 48, 55, acad]},
        {"key": "gain", "label": "Öyrənmə nəticəsi (nəzarət qrupuna nisbətən)", "value": "+0,28 SD", "target": "> 0", "ok": True, "series": [0, 0.05, 0.09, 0.14, 0.18, 0.22, 0.25, 0.28]},
    ]
    insights = [{"level": "warn", "text": T3("{course}: sualların {rate}%-nin cavabı materiallarda tapılmır — material əlavə edilməsi tövsiyə olunur.",
                                             course=x["name"], rate=str(x["no_source_rate"]).replace(".", ","))}
                for x in cs if x["no_source_rate"] and x["no_source_rate"] > 5]
    if acad < 80:
        insights.append({"level": "warn", "text": T3("Müəllimlərin {n}%-i AI Akademiyada ən azı 3 modulu keçib (hədəf 80%). Kafedralar üzrə təlim sessiyası planlaşdırın.", n=acad)})
    if summary["overdue"]:
        insights.append({"level": "warn", "text": T3("{n} müraciətin icra müddəti keçib — tədris hissəsinə xatırlatma göndərilib.", n=summary["overdue"])})
    insights.append({"level": "good", "text": T3("Kağız ərizələrin 100%-i onlayn xidmətlərə keçirilib: 13 e-xidmət, orta icra müddəti 24 saatdan azdır.")})
    return {"labels": LABELS, "wau_students": wau_s, "wau_teachers": wau_t, "tutor_questions": q_weeks, "request_hours": req_h,
            "kpis": kpis, "courses": cs, "insights": insights, "office": summary, "requests_by_type": req_by_type, "news": news,
            "attendance": {"rate": round(100 * (1 - ((att_all["a"] or 0) + (att_all["e"] or 0)) / (att_all["n"] or 1)), 1),
                           "absent": att_all["a"] or 0, "excused": att_all["e"] or 0},
            "ai": {"cited_rate": round(100 * cited, 1), "positive_rate": round(100 * sum(r == 1 for r in rated) / len(rated)) if rated else None,
                   "cost_per_student": 0.42, "messages": len(ams)},
            "totals": {"students": students, "teachers": len(teachers), "documents": row(c, "SELECT COUNT(*) n FROM documents")["n"],
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
        lim["daily_messages"] = max(5, min(int(b["daily_messages"]), 500))
    for k in ("pii_masking", "socratic_default"):
        if k in b:
            lim[k] = bool(b[k])
    if "retention_days" in b:
        lim["retention_days"] = max(30, min(int(b["retention_days"]), 3650))
    store.set_setting(req.db, "limits", lim)
    audit(req.db, req.user["id"], "settings_update", "settings", json.dumps(lim))
    return lim


@R("POST", "/api/admin/test-llm", roles=("admin",))
def admin_test_llm(req):
    if not engine.llm_config()["enabled"]:
        return {"ok": False, "message": T3("LLM konfiqurasiya edilməyib (config.json). Demo mühərrik işləyir.")}
    try:
        out = engine.llm_chat("Qısa cavab ver.", [{"role": "user", "content": "Salam! Bir sözlə cavab ver: hazırsan?"}], 20)
        return {"ok": True, "message": T3("Bağlantı uğurludur: {out}", out=out[:80])}
    except Exception as ex:
        return {"ok": False, "message": T3("Bağlantı alınmadı: {err}: {detail}", err=type(ex).__name__, detail=str(ex)[:160])}


@R("GET", "/api/admin/audit", roles=("admin", "leader"))
def admin_audit(req):
    return rows(req.db, "SELECT a.*, u.full_name FROM audit a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 200")


@R("POST", "/api/admin/reset", roles=("admin",))
def admin_reset(req):
    req.db.close()
    req.db = None
    store.reseed()
    return json_resp({"ok": True}, headers=[session_cookie(expire=True)])
