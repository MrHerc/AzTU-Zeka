"""Demo storylines for Zəka Radar (synthetic data, generated relative to "now").

The random cohort already produces a realistic spread of risk. These storylines make the demo explainable: a few named
students in ELM-2105 (the demo teacher's course) whose attendance, grades, quiz attempts and tutor activity tell a clear
story, plus two support plans sent earlier in the semester so the impact loop (risk before → risk now) is visible.

  Murad Hüseynov   high   stopped attending (last 4 lessons + 2 other courses), results falling, keeps asking about Kirchhoff's law
  Elnur Səfərov    watch  attends every lesson but fails tests — concept gaps in AC circuits
  Nərmin Abbasova  watch  disengaged: active in the tutor early in the term, silent for weeks, no test attempts
  Fidan Musayeva   open plan sent ~2 weeks ago: 3 of 4 steps completed from real activity, risk falling
  Kamran Babayev   completed plan: back to normal
  Lalə Kərimova    4 absences, all excused by a medical certificate — never counted against her

Tutor answers are composed by the real offline engine, so a presenter who logs in as one of these students sees a genuine
chat history. Everything here is synthetic and labelled as such in the UI.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, time, timedelta

from . import engine, radar, store, tutor
from .i18n import S, T3
from .store import iso, notify, row, rows

STORY = {
    "murad": ("Murad", "Hüseynov", "Elşən oğlu", "#0891b2"),
    "elnur": ("Elnur", "Səfərov", "Rauf oğlu", "#7c3aed"),
    "nermin": ("Nərmin", "Abbasova", "Kamal qızı", "#db2777"),
    "fidan": ("Fidan", "Musayeva", "Vüqar qızı", "#0e9f6e"),
    "kamran": ("Kamran", "Babayev", "Anar oğlu", "#d97706"),
    "lale": ("Lalə", "Kərimova", "Ramil qızı", "#2b5aa8"),
}
DEMO_STUDENTS = tuple(STORY)


def _at(day: str, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(datetime.fromisoformat(day).date(), time(hh, mm))


class Ctx:
    def __init__(self, c, t0):
        self.c, self.t0, self.rng = c, t0, random.Random(2026)
        self.course = {co["code"]: co for co in rows(c, "SELECT * FROM courses")}
        self.group = row(c, "SELECT id FROM study_groups WHERE name='İT-25-1'")["id"]

    def lessons(self, code):
        return rows(self.c, "SELECT * FROM lessons WHERE course_id=? ORDER BY day, start", (self.course[code]["id"],))

    def q(self, code, topic, qtype):
        return row(self.c, "SELECT * FROM questions WHERE course_id=? AND topic=? AND qtype=? AND origin='manual' ORDER BY id",
                   (self.course[code]["id"], topic, qtype))

    def quiz(self, title):
        return row(self.c, "SELECT * FROM quizzes WHERE title=?", (title,))


def _claim(ctx: Ctx, uid: int, key: str):
    first, last, patronymic, color = STORY[key]
    name = f"{first} {last}"
    for other in rows(ctx.c, "SELECT id, full_name FROM users WHERE full_name=? AND id<>?", (name, uid)):   # keep names unique
        ctx.c.execute("UPDATE users SET full_name=? WHERE id=?", (other["full_name"].split(" ")[0] + " Əhmədov" +
                                                                  ("a" if other["full_name"].endswith("a") else ""), other["id"]))
    ctx.c.execute("UPDATE users SET username=?, full_name=?, patronymic=?, color=?, group_id=? WHERE id=?",
                  (key, name, patronymic, color, ctx.group, uid))


def _attendance(ctx: Ctx, uid: int, code: str, absent=(), excused=(), late=()):
    for i, les in enumerate(ctx.lessons(code)):
        st = "absent" if i in absent else "excused" if i in excused else "late" if i in late else "present"
        ctx.c.execute("UPDATE attendance SET status=? WHERE lesson_id=? AND user_id=?", (st, les["id"], uid))


def _grades(ctx: Ctx, uid: int, code: str, sw: float, lab: float):
    cid = ctx.course[code]["id"]
    ctx.c.execute("UPDATE grades SET score=? WHERE user_id=? AND course_id=? AND component='Sərbəst iş 1'", (sw, uid, cid))
    ctx.c.execute("UPDATE grades SET score=? WHERE user_id=? AND course_id=? AND component='Laboratoriya / məşğələ'", (lab, uid, cid))


def _clear(ctx: Ctx, uid: int, code: str):
    cid = ctx.course[code]["id"]
    ctx.c.execute("DELETE FROM attempts WHERE user_id=? AND quiz_id IN (SELECT id FROM quizzes WHERE course_id=?)", (uid, cid))
    ctx.c.execute("DELETE FROM messages WHERE user_id=? AND course_id=? AND channel='tutor'", (uid, cid))


def _attempt(ctx: Ctx, uid: int, title: str, pattern: list[bool], when: datetime):
    qz = ctx.quiz(title)
    qids = json.loads(qz["question_ids"])
    details = []
    for qid, ok in zip(qids, pattern):
        q = store.row(ctx.c, "SELECT topic FROM questions WHERE id=?", (qid,))
        details.append({"qid": qid, "correct": ok, "topic": q["topic"]})
    ctx.c.execute("INSERT INTO attempts(quiz_id,user_id,answers,details,score,max_score,started_at,finished_at,synthetic) VALUES(?,?,?,?,?,?,?,?,1)",
                  (qz["id"], uid, "{}", json.dumps(details, ensure_ascii=False), sum(pattern), len(qids), iso(when - timedelta(minutes=9)), iso(when)))


def _msg(ctx: Ctx, uid, cid, role, content, cites, meta, when):
    ctx.c.execute("INSERT INTO messages(user_id,course_id,channel,role,content,cites,meta,created_at,synthetic) VALUES(?,?,?,?,?,?,?,?,1)",
                  (uid, cid, "tutor", role, content, json.dumps(cites or []), json.dumps(meta or {}, ensure_ascii=False), iso(when)))


def _ask(ctx: Ctx, uid: int, code: str, question: str, mode: str, when: datetime):
    """A real tutor turn: the offline engine composes the grounded answer exactly as it would live."""
    co = ctx.course[code]
    hits = engine.INDEX["chunks"].search(question, k=4, where=lambda m: m["course_id"] == co["id"])
    r = tutor.compose_tutor(mode, question, hits, [], co, "az")
    _msg(ctx, uid, co["id"], "user", question, [], {"mode": mode, "pii": []}, when)
    _msg(ctx, uid, co["id"], "assistant", r["text"], r["cites"], r["meta"], when + timedelta(seconds=5))


def _practice(ctx: Ctx, uid: int, code: str, q: dict, given: str, ok: bool, when: datetime):
    cid = ctx.course[code]["id"]
    q = dict(q)
    q["options"], q["answer"] = json.loads(q["options"] or "[]"), json.loads(q["answer"])
    s = lambda text, **k: S(text, "az", **k)  # noqa: E731
    _msg(ctx, uid, cid, "user", q["topic"], [], {"mode": "practice", "pii": []}, when)
    _msg(ctx, uid, cid, "assistant", s("Biliyinizi yoxlayaq.") + "\n\n" + tutor.format_practice(q, "az"), [],
         {"mode": "practice", "practice_qid": q["id"], "topic": q["topic"]}, when + timedelta(seconds=4))
    _msg(ctx, uid, cid, "user", given, [], {"mode": "practice", "pii": []}, when + timedelta(minutes=2))
    cites = [q["chunk_id"]] if q["chunk_id"] else []
    if ok:
        text = s("**Düzdür!** {explanation}{ref}\n\nNövbəti suala keçmək üçün **Davam** yazın.", explanation=q["explanation"], ref=" [1]" if cites else "")
    else:
        text = s("Bu dəfə alınmadı. Sizin cavabınız: {given}. Düzgün cavab: **{answer}**.\n\n{explanation}{ref}\n\n"
                 "Mövzunu **İzah** rejimində təkrarlaya və ya **Davam** yazıb yeni sual ala bilərsiniz.",
                 given=given, answer=engine.answer_display(q), explanation=q["explanation"], ref=" [1]" if cites else "")
    _msg(ctx, uid, cid, "assistant", text, cites, {"mode": "practice", "practice_qid": q["id"], "graded": True, "correct": ok, "topic": q["topic"]},
         when + timedelta(minutes=2, seconds=4))


def _day(lessons, i):
    return lessons[max(0, min(len(lessons) - 1, i))]["day"]


def _plan(ctx: Ctx, uid: int, code: str, teacher: int, created: datetime, status: str, closed: datetime | None = None, note: str = ""):
    """Send a plan 'in the past': diagnosis as of that day, then let real activity since then tick the steps."""
    co = ctx.course[code]
    frame = radar.Frame(ctx.c, [co["id"]])
    frame.now = created
    prof = radar.profile(frame, uid, co["id"], created)
    plan = radar.build_plan(ctx.c, prof, co, "plan", note, when=created)
    iv = {"student_id": uid, "course_id": co["id"], "created_at": iso(created)}
    radar.auto_progress(ctx.c, iv, plan)
    if status == "completed":
        for st_ in plan["steps"]:
            st_.setdefault("done_at", iso(closed))
            st_["done"] = True
    drivers = [{"key": d["key"], "points": d["points"]} for d in prof["drivers"]]
    iid = ctx.c.execute("INSERT INTO interventions(student_id,course_id,created_by,kind,status,plan,risk_before,level_before,drivers,note,created_at,"
                        "updated_at,due_at,closed_at,synthetic) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
                        (uid, co["id"], teacher, "plan", status, radar.dump(plan), prof["score"], prof["level"], json.dumps(drivers), note,
                         iso(created), iso(closed or created), plan["due_at"], iso(closed) if closed else None)).lastrowid
    notify(ctx.c, uid, "plan", {"az": "Sizin üçün fərdi dəstək planı hazırlanıb", "en": "A personal support plan has been prepared for you",
                                "ru": "Для вас подготовлен индивидуальный план поддержки"},
           T3("{course} · {n} addım", course=co["name"], n=len(plan["steps"])), f"/student/plan/{iid}", created, read=True)
    return iid


def _tail(ctx: Ctx, exclude: set):
    """A real cohort has a heavier tail than the uniform generator: a few unnamed students who stopped attending and fail."""
    pool = [r["id"] for r in rows(ctx.c, "SELECT id FROM users WHERE role='student' AND synthetic=1 ORDER BY id") if r["id"] not in exclude]
    for code, k in (("ELM-2105", 1), ("KOMP-1102", 2), ("RİY-1101", 1), ("FİZ-1103", 1)):
        les = ctx.lessons(code)
        for uid in ctx.rng.sample(pool, k):
            pool.remove(uid)
            nl = len(les)
            _attendance(ctx, uid, code, absent={ctx.rng.randint(2, nl // 2), nl - 4, nl - 3, nl - 2, nl - 1})
            _grades(ctx, uid, code, round(ctx.rng.uniform(1.8, 2.4), 1), round(ctx.rng.uniform(3.8, 4.8), 1))
            qz = row(ctx.c, "SELECT title, question_ids FROM quizzes WHERE course_id=? AND kind='practice' ORDER BY id", (ctx.course[code]["id"],))
            ctx.c.execute("DELETE FROM attempts WHERE user_id=? AND quiz_id IN (SELECT id FROM quizzes WHERE course_id=?)", (uid, ctx.course[code]["id"]))
            k_q = len(json.loads(qz["question_ids"]))
            _attempt(ctx, uid, qz["title"], [i == 0 for i in range(k_q)], ctx.t0 - timedelta(days=ctx.rng.randint(3, 9), hours=ctx.rng.randint(1, 6)))


def seed(c, t0):
    store.build_indexes(c)            # questions + chunks of this seed (plans cite them)
    ctx = Ctx(c, t0)
    elm, fiz, komp = "ELM-2105", "FİZ-1103", "KOMP-1102"
    L = ctx.lessons(elm)
    n = len(L)
    if n < 8:                          # first days of a semester: the cohort is too young for storylines
        radar.snapshot_history(c)
        return
    synth = [r["id"] for r in rows(c, "SELECT id FROM users WHERE role='student' AND synthetic=1 ORDER BY id")]
    picks = dict(zip(DEMO_STUDENTS, (synth[4], synth[11], synth[18], synth[27], synth[35], synth[44])))
    for key, uid in picks.items():
        _claim(ctx, uid, key)
        _clear(ctx, uid, elm)
    rauf = row(c, "SELECT id FROM users WHERE username='rauf'")["id"]
    q_kcl_num, q_kcl_mcq = ctx.q(elm, "Kirxhofun birinci qanunu", "numeric"), ctx.q(elm, "Kirxhofun birinci qanunu", "mcq")
    q_par = ctx.q(elm, "Paralel birləşmə", "numeric")
    q_ohm_num, q_ohm_mcq = ctx.q(elm, "Om qanunu", "numeric"), ctx.q(elm, "Om qanunu", "mcq")
    q_rms = ctx.q(elm, "Effektiv qiymət", "numeric")
    early, mid = max(1, round(0.12 * n)), round(0.45 * n)

    # ---- Murad: high. Stopped coming ~10 days ago (here and in two other courses), results falling, stuck on Kirchhoff.
    m = picks["murad"]
    _attendance(ctx, m, elm, absent={early + 3, n - 4, n - 3, n - 2, n - 1}, late={early + 6})
    fl = ctx.lessons(fiz)
    _attendance(ctx, m, fiz, absent={len(fl) - 3, len(fl) - 2, len(fl) - 1})
    kl = ctx.lessons(komp)
    _attendance(ctx, m, komp, absent={len(kl) - 2, len(kl) - 1})
    _grades(ctx, m, elm, 2.2, 4.5)
    _attempt(ctx, m, "Məşq: Om qanunu və güc", [True, True, False], _at(_day(L, mid - 2), 19, 40))
    _attempt(ctx, m, "Məşq: Sinusoidal cərəyan", [False, False, True, False], t0 - timedelta(days=4, hours=3))
    _ask(ctx, m, elm, "Om qanunu nədir?", "explain", _at(_day(L, early), 20, 15))
    _ask(ctx, m, elm, "Elektrik gücü necə hesablanır?", "explain", _at(_day(L, early + 1), 21, 5))
    _ask(ctx, m, elm, "Kirxhofun birinci qanunu nədir?", "explain", t0 - timedelta(days=20, hours=2))
    _ask(ctx, m, elm, "Düyündə cərəyanların cəmi niyə sıfıra bərabərdir?", "socratic", t0 - timedelta(days=17, hours=4))
    _practice(ctx, m, elm, q_kcl_num, "14", False, t0 - timedelta(days=16, hours=5))
    _ask(ctx, m, elm, "Paralel birləşmədə ekvivalent müqavimət necə tapılır?", "explain", t0 - timedelta(days=12, hours=3))
    _practice(ctx, m, elm, q_par, "9", False, t0 - timedelta(days=12, hours=2))
    _ask(ctx, m, elm, "Kirxhofun birinci qanununu misalla izah edin", "explain", t0 - timedelta(days=9, hours=6))
    _practice(ctx, m, elm, q_kcl_num, "8", False, t0 - timedelta(days=9, hours=5))
    _ask(ctx, m, elm, "Düyünə daxil olan və çıxan cərəyanları necə ayırım?", "socratic", t0 - timedelta(days=5, hours=2))
    _ask(ctx, m, elm, "Effektiv qiymət nədir?", "explain", t0 - timedelta(days=4, hours=4))

    # ---- Elnur: watch. Attends everything, asks a lot, still fails the tests (AC circuits).
    e = picks["elnur"]
    _attendance(ctx, e, elm, late={mid})
    _grades(ctx, e, elm, 2.6, 5.4)
    _attempt(ctx, e, "Məşq: Om qanunu və güc", [False, False, True], t0 - timedelta(days=16, hours=1))
    _attempt(ctx, e, "Məşq: Sinusoidal cərəyan", [False, False, True, False], t0 - timedelta(days=3, hours=2))
    for d, qtext, mode in [(13, "Zaman sabiti nəyi göstərir?", "explain"), (11, "RC dövrəsinin zaman sabiti necə hesablanır?", "socratic"),
                           (8, "Kondensatorun dolması necə baş verir?", "explain"), (6, "Effektiv qiymət nədir?", "explain"),
                           (5, "Zaman sabiti artanda nə dəyişir?", "socratic"), (2, "Effektiv qiymətlə amplituda arasında əlaqə nədir?", "socratic")]:
        _ask(ctx, e, elm, qtext, mode, t0 - timedelta(days=d, hours=ctx.rng.randint(1, 5)))
    _practice(ctx, e, elm, q_rms, "220", False, t0 - timedelta(days=2, hours=1))

    # ---- Nərmin: watch. Engaged at the start, silent for weeks, no test attempts, the last two lessons missed.
    nm = picks["nermin"]
    _attendance(ctx, nm, elm, absent={n - 2, n - 1})
    _grades(ctx, nm, elm, 2.9, 6.0)
    for i, (qtext, mode) in enumerate([("Om qanunu nədir?", "explain"), ("Müqavimət nədən asılıdır?", "socratic"),
                                       ("Güc hansı vahidlə ölçülür?", "explain"), ("Tipik səhvlər hansılardır?", "explain")]):
        _ask(ctx, nm, elm, qtext, mode, _at(_day(L, early + i), 18, 30))

    # ---- Fidan: plan sent mid-semester after 3 missed lessons and a failed test; since then — back in class, practising.
    f = picks["fidan"]
    _attendance(ctx, f, elm, absent={mid - 3, mid - 2, mid - 1})
    _grades(ctx, f, elm, 3.6, 7.4)
    _attempt(ctx, f, "Məşq: Om qanunu və güc", [False, False, True], _at(_day(L, mid - 4), 18, 10))
    _ask(ctx, f, elm, "Om qanunu nədir?", "socratic", _at(_day(L, mid - 4), 19, 0))
    _ask(ctx, f, elm, "Cərəyan şiddəti necə tapılır?", "socratic", _at(_day(L, mid - 3), 20, 0))
    f_plan = _at(_day(L, mid - 1), 16, 20)
    _ask(ctx, f, elm, "Om qanunu mövzusunu izah et", "explain", f_plan + timedelta(days=1, hours=3))
    _practice(ctx, f, elm, q_ohm_num, "3", True, f_plan + timedelta(days=1, hours=4))
    _practice(ctx, f, elm, q_ohm_mcq, "C", True, f_plan + timedelta(days=2, hours=2))
    _ask(ctx, f, elm, "Effektiv qiymət nədir?", "explain", t0 - timedelta(days=5, hours=2))
    _attempt(ctx, f, "Məşq: Sinusoidal cərəyan", [True, True, False, True], t0 - timedelta(days=2, hours=4))

    # ---- Kamran: plan early in the semester, completed; fully recovered.
    k = picks["kamran"]
    _attendance(ctx, k, elm, absent={early, early + 1, early + 2})
    _grades(ctx, k, elm, 4.1, 8.3)
    _attempt(ctx, k, "Məşq: Om qanunu və güc", [False, True, False], _at(_day(L, early + 1), 21, 0))
    k_plan = _at(_day(L, early + 2), 15, 40)
    _ask(ctx, k, elm, "Om qanunu mövzusunu izah et", "explain", k_plan + timedelta(days=1, hours=2))
    _practice(ctx, k, elm, q_ohm_num, "3", True, k_plan + timedelta(days=1, hours=3))
    _ask(ctx, k, elm, "Kirxhofun birinci qanunu nədir?", "explain", t0 - timedelta(days=10, hours=3))
    _attempt(ctx, k, "Məşq: Sinusoidal cərəyan", [True, True, True, True], t0 - timedelta(days=5, hours=1))

    # ---- Lalə: ill for a week, medical certificate accepted — four excused absences that never count as risk.
    la = picks["lale"]
    _attendance(ctx, la, elm, excused={n - 7, n - 6, n - 5, n - 4})
    _grades(ctx, la, elm, 4.4, 8.6)
    _attempt(ctx, la, "Məşq: Om qanunu və güc", [True, True, True], t0 - timedelta(days=11))
    _ask(ctx, la, elm, "Reaktiv müqavimət nədir?", "explain", t0 - timedelta(days=2, hours=3))

    _tail(ctx, set(picks.values()))
    _ = q_kcl_mcq  # left unanswered on purpose: the live demo's practice step asks it (answer B — charge conservation)
    _plan(ctx, f, elm, rauf, f_plan, "open", note="Qayıblardan sonra Om qanunu mövzusunu bərpa etmək.")
    _plan(ctx, k, elm, rauf, k_plan, "completed", closed=k_plan + timedelta(days=9), note="Kollokviuma hazırlıq.")
    notify(c, rauf, "radar", {"az": "Zəka Radar: diqqət tələb edən tələbələr", "en": "Zəka Radar: students who need attention",
                              "ru": "Zəka Radar: студенты, требующие внимания"},
           {"az": "Elektrik dövrələrinin nəzəriyyəsi üzrə yeni xəbərdarlıqlar var", "en": "New early warnings in Theory of Electric Circuits",
            "ru": "Новые предупреждения по курсу «Теория электрических цепей»"}, "/radar", t0 - timedelta(hours=3))
    radar.snapshot_history(c)
