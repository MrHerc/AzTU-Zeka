"""SQL of the directory module. Table and column names come from domain.ENTITIES (constants), values are bound."""
from __future__ import annotations

from ...legacy.store import iso, now, row, rows
from . import domain


def _cfg(entity: str) -> dict:
    return domain.ENTITIES[entity]


def _cols(entity: str) -> str:
    return _cfg(entity).get("columns", "*")


def page(c, entity: str, q: str, active: bool | None, filters: dict, page_no: int) -> tuple[list, int]:
    cfg = _cfg(entity)
    where: list[str] = []
    args: list = []
    if q and cfg["search"]:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(" + " OR ".join(f"{col} LIKE ? ESCAPE '\\'" for col in cfg["search"]) + ")")
        args += [like] * len(cfg["search"])
    if active is not None:
        col, on, off = domain.active_column(entity)
        where.append(f"{col}=?")
        args.append(on if active else off)
    for col, value in filters.items():           # only columns named in ENTITIES[entity]["filters"]
        where.append(f"{col}=?")
        args.append(value)
    sql_where = (" WHERE " + " AND ".join(where)) if where else ""
    total = row(c, f"SELECT COUNT(*) n FROM {cfg['table']}{sql_where}", tuple(args))["n"]  # nosec B608 - names from ENTITIES
    items = rows(c, f"SELECT {_cols(entity)} FROM {cfg['table']}{sql_where} ORDER BY {cfg['order']}, id LIMIT ? OFFSET ?",  # nosec B608
                 (*args, domain.PAGE, (page_no - 1) * domain.PAGE))
    return items, total


def get(c, entity: str, rid: int, public: bool = False):
    """The row; ``public``: only the columns an answer may carry (no password hash for a user)."""
    cols = _cols(entity) if public else "*"
    return row(c, f"SELECT {cols} FROM {_cfg(entity)['table']} WHERE id=?", (rid,))  # nosec B608 - names from ENTITIES


def taken(c, entity: str, col: str, value, exclude: int | None = None) -> bool:
    return row(c, f"SELECT 1 FROM {_cfg(entity)['table']} WHERE {col}=? AND id IS NOT ?", (value, exclude)) is not None  # nosec B608


def insert(c, entity: str, values: dict) -> int:
    t = iso(now())
    col, on, _ = domain.active_column(entity)
    values = {**values, col: on, **({"created_at": t, "updated_at": t} if _cfg(entity).get("stamps", True) else {})}
    cols = ", ".join(values)
    return c.execute(f"INSERT INTO {_cfg(entity)['table']}({cols}) VALUES({', '.join('?' * len(values))})",  # nosec B608
                     tuple(values.values())).lastrowid


def update(c, entity: str, rid: int, values: dict):
    if _cfg(entity).get("stamps", True):
        values = {**values, "updated_at": iso(now())}
    sets = ", ".join(f"{k}=?" for k in values)
    c.execute(f"UPDATE {_cfg(entity)['table']} SET {sets} WHERE id=?", (*values.values(), rid))  # nosec B608 - names from ENTITIES


def set_active(c, entity: str, rid: int, active: bool):
    col, on, off = domain.active_column(entity)
    update(c, entity, rid, {col: on if active else off})


# ---------------------------------------------------------------- teaching units, enrolments, status orders (slice 2)
def unit_groups(c, unit_id: int) -> list[int]:
    return [r["group_id"] for r in rows(c, "SELECT group_id FROM teaching_unit_groups WHERE unit_id=? ORDER BY group_id", (unit_id,))]


def set_unit_groups(c, unit_id: int, group_ids: list[int]):
    c.execute("DELETE FROM teaching_unit_groups WHERE unit_id=?", (unit_id,))
    c.executemany("INSERT INTO teaching_unit_groups(unit_id,group_id) VALUES(?,?)", [(unit_id, g) for g in group_ids])


def existing_groups(c, group_ids: list[int]) -> set[int]:
    marks = ",".join("?" * len(group_ids))
    return {r["id"] for r in rows(c, f"SELECT id FROM study_groups WHERE id IN ({marks})", tuple(group_ids))}  # nosec B608


def enrollments(c, course_id: int) -> list:
    return rows(c, "SELECT e.user_id, u.full_name, u.username, u.student_no, COALESCE(e.group_id, u.group_id) group_id, "
                   "g.name group_name, e.subgroup, e.begin_date, e.end_date FROM enrollments e JOIN users u ON u.id=e.user_id "
                   "LEFT JOIN study_groups g ON g.id=COALESCE(e.group_id, u.group_id) WHERE e.course_id=? ORDER BY u.full_name, u.id",
                (course_id,))


def enrollment(c, course_id: int, user_id: int):
    return row(c, "SELECT * FROM enrollments WHERE course_id=? AND user_id=?", (course_id, user_id))


def enroll(c, course_id: int, values: dict):
    c.execute("INSERT INTO enrollments(user_id,course_id,group_id,subgroup,begin_date) VALUES(?,?,?,?,?)",
              (values["user_id"], course_id, values["group_id"], values["subgroup"], values["begin_date"]))


def end_enrollment(c, course_id: int, user_id: int, end_date: str):
    c.execute("UPDATE enrollments SET end_date=? WHERE course_id=? AND user_id=?", (end_date, course_id, user_id))


def roster(c, course_id: int, day: str) -> list:
    """The students on the course's lesson lists on ``day``: begin_date <= day < end_date, account active."""
    return rows(c, "SELECT u.id, u.full_name, u.username, u.student_no, COALESCE(e.group_id, u.group_id) group_id, e.subgroup "
                   "FROM enrollments e JOIN users u ON u.id=e.user_id WHERE e.course_id=? AND u.status='active' "
                   "AND (e.begin_date IS NULL OR e.begin_date<=?) AND (e.end_date IS NULL OR e.end_date>?) "
                   "ORDER BY u.full_name, u.id", (course_id, day, day))


def status_events(c, student_id: int) -> list:
    return rows(c, "SELECT e.*, u.full_name entered_by_name FROM student_status_events e LEFT JOIN users u ON u.id=e.entered_by "
                   "WHERE e.student_id=? ORDER BY e.effective_date, e.id", (student_id,))


def add_status_event(c, student_id: int, values: dict, from_group: int | None, by: int) -> int:
    return c.execute("INSERT INTO student_status_events(student_id,kind,order_no,order_date,effective_date,from_group_id,"
                     "to_group_id,note,entered_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (student_id, values["kind"], values["order_no"], values["order_date"], values["effective_date"],
                      from_group, values["to_group_id"], values["note"], by, iso(now()))).lastrowid


def end_open_enrollments(c, student_id: int, day: str) -> int:
    """End every enrolment still open on ``day``; earlier lessons, attendance and grades stay."""
    return c.execute("UPDATE enrollments SET end_date=? WHERE user_id=? AND (end_date IS NULL OR end_date>?)",
                     (day, student_id, day)).rowcount


def move_to_group(c, student_id: int, group_id: int):
    c.execute("UPDATE users SET group_id=? WHERE id=?", (group_id, student_id))


def current_term(c, day: str):
    """The active term whose teaching has started by ``day``, the latest such; None before the first."""
    return row(c, "SELECT * FROM academic_terms WHERE active=1 AND teaching_start<=? ORDER BY teaching_start DESC, id DESC LIMIT 1",
               (day,))
