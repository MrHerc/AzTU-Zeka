"""tools/queryplan.py (Checkpoint F, PY-F5): the exam's entry and start and the leader's sign-in are steps of their own,
timed and labelled with their scenario, not requests made while the next step is fetched."""
import json
import re

import queryplan


def test_every_exam_request_and_the_leader_s_sign_in_is_a_step(monkeypatch):
    def outside(*_a, **_k):
        raise AssertionError("a request sent from inside the step generator is neither timed nor labelled")
    monkeypatch.setattr(queryplan, "_send", outside)
    answers = {"/api/exams/3/enter": ("zeka_sid=sitting; Path=/; HttpOnly", b"{}"),
               "/api/exams/3/start": ("", json.dumps({"questions": [{"id": 11}, {"id": 12}]}).encode()),
               "/api/auth/demo": ("zeka_sid=leader; Path=/", b"{}")}
    steps, answer, seen = queryplan._routes("zeka_sid=student", [7], (3, ["zeka_sid=entry"], "zeka_sid=proctor")), None, []
    while True:
        try:
            step = steps.send(answer)
        except StopIteration:
            break
        seen.append(step)
        answer = answers.get(step[2], ("", b"{}"))
    later = [(name, method, re.sub(r"\d+", "N", path), cookie) for name, method, path, cookie, _ in seen if name != "mixed"]
    assert later == [
        ("exam", "POST", "/api/exams/N/enter", "zeka_sid=entry"), ("exam", "POST", "/api/exams/N/start", "zeka_sid=sitting"),
        ("exam", "PUT", "/api/exams/N/answers/N", "zeka_sid=sitting"), ("exam", "PUT", "/api/exams/N/answers/N", "zeka_sid=sitting"),
        ("exam", "GET", "/api/exams/N", "zeka_sid=sitting"), ("exam", "GET", "/api/exams/N/board?after=N", "zeka_sid=proctor"),
        ("exam", "POST", "/api/exams/N/submit", "zeka_sid=sitting"), ("leader", "POST", "/api/auth/demo", ""),
        ("leader", "GET", "/api/analytics", "zeka_sid=leader"), ("leader", "GET", "/api/insight/evidence", "zeka_sid=leader")]
    assert len(seen) - len(later) == 5, "the mixed scenario's read and write routes"
