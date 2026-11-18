"""Roles and permissions (tasks/todo.md, Task 13). Pure data: which role holds which permission.

A user has one primary role (``users.role``) and may hold more through ``role_grants`` (with a scope such as a faculty).
A session acts in one of them at a time (``sessions.role``). Routes declare either ``roles=(...)`` or ``perm="..."``;
the router turns a permission into the roles that hold it, so both are checked the same way.

Club leaders and moderators are not roles: a club leader is a field of the club (Task 35, an object-level check), and
moderation is the permissions below.
"""
from __future__ import annotations

ROLES = ("student", "teacher", "dept_head", "office", "academic_office", "proctor", "leader", "admin")
STAFF_ROLES = tuple(r for r in ROLES if r != "student")

# Permission -> roles holding it by default. The owner confirms the moderation split at Checkpoint B (SPEC, Open Q 24).
PERMS: dict[str, tuple[str, ...]] = {
    "qa.moderate": ("office", "admin"),
    "community.moderate": ("office", "admin"),            # plus the leader of a club, inside that club (Task 35)
    "roles.grant": ("admin",),
    "users.manage": ("admin",),
    "directory.read": STAFF_ROLES,                         # structure lists (Task 15)
    "directory.manage": ("admin", "academic_office"),      # create, change, deactivate structure and terms
    # Task 15, slice 2. Who enters status orders on screen is the owner's decision (SPEC, Open Q 17); until then only the
    # academic office. Reading them: the registry offices, leadership, and a dean's office for its own faculty.
    "students.status": ("academic_office",),
    "students.status.read": ("academic_office", "admin", "office", "leader"),
    "timetable.manage": ("admin", "academic_office"),     # timetable rows, making lessons, cancelling and moving them (Task 19)
    # Task 20: attendance after the teacher's window, imported rows and opening balances, a lesson's substitute teacher;
    # a department head scoped to departments acts on their courses only
    "journal.correct": ("dept_head", "admin"),
}

SCOPE_TYPES = ("faculty", "department", "course")


def roles_for(perm: str) -> tuple[str, ...]:
    """The roles holding ``perm``; an unknown permission is a programming error, caught when the route is declared."""
    if perm not in PERMS:
        raise KeyError(f"unknown permission {perm!r}: add it to zeka.core.perms.PERMS")
    return PERMS[perm]


def has(role: str, perm: str) -> bool:
    return role in PERMS.get(perm, ())
