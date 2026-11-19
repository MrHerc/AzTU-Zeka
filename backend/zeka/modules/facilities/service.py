"""The room page, the QR sheet of a building and the link from timetable rows to rooms (tasks/todo.md, Task 18)."""
from __future__ import annotations

from datetime import date, timedelta

from ...core.i18n import S_
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


# ---------------------------------------------------------------- routes (Task 31)
MISSING = {"no_node": S_("Bu otaq hələ marşrut xəritəsində yoxdur"),
           "no_path": S_("Bu otaqlar arasında marşrut yoxdur (pilləsiz seçimdə lift olmaya bilər)")}


def rooms_for_search(c) -> list[dict]:
    """Every active room with its building, for the assistant's lookup (Task 31)."""
    return repo.rooms_for_search(c)


def room_code(c, room_id: int):
    """{code} of a room, or None."""
    return repo.room_code(c, room_id)


def import_graph(c, building_code: str, node_rows: list[dict], edge_rows: list[dict]) -> dict:
    """Replace a building's route graph from its CSV rows, all or nothing: {ok, problems} or {ok, nodes, edges, coverage}."""
    b = repo.building_by_code(c, building_code.strip().upper())
    if not b:
        return {"ok": False, "problems": [f"no active building with the code {building_code!r}"]}
    rooms = {r["id"]: r for r in repo.rooms_of(c, b["id"])}
    nodes, edges, problems = domain.graph_input(node_rows, edge_rows, {r["code"]: rid for rid, r in rooms.items()})
    if problems:
        return {"ok": False, "problems": problems}
    repo.replace_graph(c, b["id"], nodes, edges)
    stored, stored_edges = repo.graph(c, b["id"])
    return {"ok": True, "building": b["code"], "nodes": len(nodes), "edges": len(edges),
            "coverage": domain.coverage(stored, stored_edges, rooms)}


def route(c, to_code: str, from_code: str | None = None, step_free: bool = False) -> dict | None:
    """The way to a room: from another room's door in the same building, else from the building's nearest entrance (a
    room in another building first sends the person to this building). None: no such room. ``steps`` holds
    (template, parameters) pairs; ``missing`` says why there is no way: the room has no node, or no node joins them."""
    target = repo.room_full(c, (to_code or "").strip().upper())
    if not target:
        return None
    origin = repo.room_full(c, from_code.strip().upper()) if from_code else None
    nodes, edges = repo.graph(c, target["building_id"])
    door = {n["room_id"]: k for k, n in nodes.items() if n["kind"] == "door"}
    out = {"room": target, "from": origin, "step_free": step_free, "steps": [], "length_m": None, "missing": None}
    if target["id"] not in door:
        out["missing"] = "no_node"
        return out
    lead: list[tuple[str, dict]] = []
    if origin and origin["building_id"] == target["building_id"] and origin["id"] in door:
        starts = [door[origin["id"]]]
    else:
        starts = [k for k, n in nodes.items() if n["kind"] == "entrance"]
        if origin and origin["building_id"] != target["building_id"]:
            lead = [(S_("Bu otaq başqa korpusdadır: {building} ({address})"),
                     {"building": target["building"], "address": target["address"] or ""})]
    found = domain.shortest(nodes, edges, starts, door[target["id"]], step_free) if starts else None
    if not found:
        out["missing"] = "no_path"
        return out
    path, metres = found
    out.update(steps=lead + domain.steps(path, nodes, edges), length_m=round(metres))
    return out
