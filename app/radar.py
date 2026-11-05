"""Zəka Radar — explainable early-warning engine (erkən xəbərdarlıq).

Risk is computed per student × course from data the platform already holds — attendance, current grades, quiz attempts,
AI-tutor questions and practice answers — and every score ships with its drivers and the evidence behind them, so a
teacher or the dean's office sees *why* a student is flagged, not just a number. The diagnosis is turned into a support
plan grounded in the course material (cited passages, practice questions, a tutor session, a consultation slot). Plan
steps complete themselves from real activity: an explanation requested in the tutor, a correct practice answer, lessons
attended after the plan was sent.

Model (0–100 points): attendance 30 · assessment 30 · concept gaps 25 · engagement 15.
Levels: ``high`` ≥ 50, ``watch`` ≥ 30, otherwise ``ok``. Signals built on little data are scaled down by a confidence factor,
so the first weeks of a semester (two lessons, one absence) never raise a false alarm. Excused absences never count.
Privacy: the model reads topics and counts of tutor questions, never their text; students never see a risk score.

All user-facing phrasing goes through ``T3`` (returned as {az, en, ru}); course topics and material quotes stay in the
language of the material.
"""
from __future__ import annotations

import json
import re
import statistics
import threading
import urllib.parse
from datetime import datetime, timedelta

from . import engine
from .i18n import S_, T3, num3
from .store import J, iso, now, row, rows, setting

WEIGHTS = {"attendance": 30, "assessment": 30, "concept": 25, "engagement": 15}
LEVELS = (("high", 50), ("watch", 30), ("ok", 0))
LEVEL_RANK = {"ok": 0, "watch": 1, "high": 2}
HISTORY_WEEKS = 8
GAP_MIN = 2.0          # a topic counts as a gap from two wrong answers, or one wrong answer and two questions about it


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def level_of(score: float) -> str:
    for name, floor in LEVELS:
        if score >= floor:
            return name
    return "ok"


def driver_label(key):
    if not key:
        return None
    return {"attendance": T3("Davamiyyət"), "assessment": T3("Qiymətləndirmə"), "concept": T3("Anlayış boşluğu"),
            "engagement": T3("Aktivlik")}[key]


def level_label(level: str) -> dict:
    return {"high": T3("Yüksək risk"), "watch": T3("Diqqət"), "ok": T3("Normal")}[level]


def pct(x: float, digits: int = 0) -> dict:
    return num3(100 * x, digits)


def same_topic(a: str, b: str) -> bool:
    fa, fb = engine.fold(a or "").strip(), engine.fold(b or "").strip()
    return bool(fa and fb) and (fa == fb or fa in fb or fb in fa)


def _dt(s):
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- data frame
class Frame:
    """Everything the model needs, loaded once and grouped by (student, course). Signals filter it by ``as_of``."""

    def __init__(self, c, course_ids=None):
        self.now = now()
        start = setting(c, "semester_start")
        self.semester_start = datetime.fromisoformat(start) if start else self.now - timedelta(days=56)
        self.courses = {co["id"]: co for co in rows(c, "SELECT * FROM courses ORDER BY id") if not course_ids or co["id"] in course_ids}
        self.students = {u["id"]: u for u in rows(c, "SELECT u.id, u.full_name, u.color, u.username, g.name grp FROM users u "
                                                      "LEFT JOIN study_groups g ON g.id=u.group_id WHERE u.role='student' ORDER BY u.id")}
        self.enrolled: dict[int, list[int]] = {cid: [] for cid in self.courses}
        for e in rows(c, "SELECT user_id, course_id FROM enrollments ORDER BY user_id"):
            if e["course_id"] in self.enrolled and e["user_id"] in self.students:
                self.enrolled[e["course_id"]].append(e["user_id"])
        lessons = {x["id"]: x for x in rows(c, "SELECT id, course_id, day, start, topic FROM lessons")}
        self.att: dict[tuple, list] = {}
        for a in rows(c, "SELECT lesson_id, user_id, status FROM attendance"):
            les = lessons.get(a["lesson_id"])
            if les and les["course_id"] in self.courses:
                self.att.setdefault((a["user_id"], les["course_id"]), []).append((les["day"], les["start"], a["status"], les["id"], les["topic"]))
        for v in self.att.values():
            v.sort()
        self.grades: dict[tuple, list] = {}
        for g in rows(c, "SELECT user_id, course_id, component, score, max, updated_at FROM grades"):
            if g["course_id"] in self.courses:
                self.grades.setdefault((g["user_id"], g["course_id"]), []).append((_dt(g["updated_at"]), g["score"], g["max"], g["component"]))
        self.qtopic = {q["id"]: q["topic"] for q in rows(c, "SELECT id, topic FROM questions")}
        self.attempts: dict[tuple, list] = {}
        for a in rows(c, "SELECT a.user_id, a.finished_at, a.score, a.max_score, a.details, q.course_id, q.title FROM attempts a "
                         "JOIN quizzes q ON q.id=a.quiz_id WHERE a.finished_at IS NOT NULL"):
            if a["course_id"] in self.courses and a["max_score"]:
                self.attempts.setdefault((a["user_id"], a["course_id"]), []).append(
                    (_dt(a["finished_at"]), a["score"] / a["max_score"], J(a["details"], []) or [], a["title"]))
        for v in self.attempts.values():
            v.sort(key=lambda x: x[0] or self.now)
        self.msgs: dict[tuple, list] = {}
        for m in rows(c, "SELECT user_id, course_id, role, meta, created_at FROM messages WHERE channel='tutor' ORDER BY id"):
            if m["course_id"] in self.courses:
                self.msgs.setdefault((m["user_id"], m["course_id"]), []).append((_dt(m["created_at"]), m["role"], J(m["meta"], {}) or {}))
        self._cohort: dict = {}

    def cohort(self, cid: int, as_of: datetime) -> dict:
        """Median tutor activity and the share of students who attempted a quiz — the yardstick for 'disengaged'."""
        key = (cid, as_of)
        if key not in self._cohort:
            since = as_of - timedelta(days=14)
            asks, tried = [], 0
            studs = self.enrolled.get(cid, [])
            for sid in studs:
                asks.append(sum(1 for ts, role, _m in self.msgs.get((sid, cid), []) if role == "user" and ts and since < ts <= as_of))
                tried += any(ts and ts <= as_of for ts, _p, _d, _t in self.attempts.get((sid, cid), []))
            self._cohort[key] = {"median_asks": statistics.median(asks) if asks else 0, "attempt_share": tried / len(studs) if studs else 0}
        return self._cohort[key]

    def weeks_available(self) -> int:
        return max(2, min(HISTORY_WEEKS, (self.now - self.semester_start).days // 7 + 1))


# ---------------------------------------------------------------- signals (each returns value 0..1, confidence, evidence)
def _attendance(frame: Frame, sid: int, cid: int, as_of: datetime) -> dict:
    day = as_of.date().isoformat()
    att = [a for a in frame.att.get((sid, cid), []) if a[0] <= day]
    total = len(att)
    absent = sum(1 for a in att if a[2] == "absent")
    excused = sum(1 for a in att if a[2] == "excused")
    late = sum(1 for a in att if a[2] == "late")
    streak = 0
    for a in reversed(att):
        if a[2] == "absent":
            streak += 1
        elif a[2] != "excused":
            break
    since = (as_of - timedelta(days=14)).date().isoformat()
    recent = sum(1 for a in att if a[2] == "absent" and a[0] > since)
    rate = absent / total if total else 0.0
    conf = clamp(total / 8)
    value = clamp(0.6 * clamp(rate / 0.25) + 0.4 * clamp(streak / 4)) * conf
    ev = []
    if absent:
        ev.append(T3("{absent} üzrsüz qayıb / {total} dərs ({rate}%)", absent=absent, total=total, rate=pct(rate)))
    if streak >= 2:
        ev.append(T3("son {n} dərs ardıcıl qayıb", n=streak))
    elif recent >= 2:
        ev.append(T3("son 2 həftədə {n} qayıb", n=recent))
    if excused:
        ev.append(T3("{n} üzrlü qayıb nəzərə alınmayıb", n=excused))
    missed = list(dict.fromkeys(a[4] for a in att if a[2] == "absent" and a[4]))[-3:]
    return {"key": "attendance", "value": round(value, 3), "confidence": round(conf, 2), "evidence": ev,
            "stats": {"total": total, "absent": absent, "excused": excused, "late": late, "streak": streak, "recent": recent,
                      "rate": round(100 * (total - absent - excused) / total) if total else None, "missed_topics": missed}}


def _assessment(frame: Frame, sid: int, cid: int, as_of: datetime) -> dict:
    ats = [a for a in frame.attempts.get((sid, cid), []) if a[0] and a[0] <= as_of]
    gr = [g for g in frame.grades.get((sid, cid), []) if g[0] and g[0] <= as_of]
    vq = vg = None
    ev = []
    stats = {"attempts": len(ats), "avg": None, "first": None, "last": None, "trend": None, "grade_pct": None, "series": []}
    if ats:
        pcts = [a[1] for a in ats]
        avg, first, last = sum(pcts) / len(pcts), pcts[0], pcts[-1]
        v = clamp((0.60 - avg) / 0.35)
        trend = None
        if len(pcts) >= 2 and last < first - 0.15:
            v += 0.2
            trend = "down"
        elif len(pcts) >= 2 and last > first + 0.15:
            trend = "up"
        if last < 0.4:
            v += 0.1
        vq = clamp(v) * min(1.0, len(pcts) / 2)          # one practice test is weak evidence
        stats.update({"avg": round(100 * avg), "first": round(100 * first), "last": round(100 * last), "trend": trend,
                      "series": [{"title": a[3], "percent": round(100 * a[1]), "at": iso(a[0])} for a in ats[-6:]]})
        ev.append(T3("Test nəticələri: orta {avg}% ({n} cəhd), sonuncu {last}%", avg=pct(avg), n=len(pcts), last=pct(last)))
        if trend == "down":
            ev.append(T3("nəticə {a}% → {b}% azalıb", a=pct(first), b=pct(last)))
    if gr:
        got, mx = sum(g[1] for g in gr), sum(g[2] for g in gr)
        if mx:
            gp = got / mx
            vg = clamp((0.65 - gp) / 0.30)
            stats["grade_pct"] = round(100 * gp)
            ev.append(T3("Cari ballar: {score} / {max} ({pct}%)", score=num3(got, 1), max=num3(mx, 0), pct=pct(gp)))
    if vq is not None and vg is not None:
        value, conf = 0.55 * vq + 0.45 * vg + (0.15 if min(vq, vg) >= 0.5 else 0.0), 1.0
    elif vq is not None or vg is not None:
        value, conf = 0.75 * (vq if vq is not None else vg), 0.75
    else:
        value, conf = 0.0, 0.0
    return {"key": "assessment", "value": round(clamp(value), 3), "confidence": conf, "evidence": ev, "stats": stats}


def _concept(frame: Frame, sid: int, cid: int, as_of: datetime) -> dict:
    """Topics the student keeps asking the tutor about and keeps getting wrong (practice + quizzes), last 4 weeks."""
    since = as_of - timedelta(days=28)
    asks: dict[str, int] = {}
    wrong: dict[str, int] = {}
    for ts, role, meta in frame.msgs.get((sid, cid), []):
        if role != "assistant" or not ts or not (since < ts <= as_of):
            continue
        topic = meta.get("topic")
        if not topic or meta.get("no_source"):
            continue
        if meta.get("mode") == "practice":
            if meta.get("graded") and meta.get("correct") is False:
                wrong[topic] = wrong.get(topic, 0) + 1
        else:
            asks[topic] = asks.get(topic, 0) + 1
    for ts, _p, details, _title in frame.attempts.get((sid, cid), []):
        if not ts or not (since < ts <= as_of):
            continue
        for d in details:
            if d.get("correct"):
                continue
            topic = d.get("topic") or frame.qtopic.get(d.get("qid"))
            if topic:
                wrong[topic] = wrong.get(topic, 0) + 1
    gaps = [{"topic": tp, "asks": asks.get(tp, 0), "wrong": wrong.get(tp, 0), "score": round(0.6 * asks.get(tp, 0) + 1.2 * wrong.get(tp, 0), 2)}
            for tp in set(asks) | set(wrong)]
    gaps.sort(key=lambda g: (-g["score"], g["topic"]))
    top = gaps[0]["score"] if gaps else 0.0
    value = clamp(top / 6) * 0.8 + (0.2 if sum(1 for g in gaps if g["score"] >= 2.4) >= 2 else 0.0)
    ev = [T3("«{topic}»: {asks} tutor sualı, {wrong} səhv cavab", topic=g["topic"], asks=g["asks"], wrong=g["wrong"])
          for g in gaps[:2] if g["score"] >= GAP_MIN]
    return {"key": "concept", "value": round(clamp(value), 3), "confidence": 1.0 if gaps else 0.0, "evidence": ev, "gaps": gaps[:5]}


def _engagement(frame: Frame, sid: int, cid: int, as_of: datetime) -> dict:
    since = as_of - timedelta(days=14)
    msgs = [m for m in frame.msgs.get((sid, cid), []) if m[1] == "user" and m[0] and m[0] <= as_of]
    n14 = sum(1 for m in msgs if m[0] > since)
    before = len(msgs) - n14
    ats = [a for a in frame.attempts.get((sid, cid), []) if a[0] and a[0] <= as_of]
    co = frame.cohort(cid, as_of)
    value, ev = 0.0, []
    if n14 == 0 and (co["median_asks"] >= 1 or before >= 3):
        value += 0.6
        ev.append(T3("Son 14 gündə tutora sual yoxdur (qrup mediyanı: {m})", m=num3(co["median_asks"], 0)))
    if not ats and co["attempt_share"] >= 0.5:
        value += 0.4
        ev.append(T3("Heç bir test cəhdi yoxdur (kursun {p}%-i cəhd edib)", p=pct(co["attempt_share"])))
    return {"key": "engagement", "value": round(clamp(value), 3), "confidence": 1.0, "evidence": ev,
            "stats": {"asks_14d": n14, "asks_before": before, "median_asks": co["median_asks"], "attempts": len(ats)}}


# What the teacher is offered, by the strongest *actionable* signal. Kinds: plan | consult | office | nudge.
REC_TEXT = {
    "plan": S_("Fərdi dəstək planı: boşluq olan mövzular üzrə material, məşq və konsultasiya"),
    "consult": S_("Müəllimlə konsultasiya və məşq planı — nəticələr aşağı düşür"),
    "office": S_("Dekanlıqla əlaqə: qayıbların səbəbini dəqiqləşdirin (üzrlü ola bilər) və tələbəni dərsə qaytarın"),
    "nudge": S_("Xatırlatma və tutora dəvət — tələbə platformadan uzaqlaşıb"),
}


def recommend(drivers: list[dict], gaps: list[dict]):
    pts = {d["key"]: d["points"] for d in drivers}
    if drivers[0]["points"] < 4:
        return None
    strong_gaps = [g for g in gaps if g["score"] >= GAP_MIN]
    top = drivers[0]["key"]
    if strong_gaps and (pts["concept"] >= 6 or pts["assessment"] >= 8):
        kind = "plan"
    elif top == "attendance":
        kind = "office"
    elif top == "assessment":
        kind = "consult"
    elif top == "engagement":
        kind = "nudge"
    else:
        kind = "plan"
    return {"kind": kind, "text": T3(REC_TEXT[kind]), "cc_office": pts["attendance"] >= 15}


def profile(frame: Frame, sid: int, cid: int, as_of: datetime | None = None) -> dict:
    as_of = as_of or frame.now
    sig = [_attendance(frame, sid, cid, as_of), _assessment(frame, sid, cid, as_of), _concept(frame, sid, cid, as_of), _engagement(frame, sid, cid, as_of)]
    drivers = [{"key": s["key"], "label": driver_label(s["key"]), "weight": WEIGHTS[s["key"]], "value": s["value"],
                "points": round(WEIGHTS[s["key"]] * s["value"], 1), "confidence": s["confidence"], "evidence": s["evidence"]} for s in sig]
    drivers.sort(key=lambda d: -d["points"])
    score = round(sum(d["points"] for d in drivers), 1)
    level = level_of(score)
    att, ass, con, eng = sig
    if att["stats"]["total"] >= 10 and (ass["stats"]["attempts"] or ass["stats"]["grade_pct"] is not None):
        confidence = "high"
    elif att["stats"]["total"] + ass["stats"]["attempts"] + eng["stats"]["asks_14d"] + eng["stats"]["asks_before"] >= 6:
        confidence = "medium"
    else:
        confidence = "low"
    return {"student_id": sid, "course_id": cid, "score": score, "level": level, "level_label": level_label(level), "drivers": drivers,
            "top_driver": drivers[0]["key"] if drivers[0]["points"] > 0 else None, "gaps": con["gaps"], "confidence": confidence,
            "recommendation": recommend(drivers, con["gaps"]) if level != "ok" else None,
            "stats": {"attendance": att["stats"], "assessment": ass["stats"], "engagement": eng["stats"]}}


def summary_line(p: dict):
    """The one-line 'why' shown in the list: the first piece of evidence of the two strongest drivers."""
    parts = [d["evidence"][0] for d in p["drivers"][:2] if d["points"] >= 4 and d["evidence"]]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return {lg: f"{parts[0][lg]} · {parts[1][lg]}" for lg in ("az", "en", "ru")}


def history(frame: Frame, sid: int, cid: int) -> list[dict]:
    out = []
    for k in range(frame.weeks_available() - 1, -1, -1):
        p = profile(frame, sid, cid, frame.now - timedelta(days=7 * k))
        out.append({"as_of": (frame.now - timedelta(days=7 * k)).date().isoformat(), "score": p["score"], "level": p["level"]})
    return out


# ---------------------------------------------------------------- cohort analysis
class Analysis:
    def __init__(self, frame: Frame, as_of: datetime | None = None):
        self.frame = frame
        as_of = as_of or frame.now
        self.profiles: dict[tuple, dict] = {}
        for cid in frame.courses:
            for sid in frame.enrolled.get(cid, []):
                self.profiles[(sid, cid)] = profile(frame, sid, cid, as_of)
        self.rows = self._rows()

    def _rows(self) -> list[dict]:
        by_student: dict[int, list] = {}
        for (sid, cid), p in self.profiles.items():
            by_student.setdefault(sid, []).append(p)
        out = []
        for sid, ps in by_student.items():
            u = self.frame.students[sid]
            ps.sort(key=lambda p: -p["score"])
            top = ps[0]
            courses = [{"id": p["course_id"], "code": self.frame.courses[p["course_id"]]["code"], "name": self.frame.courses[p["course_id"]]["name"],
                        "color": self.frame.courses[p["course_id"]]["color"], "score": p["score"], "level": p["level"], "top_driver": p["top_driver"]}
                       for p in ps]
            gaps = [{"topic": g["topic"], "course_id": p["course_id"], "code": self.frame.courses[p["course_id"]]["code"],
                     "color": self.frame.courses[p["course_id"]]["color"], "score": g["score"]}
                    for p in ps[:3] if p["level"] != "ok" for g in p["gaps"] if g["score"] >= GAP_MIN]
            gaps.sort(key=lambda g: -g["score"])
            out.append({"id": sid, "name": u["full_name"], "color": u["color"], "group": u["grp"], "score": top["score"], "level": top["level"],
                        "level_label": top["level_label"], "course_id": top["course_id"], "top_driver": top["top_driver"],
                        "top_driver_label": driver_label(top["top_driver"]), "why": summary_line(top) if top["level"] != "ok" else None,
                        "drivers": [{"key": d["key"], "points": d["points"]} for d in top["drivers"]], "confidence": top["confidence"],
                        "recommendation": top["recommendation"], "courses": courses, "at_risk_courses": sum(1 for x in courses if x["level"] != "ok"),
                        "gaps": gaps[:3]})
        out.sort(key=lambda r: (-r["score"], r["name"]))
        return out

    def counts(self) -> dict:
        return counts(self.rows)

    def course_counts(self) -> list[dict]:
        out = []
        for cid, co in self.frame.courses.items():
            levels = [self.profiles[(sid, cid)]["level"] for sid in self.frame.enrolled.get(cid, [])]
            out.append({"id": cid, "code": co["code"], "name": co["name"], "color": co["color"], "students": len(levels),
                        "high": levels.count("high"), "watch": levels.count("watch"), "ok": levels.count("ok")})
        return out

    def cohort_gaps(self, limit: int = 6) -> list[dict]:
        """Topics several at-risk students struggle with — a teaching signal ('re-teach this'), not a student one."""
        agg: dict[tuple, set] = {}
        for (sid, cid), p in self.profiles.items():
            if p["level"] == "ok":
                continue
            for g in p["gaps"]:
                if g["score"] >= GAP_MIN:
                    agg.setdefault((cid, g["topic"]), set()).add(sid)
        out = []
        for (cid, topic), studs in agg.items():
            co = self.frame.courses[cid]
            hit = engine.INDEX["chunks"].search(topic, k=1, where=lambda m, c_=cid: m["course_id"] == c_)
            out.append({"course_id": cid, "code": co["code"], "course": co["name"], "color": co["color"], "topic": topic, "students": len(studs),
                        "chunk_id": hit[0]["id"] if hit else None, "material": hit[0]["material"] if hit else None})
        out.sort(key=lambda g: (-g["students"], g["topic"]))
        return out[:limit]

    def driver_mix(self) -> list[dict]:
        mix = {k: 0 for k in WEIGHTS}
        for r in self.rows:
            if r["level"] != "ok" and r["top_driver"]:
                mix[r["top_driver"]] += 1
        return [{"key": k, "label": driver_label(k), "n": n} for k, n in sorted(mix.items(), key=lambda kv: -kv[1])]


def counts(rows_: list[dict]) -> dict:
    return {"high": sum(1 for r in rows_ if r["level"] == "high"), "watch": sum(1 for r in rows_ if r["level"] == "watch"),
            "ok": sum(1 for r in rows_ if r["level"] == "ok"), "students": len(rows_)}


# Cache keyed on a cheap fingerprint of the inputs: always fresh, recomputed only when the underlying data changed.
_CACHE: dict = {}
_LOCK = threading.Lock()


def fingerprint(c) -> tuple:
    r = row(c, "SELECT (SELECT COUNT(*) FROM messages WHERE channel='tutor') m1, (SELECT COALESCE(MAX(id),0) FROM messages) m2, "
               "(SELECT COUNT(*) FROM attempts WHERE finished_at IS NOT NULL) a, (SELECT COUNT(*) FROM attendance WHERE status='absent') ab, "
               "(SELECT COUNT(*) FROM attendance WHERE status='excused') ex, (SELECT COALESCE(SUM(score),0) FROM grades) g, "
               "(SELECT COUNT(*) FROM enrollments) en, (SELECT COUNT(*) FROM lessons) le")
    return tuple(r.values())


def analysis(c, course_ids=None) -> Analysis:
    key = (tuple(sorted(course_ids)) if course_ids else (), fingerprint(c), now().date())
    with _LOCK:
        hit = _CACHE.get(key)
    if hit:
        return hit
    a = Analysis(Frame(c, course_ids))
    with _LOCK:
        if len(_CACHE) > 24:
            _CACHE.clear()
        _CACHE[key] = a
    return a


def invalidate():
    with _LOCK:
        _CACHE.clear()


# ---------------------------------------------------------------- support plans
def tutor_link(cid: int, topic: str, mode: str) -> str:
    q = topic if mode == "practice" else f"{topic} mövzusunu izah et"
    return f"/student/tutor/{cid}?q={urllib.parse.quote(q)}&mode={mode}"


def next_lesson(c, cid: int, t: datetime):
    tt = rows(c, "SELECT * FROM timetable WHERE course_id=? ORDER BY weekday, start", (cid,))
    for add in range(0, 8):
        d = t.date() + timedelta(days=add)
        for x in tt:
            if x["weekday"] == d.isoweekday() and (add > 0 or x["start"] > t.strftime("%H:%M")):
                return {"date": d.isoformat(), "start": x["end"], "room": x["room"], "kind": x["kind"]}
    return None


def build_plan(c, prof: dict, course: dict, kind: str = "plan", note: str = "", when: datetime | None = None) -> dict:
    """Turn a diagnosis into concrete, cited steps. Topics come from the concept gaps, else from the lessons the student missed."""
    when = when or now()
    cid = course["id"]
    topics = [g["topic"] for g in prof["gaps"] if g["score"] >= 1.0][:2]
    source = "gaps"
    if not topics:
        topics = prof["stats"]["attendance"].get("missed_topics", [])[-2:]
        source = "missed"
    approved = {r["id"] for r in rows(c, "SELECT id FROM questions WHERE course_id=? AND status='approved'", (cid,))}
    steps = []
    if kind in ("plan", "consult"):
        for topic in topics:
            hits = engine.INDEX["chunks"].search(topic, k=2, where=lambda m, c_=cid: m["course_id"] == c_)
            cites = [{"id": h["id"], "material": h["material"], "heading": h["heading"], "snippet": engine.plain(h["text"])[:200]} for h in hits[:2]]
            steps.append({"kind": "read", "topic": topic, "title": T3("Mövzunu təkrarlayın: {topic}", topic=topic),
                          "text": T3("Mühazirənin göstərilən hissəsini oxuyun, sonra tutordan qısa izah istəyin."),
                          "cites": cites, "link": tutor_link(cid, topic, "explain"), "done": False})
            qhits = engine.INDEX["questions"].search(topic, k=4, where=lambda m, c_=cid: m["course_id"] == c_ and m["status"] == "approved")
            qids = [h["id"] for h in qhits if h["id"] in approved][:3]
            steps.append({"kind": "practice", "topic": topic, "title": T3("Məşq: {topic}", topic=topic),
                          "text": T3("Tutorun Məşq rejimində suallara cavab verin — cavab dərhal yoxlanılır və izah olunur."),
                          "question_ids": qids, "link": tutor_link(cid, topic, "practice"), "done": False})
    att = prof["stats"]["attendance"]
    if kind in ("plan", "office") and (att.get("streak", 0) >= 2 or att.get("recent", 0) >= 2):
        steps.append({"kind": "attend", "title": T3("Növbəti dərslərdə iştirak"),
                      "text": T3("Növbəti 2 dərsdə iştirak edin. Üzrlü səbəbiniz olubsa, təsdiqedici sənədi E-xidmətlərdən yükləyin — qayıb üzrlü sayılacaq."),
                      "link": "/student/attendance", "done": False})
    if kind in ("plan", "consult"):
        nxt = next_lesson(c, cid, when)
        steps.append({"kind": "consult", "title": T3("Müəllimlə 15 dəqiqəlik konsultasiya"),
                      "text": T3("{date}, {time} · {room} — dərsdən sonra.", date=nxt["date"][8:10] + "." + nxt["date"][5:7] + "." + nxt["date"][:4],
                                 time=nxt["start"], room=nxt["room"]) if nxt else T3("Vaxt müəllimlə razılaşdırılacaq."),
                      "when": nxt, "link": f"/student/course/{cid}", "done": False})
    if kind == "nudge":
        steps.append({"kind": "tutor", "title": T3("AI tutora qayıdın"), "text": T3("Fənn üzrə istənilən sualı verin — cavablar müəllimin materiallarına əsaslanır."),
                      "link": f"/student/tutor/{cid}", "done": False})
        if prof["stats"]["engagement"]["attempts"] == 0:
            steps.append({"kind": "quiz", "title": T3("Məşq testini həll edin"), "text": T3("Fənn üzrə ilk məşq testini həll edin — nəticə fərdi tövsiyələr üçün istifadə olunur."),
                          "link": "/student/quizzes", "done": False})
    due = when + timedelta(days=14 if kind in ("plan", "consult") else 7)
    titles = {"plan": "Fərdi dəstək planı · {course}", "consult": "Konsultasiya və məşq · {course}", "nudge": "Fənnə qayıdış · {course}",
              "office": "Davamiyyət üzrə dəstək · {course}"}
    return {"kind": kind, "title": T3(titles[kind], course=course["name"]), "topics": topics, "topics_source": source, "steps": steps,
            "due_at": iso(due), "note": (note or "").strip()[:600], "cc_office": bool((prof.get("recommendation") or {}).get("cc_office")) or kind == "office"}


def plan_progress(plan: dict) -> dict:
    steps = plan.get("steps", [])
    done = sum(1 for s in steps if s.get("done"))
    return {"done": done, "total": len(steps), "percent": round(100 * done / len(steps)) if steps else 0}


def auto_progress(c, iv: dict, plan: dict) -> bool:
    """Tick plan steps from real activity since the plan was sent. Returns True when something changed."""
    since = iv["created_at"]
    msgs = rows(c, "SELECT role, meta, created_at FROM messages WHERE user_id=? AND course_id=? AND channel='tutor' AND created_at>=? ORDER BY id",
                (iv["student_id"], iv["course_id"], since))
    metas = [(J(m["meta"], {}) or {}, m["created_at"]) for m in msgs if m["role"] == "assistant"]
    asked = any(m["role"] == "user" for m in msgs)
    att = rows(c, "SELECT a.status FROM attendance a JOIN lessons l ON l.id=a.lesson_id WHERE a.user_id=? AND l.course_id=? "
                  "AND (l.day || 'T' || l.start)>? AND l.day<=? ORDER BY l.day, l.start", (iv["student_id"], iv["course_id"], since[:16], now().date().isoformat()))
    attempts = row(c, "SELECT COUNT(*) n FROM attempts a JOIN quizzes q ON q.id=a.quiz_id WHERE a.user_id=? AND q.course_id=? AND a.finished_at>=?",
                   (iv["student_id"], iv["course_id"], since))["n"]
    changed = False
    for s in plan.get("steps", []):
        if s.get("done"):
            continue
        hit = None
        if s["kind"] == "read":
            hit = next((ts for m, ts in metas if m.get("mode") in ("explain", "socratic") and not m.get("no_source") and same_topic(m.get("topic"), s["topic"])), None)
        elif s["kind"] == "practice":
            hit = next((ts for m, ts in metas if m.get("mode") == "practice" and m.get("graded") and m.get("correct")
                        and (m.get("practice_qid") in s.get("question_ids", []) or same_topic(m.get("topic"), s["topic"]))), None)
        elif s["kind"] == "tutor" and asked:
            hit = next((ts for m, ts in metas), None)
        elif s["kind"] == "attend" and len(att) >= 2 and all(a["status"] in ("present", "late", "excused") for a in att):
            hit = iso(now())
        elif s["kind"] == "quiz" and attempts:
            hit = iso(now())
        if hit:
            s.update({"done": True, "done_at": hit, "auto": True})
            changed = True
    return changed


def impact(c, an: Analysis, course_ids=None) -> dict:
    """Did the plans work? Current risk of every supported student versus their risk when the plan was sent."""
    sql = "SELECT i.*, u.full_name student, co.code, co.name course, co.color FROM interventions i JOIN users u ON u.id=i.student_id JOIN courses co ON co.id=i.course_id"
    args: tuple = ()
    if course_ids:
        sql += f" WHERE i.course_id IN ({','.join('?' * len(course_ids))})"
        args = tuple(course_ids)
    items = []
    for iv in rows(c, sql + " ORDER BY i.id DESC", args):
        if iv["status"] == "cancelled":
            continue
        p = an.profiles.get((iv["student_id"], iv["course_id"]))
        if not p:
            continue
        delta = round(p["score"] - (iv["risk_before"] or 0), 1)
        improved = delta <= -10 or LEVEL_RANK[p["level"]] < LEVEL_RANK.get(iv["level_before"] or "ok", 0)
        plan = J(iv["plan"], {}) or {}
        items.append({"id": iv["id"], "student_id": iv["student_id"], "student": iv["student"], "course_id": iv["course_id"], "code": iv["code"],
                      "course": iv["course"], "color": iv["color"], "kind": iv["kind"], "status": iv["status"], "created_at": iv["created_at"],
                      "risk_before": iv["risk_before"], "level_before": iv["level_before"], "risk_now": p["score"], "level_now": p["level"],
                      "delta": delta, "improved": improved, "progress": plan_progress(plan)})
    aged = [x for x in items if (now() - datetime.fromisoformat(x["created_at"])).days >= 7]
    return {"plans": len(items), "open": sum(1 for x in items if x["status"] == "open"), "completed": sum(1 for x in items if x["status"] == "completed"),
            "measured": len(aged), "improved": sum(1 for x in aged if x["improved"]),
            "avg_delta": round(sum(x["delta"] for x in aged) / len(aged), 1) if aged else None, "items": items[:12]}


# ---------------------------------------------------------------- weekly snapshots (the cohort trend, computed from the data as of each week)
def snapshot_history(c):
    frame = Frame(c)
    c.execute("DELETE FROM risk_snapshots")
    for k in range(frame.weeks_available() - 1, 0, -1):
        as_of = frame.now - timedelta(days=7 * k)
        an = Analysis(frame, as_of)
        agg = an.counts()
        c.execute("INSERT INTO risk_snapshots(week_start,course_id,high,watch,ok,students) VALUES(?,?,?,?,?,?)",
                  (as_of.date().isoformat(), 0, agg["high"], agg["watch"], agg["ok"], agg["students"]))
        for cc in an.course_counts():
            c.execute("INSERT INTO risk_snapshots(week_start,course_id,high,watch,ok,students) VALUES(?,?,?,?,?,?)",
                      (as_of.date().isoformat(), cc["id"], cc["high"], cc["watch"], cc["ok"], cc["students"]))


def trend(c, an: Analysis, course_ids=None) -> list[dict]:
    """Weekly high/watch counts: stored snapshots for past weeks plus the live current week."""
    if course_ids and len(course_ids) == 1:
        cid = course_ids[0]
        past = rows(c, "SELECT week_start, high, watch, ok FROM risk_snapshots WHERE course_id=? ORDER BY week_start", (cid,))
        cur = next(x for x in an.course_counts() if x["id"] == cid)
    else:
        past = rows(c, "SELECT week_start, high, watch, ok FROM risk_snapshots WHERE course_id=0 ORDER BY week_start")
        cur = an.counts()
    return past + [{"week_start": now().date().isoformat(), "high": cur["high"], "watch": cur["watch"], "ok": cur["ok"]}]


def dump(plan: dict) -> str:
    return json.dumps(plan, ensure_ascii=False)


_WS = re.compile(r"\s+")


def clean_note(s) -> str:
    return _WS.sub(" ", str(s or "")).strip()[:600]
