"""Attendance rules (tasks/todo.md, Task 20): the share of missed academic hours, the cut-over date, the opening
balance, excused absences and the edit window."""
from datetime import datetime

from zeka.modules.journal import domain


def lessons(n, hours=3, first_day=1):
    return [{"id": i, "day": f"2026-10-{first_day + i:02d}", "academic_hours": hours} for i in range(n)]


def absent(ids, status="absent", source="zeka"):
    return {i: {"status": status, "source": source} for i in ids}


def standing(ls, recs, **kw):
    return domain.standing(ls, recs, **{"cutover": None, "opening": None, "excused_counts": True, "limit_percent": 25, **kw})


def test_eleven_of_forty_five_hours_admits_twelve_does_not():
    ls = [{"id": i, "day": f"2026-10-{1 + i:02d}", "academic_hours": 1} for i in range(45)]
    eleven, twelve = standing(ls, absent(range(11))), standing(ls, absent(range(12)))
    assert eleven["planned_hours"] == 45 and eleven["missed_hours"] == 11 and eleven["status"] != "not_admitted"
    assert twelve["missed_hours"] == 12 and twelve["status"] == "not_admitted"
    assert standing(ls, absent(range(11)) | absent([11], "late"))["status"] != "not_admitted", "late is not missed"


def test_cancelled_lessons_and_days_after_the_term_are_left_out_by_the_caller():
    # the service passes only the lessons of the teaching period that are not cancelled: the share is of what remains
    assert standing(lessons(10, hours=2), absent([0]))["percent"] == 10.0


def test_excused_hours_count_only_when_the_university_says_so():
    ls = lessons(10, hours=2)
    recs = absent([0, 1]) | absent([2, 3, 4], "excused")
    assert standing(ls, recs, excused_counts=True)["missed_hours"] == 10
    off = standing(ls, recs, excused_counts=False)
    assert off["missed_hours"] == 4 and off["excused_hours"] == 6 and off["unexcused_hours"] == 4


def test_a_warning_comes_before_the_limit():
    ls = lessons(20, hours=1)
    assert standing(ls, absent(range(4)))["status"] == "normal", "exactly 80% of the limit is not past it"
    assert standing(ls, absent(range(5)))["status"] == "warning"
    assert standing(ls, absent(range(6)))["status"] == "not_admitted"


def test_an_opening_balance_and_zeka_records_add_up():
    ls = lessons(25, hours=4)                                            # 100 planned hours
    opening = {"unexcused_hours": 20, "excused_hours": 0, "as_of": "2026-10-10"}
    after = [x["id"] for x in ls if x["day"] > "2026-10-10"][:2]          # 2 lessons x 4 = 8 hours after the cut-over
    before_zeka = [x["id"] for x in ls if x["day"] <= "2026-10-10"][:3]   # Zəka rows before the cut-over are not counted again
    s = standing(ls, absent(after + before_zeka), cutover="2026-10-10", opening=opening)
    assert s["missed_hours"] == 28 and s["status"] == "not_admitted" and s["as_of"] == "2026-10-10"
    assert standing(ls, absent(after[:1]), cutover="2026-10-10", opening=opening)["missed_hours"] == 24


def test_twenty_percent_imported_and_six_in_zeka_is_not_admitted():
    ls = lessons(25, hours=4)
    opening = {"unexcused_hours": 20, "excused_hours": 0, "as_of": "2026-10-10"}
    after = [x for x in ls if x["day"] > "2026-10-10"]
    six = {after[0]["id"]: {"status": "absent"}, after[1]["id"]: {"status": "absent"}}     # 8 hours = 8%
    assert standing(ls, six, cutover="2026-10-10", opening=opening)["status"] == "not_admitted"


def test_legacy_lesson_rows_give_the_same_standing_as_an_opening_balance():
    ls = lessons(25, hours=4)
    before = [x for x in ls if x["day"] <= "2026-10-10"]
    legacy = absent([x["id"] for x in before[:5]], source="legacy") | {x["id"]: {"status": "present", "source": "legacy"} for x in before[5:]}
    by_rows = standing(ls, legacy, cutover="2026-10-10")
    by_opening = standing(ls, {}, cutover="2026-10-10", opening={"unexcused_hours": 20, "excused_hours": 0, "as_of": "2026-10-10"})
    keys = ("missed_hours", "percent", "status")
    assert {k: by_rows[k] for k in keys} == {k: by_opening[k] for k in keys}


def test_nothing_imported_for_lessons_before_the_cut_over_is_incomplete_not_refused():
    ls = lessons(25, hours=4)
    s = standing(ls, absent([x["id"] for x in ls if x["day"] > "2026-10-10"]), cutover="2026-10-10")
    assert s["status"] == "incomplete", "never not_admitted on missing data"
    assert standing(lessons(5, first_day=20), {}, cutover="2026-10-10")["status"] == "normal", "no lesson before the cut-over"


def test_marks_default_to_present_and_refuse_strangers():
    marks, problem = domain.marks_input({"marks": {"2": "absent", "3": "late"}}, {1, 2, 3})
    assert problem is None and marks == {1: "present", 2: "absent", 3: "late"}
    assert domain.marks_input({"marks": {"9": "absent"}}, {1})[1] is not None
    assert domain.marks_input({"marks": {"1": "excused"}}, {1})[1] is None, "an excused row is sent back as it is; the service refuses a new one"
    assert domain.marks_input({"marks": {"1": "ill"}}, {1})[1] is not None
    assert domain.marks_input({"marks": ["1"]}, {1})[1] is not None


def test_the_edit_window():
    at = datetime.fromisoformat
    assert domain.window_open("2026-11-18", "10:20", at("2026-11-18T08:00"), 48)
    assert domain.window_open("2026-11-18", "10:20", at("2026-11-20T10:20"), 48)
    assert not domain.window_open("2026-11-18", "10:20", at("2026-11-20T10:21"), 48)
    assert not domain.window_open("2026-11-18", "10:20", at("2026-11-17T23:59"), 48), "not before the lesson's day"


def test_the_syllabus_may_only_lower_the_limit():
    assert domain.effective_limit(25, None) == 25 and domain.effective_limit(25, 20) == 20 and domain.effective_limit(25, 30) == 25
