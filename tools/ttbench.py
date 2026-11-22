"""Timetable solver bench (tasks/todo.md, Task 48): a synthetic term of one department, or of many, and the solver's
timings against the targets of docs/perf/timetable.md.

    python tools/ttbench.py [--units 1250] [--groups 300] [--teachers 90] [--rooms 60] [--seed 1] [--iters 50000]

The instance follows the shape of the real Forma №3 files (hours by kind, groups per unit, students per group,
teachers' loads, timetable-inputs §1) with synthetic ids only: no name, no code and no cell of a real file. Courses
have a lecture for a stream of 1 to 6 groups, a seminar per group and sometimes a lab; groups have a shift and a home
building; some teachers have unavailable and undesired cells; a few groups have practice weeks.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from zeka.core import tenant  # noqa: E402
from zeka.modules.timetable import domain, solver  # noqa: E402

LECTURE_H = [(30, 85), (45, 7), (15, 5), (60, 1), (14, 1), (20, 1)]
SEMINAR_H = [(15, 70), (30, 27), (7.5, 2), (60, 1)]
LAB_H = [(15, 57), (30, 32), (60, 6), (10, 3), (6, 2)]
STREAM = [(1, 60), (2, 20), (3, 12), (4, 4), (5, 2), (6, 2)]


def _weighted(rng, table):
    total = sum(w for _, w in table)
    x = rng.random() * total
    for v, w in table:
        x -= w
        if x < 0:
            return v
    return table[-1][0]


def synthetic(units: int = 1250, groups: int = 300, teachers: int = 90, rooms: int = 60, seed: int = 1,
              weeks: int = 15, buildings: int = 2) -> dict:
    """A solver problem (the shape ``solver.prepare`` takes) of a synthetic department-term."""
    import random
    rng = random.Random(seed)
    settings = copy.deepcopy(tenant.DEFAULTS["timetable"])
    gs: list[dict] = [{"id": 1000 + g, "shift": "morning" if g % 20 < 12 else ("afternoon" if g % 20 < 19 else None),
           "home_building_id": 1 + g % buildings, "size": 8 + rng.randrange(23)} for g in range(groups)]
    n_halls, n_labs, n_comp = max(2, rooms // 8), max(1, rooms // 8), max(1, rooms // 15)
    rs = []
    for k in range(rooms):
        if k < n_halls:
            kind, cap = "lecture_hall", (160 if k < 2 else 120 if k < 4 else 80)
        elif k < n_halls + n_labs:
            kind, cap = "lab", 32
        elif k < n_halls + n_labs + n_comp:
            kind, cap = "computer_lab", 32
        else:
            kind, cap = "classroom", 32 + 4 * (k % 3)
        rs.append({"id": 500 + k, "kind": kind, "capacity": cap, "building_id": 1 + k % buildings, "schedulable": 1, "dedicated": 0})
    # teachers' loads are uneven: a few carry much more than the median
    weight = [2 if t % 10 == 0 else 1 for t in range(teachers)]
    tids = [2000 + t for t in range(teachers)]

    def teacher():
        if rng.random() < 0.03:
            return None                                           # a vacancy: placed without a teacher
        return tids[_pick_weighted(rng, weight)]

    out: list[dict] = []
    course = 0
    order = sorted(range(groups), key=lambda g: (str(gs[g]["shift"]), g))     # a stream's groups mostly share a shift
    pos = 0
    while len(out) < units:
        course += 1
        k = _weighted(rng, STREAM)
        stream: list[int] = []
        for _ in range(k):
            stream.append(gs[order[pos % groups]]["id"])
            pos += 1
        stream = sorted(set(stream))
        lect = teacher()
        sizes = {g["id"]: g["size"] for g in gs}
        out.append({"id": len(out) + 1, "course_id": course, "kind": "lecture", "teacher_id": lect, "subgroup": None,
                    "groups": stream, "hours": _weighted(rng, LECTURE_H), "students": sum(sizes[g] for g in stream)})
        for g in stream:
            if len(out) >= units:
                break
            out.append({"id": len(out) + 1, "course_id": course, "kind": "seminar", "teacher_id": lect if rng.random() < 0.3 else teacher(),
                        "subgroup": None, "groups": [g], "hours": _weighted(rng, SEMINAR_H), "students": sizes[g]})
            if rng.random() < 0.25 and len(out) < units:
                out.append({"id": len(out) + 1, "course_id": course, "kind": "lab", "teacher_id": teacher(), "subgroup": None,
                            "groups": [g], "hours": _weighted(rng, LAB_H), "students": sizes[g]})
    avail = []
    for t in tids:
        if rng.random() < 0.2:
            for _ in range(3 + rng.randrange(4)):
                avail.append({"subject_type": "teacher", "subject_id": t, "weekday": 1 + rng.randrange(6),
                              "period": 1 + rng.randrange(6), "weeks": "all", "level": rng.choice(["unavailable", "undesired"])})
    cells: dict[tuple, dict] = {}
    for a in avail:                                                # one row per cell, as tt_availability's unique index
        cells.setdefault((a["subject_id"], a["weekday"], a["period"]), a)
    avail = list(cells.values())
    blocks = [{"subject_type": "group", "subject_id": g["id"], "weeks": f"{weeks - 2}-{weeks}", "active": 1} for g in gs[::50]]
    return {"weeks": weeks, "lesson_times": domain.DEFAULT_TIMES, "settings": settings, "rooms": rs, "groups": gs,
            "units": out, "needs": [], "availability": avail, "blocks": blocks, "obstacles": [], "locked": [], "reference": []}


def _pick_weighted(rng, weight: list[int]) -> int:
    x = int(rng.random() * sum(weight))
    for i, w in enumerate(weight):
        x -= w
        if x < 0:
            return i
    return len(weight) - 1


def bench(problem: dict, iters: int, seed: int = 1) -> dict:
    """Timings (seconds) of the solver's phases on a problem, with the result's counts and the checker's verdict."""
    out: dict = {}
    t = time.perf_counter()
    model = solver.prepare(problem)
    pre = solver.precheck(model)
    out["prepare_s"] = round(time.perf_counter() - t, 3)
    t = time.perf_counter()
    state = solver.run(model, seed=seed, budget=iters, until_iter=0)
    out["construct_s"] = round(time.perf_counter() - t, 3)
    out["after_construct"] = state["score"]
    t = time.perf_counter()
    state = solver.run(model, state)
    out["improve_s"] = round(time.perf_counter() - t, 3)
    out["iterations"] = state["it"]
    res = solver.result(model, state)
    t = time.perf_counter()
    hard = domain.check(problem, res["placements"])
    card = domain.scorecard(problem, res["placements"])
    out["check_s"] = round(time.perf_counter() - t, 3)
    out.update(meetings=model.N, units=len(problem["units"]), placed=res["counts"]["placed"], unplaced=res["counts"]["unplaced"],
               excluded=res["counts"]["excluded"], hard=len(hard), soft=res["score"]["soft"], scorecard_soft=card["soft"],
               precheck=len(pre), stopped=res["stopped"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--units", type=int, default=1250)
    ap.add_argument("--groups", type=int, default=300)
    ap.add_argument("--teachers", type=int, default=90)
    ap.add_argument("--rooms", type=int, default=60)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--iters", type=int, default=50_000)
    a = ap.parse_args()
    problem = synthetic(a.units, a.groups, a.teachers, a.rooms, a.seed)
    print(json.dumps(bench(problem, a.iters, a.seed), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
