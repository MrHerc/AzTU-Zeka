"""The exam page in a real browser (tasks/todo.md, Task 27): answers typed while offline reach the server when the
connection is back, the attempt goes on after a reload, and the timer follows the server even when the computer's
clock is four hours wrong. Needs node with Playwright (skipped without them); the script is tests/e2e/exam_offline.js."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from zeka.legacy import store

SCRIPT = Path(__file__).resolve().parents[1] / "e2e" / "exam_offline.js"


def _playwright() -> bool:
    node = shutil.which("node")
    return bool(node) and subprocess.run([node, "-e", "require('playwright')"], capture_output=True, timeout=30).returncode == 0


pytestmark = pytest.mark.skipif(not _playwright(), reason="node with Playwright is not installed")


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def test_offline_answers_arrive_and_the_timer_follows_the_server(app_db):
    teacher, student = app_db.client("teacher"), app_db.client("student")
    cid = q("SELECT c.id FROM courses c JOIN enrollments e ON e.course_id=c.id WHERE c.teacher_id=? AND e.user_id=? ORDER BY c.id LIMIT 1",
            (teacher.user["id"], student.user["id"]))[0]["id"]
    c = store.connect()
    try:
        for i in range(3):
            c.execute("INSERT INTO questions(course_id,qtype,text,options,answer,unit,explanation,difficulty,topic,status,purpose,created_at) "
                      "VALUES(?,'numeric',?,'[]','42','','x','Asan','Brauzer','approved','exam','x')", (cid, f"Brauzer sualı {i}"))
        c.commit()
    finally:
        c.close()
    r = teacher.post(f"/api/courses/{cid}/exams", {"title": "Brauzer sınağı", "day": store.now().date().isoformat(), "start": "00:01",
                                                   "end": "23:59", "duration_min": 60, "plan": [{"topic": "Brauzer", "count": 3}]})
    assert r.status == 200, r.text
    eid = r.json["id"]
    assert teacher.post(f"/api/exams/{eid}/open").status == 200
    run = subprocess.run([shutil.which("node"), str(SCRIPT), app_db.url, str(eid)], capture_output=True, text=True, timeout=120)
    seen = json.loads(run.stdout.strip().splitlines()[-1])
    assert "error" not in seen, seen
    assert seen["enter"] == 200 and seen["queued"] == 2 and seen["queued_after"] == 0
    assert seen["timer_delta"] <= 2, "a clock four hours wrong does not move the deadline"
    values = {r["value"] for r in q("SELECT value FROM exam_answers WHERE attempt_id=(SELECT id FROM exam_attempts WHERE exam_id=?)", (eid,))}
    assert {'"41"', '"42"'} <= values, values
    assert seen["after_reload"] == ["41", "42"], "the attempt goes on after a reload"
