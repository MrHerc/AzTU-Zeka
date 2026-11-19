"""Two processes append to one exam's chain at once (tasks/todo.md, Task 30): 500 events give one chain with seq 1..500
and no gap, and it verifies. Each append reads the head and writes the next link under the write lock."""
import os
import subprocess
import sys
from pathlib import Path

from zeka.legacy import store
from zeka.modules.exam import service

ROOT = Path(__file__).resolve().parents[2]
WRITER = """
import sys
sys.path.insert(0, {backend!r})
from zeka.legacy import store
from zeka.modules.exam import repo
eid, tag = int(sys.argv[1]), sys.argv[2]
c = store.connect()
for i in range(250):
    repo.add_event(c, eid, "load.event", None, None, {{"writer": tag, "i": i}}, "2026-11-19T06:00:00+00:00")
    c.commit()
c.close()
"""


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def test_two_processes_make_one_gapless_chain(app_db):
    teacher = app_db.client("teacher")
    cid = q("SELECT id FROM courses WHERE teacher_id=? ORDER BY id LIMIT 1", (teacher.user["id"],))[0]["id"]
    c = store.connect()
    try:
        eid = c.execute("INSERT INTO exams(course_id,title,opens_at,closes_at,duration_min,plan,secret,created_at) "
                        "VALUES(?,'Paralel','2026-11-19T06:00:00+00:00','2026-11-19T08:00:00+00:00',60,'[]','s','x')", (cid,)).lastrowid
        c.commit()
    finally:
        c.close()
    env = {**os.environ, "ZEKA_DATA": str(store.DATA), "PYTHONIOENCODING": "utf-8"}
    code = WRITER.format(backend=str(ROOT / "backend"))
    procs = [subprocess.Popen([sys.executable, "-c", code, str(eid), tag], env=env, stderr=subprocess.PIPE) for tag in ("a", "b")]
    for p in procs:
        _, err = p.communicate(timeout=120)
        assert p.returncode == 0, err.decode("utf-8", "replace")[-800:]
    seqs = [r["seq"] for r in q("SELECT seq FROM exam_events WHERE exam_id=? ORDER BY seq", (eid,))]
    assert seqs == list(range(1, 501))
    c = store.connect()
    try:
        r = service.verify(c, eid)
    finally:
        c.close()
    assert r["problems"] == [] and r["events"] == 500
