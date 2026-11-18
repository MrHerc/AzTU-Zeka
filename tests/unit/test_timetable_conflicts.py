"""Timetable rules (tasks/todo.md, Task 19): clashes of rooms, teachers and (sub)groups, the days a weekly row holds a
lesson, and the iCalendar text."""
from datetime import date, datetime, timezone

from zeka.modules.timetable import domain

A, B, C = 1, 2, 3
TERM = {"teaching_start": "2026-09-14", "teaching_end": "2026-10-11"}      # Monday 14 Sep to Sunday 11 Oct: 4 weeks


def slot(i, weekday=1, start="09:00", end="10:20", weeks="all", room=None, teacher=None, groups=()):
    return {"id": i, "weekday": weekday, "start": start, "end": end, "weeks": weeks, "room": room, "teacher_id": teacher,
            "groups": list(groups)}


def test_a_stream_three_seminars_and_two_lab_subgroups_do_not_clash():
    rows = [slot(1, start="09:00", end="10:20", room="r220", teacher=10, groups=[(A, None), (B, None), (C, None)]),
            slot(2, start="10:30", end="11:50", room="r224", teacher=20, groups=[(A, None)]),
            slot(3, start="12:00", end="13:20", room="r224", teacher=20, groups=[(B, None)]),
            slot(4, start="13:50", end="15:10", room="r224", teacher=20, groups=[(C, None)]),
            slot(5, weekday=2, room="r316", teacher=30, groups=[(A, 1)]),
            slot(6, weekday=2, room="r121", teacher=40, groups=[(A, 2)])]
    assert all(domain.conflicts(r, rows) == [] for r in rows)


def test_the_same_group_twice_at_once_clashes():
    stream = slot(1, groups=[(A, None), (B, None)])
    found = domain.conflicts(slot(9, start="10:00", end="11:00", groups=[(B, None)]), [stream])
    assert found == [{"id": 1, "what": "group", "groups": [B]}]


def test_a_whole_group_clashes_with_each_of_its_subgroups():
    assert domain.conflicts(slot(9, groups=[(A, None)]), [slot(1, groups=[(A, 2)])])[0]["what"] == "group"
    assert domain.conflicts(slot(9, groups=[(A, 1)]), [slot(1, groups=[(A, None)])])[0]["what"] == "group"
    assert domain.conflicts(slot(9, groups=[(A, 1)]), [slot(1, groups=[(A, 2)])]) == []


def test_rooms_teachers_times_and_weeks():
    base = slot(1, room="r1", teacher=7)
    assert [x["what"] for x in domain.conflicts(slot(9, room="r1"), [base])] == ["room"]
    assert [x["what"] for x in domain.conflicts(slot(9, teacher=7), [base])] == ["teacher"]
    assert domain.conflicts(slot(9, start="10:20", end="11:00", room="r1"), [base]) == [], "back to back is not a clash"
    assert domain.conflicts(slot(9, weekday=2, room="r1"), [base]) == []
    odd = slot(1, weeks="odd", room="r1")
    assert domain.conflicts(slot(9, weeks="even", room="r1"), [odd]) == []
    assert domain.conflicts(slot(9, weeks="all", room="r1"), [odd]) != []
    assert domain.conflicts(slot(1, room="r1"), [slot(1, room="r1")]) == [], "a row does not clash with itself"


def test_lessons_follow_the_week_pattern_and_skip_holidays():
    every = domain.lesson_dates({"weekday": 3, "weeks": "all"}, TERM, [])
    assert [d.isoformat() for d in every] == ["2026-09-16", "2026-09-23", "2026-09-30", "2026-10-07"]
    odd = domain.lesson_dates({"weekday": 3, "weeks": "odd"}, TERM, [])
    even = domain.lesson_dates({"weekday": 3, "weeks": "even"}, TERM, [])
    assert [d.day for d in odd] == [16, 30] and [d.day for d in even] == [23, 7]
    assert date(2026, 9, 23) not in domain.lesson_dates({"weekday": 3, "weeks": "all"}, TERM, ["2026-09-23"])
    assert domain.lesson_dates({"weekday": 3, "weeks": "all"}, TERM, [], start_from=date(2026, 10, 1)) == [date(2026, 10, 7)]


def test_no_lesson_outside_the_teaching_period():
    term = {"teaching_start": "2026-09-16", "teaching_end": "2026-09-29"}         # Wednesday to Tuesday
    days = domain.lesson_dates({"weekday": 1, "weeks": "all"}, term, [])
    assert days == [date(2026, 9, 21), date(2026, 9, 28)]
    assert domain.week_no(date(2026, 9, 21), date(2026, 9, 16)) == 2, "week 1 is the week of the first teaching day"


def test_a_student_attends_the_units_of_their_group_and_subgroup():
    s = {"group_id": A, "subgroup": 1}
    assert domain.attends(s, [A, B], None) and domain.attends(s, [A], 1) and domain.attends(s, [], None)
    assert not domain.attends(s, [A], 2) and not domain.attends(s, [B], None)


def test_the_calendar_is_rfc_5545_text():
    ev = {"id": 7, "day": "2026-11-24", "start": "09:00", "end": "10:20", "summary": "Ali riyaziyyat I, mühazirə; " + "ə" * 60,
          "location": "Əsas korpus, 220", "status": "cancelled", "note": "Səbəb\nyeni sətir"}
    text = domain.calendar([ev], tzid="Asia/Baku", offset="+0400", host="zeka.aztu.edu.az",
                           stamp=datetime(2026, 11, 18, 20, 0, tzinfo=timezone.utc), name="Zəka")
    lines = text.split("\r\n")
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    assert all(len(x.encode()) <= 75 for x in lines)
    unfolded = text.replace("\r\n ", "")
    for want in ("BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:", "TZID:Asia/Baku", "TZOFFSETTO:+0400", "UID:lesson-7@zeka.aztu.edu.az",
                 "DTSTAMP:20261118T200000Z", "DTSTART;TZID=Asia/Baku:20261124T090000", "DTEND;TZID=Asia/Baku:20261124T102000",
                 "STATUS:CANCELLED", "LOCATION:Əsas korpus\\, 220", "DESCRIPTION:Səbəb\\nyeni sətir", "END:VCALENDAR"):
        assert want in unfolded, want
    assert "SUMMARY:Ali riyaziyyat I\\, mühazirə\\; " in unfolded
