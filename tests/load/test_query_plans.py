"""No full scan of a large table on the routes of the load scenarios (tasks/todo.md, Tasks 7 and 42).

tools/queryplan.py builds the university dataset (10 000 students, 100 000 attempts, 100 000 chunks) in its own process,
sends the mixed scenario (read and write routes) as a student, the exam scenario as a student and its proctor board (with a
released exam of 1 200 students beside it, so every exam table is large), and the leader's dashboard and Radar page, and
explains every statement the handlers ran. The leader's scans are reported, not failed: the dashboard counts every
course's rows and the Radar page reads every student's records (docs/perf/task42.md). The timetable builder's read routes
and a move run as the academic office over a term whose builder tables are all large (Task 48); the syllabus approval
queue and a term's overview over more than 1 000 versions and courses (AR-11).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.slow


def test_the_mixed_and_exam_routes_never_scan_a_table_with_more_than_1000_rows():
    env = {k: v for k, v in os.environ.items() if not k.startswith("ZEKA_")}
    run = subprocess.run([sys.executable, str(ROOT / "tools" / "queryplan.py"), "--dataset", "university"],
                         env={**env, "PYTHONIOENCODING": "utf-8"}, capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert run.returncode in (0, 1), run.stderr[-2000:]
    report = json.loads(run.stdout)
    assert report["statements"] > 50, report          # the routes really ran
    assert {"mixed", "exam", "leader", "timetable", "syllabus"} <= set(report["scenarios"]), report["scenarios"]
    assert min(report["syllabus_rows"].values()) > 1000, report["syllabus_rows"]      # the syllabus queue and overview (AR-11)
    big = {t for t, n in report["exam_rows"].items() if n > 1000}      # Checkpoint F (TE-F6): a scan of these would show
    assert {"exam_answers", "exam_attempts", "exam_events", "exam_forms", "exam_roster"} <= big, report["exam_rows"]
    tt = {t for t, n in report["tt_rows"].items() if n > 1000}
    assert {"tt_availability", "tt_availability_status", "tt_placements", "tt_runs", "tt_unit_needs", "tt_unplaced"} <= tt, report["tt_rows"]
    scans = {k: v for k, v in report["scans"].items() if k != "leader"}
    assert scans == {}, json.dumps(scans, ensure_ascii=False, indent=1)
