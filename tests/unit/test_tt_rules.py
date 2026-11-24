"""Timetable builder rules (tasks/todo.md, Task 48, slice 1): the week-set grammar, the weekly-pattern rule, every
hard rule of the independent checker (violated and not), the clock-time clash rule over a whole set, the planned
against form hours report, and the settings section's checks."""
import copy
import random

import pytest

from zeka.core import tenant
from zeka.modules.timetable import domain, solver

ODD, EVEN = "odd", "even"


# ---------------------------------------------------------------- week sets
def test_week_grammar_and_canonical_text():
    assert domain.week_mask("all", 4) == 0b1111 and domain.week_mask("odd", 4) == 0b0101 and domain.week_mask("even", 4) == 0b1010
    assert domain.week_mask("1-3,9", 10) == 0b100000111 and domain.week_mask(" 2 - 3 ", 5) == 0b110
    assert domain.week_mask("1-60", 15) == 0 and domain.week_mask("3-2", 15) == 0 and domain.week_mask("x", 15) == 0
    assert domain.week_mask(None, 15) == 0 and domain.week_mask("0", 15) == 0
    assert domain.week_mask("1-53", 15) == (1 << 15) - 1, "weeks after the term are cut"
    assert domain.week_text(0b1111, 4) == "all" and domain.week_text(0b0101, 4) == ODD and domain.week_text(0b1010, 4) == EVEN
    assert domain.week_text(0b100000111, 10) == "1-3,9" and domain.week_text(0, 10) == ""


def test_every_mask_round_trips():
    for n in range(1, 13):
        for mask in range(1 << n):
            assert domain.week_mask(domain.week_text(mask, n), n) == mask, (n, mask)
    rng = random.Random(4)
    for n in range(13, 21):
        for _ in range(3000):
            mask = int(rng.random() * (1 << n))
            assert domain.week_mask(domain.week_text(mask, n), n) == mask


def test_in_weeks_and_the_wider_grammar_in_the_task_19_rules():
    assert domain.in_weeks("1-8", 8) and not domain.in_weeks("1-8", 10) and domain.in_weeks("odd", 3) and not domain.in_weeks("even", 3)
    assert domain.in_weeks("all", 17) and not domain.in_weeks("all", 0)
    base = {"id": 1, "weekday": 1, "start": "09:00", "end": "10:20", "room": "r1", "teacher_id": None, "groups": []}
    assert domain.conflicts({**base, "id": 2, "weeks": "1-3"}, [{**base, "weeks": ODD}]) != [], "odd meets weeks 1-3 in weeks 1 and 3"
    assert domain.conflicts({**base, "id": 2, "weeks": "2"}, [{**base, "weeks": ODD}]) == []
    assert domain.conflicts({**base, "id": 2, "weeks": "garbage"}, [{**base, "weeks": ODD}]) != [], "an unknown text never hides a clash"


# ---------------------------------------------------------------- the weekly pattern
@pytest.mark.parametrize("hours, shape", [
    (6, "block3"), (8, "block4"), (10, "block5"), (7.5, "block4"), (14, "fortnight"), (15, "fortnight"), (18, "block9"),
    (20, "block10"), (24, "block12"), (30, "weekly"), (45, "weekly+fortnight"), (60, "2weekly")])
def test_the_pattern_table(hours, shape):
    full, odd, even = (1 << 15) - 1, domain.week_mask(ODD, 15), domain.week_mask(EVEN, 15)
    got = domain.pattern(hours, 15, 2)

    def block(n):
        return [((1 << n) - 1) << s for s in range(0, 15 - n + 1, n)]

    want = {"weekly": [[full]], "2weekly": [[full], [full]], "fortnight": [[odd, even]], "weekly+fortnight": [[full], [odd, even]]}.get(shape)
    if want is None:
        want = [block(int(shape[5:]))]
    assert got == want


def test_pattern_edges_and_override():
    assert domain.pattern(0, 15, 2) == [] and domain.pattern(-5, 15, 2) == [] and domain.pattern(None, 15, 2) == []
    assert domain.pattern("x", 15, 2) == [] and domain.pattern(float("nan"), 15, 2) == [] and domain.pattern(30, 0, 2) == []
    assert domain.pattern(0.5, 15, 2) == [], "a remainder under half a week is dropped"
    assert domain.pattern(30, 15, 2, duration=2) == [[domain.week_mask(ODD, 15), domain.week_mask(EVEN, 15)]]
    assert domain.pattern(30, 15, 2, override=["1-12", "odd"]) == [[(1 << 12) - 1], [domain.week_mask(ODD, 15)]]
    assert domain.pattern(30, 15, 2, override=["nonsense"]) == []


# ---------------------------------------------------------------- the checker, one rule at a time
def base() -> dict:
    st = copy.deepcopy(tenant.DEFAULTS["timetable"])
    st["shifts"] = {"morning": [1, 2, 3], "afternoon": [3, 4]}
    return {"weeks": 4, "lesson_times": domain.DEFAULT_TIMES[:4], "settings": st,
            "rooms": [{"id": 100, "kind": "classroom", "capacity": 30, "building_id": 1},
                      {"id": 101, "kind": "classroom", "capacity": 30, "building_id": 2},
                      {"id": 102, "kind": "lecture_hall", "capacity": 100, "building_id": 1},
                      {"id": 103, "kind": "lab", "capacity": 30, "building_id": 1}],
            "groups": [{"id": 10, "shift": "morning", "size": 20}, {"id": 11, "shift": None, "size": 20}],
            "units": [{"id": 1, "course_id": 1, "kind": "seminar", "teacher_id": 200, "groups": [10], "hours": 8, "students": 20},
                      {"id": 2, "course_id": 2, "kind": "seminar", "teacher_id": 201, "groups": [11], "hours": 8, "students": 20},
                      {"id": 3, "course_id": 3, "kind": "lab", "teacher_id": 202, "groups": [11], "subgroup": 1, "hours": 8, "students": 10},
                      {"id": 4, "course_id": 3, "kind": "lab", "teacher_id": 203, "groups": [11], "subgroup": 2, "hours": 8, "students": 10}],
            "needs": [], "availability": [], "blocks": [], "obstacles": [], "locked": [], "reference": []}


def pl(key, weekday=1, period=1, weeks="all", room=100, duration=1):
    return {"key": key, "weekday": weekday, "period": period, "duration": duration, "weeks": weeks, "room_id": room}


OK = [pl("1:0"), pl("2:0", room=101, period=2), pl("3:0", weekday=2, room=103), pl("4:0", weekday=3, room=103)]


def codes(problem, placements):
    return sorted({v["code"] for v in domain.check(problem, placements)})


def test_a_valid_timetable_passes_and_two_subgroups_share_a_slot():
    p = base()
    p["rooms"].append({"id": 104, "kind": "lab", "capacity": 30, "building_id": 1})
    good = [*OK[:3], pl("4:0", weekday=2, room=104)]
    assert domain.check(p, good) == []


@pytest.mark.parametrize("change, want", [
    (lambda p, x: x[0].update(weekday=7), "day"),                                     # H13
    (lambda p, x: x[0].update(period=4, duration=2), "duration"),                     # H10: past the last pair
    (lambda p, x: x[0].update(weeks="odd"), "pattern"),                               # H10: not a variant of 8 h
    (lambda p, x: p.update(from_week=2), "past"),                                     # a repair never changes the past
    (lambda p, x: p["locked"].append({"key": "1:0", "weekday": 3, "period": 1, "weeks": "all", "room_id": 100}), "locked"),   # H14
    (lambda p, x: x[0].update(period=4), "shift"),                                    # H7
    (lambda p, x: p["blocks"].append({"subject_type": "group", "subject_id": 10, "weeks": "2"}), "block"),     # H16
    (lambda p, x: p["blocks"].append({"subject_type": "teacher", "subject_id": 200, "weeks": "2"}), "block"),
    (lambda p, x: p["blocks"].append({"subject_type": "room", "subject_id": 100, "weeks": "2"}), "block"),
    (lambda p, x: p["settings"].update(fixed_slots=[{"weekday": 1, "period": 1, "groups": None}]), "fixed_slot"),    # H8
    (lambda p, x: p["availability"].append({"subject_type": "teacher", "subject_id": 200, "weekday": 1, "period": 1, "weeks": "odd",
                                            "level": "unavailable"}), "teacher_unavailable"),                         # H6
    (lambda p, x: p["availability"].append({"subject_type": "room", "subject_id": 100, "weekday": 1, "period": 1, "weeks": "all",
                                            "level": "unavailable"}), "room_unavailable"),
    (lambda p, x: x[0].update(room_id=103), "room_fit"),                              # H5: a lab for a seminar
    (lambda p, x: x[0].update(room_id=None), "no_room"),
    (lambda p, x: p["units"][0].update(students=31), "capacity"),                     # H4
    (lambda p, x: x[1].update(period=1, room_id=100), "room_clash"),                  # H3
    (lambda p, x: p["units"][1].update(teacher_id=200) or x[1].update(period=1), "teacher_clash"),   # H1
    (lambda p, x: x.append(pl("3:0", weekday=1, period=2, room=103)) or x.pop(2), "group_clash"),     # H2: subgroup 1 meets the whole group
    (lambda p, x: p["units"][1].update(teacher_id=200), "travel"),                    # H9: pair 1 in building 1, pair 2 in building 2
    (lambda p, x: p["settings"].update(max_pairs_day_teacher=1) or p["units"][1].update(teacher_id=200) or x[1].update(room_id=102),
     "day_limit_teacher"),                                                            # H11
    (lambda p, x: p["settings"].update(max_pairs_day_group=1) or p["units"][1].update(groups=[10]) or x[1].update(room_id=102),
     "day_limit_group"),
    (lambda p, x: p["settings"].update(max_week_hours_group=2) or p["units"][1].update(groups=[10]) or x[1].update(room_id=102),
     "week_hours"),                                                                   # H12
    (lambda p, x: x.append(pl("9:0")), "unknown_meeting"),
    (lambda p, x: x.append(dict(x[0])), "duplicate"),
])
def test_each_hard_rule_is_found(change, want):
    p, x = base(), copy.deepcopy(OK)
    assert want not in codes(p, x)
    change(p, x)
    assert want in codes(p, x), codes(p, x)


def test_travel_allows_a_break_exactly_as_long_as_the_walk():
    """TE-F9: pair 1 in building 1, pair 2 in building 2, a 10-minute break: a 10-minute walk fits, an 11-minute one does not."""
    p, x = base(), copy.deepcopy(OK)
    p["units"][1].update(teacher_id=200)
    assert domain.breaks(domain.lesson_times(p))[0] == 10
    p["settings"]["travel_default_min"] = 10
    assert "travel" not in codes(p, x)
    p["settings"]["travel_default_min"] = 11
    assert "travel" in codes(p, x)


def test_online_needs_no_room_and_manual_rows_are_obstacles():
    p = base()
    p["needs"] = [{"unit_id": 4, "mode": "online"}]
    assert domain.check(p, [*OK[:3], pl("4:0", weekday=2, room=None)]) == [], "online: subgroup 2 shares the slot of subgroup 1, no room"
    assert "room_fit" in codes(p, OK)
    p["needs"] = []
    p["obstacles"] = [{"key": "m1", "teacher_id": 200, "groups": [], "room_id": None, "weekday": 1, "period": 1, "duration": 1, "weeks": "even"}]
    assert codes(p, OK) == ["teacher_clash"]
    p["obstacles"].append({"key": "m2", "teacher_id": 200, "groups": [], "room_id": None, "weekday": 3, "period": 1, "duration": 1, "weeks": "all"})
    p["obstacles"].append({"key": "m3", "teacher_id": 200, "groups": [], "room_id": None, "weekday": 3, "period": 1, "duration": 1, "weeks": "all"})
    assert codes(p, OK) == ["teacher_clash"], "two manual rows that clash with each other are not this timetable's violation"


# ---------------------------------------------------------------- the clock-time rule over a whole set
def test_conflicts_all_equals_the_pairwise_rule():
    rng = random.Random(9)
    for _ in range(200):
        rows = []
        for i in range(rng.randrange(2, 25)):
            h = rng.randrange(8, 14)
            rows.append({"id": i, "weekday": rng.choice([1, 2]), "start": f"{h:02d}:00", "end": f"{h + rng.choice([1, 2]):02d}:00",
                         "weeks": rng.choice(["all", ODD, EVEN, "1-3"]), "room": rng.choice([None, "a", "b"]),
                         "teacher_id": rng.choice([None, 1, 2]), "groups": [(rng.choice([1, 2, 3]), rng.choice([None, 1, 2]))]})
        want = {}
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                for c in domain.conflicts(a, [b]):
                    want.setdefault((a["id"], b["id"], c["what"]), set()).update(c["groups"])
        got = {(x["a"], x["b"], x["what"]): set(x["groups"]) for x in domain.conflicts_all(rows)}
        assert got == want


# ---------------------------------------------------------------- hours
def test_the_hours_report_names_the_reason_of_every_difference():
    p = base()
    p["weeks"] = 15
    p["units"] = [{"id": 1, "course_id": 1, "kind": "seminar", "teacher_id": 200, "groups": [10], "hours": 15},     # fortnightly: 16 or 14
                  {"id": 2, "course_id": 1, "kind": "lecture", "teacher_id": 200, "groups": [10, 11], "hours": 30},  # weekly; a holiday falls on it
                  {"id": 3, "course_id": 2, "kind": "lab", "teacher_id": 201, "groups": [11], "hours": 30},          # not placed
                  {"id": 4, "course_id": 2, "kind": "lab", "teacher_id": 201, "groups": [], "hours": 30}]            # no groups
    term = {"teaching_start": "2026-09-14", "teaching_end": "2026-12-27"}            # 15 weeks from a Monday
    placements = [pl("1:0", weeks=ODD), pl("2:0", weekday=2, room=102)]
    rep = domain.hours_report(p, placements, term, ["2026-09-15"])
    by = {x["unit_id"]: x for x in rep["units"]}
    assert (by[1]["planned_h"], by[1]["delta"], by[1]["reasons"], by[1]["flagged"]) == (16, 1, ["fortnight_rounding"], False)
    assert (by[2]["planned_h"], by[2]["reasons"]) == (28, ["holidays"]) and not by[2]["flagged"]
    assert (by[3]["planned_h"], by[3]["reasons"], by[3]["flagged"]) == (0, ["unplaced"], True)
    assert by[4]["reasons"] == ["no_groups"]
    assert {x["id"]: x["planned_h"] for x in rep["teachers"]} == {200: 44, 201: 0}
    assert {x["id"]: x["form_h"] for x in rep["groups"]} == {10: 45, 11: 60}
    real = domain.hours_report(p, placements, term, [], lessons=[{"unit_id": 1, "status": "held", "academic_hours": 2}] * 7
                               + [{"unit_id": 1, "status": "cancelled", "academic_hours": 2}])
    assert {x["unit_id"]: (x["planned_h"], x["reasons"]) for x in real["units"]}[1] == (14, ["cancelled"])
    # F2: lessons only from a later publication's date (or moved, or extra) are named as such, never as a rounding
    late = domain.hours_report(p, placements, term, [], lessons=[{"unit_id": 1, "status": "held", "academic_hours": 2}] * 3
                               + [{"unit_id": 3, "status": "held", "academic_hours": 2}])
    by = {x["unit_id"]: (x["planned_h"], x["reasons"]) for x in late["units"]}
    assert by[1] == (6, ["lessons_differ"]) and by[2] == (0, ["lessons_differ"]) and by[3] == (2, ["unplaced", "lessons_differ"]), by
    # published (acceptance on the real files): the lessons skip the holiday, and the reason is still the holiday, never
    # a rounding of the weekly pattern
    held = domain.hours_report(p, placements, term, ["2026-09-15"], lessons=[{"unit_id": 2, "status": "scheduled", "academic_hours": 2}] * 14)
    assert {x["unit_id"]: (x["planned_h"], x["reasons"]) for x in held["units"]}[2] == (28, ["holidays"])


# ---------------------------------------------------------------- the settings section
def test_the_timetable_settings_are_checked():
    ok = copy.deepcopy(tenant.DEFAULTS["timetable"])
    assert tenant.problem("timetable", ok) is None and tenant.problem("timetable", {}) is None

    def bad(**kw):
        return tenant.problem("timetable", {**ok, **kw}) is not None

    assert bad(max_week_hours_group=31), "the legal ceiling may only go down"
    assert bad(days=[1, 1]) and bad(days=[8]) and bad(days=[3, 1]) and bad(days=[])
    assert bad(shifts={"morning": [0]}) and bad(shifts={"morning": []})
    assert bad(solver={**ok["solver"], "chunk_s": 4}) and bad(solver={**ok["solver"], "chunk_s": 61}) and bad(solver={"chunk_s": 20})
    assert bad(offsets={**ok["offsets"], "needs": 3}) and bad(weights={**ok["weights"], "saturday": -1})
    assert bad(weights={**ok["weights"], "saturday": 1.5}) and bad(confirmed=["nonsense"]) and bad(confirmed=["pattern", "pattern"])
    assert bad(publish_requires=["term_dates", "lesson_times"]), "bell times, dates and the pattern always gate a publish"
    assert bad(pair_hours=True) and bad(review_silence="maybe") and bad(fixed_slots=[{"weekday": 1}])
    assert bad(approver={"title": ""}) and bad(unknown=1)
    # malformed JSON ends as a message (a 400), never an exception (a 500): lists of lists or objects are not hashable
    assert bad(days=[[1]]) and bad(confirmed=[[1]]) and bad(publish_requires=[{}]) and bad(shifts={"a": [[1]]})
    assert bad(fixed_slots=[{"weekday": 1, "period": 1, "groups": [[2]]}]) and bad(shifts=[1]) and bad(approver=[])
    assert not bad(max_week_hours_group=24, confirmed=["pattern"], max_week_pairs_teacher=20,
                   fixed_slots=[{"weekday": 3, "period": 4, "groups": [5, 6]}])


def test_s10_counts_the_weeks_a_placement_holds_and_the_solver_avoids_a_holiday_weekday():
    """CORR-F1: hours_miss counted planned hours before holidays, so Monday (two holidays) and Thursday scored the same,
    the solver kept Monday and the version showed hours_miss 0 while the hours report flagged the unit."""
    term, holidays = {"teaching_start": "2027-02-15", "teaching_end": "2027-05-29"}, ["2027-03-08", "2027-05-10"]   # two Mondays
    p = base()
    p["weeks"] = domain.term_weeks(term)
    p["units"] = [{"id": 1, "course_id": 1, "kind": "seminar", "teacher_id": 200, "groups": [10], "hours": 30, "students": 20}]
    p["off"] = domain.lost_weeks(term, holidays, p["weeks"])
    assert p["weeks"] == 15 and p["off"][1] == (1 << 3) | (1 << 12) and p["off"][4] == 0
    card = {wd: domain.scorecard(p, [pl("1:0", weekday=wd)]) for wd in (1, 4)}
    assert card[1]["components"]["hours_miss"]["value"] == 2 and card[1]["hours"]["flagged"] == 1 and card[1]["hours"]["planned_h"] == 26
    assert card[4]["components"]["hours_miss"]["value"] == 0 and card[4]["hours"]["flagged"] == 0
    rep = domain.hours_report(p, [pl("1:0", weekday=1)], term, holidays)
    assert rep["units"][0]["planned_h"] == 26 and rep["flagged"] == 1 and "holidays" in rep["units"][0]["reasons"]
    model = solver.prepare(p)
    out = solver.result(model, solver.run(model, seed=0, budget=2000))
    (chosen,) = out["placements"]
    assert chosen["weekday"] != 1 and domain.scorecard(p, out["placements"])["components"]["hours_miss"]["value"] == 0
    assert domain.scorecard(p, out["placements"])["soft"] == out["score"]["soft"], "the solver's running cost is the scorecard's"
