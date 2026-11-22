"""The exam core (tasks/todo.md, Task 26): exams of a course, the roster drawn when an exam opens, one form and one
attempt per student, answers checked against the server's clock, an automatic submission at the deadline (the
``exam.autosubmit`` job), grading when the exam closes, and every step in the exam's log."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta

from ...core import clock, jobs
from ...core.i18n import E, T3
from ...legacy.store import J, audit
from . import domain, repo, seb

LIVE = ("in_progress", "paused")                       # an attempt not yet submitted


def _now() -> datetime:
    return clock.now()


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _refusal(c, eid: int, kind: str, user_id: int, data: dict):
    """A refusal event, at most REFUSAL_CAP of a kind per student and exam: the refusal itself (403) always happens,
    but a script cannot flood the exam's log, its protocol counts or the board."""
    if repo.count_events(c, eid, user_id, kind) < domain.REFUSAL_CAP:
        repo.add_event(c, eid, kind, user_id, user_id, data, _iso(_now()))


def open_count(c) -> int:
    """The exams going on now: a writing import does not start while there is one (Task 38)."""
    return repo.open_count(c)


def question_locked(c, q: dict) -> bool:
    """An exam question is not edited or deleted while an exam of its course is open (Checkpoint D, CR-3/TM-4): forms
    drawn from it would show or grade something else."""
    return (q.get("purpose") or "practice") == "exam" and repo.open_exam_of(c, q["course_id"])


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
    v, problem = domain.exam_input(body, clock.ZONE)
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
            extra = {"seb_link": seb_settings(repo.exam(c, e["id"]))["link"]} if e["protection"] == "seb" and e["status"] == "open" else {}
            out.append({**e, "roster": r["status"] if r else None, "attempt": a["status"] if a else None, **extra})
        return out
    from ..journal import service as journal
    if journal.can_read_course(c, user, cid) or may_manage(c, user, cid):   # the journal's read rule: a dept head of this course only
        return repo.exams_of(c, cid)
    return None


def manage(c, user, eid: int) -> dict | None:
    e = repo.exam(c, eid)
    if not e or not (_may_see_results(c, user, e) or may_manage(c, user, e["course_id"])):    # roster and raw scores: as /results
        return None
    from ...legacy.common import serves
    roster = [r for r in repo.roster(c, eid) if serves(c, user, r["student_id"])]
    shown = {r["student_id"] for r in roster}
    return {"exam": {**_public_exam(e), "plan": json.loads(e["plan"]), "allowed_cidrs": json.loads(e["allowed_cidrs"] or "[]"),
                     "protocol_id": e["protocol_id"],
                     **({"seb": {k: v for k, v in seb_settings(e).items() if k != "config"}} if e["protection"] == "seb" else {})},
            "proctors": repo.proctors(c, eid), "roster": roster,
            "attempts": [{k: a[k] for k in ("student_id", "full_name", "status", "started_at", "deadline_at", "submitted_at", "auto", "score", "max_score")}
                         for a in repo.attempts(c, eid) if a["student_id"] in shown], "pool": len(repo.pool(c, e["course_id"]))}


def open_exam(c, user, eid: int) -> tuple[str, object]:
    """Draw the roster once: the course's students; one not admitted by the journal (Task 20) is on it as excluded."""
    e = repo.exam(c, eid)
    if not e or not may_manage(c, user, e["course_id"]):
        return "missing", None
    if e["status"] != "draft":
        return "invalid", E("İmtahan artıq açılıb")
    problem = domain.plan_problem(repo.pool(c, e["course_id"]), json.loads(e["plan"]))   # the pool may have shrunk since
    if problem:
        return "invalid", problem
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
    if e["status"] != "open":
        return "closed", E("İstisna yalnız açıq imtahana verilir")         # a draft's roster is drawn anew when it opens
    reason = " ".join(str(body.get("reason") or "").split())[:300]
    if len(reason) < 3:
        return "invalid", E("İstisnanın səbəbini yazın")
    at = _iso(_now())
    repo.put_roster(c, eid, sid, "exception", reason, user["id"], at)
    repo.add_event(c, eid, "roster.exception", user["id"], sid, {"reason": reason}, at)
    audit(c, user["id"], "exam_exception", "exam", f"#{eid} · #{sid} · {reason}")
    return "ok", manage(c, user, eid)


def may_enter(c, user, eid: int, ip: str = "") -> tuple[str, object]:
    """('ok', exam) | ('missing', None) | ('refused', reason) | ('closed', reason): whether a student may take an exam
    session now (Task 27): on the roster, from an address on the exam's network list (Task 29). Task 28 (Safe Exam
    Browser) joins here."""
    e = repo.exam(c, eid)
    if not e or e["status"] == "draft":
        return "missing", None
    if e["status"] != "open":                         # a closed exam's chain takes no more refusals (Checkpoint D, CR-11)
        return "closed", E("İmtahan pəncərəsi açıq deyil")
    r = repo.roster_of(c, eid, user["id"])
    if not r or r["status"] == "excluded":
        _refusal(c, eid, "session.refused", user["id"], {"reason": r["reason"] if r else "not_on_roster"})
        return "refused", E("Siz bu imtahanın siyahısında deyilsiniz. Dekanlığa müraciət edin.") if not r or r["reason"] != "not_admitted" \
            else E("Davamiyyət həddi keçildiyi üçün imtahana buraxılmırsınız. Dekanlığa müraciət edin.")
    a = repo.attempt(c, eid, user["id"])
    running = bool(a and a["status"] in LIVE and _now() < _t(a["deadline_at"]))
    if e["status"] != "open" or (_now() >= _t(e["closes_at"]) and not running):   # an extended attempt still comes back in (TM-18)
        return "closed", E("İmtahan pəncərəsi açıq deyil")
    if not domain.ip_allowed(json.loads(e["allowed_cidrs"] or "[]"), ip):
        _refusal(c, eid, "session.refused", user["id"], {"reason": "network", "ip": ip})
        return "refused", NETWORK
    return "ok", e


NETWORK = E("Bu ünvandan imtahana daxil olmaq mümkün deyil: imtahan otağının şəbəkəsindən daxil olun")


SEB_OPEN = ("/seb-verify", "/leave")                    # what an exam session reaches before SEB is verified (Task 28)
SEB_NEEDED = E("Bu imtahan yalnız Safe Exam Browser-də açılır: imtahana SEB-dən daxil olun")


def check_request(c, eid: int, user, ip: str, session_ip: str | None, session_id: int, path: str = "", seb_ok: bool = True) -> dict | None:
    """Every request of an exam session (Task 29): an address off the exam's network list is refused and logged; a
    change of address on the list is a board event. Task 28: an exam in SEB mode answers its question and answer routes
    only to a session whose SEB hash checked out. Returns the refusal, or None. The caller commits the event."""
    e = repo.exam(c, eid)
    if not e:
        return None
    if not domain.ip_allowed(json.loads(e["allowed_cidrs"] or "[]"), ip):
        _refusal(c, eid, "net.refused", user["id"], {"ip": ip, "session_ip": session_ip})
        return NETWORK
    if session_ip and ip != session_ip:
        repo.add_event(c, eid, "net.changed", user["id"], user["id"], {"from": session_ip, "to": ip}, _iso(_now()))
        repo.set_session_ip(c, session_id, ip)
    if e["protection"] == "seb" and not seb_ok and not path.endswith(SEB_OPEN):
        return SEB_NEEDED
    return None


def note_session(c, eid: int, user_id: int, kind: str, data: dict):
    """An exam session event: entered, took over an earlier exam session, an ordinary sign-in during the attempt. Only
    while the exam is open: a stale exam session after the close adds nothing to its chain (Checkpoint D, CR-11)."""
    e = repo.exam(c, eid)
    if e and e["status"] == "open":
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
        _refusal(c, eid, "attempt.refused", user["id"], {"reason": r["reason"] if r else "not_on_roster"})
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
    if not e or not repo.is_enrolled(c, e["course_id"], user["id"]) or e["status"] == "draft":   # one indexed lookup (AR-9)
        return None
    r, a = repo.roster_of(c, eid, user["id"]), repo.attempt(c, eid, user["id"])
    out: dict = {"exam": _public_exam(e), "roster": r["status"] if r else None, "attempt": None, "questions": []}
    if a:
        items = _form(c, e, user["id"])
        qs = repo.questions(c, [x["qid"] for x in items])
        answers = repo.answers(c, a["id"])
        out["attempt"] = {"status": a["status"], "started_at": a["started_at"], "deadline_at": a["deadline_at"], "submitted_at": a["submitted_at"],
                          "remaining_s": domain.remaining(_t(a["deadline_at"]), _now(), _t(a["paused_at"]) if a["paused_at"] else None)
                          if a["status"] in LIVE else 0,
                          "answers": {str(k): v for k, v in answers.items()}}
        if a["status"] == "in_progress":
            out["questions"] = [domain.public(qs[x["qid"]], x["order"]) for x in items if x["qid"] in qs]
    return out


def answer(c, user, eid: int, qid: int, body) -> tuple[str, object]:
    repo.lock(c)                                       # Checkpoint D (TM-10): no answer lands after a submission froze it
    e = repo.exam(c, eid)
    a = repo.attempt(c, eid, user["id"]) if e else None
    if not a:
        return "missing", None
    if a["status"] == "paused":
        return "closed", E("İmtahan nəzarətçi tərəfindən dayandırılıb: cavablar imtahan davam etdirildikdə göndəriləcək")
    if a["status"] != "in_progress" or _now() > _t(a["deadline_at"]):
        return "closed", E("İmtahanın vaxtı bitib: cavab qəbul olunmur")
    if qid not in {x["qid"] for x in _form(c, e, user["id"])}:
        return "missing", None
    v = body.get("value")
    if v is not None and not (isinstance(v, (str, int, float)) and not isinstance(v, bool)) or (isinstance(v, str) and len(v) > 2000):
        return "invalid", E("Cavabın formatı düzgün deyil")
    repo.put_answer(c, a["id"], qid, json.dumps(v, ensure_ascii=False), _iso(_now()))
    return "ok", {"saved": True, "remaining_s": max(0, int((_t(a["deadline_at"]) - _now()).total_seconds()))}


def submit(c, user, eid: int, auto: bool = False) -> tuple[str, object]:
    """The student's submission. ``auto`` is the page's own at its 00:00: refused (409) while the server's deadline has
    not passed or the attempt is paused, so a proctor's extension or pause in the last seconds is kept (NEW-G1)."""
    repo.lock(c)                                       # Checkpoint D (CR-1): never turns a graded attempt back
    a = repo.attempt(c, eid, user["id"])
    if not a:
        return "missing", None
    if auto and (a["status"] == "paused" or (a["status"] == "in_progress" and _now() < _t(a["deadline_at"]))):
        return "closed", E("Vaxt hələ bitməyib: nəzarətçi vaxt əlavə edib və ya imtahanı dayandırıb")
    if a["status"] in LIVE:
        t = _iso(_now())
        repo.set_attempt(c, a["id"], status="submitted", submitted_at=t, paused_at=None)
        _submitted(c, eid, a, user["id"], False, t)
    return "ok", view(c, user, eid)


def autosubmit(c) -> str:
    """The job ``exam.autosubmit``: every attempt past its deadline and not submitted is submitted, without the student."""
    repo.lock(c)                                       # Checkpoint D (AR-1): the overdue list and the writes see one state
    t = _iso(_now())
    done = 0
    for a in repo.overdue(c, t):
        repo.set_attempt(c, a["id"], status="submitted", submitted_at=a["deadline_at"], auto=1)
        _submitted(c, a["exam_id"], a, None, True, t)
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
    repo.lock(c)                                       # Checkpoint D: a second close or a late submit waits, then sees "closed"
    e = repo.exam(c, eid)
    if not e or not may_manage(c, user, e["course_id"]):
        return "missing", None
    if e["status"] != "open":
        return "invalid", E("Yalnız açıq imtahan bağlanır")
    t = _iso(_now())
    forms, answers_of = repo.forms_full(c, eid), repo.answers_of_exam(c, eid)        # three reads for the whole exam (AR-3)
    qs = repo.questions(c, sorted({x["qid"] for f in forms.values() for x in json.loads(f["items"])}))
    for a in repo.attempts(c, eid):
        f = forms.get(a["student_id"])
        items, answers = (json.loads(f["items"]) if f else []), answers_of.get(a["id"], {})
        if a["status"] in LIVE:
            repo.set_attempt(c, a["id"], status="submitted", submitted_at=t, auto=1, paused_at=None)
            _submitted(c, eid, a, user["id"], True, t, f, answers)
        score = sum(1 for x in items if x["qid"] in qs and _grade(qs[x["qid"]], x["order"], answers.get(x["qid"])))
        repo.set_attempt(c, a["id"], status="graded", score=float(score), max_score=float(len(items)))
        repo.add_event(c, eid, "attempt.graded", user["id"], a["student_id"], {"attempt_id": a["id"], "score": float(score),
                                                                              "max_score": float(len(items))}, t)
    repo.set_exam(c, eid, status="closed", closed_at=t)
    repo.add_event(c, eid, "exam.closed", user["id"], None, {"attempts": len(repo.attempts(c, eid))}, t)
    doc = _protocol(c, user, repo.exam(c, eid))
    audit(c, user["id"], "exam_closed", "exam", f"#{eid}")
    out = manage(c, user, eid) or {}
    return "ok", {**out, "root_mailed": doc["root_mailed"]}


def _submitted(c, eid: int, a: dict, actor: int | None, auto: bool, at: str, form: dict | None = None, answers: dict | None = None):
    """The submission event (Task 30) freezes the attempt: its form (seed and the digest of its items, Checkpoint D TM-5)
    and the digest of its answers as stored."""
    f = form if form is not None else repo.form(c, eid, a["student_id"])
    repo.add_event(c, eid, "attempt.submitted", actor, a["student_id"],
                   {"attempt_id": a["id"], "auto": auto, "form_seed": f["seed"] if f else None,
                    "form_sha256": hashlib.sha256(f["items"].encode()).hexdigest() if f else None,
                    "answers_sha256": domain.answers_digest(answers if answers is not None else repo.answers(c, a["id"]))}, at)


def verify(c, eid: int, root: str | None = None) -> dict | None:
    """``manage.py exam-verify`` (Task 30, Checkpoint D): every link of the exam's chain; no attempt event after the
    exam closed; every attempt row against its events (it exists, belongs to the student, its status, its form, its
    answers as frozen at the last submission, its score and maximum as graded); every printed anchor (the protocol and
    the statements, read from their hashed payloads); ``root`` (from an e-mail) must be a link of the chain.
    ``problems`` is empty when everything holds."""
    e = repo.exam(c, eid)
    if not e:
        return None
    events = repo.events(c, eid)
    problems: list[dict] = []
    broken = domain.chain_break(events)
    if broken:
        problems.append({"what": "chain", **broken})
    submitted: dict[int, dict] = {}
    graded: dict[int, dict] = {}
    owner: dict[int, int] = {}
    closed_at = None
    for ev in events:
        if ev["kind"] == "exam.closed" and closed_at is None:
            closed_at = ev["seq"]
        if ev["kind"] in ("attempt.submitted", "attempt.graded"):
            data = json.loads(ev["data"] or "{}")
            aid = data.get("attempt_id")
            if ev["kind"] == "attempt.submitted" and closed_at is not None:    # nothing submits after the close (TM-1)
                problems.append({"what": "event", "seq": ev["seq"], "problem": "submission_after_close"})
            if ev["kind"] == "attempt.graded" and closed_at is not None and ev["seq"] > closed_at:
                problems.append({"what": "event", "seq": ev["seq"], "problem": "grading_after_close"})
            (submitted if ev["kind"] == "attempt.submitted" else graded)[aid] = data          # the last one counts
            owner.setdefault(aid, ev["student_id"])
    rows_ = {a["id"]: a for a in repo.attempts(c, eid)}
    forms = repo.forms_full(c, eid)
    answers_of = repo.answers_of_exam(c, eid)
    bad = lambda a, why: problems.append({"what": "attempt", "attempt_id": a["id"] if isinstance(a, dict) else a,  # noqa: E731
                                          "student_id": a["student_id"] if isinstance(a, dict) else owner.get(a), "problem": why})
    for aid in owner:
        if aid not in rows_:
            bad(aid, "attempt_missing")                                     # deleted after its events (TM-2)
    for a in rows_.values():
        if a["id"] in owner and owner[a["id"]] != a["student_id"]:
            bad(a, "student_changed")
        if closed_at is not None and a["status"] != "graded":
            bad(a, "status_changed")
        if a["status"] in ("submitted", "graded"):
            s = submitted.get(a["id"])
            f = forms.get(a["student_id"])
            if not s:
                bad(a, "no_submission_event")
            else:
                if s.get("answers_sha256") != domain.answers_digest(answers_of.get(a["id"], {})):
                    bad(a, "answers_changed")
                if f and (s.get("form_seed") != f["seed"] or (s.get("form_sha256") and s["form_sha256"] != hashlib.sha256(f["items"].encode()).hexdigest())):
                    bad(a, "form_changed")                                  # TM-5
        if a["status"] == "graded":
            g = graded.get(a["id"])
            if not g:
                bad(a, "no_grading_event")
            elif g.get("score") != a["score"] or ("max_score" in g and g["max_score"] != a["max_score"]):
                bad(a, "score_changed")
    head = events[-1]["hash"] if events else domain.GENESIS
    by_seq = {ev["seq"]: ev["hash"] for ev in events}
    if closed_at is not None and not e["protocol_id"]:
        problems.append({"what": "anchor", "document": "protocol", "seq": closed_at, "problem": "anchor_missing"})
    for name, data in _anchors(c, eid):
        if data is None:
            problems.append({"what": "anchor", "document": name, "seq": None, "problem": "anchor_unreadable"})
        elif by_seq.get(data.get("seq")) != data.get("root"):
            problems.append({"what": "anchor", "document": name, "seq": data.get("seq"), "problem": "root_differs"})
    if root is not None and root.strip().lower() not in by_seq.values():
        problems.append({"what": "root", "problem": "not_in_chain", "head": head})
    return {"exam_id": eid, "events": len(events), "head": head, "problems": problems}


def _anchors(c, eid: int) -> list[tuple[str, dict | None]]:
    """The documents that printed a link of the chain: the closing protocol and each group's statement, read from the
    payload whose hash the document carries (Checkpoint D, TM-16); a document missing or changed reads as None."""
    from ...legacy.store import payload_state
    e = repo.exam(c, eid)
    out: list[tuple[str, dict | None]] = []

    def read(name: str, did: int):
        d = repo.document(c, did)
        if not d or payload_state(d) != "ok":
            out.append((name, None))
        else:
            out.append((name, json.loads(d["payload"]).get("data") or {}))
    if e and e["protocol_id"]:
        read("protocol", e["protocol_id"])
    for st in repo.statements(c, eid).values():
        read(f"statement {st['group_id']}", st["document_id"])
    return out


# ---------------------------------------------------------------- Safe Exam Browser (Task 28)
def _base() -> str:
    from ...legacy.common import BASE_URL
    return BASE_URL["value"].rstrip("/")


def seb_settings(e: dict) -> dict:
    """The exam's SEB configuration, its Config Key, the config download token and the quit password (derived from the
    exam's secret, so nothing is stored and the key always matches the file that is served)."""
    quit_password = seb.secret(e["secret"], "quit")[:8]
    cfg = seb.config(e["id"], _base(), quit_password)
    token = seb.secret(e["secret"], "config")[:32]
    return {"config": cfg, "key": seb.config_key(cfg), "token": token, "quit_password": quit_password,
            "link": seb.launch_link(_base(), e["id"], token), "download": f"/exam/{e['id']}/config.seb?k={token}"}


def seb_file(c, eid: int, token: str) -> bytes | None:
    """The .seb file for SEB to fetch (no session: SEB downloads it itself); only with the exam's token."""
    e = repo.exam(c, eid)
    if not e or e["protection"] != "seb" or e["status"] not in ("draft", "open") or not isinstance(token, str):
        return None
    st = seb_settings(e)
    return seb.to_file(st["config"]) if hmac.compare_digest(token.encode(), st["token"].encode()) else None


def seb_verify(c, user, eid: int, session_id: int, nonce: str | None, raw_target: str, header: str | None, body) -> tuple[str, object]:
    """Mark the exam session verified when SEB's Config Key hash is right: the header over the public address plus this
    request's raw target, or the JS API's hash over the page URL the client sends; both carry the session's one-time
    value. A refusal is an exam event."""
    e = repo.exam(c, eid)
    if not e:
        return "missing", None
    if e["protection"] != "seb":
        return "ok", {"ok": True, "seb": False}
    key, base = seb_settings(e)["key"], _base()
    page, js_hash = body.get("url"), body.get("config_key_hash")
    ok = seb.header_ok(base, raw_target, header or "", key, nonce or "") or seb.page_ok(base, page, js_hash, key, nonce or "")
    at = _iso(_now())
    if not ok:
        _refusal(c, eid, "seb.refused", user["id"], {"header": bool(header), "js": bool(js_hash)})
        return "refused", SEB_NEEDED
    repo.set_seb_ok(c, session_id)
    if repo.has_other_session(c, user["id"], f"exam:{eid}", session_id):     # now the earlier exam session gives way
        repo.end_sessions_except(c, user["id"], f"exam:{eid}", keep_id=session_id)
        repo.add_event(c, eid, "session.takeover", user["id"], user["id"], {"seb": True}, at)
    repo.add_event(c, eid, "seb.verified", user["id"], user["id"], {"path": "header" if header and seb.header_ok(base, raw_target, header, key, nonce or "") else "js"}, at)
    return "ok", {"ok": True, "seb": True}


# ---------------------------------------------------------------- the proctor panel (Task 29)
WATCHERS = ("admin", "academic_office")               # reach every exam's board without an assignment


def may_proctor(c, user, e: dict) -> bool:
    """The exam's assigned proctors, the course's teachers, the academic office and the administrator."""
    return user["role"] in WATCHERS or repo.is_proctor(c, e["id"], user["id"]) or may_manage(c, user, e["course_id"])


def set_proctors(c, user, eid: int, body) -> tuple[str, object]:
    """Assign the exam's proctors by username (staff accounts only); replaces the list."""
    e = repo.exam(c, eid)
    if not e or not (user["role"] in WATCHERS or may_manage(c, user, e["course_id"])):
        return "missing", None
    names = body.get("usernames")
    if not isinstance(names, list) or len(names) > 20 or not all(isinstance(n, str) for n in names):
        return "invalid", E("Nəzarətçilərin siyahısında ən çox 20 istifadəçi adı ola bilər")
    names = sorted({n.strip() for n in names if n.strip()})
    found = {u["username"]: u for u in repo.staff_by_username(c, names)}
    bad = [n for n in names if n not in found or found[n]["role"] == "student" or found[n]["status"] != "active"]
    if bad:
        return "invalid", E("Aktiv əməkdaş tapılmadı: {names}", names=", ".join(bad))
    uids = [found[n]["id"] for n in names]
    at = _iso(_now())
    repo.set_proctors(c, eid, uids, user["id"], at)
    repo.add_event(c, eid, "proctors.set", user["id"], None, {"user_ids": uids}, at)
    audit(c, user["id"], "exam_proctors", "exam", f"#{eid} · {', '.join(names) or '—'}")
    return "ok", {"proctors": repo.proctors(c, eid)}


def watch_list(c, user) -> list[dict]:
    """The exams on the user's proctor page: assigned ones, the open exams of the courses they head, and for the
    academic office and the administrator every open exam."""
    seen: dict[int, dict] = {e["id"]: e for e in repo.proctor_exams(c, user["id"])}
    more = repo.open_exams(c) if user["role"] in WATCHERS else repo.open_exams(c, user["id"]) if user["role"] in ("teacher", "dept_head") else []
    for e in more:
        seen.setdefault(e["id"], e)
    return sorted(seen.values(), key=lambda e: e["opens_at"])


BOARD_FLAGS = ("client.blur", "client.fullscreen_exit", "client.reconnect", "net.changed", "net.refused", "login.during_exam", "seb.refused")


def board(c, user, eid: int, after: int = 0) -> dict | None:
    """The live board (polled every 5 s): every student on the roster with the attempt's state, progress, time left,
    when last seen, the address and the counts of the flagged events; and the exam's events after ``after``."""
    e = repo.exam(c, eid)
    if not e or not may_proctor(c, user, e):
        return None
    from ...legacy.store import now as local_now
    t, local = _now(), local_now()
    attempts = {a["student_id"]: a for a in repo.attempts(c, eid)}
    counts, last, flags = repo.answer_counts(c, eid), repo.last_answers(c, eid), repo.event_counts(c, eid)
    sessions = repo.exam_sessions(c, f"exam:{eid}")
    total = sum(int(x["count"]) for x in json.loads(e["plan"]))
    students = []
    for r in repo.roster(c, eid):
        sid, a, s = r["student_id"], attempts.get(r["student_id"]), sessions.get(r["student_id"])
        idle = []
        if s and s["last_seen"]:
            idle.append((local - datetime.fromisoformat(s["last_seen"])).total_seconds())
        if a and last.get(a["id"]):
            idle.append((t - _t(last[a["id"]])).total_seconds())
        students.append({
            "student_id": sid, "full_name": r["full_name"], "student_no": r["student_no"], "roster": r["status"], "reason": r["reason"],
            "attempt": a["status"] if a else None, "answered": counts.get(a["id"], 0) if a else 0, "total": total,
            "remaining_s": domain.remaining(_t(a["deadline_at"]), t, _t(a["paused_at"]) if a["paused_at"] else None) if a and a["status"] in LIVE else 0,
            "deadline_at": a["deadline_at"] if a else None, "online": bool(s), "seen_s": int(max(0, min(idle))) if idle else None,
            "ip": s["ip"] if s else None, "flags": {k: n for k, n in flags.get(sid, {}).items() if k in BOARD_FLAGS}})
    events = repo.events_after(c, eid, max(0, after))
    for ev in events:
        ev["data"] = json.loads(ev["data"] or "{}")
    return {"exam": {**_public_exam(e), "allowed_cidrs": json.loads(e["allowed_cidrs"] or "[]")}, "now": _iso(t),
            "students": students, "events": events, "seq": events[-1]["seq"] if events else max(0, after)}


def act(c, user, eid: int, sid: int, action: str, body) -> tuple[str, object]:
    """A proctor's action on one student of the exam's roster, always with a reason, always in the exam's log:
    extend (minutes), pause, resume, end, reopen (minutes from now), unlock (the student's sign-in lock)."""
    repo.lock(c)                                       # Checkpoint D (TM-10): an extension never races the autosubmit
    e = repo.exam(c, eid)
    if not e or not may_proctor(c, user, e) or not repo.roster_of(c, eid, sid):
        return "missing", None
    v, problem = domain.proctor_input(action, body)
    if problem:
        return "invalid", problem
    t = _now()
    a = repo.attempt(c, eid, sid)
    wrong = "closed", E("Bu əməliyyat cəhdin indiki vəziyyətində mümkün deyil")
    data: dict = {"reason": v["reason"]}
    if action == "unlock":
        if e["status"] != "open":
            return wrong                                # the sign-in lock is the exam's business only while it runs
        from ..identity import service as identity
        target = identity.account(c, sid)
        if not target:
            return "missing", None
        identity.unlock(c, user, target, f"imtahan #{eid} · {v['reason']}")
    else:
        if e["status"] != "open" or not a:
            return wrong
        if action == "extend" and a["status"] in LIVE:
            new = _t(a["deadline_at"]) + timedelta(minutes=v["minutes"])
            repo.set_attempt(c, a["id"], deadline_at=_iso(new))
            data.update(minutes=v["minutes"], deadline_at=_iso(new))
        elif action == "pause" and a["status"] == "in_progress" and t < _t(a["deadline_at"]):
            repo.set_attempt(c, a["id"], status="paused", paused_at=_iso(t))
        elif action == "resume" and a["status"] == "paused":
            new = domain.resumed_deadline(_t(a["deadline_at"]), _t(a["paused_at"]), t)
            repo.set_attempt(c, a["id"], status="in_progress", paused_at=None, deadline_at=_iso(new))
            data.update(deadline_at=_iso(new))
        elif action == "end" and a["status"] in LIVE:
            repo.set_attempt(c, a["id"], status="submitted", submitted_at=_iso(t), auto=1, paused_at=None)
            _submitted(c, eid, a, user["id"], True, _iso(t))
        elif action == "reopen" and a["status"] == "submitted":
            new = t + timedelta(minutes=v["minutes"])
            repo.set_attempt(c, a["id"], status="in_progress", submitted_at=None, auto=0, paused_at=None, deadline_at=_iso(new))
            data.update(minutes=v["minutes"], deadline_at=_iso(new))
        else:
            return wrong
    repo.add_event(c, eid, f"proctor.{action}", user["id"], sid, data, _iso(t))
    audit(c, user["id"], f"exam_{action}", "exam", f"#{eid} · #{sid} · {v['reason']}")
    return "ok", board(c, user, eid)


def signal(c, user, eid: int, body) -> tuple[str, object]:
    """What the exam page reports by itself (focus lost, full screen left, reconnected): a board flag, capped per student."""
    kind = body.get("kind")
    if kind not in domain.SIGNALS:
        return "invalid", E("Naməlum siqnal")
    e = repo.exam(c, eid)
    if not e or e["status"] != "open":                # nothing is added to a closed exam's chain (Checkpoint D, CR-11)
        return "ok", {"ok": True, "kept": False}
    if repo.count_events(c, eid, user["id"], f"client.{kind}") >= domain.SIGNAL_CAP:    # per kind: blur spam does not hide the rest
        return "ok", {"ok": True, "kept": False}
    repo.add_event(c, eid, f"client.{kind}", user["id"], user["id"], {}, _iso(_now()))
    return "ok", {"ok": True, "kept": True}


# ---------------------------------------------------------------- protocol, release, statements, analysis (Task 30)
PROTOCOL_FLAGS = ("client.blur", "client.fullscreen_exit", "client.reconnect", "net.changed", "net.refused", "login.during_exam",
                  "session.refused", "session.takeover", "seb.refused")
EXAM_DOCS = ("exam_protocol", "exam_statement")


def _protocol(c, user, e: dict) -> dict:
    """The closing protocol (a QR document through the stored-payload path of Task 45): the facts, the counts, the
    incidents and the chain's root at closing, which also goes by e-mail to the course's teacher and the dean's offices."""
    from ...legacy.common import BASE_URL
    from ...legacy.store import issue_document
    eid = e["id"]
    h = repo.head(c, eid)
    co = repo.course(c, e["course_id"])
    roster = repo.roster_groups(c, eid)
    attempts = repo.attempts(c, eid)
    counts: dict[str, int] = {}
    for per in repo.event_counts(c, eid).values():
        for k, n in per.items():
            counts[k] = counts.get(k, 0) + n
    seated = sum(1 for r in roster if r["status"] != "excluded")
    groups = sorted({r["group_id"] for r in roster if r["group_id"]})
    data = {"type": "exam_protocol", "exam_id": eid, "course_id": co["id"], "course": f"{co['code']} · {co['name']}", "title": e["title"],
            "kind": e["kind"], "attempt_no": e["attempt_no"], "opens_at": e["opens_at"], "closes_at": e["closes_at"], "duration_min": e["duration_min"],
            "roster": {k: sum(1 for r in roster if r["status"] == k) for k in ("eligible", "exception", "excluded")},
            "attempts": {"started": len(attempts), "auto": sum(1 for a in attempts if a["auto"]), "absent": max(0, seated - len(attempts))},
            "incidents": {k: counts[k] for k in PROTOCOL_FLAGS if counts.get(k)},
            "actions": {k: n for k, n in sorted(counts.items()) if k.startswith("proctor.")},
            "group_ids": groups, "seq": h["seq"], "root": h["hash"]}
    doc = issue_document(c, "exam_protocol", co["teacher_id"], "İmtahan protokolu", data, user["id"], "IMP")
    repo.set_exam(c, eid, protocol_id=doc["id"])
    doc["root_mailed"] = _send_root(c, e, "close", f"{BASE_URL['value']}/verify/{doc['verify_code']}")
    return doc


def _send_root(c, e: dict, what: str, verify_url: str = "") -> int:
    """The chain's head leaves the database after every step that ends a stage (closing, release, a statement, an
    office's score change; Checkpoint D, TM-3): by e-mail to the course's teacher and the dean's offices of the exam's
    groups. Returns how many messages were queued; none (no relay, no address) is in the audit log, never silent (TM-12)."""
    from ..comms import service as comms
    h = repo.head(c, e["id"])
    co = repo.course(c, e["course_id"])
    groups = sorted({r["group_id"] for r in repo.roster_groups(c, e["id"]) if r["group_id"]})
    params = {"title": e["title"], "root": h["hash"], "seq": h["seq"], "exam_id": e["id"], "what": what, "verify_url": verify_url}
    people = [repo.person(c, co["teacher_id"])] + repo.offices_of_groups(c, groups)
    sent = 0
    for p in {x["id"]: x for x in people if x}.values():
        lang = (J(p["prefs"], {}) or {}).get("lang") or "az"
        sent += bool(comms.queue_to(c, p["email"] or "", "exam.root", "exam.root", params, lang, p["id"]))
    audit(c, None, "exam_root_mailed" if sent else "exam_root_not_mailed", "exam", f"#{e['id']} · {what} · seq {h['seq']} · {h['hash']} · {sent}")
    return sent


def may_read_doc(c, user, doc: dict) -> bool:
    """Who opens an exam's protocol or statement: the course's teachers, the academic office, the administrator and
    leadership, and a dean's office whose faculty covers the group (the statement) or one of the groups (the protocol)."""
    data = json.loads(doc["data"] or "{}")
    if user["role"] in ("academic_office", "admin", "leader") or doc["holder_id"] == user["id"]:
        return True
    if user["role"] == "office":
        gids = [data["group_id"]] if data.get("group_id") else data.get("group_ids") or []
        return any(repo.office_serves_group(c, user["id"], g) for g in gids)
    return bool(data.get("course_id")) and may_manage(c, user, data["course_id"])


def release(c, user, eid: int) -> tuple[str, object]:
    """The teacher releases a closed exam: each graded attempt's raw score, scaled to the exam component, is published
    in the journal with the exam and its attempt number; an earlier result (a first attempt before a retake) stays in its
    exam and in the grade journal."""
    repo.lock(c)
    e = repo.exam(c, eid)
    if not e or not may_manage(c, user, e["course_id"]):
        return "missing", None
    if e["status"] != "closed":
        return "invalid", E("Yalnız bağlanmış imtahanın nəticəsi açıqlanır")
    from ...legacy.store import notify
    from ..journal import service as journal
    col = journal.exam_column(c, e["course_id"])
    scores = [(a["student_id"], domain.scale(min(a["score"], a["max_score"]), a["max_score"], col["max"]))   # never above the component
              for a in repo.attempts(c, eid) if a["status"] == "graded"]
    shown, skipped = journal.put_exam_scores(c, user["id"], e["course_id"], scores, eid, e["attempt_no"], f"imtahan #{eid}: {e['title']}")
    t = _iso(_now())
    repo.set_exam(c, eid, status="released")
    repo.add_event(c, eid, "exam.released", user["id"], None, {"scores": len(shown), "skipped": skipped, "component": col["key"],
                                                               "max": col["max"]}, t)
    if shown:
        notify(c, shown, "exam", T3("İmtahan nəticəsi açıqlandı: {title}", title=e["title"]), "", "/student/grades")
    audit(c, user["id"], "exam_released", "exam", f"#{eid} · {len(shown)} · skipped {len(skipped)}")
    _send_root(c, e, "release")
    from ..integration import webhooks
    webhooks.emit(c, "exam.released", {"exam_id": eid, "course_id": e["course_id"], "released": len(shown), "skipped": len(skipped)})
    return "ok", {"ok": True, "released": len(shown), "skipped": skipped}


def _rows(c, e: dict, students: list[dict]) -> list[dict]:
    """Each student's line of a released exam: raw score, points, the course's semester points, total, letter, status."""
    from ..journal import service as journal
    co = repo.course(c, e["course_id"])
    col = journal.exam_column(c, e["course_id"])
    attempts = {a["student_id"]: a for a in repo.attempts(c, e["id"])}
    graded = journal.published_results(c, co, [r["student_id"] for r in students
                                               if attempts.get(r["student_id"], {}).get("status") == "graded"])
    out = []
    for r in students:
        a = attempts.get(r["student_id"])
        res = graded[r["student_id"]][1] if r["student_id"] in graded else None
        out.append({"student_id": r["student_id"], "full_name": r["full_name"], "student_no": r["student_no"], "group_id": r.get("group_id"),
                    "group_name": r.get("group_name"), "raw": a["score"] if a and a["status"] == "graded" else None,
                    "raw_max": a["max_score"] if a else None,
                    "points": domain.scale(a["score"], a["max_score"], col["max"]) if a and a["status"] == "graded" else None,
                    "semester": res["semester"] if res else None, "total": res["total"] if res else None, "letter": res["letter"] if res else None,
                    "status": domain.result_status(r["status"], a["status"] if a else None, res)})
    return out


def _may_see_results(c, user, e: dict) -> bool:
    """The journal's own read rule (Checkpoint D, SEC-4): the course's teachers, a department head whose grant covers the
    course, the registry offices and leadership; a dean's office then sees only its faculties' students."""
    from ..journal import service as journal
    return journal.can_read_course(c, user, e["course_id"])


def results(c, user, eid: int) -> dict | None:
    """A released (or closed) exam's results: the course's teachers, the academic office, leadership; a dean's office
    sees its own faculties' students."""
    e = repo.exam(c, eid)
    if not e or e["status"] not in ("closed", "released") or not _may_see_results(c, user, e):
        return None
    from ...legacy.common import serves
    from ..journal import service as journal
    students = [r for r in repo.roster_groups(c, eid) if serves(c, user, r["student_id"])]
    return {"exam": _public_exam(e), "released": e["status"] == "released", "rows": _rows(c, e, students),
            "exam_max": journal.exam_column(c, e["course_id"])["max"]}


def course_results(c, user, cid: int) -> list[dict] | None:
    """Every released exam of a course with its results, a retake next to the first attempt: neither replaces the other."""
    from ..journal import service as journal
    if not repo.course(c, cid) or not journal.can_read_course(c, user, cid):
        return None
    return [r for r in (results(c, user, e["id"]) for e in repo.exams_of(c, cid, ("released",))) if r]


def statements(c, user, eid: int) -> dict | None:
    """The groups of a released exam and whether the dean's office has closed each one's statement."""
    e = repo.exam(c, eid)
    if not e or e["status"] != "released" or not _may_see_results(c, user, e):
        return None
    closed = repo.statements(c, eid)
    groups: dict[int, dict] = {}
    served: dict[int, bool] = {}
    for r in repo.roster_groups(c, eid):
        gid = r["group_id"]
        if gid and gid not in served:
            served[gid] = user["role"] != "office" or repo.office_serves_group(c, user["id"], gid)   # once per group (AR-5)
        if gid and served[gid]:
            g = groups.setdefault(gid, {"group_id": gid, "group_name": r["group_name"], "students": 0})
            g["students"] += 1
    for g in groups.values():
        st = closed.get(g["group_id"])
        g.update(closed=bool(st), document_id=st["document_id"] if st else None, reg_no=st["reg_no"] if st else None,
                 verify_code=st["verify_code"] if st else None, closed_at=st["closed_at"] if st else None)
    return {"exam": _public_exam(e), "groups": sorted(groups.values(), key=lambda g: g["group_name"] or "")}


def statement_list(c, user) -> list[dict]:
    """The dean's office's page: the released exams with a group it serves, and how many of their statements are closed."""
    out = []
    for e in (repo.released_exams_for_office(c, user["id"]) if user["role"] == "office" else repo.released_exams(c)):   # AR-5
        st = statements(c, user, e["id"])
        if st and st["groups"]:
            out.append({**e, "groups": len(st["groups"]), "closed": sum(1 for g in st["groups"] if g["closed"])})
    return out


def close_statement(c, user, eid: int, gid: int) -> tuple[str, object]:
    """The dean's office closes a group's statement: a QR document of the group's results with the chain's head; from
    then on an exam score of the group changes only through the office (``change_score``)."""
    repo.lock(c)                                       # Checkpoint D (CR-10): a second close waits, then answers 409
    e = repo.exam(c, eid)
    if not e or e["status"] != "released" or (user["role"] == "office" and not repo.office_serves_group(c, user["id"], gid)):
        return "missing", None
    students = [r for r in repo.roster_groups(c, eid) if r["group_id"] == gid]
    if not students:
        return "missing", None
    if gid in repo.statements(c, eid):
        return "closed", E("Bu qrupun cədvəli artıq bağlanıb")
    from ...legacy.store import issue_document
    co = repo.course(c, e["course_id"])
    h = repo.head(c, eid)
    data = {"type": "exam_statement", "exam_id": eid, "course_id": co["id"], "course": f"{co['code']} · {co['name']}", "title": e["title"],
            "kind": e["kind"], "attempt_no": e["attempt_no"], "group_id": gid, "group_name": students[0]["group_name"],
            "rows": [{k: r[k] for k in ("full_name", "student_no", "points", "semester", "total", "letter", "status")} for r in _rows(c, e, students)],
            "seq": h["seq"], "root": h["hash"]}
    doc = issue_document(c, "exam_statement", co["teacher_id"], "İmtahan-qiymət cədvəli", data, user["id"], "IQC")
    t = _iso(_now())
    repo.add_statement(c, eid, gid, doc["id"], user["id"], t)
    repo.add_event(c, eid, "statement.closed", user["id"], None, {"group_id": gid, "document_id": doc["id"], "reg_no": doc["reg_no"]}, t)
    audit(c, user["id"], "exam_statement_closed", "exam", f"#{eid} · {students[0]['group_name']} · {doc['reg_no']}")
    _send_root(c, e, "statement")
    return "ok", statements(c, user, eid)


def change_score(c, user, eid: int, sid: int, body) -> tuple[str, object]:
    """After the statement is closed, the dean's office changes an exam score with a reason and a grade appeal of the
    student or an order number; the change is in the grade journal and the exam log; the attempt itself is not touched."""
    repo.lock(c)
    e = repo.exam(c, eid)
    from ...legacy.common import serves
    if not e or e["status"] != "released" or not serves(c, user, sid):
        return "missing", None
    r = next((x for x in repo.roster_groups(c, eid) if x["student_id"] == sid), None)
    if not r or r["group_id"] not in repo.statements(c, eid):
        return "closed", E("Cədvəl hələ bağlanmayıb: balı müəllim jurnalda dəyişir")
    from ..journal import service as journal
    col = journal.exam_column(c, e["course_id"])
    score = body.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= col["max"]:
        return "invalid", E("Bal 0 ilə {max} arasında olmalıdır", max=col["max"])
    reason = " ".join(str(body.get("reason") or "").split())[:300]
    appeal, order = body.get("appeal_id"), " ".join(str(body.get("order_no") or "").split())[:40]
    if len(reason) < 3:
        return "invalid", E("Dəyişikliyin səbəbini yazın")
    if appeal is not None:
        req_ = repo.appeal_state(c, appeal, sid) if isinstance(appeal, int) and not isinstance(appeal, bool) else None
        if not req_:
            return "invalid", E("Bu tələbənin belə apellyasiya müraciəti yoxdur")
        if req_["status"] in ("rejected", "cancelled") or repo.appeal_used(c, sid, e["course_id"], appeal):   # SEC-6
            return "invalid", E("Bu apellyasiya rədd edilib, ləğv olunub və ya artıq tətbiq edilib")
    elif not order or not any(ch.isdigit() for ch in order):
        return "invalid", E("Apellyasiya müraciətini və ya əmrin nömrəsini göstərin")
    cell = journal.exam_cell(c, e["course_id"], sid)
    if cell and cell["exam_id"] and cell["exam_id"] != eid:                     # CR-7: the journal holds another exam's score
        return "closed", E("Tələbənin jurnaldakı imtahan balı başqa imtahandandır: dəyişiklik o imtahanda aparılır")
    score = domain.points(score)                                                # the one rounding rule (PY-9)
    basis = f"apellyasiya #{appeal}" if appeal is not None else f"əmr № {order}"
    journal.put_exam_score(c, user["id"], e["course_id"], sid, float(score), eid, e["attempt_no"], f"{reason} · {basis}", source="appeal")
    t = _iso(_now())
    repo.add_event(c, eid, "score.changed", user["id"], sid, {"score": float(score), "reason": reason, "appeal_id": appeal, "order_no": order or None}, t)
    audit(c, user["id"], "exam_score_changed", "exam", f"#{eid} · #{sid} · {score} · {reason} · {basis}")
    _send_root(c, e, "score")
    return "ok", {"ok": True, "score": float(score)}


def analysis(c, user, eid: int) -> dict | None:
    """For the course's teachers only: each question's share of correct answers and its commonest wrong answers, and
    pairs of students with the same wrong answers to several questions (a signal to look at, not a verdict)."""
    e = repo.exam(c, eid)
    if not e or e["status"] not in ("closed", "released") or not may_manage(c, user, e["course_id"]):
        return None
    forms = repo.forms(c, eid)
    order = {(sid, x["qid"]): x["order"] for sid, items in forms.items() for x in items}
    qs = repo.questions(c, sorted({x["qid"] for items in forms.values() for x in items}))
    answered = {q: 0 for q in qs}
    correct = {q: 0 for q in qs}
    wrong_values: dict[int, dict[str, int]] = {q: {} for q in qs}
    wrong: dict[int, dict[int, str]] = {}
    for r in repo.all_answers(c, eid):
        q = qs.get(r["qid"])
        if not q or r["value"] in (None, "null", '""'):
            continue
        answered[r["qid"]] += 1
        seen = order.get((r["student_id"], r["qid"]), [])
        if _grade(q, seen, r["value"]):
            correct[r["qid"]] += 1
        else:
            shown = json.dumps(domain.original_value(q, seen, json.loads(r["value"])), ensure_ascii=False)
            wrong_values[r["qid"]][shown] = wrong_values[r["qid"]].get(shown, 0) + 1
            wrong.setdefault(r["student_id"], {})[r["qid"]] = shown
    names = {x["student_id"]: x["full_name"] for x in repo.roster_groups(c, eid)}
    rate = {q: round(correct[q] / answered[q], 2) if answered[q] else None for q in qs}
    return {"exam": _public_exam(e),
            "questions": [{"id": q, "text": qs[q]["text"], "answered": answered[q], "correct": correct[q], "rate": rate[q],
                           "wrong": [{"value": v, "n": n} for v, n in sorted(wrong_values[q].items(), key=lambda w: -w[1])[:3]]}
                          for q in sorted(qs, key=lambda q: 2.0 if rate[q] is None else float(rate[q] or 0))],   # hardest first
            "pairs": [{**p, "a_name": names.get(p["a"]), "b_name": names.get(p["b"])} for p in domain.similar_pairs(wrong)[:50]]}


jobs.periodic("exam.autosubmit", timedelta(minutes=1), autosubmit)
