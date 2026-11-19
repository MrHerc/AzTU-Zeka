"""Rules of the e-mail outbox (tasks/todo.md, Task 36, slice 2). No I/O.

Each in-app notification kind may also go by e-mail. A person turns e-mail off or on per kind; the kinds that would
flood an inbox (news, events, practice tests, the academy, Radar digests) start off, the rest start on. A failed
attempt is tried again after 1, 2, 4, ... minutes (at most six hours) and given up after ``MAX_ATTEMPTS`` (about three days).
"""
from __future__ import annotations

from datetime import timedelta

from ...core.i18n import E, S_

# kind -> label (the notification kinds that exist today; store.notify's second argument)
KINDS = {"request": S_("Müraciətlər"), "message": S_("Dekanlıqdan mesajlar"), "support": S_("Dəstək sorğuları"),
         "exam": S_("İmtahanlar"), "assignment": S_("Tapşırıqlar"), "attendance": S_("Davamiyyət"), "schedule": S_("Dərs cədvəli"),
         "syllabus": S_("Sillabus"), "news": S_("Xəbərlər"), "event": S_("Tədbirlər"), "quiz": S_("Testlər"),
         "academy": S_("AI Akademiya"), "radar": S_("Zəka Radar"), "question": S_("Tələbə sualları"),
         "answer": S_("Suallarıma cavablar"), "plan": S_("Dəstək planı")}
OFF_BY_DEFAULT = frozenset({"news", "event", "quiz", "academy", "radar", "plan"})   # plan: a Radar support plan, like radar (CR-9)
MAX_ATTEMPTS = 20                                 # about three days of waits (Checkpoint D, T-7): an outage does not lose mail


def wants_email(prefs: dict, kind: str) -> bool:
    chosen = (prefs.get("email") or {}).get(kind) if isinstance(prefs.get("email"), dict) else None
    return (kind not in OFF_BY_DEFAULT) if chosen is None else bool(chosen)


def backoff(attempts: int) -> timedelta:
    """The wait after the ``attempts``-th failed attempt: 1, 2, 4, ... minutes, at most six hours."""
    return timedelta(minutes=min(2 ** max(0, attempts - 1), 360))


def prefs_input(body) -> tuple[dict, dict | None]:
    """{kind: bool} for known kinds only."""
    email = body.get("email")
    if not isinstance(email, dict) or not all(k in KINDS and isinstance(v, bool) for k, v in email.items()):
        return {}, E("Bildiriş ayarları düzgün deyil")
    return email, None
