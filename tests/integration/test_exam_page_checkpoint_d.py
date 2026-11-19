"""Browser regression tests for the Checkpoint D frontend fixes (docs/review/checkpoint-d-2026-11-19.md, section G):
the exam page (exam.js), the proctor board (proctor.js) and the student's exam list (exams.js). One node run
(tests/e2e/exam_checkpoint_d.js, Playwright, fake clock, page.route() failures) sees every scenario; each test below
asserts one finding id. Skipped without node and Playwright, like test_exam_page.py."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from zeka.legacy import store

SCRIPT = Path(__file__).resolve().parents[1] / "e2e" / "exam_checkpoint_d.js"


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


@pytest.fixture(scope="module")
def seen(app_db):
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
    r = teacher.post(f"/api/courses/{cid}/exams", {"title": "Brauzer sınağı D", "day": store.now().date().isoformat(), "start": "00:01",
                                                   "end": "23:59", "duration_min": 60, "plan": [{"topic": "Brauzer", "count": 3}]})
    assert r.status == 200, r.text
    eid = r.json["id"]
    assert teacher.post(f"/api/exams/{eid}/open").status == 200
    run = subprocess.run([shutil.which("node"), str(SCRIPT), app_db.url, str(eid), str(student.user["id"]), str(cid)],
                         capture_output=True, text=True, timeout=240)
    assert run.stdout.strip(), run.stderr
    return json.loads(run.stdout.strip().splitlines()[-1])


def got(seen, key):
    assert "error" not in seen[key], seen[key]
    return seen[key]


def test_sf1_a_refused_save_is_not_a_lost_answer(seen):
    s = got(seen, "SF-1")
    assert s["gets_after_403"] >= 1, "401/403 reloads the exam view (load())"
    assert s["queued_after_503"] == 1, "a 5xx keeps the answer queued"
    assert s["queued_after_recovery"] == 0 and s["on_server"], "and it is sent once the server answers 200"
    assert s["queued_after_400"] == 0 and s["queued_after_404"] == 0, "400/404 drop it"


def test_bug_flush_an_empty_first_flush_does_not_block_every_later_save(seen):
    """After a reload with an attempt running, the first flush finds an empty queue: later answers are still sent."""
    s = got(seen, "BUG-flush")
    assert s["puts"] >= 1 and s["on_server"]


def test_sf2_answers_are_sent_when_local_storage_throws(seen):
    s = got(seen, "SF-2")
    assert s["on_server"], "the in-memory queue still sends the answer"
    assert s["warning"] >= 1, "and the page warns that the browser cannot keep answers"


def test_sf3_a_manual_submit_with_queued_answers_is_refused(seen):
    s = got(seen, "SF-3")
    assert s["alerts"] >= 1 and s["submits_while_failing"] == 0, "refused on the page, nothing posted"
    assert s["queued"] == 1, "the queued answer is not lost"
    assert s["leave_card"] and s["submits_after"] == 1 and s["on_server"], "after the save works the submit goes through"
    assert s["reopen"] == 200


def test_sf9_answers_after_the_deadline_are_counted_on_the_final_card(seen):
    s = got(seen, "SF-9")
    assert s["final_card"]
    assert any("1" in w for w in s["warn"]), s["warn"]


def test_sf10_a_refused_submit_is_never_silent(seen):
    s = got(seen, "SF-10")
    assert s["gets_after_409"] >= 1, "a 409 reloads the exam view"
    assert s["alerts_409"] == 0
    assert s["alerts_500"] == 1, "another status shows the offline message"


def test_sf17_repeated_5xx_gives_one_retry_chain_and_no_blank_page(seen):
    s = got(seen, "SF-17")
    assert s["blank_text"] > 0, "the page says the server is not answering"
    assert s["gets_no_view"] <= 16, s            # one 3 s chain over 40 s (about 14)
    assert s["gets_paused"] <= 18, s             # chain plus the 5 s paused poll, never one chain per call (old code: 50+)
    assert s["text_after"] > 0


def test_new_g1_the_automatic_submit_says_it_is_automatic(seen):
    s = got(seen, "NEW-G1")
    assert s["bodies"] and all(b == {"auto": True} for b in s["bodies"]), s


def test_new_g2_a_reopened_attempt_reaches_the_open_page(seen):
    s = got(seen, "NEW-G2")
    assert s["submitted"] and s["reopen"] == 200
    assert s["back"], "the page polling in the submitted state returns to the open attempt"


def test_sf13_the_board_countdown_does_not_jump_back_and_refusals_are_said(seen):
    s = got(seen, "SF-13")
    assert s["countdown_drop"] >= 10, "12 s of failed polls: the countdown kept going down"
    for code in (403, 404):
        assert s[f"rows_after_{code}"] == 0 and s[f"says_{code}"], f"{code} shows the failure view"


def test_sf16_the_students_exam_list_says_when_it_cannot_load(seen):
    assert "exams-boom" in got(seen, "SF-16")["text"]
