"""Rooms (tasks/todo.md, Task 18): how a timetable text names a room, and what a room's page shows now and next."""
from datetime import date

from zeka.modules.facilities import domain

TUE = date(2026, 11, 24)                 # a Tuesday
LESSONS = [{"day": "2026-11-24", "start": "09:00", "end": "10:20", "course": "A"}, {"day": "2026-11-24", "start": "12:00", "end": "13:20", "course": "B"},
           {"day": "2026-11-26", "start": "10:30", "end": "11:50", "course": "C"}]


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
    cur, nxt = domain.now_and_next(LESSONS, TUE, "09:30")
    assert cur["course"] == "A" and nxt["course"] == "B"
    cur, nxt = domain.now_and_next(LESSONS, TUE, "10:20")
    assert cur is None and nxt["course"] == "B", "a lesson ends at its end time"
    cur, nxt = domain.now_and_next(LESSONS, TUE, "14:00")
    assert cur is None and nxt["day"] == "2026-11-26"
    assert domain.now_and_next(LESSONS, date(2026, 11, 27), "08:00") == (None, None)
    assert domain.now_and_next(list(reversed(LESSONS)), TUE, "08:00")[1]["course"] == "A", "the order of the input does not matter"
