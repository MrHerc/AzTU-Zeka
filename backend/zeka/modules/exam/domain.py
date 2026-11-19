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
from datetime import date, datetime, time, timedelta, timezone, tzinfo

from ...core.i18n import E

KINDS = ("main", "retake", "individual")          # əsas | təkrar | fərdi vaxt
PROTECTION = ("open", "seb")
PUBLIC = ("id", "qtype", "text", "options", "unit")
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$", re.ASCII)


def to_utc(day: date, hhmm: str, zone: tzinfo | None) -> datetime:
    """A local wall time of the university as an aware UTC time (no zone database: taken as UTC)."""
    local = datetime.combine(day, time.fromisoformat(hhmm)).replace(tzinfo=zone or timezone.utc)
    return local.astimezone(timezone.utc)


def exam_input(body, zone: tzinfo | None, pool_size: int) -> tuple[dict, dict | None]:
    """title, kind, day (YYYY-MM-DD), start and end (HH:MM local), duration_min, plan, protection, allowed_cidrs."""
    title = " ".join(str(body.get("title") or "").split())
    if not 3 <= len(title) <= 200:
        return {}, E("İmtahanın adı 3–200 simvol olmalıdır")
    kind = body.get("kind") or "main"
    if kind not in KINDS:
        return {}, E("İmtahanın növü əsas, təkrar və ya fərdi vaxt olmalıdır")
    try:
        day = date.fromisoformat(str(body.get("day") or ""))
    except ValueError:
        return {}, E("«{field}» sahəsində tarix İİİİ-AA-GG formatında olmalıdır", field="day")
    start, end = body.get("start"), body.get("end")
    if not (isinstance(start, str) and HHMM.fullmatch(start) and isinstance(end, str) and HHMM.fullmatch(end)) or start >= end:
        return {}, E("Pəncərənin başlanğıcı və sonu SS:DD formatında olmalı, sonu başlanğıcdan sonra gəlməlidir")
    duration = body.get("duration_min")
    window = (datetime.combine(day, time.fromisoformat(end)) - datetime.combine(day, time.fromisoformat(start))).seconds // 60
    if not isinstance(duration, int) or isinstance(duration, bool) or not 5 <= duration <= window:
        return {}, E("Müddət 5 dəqiqə ilə pəncərənin uzunluğu ({n} dəq.) arasında olmalıdır", n=window)
    plan, problem = plan_input(body.get("plan"))
    if problem:
        return {}, problem
    protection = body.get("protection") or "open"
    if protection not in PROTECTION:
        return {}, E("Qoruma rejimi açıq və ya SEB olmalıdır")
    cidrs = body.get("allowed_cidrs") or []
    if not isinstance(cidrs, list) or len(cidrs) > 50:
        return {}, E("Şəbəkə siyahısı ən çox 50 ünvan blokudur")
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


def plan_problem(pool: list[dict], plan: list[dict]) -> dict | None:
    """Whether the pool holds enough exam questions for every item of the plan (each question used once)."""
    used: set[int] = set()
    for item in plan:
        free = [q["id"] for q in pool if q["id"] not in used and _fits(q, item)]
        if len(free) < item["count"]:
            return E("Hovuzda bu plan üçün kifayət qədər imtahan sualı yoxdur: lazımdır {need}, var {have}", need=item["count"], have=len(free))
        used.update(free[:item["count"]])
    return None


def seed(secret: str, exam_id: int, student_id: int) -> str:
    return hashlib.sha256(f"{secret}:{exam_id}:{student_id}".encode()).hexdigest()


def build_form(pool: list[dict], plan: list[dict], seed_hex: str) -> list[dict]:
    """[{qid, order}] for one student: the plan's questions in a shuffled order, a multiple-choice question's options
    shuffled too (``order[i]`` is the original index of the option shown i-th). The same seed gives the same form."""
    rng = random.Random(seed_hex)
    chosen: list[dict] = []
    used: set[int] = set()
    for item in plan:
        free = sorted((q for q in pool if q["id"] not in used and _fits(q, item)), key=lambda q: q["id"])
        picked = rng.sample(free, item["count"])
        used.update(q["id"] for q in picked)
        chosen += picked
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
