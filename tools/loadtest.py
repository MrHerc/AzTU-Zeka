"""Load test against a real server process on a throw-away data directory (tasks/todo.md, Task 6).

    python tools/loadtest.py --scenario read --users 300 --seconds 30 --dataset demo [--workers 1] [--fail-on-errors]

The repository's data/ folder is never touched: the dataset is built in a temporary ZEKA_DATA directory, the server is
started from backend/run.py on a free port and stopped at the end.

Scenarios: closed loop, no think time, one keep-alive connection per virtual user, 25 shared student sessions.
    read    GET /api/student/home 60 %, GET /api/schedule 20 %, GET /api/courses 20 %
    write   PUT /api/me/prefs 70 %, POST /api/news/{id}/save 30 %
    mixed   the read mix 80 %, the write mix 20 %

Datasets (added on top of the demo seed):
    demo        nothing: 147 users, 6 courses
    faculty     2 000 students, 12 000 enrolments, 1 200 timetable rows, 20 000 quiz attempts, 20 000 material chunks
    university  10 000 students, 60 000 enrolments, 6 000 timetable rows, 100 000 quiz attempts, 100 000 material chunks

Output: requests, requests/s, p50/p95/p99 latency, 5xx, 4xx, connection errors.
"""
from __future__ import annotations

import argparse
import http.client
import json
import multiprocessing
import os
import random
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIZES = {"demo": None, "faculty": (2000, 200, 20000, 20000), "university": (10000, 1000, 100000, 100000)}
READ = [(60, "GET", "/api/student/home"), (20, "GET", "/api/schedule"), (20, "GET", "/api/courses")]
WRITE = [(70, "PUT", "/api/me/prefs"), (30, "POST", "/api/news/{news}/save")]
MIX = {"read": READ, "write": WRITE, "mixed": [(w * 0.8, m, p) for w, m, p in READ] + [(w * 0.2, m, p) for w, m, p in WRITE]}
SESSIONS = 25          # the demo login allows 30 per client per minute


def build_dataset(data: Path, name: str) -> None:
    os.environ["ZEKA_DATA"] = str(data)
    os.environ.pop("ZEKA_MODE", None)
    sys.path.insert(0, str(ROOT / "backend"))
    from zeka.legacy import store
    store.init(reset=True)
    if SIZES[name] is None:
        return
    students, courses, attempts, chunks = SIZES[name]
    rng = random.Random(7)
    c = store.connect()
    try:
        now = store.iso(store.now())
        groups = [r["id"] for r in store.rows(c, "SELECT id FROM study_groups")]
        base_courses = [r["id"] for r in store.rows(c, "SELECT id FROM courses")]
        c.executemany("INSERT INTO users(username,full_name,role,title,group_id,color,synthetic,student_no,admission_year,consent_at) "
                      "VALUES(?,?,'student','',?,'#5a9bd3',1,?,2025,?)",
                      [(f"lt_s{i}", f"Test Tələbə {i}", groups[i % len(groups)], f"LT{i:06d}", now) for i in range(students)])
        sids = [r["id"] for r in store.rows(c, "SELECT id FROM users WHERE username LIKE 'lt_s%'")]
        c.executemany("INSERT INTO enrollments(user_id,course_id) VALUES(?,?)", [(s, k) for s in sids for k in base_courses])
        for i in range(courses):
            cid = c.execute("INSERT INTO courses(code,name,teacher_id,credits,color,description,suggestions,tutor_modes,tutor_rules,tutor_locked) "
                            "SELECT ?, ?, teacher_id, credits, color, description, suggestions, tutor_modes, tutor_rules, tutor_locked "
                            "FROM courses WHERE id=?", (f"LT-{i:04d}", f"Yük testi fənni {i}", base_courses[i % len(base_courses)])).lastrowid
            c.executemany("INSERT INTO timetable(course_id,weekday,start,end,kind,room) VALUES(?,?,?,?,?,?)",
                          [(cid, 1 + k % 5, ("09:00", "10:30", "12:00")[k % 3], ("10:20", "11:50", "13:20")[k % 3], "Mühazirə", f"LT {k}")
                           for k in range(6)])
        quizzes = [r["id"] for r in store.rows(c, "SELECT id FROM quizzes")]
        c.executemany("INSERT INTO attempts(quiz_id,user_id,answers,details,score,max_score,started_at,finished_at,synthetic) "
                      "VALUES(?,?,'{}','[]',?,10,?,?,1)",
                      [(rng.choice(quizzes), rng.choice(sids), rng.randint(0, 10), now, now) for _ in range(attempts)])
        words = " ".join(r["text"] for r in store.rows(c, "SELECT text FROM chunks")).split()
        extra = [r["id"] for r in store.rows(c, "SELECT id FROM courses WHERE code LIKE 'LT-%'")]
        per_course = max(1, chunks // len(extra))
        for cid in extra:
            mid = c.execute("INSERT INTO materials(course_id,title,filename,text,chunk_count,term_count,uploaded_by,created_at) "
                            "VALUES(?,?,?,?,?,0,NULL,?)", (cid, "Yük testi materialı", "lt.md", "", per_course, now)).lastrowid
            c.executemany("INSERT INTO chunks(material_id,course_id,seq,heading,text) VALUES(?,?,?,?,?)",
                          [(mid, cid, k, f"Bölmə {k}", " ".join(rng.choices(words, k=120))) for k in range(per_course)])
        c.commit()
    finally:
        c.close()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(conn, method, path, body, headers):
    conn.request(method, path, body=body, headers=headers)
    r = conn.getresponse()
    r.read()
    return r.status


def start_server(data: Path, port: int, workers: int) -> subprocess.Popen:
    env = {**os.environ, "ZEKA_DATA": str(data), "PYTHONIOENCODING": "utf-8"}
    env.pop("ZEKA_MODE", None)
    proc = subprocess.Popen([sys.executable, str(ROOT / "backend" / "run.py"), "--port", str(port), "--workers", str(workers)],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    deadline = time.time() + 300
    while time.time() < deadline:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            if call(conn, "GET", "/healthz", None, {}) == 200:
                return proc
        except OSError:
            if proc.poll() is not None:
                raise SystemExit(f"server exited: {proc.communicate()[1].decode('utf-8', 'replace')[-800:]}") from None
        finally:
            conn.close()
        time.sleep(0.3)
    proc.kill()
    raise SystemExit("server did not answer /healthz within 300 s")


def sessions(port: int, data: Path) -> tuple[list[str], list[int]]:
    import sqlite3
    db = sqlite3.connect(data / "campus.db")
    try:
        users = [r[0] for r in db.execute("SELECT username FROM users WHERE role='student' ORDER BY id LIMIT ?", (SESSIONS,))]
        news = [r[0] for r in db.execute("SELECT id FROM news WHERE status='published' ORDER BY id")]
    finally:
        db.close()
    tokens = []
    for u in users:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        conn.request("POST", "/api/auth/demo", body=json.dumps({"role": "student", "user": u}),
                     headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"})
        r = conn.getresponse()
        tokens.append(json.loads(r.read())["token"])
        conn.close()
    return tokens, news


def client(args) -> list[tuple[float, int]]:
    port, threads, seconds, scenario, tokens, news, seed = args
    import threading
    out: list[tuple[float, int]] = []
    lock = threading.Lock()
    stop_at = time.time() + seconds
    mix = MIX[scenario]

    def user(n):
        rng = random.Random(seed * 1000 + n)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        base = {"X-Session": tokens[n % len(tokens)], "X-Lang": "az", "Origin": f"http://127.0.0.1:{port}"}
        mine = []
        while time.time() < stop_at:
            _, method, path = rng.choices(mix, weights=[w for w, _, _ in mix])[0]
            body, headers = None, dict(base)
            if method != "GET":
                body = json.dumps({"theme": rng.choice(["light", "dark"])} if path.endswith("prefs") else {})
                headers["Content-Type"] = "application/json"
            t = time.perf_counter()
            try:
                status = call(conn, method, path.format(news=rng.choice(news)), body, headers)
            except (OSError, http.client.HTTPException):
                status = 0
                conn.close()
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
            mine.append((time.perf_counter() - t, status))
        conn.close()
        with lock:
            out.extend(mine)

    ts = [threading.Thread(target=user, args=(n,)) for n in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return out


def report(results, seconds) -> dict:
    lat = sorted(r[0] for r in results)
    n = len(lat)

    def pct(q):
        return round(1000 * lat[min(n - 1, int(q * n))]) if n else None

    return {"requests": n, "rps": round(n / seconds), "p50_ms": pct(0.5), "p95_ms": pct(0.95), "p99_ms": pct(0.99),
            "5xx": sum(1 for r in results if r[1] >= 500), "4xx": sum(1 for r in results if 400 <= r[1] < 500),
            "conn_errors": sum(1 for r in results if r[1] == 0)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--scenario", choices=sorted(MIX), default="read")
    ap.add_argument("--users", type=int, default=300)
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--dataset", choices=sorted(SIZES), default="demo")
    ap.add_argument("--workers", type=int, default=1, help="server processes (backend/run.py --workers)")
    ap.add_argument("--clients", type=int, default=min(4, os.cpu_count() or 1), help="load generator processes")
    ap.add_argument("--fail-on-errors", action="store_true", help="exit 1 on any 5xx or connection error")
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="zeka-load-") as tmp:
        data = Path(tmp)
        t = time.time()
        build_dataset(data, args.dataset)
        print(f"dataset {args.dataset}: built in {time.time() - t:.1f} s", flush=True)
        port = free_port()
        t = time.time()
        proc = start_server(data, port, args.workers)
        print(f"server: {args.workers} worker(s), ready in {time.time() - t:.1f} s", flush=True)
        try:
            tokens, news = sessions(port, data)
            k = max(1, min(args.clients, args.users))
            jobs = [(port, args.users // k + (1 if i < args.users % k else 0), args.seconds, args.scenario, tokens, news, i) for i in range(k)]
            with multiprocessing.get_context("spawn").Pool(k) as pool:
                results = [r for part in pool.map(client, jobs) for r in part]
        finally:
            proc.terminate()
            try:
                proc.communicate(timeout=30)          # also closes the stderr pipe
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
    rep = report(results, args.seconds)
    print(json.dumps({"scenario": args.scenario, "dataset": args.dataset, "users": args.users, "workers": args.workers, **rep}))
    return 1 if args.fail_on_errors and (rep["5xx"] or rep["conn_errors"]) else 0


if __name__ == "__main__":
    sys.exit(main())
