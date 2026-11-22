"""The timetable builder's service rules (tasks/todo.md, Task 48, slice 2): availability grids and the cap, unit needs,
the readiness checklist and its gates, the publication plan, and the editor's options and live clash check."""
import copy

from zeka.core import tenant
from zeka.modules.timetable import domain

ST = copy.deepcopy(tenant.DEFAULTS["timetable"])
DAYS = [1, 2, 3, 4, 5, 6]


def test_term_weeks_pairs_and_spans():
    assert domain.term_weeks({"teaching_start": "2026-09-15", "teaching_end": "2026-12-28"}) == 16
    assert domain.term_weeks({"teaching_start": "2026-12-28", "teaching_end": "2026-09-15"}) == 0
    assert domain.term_weeks(None) == 0
    times = domain.DEFAULT_TIMES
    assert domain.pair_span(times, 2, 2) == ("10:30", "13:20")
    assert domain.pair_span(times, 8, 2) is None and domain.pair_span(times, 0, 1) is None
    assert domain.pairs_of(times, "10:00", "12:30") == (1, 3)
    assert domain.pairs_of(times, "22:00", "23:00") is None


def test_an_availability_grid_is_checked_cell_by_cell():
    cells, problem = domain.availability_input([{"weekday": 1, "period": 2, "level": "unavailable", "weeks": "1-4", "note": "  a  b "}],
                                               DAYS, 6, 15)
    assert problem is None and cells == [{"weekday": 1, "period": 2, "level": "unavailable", "weeks": "1-4", "note": "a b"}]
    for bad in ([{"weekday": 7, "period": 1, "level": "unavailable"}], [{"weekday": 1, "period": 7, "level": "unavailable"}],
                [{"weekday": 1, "period": 1, "level": "busy"}], [{"weekday": 1, "period": 1, "level": "undesired", "weeks": "20-25"}],
                [{"weekday": True, "period": 1, "level": "undesired"}], "x", [[1, 2]], [{"weekday": 1, "period": 1, "level": "undesired", "note": 5}]):
        assert domain.availability_input(bad, DAYS, 6, 15)[1] is not None, bad
    twice = [{"weekday": 1, "period": 1, "level": "undesired"}] * 2
    assert domain.availability_input(twice, DAYS, 6, 15)[1] is not None


def test_the_cap_counts_unavailable_cells_and_the_free_cells_the_load_needs():
    cell = {"level": "unavailable"}
    ok = domain.availability_feedback([cell] * 10, 4, ST, 6, 6)        # 36 cells, 30 %: 10 allowed; 26 free >= 6 needed
    assert ok["over_cap"] == 0 and ok["unavailable_pct"] == 27 and ok["needed_cells"] == 6
    assert domain.availability_feedback([cell] * 12, 4, ST, 6, 6)["over_cap"] == 2
    heavy = domain.availability_feedback([cell] * 10, 20, ST, 6, 6)     # 20 pairs need 30 free cells, 26 are free
    assert heavy["over_cap"] == 4
    assert domain.weekly_pairs([{"hours": 30}, {"hours": 15}, {"hours": None}], ST, 15) == 2


def test_unit_needs_keep_planned_hours_within_the_tolerance():
    unit = {"hours": 30}
    v, problem = domain.needs_input({"pattern": ["1-15"], "duration": 1}, unit, ST, 15, {1, 2})
    assert problem is None and v["pattern"] == ["all"] and v["mode"] == "in_person"
    _, problem = domain.needs_input({"pattern": ["1-8"]}, unit, ST, 15, set())
    assert problem is not None and "16" in problem["az"] and "30 saat" in problem["az"]
    assert domain.needs_input({"need": 40}, unit, ST, 15, set())[1] is not None            # a seat override needs a reason
    assert domain.needs_input({"need": 40, "need_reason": "Axın birləşir"}, unit, ST, 15, set())[0]["need"] == 40
    assert domain.needs_input({"room_ids": [3]}, unit, ST, 15, {1, 2})[1] is not None       # an unknown room
    for bad in ({"room_kinds": ["pool"]}, {"room_kinds": "lab"}, {"duration": 0}, {"mode": "hybrid"}, {"split": "half"},
                {"need": "40"}, {"room_ids": [1, 1]}, {"pattern": "all"}):
        assert domain.needs_input(bad, unit, ST, 15, {1})[1] is not None, bad


def _facts(**kw):
    base = {"term": {"teaching_start": "2026-09-15"}, "weeks": 15, "lesson_times": domain.DEFAULT_TIMES,
            "rooms": [{"kind": "classroom", "capacity": 30, "building_id": 1, "schedulable": 1}], "groups": [1, 2], "groups_no_shift": [],
            "units": [10, 11], "units_no_groups": [], "units_no_teacher": [], "units_over_room": [], "teachers": [5],
            "teachers_unconfirmed": [], "pending": [], "availability_due": "2026-09-01"}
    return {**base, **kw}


def _line(lines, code):
    return next(x for x in lines if x["code"] == code)


def test_readiness_gates_name_what_they_stop():
    st = {**ST, "confirmed": ["term_dates", "lesson_times", "pattern"]}
    lines = domain.readiness(_facts(), st, "2026-08-01")
    assert domain.gate(lines, "run") == [] and domain.gate(lines, "publish") == []
    assert {x["code"] for x in lines if x["level"] == "ok"} >= {"term_dates", "pattern", "lesson_times", "rooms", "availability"}
    raw = domain.readiness(_facts(), ST, "2026-08-01")                  # nothing confirmed: publishing stops, runs do not
    assert {x["code"] for x in domain.gate(raw, "publish")} == {"term_dates", "pattern", "lesson_times"}
    assert domain.gate(raw, "run") == []
    assert {x["code"] for x in domain.gate(domain.readiness(_facts(term=None, weeks=0), st, "2026-08-01"), "run")} == {"term_dates"}
    assert {x["code"] for x in domain.gate(domain.readiness(_facts(rooms=[]), st, "2026-08-01"), "run")} == {"rooms"}
    short = _facts(lesson_times=domain.DEFAULT_TIMES[:6])               # the evening shift names pairs 7 and 8
    assert _line(domain.readiness(short, st, "2026-08-01"), "lesson_times")["samples"] == [7, 8]
    assert "run" in _line(domain.readiness(short, st, "2026-08-01"), "lesson_times")["blocks"]
    stored = domain.readiness(_facts(lesson_times=[]), st, "2026-08-01")   # defaults used: a run may go, a publication not
    assert _line(stored, "lesson_times")["blocks"] == ["publish"]
    late = domain.readiness(_facts(teachers_unconfirmed=[5], pending=[5]), st, "2026-09-02")
    assert {"availability_late", "availability_pending"} <= {x["code"] for x in late}
    assert _line(domain.readiness(_facts(groups_no_shift=[2], units_no_teacher=[11]), st, "2026-08-01"), "group_shifts")["found"] == 1


def test_the_publication_plan_matches_rows_by_meeting():
    published = [{"id": 1, "meeting_key": "5:0", "unit_id": 5, "weekday": 1, "period": 1, "start": "09:00", "end": "10:20", "weeks": "all",
                  "room_id": 3, "academic_hours": 2},
                 {"id": 2, "meeting_key": "6:0", "unit_id": 6, "weekday": 2, "period": 1, "start": "09:00", "end": "10:20", "weeks": "all",
                  "room_id": 3, "academic_hours": 2},
                 {"id": 3, "meeting_key": None, "unit_id": 7}]
    times = domain.DEFAULT_TIMES
    wanted = [domain.published_row({"meeting_key": "5:0", "unit_id": 5, "weekday": 1, "period": 1, "duration": 1, "weeks": "all", "room_id": 3}, times, 2),
              domain.published_row({"meeting_key": "6:0", "unit_id": 6, "weekday": 3, "period": 2, "duration": 1, "weeks": "odd", "room_id": 3}, times, 2),
              domain.published_row({"meeting_key": "8:0", "unit_id": 8, "weekday": 4, "period": 1, "duration": 2, "weeks": "all", "room_id": None}, times, 2)]
    plan = domain.publish_plan(published, wanted)
    assert plan["unchanged"] == [1] and [x["id"] for x in plan["update"]] == [2] and plan["deactivate"] == []
    assert plan["insert"][0]["meeting_key"] == "8:0" and plan["insert"][0]["end"] == "11:50" and plan["insert"][0]["academic_hours"] == 4
    assert domain.publish_plan(published, wanted[:1])["deactivate"] == [2]          # the manual row is never touched


def _problem():
    st = {**ST, "days": [1, 2]}
    return {"weeks": 4, "lesson_times": domain.DEFAULT_TIMES[:3], "settings": st,
            "rooms": [{"id": 1, "kind": "classroom", "capacity": 30, "building_id": 1}, {"id": 2, "kind": "classroom", "capacity": 40, "building_id": 1}],
            "groups": [{"id": 10}, {"id": 11}],
            "units": [{"id": 1, "course_id": 1, "kind": "seminar", "teacher_id": 5, "groups": [10], "hours": 8, "students": 20},
                      {"id": 2, "course_id": 2, "kind": "seminar", "teacher_id": 6, "groups": [10], "hours": 8, "students": 20},
                      {"id": 3, "course_id": 3, "kind": "seminar", "teacher_id": 5, "groups": [11], "hours": 8, "students": 20}],
            "needs": [], "availability": [{"subject_type": "teacher", "subject_id": 5, "weekday": 2, "period": 3, "weeks": "all",
                                           "level": "unavailable"}],
            "blocks": [], "obstacles": [{"key": "row:1", "weekday": 2, "period": 1, "duration": 1, "weeks": "all", "teacher_id": None,
                                         "groups": [], "room_id": 1}], "reference": [], "locked": []}


def test_a_move_is_checked_against_its_neighbourhood():
    problem = _problem()
    pls = [{"key": "1:0", "unit_id": 1, "weekday": 1, "period": 1, "duration": 1, "weeks": "all", "room_id": 1},
           {"key": "2:0", "unit_id": 2, "weekday": 1, "period": 2, "duration": 1, "weeks": "all", "room_id": 1},
           {"key": "3:0", "unit_id": 3, "weekday": 1, "period": 3, "duration": 1, "weeks": "all", "room_id": 1}]
    assert domain.check(problem, pls) == []
    to = {**pls[0], "period": 2}
    assert {v["code"] for v in domain.move_problems(problem, pls, to)} == {"group_clash", "room_clash"}
    assert {v["code"] for v in domain.move_problems(problem, pls, {**pls[0], "period": 3, "room_id": 2})} == {"teacher_clash"}
    assert {v["code"] for v in domain.move_problems(problem, pls, {**pls[0], "weekday": 2, "period": 3, "room_id": 2})} == {"teacher_unavailable"}
    assert domain.move_problems(problem, pls, {**pls[0], "weekday": 2, "period": 2}) == []
    opts = {(o["weekday"], o["period"]): o for o in domain.options(problem, pls, "1:0")}
    assert len(opts) == 6 and opts[(1, 1)]["current"] and opts[(1, 1)]["room_id"] == 1
    assert "group_clash" in opts[(1, 2)]["reasons"] and opts[(2, 3)]["reasons"] == ["teacher_unavailable"]
    assert opts[(2, 1)]["reasons"] == [] and opts[(2, 1)]["room_id"] == 2        # room 1 holds a hand-written row then
    for o in opts.values():                                                    # every slot it calls free really is
        if not o["reasons"]:
            assert domain.move_problems(problem, pls, {**pls[0], "weekday": o["weekday"], "period": o["period"], "room_id": o["room_id"]}) == []


def test_review_readiness_a_confirmed_term_is_ok_and_hand_written_units_are_named():
    """Task 48 review UX13: a confirmed term of 16 weeks against 15 expected stayed a warning nobody could clear; UX3:
    units kept out of a run by their hand-written rows are a line of their own."""
    st = {**ST, "confirmed": ["term_dates", "lesson_times", "pattern"], "weeks_expected": 15}
    assert _line(domain.readiness(_facts(weeks=16), st, "2026-08-01"), "term_dates")["level"] == "ok"
    assert _line(domain.readiness(_facts(weeks=16), {**st, "confirmed": [], "publish_requires": []}, "2026-08-01"), "term_dates")["level"] == "warn"
    assert "manual_rows" not in {x["code"] for x in domain.readiness(_facts(), st, "2026-08-01")}
    line = _line(domain.readiness(_facts(units_manual=[11]), st, "2026-08-01"), "manual_rows")
    assert (line["level"], line["found"], line["of"], line["samples"], line["blocks"]) == ("warn", 1, 2, [11], [])


def test_review_a_wrong_week_set_says_so():
    """UX6: a week set the grammar refuses answered with the grid's general message."""
    _, problem = domain.availability_input([{"weekday": 1, "period": 1, "level": "unavailable", "weeks": "tək"}], DAYS, 6, 15)
    assert problem["az"].startswith("Xananın həftələri düzgün deyil")
