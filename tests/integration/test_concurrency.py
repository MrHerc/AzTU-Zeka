"""Handler gate, slow routes and worker processes (tasks/todo.md, Task 6). Throughput itself: tools/loadtest.py."""
import http.client
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import loadtest
from zeka.core import web
from zeka.legacy import engine

ROOT = Path(__file__).resolve().parents[2]


def test_the_gate_does_not_leak_after_a_thousand_failing_requests(anon, student):
    for i in range(1000):                       # 401 raised inside the gate, in before()
        assert anon.get("/api/me").status == 401, i
    assert web.GATE._value == web.HANDLERS and web.SLOW._value == web.SLOW_HANDLERS
    assert student.get("/api/student/home").status == 200


def test_a_full_queue_answers_503_with_retry_after(student, monkeypatch):
    monkeypatch.setattr(web, "QUEUE_WAIT", 0.2)
    taken = [web.GATE.acquire(timeout=5) for _ in range(web.HANDLERS)]
    try:
        r = student.get("/api/student/home")
    finally:
        for _ in taken:
            web.GATE.release()
    assert r.status == 503 and r.headers.get("Retry-After") == "5"
    assert student.get("/api/student/home").status == 200


def test_slow_handlers_do_not_take_the_fast_slots(admin, student, monkeypatch):
    monkeypatch.setattr(engine, "llm_config", lambda: {"enabled": True, "provider": "openai", "model": "fake", "api_key": "x", "base_url": "https://x"})
    monkeypatch.setattr(engine, "llm_chat", lambda *a, **k: time.sleep(2) or "ok")
    with ThreadPoolExecutor(4) as slow:
        pending = [slow.submit(admin.post, "/api/admin/test-llm", {}) for _ in range(4)]
        time.sleep(0.3)                          # all four are inside the slow handler now
        assert web.SLOW._value == 0 and web.GATE._value == web.HANDLERS
        lat = []
        for _ in range(30):
            t = time.perf_counter()
            assert student.get("/api/student/home").status == 200
            lat.append(time.perf_counter() - t)
        assert all(not f.done() for f in pending)          # the fast requests finished while the slow ones were running
        assert sorted(lat)[int(0.95 * len(lat))] <= 0.5
        assert all(f.result().status == 200 for f in pending)


def _get(port, path="/healthz"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request("GET", path)
        r = conn.getresponse()
        return r.status, json.loads(r.read() or b"{}")
    finally:
        conn.close()


@pytest.mark.slow
@pytest.mark.skipif(not hasattr(os, "fork"), reason="--workers needs fork")
def test_workers_share_the_port_and_a_killed_worker_comes_back(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "ZEKA_DATA": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    env.pop("ZEKA_MODE", None)
    proc = subprocess.Popen([sys.executable, str(ROOT / "backend" / "run.py"), "--port", str(port), "--workers", "2"],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        pids, deadline = set(), time.time() + 90
        while len(pids) < 2 and time.time() < deadline:
            try:
                pids.add(_get(port)[1]["worker"])
            except OSError:
                time.sleep(0.2)
        assert len(pids) == 2, "two workers answer on one port"
        victim = min(pids)
        os.kill(victim, signal.SIGKILL)
        time.sleep(0.2)
        seen, t0 = set(), time.time()
        while time.time() - t0 < 10:
            status, body = _get(port)                        # the remaining worker answers every request meanwhile
            assert status == 200
            seen.add(body["worker"])
            if seen - pids:
                break
        assert seen - pids and victim not in seen, "a new worker replaced the killed one"
        assert time.time() - t0 < 3, "replaced within about two seconds on the demo database"
    finally:
        proc.send_signal(signal.SIGTERM)
        err = proc.communicate(timeout=30)[1].decode("utf-8", "replace")
    assert proc.returncode == 0, err[-500:]


@pytest.mark.slow
def test_the_load_tool_runs(capsys):
    assert loadtest.main(["--scenario", "mixed", "--users", "8", "--seconds", "2", "--dataset", "demo", "--clients", "2", "--fail-on-errors"]) == 0
    assert '"5xx": 0' in capsys.readouterr().out


def test_a_slow_request_body_never_holds_a_handler_slot(app_db, monkeypatch):
    monkeypatch.setattr(web, "QUEUE_WAIT", 1.0)
    token = re.search(r"zeka_sid=([^;]+)", app_db.client().post("/api/auth/demo", {"role": "student"}).headers["Set-Cookie"]).group(1)
    stalled = []
    for _ in range(web.HANDLERS + 1):           # more half-sent uploads than there are slots
        s = socket.create_connection(("127.0.0.1", app_db.port))
        s.sendall(b"PUT /api/me/prefs HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
                  b"Cookie: zeka_sid=" + token.encode() + b"\r\nContent-Length: 50\r\n\r\n{")
        stalled.append(s)
    try:
        time.sleep(0.3)
        assert web.GATE._value == web.HANDLERS
        t = time.perf_counter()
        assert app_db.client("student").get("/api/student/home").status == 200
        assert time.perf_counter() - t < 0.9
    finally:
        for s in stalled:
            s.close()


def test_drain_waits_until_every_started_answer_is_written(app_db):
    from zeka.legacy import api

    started = threading.Event()

    def slow(req):
        started.set()
        time.sleep(0.5)
        return {"ok": True}

    slow.demo_only, slow.slow = False, False
    api.R.add("GET", "/api/test-drain", slow, None, False)
    try:
        with ThreadPoolExecutor(1) as pool:
            fut = pool.submit(app_db.client().get, "/api/test-drain")
            assert started.wait(5)
            t = time.perf_counter()
            assert web.drain(timeout=5)
            assert time.perf_counter() - t >= 0.3
            assert fut.result(timeout=5).status == 200
    finally:
        web._STOPPING[0] = False
        api.R.routes.pop()


def test_the_pdf_preview_runs_under_the_slow_slots():
    from zeka.legacy import api
    assert api.R.match("GET", "/api/files/1/preview")[0].slow


def test_tutor_answers_waiting_on_the_llm_leave_reads_and_writes_fast(teacher, student, monkeypatch):
    from zeka.legacy import r_learning, tutor
    from zeka.modules.identity import privacy
    cid = teacher.get("/api/courses").json[0]["id"]
    monkeypatch.setattr(engine, "llm_config", lambda: {"enabled": True, "provider": "openai", "model": "fake", "api_key": "x", "base_url": "https://x"})
    # Task 40: the external AI needs a consent to the version the page showed (Checkpoint F, SF-F9)
    assert teacher.post("/api/consent", {"ai": True, "external": True, "versions": {"external_ai": privacy.version("external_ai")}}).status == 200
    monkeypatch.setattr(r_learning, "search_chunks", lambda course_id, q: [{"score": 5.0}])
    monkeypatch.setattr(tutor, "llm_tutor", lambda *a, **k: time.sleep(1.5) or {"text": "ok", "cites": [], "meta": {"mode": "explain"}})
    with ThreadPoolExecutor(4) as pool:
        pending = [pool.submit(teacher.post, f"/api/tutor/{cid}/ask", {"message": "Om qanunu nədir?"}) for _ in range(4)]
        time.sleep(0.3)
        assert web.SLOW._value == 0 and web.GATE._value == web.HANDLERS
        lat = []
        for i in range(15):
            t = time.perf_counter()
            assert student.put("/api/me/prefs", {"theme": "dark" if i % 2 else "light"}).status == 200
            assert student.get("/api/student/home").status == 200
            lat.append(time.perf_counter() - t)
        assert all(not f.done() for f in pending)
        assert sorted(lat)[int(0.95 * len(lat))] <= 0.5
        assert all(f.result().status == 200 for f in pending)


@pytest.mark.slow
@pytest.mark.skipif(not hasattr(os, "fork"), reason="--workers needs fork")
def test_the_supervisor_gives_up_when_workers_cannot_start():
    code = ("import sys, types\nsys.path.insert(0, 'backend')\nimport run\n"
            "def boom(args, log):\n    raise RuntimeError('cannot bind the port')\n"
            "run.worker = boom\nrun.supervise(types.SimpleNamespace(workers=1), lambda m: None)\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("ZEKA_")}
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env={**env, "PYTHONIOENCODING": "utf-8"},
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 1 and "cannot bind the port" in r.stderr and "başlaya bilmir" in r.stderr, r.stderr[-600:]
