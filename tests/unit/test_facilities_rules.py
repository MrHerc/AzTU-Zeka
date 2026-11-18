"""Rooms (tasks/todo.md, Task 18): how a timetable text names a room, and what a room's page shows now and next."""
from datetime import date

from zeka.modules.facilities import domain

TUE = date(2026, 11, 24)                 # a Tuesday
ROWS = [{"weekday": 2, "start": "09:00", "end": "10:20", "course": "A"}, {"weekday": 2, "start": "12:00", "end": "13:20", "course": "B"},
        {"weekday": 4, "start": "10:30", "end": "11:50", "course": "C"}]


def always(d):
    return True


def test_room_texts_compare_without_case_spaces_or_dotless_i():
    assert domain.room_key("Əsas korpus, 118") == domain.room_key("ƏSAS  KORPUS,118")
    assert domain.room_key("İT korpusu, 101") == domain.room_key("IT korpusu, 101") == domain.room_key("it korpusu,101")
    assert domain.room_key("EK-118") != domain.room_key("EK-1180")


def test_a_text_two_rooms_answer_to_links_neither():
    b = {"name": "Əsas korpus"}
    idx = domain.index([({"id": 1, "code": "EK-118", "number": "118", "name": "Fizika"}, b),
                        ({"id": 2, "code": "EK-B118", "number": "118", "name": None}, b)])
    assert idx[domain.room_key("EK-118")] == 1 and idx[domain.room_key("Fizika, 118")] == 1
    assert idx[domain.room_key("Əsas korpus, 118")] is None


def test_the_lesson_in_progress_and_the_next_one():
    cur, nxt = domain.now_and_next(ROWS, TUE, "09:30", always)
    assert cur["course"] == "A" and nxt == (TUE, ROWS[1])
    cur, nxt = domain.now_and_next(ROWS, TUE, "10:20", always)
    assert cur is None, "a lesson ends at its end time"
    cur, nxt = domain.now_and_next(ROWS, TUE, "14:00", always)
    assert cur is None and nxt == (date(2026, 11, 26), ROWS[2])


def test_closed_days_hold_no_lesson():
    holiday = domain.teaching_day({"teaching_start": "2026-09-15", "teaching_end": "2026-12-31"}, ["2026-11-24", "2026-11-26"])
    cur, nxt = domain.now_and_next(ROWS, TUE, "09:30", holiday)
    assert cur is None and nxt == (date(2026, 12, 1), ROWS[0])
    ended = domain.teaching_day({"teaching_start": "2026-09-15", "teaching_end": "2026-11-24"}, [])
    assert domain.now_and_next(ROWS, TUE, "14:00", ended) == (None, None), "nothing after the term's last teaching day"
    assert domain.now_and_next(ROWS, TUE, "09:30", domain.teaching_day(None, [])) == (None, None), "no term: no lessons"
