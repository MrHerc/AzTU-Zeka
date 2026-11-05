"""Zəka Radar routes: early-warning dashboard, explainable student profile, support plans (teacher → student) and their impact."""
from __future__ import annotations

import json

from . import radar
from .common import R
from .i18n import E, T3
from .store import J, audit, iso, notify, now, row, rows
from .web import HTTPError

VIEW = ("teacher", "office", "leader", "admin")
ACT = ("teacher", "office", "admin")           # leadership reads the radar; teachers and the dean's office act on it
KINDS = ("plan", "consult", "nudge", "office")


def scope(req):
    """(course ids the user may see, course ids to analyse). Teachers see their own courses, staff see all."""
    c, u = req.db, req.user
    if u["role"] == "teacher":
        ids = [r["id"] for r in rows(c, "SELECT id FROM courses WHERE teacher_id=? ORDER BY id", (u["id"],))]
        if not ids:
            raise HTTPError(403, "Sizə təyin olunmuş fənn yoxdur")
    else:
        ids = [r["id"] for r in rows(c, "SELECT id FROM courses ORDER BY id")]
    sel = req.query.get("course")
    if sel and sel.isdigit() and int(sel) in ids:
        return ids, [int(sel)]
    return ids, (ids if u["role"] == "teacher" else None)


def course_brief(c, cid):
    co = row(c, "SELECT id, code, name, color, teacher_id FROM courses WHERE id=?", (cid,))
    t = row(c, "SELECT full_name FROM users WHERE id=?", (co["teacher_id"],)) if co else None
    return {**co, "teacher": t["full_name"] if t else ""} if co else None


def refresh(c, iv: dict) -> dict:
    """Auto-tick plan steps from real activity; close the plan when every step is done (and tell its author)."""
    plan = J(iv["plan"], {}) or {}
    if iv["status"] != "open":
        return plan
    changed = radar.auto_progress(c, iv, plan)
    prog = radar.plan_progress(plan)
    if prog["total"] and prog["done"] == prog["total"]:
        iv["status"], iv["closed_at"] = "completed", iso(now())
        c.execute("UPDATE interventions SET status='completed', closed_at=? WHERE id=?", (iv["closed_at"], iv["id"]))
        st = row(c, "SELECT full_name FROM users WHERE id=?", (iv["student_id"],))
        co = row(c, "SELECT name FROM courses WHERE id=?", (iv["course_id"],))
        notify(c, iv["created_by"], "radar", T3("{student} dəstək planını tamamladı", student=st["full_name"]),
               T3("{course} · bütün addımlar yerinə yetirilib", course=co["name"]), f"/radar/student/{iv['student_id']}?course={iv['course_id']}")
        changed = True
    if changed:
        iv["plan"] = radar.dump(plan)
        iv["updated_at"] = iso(now())
        c.execute("UPDATE interventions SET plan=?, updated_at=? WHERE id=?", (iv["plan"], iv["updated_at"], iv["id"]))
    return plan


def iv_out(c, iv: dict, for_student: bool = False) -> dict:
    plan = refresh(c, iv)
    author = row(c, "SELECT full_name, title FROM users WHERE id=?", (iv["created_by"],))
    out = {"id": iv["id"], "student_id": iv["student_id"], "kind": iv["kind"], "status": iv["status"], "created_at": iv["created_at"],
           "updated_at": iv["updated_at"], "due_at": iv["due_at"], "closed_at": iv["closed_at"], "note": iv["note"] or "", "plan": plan,
           "progress": radar.plan_progress(plan), "course": course_brief(c, iv["course_id"]),
           "author": author["full_name"] if author else "", "author_title": author["title"] if author else ""}
    if not for_student:                      # students see support, never a risk score
        out.update({"risk_before": iv["risk_before"], "level_before": iv["level_before"], "drivers": J(iv["drivers"], [])})
    return out


def student_access(req, sid: int, ids: list[int]):
    c = req.db
    st = row(c, "SELECT u.id, u.full_name, u.patronymic, u.color, u.student_no, u.username, g.name grp FROM users u "
                "LEFT JOIN study_groups g ON g.id=u.group_id WHERE u.id=? AND u.role='student'", (sid,))
    if not st:
        raise HTTPError(404, "Tələbə tapılmadı")
    mine = [r["course_id"] for r in rows(c, "SELECT course_id FROM enrollments WHERE user_id=? ORDER BY course_id", (sid,)) if r["course_id"] in ids]
    if not mine:
        raise HTTPError(403, "Bu tələbə sizin fənlərinizə qeydiyyatda deyil")
    return st, mine


# ---------------------------------------------------------------- dashboard
@R("GET", "/api/radar", roles=VIEW)
def radar_home(req):
    c = req.db
    ids, sel = scope(req)
    an = radar.analysis(c, sel)
    sql = "SELECT id, student_id, course_id, kind, status, plan, created_at FROM interventions WHERE status='open'"
    open_iv = {}
    for iv in rows(c, sql + " ORDER BY id"):
        if iv["course_id"] in (sel or ids):
            open_iv[iv["student_id"]] = {"id": iv["id"], "course_id": iv["course_id"], "kind": iv["kind"], "created_at": iv["created_at"],
                                         "progress": radar.plan_progress(J(iv["plan"], {}) or {})}
    out_rows = [{**r, "intervention": open_iv.get(r["id"])} for r in an.rows]
    courses = [course_brief(c, cid) for cid in ids]
    return {"scope": {"role": req.user["role"], "courses": courses, "selected": sel[0] if sel and len(sel) == 1 else None,
                      "can_act": req.user["role"] in ACT},
            "counts": an.counts(), "course_counts": an.course_counts(), "rows": out_rows, "gaps": an.cohort_gaps(), "drivers": an.driver_mix(),
            "trend": radar.trend(c, an, sel), "impact": radar.impact(c, an, sel),
            "model": {"weights": radar.WEIGHTS, "levels": {"high": 50, "watch": 30}}, "generated_at": iso(now())}


@R("GET", "/api/radar/student/{sid:int}", roles=VIEW)
def radar_student(req):
    c = req.db
    ids, _ = scope(req)
    st, mine = student_access(req, req.params["sid"], ids)
    an = radar.analysis(c, ids if req.user["role"] == "teacher" else None)
    sid = st["id"]
    q = req.query.get("course")
    cid = int(q) if q and q.isdigit() and int(q) in mine else max(mine, key=lambda x: an.profiles[(sid, x)]["score"])
    p = an.profiles[(sid, cid)]
    att = an.frame.att.get((sid, cid), [])
    peers = [an.profiles[(x, cid)] for x in an.frame.enrolled.get(cid, []) if (x, cid) in an.profiles]
    rates = [x["stats"]["attendance"]["rate"] for x in peers if x["stats"]["attendance"]["rate"] is not None]
    grades = [x["stats"]["assessment"]["grade_pct"] for x in peers if x["stats"]["assessment"]["grade_pct"] is not None]
    rank = sorted(peers, key=lambda x: -x["score"]).index(p) + 1 if p in peers else None
    ivs = rows(c, f"SELECT * FROM interventions WHERE student_id=? AND course_id IN ({','.join('?' * len(mine))}) AND status<>'cancelled' ORDER BY id DESC",
               (sid, *mine))
    row_ = next((r for r in an.rows if r["id"] == sid), None)
    return {"student": {"id": sid, "name": st["full_name"], "patronymic": st["patronymic"], "group": st["grp"], "student_no": st["student_no"],
                        "color": st["color"]},
            "course": course_brief(c, cid), "profile": p, "history": radar.history(an.frame, sid, cid),
            "lessons": [{"day": a[0], "start": a[1], "status": a[2], "topic": a[4]} for a in att[-14:]],
            "courses": [x for x in (row_["courses"] if row_ else []) if x["id"] in mine],
            "cohort": {"students": len(peers), "rank": rank, "attendance": round(sum(rates) / len(rates)) if rates else None,
                       "grades": round(sum(grades) / len(grades)) if grades else None},
            "interventions": [iv_out(c, iv) for iv in ivs],
            "can_act": req.user["role"] in ACT and (req.user["role"] != "teacher" or cid in ids)}


@R("POST", "/api/radar/student/{sid:int}/plan", roles=ACT)
def radar_plan(req):
    c, u = req.db, req.user
    ids, _ = scope(req)
    st, mine = student_access(req, req.params["sid"], ids)
    b = req.json()
    cid = int(b.get("course_id") or 0)
    if cid not in mine:
        raise HTTPError(400, "Fənn seçilməyib")
    course = row(c, "SELECT * FROM courses WHERE id=?", (cid,))
    an = radar.analysis(c, [cid])
    p = an.profiles[(st["id"], cid)]
    kind = b.get("kind") if b.get("kind") in KINDS else ((p["recommendation"] or {}).get("kind") or "plan")
    plan = radar.build_plan(c, p, course, kind, radar.clean_note(b.get("note")))
    if not plan["steps"]:
        raise HTTPError(422, "Bu tələbə üçün plan addımı yaratmaq üçün kifayət qədər məlumat yoxdur")
    if b.get("preview"):
        return {"plan": plan, "score": p["score"], "level": p["level"], "kind": kind}
    if row(c, "SELECT 1 FROM interventions WHERE student_id=? AND course_id=? AND status='open'", (st["id"], cid)):
        raise HTTPError(409, "Bu tələbə üçün bu fənn üzrə açıq dəstək planı artıq var")
    drivers = [{"key": d["key"], "points": d["points"]} for d in p["drivers"]]
    t = iso(now())
    iid = c.execute("INSERT INTO interventions(student_id,course_id,created_by,kind,status,plan,risk_before,level_before,drivers,note,created_at,"
                    "updated_at,due_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (st["id"], cid, u["id"], kind, "open", radar.dump(plan), p["score"], p["level"], json.dumps(drivers), plan["note"], t, t,
                     plan["due_at"])).lastrowid
    notify(c, st["id"], "plan", T3("Sizin üçün fərdi dəstək planı hazırlanıb"),
           T3("{course} · {n} addım · {author}", course=course["name"], n=len(plan["steps"]), author=u["full_name"]), f"/student/plan/{iid}")
    if plan["cc_office"]:
        a = p["stats"]["attendance"]
        notify(c, [r["id"] for r in rows(c, "SELECT id FROM users WHERE role='office'") if r["id"] != u["id"]], "radar",
               T3("Radar: davamiyyət üzrə yönəldilmə"),
               T3("{student} · {course}: {n} üzrsüz qayıb, son {k} dərs ardıcıl", student=st["full_name"], course=course["name"], n=a["absent"], k=a["streak"]),
               f"/radar/student/{st['id']}?course={cid}")
    audit(c, u["id"], "radar_plan", "student", f"{st['full_name']} · {course['code']} · {kind} · risk {p['score']:g}")
    return {"id": iid, "intervention": iv_out(c, row(c, "SELECT * FROM interventions WHERE id=?", (iid,)))}


@R("POST", "/api/interventions/{id:int}/status", roles=ACT)
def intervention_status(req):
    c, u = req.db, req.user
    iv = row(c, "SELECT * FROM interventions WHERE id=?", (req.params["id"],))
    if not iv:
        raise HTTPError(404, "Plan tapılmadı")
    ids, _ = scope(req)
    if iv["course_id"] not in ids:
        raise HTTPError(403, "Bu plan sizin fənninizə aid deyil")
    st = req.json().get("status")
    if st not in ("completed", "cancelled"):
        raise HTTPError(400, "Yanlış status")
    if iv["status"] != "open":
        raise HTTPError(409, "Plan artıq bağlanıb")
    c.execute("UPDATE interventions SET status=?, closed_at=?, updated_at=? WHERE id=?", (st, iso(now()), iso(now()), iv["id"]))
    audit(c, u["id"], "radar_plan_" + st, "intervention", f"#{iv['id']}")
    return iv_out(c, row(c, "SELECT * FROM interventions WHERE id=?", (iv["id"],)))


# ---------------------------------------------------------------- the student's side: support, not a label
def own_plan(req, iid: int) -> dict:
    iv = row(req.db, "SELECT * FROM interventions WHERE id=? AND student_id=? AND status<>'cancelled'", (iid, req.user["id"]))
    if not iv:
        raise HTTPError(404, "Plan tapılmadı")
    return iv


@R("GET", "/api/student/plans", roles=("student",))
def student_plans(req):
    c = req.db
    ivs = rows(c, "SELECT * FROM interventions WHERE student_id=? AND status<>'cancelled' ORDER BY status='open' DESC, id DESC LIMIT 10", (req.user["id"],))
    return {"items": [iv_out(c, iv, for_student=True) for iv in ivs]}


@R("GET", "/api/student/plans/{id:int}", roles=("student",))
def student_plan(req):
    return iv_out(req.db, own_plan(req, req.params["id"]), for_student=True)


@R("POST", "/api/student/plans/{id:int}/steps", roles=("student",))
def student_plan_step(req):
    c = req.db
    iv = own_plan(req, req.params["id"])
    if iv["status"] != "open":
        raise HTTPError(409, "Plan artıq tamamlanıb")
    b = req.json()
    plan = J(iv["plan"], {}) or {}
    try:
        step = plan["steps"][int(b.get("index"))]
    except (KeyError, IndexError, TypeError, ValueError):
        raise HTTPError(400, "Addım tapılmadı")
    done = bool(b.get("done", True))
    step.update({"done": done, "done_at": iso(now()) if done else None, "auto": False})
    iv["plan"] = radar.dump(plan)
    c.execute("UPDATE interventions SET plan=?, updated_at=? WHERE id=?", (iv["plan"], iso(now()), iv["id"]))
    audit(c, req.user["id"], "radar_step", "intervention", f"#{iv['id']} · {int(b.get('index'))} · {'done' if done else 'undo'}")
    return iv_out(c, iv, for_student=True)


@R("GET", "/api/demo/storyline", auth=False)
def demo_storyline(req):
    """Ids the 3-minute presenter needs (only the synthetic demo storyline students; no personal data)."""
    from .radar_seed import DEMO_STUDENTS
    c = req.db
    ids = {r["username"]: r["id"] for r in rows(c, f"SELECT id, username FROM users WHERE role='student' AND synthetic=1 AND username IN "
                                                   f"({','.join('?' * len(DEMO_STUDENTS))})", DEMO_STUDENTS)}
    co = row(c, "SELECT id FROM courses WHERE code='ELM-2105'")
    return {"students": ids, "course_id": co["id"] if co else None}


def badge_count(c, u) -> int | None:
    if u["role"] not in ("teacher", "office", "leader"):
        return None
    ids = [r["id"] for r in rows(c, "SELECT id FROM courses WHERE teacher_id=?", (u["id"],))] if u["role"] == "teacher" else None
    if u["role"] == "teacher" and not ids:
        return 0
    return radar.analysis(c, ids).counts()["high"]


def leader_insight(c):
    an = radar.analysis(c)
    k, im = an.counts(), radar.impact(c, an)
    text = E("Zəka Radar: {high} tələbə yüksək risk, {watch} tələbə diqqət siyahısındadır. Dəstək planı alan {m} tələbədən {k}-nin riski azalıb.",
             high=k["high"], watch=k["watch"], m=im["measured"], k=im["improved"])
    return {"level": "warn" if k["high"] else "good", "text": text, "link": "/radar"}
