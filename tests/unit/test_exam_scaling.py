"""An exam's raw score in the journal (tasks/todo.md, Task 30): scaled to the exam component's maximum and rounded half
up to one decimal in exam/domain.py only; with an exam minimum of 17, 16.9 points fail and 17.0 pass; a released exam's
result status for each student; the similar wrong-answer pairs."""
import copy

from zeka.core import tenant
from zeka.modules.exam import domain


def grading(exam_min=17):
    g = copy.deepcopy(tenant.DEFAULTS["grading"])
    g["exam"]["min"] = exam_min
    return g


def test_scaling_rounds_half_up_to_one_decimal():
    assert domain.scale(13, 20, 26) == 16.9
    assert domain.scale(16.95, 50, 50) == 17.0
    assert domain.scale(16.94, 50, 50) == 16.9
    assert domain.scale(1, 3, 50) == 16.7
    assert domain.scale(2, 3, 50) == 33.3
    assert domain.scale(20, 20, 50) == 50.0
    assert domain.scale(0, 20, 50) == 0.0
    assert domain.scale(5, 0, 50) == 0.0                       # an empty form scores nothing, never divides by zero


def test_with_an_exam_minimum_of_17_points_16_9_fails_and_17_0_passes():
    g = grading()
    semester = {"Semestr ərzində": 50}
    low = tenant.outcome(semester, domain.scale(16.94, 50, 50), g)
    high = tenant.outcome(semester, domain.scale(16.95, 50, 50), g)
    assert (low["exam"], low["passed"], low["reason"], low["letter"]) == (16.9, False, "exam_min", "F")
    assert (high["exam"], high["passed"], high["total"], high["letter"]) == (17.0, True, 67.0, "D")
    assert domain.result_status("eligible", "graded", low) == "exam_min"
    assert domain.result_status("eligible", "graded", high) == "passed"


def test_the_result_status_of_each_student():
    g = grading(0)
    assert domain.result_status("excluded", None, None) == "not_admitted"
    assert domain.result_status("eligible", None, None) == "absent"
    assert domain.result_status("eligible", "submitted", None) == "absent"        # not graded yet: no result
    assert domain.result_status("exception", "graded", tenant.outcome({"Semestr ərzində": 10}, 20, g)) == "pass_mark"
    assert set(domain.RESULTS) == {"passed", "exam_min", "pass_mark", "not_admitted", "absent"}


def test_similar_wrong_answers_are_paired_most_first():
    wrong = {1: {10: '"7"', 11: '"x"', 12: '"2"'}, 2: {10: '"7"', 11: '"x"', 12: '"3"'}, 3: {10: '"7"'}, 4: {11: '"x"', 12: '"2"', 10: '"7"'}}
    pairs = domain.similar_pairs(wrong)
    assert [(p["a"], p["b"], p["same"]) for p in pairs] == [(1, 4, 3), (1, 2, 2), (2, 4, 2)]
    assert pairs[0]["questions"] == [10, 11, 12]
    assert domain.similar_pairs(wrong, at_least=4) == []
