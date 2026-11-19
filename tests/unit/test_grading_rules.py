"""Grade rules (tasks/todo.md, Task 21): the columns of a scheme, a typed or pasted cell, the attendance component
from the journal, and the transcript's average and credits."""
import pytest

from zeka.core import tenant
from zeka.legacy import docs
from zeka.modules.journal import domain

AZTU = {"components": [{"name": "Davamiyyət", "max": 10, "attendance": True}, {"name": "Sərbəst iş 1", "max": 5}],
        "exam": {"name": "İmtahan", "max": 50, "min": 0}, "pass_mark": 51, "scale": [["A", 91], ["E", 51]]}


def test_the_columns_are_the_scheme_then_the_exam():
    cols = domain.scheme(AZTU)
    assert [(c["key"], c["kind"]) for c in cols] == [("Davamiyyət", "attendance"), ("Sərbəst iş 1", "component"), ("İmtahan", "exam")]


@pytest.mark.parametrize("v, want", [(4, 4.0), ("4,5", 4.5), (" 3.25 ", 3.25), ("", None), (None, None), (0, 0.0), (5, 5.0)])
def test_a_cell_takes_numbers_and_pasted_text(v, want):
    assert domain.cell_value(v, 5) == (want, None)


@pytest.mark.parametrize("v", [6, -1, "beş", True, "nan", "inf", [1], {"x": 1}, float("nan")])
def test_a_cell_out_of_range_or_not_a_number_is_refused(v):
    value, problem = domain.cell_value(v, 5)
    assert value is None and problem and problem["az"]


def test_the_attendance_component_follows_the_points_rule():
    st = {"held_hours": 40, "missed_hours": 4}                        # 10% missed so far
    assert domain.attendance_score(st, 10, []) == 9.0
    assert domain.attendance_score(st, 10, [[5, 10], [15, 8], [25, 5]]) == 8.0
    assert domain.attendance_score(st, 10, [[5, 10], [9, 8]]) == 0.0, "past the last row: no points"
    assert domain.attendance_score({"held_hours": 0, "missed_hours": 0}, 10, []) is None
    assert domain.attendance_score({"held_hours": 10, "missed_hours": 12}, 10, []) == 0.0, "imported hours can exceed those held here"


def test_the_transcript_average_counts_every_course_the_credits_only_passed_ones():
    rows = [{"score": 90, "credits": 5, "passed": True}, {"score": 40, "credits": 5, "passed": False}, {"score": 80, "credits": 10, "passed": True}]
    assert domain.transcript_totals(rows) == {"average": round((450 + 200 + 800) / 20, 1), "credits": 15}
    assert domain.transcript_totals([]) == {"average": None, "credits": 0}


def test_the_transcript_document_counts_only_passed_credits():
    rows = [{"name": "I", "name_en": "1", "courses": [{"name": "Fizika", "name_en": "Physics", "credits": 5, "score": 90, "letter": "A", "passed": True},
                                                      {"name": "Kimya", "name_en": "Chem", "credits": 5, "score": 40, "letter": "F", "passed": False}]}]
    ctx = {"specialty": {"name": "X", "name_en": "X"}, "grading": tenant.DEFAULTS["grading"]}
    body = docs.transcript_body({"full_name": "Aysel", "group": "G", "student_no": "1"}, {}, ctx, rows, False)
    assert "Cəmi kredit:</b> 5" in body and "65.0" in body and "sintetik" not in body
