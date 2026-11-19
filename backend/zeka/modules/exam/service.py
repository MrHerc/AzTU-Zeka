"""The exam core (tasks/todo.md, Task 26): exams of a course, the roster drawn when an exam opens, one form and one
attempt per student, answers checked against the server's clock, an automatic submission at the deadline (the
``exam.autosubmit`` job), grading when the exam closes, and every step in the exam's log."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta

from ...core import clock, jobs
from ...core.i18n import E
from ...legacy.store import audit
from . import domain, repo

STAFF = ("admin", "academic_office", "office", "dept_head", "leader")


def _now() -> datetime:
    return clock.now()


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s)


def may_manage(c, user, cid: int) -> bool:
    """The course's teachers (its head or a unit's teacher) set, open and close its exams."""
    from ..learning import service as learning
    return learning.may_teach(c, user, cid)


def _public_exam(e: dict) -> dict:
    return {k: e[k] for k in ("id", "course_id", "kind", "title", "opens_at", "closes_at", "duration_min", "protection", "status", "attempt_no")}


def create(c, user, cid: int, body) -> tuple[str, object]:
    co = repo.course(c, cid)
    if not co or not may_manage(c, user, cid):
        return "missing", None
    v, problem = domain.exam_input(body, clock.ZONE, 0)
    if problem:
        return "invalid", problem
    problem = domain.plan_problem(repo.pool(c, cid), v["plan"])
    if problem:
        return "invalid", problem
    eid = repo.add_exam(c, cid, v, secrets.token_hex(16), user["id"], _iso(_now()))
    repo.add_event(c, eid, "exam.created", user["id"], None, {"title": v["title"], "opens_at": v["opens_at"], "closes_at": v["closes_at"]},
                   _iso(_now()))
    audit(c, user["id"], "exam_created", "course", f"{co['code']} · #{eid} · {v['title']}")
    return "ok", _public_exam(repo.exam(c, eid))


def list_for(c, user, cid: int) -> list[dict] | None:
    """A course's exams: all of them for its teachers and staff; the open and closed ones, with the student's place on
    the roster, for an enrolled student."""
    if user["role"] == "student":
        if user["id"] not in repo.enrolled(c, cid):
            return None
        out = []
        for e in repo.exams_of(c, cid, ("open", "closed", "released")):
            r = repo.roster_of(c, e["id"], user["id"])
            a = repo.attempt(c, e["id"], user["id"])
            out.append({**e, "roster": r["status"] if r else None, "attempt": a["status"] if a else None})
        return out
    if user["role"] in STAFF or may_manage(c, user, cid):
        return repo.exams_of(c, cid)
    return None


def manage(c, user, eid: int) -> dict | None:
    e = repo.exam(c, eid)
    if not e or not (user["role"] in STAFF or may_manage(c, user, e["course_id"])):
        return None
    from ...legacy.common import serves
    roster = [r for r in repo.roster(c, eid) if serves(c, user, r["student_id"])]
    shown = {r["student_id"] for r in roster}
    return {"exam": {**_public_exam(e), "plan": json.loads(e["plan"])}, "roster": roster,
            "attempts": [{k: a[k] for k in ("student_id", "full_name", "status", "started_at", "deadline_at", "submitted_at", "auto", "score", "max_score")}
                         for a in repo.attempts(c, eid) if a["student_id"] in shown], "pool": len(repo.pool(c, e["course_id"]))}


def open_exam(c, user, eid: int) -> tuple[str, object]:
    """Draw the roster once: the course's students; one not admitted by the journal (Task 20) is on it as excluded."""
    e = repo.exam(c, eid)
    if not e or not may_manage(c, user, e["course_id"]):
        return "missing", None
    if e["status"] != "draft":
        return "invalid", E("İmtahan artıq açılıb")
    from ..journal import service as journal
    standing = {s["student_id"]: s["status"] for s in journal.course_standing(c, e["course_id"])}
    at = _iso(_now())
    counts = {"eligible": 0, "excluded": 0}
    for sid in repo.enrolled(c, e["course_id"]):
        out = standing.get(sid) == "not_admitted"
        repo.put_roster(c, eid, sid, "excluded" if out else "eligible", "not_admitted" if out else None, None, at)
        counts["excluded" if out else "eligible"] += 1
    repo.set_exam(c, eid, status="open", opened_at=at)
    repo.add_event(c, eid, "exam.opened", user["id"], None, counts, at)
    audit(c, user["id"], "exam_opened", "exam", f"#{eid} · {counts}")
    return "ok", manage(c, user, eid)


def exception(c, user, eid: int, sid: int, body) -> tuple[str, object]:
    """The dean's office lets a student sit the exam despite the roster, with a reason; audited and in the log."""
    e = repo.exam(c, eid)
    from ...legacy.common import serves
    if not e or not serves(c, user, sid) or sid not in repo.enrolled(c, e["course_id"]):
        return "missing", None
    reason = " ".join(str(body.get("reason") or "").split())[:300]
    if len(reason) < 3:
        return "invalid", E("İstisnanın səbəbini yazın")
    at = _iso(_now())
    repo.put_roster(c, eid, sid, "exception", reason, user["id"], at)
    repo.add_event(c, eid, "roster.exception", user["id"], sid, {"reason": reason}, at)
    audit(c, user["id"], "exam_exception", "exam", f"#{eid} · #{sid} · {reason}")
    return "ok", manage(c, user, eid)


def may_enter(c, user, eid: int) -> tuple[str, object]:
    """('ok', exam) | ('missing', None) | ('refused', reason) | ('closed', reason): whether a student may take an exam
    session now (Task 27). The checks of Task 28 (Safe Exam Browser) and Task 29 (network list) join here."""
    e = repo.exam(c, eid)
    if not e or e["status"] == "draft":
        return "missing", None
    r = repo.roster_of(c, eid, user["id"])
    if not r or r["status"] == "excluded":
        repo.add_event(c, eid, "session.refused", user["id"], user["id"], {"reason": r["reason"] if r else "not_on_roster"}, _iso(_now()))
        return "refused", E("Siz bu imtahanın siyahısında deyilsiniz. Dekanlığa müraciət edin.") if not r or r["reason"] != "not_admitted" \
            else E("Davamiyyət həddi keçildiyi üçün imtahana buraxılmırsınız. Dekanlığa müraciət edin.")
    if e["status"] != "open" or _now() >= _t(e["closes_at"]):
        return "closed", E("İmtahan pəncərəsi açıq deyil")
    return "ok", e


def note_session(c, eid: int, user_id: int, kind: str, data: dict):
    """An exam session event: entered, took over an earlier exam session, an ordinary sign-in during the attempt."""
    repo.add_event(c, eid, kind, user_id, user_id, data, _iso(_now()))


def _form(c, e: dict, sid: int) -> list[dict]:
    f = repo.form(c, e["id"], sid)
    if not f:
        seed = domain.seed(e["secret"], e["id"], sid)
        repo.add_form(c, e["id"], sid, seed, domain.build_form(repo.pool(c, e["course_id"]), json.loads(e["plan"]), seed), _iso(_now()))
        f = repo.form(c, e["id"], sid)
    return json.loads(f["items"])


def start(c, user, eid: int) -> tuple[str, object]:
    """('ok', view) | ('missing') | ('refused', reason) | ('closed', reason). Starting twice returns the same attempt."""
    e = repo.exam(c, eid)
    if not e or e["status"] == "draft":
        return "missing", None
    have = repo.attempt(c, eid, user["id"])
    if have:
        return "ok", view(c, user, eid)
    r = repo.roster_of(c, eid, user["id"])
    t = _now()
    if not r or r["status"] == "excluded":
        why = E("Davamiyyət həddi keçildiyi üçün imtahana buraxılmırsınız. Dekanlığa müraciət edin.") if r and r["reason"] == "not_admitted" \
            else E("Siz bu imtahanın siyahısında deyilsiniz. Dekanlığa müraciət edin.")
        repo.add_event(c, eid, "attempt.refused", user["id"], user["id"], {"reason": r["reason"] if r else "not_on_roster"}, _iso(t))
        return "refused", why
    if e["status"] != "open" or not _t(e["opens_at"]) <= t < _t(e["closes_at"]):
        return "closed", E("İmtahan pəncərəsi açıq deyil")
    _form(c, e, user["id"])
    if repo.add_attempt(c, eid, user["id"], _iso(t), _iso(domain.deadline(t, e["duration_min"], _t(e["closes_at"])))):
        repo.add_event(c, eid, "attempt.started", user["id"], user["id"], {}, _iso(t))
    return "ok", view(c, user, eid)


def view(c, user, eid: int) -> dict | None:
    """What a student sees: the exam, their place on the roster and, once started, their own form (public keys only),
    their saved answers and the seconds left by the server's clock."""
    e = repo.exam(c, eid)
    if not e or user["id"] not in repo.enrolled(c, e["course_id"]) or e["status"] == "draft":
        return None
    r, a = repo.roster_of(c, eid, user["id"]), repo.attempt(c, eid, user["id"])
    out: dict = {"exam": _public_exam(e), "roster": r["status"] if r else None, "attempt": None, "questions": []}
    if a:
        items = _form(c, e, user["id"])
        qs = repo.questions(c, [x["qid"] for x in items])
        answers = repo.answers(c, a["id"])
        out["attempt"] = {"status": a["status"], "started_at": a["started_at"], "deadline_at": a["deadline_at"], "submitted_at": a["submitted_at"],
                          "remaining_s": max(0, int((_t(a["deadline_at"]) - _now()).total_seconds())) if a["status"] == "in_progress" else 0,
                          "answers": {str(k): v for k, v in answers.items()}}
        if a["status"] == "in_progress":
            out["questions"] = [domain.public(qs[x["qid"]], x["order"]) for x in items if x["qid"] in qs]
    return out


def answer(c, user, eid: int, qid: int, body) -> tuple[str, object]:
    e = repo.exam(c, eid)
    a = repo.attempt(c, eid, user["id"]) if e else None
    if not a:
        return "missing", None
    if a["status"] != "in_progress" or _now() > _t(a["deadline_at"]):
        return "closed", E("İmtahanın vaxtı bitib: cavab qəbul olunmur")
    if qid not in {x["qid"] for x in _form(c, e, user["id"])}:
        return "missing", None
    v = body.get("value")
    if v is not None and not (isinstance(v, (str, int, float)) and not isinstance(v, bool)) or (isinstance(v, str) and len(v) > 2000):
        return "invalid", E("Cavab düzgün deyil")
    repo.put_answer(c, a["id"], qid, json.dumps(v, ensure_ascii=False), _iso(_now()))
    return "ok", {"saved": True, "remaining_s": max(0, int((_t(a["deadline_at"]) - _now()).total_seconds()))}


def submit(c, user, eid: int) -> tuple[str, object]:
    a = repo.attempt(c, eid, user["id"])
    if not a:
        return "missing", None
    if a["status"] == "in_progress":
        t = _iso(_now())
        repo.set_attempt(c, a["id"], status="submitted", submitted_at=t)
        repo.add_event(c, eid, "attempt.submitted", user["id"], user["id"], {"attempt_id": a["id"], "auto": False}, t)
    return "ok", view(c, user, eid)


def autosubmit(c) -> str:
    """The job ``exam.autosubmit``: every attempt past its deadline and not submitted is submitted, without the student."""
    t = _iso(_now())
    done = 0
    for a in repo.overdue(c, t):
        repo.set_attempt(c, a["id"], status="submitted", submitted_at=a["deadline_at"], auto=1)
        repo.add_event(c, a["exam_id"], "attempt.submitted", None, a["student_id"], {"attempt_id": a["id"], "auto": True}, t)
        done += 1
    return f"submitted {done}"


def _grade(q: dict, order: list[int], stored: str | None) -> bool:
    from ...legacy import engine
    if stored is None:
        return False
    value = domain.original_value(q, order, json.loads(stored))
    if value in (None, ""):
        return False
    full = {**q, "options": json.loads(q["options"] or "[]"), "answer": json.loads(q["answer"]) if q["answer"] is not None else None}
    ok, _ = engine.grade(full, value)
    return bool(ok)


def close(c, user, eid: int) -> tuple[str, object]:
    """Grade every submitted attempt (an attempt still running is submitted first) and close the exam."""
    e = repo.exam(c, eid)
    if not e or not may_manage(c, user, e["course_id"]):
        return "missing", None
    if e["status"] != "open":
        return "invalid", E("Yalnız açıq imtahan bağlanır")
    t = _iso(_now())
    for a in repo.attempts(c, eid):
        if a["status"] == "in_progress":
            repo.set_attempt(c, a["id"], status="submitted", submitted_at=t, auto=1)
            repo.add_event(c, eid, "attempt.submitted", user["id"], a["student_id"], {"attempt_id": a["id"], "auto": True}, t)
        items = json.loads(repo.form(c, eid, a["student_id"])["items"])
        qs, answers = repo.questions(c, [x["qid"] for x in items]), repo.answers(c, a["id"])
        score = sum(1 for x in items if x["qid"] in qs and _grade(qs[x["qid"]], x["order"], answers.get(x["qid"])))
        repo.set_attempt(c, a["id"], status="graded", score=float(score), max_score=float(len(items)))
    repo.set_exam(c, eid, status="closed", closed_at=t)
    repo.add_event(c, eid, "exam.closed", user["id"], None, {"attempts": len(repo.attempts(c, eid))}, t)
    audit(c, user["id"], "exam_closed", "exam", f"#{eid}")
    return "ok", manage(c, user, eid)


jobs.periodic("exam.autosubmit", timedelta(minutes=1), autosubmit)
