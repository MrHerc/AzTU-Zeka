"""Timetable solver review fixes (tasks/todo.md, Task 48, review of slices 1-3): a lock keeps its exact value (an online
meeting never takes a room, an in-person one never gets a room picked for it), manual rows on a day the run does not
use still count in the week limits and windows, a repair's kept locks pass the checker, precheck names a reserved room
and a teacher's available cells, and a locked meeting is explained by its lock only."""
import copy

from zeka.core import tenant
from zeka.modules.timetable import domain, solver

from .test_tt_props import instance, solve


def base(**kw) -> dict:
    st = copy.deepcopy(tenant.DEFAULTS["timetable"])
    st.update(kw.pop("st", {}))
    pr = {"weeks": 15, "lesson_times": domain.DEFAULT_TIMES[:6], "settings": st, "rooms": [], "groups": [], "units": [], "needs": [],
          "availability": [], "blocks": [], "obstacles": [], "locked": [], "reference": []}
    pr.update(kw)
    return pr


def R(i, kind="classroom", cap=30, ded=0):
    return {"id": i, "kind": kind, "capacity": cap, "building_id": 1, "schedulable": 1, "dedicated": ded}


def G(i, shift=None):
    return {"id": i, "shift": shift, "home_building_id": None, "size": 25}


def U(i, kind="seminar", t=200, g=(10,), h=30):
    return {"id": i, "course_id": i, "kind": kind, "teacher_id": t, "subgroup": None, "groups": list(g), "hours": h, "students": None}


ONE = {"days": [1], "shifts": {"x": [1]}}
LOCK = {"key": "1:0", "weekday": 1, "period": 1, "weeks": "all"}


def test_an_online_lock_with_a_room_never_takes_that_room():
    """F1: the lock was taken in person, then the unit went online. Taking the room XOR-ed a manual row's weeks away."""
    obst = [{"key": "row:9", "teacher_id": 209, "groups": [[19, None]], "room_id": 104, "weekday": 1, "period": 1, "duration": 1, "weeks": "all"}]
    pr = base(st=ONE, rooms=[R(104, "lecture_hall", 200)], groups=[G(11, "x"), G(12, "x"), G(19, "x")], obstacles=obst,
              units=[U(2, t=201, g=[11]), U(3, t=202, g=[12])], needs=[{"unit_id": 2, "mode": "online"}],
              locked=[{**LOCK, "key": "2:0", "room_id": 104}])
    _, _, res = solve(pr, iters=500)
    assert domain.check(pr, res["placements"]) == []
    assert [u["key"] for u in res["unplaced"]][0] == "2:0" and res["unplaced"][0]["reasons"][0]["code"] == "locked_infeasible"


def test_an_in_person_lock_without_a_room_fails_instead_of_picking_one():
    """F4: a lock taken while the unit was online, then the unit went in person: the checker wants the exact room."""
    pr = base(rooms=[R(100)], groups=[G(10)], units=[U(1)], locked=[{**LOCK, "room_id": None}])
    _, _, res = solve(pr, iters=500)
    assert res["placements"] == [] and res["unplaced"][0]["reasons"][0]["code"] == "locked_infeasible"
    assert domain.check(pr, res["placements"]) == []


def test_a_manual_row_off_the_teaching_days_counts_in_the_week_limits():
    """F2: a Saturday row with days Mon-Fri was dropped from the group's weekly hours; the checker still counted it."""
    pr = base(st={"days": [1, 2, 3, 4, 5]}, rooms=[R(100 + k) for k in range(3)], groups=[G(10)],
              units=[U(i, t=200 + i) for i in range(1, 16)],
              obstacles=[{"key": "row:1", "teacher_id": 299, "groups": [[10, None]], "room_id": None, "weekday": 6, "period": 1,
                          "duration": 1, "weeks": "all"}])
    _, _, res = solve(pr, iters=500)
    assert res["counts"]["placed"] == 14
    assert domain.check(pr, res["placements"]) == []
    assert domain.scorecard(pr, res["placements"])["soft"] == res["score"]["soft"]


def test_property_off_grid_rows_and_changed_locks():
    """F1, F2, F4 on random instances: manual rows on a day outside the grid, then every placement locked and the mode of
    every unit with needs flipped; the checker finds nothing and the running cost equals the scorecard."""
    for seed in range(80):
        problem = instance(seed)
        for k, o in enumerate(problem["obstacles"]):
            if k % 2 == 0:
                o["weekday"] = 7
        _, _, res = solve(problem, seed)
        assert domain.check(problem, res["placements"]) == [], seed
        assert domain.scorecard(problem, res["placements"])["soft"] == res["score"]["soft"], seed
        problem["locked"] = [{k: p[k] for k in ("key", "weekday", "period", "weeks", "room_id")} for p in res["placements"]]
        for nd in problem["needs"]:
            nd["mode"] = "in_person" if nd["mode"] == "online" else "online"
        _, _, again = solve(problem, seed)
        assert domain.check(problem, again["placements"]) == [], seed


def test_a_repair_keeps_its_locks_in_the_future_weeks():
    """F3: a repair from week 3 masks a lock with the future weeks; the checker compared it unmasked."""
    lock = [{**LOCK, "room_id": 100}]
    pr = base(rooms=[R(100)], groups=[G(10)], units=[U(1)], reference=lock, locked=lock, repair=True, from_week=3)
    _, _, res = solve(pr, iters=500)
    assert res["placements"][0]["weeks"] == "3-15" and domain.check(pr, res["placements"]) == []
    moved = [{**res["placements"][0], "period": 2}]
    assert [v["code"] for v in domain.check(pr, moved)] == ["locked"], "a moved lock is still flagged"


def test_precheck_names_a_reserved_room_and_a_teacher_s_free_cells():
    """F5: the only lab is dedicated to another unit; precheck said the room was too small. F6: the teacher's grid holds
    one free pair a week against two weekly meetings; precheck said nothing."""
    pr = base(rooms=[R(100, "lab", 30, ded=1)], groups=[G(10)], units=[U(1, "lab"), U(2, "lab", t=201)], needs=[{"unit_id": 2, "room_ids": [100]}])
    assert solver.precheck(solver.prepare(pr)) == [{"code": "room_reserved", "key": "1:0"}]
    pr["rooms"] = [R(100, "lab", 20)]
    pr["needs"] = []
    assert "no_room_capacity" in {x["code"] for x in solver.precheck(solver.prepare(pr))}, "a room that is too small is still that"
    un = [{"subject_type": "teacher", "subject_id": 200, "weekday": d, "period": p, "weeks": "all", "level": "unavailable"}
          for d in range(1, 7) for p in range(1, 7) if (d, p) != (2, 3)]
    pr = base(rooms=[R(100)], groups=[G(10)], units=[U(1, h=60)], availability=un)
    assert solver.precheck(solver.prepare(pr)) == [{"code": "teacher_overload", "teacher_id": 200, "pair_weeks": 30, "available": 15}]


def test_a_locked_meeting_is_explained_by_its_lock():
    """F7: two locks clash on the group; the second was explained as 'a free slot the search missed' over 35 slots."""
    pr = base(rooms=[R(100), R(101)], groups=[G(10)], units=[U(1), U(2, t=201)],
              locked=[{**LOCK, "room_id": 100}, {**LOCK, "key": "2:0", "room_id": 101}])
    _, _, res = solve(pr, iters=500)
    assert res["unplaced"] == [{"key": "2:0", "unit_id": 2, "reasons": [{"code": "locked_infeasible", "slots": 1, "with": []},
                                                                         {"code": "group_busy", "slots": 1, "with": ["1:0"]}]}]
