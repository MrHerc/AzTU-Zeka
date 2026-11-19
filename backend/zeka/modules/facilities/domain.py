"""Rooms and what a room's page shows (tasks/todo.md, Task 18). No I/O.

A timetable row names its room as free text ("Əsas korpus, 118"). It is linked to a room when that text, compared
without case and spaces (and with ı = i), is the room's code, "<building>, <number>" or "<room name>, <number>". A text
that two rooms answer to is linked to neither and reported.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date

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


def now_and_next(lessons: list[dict], day: date, hhmm: str) -> tuple[dict | None, dict | None]:
    """(the lesson in progress at ``day`` ``hhmm`` or None, the next lesson to start or None). ``lessons`` are a room's
    lessons that are held (cancelled ones left out), each with ``day`` (ISO) and ``start``/``end`` (HH:MM)."""
    today = day.isoformat()
    ordered = sorted(lessons, key=lambda x: (x["day"], x["start"]))
    current = next((x for x in ordered if x["day"] == today and x["start"] <= hhmm < x["end"]), None)
    upcoming = next((x for x in ordered if (x["day"], x["start"]) > (today, hhmm)), None)
    return current, upcoming
