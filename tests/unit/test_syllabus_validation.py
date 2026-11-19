"""The structured syllabus (tasks/todo.md, Task 23): what is refused, what the first draft holds, Forma №3 hours."""
import copy

import pytest

from zeka.modules.syllabus import domain

RULES = {"grading": {"components": [{"name": "Davamiyyət", "max": 10, "attendance": True}, {"name": "Kollokvium", "max": 40}],
                     "exam": {"name": "İmtahan", "max": 50, "min": 0}},
         "attendance": {"limit_percent": 25}}

GOOD = {
    "description": "Elektrik dövrələrinin əsasları.",
    "outcomes": [{"id": "N1", "text": "Om qanununu izah edir və tətbiq edir", "bloom": "apply"},
                 {"id": "N2", "text": "Kirxhof qaydaları ilə dövrəni təhlil edir", "bloom": "analyze"}],
    "plan": [{"week": 2, "topic": "Kirxhof qaydaları", "outcomes": ["N2"], "activity": "Məsələ həlli"},
             {"week": 1, "topic": "Om qanunu", "outcomes": ["N1"], "activity": ""}],
    "assessment": [{"name": "Davamiyyət", "kind": "attendance", "weight": 10}, {"name": "Kollokvium", "kind": "component", "weight": 40},
                   {"name": "İmtahan", "kind": "exam", "weight": 50}],
    "rules": {"attendance_limit": 20, "late_policy": "Gecikmə qəbul olunmur.", "ai_policy": "limited", "ai_note": "İzah üçün olar."},
    "prerequisites": ["Fizika I"],
    "literature": [{"title": "Elektrotexnikanın əsasları", "kind": "main"}],
    "workload": {"lecture": 30, "seminar": 15, "lab": 15, "independent": 90},
    "unknown": "dropped",
}


def changed(path, value):
    d = copy.deepcopy(GOOD)
    cur = d
    for k in path[:-1]:
        cur = cur[k]
    cur[path[-1]] = value
    return d


def test_a_good_syllabus_is_kept_clean_and_ordered():
    clean, problem = domain.validate(GOOD, RULES)
    assert problem is None and "unknown" not in clean
    assert [p["week"] for p in clean["plan"]] == [1, 2] and clean["rules"]["attendance_limit"] == 20.0


@pytest.mark.parametrize("path,value", [
    (("assessment", 1, "weight"), 35),                                   # 95 in all
    (("assessment", 2, "weight"), 45),                                   # the exam must weigh the university's 50
    (("assessment",), [{"name": "Kollokvium", "kind": "component", "weight": 50}, {"name": "İmtahan", "kind": "component", "weight": 50}]),
    (("rules", "attendance_limit"), 30),                                 # above the university's 25%
    (("rules", "ai_policy"), "maybe"),
    (("outcomes", 1, "id"), "N1"),
    (("outcomes", 0, "bloom"), "memorize"),
    (("outcomes", 0, "text"), "qısa"),
    (("plan", 0, "outcomes"), ["N9"]),
    (("plan", 1, "week"), 2),
    (("literature", 0, "kind"), "other"),
    (("workload", "lecture"), -1),
    (("workload", "lecture"), float("nan")),
])
def test_a_syllabus_against_the_rules_is_refused(path, value):
    assert domain.validate(changed(path, value), RULES)[1] is not None


def test_the_limit_may_be_lowered_and_equal_to_the_university_s():
    assert domain.validate(changed(("rules", "attendance_limit"), 25), RULES)[1] is None
    assert domain.validate(changed(("rules", "attendance_limit"), 10), RULES)[1] is None


def test_forma3_hours_take_the_largest_unit_of_a_kind_and_differences_are_listed():
    units = [{"kind": "lecture", "hours": 30}, {"kind": "seminar", "hours": 15}, {"kind": "seminar", "hours": 15}, {"kind": "lab", "hours": None}]
    imported = domain.workload_from_units(units)
    assert imported == {"lecture": 30.0, "seminar": 15.0}
    assert domain.workload_diff({"lecture": 30, "seminar": 15, "lab": 15}, imported) == []
    assert domain.workload_diff({"lecture": 24, "seminar": 15}, imported) == [{"kind": "lecture", "imported": 30.0, "syllabus": 24}]


def test_the_first_draft_follows_the_scheme_and_forma3_and_validates_once_outcomes_are_there():
    gen = {"description": "Təsvir", "outcomes": ["Om qanununu izah edir və tətbiq edir", "x"],
           "plan": [{"week": 1, "topic": "Om qanunu", "activity": "Mühazirə"}], "materials": ["Mühazirə 1", "[Əsas dərslik]"],
           "workload": {"total": 150, "contact": 60}}
    d = domain.initial(gen, RULES, {"lecture": 30.0, "seminar": 15.0}, ["Fizika I"])
    assert [o["id"] for o in d["outcomes"]] == ["N1"], "too short an outcome is left out"
    assert [a["weight"] for a in d["assessment"]] == [10.0, 40.0, 50.0] and d["assessment"][-1]["kind"] == "exam"
    assert d["workload"] == {"lecture": 30.0, "seminar": 15.0, "lab": 0.0, "independent": 105.0}
    assert d["literature"] == [{"title": "Mühazirə 1", "kind": "extra"}] and d["rules"]["attendance_limit"] == 25.0
    assert domain.validate(d, RULES)[1] is None
