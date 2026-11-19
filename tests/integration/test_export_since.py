"""Exports with ``--since`` (tasks/todo.md, Task 37): attendance marks and grades written at known moments (``clock.now``
patched; the server runs in this process), then ``manage.py export --kind attendance|grades --since T`` gives only the
rows written or changed after T, whatever zone T is written in, and the screen's export gives the same rows. The
queries use the indexes of migration 0371.

The marks and scores are written on the screen by the administrator (a corrector: any held lesson, with a reason). The
moments are minutes apart: a staff session ends after an idle hour."""
import csv
import io
import os
import subprocess
import sys
from datetime import timedelta, timezone
from pathlib import Path

import pytest

from zeka.core import clock
from zeka.legacy import store
from zeka.modules.integration import export

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = "Kollokvium 2"


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def wall(t) -> str:
    return t.astimezone(clock.ZONE).replace(tzinfo=None).isoformat()


FLIP = {"present": "absent", "absent": "present", "late": "present"}


def mark(admin, lid: int, flip: list[int]):
    """Send every mark of the lesson as it is, the students in ``flip`` changed: only those rows are written."""
    students = admin.get(f"/api/journal/lessons/{lid}").json["students"]
    assert all(s["status"] for s in students), "every student on a held demo lesson has a mark"
    marks = {str(s["id"]): FLIP[s["status"]] if s["id"] in flip else s["status"] for s in students}
    r = admin.put(f"/api/journal/lessons/{lid}/attendance", {"marks": marks, "reason": "eksport sınağı"})
    assert r.status == 200, r.text


def score(admin, course: int, cells: list[tuple[int, float]]):
    r = admin.put(f"/api/journal/courses/{course}/grades", {"cells": [{"student_id": s, "component": COMPONENT, "score": v} for s, v in cells],
                                                            "reason": "eksport sınağı"})
    assert r.status == 200, r.text


@pytest.fixture(scope="module")
def world(app_db):
    """BEFORE: lesson 1 of students 1 and 2, their scores. AFTER: student 1 of lesson 1 and student 3 of lesson 2 again,
    the score of student 1 changed and student 3's new. T lies between."""
    admin = app_db.client("admin")
    base = clock.now().replace(microsecond=0)
    before, t, after = base + timedelta(minutes=2), base + timedelta(minutes=5), base + timedelta(minutes=10)
    course = 1
    l1, l2 = [x["id"] for x in q("SELECT id FROM lessons WHERE course_id=? AND day<? AND status='scheduled' ORDER BY day DESC, start DESC "
                                 "LIMIT 2", (course, store.now().date().isoformat()))]
    s1, s2 = [s["id"] for s in admin.get(f"/api/journal/lessons/{l1}").json["students"] if s["status"] in FLIP][:2]
    s3 = [s["id"] for s in admin.get(f"/api/journal/lessons/{l2}").json["students"] if s["status"] in FLIP and s["id"] not in (s1, s2)][0]
    real = clock.now
    try:
        clock.now = lambda: before
        mark(admin, l1, [s1, s2])
        score(admin, course, [(s1, 5), (s2, 6)])
        clock.now = lambda: after
        mark(admin, l1, [s1])
        mark(admin, l2, [s3])
        score(admin, course, [(s1, 7), (s3, 8)])
    finally:
        clock.now = real
    no = {r["id"]: r["student_no"] for r in q("SELECT id, student_no FROM users WHERE id IN (?,?,?)", (s1, s2, s3))}
    return {"t": t, "after": after, "before": before, "l1": l1, "l2": l2, "no": no, "s": (s1, s2, s3)}


def cli(*args) -> str:
    r = subprocess.run([sys.executable, str(ROOT / "backend" / "manage.py"), "export", *args], capture_output=True,
                       env={**os.environ, "ZEKA_DATA": str(store.DATA)}, timeout=120)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return r.stdout.decode("utf-8")


def table(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def zones(t) -> list[str]:
    """The same moment written in Baku time, in UTC with Z, and in another zone."""
    return [t.astimezone(clock.ZONE).isoformat(), t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            t.astimezone(timezone(timedelta(hours=-3))).isoformat()]


def test_attendance_since_gives_only_the_marks_written_or_changed_after_it(app_db, world):
    s1, _, s3 = world["s"]
    no = world["no"]
    outs = [cli("--kind", "attendance", "--since", since) for since in zones(world["t"])]
    assert outs[0] == outs[1] == outs[2], "one moment, whatever its zone"
    got = table(outs[0])
    assert {(int(r["lessonId"]), r["identifier"]) for r in got} == {(world["l1"], no[s1]), (world["l2"], no[s3])}
    assert {r["markedAt"] for r in got} == {wall(world["after"])} and all(r["courseCode"] == "ELM-2105" for r in got)
    both = table(cli("--kind", "attendance", "--since", wall(world["before"] - timedelta(seconds=1))))     # no offset: Baku time
    assert {(int(r["lessonId"]), r["identifier"]) for r in both} == {(world["l1"], no[s1]), (world["l1"], no[world["s"][1]]),
                                                                     (world["l2"], no[s3])}, "student 2 was written before T only"
    assert len(table(cli("--kind", "attendance"))) == q("SELECT COUNT(*) n FROM attendance")[0]["n"], "without --since: every mark"
    screen = app_db.client("admin").get(f"/api/integration/export/attendance?since={zones(world['t'])[0].replace('+', '%2B')}")
    assert screen.status == 200 and screen.text == outs[0], "the screen gives the same rows"
    assert screen.headers["Content-Disposition"] == 'attachment; filename="attendance.csv"'


def test_grades_since_gives_only_the_scores_written_or_changed_after_it(app_db, world):
    s1, _, s3 = world["s"]
    no = world["no"]
    got = table(cli("--kind", "grades", "--since", zones(world["t"])[2]))
    assert {(r["identifier"], r["component"], float(r["score"])) for r in got} == {(no[s1], COMPONENT, 7.0), (no[s3], COMPONENT, 8.0)}
    assert all(r["status"] == "draft" and r["updatedAt"] == wall(world["after"]) for r in got)
    screen = app_db.client("admin").get(f"/api/integration/export/grades?since={zones(world['t'])[1]}")
    assert screen.status == 200 and table(screen.text) == got
    assert app_db.client("admin").get("/api/integration/export/grades?since=yesterday").status == 400


def test_the_since_queries_use_an_index(world):
    c = store.connect()
    seen: list[str] = []
    c.set_trace_callback(seen.append)
    try:
        export.attendance_csv(c, world["t"])
        export.grades_csv(c, world["t"])
        c.set_trace_callback(None)
        plans = {sql: " ".join(r[3] for r in c.execute("EXPLAIN QUERY PLAN " + sql)) for sql in seen
                 if sql.startswith("SELECT") and ("FROM attendance" in sql or "FROM grades" in sql)}
    finally:
        c.close()
    assert len(plans) == 2
    for sql, plan in plans.items():
        index = "idx_attendance_marked_at" if "FROM attendance" in sql else "idx_grades_updated_at"
        assert index in plan, plan


def test_only_the_administrator_exports(app_db, world):
    for role in ("teacher", "office", "leader", "student"):
        assert app_db.client(role).get("/api/integration/export/attendance").status == 403, role
    admin = app_db.client("admin")
    assert admin.get("/api/integration/export/nope").status == 404
    reg = admin.get("/api/integration/export/registry?registry=students&columns=student_no,group")
    assert reg.status == 200 and reg.text.splitlines()[0] == "student_no,group"
    bad = admin.get("/api/integration/export/registry?columns=student_no,password_hash", lang="en")
    assert bad.status == 400 and "password_hash" in bad.json["error"]
    assert q("SELECT COUNT(*) n FROM audit WHERE action='export'")[0]["n"] >= 3, "every export is in the audit log"
