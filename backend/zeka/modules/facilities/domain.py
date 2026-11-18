"""Rooms and what a room's page shows (tasks/todo.md, Task 18). No I/O.

A timetable row names its room as free text ("Əsas korpus, 118"). It is linked to a room when that text, compared
without case and spaces (and with ı = i), is the room's code, "<building>, <number>" or "<room name>, <number>". A text
that two rooms answer to is linked to neither and reported.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, timedelta

AZ_LOWER = str.maketrans({"I": "ı", "İ": "i"})         # Python lowers İ to i + a combining dot
LOOKAHEAD_DAYS = 14                                    # how far the page looks for the next lesson


def room_key(text) -> str:
    t = str(text or "").translate(AZ_LOWER).lower().replace("ı", "i")
    return "".join(t.split())


def room_names(room: dict, building: dict) -> list[str]:
    """The texts a timetable row may name this room by."""
    out = [room["code"], f"{building['name']}, {room['number']}"]
    if room.get("name"):
        out.append(f"{room['name']}, {room['number']}")
    return out


def index(rooms: Iterable[tuple[dict, dict]]) -> dict[str, int | None]:
    """{room key: room id} over (room, building) pairs; a key two rooms share maps to None."""
    out: dict[str, int | None] = {}
    for room, building in rooms:
        for name in room_names(room, building):
            k = room_key(name)
            out[k] = room["id"] if out.get(k, room["id"]) == room["id"] else None
    return out


def now_and_next(rows: list[dict], day: date, hhmm: str, open_day: Callable[[date], bool]):
    """(the row in progress at ``day`` ``hhmm`` or None, (date, row) of the next row to start or None).
    ``rows`` are weekly timetable rows (weekday 1-7, start and end as HH:MM); ``open_day`` says whether lessons are held."""
    ordered = sorted(rows, key=lambda r: (r["weekday"], r["start"]))
    current = None
    if open_day(day):
        current = next((r for r in ordered if r["weekday"] == day.isoweekday() and r["start"] <= hhmm < r["end"]), None)
    for add in range(LOOKAHEAD_DAYS + 1):
        d = day + timedelta(days=add)
        if not open_day(d):
            continue
        hit = next((r for r in ordered if r["weekday"] == d.isoweekday() and (add > 0 or r["start"] > hhmm)), None)
        if hit:
            return current, (d, hit)
    return current, None


def teaching_day(term: dict | None, holidays: Iterable[str]) -> Callable[[date], bool]:
    """Whether lessons are held on a day: inside the term's teaching dates and not a holiday."""
    off = set(holidays)

    def open_day(d: date) -> bool:
        iso = d.isoformat()
        return term is not None and term["teaching_start"] <= iso <= term["teaching_end"] and iso not in off

    return open_day
