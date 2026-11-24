"""The timetable solver at the scale of one department-term (tasks/todo.md, Task 48; docs/perf/timetable.md): about
1 250 units, 300 groups, 90 teachers and 60 rooms (tools/ttbench.py, synthetic ids only) meet the department column of
the targets with 0 hard violations and 0 unplaced meetings; a draft's placements are written in one short transaction."""
import json
import sqlite3
import time
import tracemalloc

import pytest
import ttbench

from zeka.core import migrate
from zeka.modules.timetable import domain, solver

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def department():
    return ttbench.synthetic(units=1250, groups=300, teachers=90, rooms=60, seed=1)


def test_a_department_term_meets_the_targets(department):
    out = ttbench.bench(department, iters=50_000, seed=1)
    assert out["units"] == 1250 and out["meetings"] >= 1250
    assert out["hard"] == 0 and out["unplaced"] == 0, out
    assert out["soft"] == out["scorecard_soft"], "the solver's running cost is the scorecard's"
    assert out["soft"] < out["after_construct"][1], "the improvement phase lowers the cost"
    assert out["prepare_s"] <= 1, out
    assert out["construct_s"] <= 3, out
    assert out["iterations"] == 50_000 or out["stopped"] == "stall", out
    assert out["improve_s"] <= 30, out
    assert out["check_s"] <= 1, out


def test_the_solver_s_memory_stays_within_80_mb(department):
    tracemalloc.start()
    try:
        model = solver.prepare(department)
        state = solver.run(model, seed=1, budget=2000)
        res = solver.result(model, state)
        domain.scorecard(department, res["placements"])
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak <= 80 * 2**20, peak // 2**20


def test_a_draft_is_written_in_one_short_transaction(department, tmp_path):
    model = solver.prepare(department)
    res = solver.result(model, solver.run(model, seed=1, budget=0))
    conn = sqlite3.connect(tmp_path / "t.db", isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        migrate.apply(conn)
        rows = [(1, p["key"], p["unit_id"], p["part"], p["weekday"], p["period"], p["duration"], p["weeks"], p["room_id"], int(p["locked"]))
                for p in res["placements"]]
        t = time.perf_counter()
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT INTO tt_versions(id, term_id, status, scope, created_by, created_at) VALUES(1, 1, 'draft', ?, 1, '2026-11-19T10:00:00')",
                     (json.dumps({"all": True}),))
        conn.executemany("INSERT INTO tt_placements(version_id, meeting_key, unit_id, part, weekday, period, duration, weeks, room_id, locked, "
                         "origin) VALUES(?,?,?,?,?,?,?,?,?,?,'solver')", rows)
        conn.execute("COMMIT")
        took = time.perf_counter() - t
        assert conn.execute("SELECT COUNT(*) FROM tt_placements WHERE version_id=1").fetchone()[0] == len(rows) >= 1250
        assert took <= 0.05, took          # the target is 20 ms; the margin is for a shared CI machine
    finally:
        conn.close()


def test_the_hours_report_grows_linearly_with_the_units():
    """2026-11-24 measurement: the report matched every unit against every meeting (1.2 s for 5 000 units; 0.47 s of the
    university term's report page). Grouped once, 5 000 units take about 0.1 s (docs/perf/baseline.md)."""
    p = ttbench.synthetic(units=5000, groups=1250, teachers=350, rooms=60, seed=1)
    t = time.perf_counter()
    rep = domain.hours_report(p, [], {"teaching_start": "2026-09-14", "teaching_end": "2026-12-27"}, [])
    took = time.perf_counter() - t
    assert len(rep["units"]) == 5000 and all(x["reasons"] for x in rep["units"])
    assert took <= 0.4, took           # the margin is for a shared CI machine
