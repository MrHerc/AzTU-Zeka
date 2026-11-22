"""SQL of the integration module (Task 16). Table and column names are constants of importer.TARGETS; values are bound."""
from __future__ import annotations

from ...legacy.store import iso, now, row, rows


def links(c, kind: str, source: str) -> dict[str, dict]:
    return {r["source_id"]: r for r in rows(c, "SELECT source_id, row_id, source_hash FROM import_links WHERE kind=? AND source_system=?",
                                            (kind, source))}


def links_in(c, kind: str, source: str, ids: list[str]) -> dict[str, dict]:
    """The links of the given source ids only (a kind with too many rows to read whole: lesson records, Task 38)."""
    out: dict[str, dict] = {}
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        for r in rows(c, "SELECT source_id, row_id, source_hash FROM import_links WHERE kind=? AND source_system=? "
                         f"AND source_id IN ({','.join('?' * len(part))})", (kind, source, *part)):  # nosec B608 - placeholders only
            out[r["source_id"]] = r
    return out


def marks_of(c, lesson_id: int) -> list[dict]:
    return rows(c, "SELECT rowid AS _k, lesson_id, user_id, status FROM attendance WHERE lesson_id=?", (lesson_id,))


def table(c, name: str, cols: tuple[str, ...], key: str = "id") -> dict[int, dict]:
    """Every row of a target table with the given columns, by id (by rowid for enrollments)."""
    return {r["_k"]: r for r in rows(c, f"SELECT {key} AS _k, {', '.join(cols)} FROM {name}")}  # nosec B608 - constants


def unit_groups(c) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for r in rows(c, "SELECT unit_id, group_id FROM teaching_unit_groups ORDER BY unit_id, group_id"):
        out.setdefault(r["unit_id"], []).append(r["group_id"])
    return out


def by_column(c, name: str, col: str) -> dict:
    return {r["v"]: r["id"] for r in rows(c, f"SELECT {col} AS v, id FROM {name} WHERE {col} IS NOT NULL")}  # nosec B608


def active_courses(c) -> list[dict]:
    """The active courses with their term, for matching a form's subjects (Forma №3)."""
    return rows(c, "SELECT co.id, co.name, t.name term, t.code term_code FROM courses co "
                   "LEFT JOIN academic_terms t ON t.id=co.term_id WHERE co.active=1")


def insert(c, name: str, values: dict) -> int:
    return c.execute(f"INSERT INTO {name}({', '.join(values)}) VALUES({', '.join('?' * len(values))})",  # nosec B608 - constants
                     tuple(values.values())).lastrowid


def update(c, name: str, rid: int, values: dict, key: str = "id"):
    c.execute(f"UPDATE {name} SET {', '.join(f'{k}=?' for k in values)} WHERE {key}=?", (*values.values(), rid))  # nosec B608


def one(c, name: str, cols: tuple[str, ...], rid: int, key: str = "id"):
    """One target row as it is now (re-read inside the write lock)."""
    return row(c, f"SELECT {', '.join(cols)} FROM {name} WHERE {key}=?", (rid,))  # nosec B608 - constants


def groups_of(c, unit_id: int) -> list[int]:
    return [r["group_id"] for r in rows(c, "SELECT group_id FROM teaching_unit_groups WHERE unit_id=? ORDER BY group_id", (unit_id,))]


def set_groups(c, unit_id: int, group_ids: list[int]):
    c.execute("DELETE FROM teaching_unit_groups WHERE unit_id=?", (unit_id,))
    c.executemany("INSERT INTO teaching_unit_groups(unit_id,group_id) VALUES(?,?)", [(unit_id, g) for g in group_ids])


def link(c, kind: str, source: str, source_id: str, row_id: int, source_hash: str):
    c.execute("INSERT INTO import_links(kind,source_system,source_id,row_id,source_hash,imported_at) VALUES(?,?,?,?,?,?) "
              "ON CONFLICT(kind,source_system,source_id) DO UPDATE SET row_id=excluded.row_id, source_hash=excluded.source_hash, "
              "imported_at=excluded.imported_at", (kind, source, source_id, row_id, source_hash, iso(now())))


# ---------------------------------------------------------------- activation codes
def faculty_students(c, faculty_id: int) -> list:
    """Active students of a faculty who have no way in yet: no password, no second factor, no provider link (a code
    for any other account would be a second way in that skips what the account already has)."""
    return rows(c, "SELECT u.id, u.username, u.full_name, u.student_no, g.name grp FROM users u JOIN study_groups g ON g.id=u.group_id "
                   "WHERE g.faculty_id=? AND u.role='student' AND u.status='active' AND u.password_hash IS NULL "
                   "AND u.totp_enabled_at IS NULL AND NOT EXISTS (SELECT 1 FROM sso_identities s WHERE s.user_id=u.id) "
                   "ORDER BY g.name, u.full_name, u.id", (faculty_id,))


def revoke_codes(c, user_ids: list[int], t: str):
    c.executemany("UPDATE activation_codes SET revoked_at=? WHERE user_id=? AND used_at IS NULL AND revoked_at IS NULL",
                  [(t, u) for u in user_ids])


def add_codes(c, items: list[tuple[int, str]], t: str, expires: str):
    c.executemany("INSERT INTO activation_codes(user_id,code_hash,created_at,expires_at) VALUES(?,?,?,?)",
                  [(u, h, t, expires) for u, h in items])


def code(c, code_hash: str):
    return row(c, "SELECT a.*, u.student_no, u.username, u.status, u.role, u.password_hash, u.totp_enabled_at, "
                  "EXISTS (SELECT 1 FROM sso_identities s WHERE s.user_id=u.id) AS sso FROM activation_codes a "
                  "JOIN users u ON u.id=a.user_id WHERE a.code_hash=?", (code_hash,))


def spend_code(c, code_id: int, t: str) -> bool:
    return c.execute("UPDATE activation_codes SET used_at=? WHERE id=? AND used_at IS NULL AND revoked_at IS NULL",
                     (t, code_id)).rowcount == 1
