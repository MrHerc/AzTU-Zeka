"""State shared by worker processes (tasks/todo.md, Task 7): one-time keys, rate limits, the search index.

A real server with two workers on a temporary data directory. A keep-alive connection stays with one worker, and
/healthz names the worker, so a test can make sure that two steps run in two different processes.
"""
import base64
import http.client
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.slow, pytest.mark.skipif(not hasattr(os, "fork"), reason="--workers needs fork")]


class Conn:
    def __init__(self, port, token=None):
        self.port, self.token = port, token
        self.http = http.client.HTTPConnection("127.0.0.1", port, timeout=30)

    def call(self, method, path, body=None):
        headers = {"Origin": f"http://127.0.0.1:{self.port}"}
        if self.token:
            headers["X-Session"] = self.token
        if body is not None:
            headers["Content-Type"] = "application/json"
        self.http.request(method, path, body=None if body is None else json.dumps(body), headers=headers)
        r = self.http.getresponse()
        raw = r.read()
        return r.status, (json.loads(raw) if raw and r.getheader("Content-Type", "").startswith("application/json") else raw)

    def worker(self):
        return self.call("GET", "/healthz")[1]["worker"]

    def close(self):
        self.http.close()


def on_worker(port, token=None, avoid=None):
    """A connection served by some worker other than ``avoid``."""
    for _ in range(200):
        c = Conn(port, token)
        pid = c.worker()
        if pid != avoid:
            return c, pid
        c.close()
    raise AssertionError("connections never reached a second worker")


def login(port, role):
    c = Conn(port)
    try:
        status, body = c.call("POST", "/api/auth/demo", {"role": role})
        assert status == 200, body
        return body["token"]
    finally:
        c.close()


@pytest.fixture(scope="module")
def port(tmp_path_factory):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
    env = {**os.environ, "ZEKA_DATA": str(tmp_path_factory.mktemp("workers")), "PYTHONIOENCODING": "utf-8"}
    for k in ("ZEKA_MODE", "ZEKA_TX_GUARD"):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, str(ROOT / "backend" / "run.py"), "--port", str(p), "--workers", "2"],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        seen, deadline = set(), time.time() + 90
        while len(seen) < 2 and time.time() < deadline:
            try:
                c = Conn(p)
                seen.add(c.worker())
                c.close()
            except OSError:
                time.sleep(0.2)
        assert len(seen) == 2
        yield p
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.communicate(timeout=30)


def test_a_key_issued_by_one_worker_is_accepted_once_by_another(port):
    token = login(port, "teacher")
    a, pid_a = on_worker(port, token)
    status, body = a.call("POST", "/api/syllabus/1/link", {})
    assert status == 200, body
    b, _ = on_worker(port, avoid=pid_a)                    # no session: only the key can let it in
    assert b.call("GET", body["url"])[0] == 200
    again, _ = on_worker(port)
    assert again.call("GET", body["url"])[0] == 401
    for c in (a, b, again):
        c.close()


def test_a_rate_limit_is_shared_by_the_workers(port):
    statuses, pids = [], set()
    for _ in range(70):                                      # 60 verification lookups per client per minute
        c, pid = on_worker(port)
        pids.add(pid)
        statuses.append(c.call("GET", "/verify/NOSUCHCODE")[0])
        c.close()
    assert len(pids) == 2 and statuses.count(429) == 10, (len(pids), statuses.count(429))


def test_a_material_uploaded_through_one_worker_is_found_through_the_other(port):
    token = login(port, "teacher")
    a, pid_a = on_worker(port, token)
    text = ("# Plazma generatorları\n\n## Əsas anlayışlar\n\nKsenonplazmatron — ksenon qazında plazma yaradan qurğudur. "
            "Ksenonplazmatron yüksək tezlikli sahə ilə işləyir və laboratoriya işlərində istifadə olunur.\n")
    status, body = a.call("POST", "/api/courses/1/materials", {"filename": "plazma.md", "title": "Plazma generatorları",
                                                               "content_b64": base64.b64encode(text.encode()).decode()})
    assert status == 200, body
    b, _ = on_worker(port, token, avoid=pid_a)
    status, found = b.call("GET", "/api/search?q=ksenonplazmatron")
    assert status == 200 and "Plazma generatorları" in json.dumps(found, ensure_ascii=False), found
    a.close()
    b.close()


def test_a_restarted_worker_applies_what_changed_since_the_supervisor_built_the_index(port):
    """A replacement is forked from the supervisor, whose index dates from start-up: it must apply the change log."""
    token = login(port, "teacher")
    a, pid_a = on_worker(port, token)
    b, pid_b = on_worker(port, avoid=pid_a)
    b.close()
    text = ("# Kriogen texnika\n\n## Nasoslar\n\nKriotermosifon maye azotla soyudulan dövrəli nasosdur. "
            "Kriotermosifon vakuum kameralarında istifadə olunur.\n")
    status, body = a.call("POST", "/api/courses/1/materials", {"filename": "krio.md", "title": "Kriogen texnika",
                                                               "content_b64": base64.b64encode(text.encode()).decode()})
    assert status == 200, body
    a.close()
    os.kill(pid_a, signal.SIGKILL)
    for _ in range(300):
        try:
            c = Conn(port, token)
            if c.worker() not in (pid_a, pid_b):
                break
            c.close()
        except OSError:
            pass
        time.sleep(0.02)
    else:
        raise AssertionError("no replacement worker answered")
    status, found = c.call("GET", "/api/search?q=kriotermosifon")
    c.close()
    assert status == 200 and "Kriogen texnika" in json.dumps(found, ensure_ascii=False), found
