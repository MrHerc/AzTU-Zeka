"""Assignments (tasks/todo.md, Task 22). No I/O.

A teacher sets an assignment of a course: text, due time, maximum score, the grade component it counts toward and what a
late submission is ('mark': accepted and marked late, 'refuse': not accepted). A graded submission's score goes to that
component: the sum of the student's graded assignments of the component, never above the component's maximum.
"""
from __future__ import annotations

import re

from ...core.i18n import E

LATE_RULES = ("mark", "refuse")
DUE = re.compile(r"^\d{4}-\d{2}-\d{2}T([01]\d|2[0-3]):[0-5]\d$")        # local university time, minutes


def assignment_input(body, components: dict[str, float]) -> tuple[dict, dict | None]:
    """title, body, due_at, max_score, component, late_rule; ``components``: {name: maximum} the score may count toward."""
    title = " ".join(str(body.get("title") or "").split())
    text = str(body.get("body") or "").strip()
    if not 2 <= len(title) <= 200:
        return {}, E("«{field}» sahəsi 2–200 simvol olmalıdır", field="title")
    if not 1 <= len(text) <= 20000:
        return {}, E("Tapşırığın mətnini yazın")
    due = body.get("due_at")
    if not (isinstance(due, str) and DUE.fullmatch(due)):
        return {}, E("Son tarix İİİİ-AA-GGTSS:DD formatında olmalıdır")
    comp = body.get("component")
    if comp not in components:
        return {}, E("Komponent fənnin sxemində yoxdur: {x}", x=str(comp))
    mx = body.get("max_score")
    if isinstance(mx, bool) or not isinstance(mx, (int, float)) or not 0 < mx <= components[comp]:
        return {}, E("Maksimum bal 0-dan böyük və komponentin maksimumundan ({n}) çox olmamalıdır", n=components[comp])
    rule = body.get("late_rule") or "mark"
    if rule not in LATE_RULES:
        return {}, E("Gecikmə qaydası: qeyd et və ya qəbul etmə")
    return {"title": title, "body": text, "due_at": due, "max_score": float(mx), "component": comp, "late_rule": rule}, None


def is_late(submitted_at: str, due_at: str) -> bool:
    """``submitted_at`` is an ISO time with seconds; ``due_at`` is to the minute and includes that minute."""
    return submitted_at[:16] > due_at


def component_total(scores: list[float], maximum: float) -> float | None:
    return round(min(sum(scores), maximum), 2) if scores else None
