"""Task 42, chaos: an exam keeps every answer the server acknowledged through a ``kill -9`` of a worker or of the whole
server, and a write lock that another process holds for 2 seconds gives no 5xx and loses no answer. Each test runs
``backend/run.py`` on a throw-away dataset with an open exam (``tools/loadtest.py``'s ``exam_setup``). An SMTP outage is
``test_email_outbox.py``."""
from __future__ import annotations

import http.client
import json
import os
import re
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.slow
STUDENTS = 12


def _world(data: Path) -> tuple[int, list[str]]:
    """The dataset and the open exam, built in a new process on the real clock like the server's (the suite's clock is
    pinned, conftest.py)."""
    code = ("import json, sys; sys.path.insert(0, sys.argv[1]); import loadtest; from pathlib import Path; d = Path(sys.argv[2]); "
            "loadtest.build_dataset(d, 'demo'); print(json.dumps(loadtest.exam_setup(d, int(sys.argv[3]))[:2]))")
    env = {k: v for k, v in os.environ.items() if k not in ("ZEKA_MODE", "ZEKA_DATA")}
    run = subprocess.run([sys.executable, "-c", code, str(ROOT / "tools"), str(data), str(STUDENTS)], env=env,
                         capture_output=True, text=True, timeout=180)
    assert run.returncode == 0, run.stderr[-2000:]
    eid, cookies = json.loads(run.stdout.strip().splitlines()[-1])
    return eid, cookies


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(data: Path, port: int, workers: int = 1) -> subprocess.Popen:
    env = {**os.environ, "ZEKA_DATA": str(data), "PYTHONIOENCODING": "utf-8", "ZEKA_JOBS": "0", "ZEKA_TX_GUARD": "0"}
    env.pop("ZEKA_MODE", None)
    proc = subprocess.Popen([sys.executable, str(ROOT / "backend" / "run.py"), "--port", str(port), "--workers", str(workers)],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            if _call(port, "GET", "/healthz", "")[0] == 200:
                return proc
        except OSError:
            pass
        time.sleep(0.2)                                           # not started yet, or answering but not healthy (SF-F13)
    proc.kill()
    raise AssertionError("the server did not start: " + proc.communicate(timeout=10)[1].decode("utf-8", "replace")[-2000:])


def _call(port: int, method: str, path: str, cookie: str, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        conn.request(method, path, body=json.dumps(body if body is not None else {}),
                     headers={"Cookie": cookie, "Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json", "X-Lang": "az"})
        r = conn.getresponse()
        return r.status, r.getheader("Set-Cookie") or "", json.loads(r.read() or b"{}")
    finally:
        conn.close()


def _retry(port: int, method: str, path: str, cookie: str, body=None, seconds: float = 20):
    """As the exam page does: a request that finds no server is sent again (its answers stay queued)."""
    end = time.time() + seconds
    while True:
        try:
            return _call(port, method, path, cookie, body)
        except (OSError, http.client.HTTPException):
            if time.time() > end:
                raise
            time.sleep(0.1)


def _enter(port: int, eid: int, cookie: str) -> tuple[str, list[dict]]:
    status, back, _ = _call(port, "POST", f"/api/exams/{eid}/enter", cookie)
    m = re.search(r"zeka_sid=[^;]+", back)
    assert status == 200 and m
    status, _, view = _call(port, "POST", f"/api/exams/{eid}/start", m.group(0))
    assert status == 200
    return m.group(0), view["questions"]


def _db(data: Path, sql: str, args: tuple = ()) -> list[tuple]:
    db = sqlite3.connect(data / "campus.db")
    try:
        return db.execute(sql, args).fetchall()
    finally:
        db.close()


def _stored(data: Path, eid: int) -> dict[tuple[int, int], str]:
    return {(s, q): json.loads(v) for s, q, v in _db(data, "SELECT a.student_id, x.qid, x.value FROM exam_answers x "
                                               "JOIN exam_attempts a ON a.id=x.attempt_id WHERE a.exam_id=?", (eid,))}


def _answers(view: dict) -> dict[str, str]:
    return {k: json.loads(v) for k, v in view["attempt"]["answers"].items()}     # stored as JSON text, as sent


def _sessions(data: Path, port: int, eid: int, cookies: list[str]) -> dict[int, tuple[str, list[dict]]]:
    ids = [r[0] for r in _db(data, "SELECT student_id FROM exam_roster WHERE exam_id=? ORDER BY student_id", (eid,))]
    return {sid: _enter(port, eid, cookie) for sid, cookie in zip(ids, cookies, strict=True)}   # exam_setup's cookies follow the id order


def _answer_all(port, eid, sessions, acked, statuses, upto=None):
    """Every student saves its questions (value = the question's id, ``upto`` of them or all), one request each, in
    parallel; ``acked`` gets (student, qid) -> value for each 200, ``statuses`` every status."""
    def one(sid, cookie, qs):
        for q in qs[:upto]:
            status = _retry(port, "PUT", f"/api/exams/{eid}/answers/{q['id']}", cookie, {"value": str(q["id"])})[0]
            statuses.append(status)
            if status == 200:
                acked[(sid, q["id"])] = str(q["id"])
    ts = [threading.Thread(target=one, args=(sid, c, qs)) for sid, (c, qs) in sessions.items()]
    for t in ts:
        t.start()
    for t in ts:
        t.join()


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
    proc.communicate(timeout=30)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="--workers needs fork")
def test_a_worker_killed_during_the_exam_loses_no_acknowledged_answer(tmp_path):
    eid, cookies = _world(tmp_path)
    port = _free_port()
    proc = _serve(tmp_path, port, workers=2)
    try:
        sessions = _sessions(tmp_path, port, eid, cookies)
        acked: dict = {}
        statuses: list[int] = []

        total = sum(len(qs) for _, qs in sessions.values())
        killed_at: list[int] = []

        def kill_one():                                           # mid-exam: after the 20th answer, while the rest are sent
            while len(acked) < 20:
                time.sleep(0.005)
            os.kill(_call(port, "GET", "/healthz", "")[2]["worker"], signal.SIGKILL)
            killed_at.append(len(acked))
        killer = threading.Thread(target=kill_one)
        killer.start()
        _answer_all(port, eid, sessions, acked, statuses)
        killer.join()
        assert killed_at and killed_at[0] < total and len(acked) == total, (killed_at, len(acked), total)
        stored = _stored(tmp_path, eid)
        assert {k: stored.get(k) for k in acked} == acked, "every answer the server acknowledged is in the database"
        assert not [s for s in statuses if s >= 500]
        for sid, (cookie, qs) in sessions.items():               # every attempt goes on, with every stored answer
            status, _, view = _retry(port, "GET", f"/api/exams/{eid}", cookie)
            assert status == 200 and view["attempt"]["status"] == "in_progress"
            assert _answers(view) == {str(q["id"]): stored[(sid, q["id"])] for q in qs if (sid, q["id"]) in stored}
    finally:
        _stop(proc)


def test_the_whole_server_killed_and_started_again_keeps_every_attempt(tmp_path):
    eid, cookies = _world(tmp_path)
    port = _free_port()
    proc = _serve(tmp_path, port)
    try:
        sessions = _sessions(tmp_path, port, eid, cookies)
        acked: dict = {}
        statuses: list[int] = []
        _answer_all(port, eid, sessions, acked, statuses, upto=5)
        proc.kill()                                               # mid-exam, without a drain (SIGKILL; TerminateProcess on Windows)
        proc.communicate(timeout=10)
        proc = _serve(tmp_path, port)
        assert {k: _stored(tmp_path, eid).get(k) for k in acked} == acked
        for cookie, qs in sessions.values():
            status, _, view = _call(port, "POST", f"/api/exams/{eid}/start", cookie)   # starting again: the same attempt
            assert status == 200 and [q["id"] for q in view["questions"]] == [q["id"] for q in qs]
            assert _answers(view) == {str(q["id"]): str(q["id"]) for q in qs[:5]}
        _answer_all(port, eid, sessions, acked, statuses)          # the rest of the exam, then every student submits
        for cookie, _ in sessions.values():
            assert _call(port, "POST", f"/api/exams/{eid}/submit", cookie)[0] == 200
        assert len(_stored(tmp_path, eid)) == sum(len(qs) for _, qs in sessions.values())
        assert not [s for s in statuses if s >= 500]
    finally:
        _stop(proc)


def test_a_write_lock_held_two_seconds_gives_no_5xx_and_loses_nothing(tmp_path):
    eid, cookies = _world(tmp_path)
    port = _free_port()
    proc = _serve(tmp_path, port)
    try:
        sessions = _sessions(tmp_path, port, eid, cookies)
        holder = sqlite3.connect(tmp_path / "campus.db", isolation_level=None, check_same_thread=False)
        held = threading.Event()

        def hold():
            holder.execute("BEGIN IMMEDIATE")                     # a backup, a migration or a long import elsewhere
            held.set()
            time.sleep(2)
            holder.execute("COMMIT")
        t = threading.Thread(target=hold)
        t.start()
        held.wait(5)
        acked: dict = {}
        statuses: list[int] = []
        started = time.time()
        _answer_all(port, eid, sessions, acked, statuses)
        t.join()
        holder.close()
        assert time.time() - started >= 1.5, "the answers really waited on the lock"
        assert statuses and all(s == 200 for s in statuses), sorted(set(statuses))
        assert _stored(tmp_path, eid) == acked and len(acked) == sum(len(qs) for _, qs in sessions.values())
    finally:
        _stop(proc)
