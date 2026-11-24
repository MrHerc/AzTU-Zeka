"""tools/queryplan.py (Checkpoint F, PY-F5): the exam's entry and start, the leader's sign-in and the academic office's
sign-in and role switch (Task 48) are steps of their own, timed and labelled with their scenario, not requests made while
the next step is fetched."""
import json
import re

import queryplan


def test_every_exam_request_and_the_leader_s_sign_in_is_a_step(monkeypatch):
    def outside(*_a, **_k):
        raise AssertionError("a request sent from inside the step generator is neither timed nor labelled")
    monkeypatch.setattr(queryplan, "_send", outside)
    answers = {"/api/exams/3/enter": ("zeka_sid=sitting; Path=/; HttpOnly", b"{}"),
               "/api/exams/3/start": ("", json.dumps({"questions": [{"id": 11}, {"id": 12}]}).encode()),
               "/api/auth/demo": ("zeka_sid=leader; Path=/", b"{}"), "/api/me/role": ("zeka_sid=ao; Path=/", b"{}")}
    tt = {"term": 1, "version": 2, "group": 3, "teacher": 4, "room": 5, "placement": {"id": 6, "weekday": 1, "period": 2, "room_id": 5},
          "programme": 8, "course": 9, "department": 10, "work_role": "DD-WRL-001"}
    steps, answer, seen = queryplan._routes("zeka_sid=student", [7], (3, ["zeka_sid=entry"], "zeka_sid=proctor"), tt), None, []
    while True:
        try:
            step = steps.send(answer)
        except StopIteration:
            break
        seen.append(step)
        answer = answers.get(step[2], ("", b"{}"))
    screens = [(name, method, path, cookie) for name, method, path, cookie, _ in seen if name.startswith("screens:")]
    seen = [s for s in seen if not s[0].startswith("screens:")]
    # the screens of 2026-11-23/24: each role signs in as a step of its own, then each GET carries that role's session
    assert [x[:2] for x in screens[:6]] == [("screens:login", "POST")] * 6 and all(m == "GET" for _, m, _, _ in screens[6:]), screens
    assert {n.split(":")[1] for n, *_ in screens[6:]} == {"academic_office", "office", "leader", "dept_head", "admin", "teacher"}
    assert any(p.startswith("/api/syllabi/9/prerequisites?q=") for _, _, p, _ in screens) and len(screens) == 6 + 44, len(screens)
    later = [(name, method, re.sub(r"\d+", "N", path), cookie) for name, method, path, cookie, _ in seen if name != "mixed"]
    assert later == [
        ("exam", "POST", "/api/exams/N/enter", "zeka_sid=entry"), ("exam", "POST", "/api/exams/N/start", "zeka_sid=sitting"),
        ("exam", "PUT", "/api/exams/N/answers/N", "zeka_sid=sitting"), ("exam", "PUT", "/api/exams/N/answers/N", "zeka_sid=sitting"),
        ("exam", "GET", "/api/exams/N", "zeka_sid=sitting"), ("exam", "GET", "/api/exams/N/board?after=N", "zeka_sid=proctor"),
        ("exam", "POST", "/api/exams/N/submit", "zeka_sid=sitting"), ("leader", "POST", "/api/auth/demo", ""),
        ("leader", "GET", "/api/analytics", "zeka_sid=leader"), ("leader", "GET", "/api/insight/evidence", "zeka_sid=leader"),
        ("leader", "GET", "/api/radar", "zeka_sid=leader"), ("timetable", "POST", "/api/auth/demo", ""),
        ("timetable", "POST", "/api/me/role", "zeka_sid=leader")] + [("timetable", "GET", x, "zeka_sid=ao") for x in (
        "/api/timetable/build/N", "/api/timetable/build/N/readiness", "/api/timetable/build/N/units", "/api/timetable/build/N/groups",
        "/api/timetable/build/N/versions", "/api/timetable/build/N/teachers", "/api/timetable/build/N/teachers/N/availability", "/api/timetable/versions/N/grid?group_id=N",
        "/api/timetable/versions/N/grid?teacher_id=N", "/api/timetable/versions/N/grid?room_id=N", "/api/timetable/versions/N/unplaced",
        "/api/timetable/versions/N/scorecard", "/api/timetable/versions/N/hours", "/api/timetable/versions/N/placements/N/options",
        "/api/timetable/settings")] + [
        ("timetable", "POST", "/api/timetable/versions/N/placements/N/move", "zeka_sid=ao")] + [
        ("syllabus", "GET", x, "zeka_sid=ao") for x in ("/api/syllabi/queue", "/api/syllabi/queue?page=N", "/api/syllabi/overview?term=N",
                                                       "/api/syllabi/overview?term=N&state=none&format=csv")] + [
        ("syllabus", "POST", "/api/auth/demo", ""), ("syllabus", "GET", "/api/syllabi/overview?term=N&q=QP", "zeka_sid=leader")]
    assert len(seen) - len(later) == 5, "the mixed scenario's read and write routes"
