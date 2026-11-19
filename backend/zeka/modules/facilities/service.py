"""The room page, the QR sheet of a building and the link from timetable rows to rooms (tasks/todo.md, Task 18)."""
from __future__ import annotations

from datetime import date, timedelta

from ...legacy.store import audit, now
from . import domain, repo


def room_page(c, code: str) -> dict | None:
    """What the page behind a room's QR code shows: the room, the lesson in progress and the next one. None: no such room."""
    room = repo.room_by_code(c, code.upper())
    if not room:
        return None
    t = now()
    today = t.date()
    held = repo.room_lessons(c, room["id"], today.isoformat(), (today + timedelta(days=domain.LOOKAHEAD_DAYS)).isoformat())
    current, upcoming = domain.now_and_next(held, today, t.strftime("%H:%M"))
    nxt = {**upcoming, "date": upcoming["day"], "weekday": date.fromisoformat(upcoming["day"]).isoweekday()} if upcoming else None
    return {"room": room, "now": current, "next": nxt}


def link_timetable(c, user) -> dict:
    """Set each timetable row's room from its text; the texts that name no room (or two) are reported, most rows first."""
    idx = domain.index(repo.active_rooms(c))
    changes: list[tuple[int | None, int]] = []
    unmatched: dict[str, int] = {}
    linked = 0
    for r in repo.timetable_rooms(c):
        text = (r["room"] or "").strip()
        rid = idx.get(domain.room_key(text)) if text else None
        if rid:
            linked += 1
        elif text:
            unmatched[text] = unmatched.get(text, 0) + 1
        if rid != r["room_id"]:
            changes.append((rid, r["id"]))
    repo.set_rooms(c, changes)
    audit(c, user["id"] if user else None, "rooms_linked", "timetable", f"{linked} · {sum(unmatched.values())}")
    return {"linked": linked, "changed": len(changes),
            "unmatched": [{"room": k, "rows": n} for k, n in sorted(unmatched.items(), key=lambda x: (-x[1], x[0]))]}


def qr_sheet(c, building_id: int) -> tuple[dict, list[dict]] | None:
    b = repo.building(c, building_id)
    return (b, repo.rooms_of(c, building_id)) if b else None


def room_index(c) -> dict[str, int | None]:
    """For other modules (the timetable, Task 19): {room key: room id} of the active rooms."""
    return domain.index(repo.active_rooms(c))


def room_of(index: dict[str, int | None], text: str | None) -> int | None:
    return index.get(domain.room_key(text)) if text else None


def slot_room(index: dict[str, int | None], text: str | None) -> str | None:
    """The key two timetable entries share when they are in the same room: the room's id once known, else the text."""
    rid = room_of(index, text)
    return f"#{rid}" if rid else (domain.room_key(text) or None)
