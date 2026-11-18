"""SQL of the facilities module (tasks/todo.md, Task 18)."""
from __future__ import annotations

from ...legacy.store import row, rows

ROOM_PUBLIC = "r.id, r.code, r.number, r.name, r.floor, r.kind, r.capacity, r.accessible, b.name AS building, b.address"


def room_by_code(c, code: str):
    return row(c, f"SELECT {ROOM_PUBLIC} FROM rooms r JOIN buildings b ON b.id=r.building_id "  # nosec B608 (constant columns)
                  "WHERE r.code=? AND r.active=1 AND b.active=1", (code,))


def room_lessons(c, room_id: int) -> list[dict]:
    """The weekly rows held in the room, with the course name only: no teacher and no student is shown on the door."""
    return rows(c, "SELECT t.weekday, t.start, t.end, t.kind, co.name AS course FROM timetable t JOIN courses co ON co.id=t.course_id "
                   "WHERE t.room_id=? ORDER BY t.weekday, t.start", (room_id,))


def building(c, building_id: int):
    return row(c, "SELECT * FROM buildings WHERE id=?", (building_id,))


def rooms_of(c, building_id: int) -> list[dict]:
    return rows(c, "SELECT * FROM rooms WHERE building_id=? AND active=1 ORDER BY code", (building_id,))


def active_rooms(c) -> list[tuple[dict, dict]]:
    out = rows(c, "SELECT r.id, r.code, r.number, r.name, b.name AS b_name FROM rooms r JOIN buildings b ON b.id=r.building_id "
                  "WHERE r.active=1 AND b.active=1")
    return [(r, {"name": r["b_name"]}) for r in out]


def timetable_rooms(c) -> list[dict]:
    return rows(c, "SELECT id, room, room_id FROM timetable")


def set_rooms(c, pairs: list[tuple[int | None, int]]):
    c.executemany("UPDATE timetable SET room_id=? WHERE id=?", pairs)
