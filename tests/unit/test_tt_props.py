"""Timetable solver properties (tasks/todo.md, Task 48, slice 1) on randomized synthetic instances: no hard
violation ever (the independent checker and the clock-time clash rule agree), the same seed gives the same bytes and a
run cut in two equals one run, the solver's running cost equals the scorecard recomputed from scratch, an unplaced
meeting has no free value, nothing is lost, locked placements are kept, a repair moves nothing without a change, only
the changed teacher's meetings after one, and never a past week."""
import copy
import hashlib
import json
import random

import pytest

from zeka.core import tenant
from zeka.modules.timetable import domain, solver

KINDS = ["lecture", "seminar", "lab"]
HOURS = [6, 7.5, 10, 14, 15, 18, 30, 45, 60]


def instance(seed: int, units: int | None = None) -> dict:
    """A small random term: tight or loose rooms in one or two buildings, subgroups, odd/even and block weeks, shifts,
    availability, blocks, fixed slots, online and two-pair meetings, manual rows the run may not move."""
    rng = random.Random(seed)
    n = rng.choice([8, 12, 15, 16])
    P = rng.choice([4, 5, 6])
    st = copy.deepcopy(tenant.DEFAULTS["timetable"])
    st["days"] = sorted(rng.sample(range(1, 7), rng.choice([2, 3, 4, 6])))
    st["max_pairs_day_group"] = rng.choice([2, 3, 4])
    st["max_pairs_day_teacher"] = rng.choice([2, 3, 5])
    st["max_week_hours_group"] = rng.choice([8, 12, 30])
    st["max_week_pairs_teacher"] = rng.choice([None, None, 6])
    st["shifts"] = {"morning": list(range(1, min(4, P) + 1)), "afternoon": list(range(max(1, P - 2), P + 1))}
    if rng.random() < 0.3:
        st["fixed_slots"] = [{"weekday": st["days"][0], "period": 1, "groups": None}]
    tight = rng.random() < 0.5
    groups = [{"id": 10 + g, "shift": rng.choice([None, None, "morning", "afternoon"]), "home_building_id": rng.choice([None, 1, 2]),
               "size": rng.randrange(8, 31)} for g in range(rng.randrange(2, 9))]
    rooms = [{"id": 100 + r, "kind": rng.choice(["lecture_hall", "classroom", "classroom", "lab", "computer_lab"]),
              "capacity": rng.randrange(10, 40) if tight else rng.randrange(30, 120), "building_id": rng.choice([1, 2]),
              "schedulable": int(rng.random() > 0.1), "dedicated": int(rng.random() < 0.1)} for r in range(rng.randrange(2, 9))]
    teachers = [200 + t for t in range(rng.randrange(2, 8))]
    us, needs = [], []
    for u in range(units or rng.randrange(3, 60)):
        kind = rng.choice(KINDS)
        gs = sorted(rng.sample([g["id"] for g in groups], min(len(groups), rng.choice([1, 1, 1, 2, 3])) if kind == "lecture" else 1))
        us.append({"id": u + 1, "course_id": rng.randrange(1, 12), "kind": kind, "teacher_id": rng.choice(teachers) if rng.random() > 0.05 else None,
                   "subgroup": rng.choice([1, 2]) if kind == "lab" and rng.random() < 0.3 else None, "groups": gs if rng.random() > 0.03 else [],
                   "hours": rng.choice(HOURS) * n / 15, "students": rng.choice([None, 15 * len(gs), 25 * len(gs)])})
        if rng.random() < 0.25:
            needs.append({"unit_id": u + 1, "duration": 2 if rng.random() < 0.3 else 1, "mode": "online" if rng.random() < 0.3 else "in_person",
                          "room_ids": [rng.choice(rooms)["id"]] if rng.random() < 0.2 else None,
                          "pattern": rng.choice([None, None, ["1-4"], ["odd"], ["all", "even"]]),
                          "room_kinds": None, "need": rng.choice([None, None, 12])})
    avail = []
    for t in teachers:
        for _ in range(rng.randrange(0, 5)):
            avail.append({"subject_type": "teacher", "subject_id": t, "weekday": rng.choice(st["days"]), "period": rng.randrange(1, P + 1),
                          "weeks": rng.choice(["all", "odd", "1-4"]), "level": rng.choice(["unavailable", "undesired"])})
    for r in rooms:
        if rng.random() < 0.3:
            avail.append({"subject_type": "room", "subject_id": r["id"], "weekday": rng.choice(st["days"]), "period": rng.randrange(1, P + 1),
                          "weeks": "all", "level": "unavailable"})
    blocks = [{"subject_type": kind, "subject_id": sid, "weeks": rng.choice(["1-2", f"{n - 1}-{n}", "5"]), "active": 1}
              for kind, ids in (("group", [g["id"] for g in groups]), ("teacher", teachers), ("room", [r["id"] for r in rooms]))
              for sid in ids if rng.random() < 0.15]
    obstacles = [{"key": f"m{k}", "teacher_id": rng.choice(teachers + [None]), "groups": [[rng.choice(groups)["id"], None]],
                  "room_id": rng.choice(rooms)["id"], "weekday": rng.choice(st["days"]), "period": rng.randrange(1, P + 1),
                  "duration": 1, "weeks": rng.choice(["all", "odd"]), "online": False} for k in range(rng.randrange(0, 4))]
    return {"weeks": n, "lesson_times": domain.DEFAULT_TIMES[:P], "settings": st, "rooms": rooms, "groups": groups, "units": us,
            "needs": needs, "availability": avail, "blocks": blocks, "obstacles": obstacles, "locked": [], "reference": []}


def solve(problem: dict, seed: int = 1, iters: int = 300) -> tuple[solver.Model, dict, dict]:
    model = solver.prepare(problem)
    state = solver.run(model, seed=seed, budget=iters)
    return model, state, solver.result(model, state)


def rows(problem: dict, placements: list[dict]) -> list[dict]:
    """The timetable rows a publish would write (with the manual rows), in the clock-time shape of Task 19."""
    times = domain.lesson_times(problem)
    meet = {m["key"]: m for m in domain.meetings_of(problem)[0]}
    out = []
    for p in placements:
        m = meet[p["key"]]
        out.append({"id": p["key"], "weekday": p["weekday"], "start": times[p["period"] - 1][0], "end": times[p["period"] + p["duration"] - 2][1],
                    "weeks": p["weeks"], "room": p["room_id"], "teacher_id": m["teacher_id"], "groups": [(g, m["subgroup"]) for g in m["groups"]]})
    return out


SEEDS = range(200)


@pytest.mark.parametrize("chunk", [0, 1])
def test_no_hard_violation_ever(chunk):
    """Property 1, on 200 instances: the result, a state cut inside construction and a cancelled run all pass the checker;
    the clock-time rule finds no clash in the rows a publish would write; and the solver's running cost is the scorecard's."""
    for seed in SEEDS[chunk::2]:
        problem = instance(seed)
        model, state, res = solve(problem, seed)
        assert domain.check(problem, res["placements"]) == [], seed
        assert domain.conflicts_all(rows(problem, res["placements"])) == [], seed
        assert domain.scorecard(problem, res["placements"])["soft"] == res["score"]["soft"], seed
        calls = iter([False, True])
        cut = solver.run(model, seed=seed, budget=300, should_stop=lambda calls=calls: next(calls, True))
        part = solver.result(model, {**cut, "best": cut["assign"]})
        assert domain.check(problem, part["placements"]) == [], seed
        assert domain.scorecard(problem, part["placements"])["soft"] == part["score"]["soft"], seed
        cancelled = solver.run(model, seed=seed, budget=300, should_stop=lambda: True)
        assert domain.check(problem, solver.result(model, {**cancelled, "best": cancelled["assign"]})["placements"]) == []


def test_nothing_is_silent():
    """Property 5: every meeting is placed or unplaced with its reasons; every unit has meetings or is excluded."""
    for seed in SEEDS[:60]:
        problem = instance(seed)
        model, _, res = solve(problem, seed)
        c = res["counts"]
        assert c["placed"] + c["unplaced"] == c["meetings"] == model.N
        with_meetings = {m["unit_id"] for m in model.meetings}
        assert len(with_meetings) + c["excluded"] == len(problem["units"])
        assert all(u["reasons"] for u in res["unplaced"])
        assert {x["code"] for x in res["excluded"]} <= {"no_groups", "no_hours"}


def test_the_same_seed_gives_the_same_bytes_and_a_cut_run_equals_one_run():
    """Property 2: byte-identical results for one seed; N iterations equal N/2, a JSON round trip of the state, N/2."""
    for seed in SEEDS[:40]:
        problem = instance(seed)
        model = solver.prepare(problem)
        one = solver.run(model, seed=seed, budget=400)
        again = solver.run(solver.prepare(json.loads(json.dumps(problem))), seed=seed, budget=400)
        assert json.dumps(one, sort_keys=True) == json.dumps(again, sort_keys=True), seed
        half = solver.run(model, seed=seed, budget=400, until_iter=200)
        rest = solver.run(model, json.loads(json.dumps(half)), until_iter=400)
        assert json.dumps(solver.result(model, rest), sort_keys=True) == json.dumps(solver.result(model, one), sort_keys=True), seed


def test_a_run_stopped_by_the_clock_resumes_to_the_same_result():
    problem = instance(7, units=50)
    model = solver.prepare(problem)
    one = solver.result(model, solver.run(model, seed=3, budget=500))
    clock = iter(range(10_000))
    state = None
    for _ in range(200):                      # a deadline that passes every few checks, as a job's chunks would
        start = next(clock)
        state = solver.run(model, state, seed=3, budget=500, deadline=start + 3, now=lambda: next(clock))
        if state["phase"] == "done":
            break
    assert state is not None and state["phase"] == "done"
    assert json.dumps(solver.result(model, state), sort_keys=True) == json.dumps(one, sort_keys=True)


GOLDEN = "35fed9498078c8ad6a7011a06d91dda819f4210a3c8eb5e93af09a7a526ec14c"


def test_golden_signature():
    """The same bytes on every Python version CI runs (3.10-3.13): ints only and rng.random() only."""
    problem = instance(11, units=40)
    _, _, res = solve(problem, seed=5, iters=500)
    sig = hashlib.sha256(json.dumps(res, sort_keys=True).encode()).hexdigest()
    assert sig == GOLDEN, sig


def test_an_unplaced_meeting_has_no_free_value():
    """Property 4 (brute force, at most 12 meetings): no value of an unplaced meeting, in any room, passes the checker."""
    tried = 0
    for seed in range(300):
        problem = instance(1000 + seed, units=8)
        model, _, res = solve(problem, seed)
        if model.N > 12 or not res["unplaced"]:
            continue
        tried += 1
        meet = {m["key"]: m for m in model.meetings}
        times = len(domain.lesson_times(problem))
        for u in res["unplaced"]:
            m = meet[u["key"]]
            for wd in problem["settings"]["days"]:
                for p in range(1, times + 1):
                    for mask in m["variants"]:
                        for room in [None, *(r["id"] for r in problem["rooms"])]:
                            cand = {"key": m["key"], "unit_id": m["unit_id"], "part": m["part"], "weekday": wd, "period": p,
                                    "duration": m["duration"], "weeks": domain.week_text(mask, problem["weeks"]), "room_id": room}
                            assert domain.check(problem, [*res["placements"], cand]), (seed, cand)
    assert tried >= 5


def test_locked_placements_are_kept():
    for seed in SEEDS[:40]:
        problem = instance(seed)
        _, _, res = solve(problem, seed)
        rng = random.Random(seed)
        keep = [p for p in res["placements"] if rng.random() < 0.4]
        again = {**problem, "locked": [{k: p[k] for k in ("key", "weekday", "period", "weeks", "room_id")} for p in keep]}
        _, _, res2 = solve(again, seed + 1)
        got = {p["key"]: p for p in res2["placements"]}
        for p in keep:
            assert {k: got[p["key"]][k] for k in ("weekday", "period", "weeks", "room_id")} == \
                   {k: p[k] for k in ("weekday", "period", "weeks", "room_id")}, (seed, p["key"])
            assert got[p["key"]]["locked"]
        assert domain.check(again, res2["placements"]) == []


def test_a_locked_value_that_breaks_a_rule_stays_unplaced_with_its_reason():
    problem = instance(3, units=10)
    _, _, res = solve(problem, 1)
    p = res["placements"][0]
    bad = {"key": p["key"], "weekday": 7, "period": 1, "weeks": p["weeks"], "room_id": p["room_id"]}       # Sunday: no teaching day
    problem["settings"]["days"] = [d for d in problem["settings"]["days"] if d != 7]
    _, _, res2 = solve({**problem, "locked": [bad]}, 1)
    assert p["key"] not in {x["key"] for x in res2["placements"]}


def _moved(a: list[dict], b: list[dict]) -> set[str]:
    old = {p["key"]: (p["weekday"], p["period"], p["weeks"], p["room_id"]) for p in a}
    return {p["key"] for p in b if p["key"] in old and old[p["key"]] != (p["weekday"], p["period"], p["weeks"], p["room_id"])}


def test_a_repair_without_a_change_moves_nothing():
    """Property 6, first half: a repair locks every placement that is not dirty; with nothing dirty, 0 moved. Without
    the locks, the reference alone (1 000 per moved meeting) keeps a complete timetable where it is."""
    complete = 0
    for seed in SEEDS[:60]:
        problem = instance(seed)
        _, _, res = solve(problem, seed)
        ref = [{k: p[k] for k in ("key", "weekday", "period", "weeks", "room_id")} for p in res["placements"]]
        _, _, locked = solve({**problem, "reference": ref, "locked": ref, "repair": True}, seed + 7)
        assert _moved(res["placements"], locked["placements"]) == set(), seed
        assert {p["key"] for p in locked["placements"]} >= {p["key"] for p in res["placements"]}
        if not res["unplaced"]:
            complete += 1
            _, _, soft = solve({**problem, "reference": ref, "repair": True}, seed + 7)
            assert _moved(res["placements"], soft["placements"]) == set(), seed
    assert complete >= 3


def test_a_repair_after_one_teacher_s_new_cell_moves_only_that_teacher_s_meetings():
    """Property 6, second half: everything not dirty is locked; a new unavailable cell of one teacher moves only the
    meetings of that teacher, and never a locked one; property 7: a repair never touches a week before from_week."""
    done = 0
    for seed in SEEDS[:60]:
        problem = instance(seed)
        model, _, res = solve(problem, seed)
        teaching = [p for p in res["placements"] if model.meetings[model.index[p["key"]]]["teacher_id"]]
        if not teaching:
            continue
        hit = teaching[0]
        teacher = model.meetings[model.index[hit["key"]]]["teacher_id"]
        mine = {m["key"] for m in model.meetings if m["teacher_id"] == teacher}
        changed = copy.deepcopy(problem)
        changed["availability"] = [a for a in changed["availability"]
                                   if (a["subject_type"], a["subject_id"], a["weekday"], a["period"]) != ("teacher", teacher, hit["weekday"], hit["period"])]
        changed["availability"].append({"subject_type": "teacher", "subject_id": teacher, "weekday": hit["weekday"], "period": hit["period"],
                                        "weeks": "all", "level": "unavailable"})
        keep = [{k: p[k] for k in ("key", "weekday", "period", "weeks", "room_id")} for p in res["placements"]]
        locked = [x for x in keep if x["key"] not in mine]
        changed.update(reference=keep, locked=locked, repair=True)
        _, _, rep = solve(changed, seed)
        moved = _moved(res["placements"], rep["placements"])
        assert hit["key"] not in {p["key"] for p in rep["placements"]} or hit["key"] in moved, seed
        assert moved <= mine, (seed, moved - mine)
        assert domain.check(changed, rep["placements"]) == [], seed
        # the past is frozen: a repair from week 3 places nothing in weeks 1 and 2
        past = {**changed, "from_week": 3, "locked": [], "reference": keep}
        _, _, late = solve(past, seed)
        assert all(domain.week_mask(p["weeks"], problem["weeks"]) & 0b11 == 0 for p in late["placements"]), seed
        assert domain.check(past, late["placements"]) == []
        done += 1
    assert done >= 40
