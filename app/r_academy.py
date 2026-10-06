"""Teacher academy, tech-solutions catalog and the syllabus assistant."""
from __future__ import annotations

import html
import json
import re

from . import engine, store
from .common import R, course_access, ctx
from .i18n import S_, T3

VOCAB = [S_("Sertifikat")]  # stored document titles look like "Sertifikat: <track>" and are translated part by part on display
from .store import J, audit, iso, notify, now, row, rows, setting
from .web import HTTPError, html_resp

e = html.escape
PREREQ = {"ELM-2105": "Fizika I, Ali riyaziyyat I", "KOMP-1102": "İnformatikanın əsasları", "RİY-1101": "—", "FİZ-1103": "Ali riyaziyyat I (paralel)",
          "QRF-1104": "—", "İNG-1105": "Xarici dil II"}


def _cert(c, uid, track):
    return row(c, "SELECT id, reg_no, verify_code, issued_at FROM documents WHERE kind='certificate' AND holder_id=? AND status='valid' AND data LIKE ?",
               (uid, f'%"track": "{track}"%'))


def recommended(prefs, tracks_progress):
    sa = (prefs or {}).get("self_assessment") or {}
    if not sa:
        return []
    cand = [k for k, _ in sorted(sa.items(), key=lambda kv: kv[1]) if tracks_progress.get(k, 0) < 100]
    return cand[:3]


@R("GET", "/api/academy", roles=("teacher",))
def academy(req):
    c, u = req.db, req.user
    prog = {r["module_id"]: r for r in rows(c, "SELECT * FROM academy_progress WHERE user_id=?", (u["id"],))}
    tracks, pct, hours, certs = [], {}, 0.0, []
    for t in rows(c, "SELECT * FROM academy_tracks ORDER BY seq"):
        mods = rows(c, "SELECT id, seq, title, minutes FROM academy_modules WHERE track_key=? ORDER BY seq", (t["key"],))
        done = 0
        for m in mods:
            p = prog.get(m["id"])
            m["status"], m["score"] = (p["status"], p["score"]) if p else ("todo", None)
            if p and p["status"] == "completed":
                done += 1
                hours += m["minutes"] / 60
        cert = _cert(c, u["id"], t["key"])
        if cert:
            certs.append({**cert, "track": t["title"]})
        pct[t["key"]] = round(100 * done / len(mods)) if mods else 0
        tracks.append({**t, "outcomes": J(t["outcomes"], []), "modules": mods, "done": done, "total": len(mods), "percent": pct[t["key"]],
                       "minutes": sum(m["minutes"] for m in mods), "certificate": cert,
                       "next": next((m["id"] for m in mods if m["status"] != "completed"), None)})
    prefs = J(u.get("prefs"), {}) or {}
    return {"tracks": tracks, "hours": round(hours, 1), "certificates": certs, "self_assessment": setting(c, "self_assessment", []),
            "assessment": prefs.get("self_assessment") or {}, "recommended": recommended(prefs, pct)}


@R("PUT", "/api/academy/assessment", roles=("teacher",))
def assessment(req):
    c, u = req.db, req.user
    vals = {k: max(1, min(5, int(v))) for k, v in (req.json().get("values") or {}).items()
            if k in {t["key"] for t in rows(c, "SELECT key FROM academy_tracks")}}
    prefs = J(u.get("prefs"), {}) or {}
    prefs["self_assessment"] = vals
    c.execute("UPDATE users SET prefs=? WHERE id=?", (json.dumps(prefs, ensure_ascii=False), u["id"]))
    req.user["prefs"] = json.dumps(prefs)
    return academy(req)


@R("GET", "/api/academy/module/{id:int}", roles=("teacher",))
def module(req):
    c, u = req.db, req.user
    m = row(c, "SELECT * FROM academy_modules WHERE id=?", (req.params["id"],))
    if not m:
        raise HTTPError(404, "Modul tapılmadı")
    for k in ("paragraphs", "key_points", "phrases"):
        m[k] = J(m[k], [])
    m["quiz"] = [{"q": x["q"], "o": x["o"]} for x in J(m["quiz"], [])]
    m["progress"] = row(c, "SELECT * FROM academy_progress WHERE user_id=? AND module_id=?", (u["id"], m["id"]))
    m["track"] = row(c, "SELECT key, title, color, icon FROM academy_tracks WHERE key=?", (m["track_key"],))
    sib = rows(c, "SELECT id, seq, title FROM academy_modules WHERE track_key=? ORDER BY seq", (m["track_key"],))
    i = next(k for k, s in enumerate(sib) if s["id"] == m["id"])
    m["prev"] = sib[i - 1]["id"] if i > 0 else None
    m["next"] = sib[i + 1]["id"] if i + 1 < len(sib) else None
    m["count"] = len(sib)
    return m


@R("POST", "/api/academy/module/{id:int}/complete", roles=("teacher",))
def complete(req):
    c, u = req.db, req.user
    m = row(c, "SELECT * FROM academy_modules WHERE id=?", (req.params["id"],))
    if not m:
        raise HTTPError(404, "Modul tapılmadı")
    quiz = J(m["quiz"], [])
    answers = req.json().get("answers") or []
    correct = sum(1 for i, x in enumerate(quiz) if i < len(answers) and answers[i] == x["a"])
    score = round(100 * correct / len(quiz)) if quiz else 100
    result = {"passed": score >= 50, "score": score, "correct": [x["a"] for x in quiz], "certificate": None}
    if result["passed"]:
        c.execute("INSERT OR REPLACE INTO academy_progress(user_id,module_id,status,score,completed_at) VALUES(?,?,?,?,?)",
                  (u["id"], m["id"], "completed", score, iso(now())))
        t = row(c, "SELECT * FROM academy_tracks WHERE key=?", (m["track_key"],))
        total = row(c, "SELECT COUNT(*) n, SUM(minutes) mins FROM academy_modules WHERE track_key=?", (t["key"],))
        done = row(c, "SELECT COUNT(*) n FROM academy_progress p JOIN academy_modules am ON am.id=p.module_id WHERE p.user_id=? AND am.track_key=? "
                      "AND p.status='completed'", (u["id"], t["key"]))["n"]
        if done >= total["n"] and not _cert(c, u["id"], t["key"]):
            hours = round(total["mins"] / 60, 1)
            doc = store.issue_document(c, "certificate", u["id"], f"Sertifikat: {t['title']}",
                                       {"program": t["title"], "track": t["key"], "modules": total["n"], "hours": f"{hours:g}".replace(".", ",")}, u["id"], "SRT")
            result["certificate"] = {k: doc[k] for k in ("id", "reg_no", "verify_code")}
            notify(c, u["id"], "academy", T3("Sertifikat verildi: {track}", track=t["title"]), doc["reg_no"], "/teacher/academy")
            audit(c, u["id"], "certificate_issue", "academy", doc["reg_no"])
    return result


# ---------------------------------------------------------------- tools
def _price_tone(pricing: str) -> str:
    """Badge tone decided on the Azerbaijani source text, before the response is translated."""
    return "free" if re.search(r"(?i)pulsuz", pricing) else "paid" if re.search(r"(?i)ödənişli", pricing) else "other"


@R("GET", "/api/tools", roles=("teacher", "admin", "leader"))
def tools(req):
    c, u = req.db, req.user
    areas = setting(c, "tool_areas", {})
    mine = setting(c, "dept_areas", {}).get(u.get("dept") or "", [])
    items = [{**t, "areas": J(t["areas"], []), "use_cases": J(t["use_cases"], []), "steps": J(t["steps"], []), "price_tone": _price_tone(t["pricing"])}
             for t in rows(c, "SELECT * FROM tools ORDER BY seq")]
    cs = rows(c, "SELECT id, name, code, color FROM courses WHERE teacher_id=? ORDER BY id", (u["id"],))
    for co in cs:
        co["tools"] = [r["tool_key"] for r in rows(c, "SELECT tool_key FROM course_tools WHERE course_id=?", (co["id"],))]
    return {"tools": items, "areas": areas, "my_areas": mine, "courses": cs}


@R("POST", "/api/courses/{id:int}/tools", roles=("teacher",))
def course_tool(req):
    c, u = req.db, req.user
    co = course_access(req, req.params["id"])
    key = req.json().get("tool_key")
    if not row(c, "SELECT 1 FROM tools WHERE key=?", (key,)):
        raise HTTPError(400, "Alət tapılmadı")
    if row(c, "SELECT 1 FROM course_tools WHERE course_id=? AND tool_key=?", (co["id"], key)):
        c.execute("DELETE FROM course_tools WHERE course_id=? AND tool_key=?", (co["id"], key))
        on = False
    else:
        c.execute("INSERT INTO course_tools(course_id,tool_key,added_by,created_at) VALUES(?,?,?,?)", (co["id"], key, u["id"], iso(now())))
        on = True
    return {"on": on, "tools": [r["tool_key"] for r in rows(c, "SELECT tool_key FROM course_tools WHERE course_id=?", (co["id"],))]}


# ---------------------------------------------------------------- syllabus assistant
def _lc(s):
    return s if s[:2].isupper() else engine.az_lower(s[:1]) + s[1:]


def build_syllabus(c, co, weeks=15):
    teacher = row(c, "SELECT full_name, title FROM users WHERE id=?", (co["teacher_id"],))
    weekly = rows(c, "SELECT kind, COUNT(*) n FROM timetable WHERE course_id=? GROUP BY kind", (co["id"],))
    pairs = sum(w["n"] for w in weekly)
    contact = pairs * 2 * weeks
    total = co["credits"] * 30
    mats = rows(c, "SELECT id, title, text FROM materials WHERE course_id=? ORDER BY id", (co["id"],))
    outcomes, topics = [], []
    for m in mats:
        gl = [t for t, _ in engine.glossary(m["text"])][:3]
        if engine.code_blocks(m["text"]):
            act = "uyğun proqram kodunu yazır və test edir"
        elif engine.formulas(m["text"]):
            act = "müvafiq düsturları məsələ həllində tətbiq edir"
        else:
            act = "onları praktik nümunələrdə tətbiq edir"
        if gl:
            names = ", ".join(_lc(g) for g in gl[:-1]) + (f" və {_lc(gl[-1])}" if len(gl) > 1 else _lc(gl[0]))
            outcomes.append(f"{names} anlayışlarını izah edir və {act}")
        for h in [ch["heading"] for ch in rows(c, "SELECT heading FROM chunks WHERE material_id=? ORDER BY seq", (m["id"],))]:
            h = re.sub(r"\s*\(\d+\)$", "", h)
            if h not in ("Əsas anlayışlar", "Giriş", "Tipik səhvlər") and not h.startswith("Key vocabulary") and h not in topics:
                topics.append(h)
    outcomes.append("mövzular üzrə tipik səhvləri tanıyır, nəticələrin düzgünlüyünü yoxlayır və əsaslandırır")
    plan, ti = [], 0
    labs = any(w["kind"] == "Laboratoriya" for w in weekly)
    for w in range(1, weeks + 1):
        if w == 7:
            plan.append({"week": w, "topic": "Kollokvium 1", "activity": "Yazılı kollokvium (mövzular 1–6)"})
        elif w == 13:
            plan.append({"week": w, "topic": "Kollokvium 2", "activity": "Yazılı kollokvium (mövzular 8–12)"})
        elif w == weeks:
            plan.append({"week": w, "topic": "Təkrar və imtahana hazırlıq", "activity": "AI tutorun Məşq rejimi, sual-cavab"})
        else:
            topic = topics[ti % len(topics)] if topics else "Mövzu"
            ti += 1
            act = "Mühazirə + AI tutorla dərsdən əvvəl hazırlıq"
            if labs and w % 2 == 0:
                act += f"; laboratoriya işi {w // 2}"
            plan.append({"week": w, "topic": topic, "activity": act})
    tl = [r["name"] for r in rows(c, "SELECT t.name FROM course_tools ct JOIN tools t ON t.key=ct.tool_key WHERE ct.course_id=?", (co["id"],))]
    return {
        "course": {"name": co["name"], "code": co["code"], "credits": co["credits"], "teacher": teacher["full_name"] if teacher else "",
                   "teacher_title": teacher["title"] if teacher else "", "semester": setting(c, "university")["semester"],
                   "prereq": PREREQ.get(co["code"], "—"), "language": "İngilis dili" if co["code"].startswith("İNG") else "Azərbaycan dili"},
        "description": co["description"] + " Fənn nəzəri biliklərin mühəndislik məsələlərinin həllində tətbiqinə yönəlib.",
        "workload": {"total": total, "contact": contact, "independent": max(total - contact, 0), "weeks": weeks, "pairs": pairs},
        "outcomes": outcomes[:6],
        "plan": plan,
        "assessment": [["Davamiyyət", 10], ["Sərbəst işlər (2 × 5)", 10], ["Laboratoriya / məşğələ", 10], ["Kollokviumlar (2 × 10)", 20], ["Semestr imtahanı", 50]],
        "materials": [m["title"] for m in mats] + ["[Əsas dərslik — müəllim tərəfindən əlavə edilməlidir]"],
        "tools": tl + ["Zəka AI tutor və Test studiyası"],
        "policies": [
            "Davamiyyət: buraxılmış dərslər ümumi saatların 25%-ni keçərsə, tələbə imtahana buraxılmaya bilər. Üzrlü səbəblər Zəka platformasında sənədlə təsdiqlənir.",
            "Tapşırıqlar: gecikmiş tapşırıqlar üçün hər gecikmiş gün üçün balın 10%-i çıxılır (ən çox 3 gün).",
            "Akademik dürüstlük: köçürmə və plagiat qadağandır; aşkar edildikdə iş qiymətləndirilmir.",
            "Süni intellekt: AI tutordan izah və məşq üçün istifadə etmək olar; AI-ın yazdığı mətni və ya həlli öz işi kimi təqdim etmək qadağandır. AI istifadəsi tapşırıqda açıqlanmalıdır.",
            "Əlaqə: suallar Zəka platforması vasitəsilə göndərilir, cavab 2 iş günü ərzində verilir.",
        ],
        "generated_at": iso(now()),
    }


@R("GET", "/api/syllabus/{cid:int}", roles=("teacher",))
def syllabus_get(req):
    co = course_access(req, req.params["cid"])
    s = row(req.db, "SELECT * FROM syllabi WHERE course_id=?", (co["id"],))
    return {"saved": J(s["data"], None) if s else None, "updated_at": s["updated_at"] if s else None}


@R("POST", "/api/syllabus/{cid:int}/generate", roles=("teacher",))
def syllabus_generate(req):
    co = course_access(req, req.params["cid"])
    weeks = max(10, min(int(req.json().get("weeks") or 15), 18))
    audit(req.db, req.user["id"], "syllabus_generate", "course", co["code"])
    return build_syllabus(req.db, co, weeks)


@R("PUT", "/api/syllabus/{cid:int}", roles=("teacher",))
def syllabus_save(req):
    co = course_access(req, req.params["cid"])
    data = req.json().get("data")
    if not isinstance(data, dict) or "course" not in data:
        raise HTTPError(400, "Sillabus məlumatı düzgün deyil")
    req.db.execute("INSERT OR REPLACE INTO syllabi(course_id,user_id,data,updated_at) VALUES(?,?,?,?)",
                   (co["id"], req.user["id"], json.dumps(data, ensure_ascii=False)[:200000], iso(now())))
    return {"ok": True, "updated_at": iso(now())}


@R("POST", "/api/syllabus/{cid:int}/link", roles=("teacher",))
def syllabus_link(req):
    co = course_access(req, req.params["cid"])
    from .common import make_key
    return {"url": f"/syllabus/{co['id']}?k={make_key('syl', co['id'], req.user['id'])}"}


@R("GET", "/syllabus/{cid:int}", roles=("teacher", "admin", "leader"))
def syllabus_page(req):
    c = req.db
    co = course_access(req, req.params["cid"]) if req.user["role"] == "teacher" else row(c, "SELECT * FROM courses WHERE id=?", (req.params["cid"],))
    s = row(c, "SELECT data FROM syllabi WHERE course_id=?", (co["id"],))
    d = J(s["data"], None) if s else build_syllabus(c, co)
    uni = ctx(c)["university"]
    li = lambda xs: "".join(f"<li>{e(str(x))}</li>" for x in xs)
    plan = "".join(f"<tr><td>{p['week']}</td><td>{e(p['topic'])}</td><td>{e(p['activity'])}</td></tr>" for p in d["plan"])
    ass = "".join(f"<tr><td>{e(a)}</td><td>{b}</td></tr>" for a, b in d["assessment"])
    w = d["workload"]
    body = f"""<div class="toolbar no-print"{' hidden' if req.query.get('embed') == '1' else ''}><button id="print-btn">🖨 Çap et / PDF kimi saxla</button></div>
<div class="paper syllabus"><header class="doc-head"><img class="crest" src="/static/img/brand/icon.png" alt="AzTU">
<div><div class="org">{e(uni['name'].upper())}</div><div class="sub">Fənn proqramı (sillabus) · {e(d['course']['semester'])}</div></div></header>
<h1>{e(d['course']['name'])}</h1>
<table class="meta"><tr><th>Fənnin kodu</th><td>{e(d['course']['code'])}</td><th>Kredit (AKTS)</th><td>{d['course']['credits']}</td></tr>
<tr><th>Müəllim</th><td>{e(d['course']['teacher'])}</td><th>Tədris dili</th><td>{e(d['course']['language'])}</td></tr>
<tr><th>Ön şərtlər</th><td>{e(d['course']['prereq'])}</td><th>İş yükü</th><td>{w['total']} saat (auditoriya {w['contact']}, sərbəst {w['independent']})</td></tr></table>
<h3>Fənnin təsviri</h3><p>{e(d['description'])}</p>
<h3>Təlim nəticələri</h3><p>Fənni uğurla bitirən tələbə:</p><ol>{li(d['outcomes'])}</ol>
<h3>Həftəlik plan</h3><table class="grades"><tr><th>Həftə</th><th>Mövzu</th><th>Fəaliyyət</th></tr>{plan}</table>
<h3>Qiymətləndirmə</h3><table class="grades"><tr><th>Komponent</th><th>Bal</th></tr>{ass}<tr><th>Cəmi</th><th>100</th></tr></table>
<h3>Materiallar və ədəbiyyat</h3><ul>{li(d['materials'])}</ul>
<h3>Rəqəmsal alətlər</h3><ul>{li(d['tools'])}</ul>
<h3>Qaydalar</h3><ul>{li(d['policies'])}</ul>
<footer class="doc-foot">Zəka platformasının AI sillabus köməkçisi ilə hazırlanıb və müəllim tərəfindən redaktə olunub · DEMO</footer></div>"""
    return html_resp(f"""<!doctype html><html lang="az"><head><meta charset="utf-8"><title>Sillabus · {e(d['course']['name'])}</title>
<link rel="icon" href="/static/img/brand/icon.png"><link rel="stylesheet" href="/static/css/doc.css"></head><body>{body}
<script src="/static/js/print.js"></script></body></html>""")
