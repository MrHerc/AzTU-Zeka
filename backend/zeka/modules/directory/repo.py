"""SQL of the directory module. Table and column names come from domain.ENTITIES (constants), values are bound."""
from __future__ import annotations

from ...legacy.store import iso, now, row, rows
from . import domain


def _cfg(entity: str) -> dict:
    return domain.ENTITIES[entity]


def page(c, entity: str, q: str, active: int | None, page_no: int) -> tuple[list, int]:
    cfg = _cfg(entity)
    where: list[str] = []
    args: list = []
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(" + " OR ".join(f"{col} LIKE ? ESCAPE '\\'" for col in cfg["search"]) + ")")
        args += [like] * len(cfg["search"])
    if active is not None:
        where.append("active=?")
        args.append(active)
    sql_where = (" WHERE " + " AND ".join(where)) if where else ""
    total = row(c, f"SELECT COUNT(*) n FROM {cfg['table']}{sql_where}", tuple(args))["n"]  # nosec B608 - names from ENTITIES
    items = rows(c, f"SELECT * FROM {cfg['table']}{sql_where} ORDER BY {cfg['order']}, id LIMIT ? OFFSET ?",  # nosec B608
                 (*args, domain.PAGE, (page_no - 1) * domain.PAGE))
    return items, total


def get(c, entity: str, rid: int):
    return row(c, f"SELECT * FROM {_cfg(entity)['table']} WHERE id=?", (rid,))  # nosec B608 - name from ENTITIES


def taken(c, entity: str, value, exclude: int | None = None) -> bool:
    col = domain.UNIQUE[entity]
    return row(c, f"SELECT 1 FROM {_cfg(entity)['table']} WHERE {col}=? AND id IS NOT ?", (value, exclude)) is not None  # nosec B608


def insert(c, entity: str, values: dict) -> int:
    t = iso(now())
    values = {**values, "active": 1, **({"created_at": t, "updated_at": t} if entity != "groups" else {})}
    cols = ", ".join(values)
    return c.execute(f"INSERT INTO {_cfg(entity)['table']}({cols}) VALUES({', '.join('?' * len(values))})",  # nosec B608
                     tuple(values.values())).lastrowid


def update(c, entity: str, rid: int, values: dict):
    if entity != "groups":
        values = {**values, "updated_at": iso(now())}
    sets = ", ".join(f"{k}=?" for k in values)
    c.execute(f"UPDATE {_cfg(entity)['table']} SET {sets} WHERE id=?", (*values.values(), rid))  # nosec B608 - names from ENTITIES
