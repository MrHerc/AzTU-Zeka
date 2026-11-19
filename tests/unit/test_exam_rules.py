"""The exam core's rules (tasks/todo.md, Task 26): the window in UTC, forms by seed and plan, what a student sees."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from zeka.modules.exam import domain

POOL = [{"id": i, "qtype": "mcq" if i % 2 else "numeric", "text": f"S{i}", "options": ["a", "b", "c", "d"] if i % 2 else [],
         "answer": "0", "explanation": "izah", "difficulty": "Asan" if i <= 12 else "Orta", "topic": "Om", "unit": ""} for i in range(1, 21)]
PLAN = [{"difficulty": "Asan", "topic": None, "count": 6}, {"difficulty": "Orta", "topic": None, "count": 4}]


def test_a_window_entered_in_baku_time_opens_in_utc():
    baku = ZoneInfo("Asia/Baku")
    assert domain.to_utc(date(2026, 12, 10), "10:00", baku).isoformat() == "2026-12-10T06:00:00+00:00"
    v, problem = domain.exam_input({"title": "Yekun imtahan", "day": "2026-12-10", "start": "10:00", "end": "12:00", "duration_min": 90,
                                    "plan": PLAN}, baku, 20)
    assert problem is None and v["opens_at"] == "2026-12-10T06:00:00+00:00" and v["closes_at"] == "2026-12-10T08:00:00+00:00"


def test_bad_exams_are_refused():
    base = {"title": "Yekun imtahan", "day": "2026-12-10", "start": "10:00", "end": "12:00", "duration_min": 90, "plan": PLAN}
    for bad in ({"start": "12:00", "end": "10:00"}, {"duration_min": 150}, {"duration_min": 2}, {"kind": "x"}, {"plan": []},
                {"plan": [{"count": 0}]}, {"allowed_cidrs": ["10.0.0.0/33"]}, {"day": "10.12.2026"}, {"title": "x"}):
        assert domain.exam_input({**base, **bad}, None, 20)[1] is not None, bad


def test_two_students_get_different_forms_and_one_student_always_the_same():
    a1 = domain.build_form(POOL, PLAN, domain.seed("s", 1, 101))
    a2 = domain.build_form(POOL, PLAN, domain.seed("s", 1, 101))
    b = domain.build_form(POOL, PLAN, domain.seed("s", 1, 102))
    assert a1 == a2 and a1 != b
    assert len(a1) == 10 and len({x["qid"] for x in a1}) == 10
    assert sum(1 for x in a1 if POOL[x["qid"] - 1]["difficulty"] == "Asan") == 6, "the plan's counts"
    assert any(x["order"] != sorted(x["order"]) for x in a1 if POOL[x["qid"] - 1]["qtype"] == "mcq"), "options are shuffled"


def test_a_plan_the_pool_cannot_fill_is_refused():
    assert domain.plan_problem(POOL, [{"difficulty": "Orta", "topic": None, "count": 9}]) is not None
    assert domain.plan_problem(POOL, PLAN) is None


def test_a_student_sees_only_the_public_keys_and_answers_map_back():
    q = POOL[0]
    shown = domain.public(q, [2, 0, 3, 1])
    assert set(shown) == set(domain.PUBLIC) and shown["options"] == ["c", "a", "d", "b"]
    assert domain.original_value(q, [2, 0, 3, 1], 0) == 2, "the first option shown is the original third"


def test_an_attempt_ends_at_its_duration_or_the_window_s_end():
    s = datetime(2026, 12, 10, 6, 0, tzinfo=timezone.utc)
    assert domain.deadline(s, 90, s + timedelta(hours=2)) == s + timedelta(minutes=90)
    assert domain.deadline(s + timedelta(minutes=60), 90, s + timedelta(hours=2)) == s + timedelta(hours=2)
