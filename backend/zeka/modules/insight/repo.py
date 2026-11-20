"""SQL of the measured indicators and the accreditation evidence (tasks/todo.md, Task 39).

``since`` and ``until`` (both included) are ISO times in the form each table stores: the university's wall clock (store.now) for events,
lessons, requests and messages, aware UTC for exams and job runs. Per-week rows carry ``w``: 0 is the 7 days before
``until``, 1 the 7 before those, and so on.
"""
from __future__ import annotations

from ...core.perms import STAFF_ROLES
from ...legacy.store import row, rows

WEEK = "CAST((julianday(?) - julianday({t})) / 7 AS INTEGER)"
LESSON_END = "l.day || 'T' || l.\"end\""


def _n(c, sql: str, args: tuple = ()) -> int:
    return row(c, sql, args)["n"]


def accounts(c, role: str) -> int:
    return row(c, "SELECT COUNT(*) AS n FROM users WHERE role=? AND status='active'", (role,))["n"]


def active_weekly(c, role: str, since: str, until: str) -> list[dict]:
    """Distinct users with an event per week, in sessions acting in ``role``."""
    return rows(c, f"SELECT {WEEK.format(t='created_at')} AS w, COUNT(DISTINCT user_id) AS n FROM events "
                   "WHERE created_at>=? AND created_at<=? AND role=? GROUP BY w", (until, since, until, role))


def active_by_role(c, since: str, until: str) -> list[dict]:
    return rows(c, "SELECT role, COUNT(DISTINCT user_id) AS n FROM events WHERE created_at>=? AND created_at<=? "
                   "GROUP BY role ORDER BY n DESC, role", (since, until))


def lessons_weekly(c, since: str, until: str, cutover: str | None = None) -> list[dict]:
    """Lessons that ended in the period and were not cancelled (``held``), and of them those with an attendance row
    (``filled``), per week. A lesson on or before the journal's cut-over date is closed for marking in Zəka (Task 20) and
    does not count."""
    return rows(c, f"SELECT {WEEK.format(t=LESSON_END)} AS w, COUNT(*) AS held, "
                   "SUM(EXISTS(SELECT 1 FROM attendance a WHERE a.lesson_id=l.id)) AS filled FROM lessons l "
                   f"WHERE l.day>=? AND l.day<=? AND l.day>? AND {LESSON_END}>=? AND {LESSON_END}<=? AND l.status<>'cancelled' GROUP BY w",
                (until, since[:10], until[:10], cutover or "", since, until))


def requests_weekly(c, since: str, until: str) -> list[dict]:
    """Requests closed (ready or rejected) in the period, per week: how many, their hours from filing to closing, how
    many had a due time and how many of those closed by it."""
    return rows(c, f"SELECT {WEEK.format(t='updated_at')} AS w, COUNT(*) AS n, "
                   "SUM((julianday(updated_at) - julianday(created_at)) * 24) AS hours, SUM(due_at IS NOT NULL) AS due, "
                   "SUM(due_at IS NOT NULL AND updated_at<=due_at) AS in_time FROM requests "
                   "WHERE status IN ('ready','rejected') AND updated_at>=? AND updated_at<=? GROUP BY w", (until, since, until))


def answers_weekly(c, since: str, until: str) -> list[dict]:
    """Answers of the AI tutor and the campus assistant per week, and those citing at least one source."""
    return rows(c, f"SELECT {WEEK.format(t='created_at')} AS w, COUNT(*) AS n, SUM(COALESCE(cites,'[]') NOT IN ('','[]')) AS cited "
                   "FROM messages WHERE created_at>=? AND created_at<=? AND role='assistant' AND channel IN ('tutor','campus') "
                   "GROUP BY w", (until, since, until))


def exams_weekly(c, since_utc: str, until_utc: str) -> list[dict]:
    """Exams opened in the period, per week."""
    return rows(c, f"SELECT {WEEK.format(t='opened_at')} AS w, COUNT(*) AS n FROM exams WHERE opened_at>=? AND opened_at<=? "
                   "GROUP BY w", (until_utc, since_utc, until_utc))


def academy_completions(c) -> list[dict]:
    """The completed AI Academy modules of active teachers: who and when."""
    return rows(c, "SELECT p.user_id, p.completed_at FROM academy_progress p JOIN users u ON u.id=p.user_id "
                   "WHERE u.role='teacher' AND u.status='active' AND p.status='completed' AND p.completed_at IS NOT NULL")


def evidence_counts(c, since: str, until: str, since_utc: str) -> dict:
    """The live counts of the accreditation evidence page, the period ones over [since, until)."""
    staff = row(c, "SELECT COUNT(*) AS n, SUM(totp_enabled_at IS NOT NULL) AS mfa FROM users WHERE status='active' "
                   f"AND role IN ({','.join('?' * len(STAFF_ROLES))})", STAFF_ROLES)
    held = _n(c, f"SELECT COUNT(*) AS n FROM lessons l WHERE l.day>=? AND l.day<=? AND {LESSON_END}>=? AND {LESSON_END}<=? "
                 "AND l.status<>'cancelled'", (since[:10], until[:10], since, until))
    return {
        "courses": _n(c, "SELECT COUNT(*) AS n FROM courses"),
        "materials": _n(c, "SELECT COUNT(*) AS n FROM materials"),
        "assignments": _n(c, "SELECT COUNT(*) AS n FROM assignments"),
        "lessons_held": held,
        "exams": _n(c, "SELECT COUNT(*) AS n FROM exams WHERE opened_at>=?", (since_utc,)),
        "student_events": _n(c, "SELECT COUNT(*) AS n FROM events WHERE created_at>=? AND created_at<=? AND role='student'", (since, until)),
        "attendance_marks": _n(c, "SELECT COUNT(*) AS n FROM attendance WHERE marked_at>=? AND marked_at<=?", (since, until)),
        "services": _n(c, "SELECT COUNT(*) AS n FROM request_types WHERE enabled=1"),
        "modules": _n(c, "SELECT COUNT(DISTINCT module) AS n FROM events WHERE created_at>=? AND created_at<=?", (since, until)),
        "roles": _n(c, "SELECT COUNT(*) AS n FROM (SELECT role FROM users WHERE status='active' UNION SELECT role FROM role_grants)"),
        "grants": _n(c, "SELECT COUNT(*) AS n FROM role_grants"),
        "students": accounts(c, "student"),
        "students_active": _n(c, "SELECT COUNT(DISTINCT user_id) AS n FROM events WHERE created_at>=? AND created_at<=? AND role='student'",
                               (since, until)),
        "teachers": accounts(c, "teacher"),
        "teachers_active": _n(c, "SELECT COUNT(DISTINCT user_id) AS n FROM events WHERE created_at>=? AND created_at<=? AND role='teacher'",
                               (since, until)),
        "staff": staff["n"],
        "staff_mfa": staff["mfa"] or 0,
        "status_reported": _n(c, "SELECT COUNT(*) AS n FROM student_status_events WHERE reported_at IS NOT NULL"),
        "api_keys": _n(c, "SELECT COUNT(*) AS n FROM api_tokens WHERE revoked_at IS NULL"),
        "jobs_ok": _n(c, "SELECT COUNT(*) AS n FROM job_runs WHERE status='ok' AND started_at>=?", (since_utc,)),
    }
