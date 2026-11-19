"""Rooms and what a room's page shows (tasks/todo.md, Task 18). No I/O.

A timetable row names its room as free text ("Əsas korpus, 118"). It is linked to a room when that text, compared
without case and spaces (and with ı = i), is the room's code, "<building>, <number>" or "<room name>, <number>". A text
that two rooms answer to is linked to neither and reported.
"""
from __future__ import annotations

import heapq
from collections.abc import Iterable
from datetime import date

from ...core.i18n import S_

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


# ---------------------------------------------------------------- the route graph (Task 31)
NODE_KINDS = ("entrance", "corridor", "stairs", "lift", "door")
MAX_EDGE_M = 2000.0


def _flag(text) -> int | None:
    t = str(text or "").strip().lower()
    return 1 if t in ("1", "yes", "true", "bəli") else 0 if t in ("0", "no", "false", "xeyr") else None


def graph_input(node_rows: list[dict], edge_rows: list[dict], rooms: dict[str, int]) -> tuple[list[dict], list[dict], list[str]]:
    """A building's nodes and edges from its two CSV files (``code,kind,floor,room,label`` and
    ``from,to,length_m,step_free``), checked as a whole: (nodes, edges, problems), each problem naming its file and line.
    ``rooms``: the building's room codes and ids. A floor change joins two stairs (never step-free) or two lifts."""
    problems: list[str] = []
    nodes: list[dict] = []
    by_code: dict[str, dict] = {}
    for line, r in enumerate(node_rows, start=2):
        code = str(r.get("code") or "").strip()
        kind = str(r.get("kind") or "").strip().lower()
        room = str(r.get("room") or "").strip().upper()
        try:
            floor = int(str(r.get("floor") or "").strip())
        except ValueError:
            floor = None
        where = f"nodes.csv:{line}"
        if not code or code in by_code:
            problems.append(f"{where}: the code is empty or repeated")
            continue
        if kind not in NODE_KINDS:
            problems.append(f"{where}: kind must be one of {', '.join(NODE_KINDS)}")
        if floor is None or not -5 <= floor <= 100:
            problems.append(f"{where}: floor must be a whole number")
        if kind == "door" and room not in rooms:
            problems.append(f"{where}: a door names a room of this building (got {room or 'nothing'})")
        if kind != "door" and room:
            problems.append(f"{where}: only a door names a room")
        n = {"code": code, "kind": kind, "floor": floor, "room_id": rooms.get(room) if kind == "door" else None,
             "label": " ".join(str(r.get("label") or "").split())[:120] or room or code}
        by_code[code] = n
        nodes.append(n)
    edges: list[dict] = []
    for line, r in enumerate(edge_rows, start=2):
        a, b = str(r.get("from") or "").strip(), str(r.get("to") or "").strip()
        where = f"edges.csv:{line}"
        try:
            length = float(str(r.get("length_m") or "").strip().replace(",", "."))
        except ValueError:
            length = -1.0
        step_free = _flag(r.get("step_free"))
        if a not in by_code or b not in by_code or a == b:
            problems.append(f"{where}: both ends must be different nodes of nodes.csv")
            continue
        if not 0 < length <= MAX_EDGE_M:
            problems.append(f"{where}: length_m must be a number of metres above 0")
        if step_free is None:
            problems.append(f"{where}: step_free must be 1 or 0")
        na, nb = by_code[a], by_code[b]
        if na["floor"] != nb["floor"]:
            pair = {na["kind"], nb["kind"]}
            if pair == {"stairs"} and step_free:
                problems.append(f"{where}: stairs are never step-free")
            elif pair not in ({"stairs"}, {"lift"}):
                problems.append(f"{where}: a floor change joins two stairs or two lifts")
        edges.append({"a": a, "b": b, "length_m": length, "step_free": step_free or 0})
    return nodes, edges, problems


def _adjacency(nodes: dict, edges: list[dict], step_free: bool) -> dict:
    """{node: [(neighbour, metres)]}; a step-free graph has no step edge and no stairs node at all."""
    adj: dict = {}
    for e in edges:
        if step_free and (not e["step_free"] or "stairs" in (nodes[e["a"]]["kind"], nodes[e["b"]]["kind"])):
            continue
        adj.setdefault(e["a"], []).append((e["b"], e["length_m"]))
        adj.setdefault(e["b"], []).append((e["a"], e["length_m"]))
    return adj


def shortest(nodes: dict, edges: list[dict], starts: Iterable, goal, step_free: bool = False) -> tuple[list, float] | None:
    """Dijkstra from the nearest of ``starts`` to ``goal``: (the nodes on the way, metres) or None when there is no way.
    ``nodes``: {key: {kind, floor, ...}}; ``edges``: {a, b, length_m, step_free} with node keys."""
    adj = _adjacency(nodes, edges, step_free)
    dist: dict = {}
    prev: dict = {}
    heap: list = []
    for s in starts:
        dist[s] = 0.0
        heap.append((0.0, str(s), s))
    heapq.heapify(heap)
    while heap:
        d, _, n = heapq.heappop(heap)
        if n == goal:
            break
        if d > dist.get(n, float("inf")):
            continue
        for m, w in adj.get(n, ()):
            if d + w < dist.get(m, float("inf")):
                dist[m], prev[m] = d + w, n
                heapq.heappush(heap, (d + w, str(m), m))
    if goal not in dist:
        return None
    path = [goal]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    return path[::-1], dist[goal]


def steps(path: list, nodes: dict, edges: list[dict]) -> list[tuple[str, dict]]:
    """The way as short instructions (template, parameters): walks on a floor summed up, a run of stairs or a lift ride
    as one step to its last floor."""
    length = {}
    for e in edges:
        length[(e["a"], e["b"])] = length[(e["b"], e["a"])] = e["length_m"]
    out: list[tuple[str, dict]] = [(S_("Başlanğıc: {label}"), {"label": nodes[path[0]]["label"]})]
    walk = 0.0
    for a, b in zip(path, path[1:], strict=False):
        fa, fb = nodes[a]["floor"], nodes[b]["floor"]
        if fa == fb:
            walk += length[(a, b)]
            continue
        if walk:
            out.append((S_("{m} m gedin → {label}"), {"m": max(1, round(walk)), "label": nodes[a]["label"]}))
            walk = 0.0
        lift = nodes[a]["kind"] == "lift"
        up = fb > fa
        template = ((S_("Liftlə qalxın, mərtəbə: {floor}") if up else S_("Liftlə düşün, mərtəbə: {floor}")) if lift else
                    (S_("Pilləkənlə qalxın, mərtəbə: {floor}") if up else S_("Pilləkənlə düşün, mərtəbə: {floor}")))
        if out[-1][0] == template:
            out[-1] = (template, {"floor": fb})
        else:
            out.append((template, {"floor": fb}))
    if walk:
        out.append((S_("{m} m gedin → {label}"), {"m": max(1, round(walk)), "label": nodes[path[-1]]["label"]}))
    out.append((S_("Çatdınız: {label}"), {"label": nodes[path[-1]]["label"]}))
    return out


def coverage(nodes: dict, edges: list[dict], rooms: dict[int, dict]) -> dict:
    """What the import leaves out: rooms of the building without a door node, doors no entrance reaches, and doors of
    rooms marked accessible that no entrance reaches without steps."""
    doors = {n["room_id"]: k for k, n in nodes.items() if n["kind"] == "door"}
    entrances = [k for k, n in nodes.items() if n["kind"] == "entrance"]

    def reach(step_free: bool) -> set:
        adj, seen, todo = _adjacency(nodes, edges, step_free), set(entrances), list(entrances)
        while todo:
            for m, _ in adj.get(todo.pop(), ()):
                if m not in seen:
                    seen.add(m)
                    todo.append(m)
        return seen
    anyway, level = reach(False), reach(True)
    return {"rooms_without_node": sorted(r["code"] for rid, r in rooms.items() if rid not in doors),
            "unreachable": sorted(rooms[rid]["code"] for rid, k in doors.items() if k not in anyway and rid in rooms),
            "no_step_free_route": sorted(rooms[rid]["code"] for rid, k in doors.items()
                                         if rid in rooms and rooms[rid].get("accessible") and k not in level)}
