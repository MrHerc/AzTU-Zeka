"""The semester timetable solver (tasks/todo.md, Task 48). Pure: no I/O, no clock, no database.

``prepare(problem) -> Model`` builds the meetings, their domains and the obstacles; ``run(model, state, ...)`` works
the search for a number of iterations or until a deadline and returns a JSON state to resume from; ``result`` gives
the placements, the unplaced meetings with their reasons and the score. The state never holds a hard violation: a
value is taken only after every hard rule passed, and a meeting that fits nowhere stays unplaced.

Search: construction by iterative forward search with ejection (UniTime's approach), then simulated annealing with a
move, a swap and ruin-and-recreate around unplaced meetings. The objective is the tuple (unplaced pairs, soft cost),
integers only. Determinism: one ``random.Random(seed)``, used only through ``rng.random()``; no ``hash()``, no
iteration over a set; the clock is a parameter and can only stop a run early, so N iterations in one go equal N/2,
save, resume and N/2.
"""
from __future__ import annotations

import bisect
import heapq
import random
from collections.abc import Callable

from . import domain

T0 = 30.0               # the annealing temperature at iteration 0 (cost units); T(i) = T0 x (1 - i/N)^2
SAMPLE = 8              # M1 draws this many values of the meeting and takes the cheapest feasible one
EJECT_TRIES = 8         # values of a meeting tried with ejection, cheapest estimate first
NONE = -1


class Model:
    """Everything that does not change during a run: meetings, values, rooms, resources, obstacles."""

    def __init__(self, problem: dict):
        st = problem["settings"]
        self.problem = problem
        self.settings = st
        self.w = st["weights"]
        self.n = problem["weeks"]
        self.full = (1 << self.n) - 1
        self.days = list(st["days"])
        times = domain.lesson_times(problem)
        self.P = len(times)
        self.D = len(self.days)
        self.S = self.D * self.P
        self.breaks = domain.breaks(times)
        self.travel = st["travel_default_min"]
        self.repair = bool(problem.get("repair"))
        self.meetings, self.excluded = domain.meetings_of(problem)
        M = self.meetings
        self.N = len(M)
        self.index = {m["key"]: i for i, m in enumerate(M)}
        groups = {g["id"]: g for g in problem.get("groups") or []}
        # rooms renumbered by capacity, so the smallest room that fits is the lowest bit of a meeting's room set
        self.rooms = sorted(problem.get("rooms") or [], key=lambda r: (r.get("capacity") or 0, r["id"]))
        self.room_index = {r["id"]: k for k, r in enumerate(self.rooms)}
        self.cap = [r.get("capacity") or 0 for r in self.rooms]
        self.bld = [r.get("building_id") for r in self.rooms]
        self.multi_building = len({b for b in self.bld}) > 1
        # resources: teachers and group cells (g, None) and (g, s) for every subgroup s some unit or obstacle names
        self.subs = domain.subgroups(problem)
        self.res: dict[tuple, int] = {}

        def rid(key: tuple) -> int:
            if key not in self.res:
                self.res[key] = len(self.res)
            return self.res[key]

        def cells_of(g: int, s) -> list[int]:
            return [rid(("g", g, None)), *(rid(("g", g, x)) for x in self.subs.get(g, []))] if not s else [rid(("g", g, s))]

        self.teacher = [rid(("t", m["teacher_id"])) if m["teacher_id"] else NONE for m in M]
        self.cells = [sorted({c for g in m["groups"] for c in cells_of(g, m["subgroup"])}) for m in M]
        self.dur = [m["duration"] for m in M]
        self.variants = [m["variants"] for m in M]
        self.online = [m["online"] for m in M]
        self.need = [m["need"] for m in M]
        self.course = [m["course_id"] for m in M]
        self.units = sorted({m["unit_id"] for m in M})
        unit_pos = {u: k for k, u in enumerate(self.units)}
        self.unit = [unit_pos[m["unit_id"]] for m in M]
        forms = {u["id"]: u.get("hours") for u in problem["units"]}
        self.form = [forms[u] for u in self.units]
        # S10 per variant and day: the weeks the placement holds (its week set without the day's lost weeks, CORR-F1)
        lost = [domain.off_of(problem, wd) for wd in self.days]
        self.hours = [[[(v & ~lw).bit_count() * st["pair_hours"] * m["duration"] for lw in lost] for v in m["variants"]] for m in M]
        self.pairs = [max((v.bit_count() for v in m["variants"]), default=0) * m["duration"] for m in M]
        self.homes = [[(groups.get(g) or {}).get("home_building_id") for g in m["groups"]] for m in M]
        self.room_bits = [sum(1 << k for k, r in enumerate(self.rooms) if domain.room_fits(m, r)) for m in M]
        # obstacles: items N.. with their resources and room
        future = domain.future_mask(problem)
        self.obstacles = []
        self.offgrid = []        # obstacles on a weekday the run does not use: they count in the week limits and windows only
        for o in problem.get("obstacles") or []:
            mask = domain.week_mask(o["weeks"], self.n) & future
            if not mask:
                continue
            first = o["period"] - 1
            last = min(self.P, first + (o.get("duration") or 1))
            if first < 0 or first >= last:
                continue
            res = sorted({c for g, s in o["groups"] for c in cells_of(g, s)} | ({rid(("t", o["teacher_id"]))} if o.get("teacher_id") else set()))
            if o["weekday"] not in self.days:
                self.offgrid.append({"weekday": o["weekday"], "p": first, "dur": last - first, "mask": mask, "res": res})
                continue
            ri = self.room_index.get(o.get("room_id"), NONE) if not o.get("online") else NONE
            self.obstacles.append({"key": o["key"], "slot": self.days.index(o["weekday"]) * self.P + first, "dur": last - first,
                                   "mask": mask, "res": res, "room": ri})
        self.R = len(self.res)
        self.is_cell = [k[0] == "g" for k in sorted(self.res, key=lambda k: self.res[k])]
        # static rules: days, duration, shift (H7), fixed slots (H8), teacher availability (H6), costs that depend on the value only
        t_un = domain._avail(problem, "teacher", "unavailable")
        und = domain._avail(problem, "teacher", "undesired")
        self.room_un = domain._avail(problem, "room", "unavailable")
        self.room_block = domain._blocks(problem)
        fixed = domain._fixed(problem)
        ref = {x["key"]: x for x in problem.get("reference") or []}
        self.ref: list[tuple | None] = []
        self.values: list[list[tuple[int, int, int]]] = []
        for i, m in enumerate(M):
            r = ref.get(m["key"])
            self.ref.append(None if r is None or r["weekday"] not in self.days else
                            ((self.days.index(r["weekday"])) * self.P + r["period"] - 1, domain.week_mask(r["weeks"], self.n) & future,
                             self.room_index.get(r.get("room_id"), NONE)))
            shifts = [domain._shift_periods(problem, groups.get(g)) for g in m["groups"]]
            late = any(s is None for s in shifts)
            vals = []
            for di, wd in enumerate(self.days):
                for p in range(self.P - m["duration"] + 1):
                    periods = range(p + 1, p + m["duration"] + 1)
                    if any(s is not None and not set(periods) <= s for s in shifts):
                        continue
                    if any(f["weekday"] == wd and f["period"] in periods and (f.get("groups") is None or set(f["groups"]) & set(m["groups"]))
                           for f in fixed):
                        continue
                    s = di * self.P + p
                    for vi, mask in enumerate(m["variants"]):
                        if m["teacher_id"] and any(t_un.get((m["teacher_id"], wd, q), 0) & mask for q in periods):
                            continue
                        weeks = mask.bit_count()
                        cost = self.w["saturday"] * weeks * m["duration"] * (wd == 6)
                        cost += self.w["late_pair"] * weeks * sum(q > domain.LATE_AFTER for q in periods) * late
                        if m["teacher_id"]:
                            cost += self.w["undesired"] * sum((und.get((m["teacher_id"], wd, q), 0) & mask).bit_count() for q in periods)
                        rf = self.ref[i]
                        if rf is not None:
                            moved, reweek = rf[0] != s, rf[1] != mask
                            cost += self.w["stability_time"] * moved + self.w["stability_weeks"] * reweek
                            cost += self.w["move_repair"] * (self.repair and (moved or reweek))
                        vals.append((s, vi, cost))
            vals.sort(key=lambda x: (x[2], x[0], x[1]))
            self.values.append(vals)
        self.value_at = [{(s, vi): j for j, (s, vi, _) in enumerate(vals)} for vals in self.values]
        # neighbours: meetings that share a teacher or a group cell (M2, M5)
        by_res: dict[int, list[int]] = {}
        for i in range(self.N):
            for r in ([self.teacher[i]] if self.teacher[i] != NONE else []) + self.cells[i]:
                by_res.setdefault(r, []).append(i)
        self.neighbours = [sorted({x for r in ([self.teacher[i]] if self.teacher[i] != NONE else []) + self.cells[i]
                                   for x in by_res[r] if x != i}) for i in range(self.N)]
        degree = [len(nb) for nb in self.neighbours]
        lock = {x["key"]: x for x in problem.get("locked") or []}
        self.locked: dict[int, tuple] = {}
        for k, x in sorted(lock.items()):
            if k in self.index:          # a value off the grid (not a teaching day) is slot -1: it fails and stays unplaced
                slot = self.days.index(x["weekday"]) * self.P + x["period"] - 1 if x["weekday"] in self.days else -1
                self.locked[self.index[k]] = (slot,
                                              domain.week_mask(x["weeks"], self.n) & future, x.get("room_id"))
        # construction order: in a repair the kept meetings first; then the smallest domain per degree, more groups, a
        # larger need
        self.rank = [0] * self.N
        order = sorted(range(self.N), key=lambda i: (not (self.repair and self.ref[i] is not None), len(self.values[i]) * max(1, self.room_bits[i].bit_count()) * 64 // (1 + degree[i]),
                                                     -len(M[i]["groups"]), -self.need[i], i))
        for pos, i in enumerate(order):
            self.rank[i] = pos
        self.gaps = [domain._gaps(b) for b in range(1 << self.P)]


def prepare(problem: dict) -> Model:
    return Model(problem)


def precheck(model: Model) -> list[dict]:
    """Reasons visible before any search (they never stop a run): units that cannot be scheduled, meetings without a
    week, a room or a slot, teachers and groups loaded above what their week holds, and too few large rooms."""
    st, n = model.settings, model.n
    out = [dict(x) for x in model.excluded]
    kinds_seen = {r["kind"] for r in model.rooms if r.get("schedulable", 1)}
    for i, m in enumerate(model.meetings):
        if not m["variants"]:
            out.append({"code": "blocked_weeks", "key": m["key"]})
        elif not m["online"] and not model.room_bits[i]:
            fit = [model.cap[k] for k, r in enumerate(model.rooms) if r["kind"] in m["kinds"] and r.get("schedulable", 1)]
            if not set(m["kinds"]) & kinds_seen or not fit:
                out.append({"code": "no_room_kind", "key": m["key"]})
            elif max(fit) >= m["need"]:      # large enough rooms exist, but are dedicated to other units or not on its list
                out.append({"code": "room_reserved", "key": m["key"]})
            else:
                out.append({"code": "no_room_capacity", "key": m["key"], "need": m["need"], "max": max(fit)})
        if m["variants"] and not model.values[i]:
            out.append({"code": "empty_time_domain", "key": m["key"]})
    load: dict[int, int] = {}
    for i in range(model.N):
        for r in ([model.teacher[i]] if model.teacher[i] != NONE else []) + model.cells[i]:
            load[r] = load.get(r, 0) + model.pairs[i]
    names = sorted(model.res, key=lambda k: model.res[k])
    t_un, blocks = domain._avail(model.problem, "teacher", "unavailable"), domain._blocks(model.problem)
    weeks = domain.future_mask(model.problem)
    for r in sorted(load):
        key = names[r]
        if key[0] == "t":
            # the (pair, week) cells the teacher can teach in: not unavailable, not blocked, within the day limit
            free = weeks & ~blocks.get(("teacher", key[1]), 0)
            cells = sum((free & ~t_un.get((key[1], wd, p + 1), 0)).bit_count() for wd in model.days for p in range(model.P))
            available = min(cells, min(model.S, st["max_pairs_day_teacher"] * model.D) * n)
            if load[r] > available:
                out.append({"code": "teacher_overload", "teacher_id": key[1], "pair_weeks": load[r], "available": available})
        if key[0] == "g" and load[r] * st["pair_hours"] > st["max_week_hours_group"] * n:
            out.append({"code": "group_over_law", "group_id": key[1], "subgroup": key[2], "hours": load[r] * st["pair_hours"] // n})
    # room supply: pair-weeks of in-person meetings that need at least c seats against rooms of c seats or more
    needs = sorted({model.need[i] for i in range(model.N) if not model.online[i]})
    for c in needs:
        demand = sum(model.pairs[i] for i in range(model.N) if not model.online[i] and model.need[i] >= c)
        supply = sum(1 for k, r in enumerate(model.rooms) if r.get("schedulable", 1) and model.cap[k] >= c) * model.S * n
        if demand > supply:
            out.append({"code": "room_supply", "need": c, "demand": demand // max(1, n), "supply": supply // max(1, n)})
    return out


class Search:
    """The mutable state of one run: the assignment and the incremental structures every hard check and soft cost
    reads. Rebuilt from the JSON state at each call of ``run``."""

    def __init__(self, model: Model):
        self.m = model
        mo = model
        self.assign: list[tuple[int, int] | None] = [None] * mo.N
        self.mask_of: list[int] = [0] * (mo.N + len(mo.obstacles))
        self.bld_of: list[int | None] = [None] * (mo.N + len(mo.obstacles))
        self.occ = [0] * (mo.R * mo.S)                  # resource x slot -> union of week masks (disjoint, so XOR removes)
        self.holders: dict[int, list[int]] = {}
        self.rocc = [0] * (len(mo.rooms) * mo.S)        # room x slot, starting with its unavailable and blocked weeks
        self.rholders: dict[int, list[int]] = {}
        self.rfull = [0] * mo.S                          # rooms whose every week is taken at a slot
        self.prof: list[list[list[int]]] = [[[mo.full, 0]] for _ in range(mo.R * mo.D)]   # [weeks, pair bits] classes
        self.weekc: list[list[list[int]]] = [[[mo.full, 0]] for _ in range(mo.R)]         # [weeks, pairs] classes
        self.course_day: dict[tuple, list[int]] = {}
        self.unit_sum = [0] * len(mo.units)
        self.open = list(range(mo.N))                   # the unplaced meetings, sorted (kept, not recomputed per iteration)
        self.ejected = [0] * mo.N                        # how often each meeting was ejected (construction)
        st = mo.settings
        self.max_t, self.max_g = st["max_pairs_day_teacher"], st["max_pairs_day_group"]
        self.max_week_g = st["max_week_hours_group"] // st["pair_hours"]
        self.max_week_t = st.get("max_week_pairs_teacher") or 0
        self.soft = mo.w["hours_miss"] * sum(domain._hours_cost(0, f, st) for f in mo.form)
        self.unplaced_pairs = sum(mo.pairs)
        for k, r in enumerate(mo.rooms):
            block = mo.room_block.get(("room", r["id"]), 0)
            for di, wd in enumerate(mo.days):
                for p in range(mo.P):
                    s = di * mo.P + p
                    self.rocc[k * mo.S + s] = (block | mo.room_un.get((r["id"], wd, p + 1), 0)) & mo.full
                    if self.rocc[k * mo.S + s] == mo.full:
                        self.rfull[s] |= 1 << k
        for j, o in enumerate(mo.obstacles):
            x = mo.N + j
            self.mask_of[x] = o["mask"]
            self.bld_of[x] = mo.bld[o["room"]] if o["room"] != NONE else None
            for q in range(o["dur"]):
                s = o["slot"] + q
                for r in o["res"]:
                    self.occ[r * mo.S + s] |= o["mask"]                 # obstacles never move: a union, never undone
                    self.holders.setdefault(r * mo.S + s, []).append(x)
                if o["room"] != NONE:
                    self.rocc[o["room"] * mo.S + s] |= o["mask"]
                    self.rholders.setdefault(o["room"] * mo.S + s, []).append(x)
                    if self.rocc[o["room"] * mo.S + s] == mo.full:
                        self.rfull[s] |= 1 << o["room"]
            day, p = divmod(o["slot"], mo.P)
            bits = ((1 << o["dur"]) - 1) << p
            for r in o["res"]:
                self.soft += self._window_weight(r) * self._prof_add(r * mo.D + day, o["mask"], bits)
                self._count_add(self.weekc[r], o["mask"], o["dur"])
        off: dict[tuple[int, int], int] = {}     # (resource, weekday) -> its day profile, kept after the grid's
        for o in mo.offgrid:
            bits = ((1 << o["dur"]) - 1) << o["p"]
            for r in o["res"]:
                if (r, o["weekday"]) not in off:
                    off[(r, o["weekday"])] = len(self.prof)
                    self.prof.append([[mo.full, 0]])
                self.soft += self._window_weight(r) * self._prof_add(off[(r, o["weekday"])], o["mask"], bits)
                self._count_add(self.weekc[r], o["mask"], o["dur"])

    # ---------------------------------------------------------------- incremental structures
    def _window_weight(self, r: int) -> int:
        return self.m.w["group_window"] if self.m.is_cell[r] else self.m.w["teacher_window"]

    def _win_delta(self, classes: list[list[int]], mask: int, bits: int) -> int:
        g = self.m.gaps
        return sum((wm & mask).bit_count() * (g[pb | bits] - g[pb]) for wm, pb in classes if wm & mask)

    def _prof_add(self, k: int, mask: int, bits: int) -> int:
        """Add bits in the weeks of mask to a profile; the change of its window count."""
        delta = self._win_delta(self.prof[k], mask, bits)
        self.prof[k] = self._merge([c for wm, pb in self.prof[k] for c in
                                    (([[wm & ~mask, pb]] if wm & ~mask else []) + [[wm & mask, pb | bits]] if wm & mask else [[wm, pb]])])
        return delta

    def _prof_remove(self, k: int, mask: int, bits: int) -> int:
        self.prof[k] = self._merge([c for wm, pb in self.prof[k] for c in
                                    (([[wm & ~mask, pb]] if wm & ~mask else []) + [[wm & mask, pb & ~bits]] if wm & mask else [[wm, pb]])])
        return -self._win_delta(self.prof[k], mask, bits)

    @staticmethod
    def _merge(classes: list[list[int]]) -> list[list[int]]:
        out: dict[int, int] = {}
        for wm, v in classes:
            out[v] = out.get(v, 0) | wm
        return [[wm, v] for v, wm in out.items()]

    def _count_add(self, classes: list[list[int]], mask: int, d: int) -> None:
        classes[:] = self._merge([c for wm, v in classes for c in
                                  (([[wm & ~mask, v]] if wm & ~mask else []) + [[wm & mask, v + d]] if wm & mask else [[wm, v]])])

    def _hours_delta(self, i: int, vi: int, day: int, sign: int) -> int:
        u, st = self.m.unit[i], self.m.settings
        before = self.unit_sum[u]
        return self.m.w["hours_miss"] * (domain._hours_cost(before + sign * self.m.hours[i][vi][day], self.m.form[u], st)
                                         - domain._hours_cost(before, self.m.form[u], st))

    def _resources(self, i: int) -> list[int]:
        t = self.m.teacher[i]
        return ([t] if t != NONE else []) + self.m.cells[i]

    # ---------------------------------------------------------------- hard rules of a value
    def time_ok(self, i: int, s: int, mask: int) -> bool:
        """H1, H2 (clashes), H11 (pairs a day) and H12 (hours a week) of meeting i at slot s in the weeks of mask."""
        mo = self.m
        d = mo.dur[i]
        t = mo.teacher[i]
        S = mo.S
        res = self._resources(i)
        for q in range(d):
            for r in res:
                if self.occ[r * S + s + q] & mask:
                    return False
        day = s // mo.P
        for r in res:
            limit = self.max_g if mo.is_cell[r] else self.max_t
            for wm, pb in self.prof[r * mo.D + day]:
                if wm & mask and pb.bit_count() + d > limit:
                    return False
        for r in mo.cells[i]:
            for wm, v in self.weekc[r]:
                if wm & mask and v + d > self.max_week_g:
                    return False
        if self.max_week_t and t != NONE:
            for wm, v in self.weekc[t]:
                if wm & mask and v + d > self.max_week_t:
                    return False
        return True

    def required_building(self, i: int, s: int, mask: int):
        """H9: the building the room must be in so the pair before and the pair after can be reached (None: any;
        False: none can)."""
        mo = self.m
        if not mo.multi_building or mo.online[i]:
            return None
        day, p = divmod(s, mo.P)
        d = mo.dur[i]
        need = None
        for q, gap in ((p - 1, mo.breaks[p - 1] if p > 0 else None), (p + d, mo.breaks[p + d - 1] if p + d < mo.P else None)):
            if gap is None or gap >= mo.travel:
                continue
            for r in self._resources(i):
                for x in self.holders.get(r * mo.S + day * mo.P + q, ()):
                    b = self.bld_of[x]
                    if b is not None and self.mask_of[x] & mask:
                        if need is not None and need != b:
                            return False
                        need = b
        return need

    def room_cost(self, i: int, k: int, s: int, mask: int) -> int:
        mo = self.m
        if k == NONE:
            return 0
        w = mo.w
        cost = w["room_waste_10"] * (max(0, mo.cap[k] - mo.need[i]) // 10)
        cost += w["foreign_building"] * sum(1 for h in mo.homes[i] if h is not None and h != mo.bld[k])
        rf = mo.ref[i]
        if rf is not None and rf[2] != k:
            cost += w["stability_room"] + w["move_repair"] * (mo.repair and rf[0] == s and rf[1] == mask)
        return cost

    def pick_room(self, i: int, s: int, mask: int, bound: float = float("inf")):
        """The cheapest free room that fits (H3-H6 of rooms, H9), as (room, cost), or None. Online: (NONE, 0)."""
        mo = self.m
        need = self.required_building(i, s, mask)
        if need is False:
            return None
        if mo.online[i]:
            return NONE, 0
        d = mo.dur[i]
        bits = mo.room_bits[i]
        for q in range(d):
            bits &= ~self.rfull[s + q]
        best = None
        while bits:
            low = bits & -bits
            bits ^= low
            k = low.bit_length() - 1
            if mo.w["room_waste_10"] * (max(0, mo.cap[k] - mo.need[i]) // 10) >= bound:
                break
            if need is not None and mo.bld[k] != need:
                continue
            if any(self.rocc[k * mo.S + s + q] & mask for q in range(d)):
                continue
            c = self.room_cost(i, k, s, mask)
            if c < bound:
                best, bound = (k, c), c
        return best

    def time_cost(self, i: int, s: int, vi: int) -> int:
        """The soft change of adding meeting i at slot s with variant vi, without its room."""
        mo = self.m
        mask = mo.variants[i][vi]
        day, p = divmod(s, mo.P)
        bits = ((1 << mo.dur[i]) - 1) << p
        t = mo.teacher[i]
        cost = mo.w["teacher_window"] * self._win_delta(self.prof[t * mo.D + day], mask, bits) if t != NONE else 0
        gw, sdc = mo.w["group_window"], mo.w["same_day_course"]
        course = mo.course[i]
        for r in mo.cells[i]:
            cost += gw * self._win_delta(self.prof[r * mo.D + day], mask, bits)
            if course is not None:
                cost += sdc * sum((mask & x).bit_count() for x in self.course_day.get((r, day, course), ()))
        return cost + self._hours_delta(i, vi, day, 1)

    def best_value(self, i: int):
        """The cheapest feasible value of meeting i as (value index, room, cost), or None."""
        mo = self.m
        best = None
        bound = float("inf")
        for j, (s, vi, stat) in enumerate(mo.values[i]):
            if stat >= bound:
                break
            mask = mo.variants[i][vi]
            if not self.time_ok(i, s, mask):
                continue
            c = stat + self.time_cost(i, s, vi)
            if c >= bound:
                continue
            room = self.pick_room(i, s, mask, bound - c)
            if room is not None and c + room[1] < bound:
                best, bound = (j, room[0], c + room[1]), c + room[1]
        return best

    # ---------------------------------------------------------------- changes
    def add(self, i: int, j: int, k: int) -> None:
        mo = self.m
        s, vi, stat = mo.values[i][j]
        mask = mo.variants[i][vi]
        self.soft += stat + self.time_cost(i, s, vi) + self.room_cost(i, k, s, mask)
        d = mo.dur[i]
        day, p = divmod(s, mo.P)
        bits = ((1 << d) - 1) << p
        for r in self._resources(i):
            for q in range(d):
                self.occ[r * mo.S + s + q] ^= mask
                self.holders.setdefault(r * mo.S + s + q, []).append(i)
            self._prof_add(r * mo.D + day, mask, bits)
            if mo.is_cell[r] or self.max_week_t:
                self._count_add(self.weekc[r], mask, d)
        if mo.course[i] is not None:
            for r in mo.cells[i]:
                self.course_day.setdefault((r, day, mo.course[i]), []).append(mask)
        if k != NONE:
            for q in range(d):
                x = k * mo.S + s + q
                assert not self.rocc[x] & mask, "a room taken twice"     # XOR below would free the other holder's weeks
                self.rocc[x] ^= mask
                self.rholders.setdefault(x, []).append(i)
                if self.rocc[x] == mo.full:
                    self.rfull[s + q] |= 1 << k
        self.unit_sum[mo.unit[i]] += mo.hours[i][vi][day]
        self.assign[i] = (j, k)
        del self.open[bisect.bisect_left(self.open, i)]
        self.mask_of[i] = mask
        self.bld_of[i] = mo.bld[k] if k != NONE else None
        self.unplaced_pairs -= mo.pairs[i]

    def remove(self, i: int) -> tuple[int, int]:
        mo = self.m
        a = self.assign[i]
        assert a is not None
        j, k = a
        s, vi, stat = mo.values[i][j]
        mask = mo.variants[i][vi]
        d = mo.dur[i]
        day, p = divmod(s, mo.P)
        bits = ((1 << d) - 1) << p
        self.assign[i] = None
        bisect.insort(self.open, i)
        self.unit_sum[mo.unit[i]] -= mo.hours[i][vi][day]
        for r in self._resources(i):
            for q in range(d):
                self.occ[r * mo.S + s + q] ^= mask
                self.holders[r * mo.S + s + q].remove(i)
            self._prof_remove(r * mo.D + day, mask, bits)
            if mo.is_cell[r] or self.max_week_t:
                self._count_add(self.weekc[r], mask, -d)
        if mo.course[i] is not None:
            for r in mo.cells[i]:
                self.course_day[(r, day, mo.course[i])].remove(mask)
        if k != NONE:
            for q in range(d):
                x = k * mo.S + s + q
                self.rocc[x] ^= mask
                self.rholders[x].remove(i)
                self.rfull[s + q] &= ~(1 << k)
        self.soft -= stat + self.time_cost(i, s, vi) + self.room_cost(i, k, s, mask)
        self.mask_of[i] = 0
        self.bld_of[i] = None
        self.unplaced_pairs += mo.pairs[i]
        return j, k

    def score(self) -> list[int]:
        return [self.unplaced_pairs, self.soft]

    # ---------------------------------------------------------------- ejection (construction)
    def clashing(self, i: int, s: int, mask: int) -> list[int]:
        out: set[int] = set()
        mo = self.m
        for r in self._resources(i):
            for q in range(mo.dur[i]):
                out.update(x for x in self.holders.get(r * mo.S + s + q, ()) if self.mask_of[x] & mask)
        return sorted(out)

    def place_with_ejection(self, i: int, movable: Callable[[int], bool]) -> list[int] | None:
        """Place meeting i by unassigning the cheapest set of movable meetings in its way; the ejected meetings, or None."""
        mo = self.m
        cands = []
        for j, (s, vi, stat) in enumerate(mo.values[i]):
            c = self.clashing(i, s, mo.variants[i][vi])
            if all(movable(x) for x in c):
                cands.append((len(c) + sum(self.ejected[x] for x in c if x < mo.N), stat, j, c))
        cands.sort(key=lambda x: (x[0], x[1], x[2]))
        for _, _, j, c in cands[:EJECT_TRIES]:
            s, vi, _ = mo.values[i][j]
            mask = mo.variants[i][vi]
            old = [(x, self.remove(x)) for x in c]
            out = [x for x, _ in old]
            if self.time_ok(i, s, mask):
                room = self.pick_room(i, s, mask)
                if room is None and not mo.online[i]:         # free the smallest fitting room of movable meetings
                    room, extra = self._eject_room(i, s, mask, movable)
                    out += [x for x, _ in extra]
                    old += extra
                if room is not None:
                    self.add(i, j, room[0])
                    return out
            for x, (jx, kx) in reversed(old):
                self.add(x, jx, kx)
        return None

    def _eject_room(self, i: int, s: int, mask: int, movable: Callable[[int], bool]):
        mo = self.m
        bits = mo.room_bits[i]
        while bits:
            low = bits & -bits
            bits ^= low
            k = low.bit_length() - 1
            hold = sorted({x for q in range(mo.dur[i]) for x in self.rholders.get(k * mo.S + s + q, ()) if self.mask_of[x] & mask})
            if not hold or not all(movable(x) for x in hold):
                continue
            extra = [(x, self.remove(x)) for x in hold]
            room = self.pick_room(i, s, mask)
            if room is not None:
                return room, extra
            for x, (jx, kx) in reversed(extra):
                self.add(x, jx, kx)
        return None, []


# ---------------------------------------------------------------- runs
def _new_state(model: Model, seed: int, budget: int) -> dict:
    rng = random.Random(seed)
    v, internal, g = rng.getstate()
    heap = [[model.rank[i], i] for i in range(model.N) if i not in model.locked]
    heapq.heapify(heap)
    return {"phase": "locked", "it": 0, "budget": budget, "steps": 0, "rng": [v, list(internal), g], "assign": [None] * model.N,
            "best": None, "best_score": None, "ejected": [0] * model.N, "heap": heap, "unplaced": [], "last_improve": 0,
            "stopped": None, "locked_failed": []}


def _load(model: Model, state: dict) -> tuple[Search, random.Random]:
    se = Search(model)
    se.ejected = list(state["ejected"])
    for i, a in enumerate(state["assign"]):
        if a is not None:
            se.add(i, a[0], a[1])
    rng = random.Random()
    v, internal, g = state["rng"]
    rng.setstate((v, tuple(internal), g))
    return se, rng


def _dump(se: Search, rng: random.Random, state: dict) -> dict:
    v, internal, g = rng.getstate()
    return {**state, "assign": [list(a) if a is not None else None for a in se.assign], "ejected": list(se.ejected),
            "rng": [v, list(internal), g], "score": se.score()}


def run(model: Model, state: dict | None = None, *, until_iter: int | None = None, seed: int = 0, budget: int | None = None,
        deadline: float | None = None, now: Callable[[], float] | None = None, should_stop: Callable[[], bool] | None = None) -> dict:
    """Work the search from ``state`` (None: a new run with ``seed`` and an iteration ``budget``, by default the
    setting) up to improvement iteration ``until_iter`` (default: the budget), or until ``now() >= deadline`` or
    ``should_stop()``; the new state (JSON). ``state["phase"]`` is "done" once the budget is spent or the search stalls."""
    if state is None:
        state = _new_state(model, seed, budget if budget is not None else model.settings["solver"]["iter_budget"])
    until_iter = state["budget"] if until_iter is None else min(until_iter, state["budget"])
    se, rng = _load(model, state)
    st = model.settings["solver"]
    limit = st["construct_ejections"]
    unplaced = set(state["unplaced"])

    def stop(k: int) -> bool:
        return (k & 15) == 0 and ((deadline is not None and now is not None and now() >= deadline)
                                  or (should_stop is not None and should_stop()))

    if state["phase"] == "locked":
        failed = []
        for i, (s, mask, room_id) in sorted(model.locked.items()):
            vi = model.variants[i].index(mask) if mask in model.variants[i] else -1
            j = model.value_at[i].get((s, vi))
            ok = j is not None and se.time_ok(i, s, mask)
            k = model.room_index.get(room_id, NONE) if room_id is not None else NONE
            # a lock keeps its exact value, room included: an online meeting with a room, or an in-person one without
            # (the unit's mode changed after the lock), fails and stays unplaced as the checker would flag it
            if ok and model.online[i]:
                ok = room_id is None
            elif ok:
                ok = (k != NONE and model.room_bits[i] >> k & 1 == 1 and se.required_building(i, s, mask) in (None, model.bld[k])
                      and not any(se.rocc[k * model.S + s + q] & mask for q in range(model.dur[i])))
            if ok and j is not None:
                se.add(i, j, k)
            else:
                failed.append(i)
        state = {**state, "phase": "construct", "locked_failed": failed}
        unplaced.update(failed)

    def movable(x: int) -> bool:          # a repair never ejects a kept meeting: only the annealing may move one, at its cost
        return x < model.N and x not in model.locked and se.ejected[x] < limit and not (model.repair and model.ref[x] is not None)

    if state["phase"] == "construct":
        heap = state["heap"]
        k = state["steps"]
        while heap:
            if stop(k):
                break
            k += 1
            _, i = heapq.heappop(heap)
            if se.assign[i] is not None:
                continue
            best = se.best_value(i)
            if best is not None:
                se.add(i, best[0], best[1])
                unplaced.discard(i)
                continue
            out = se.place_with_ejection(i, movable) if se.ejected[i] < limit else None
            if out is None:
                unplaced.add(i)
                continue
            unplaced.discard(i)
            for x in out:
                se.ejected[x] += 1
                heapq.heappush(heap, [model.rank[x] - 50 * se.ejected[x], x])
        state = {**state, "heap": heap, "steps": k}
        if not heap:
            state["phase"] = "improve"
            state["best"] = [list(a) if a else None for a in se.assign]
            state["best_score"] = se.score()
    if state["phase"] == "improve":
        state = _improve(model, se, rng, state, until_iter, stop)
    state["unplaced"] = sorted(i for i in range(model.N) if se.assign[i] is None)
    return _dump(se, rng, state)


def _improve(model: Model, se: Search, rng: random.Random, state: dict, until_iter: int, stop) -> dict:
    st = model.settings["solver"]
    movable = [i for i in range(model.N) if i not in model.locked and model.values[i]]
    best_score = state["best_score"]
    best = state["best"]
    last = state["last_improve"]
    it = state["it"]
    total = max(1, state["budget"])
    stopped = None
    while it < until_iter:
        if stop(it):
            stopped = "deadline"
            break
        if it - last >= st["stall"]:
            stopped = "stall"
            break
        temp = T0 * (1 - it / total) ** 2
        open_ = ([i for i in se.open if model.values[i] and i not in model.locked]
                 if it % 4 == 3 and se.unplaced_pairs else [])
        before = se.score()
        if open_:
            changed = _ruin(model, se, rng, open_)
        elif it % 4 == 2:
            changed = _swap(model, se, rng, movable)
        else:
            changed = _move(model, se, rng, movable)
        if changed is not None:
            after = se.score()
            delta = after[1] - before[1]
            keep = after[0] < before[0] or (after[0] == before[0] and (delta <= 0 or rng.random() < _accept(delta, temp)))
            if not keep:
                for x in sorted(changed):
                    if se.assign[x] is not None:
                        se.remove(x)
                for x in sorted(changed):
                    if changed[x] is not None:
                        se.add(x, *changed[x])
            elif after < best_score:
                best_score, best, last = after, [list(a) if a else None for a in se.assign], it
        it += 1
    else:
        stopped = "budget" if it >= state["budget"] else None
    if stopped in ("budget", "stall"):
        # the run ends on its best state
        for i in range(model.N):
            if se.assign[i] is not None:
                se.remove(i)
        for i, a in enumerate(best):
            if a is not None:
                se.add(i, a[0], a[1])
        # a last pass: a meeting the moves made room for is placed now (so no unplaced meeting has a free value)
        for i in sorted(range(model.N), key=lambda x: model.rank[x]):
            if se.assign[i] is None and i not in model.locked:
                found = se.best_value(i)
                if found is not None:
                    se.add(i, found[0], found[1])
        best, best_score = [list(a) if a else None for a in se.assign], se.score()
        state = {**state, "phase": "done"}
    return {**state, "it": it, "best": best, "best_score": best_score, "last_improve": last, "stopped": stopped}


def _accept(delta: int, temp: float) -> float:
    """The probability of taking a worse state: 1 / (1 + x + x^2/2 + x^3/6), x = delta / T, close to exp(-x) but made
    of + - * / only, so it is the same number on every platform."""
    if temp <= 1e-9:
        return 0.0
    x = delta / temp
    return 1.0 / (1.0 + x + x * x / 2 + x * x * x / 6)


def _pick(rng: random.Random, xs: list):
    return xs[int(rng.random() * len(xs))]


def _move(model: Model, se: Search, rng: random.Random, movable: list[int]):
    """M1: one meeting to another value of its domain; the changed meetings with their old values, or None."""
    if not movable:
        return None
    i = _pick(rng, movable)
    old = se.assign[i]
    if old is None:
        return None
    vals = model.values[i]
    se.remove(i)
    best = None
    bound = float("inf")
    for _ in range(SAMPLE):
        j = int(rng.random() * len(vals))
        s, vi, stat = vals[j]
        if j == old[0] or stat >= bound:
            continue
        mask = model.variants[i][vi]
        if not se.time_ok(i, s, mask):
            continue
        c = stat + se.time_cost(i, s, vi)
        if c >= bound:
            continue
        room = se.pick_room(i, s, mask, bound - c)
        if room is not None:
            best, bound = (j, room[0]), c + room[1]
    if best is None:
        se.add(i, *old)
        return None
    se.add(i, *best)
    return {i: old}


def _swap(model: Model, se: Search, rng: random.Random, movable: list[int]):
    """M2: two meetings that share a teacher or a group cell exchange their slots."""
    if not movable:
        return None
    i = _pick(rng, movable)
    nb = [x for x in model.neighbours[i] if x not in model.locked]
    if not nb:
        return None
    x = _pick(rng, nb)
    oi, ox = se.assign[i], se.assign[x]
    if oi is None or ox is None:
        return None
    si, vi_, _ = model.values[i][oi[0]]
    sx, vx, _ = model.values[x][ox[0]]
    ji, jx = model.value_at[i].get((sx, vi_)), model.value_at[x].get((si, vx))
    if ji is None or jx is None or si == sx:
        return None
    se.remove(i)
    se.remove(x)
    for a, j in ((i, ji), (x, jx)):
        s, v, _ = model.values[a][j]
        mask = model.variants[a][v]
        room = se.pick_room(a, s, mask) if se.time_ok(a, s, mask) else None
        if room is None:
            for b in (i, x):
                if se.assign[b] is not None:
                    se.remove(b)
            se.add(i, *oi)
            se.add(x, *ox)
            return None
        se.add(a, j, room[0])
    return {i: oi, x: ox}


def _ruin(model: Model, se: Search, rng: random.Random, open_: list[int]):
    """M5: free up to lns_k meetings around an unplaced one, place it first, then put the others back greedily."""
    u = _pick(rng, open_)
    k = model.settings["solver"]["lns_k"]
    around = [x for x in model.neighbours[u] if x not in model.locked and se.assign[x] is not None]
    if around:
        start = int(rng.random() * len(around))
        around = (around[start:] + around[:start])[: k - 1]
    changed = {x: se.assign[x] for x in around}
    changed[u] = None
    for x in around:
        se.remove(x)
    for x in [u, *sorted(around, key=lambda y: model.rank[y])]:
        best = se.best_value(x)
        if best is not None:
            se.add(x, best[0], best[1])
    return changed


# ---------------------------------------------------------------- results and explanations
def _placements(model: Model, se: Search) -> list[dict]:
    out = []
    for i, a in enumerate(se.assign):
        if a is None:
            continue
        m = model.meetings[i]
        s, vi, _ = model.values[i][a[0]]
        day, p = divmod(s, model.P)
        out.append({"key": m["key"], "unit_id": m["unit_id"], "part": m["part"], "weekday": model.days[day], "period": p + 1,
                    "duration": m["duration"], "weeks": domain.week_text(model.variants[i][vi], model.n),
                    "room_id": model.rooms[a[1]]["id"] if a[1] != NONE else None, "locked": i in model.locked})
    return out


def explain(model: Model, se: Search, i: int) -> dict:
    """Why meeting i has no value: for every slot of its grid the first blocking reason, counted by code, with the
    meetings in the way most often (at most 3)."""
    mo = model
    m = mo.meetings[i]
    counts: dict[str, int] = {}
    blockers: dict[str, dict[str, int]] = {}
    if i in mo.locked:      # the search never moves a locked meeting: only its locked value explains it
        s, mask, _ = mo.locked[i]
        reasons = [{"code": "locked_infeasible", "slots": 1, "with": []}]
        vals = [(j, vi) for j, (ss, vi, _) in enumerate(mo.values[i]) if ss == s and mo.variants[i][vi] == mask]
        code, who = _slot_reason(mo, se, i, s, vals) if 0 <= s < mo.S else ("day", [])
        if code != "free":
            reasons.append({"code": code, "slots": 1, "with": sorted({mo.meetings[x]["key"] if x < mo.N else mo.obstacles[x - mo.N]["key"]
                                                                       for x in who})[:3]})
        return {"key": m["key"], "reasons": reasons}
    for s in range(mo.S):
        day, p = divmod(s, mo.P)
        if p + mo.dur[i] > mo.P:
            continue
        vals = [(j, vi) for j, (ss, vi, _) in enumerate(mo.values[i]) if ss == s]
        code, who = _slot_reason(mo, se, i, s, vals)
        counts[code] = counts.get(code, 0) + 1
        for x in who:
            key = mo.meetings[x]["key"] if x < mo.N else mo.obstacles[x - mo.N]["key"]
            blockers.setdefault(code, {})[key] = blockers.setdefault(code, {}).get(key, 0) + 1
    reasons = [{"code": c, "slots": n, "with": [k for k, _ in sorted(blockers.get(c, {}).items(), key=lambda kv: (-kv[1], kv[0]))[:3]]}
               for c, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    return {"key": m["key"], "reasons": reasons}


def _slot_reason(mo: Model, se: Search, i: int, s: int, vals: list[tuple[int, int]]) -> tuple[str, list[int]]:
    if not mo.variants[i]:
        return "blocked_weeks", []
    if not vals:
        return "slot_rules", []          # shift, fixed slot or the teacher's unavailable cells
    if not mo.online[i] and not mo.room_bits[i]:
        return "no_room", []
    rank = ["teacher_busy", "group_busy", "day_limit", "week_hours", "travel", "rooms_busy", "free"]
    best: tuple[int, str, list[int]] = (-1, "teacher_busy", [])
    for _, vi in vals:
        mask = mo.variants[i][vi]
        who = se.clashing(i, s, mask)
        if who:
            t = mo.teacher[i]
            code = "teacher_busy" if t != NONE and any(x in se.holders.get(t * mo.S + s + q, ()) for x in who for q in range(mo.dur[i])) else "group_busy"
        elif not se.time_ok(i, s, mask):
            code = "day_limit" if _day_full(mo, se, i, s, mask) else "week_hours"
        elif se.required_building(i, s, mask) is False:
            code = "travel"
        elif se.pick_room(i, s, mask) is None:
            code = "rooms_busy"
            who = sorted({x for q in range(mo.dur[i]) for k in range(len(mo.rooms)) if mo.room_bits[i] >> k & 1
                          for x in se.rholders.get(k * mo.S + s + q, ()) if se.mask_of[x] & mask})
        else:
            code = "free"
        if rank.index(code) > best[0]:
            best = (rank.index(code), code, who)
    return best[1], best[2]


def _day_full(mo: Model, se: Search, i: int, s: int, mask: int) -> bool:
    day = s // mo.P
    for r in se._resources(i):
        limit = se.max_g if mo.is_cell[r] else se.max_t
        if any(wm & mask and pb.bit_count() + mo.dur[i] > limit for wm, pb in se.prof[r * mo.D + day]):
            return True
    return False


def result(model: Model, state: dict) -> dict:
    """Placements (the best state), unplaced meetings with their reasons, excluded units, the score and run counters."""
    best = state.get("best") or state["assign"]
    se, _ = _load(model, {**state, "assign": best})
    unplaced = [i for i in range(model.N) if se.assign[i] is None]
    return {"placements": _placements(model, se), "unplaced": [{**explain(model, se, i), "unit_id": model.meetings[i]["unit_id"]}
                                                               for i in unplaced],
            "excluded": list(model.excluded), "score": {"unplaced_pairs": se.unplaced_pairs, "soft": se.soft},
            "iterations": state["it"], "stopped": state.get("stopped"),
            "counts": {"meetings": model.N, "placed": model.N - len(unplaced), "unplaced": len(unplaced),
                       "excluded": len(model.excluded), "units": len(model.problem["units"])}}
