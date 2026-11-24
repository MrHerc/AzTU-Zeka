"""The exam core (tasks/todo.md, Task 26). No I/O.

An exam's window is entered in the university's local time and stored in UTC: 10:00-12:00 in Baku opens at
06:00:00+00:00. A student's form is drawn from the exam pool by the exam's plan (how many questions of which difficulty
or topic) with a seed of the exam's secret and the student, so it is the same every time it is made and differs between
students; question order and the options of a multiple-choice question are shuffled. A student sees only the keys in
``PUBLIC``: never the answer, the explanation or a score of a question.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import random
import re
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from decimal import ROUND_HALF_UP, Decimal

from ...core.i18n import E

KINDS = ("main", "retake", "individual")          # əsas | təkrar imtahan | fərdi vaxt
PROTECTION = ("open", "seb")
PUBLIC = ("id", "qtype", "text", "options", "unit")
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$", re.ASCII)


def to_utc(day: date, hhmm: str, zone: tzinfo | None) -> datetime:
    """A local wall time of the university as an aware UTC time. Without a zone database (a Windows demo without
    tzdata; prod refuses to start) the wall time is the computer's own, as clock.local() takes it."""
    wall = datetime.combine(day, time.fromisoformat(hhmm))
    return (wall.replace(tzinfo=zone) if zone else wall.astimezone()).astimezone(timezone.utc)


def exam_input(body, zone: tzinfo | None) -> tuple[dict, dict | None]:
    """title, kind, day (YYYY-MM-DD), start and end (HH:MM local), duration_min, plan, protection, allowed_cidrs."""
    title = " ".join(str(body.get("title") or "").split())
    if not 2 <= len(title) <= 200:                  # as short as a syllabus component name (F4)
        return {}, E("İmtahanın adı 2–200 simvol olmalıdır")
    kind = body.get("kind") or "main"
    if kind not in KINDS:
        return {}, E("İmtahanın növü əsas, təkrar və ya fərdi vaxt olmalıdır")
    try:
        day = date.fromisoformat(str(body.get("day") or ""))
    except ValueError:
        return {}, E("«{field}» sahəsində tarix İİİİ-AA-GG formatında olmalıdır", field="day")
    start, end = body.get("start"), body.get("end")
    if not (isinstance(start, str) and HHMM.fullmatch(start) and isinstance(end, str) and HHMM.fullmatch(end)) or start >= end:
        return {}, E("Keçirilmə vaxtının başlanğıcı və sonu SS:DD formatında olmalı, son vaxt başlanğıcdan sonra olmalıdır")
    duration = body.get("duration_min")
    window = (datetime.combine(day, time.fromisoformat(end)) - datetime.combine(day, time.fromisoformat(start))).seconds // 60
    if not isinstance(duration, int) or isinstance(duration, bool) or not 5 <= duration <= window:
        return {}, E("Müddət 5 dəqiqə ilə imtahanın keçirilmə vaxtının uzunluğu ({n} dəq.) arasında olmalıdır", n=window)
    plan, problem = plan_input(body.get("plan"))
    if problem:
        return {}, problem
    protection = body.get("protection") or "open"
    if protection not in PROTECTION:
        return {}, E("Qoruma rejimi açıq və ya SEB olmalıdır")
    cidrs = body.get("allowed_cidrs") or []
    if not isinstance(cidrs, list) or len(cidrs) > 50:
        return {}, E("Şəbəkə siyahısında ən çox 50 ünvan bloku ola bilər")
    try:
        cidrs = [str(ipaddress.ip_network(str(x), strict=False)) for x in cidrs]
    except ValueError:
        return {}, E("Şəbəkə siyahısında ünvan bloku düzgün deyil (məs. 10.0.0.0/24)")
    return {"title": title, "kind": kind, "opens_at": to_utc(day, start, zone).isoformat(), "closes_at": to_utc(day, end, zone).isoformat(),
            "duration_min": duration, "plan": plan, "protection": protection, "allowed_cidrs": cidrs}, None


def plan_input(plan) -> tuple[list[dict], dict | None]:
    """[{difficulty or None, topic or None, count}]: how many exam questions of which kind a form holds."""
    if not isinstance(plan, list) or not 1 <= len(plan) <= 20:
        return [], E("İmtahan planında 1 ilə 20 arasında bənd olmalıdır")
    out = []
    for p in plan:
        count = p.get("count") if isinstance(p, dict) else None
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 100:
            return [], E("Plan bəndinin sual sayı 1 ilə 100 arasında olmalıdır")
        out.append({"difficulty": (str(p.get("difficulty")).strip()[:40] or None) if p.get("difficulty") else None,
                    "topic": (str(p.get("topic")).strip()[:200] or None) if p.get("topic") else None, "count": count})
    return out, None


def _fits(q: dict, item: dict) -> bool:
    return (not item["difficulty"] or q.get("difficulty") == item["difficulty"]) and (not item["topic"] or q.get("topic") == item["topic"])


def _assign(pool: list[dict], plan: list[dict], rng: random.Random) -> list[list[dict]] | None:
    """Questions for every item of the plan, each question used once, or None when no such choice exists. The items
    may overlap (a difficulty and a topic): an augmenting-path matching finds a choice whenever one exists, so a plan
    accepted at creation never fails a student at start (Checkpoint D, T-5). The candidates are tried in the seed's
    order, so each student gets their own questions and the same seed gives the same ones."""
    order = sorted(pool, key=lambda q: q["id"])
    rng.shuffle(order)
    cand = [[q for q in order if _fits(q, item)] for item in plan]
    slots = [i for i, item in enumerate(plan) for _ in range(item["count"])]
    held: dict[int, int] = {}                 # question id -> slot
    slot_q: dict[int, dict] = {}              # slot -> question
    for s in range(len(slots)):
        came: dict[int, tuple[int, dict]] = {}   # question id -> (the slot that reached it, the question)
        frontier, seen, found = [s], {s}, None
        while frontier and found is None:
            nxt = []
            for sl in frontier:
                for q in cand[slots[sl]]:
                    if q["id"] in came:
                        continue
                    came[q["id"]] = (sl, q)
                    if q["id"] not in held:
                        found = q
                        break
                    if held[q["id"]] not in seen:
                        seen.add(held[q["id"]])
                        nxt.append(held[q["id"]])
                if found is not None:
                    break
            frontier = nxt
        if found is None:
            return None
        step: dict | None = found
        while step is not None:              # walk the path back: each slot takes the question it reached
            sl, _ = came[step["id"]]
            before = slot_q.get(sl)
            slot_q[sl], held[step["id"]] = step, sl
            step = before
    return [[slot_q[s] for s in range(len(slots)) if slots[s] == i] for i in range(len(plan))]


def plan_problem(pool: list[dict], plan: list[dict]) -> dict | None:
    """Whether the pool holds enough exam questions for every item of the plan, each question used once."""
    for item in plan:
        have = sum(1 for q in pool if _fits(q, item))
        if have < item["count"]:
            return E("Sual bankında bu plan üçün kifayət qədər imtahan sualı yoxdur: tələb olunan {need}, mövcud {have}", need=item["count"], have=have)
    if _assign(pool, plan, random.Random(0)) is None:
        need = sum(item["count"] for item in plan)
        have = len({q["id"] for q in pool if any(_fits(q, item) for item in plan)})
        return E("Sual bankında bu plan üçün kifayət qədər imtahan sualı yoxdur: tələb olunan {need}, mövcud {have}", need=need, have=have)
    return None


def seed(secret: str, exam_id: int, student_id: int) -> str:
    return hashlib.sha256(f"{secret}:{exam_id}:{student_id}".encode()).hexdigest()


def build_form(pool: list[dict], plan: list[dict], seed_hex: str) -> list[dict]:
    """[{qid, order}] for one student: the plan's questions in a shuffled order, a multiple-choice question's options
    shuffled too (``order[i]`` is the original index of the option shown i-th). The same seed gives the same form."""
    rng = random.Random(seed_hex)
    picked = _assign(pool, plan, rng)
    if picked is None:
        raise ValueError("Sual bankı artıq imtahan planı üçün kifayət etmir")
    chosen = [q for group in picked for q in group]
    rng.shuffle(chosen)
    out = []
    for q in chosen:
        opts = q["options"] if isinstance(q["options"], list) else json.loads(q["options"] or "[]")
        order = list(range(len(opts)))
        if q["qtype"] == "mcq":
            rng.shuffle(order)
        out.append({"qid": q["id"], "order": order})
    return out


def public(q: dict, order: list[int]) -> dict:
    """The question as a student sees it: only the keys in PUBLIC, the options in the form's order."""
    opts = q["options"] if isinstance(q["options"], list) else json.loads(q["options"] or "[]")
    shown = {**q, "options": [opts[i] for i in order] if order and len(order) == len(opts) else opts}
    return {k: shown.get(k) for k in PUBLIC}


def original_value(q: dict, order: list[int], value):
    """A multiple-choice answer given as the index of the shown option, as the index of the original option."""
    if q["qtype"] == "mcq" and isinstance(value, int) and not isinstance(value, bool) and 0 <= value < len(order):
        return order[value]
    return value


def deadline(started: datetime, duration_min: int, closes: datetime) -> datetime:
    """An attempt ends after its duration or when the exam window closes, whichever comes first."""
    return min(started + timedelta(minutes=duration_min), closes)


# ---------------------------------------------------------------- the proctor panel (Task 29)
# action -> needs minutes. Every action needs a reason; extending and reopening also say by how many minutes.
ACTIONS = {"extend": True, "pause": False, "resume": False, "end": False, "reopen": True, "unlock": False}
# What the exam page reports by itself (the board counts them); everything else a client sends is refused.
SIGNALS = ("blur", "fullscreen_exit", "reconnect")
SIGNAL_CAP = 300                                  # per student and exam: a looping page cannot flood the log
REFUSAL_CAP = 10                                  # refusal events per student, exam and kind (Checkpoint D, TM-11): the 403 stays


def ip_allowed(cidrs: list[str], ip: str) -> bool:
    """An empty list allows every address; otherwise the address must be in one of the blocks."""
    if not cidrs:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in ipaddress.ip_network(c, strict=False) for c in cidrs)


def proctor_input(action: str, body) -> tuple[dict, dict | None]:
    """{reason, minutes}: the reason is required (3-300 characters); minutes 1-240 for extend and reopen."""
    if action not in ACTIONS:
        return {}, E("Naməlum əməliyyat")
    reason = " ".join(str(body.get("reason") or "").split())[:300]
    if len(reason) < 3:
        return {}, E("Əməliyyatın səbəbini yazın")
    minutes = body.get("minutes")
    if ACTIONS[action]:
        if not isinstance(minutes, int) or isinstance(minutes, bool) or not 1 <= minutes <= 240:
            return {}, E("Dəqiqə sayı 1 ilə 240 arasında olmalıdır")
    else:
        minutes = None
    return {"reason": reason, "minutes": minutes}, None


def resumed_deadline(deadline: datetime, paused_at: datetime, now: datetime) -> datetime:
    """A paused attempt's clock stops: resuming moves the deadline by the time it stood still."""
    return deadline + max(timedelta(0), now - paused_at)


def remaining(deadline: datetime, now: datetime, paused_at: datetime | None) -> int:
    """Seconds left by the server's clock; a paused attempt shows what was left when it stopped."""
    return max(0, int((deadline - (paused_at or now)).total_seconds()))


# ---------------------------------------------------------------- the hash chain (Task 30)
# Every exam has one chain of events ordered by seq (1..N, no gap): hash = sha256(prev_hash + the canonical event),
# the first event's prev_hash is GENESIS. Changing or removing any stored event breaks a link or the head; the head
# (the root) leaves the database in the closing protocol and the closing e-mail.
GENESIS = "0" * 64


def canonical_event(exam_id: int, seq: int, kind: str, actor_id: int | None, student_id: int | None, data: dict, at: str) -> str:
    return json.dumps({"exam_id": exam_id, "seq": seq, "kind": kind, "actor_id": actor_id, "student_id": student_id, "data": data, "at": at},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def link(prev_hash: str, canonical: str) -> str:
    return hashlib.sha256((prev_hash + canonical).encode()).hexdigest()


def answers_digest(answers: Mapping[int, str | None]) -> str:
    """SHA-256 of the canonical JSON of the (qid, stored value) pairs ordered by qid: what a submission froze."""
    pairs = [[qid, answers[qid]] for qid in sorted(answers)]
    return hashlib.sha256(json.dumps(pairs, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def chain_break(events: list[dict]) -> dict | None:
    """The first broken link of a chain (events ordered by seq, ``data`` as stored text), or None. A missing seq, a
    prev_hash that is not the previous hash, and a hash that does not match the event are each a break."""
    prev = GENESIS
    for i, ev in enumerate(events, start=1):
        if ev["seq"] != i:
            return {"seq": i, "problem": "missing"}
        if ev["prev_hash"] != prev:
            return {"seq": i, "problem": "prev_hash"}
        try:
            data = json.loads(ev["data"] or "{}")
        except ValueError:
            return {"seq": i, "problem": "data"}
        if link(prev, canonical_event(ev["exam_id"], ev["seq"], ev["kind"], ev["actor_id"], ev["student_id"], data, ev["at"])) != ev["hash"]:
            return {"seq": i, "problem": "hash"}
        prev = ev["hash"]
    return None


# ---------------------------------------------------------------- release to the journal (Task 30)
RESULTS = ("passed", "exam_min", "pass_mark", "not_admitted", "absent")    # keçdi | imtahan < minimum | cəm < keçid | buraxılmayıb | gəlməyib


def scale(raw: float, raw_max: float, component_max: float) -> float:
    """A raw exam score as points of the journal's exam component: raw / raw_max x component_max, rounded half up to one
    decimal. This is the only rounding rule of an exam score (so 16.95 is 17.0 and 16.94 is 16.9)."""
    if not raw_max or raw_max <= 0:
        return 0.0
    points = Decimal(str(raw)) * Decimal(str(component_max)) / Decimal(str(raw_max))
    return float(points.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def points(value: float) -> float:
    """A score entered by hand, by the same rule as ``scale``: half up to one decimal."""
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def result_status(roster: str | None, attempt: str | None, outcome: dict | None) -> str:
    """One student's result of a released exam: not admitted, absent, or what the journal's outcome says."""
    if roster == "excluded":
        return "not_admitted"
    if attempt not in ("graded",) or not outcome or outcome.get("passed") is None:
        return "absent"
    return "passed" if outcome["passed"] else (outcome.get("reason") or "pass_mark")


def similar_pairs(wrong: dict[int, dict[int, str]], at_least: int = 2) -> list[dict]:
    """Pairs of students who gave the same wrong answer to at least ``at_least`` of the same questions, most first. A
    signal for the teacher to look at, never a verdict: it is shown to the course's teachers only."""
    out = []
    ids = sorted(wrong)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            same = sorted(q for q, v in wrong[a].items() if wrong[b].get(q) == v)
            if len(same) >= at_least:
                out.append({"a": a, "b": b, "same": len(same), "questions": same})
    return sorted(out, key=lambda p: (-p["same"], p["a"], p["b"]))
