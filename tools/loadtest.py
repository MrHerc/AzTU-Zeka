"""Load test against a real server process on a throw-away data directory (tasks/todo.md, Task 6).

    python tools/loadtest.py --scenario read --users 300 --seconds 30 --dataset demo [--workers 1] [--fail-on-errors]

The repository's data/ folder is never touched: the dataset is built in a temporary ZEKA_DATA directory, the server is
started from backend/run.py on a free port and stopped at the end.

Scenarios: closed loop, no think time, one keep-alive connection per virtual user, 25 shared student sessions.
    read    GET /api/student/home 60 %, GET /api/schedule 20 %, GET /api/courses 20 %
    write   PUT /api/me/prefs 70 %, POST /api/news/{id}/save 30 %
    mixed   the read mix 80 %, the write mix 20 %
    exam    Task 27: one exam, one distinct student per virtual user: enter, start, every answer, submit (one pass each),
            spread over --seconds like a sitting (entries in its first tenth, answers through it, the submission at its
            end); --burst sends everything at once with no pause, the worst case. The report adds the answers the
            clients saw saved and the ones the server holds ("lost": the difference)

Datasets (added on top of the demo seed):
    demo        nothing: 147 users, 6 courses
    faculty     2 000 students, 12 000 enrolments, 1 200 timetable rows, 20 000 quiz attempts, 20 000 material chunks
    university  10 000 students, 60 000 enrolments, 6 000 timetable rows, 100 000 quiz attempts, 100 000 material chunks

Output: requests, requests/s, p50/p95/p99 latency, 5xx, 4xx, connection errors; read/write/mixed add the requests sent
again on a new connection after the server closed an idle keep-alive one ("reopened", what a browser does) and every
non-2xx answer by route ("errors_by_route").
"""
from __future__ import annotations

import argparse
import http.client
import json
import multiprocessing
import os
import random
import re
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
MIX = {"read": READ, "write": WRITE, "mixed": [(w * 0.8, m, p) for w, m, p in READ] + [(w * 0.2, m, p) for w, m, p in WRITE], "exam": []}
EXAM_QUESTIONS = 10    # per form, drawn from 30 exam questions
SESSIONS = 25          # the demo login allows 30 per client per minute


def build_dataset(data: Path, name: str) -> None:
    """Runs in its own process (see main): ZEKA_DATA is read when store is imported and must not leak to the caller."""
    os.environ["ZEKA_DATA"] = str(data)
    os.environ.pop("ZEKA_MODE", None)
    sys.path.insert(0, str(ROOT / "backend"))
    from zeka.legacy import store
    store.init(reset=True)
    size = SIZES[name]
    if size is None:
        return
    students, courses, attempts, chunks = size
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
        # Task 42: only news a student may open; a teachers-only item answered 404, the script's own error
        news = [r[0] for r in db.execute("SELECT id FROM news WHERE status='published' AND audience IN ('all','students') ORDER BY id")]
    finally:
        db.close()
    tokens = []
    for u in users:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        conn.request("POST", "/api/auth/demo", body=json.dumps({"role": "student", "user": u}),
                     headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"})
        r = conn.getresponse()
        r.read()
        m = re.search(r"zeka_sid=[^;]+", r.getheader("Set-Cookie") or "")   # the session is only in the cookie
        if not m:
            raise SystemExit(f"demo login for {u} returned no session cookie (HTTP {r.status})")
        tokens.append(m.group(0))
        conn.close()
    return tokens, news


def client(args) -> list[tuple[float, int, str, bool]]:
    """(latency, status, "METHOD path", reopened) per request; status 0 is a connection error."""
    port, threads, seconds, scenario, tokens, news, seed, think = args
    import threading
    out: list[tuple[float, int, str, bool]] = []
    lock = threading.Lock()
    stop_at = time.time() + seconds
    mix = MIX[scenario]

    def user(n):
        rng = random.Random(seed * 1000 + n)
        conn, used = http.client.HTTPConnection("127.0.0.1", port, timeout=60), False
        base = {"Cookie": tokens[n % len(tokens)], "X-Lang": "az", "Origin": f"http://127.0.0.1:{port}"}
        mine = []
        while time.time() < stop_at:
            _, method, path = rng.choices(mix, weights=[w for w, _, _ in mix])[0]
            body, headers = None, dict(base)
            if method != "GET":
                body = json.dumps({"theme": rng.choice(["light", "dark"])} if path.endswith("prefs") else {})
                headers["Content-Type"] = "application/json"
            url = path.format(news=rng.choice(news))
            t = time.perf_counter()
            status, reopened = 0, False
            # Task 42: the server closes a keep-alive connection idle for 30 s (a user thinking longer); like a browser,
            # a request that fails on a reused connection is sent once more on a new one. A new one that fails is an error.
            for again in (used, False):
                try:
                    status, used = call(conn, method, url, body, headers), True
                    break
                except (OSError, http.client.HTTPException):
                    conn.close()
                    conn, used = http.client.HTTPConnection("127.0.0.1", port, timeout=60), False
                    reopened = again
                    if not again:
                        break
            mine.append((time.perf_counter() - t, status, f"{method} {path}", reopened))
            if think:                                  # a person reads the page before the next click (exponential pause)
                time.sleep(min(rng.expovariate(1 / think), stop_at - time.time()) if stop_at > time.time() else 0)
        conn.close()
        with lock:
            out.extend(mine)

    ts = [threading.Thread(target=user, args=(n,)) for n in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return out


def exam_setup(data: Path, users: int) -> tuple[int, list[str], str]:
    """An open exam of a new course with ``users`` enrolled students, each with a session written straight into the
    throw-away database (the demo login allows 30 per client per minute)."""
    import sqlite3
    from datetime import timedelta
    sys.path.insert(0, str(ROOT / "backend"))
    from zeka.core import clock
    from zeka.modules.identity import domain as identity
    db = sqlite3.connect(data / "campus.db")
    try:
        students = [r[0] for r in db.execute("SELECT id FROM users WHERE role='student' AND status='active' ORDER BY id LIMIT ?", (users,))]
        if len(students) < users:
            raise SystemExit(f"the dataset has {len(students)} students; --users {users} needs as many")
        cid = db.execute("INSERT INTO courses(code,name,teacher_id,credits) VALUES('LT-EXAM','Yük imtahanı',"
                         "(SELECT id FROM users WHERE role='teacher' ORDER BY id LIMIT 1),5)").lastrowid
        db.executemany("INSERT OR IGNORE INTO enrollments(user_id,course_id) VALUES(?,?)", [(s, cid) for s in students])
        for i in range(30):
            db.execute("INSERT INTO questions(course_id,qtype,text,options,answer,unit,explanation,difficulty,topic,status,purpose,created_at) "
                       "VALUES(?,'numeric',?,'[]',?,'','','Asan','Yük','approved','exam','x')", (cid, f"Yük sualı {i}", str(i)))
        t = clock.now()
        eid = db.execute("INSERT INTO exams(course_id,kind,title,opens_at,closes_at,duration_min,plan,status,secret,created_at,opened_at) "
                         "VALUES(?,'main','Yük imtahanı',?,?,120,?,'open','load',?,?)",
                         (cid, (t - timedelta(hours=1)).isoformat(timespec="seconds"), (t + timedelta(hours=3)).isoformat(timespec="seconds"),
                          json.dumps([{"difficulty": None, "topic": None, "count": EXAM_QUESTIONS}]), t.isoformat(timespec="seconds"),
                          t.isoformat(timespec="seconds"))).lastrowid
        assert eid is not None
        local = clock.local().isoformat(timespec="seconds")
        db.executemany("INSERT INTO exam_roster(exam_id,student_id,status,added_at) VALUES(?,?,'eligible',?)", [(eid, s, local) for s in students])
        teacher = db.execute("SELECT teacher_id FROM courses WHERE id=?", (cid,)).fetchone()[0]
        tsid = identity.new_session_id()                          # the course's teacher watches the board (Task 29)
        db.execute("INSERT INTO sessions(id_hash,user_id,created_at,last_seen,scope,role) VALUES(?,?,?,?,'full','teacher')",
                   (identity.session_hash(tsid), teacher, local, local))
        cookies = []
        for s in students:
            sid = identity.new_session_id()
            db.execute("INSERT INTO sessions(id_hash,user_id,created_at,last_seen,scope,role) VALUES(?,?,?,?,'full','student')",
                       (identity.session_hash(sid), s, local, local))
            cookies.append(f"zeka_sid={sid}")
        db.commit()
    finally:
        db.close()
    return eid, cookies, f"zeka_sid={tsid}"


def board_poll(port: int, eid: int, cookie: str, stop, out: list):
    """A proctor's board (Task 29): one request every 5 seconds with the last event seen, until ``stop`` is set."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    headers = {"Cookie": cookie, "X-Lang": "az"}
    seq = 0
    while not stop.is_set():
        t = time.perf_counter()
        try:
            conn.request("GET", f"/api/exams/{eid}/board?after={seq}", headers=headers)
            r = conn.getresponse()
            raw = r.read()
            out.append((time.perf_counter() - t, r.status))
            if r.status == 200:
                seq = json.loads(raw)["seq"]
        except (OSError, http.client.HTTPException):
            out.append((time.perf_counter() - t, 0))
            conn.close()
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        stop.wait(5)
    conn.close()


def exam_client(args) -> tuple[list[tuple[float, int]], int]:
    """One process of exam users: each enters, starts, answers every question and submits, once; spread over
    ``seconds`` unless ``burst``."""
    port, eid, cookies, seconds, burst, seed, ramp = args
    import threading
    out: list[tuple[float, int]] = []
    saved = [0]
    lock = threading.Lock()

    def user(n, cookie):
        rng = random.Random(seed * 1000 + n)
        pause = (lambda s: None) if burst else time.sleep
        pause(rng.uniform(0, seconds * 0.1 if ramp is None else ramp))   # the students come in (first tenth, or --ramp)
        conn = [http.client.HTTPConnection("127.0.0.1", port, timeout=60)]
        headers = {"Cookie": cookie, "X-Lang": "az", "Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json"}
        mine, ok = [], 0

        def go(method, path, body=None):
            t = time.perf_counter()
            for again in (True, False):   # the server closes a connection idle for 30 s; a browser opens a new one
                try:
                    conn[0].request(method, path, body=json.dumps(body if body is not None else {}), headers=headers)
                    r = conn[0].getresponse()
                    raw = r.read()
                    mine.append((time.perf_counter() - t, r.status))
                    return r.status, r.getheader("Set-Cookie") or "", raw
                except (OSError, http.client.HTTPException):
                    conn[0].close()
                    conn[0] = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
                    if not again:
                        mine.append((time.perf_counter() - t, 0))
            return 0, "", b""
        status, cookie_back, _ = go("POST", f"/api/exams/{eid}/enter")
        m = re.search(r"zeka_sid=[^;]+", cookie_back)
        if status == 200 and m:
            headers["Cookie"] = m.group(0)
            status, _, raw = go("POST", f"/api/exams/{eid}/start")
            if status == 200:
                qs = json.loads(raw)["questions"]
                step = seconds * 0.8 / max(1, len(qs))
                for q in qs:
                    pause(rng.uniform(0.5, 1.5) * step)                # thinking over a question
                    if go("PUT", f"/api/exams/{eid}/answers/{q['id']}", {"value": str(q["id"])})[0] == 200:
                        ok += 1
                go("POST", f"/api/exams/{eid}/submit")
        conn[0].close()
        with lock:
            out.extend(mine)
            saved[0] += ok

    ts = [threading.Thread(target=user, args=(n, c)) for n, c in enumerate(cookies)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return out, saved[0]


def _memory_gb() -> float | None:
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            return round(int(f.readline().split()[1]) / 1024 / 1024, 1)
    except (OSError, ValueError, IndexError):
        return None


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
    ap.add_argument("--fail-on-errors", action="store_true",
                    help="exit 1 on any 5xx or connection error, and on any 4xx in read/write/mixed (the script sends none it expects)")
    ap.add_argument("--burst", action="store_true", help="exam: no pauses, every student at once (the worst case)")
    ap.add_argument("--proctors", type=int, default=3, help="exam: boards polled every 5 s during the sitting (Task 29)")
    ap.add_argument("--ramp", type=float, help="exam: every student enters within this many seconds (default: the first tenth)")
    ap.add_argument("--think", type=float, default=0, help="read/write/mixed: mean seconds a user waits between requests (0: none)")
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="zeka-load-") as tmp:
        data = Path(tmp)
        t = time.time()
        builder = multiprocessing.get_context("spawn").Process(target=build_dataset, args=(data, args.dataset))
        builder.start()
        builder.join()
        if builder.exitcode != 0:
            raise SystemExit(f"building the {args.dataset} dataset failed (exit {builder.exitcode})")
        print(f"dataset {args.dataset}: built in {time.time() - t:.1f} s", flush=True)
        eid, cookies, proctor = exam_setup(data, args.users) if args.scenario == "exam" else (0, [], "")
        port = free_port()
        t = time.time()
        proc = start_server(data, port, args.workers)
        print(f"server: {args.workers} worker(s), ready in {time.time() - t:.1f} s", flush=True)
        extra: dict = {}
        try:
            if args.scenario == "exam":
                k = max(1, min(args.clients, args.users))
                import threading
                stop = threading.Event()
                boards: list[list[tuple[float, int]]] = [[] for _ in range(args.proctors)]
                watchers = [threading.Thread(target=board_poll, args=(port, eid, proctor, stop, boards[i])) for i in range(args.proctors)]
                for w in watchers:
                    w.start()
                started = time.time()
                try:
                    with multiprocessing.get_context("spawn").Pool(k) as pool:
                        parts = pool.map(exam_client, [(port, eid, cookies[i::k], args.seconds, args.burst, i, args.ramp) for i in range(k)])
                finally:
                    stop.set()
                    for w in watchers:
                        w.join()
                args.seconds = max(time.time() - started, 0.001)
                results = [r for part, _ in parts for r in part]
                import sqlite3
                db = sqlite3.connect(data / "campus.db")
                try:
                    held = db.execute("SELECT COUNT(*) FROM exam_answers a JOIN exam_attempts t ON t.id=a.attempt_id WHERE t.exam_id=?", (eid,)).fetchone()[0]
                finally:
                    db.close()
                verify = subprocess.run([sys.executable, str(ROOT / "backend" / "manage.py"), "exam-verify", str(eid)],
                                        env={**os.environ, "ZEKA_DATA": str(data), "PYTHONIOENCODING": "utf-8"},
                                        capture_output=True, text=True, timeout=600)
                client_saved = sum(n for _, n in parts)
                polls = sorted(t for b in boards for t, _ in b)
                extra = {"answers_saved_client": client_saved, "answers_on_server": held, "lost": client_saved - held,
                         "expected": args.users * EXAM_QUESTIONS, "board_polls": len(polls),
                         "board_errors": sum(1 for b in boards for _, st in b if st != 200),
                         "board_p95_ms": round(1000 * polls[min(len(polls) - 1, int(0.95 * len(polls)))]) if polls else None,
                         "exam_verify": verify.returncode, "exam_verify_out": verify.stdout.strip().splitlines()[-1:] or verify.stderr[-300:]}
            else:
                tokens, news = sessions(port, data)
                k = max(1, min(args.clients, args.users))
                jobs = [(port, args.users // k + (1 if i < args.users % k else 0), args.seconds, args.scenario, tokens, news, i, args.think)
                        for i in range(k)]
                with multiprocessing.get_context("spawn").Pool(k) as pool:
                    sent = [r for part in pool.map(client, jobs) for r in part]
                results = [(lat, status) for lat, status, _, _ in sent]
                failed: dict[str, dict[str, int]] = {}
                for _, status, route, _ in sent:
                    if not 200 <= status < 300:
                        failed.setdefault(route, {}).setdefault(str(status), 0)
                        failed[route][str(status)] += 1
                extra = {"reopened": sum(1 for r in sent if r[3]), "errors_by_route": failed}
        finally:
            proc.terminate()
            try:
                proc.communicate(timeout=30)          # also closes the stderr pipe
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
    rep = report(results, args.seconds)
    machine = {"cores": os.cpu_count(), "memory_gb": _memory_gb(), "python": sys.version.split()[0]}
    print(json.dumps({"scenario": args.scenario, "dataset": args.dataset, "users": args.users, "workers": args.workers,
                      "think_s": args.think, "ramp_s": args.ramp, **machine, **rep, **extra}))
    bad = rep["5xx"] or rep["conn_errors"] or (rep["4xx"] and args.scenario != "exam") or extra.get("lost") or extra.get("exam_verify")
    return 1 if args.fail_on_errors and bad else 0


if __name__ == "__main__":
    sys.exit(main())
