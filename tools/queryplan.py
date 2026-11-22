"""Query plans of the load-test routes on a large dataset (tasks/todo.md, Tasks 7 and 42).

    python tools/queryplan.py [--dataset university] [--min-rows 1000]

Builds the dataset in a throw-away ZEKA_DATA directory with an open exam (tools/loadtest.py exam_setup) and a released one
that 1 200 students sat (``bulk_exam``: every exam table above --min-rows), serves the API in this process and sends, once
each: every route of the mixed scenario (READ and WRITE) as a student; the exam scenario as a student (enter, start, every
answer, view, submit) and the proctor board as the course's teacher; as a leader, the leadership dashboard (its one
request, /api/analytics: its Radar line and card are the periodic job's summary), the accreditation evidence (Task 39) and
the Radar page (/api/radar, the live campus-wide analysis); and as the academic office, the timetable builder's read
routes and one move (Task 48) over a term whose builder tables all hold more than --min-rows rows (``bulk_timetable``). Records each SQL statement the handlers run and prints, as
JSON, every statement whose EXPLAIN QUERY PLAN scans a table that has more than --min-rows rows, by scenario, and the
slowest routes. Exit 1 when a read, mixed or exam route scans one; the leader's routes are reported, not failed: the
dashboard counts every course's rows and the Radar page reads every student's records by design (docs/perf/task42.md).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path

import loadtest

ROOT = Path(__file__).resolve().parents[1]
WRITES = re.compile(r"\s*(SELECT|WITH|UPDATE|DELETE)\b", re.I)
ALIAS = re.compile(r"\b(?:FROM|JOIN)\s+(\w+)(?:\s+(?:AS\s+)?(?!ON\b|WHERE\b|JOIN\b|LEFT\b|ORDER\b|GROUP\b|LIMIT\b)(\w+))?", re.I)


def scans(db: sqlite3.Connection, sql: str, sizes: dict[str, int], min_rows: int) -> list[str]:
    """The plan lines of ``sql`` that walk a whole table (or a whole index of it) with more than ``min_rows`` rows."""
    alias = {(a or t).lower(): t.lower() for t, a in ALIAS.findall(sql)}
    out = []
    for *_, detail in db.execute("EXPLAIN QUERY PLAN " + sql):
        m = re.match(r"SCAN (\w+)", detail)
        if m and sizes.get(alias.get(m.group(1).lower(), m.group(1).lower()), 0) > min_rows:
            out.append(detail)
    return out


def _send(port: int, method: str, path: str, cookie: str, body=None) -> tuple[int, str, bytes]:
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    try:
        conn.request(method, path, body=None if body is None else json.dumps(body),
                     headers={"Cookie": cookie, "Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json", "X-Lang": "az"})
        r = conn.getresponse()
        return r.status, r.getheader("Set-Cookie") or "", r.read()
    finally:
        conn.close()


def _sid(set_cookie: str, step: str) -> str:
    m = re.search(r"zeka_sid=[^;]+", set_cookie)
    if not m:
        raise SystemExit(f"{step}: no session cookie")
    return m.group(0)


def _routes(student: str, news: list[int], exam: tuple[int, list[str], str], tt: dict):
    """(scenario, method, path, cookie, body) in order. The caller sends each step and passes its answer back with
    ``send((set_cookie, body))``: the exam's steps need the session and the questions of the earlier ones. Every request
    is a step, so each one is timed and its statements carry its scenario (Checkpoint F, PY-F5)."""
    for _, method, path in loadtest.READ + loadtest.WRITE:
        yield "mixed", method, path.format(news=news[0]), student, None if method == "GET" else ({"theme": "dark"} if path.endswith("prefs") else {})
    eid, cookies, proctor = exam
    back, _ = yield "exam", "POST", f"/api/exams/{eid}/enter", cookies[0], {}
    sitting = _sid(back, "exam: enter")
    _, raw = yield "exam", "POST", f"/api/exams/{eid}/start", sitting, {}
    for q in json.loads(raw)["questions"]:
        yield "exam", "PUT", f"/api/exams/{eid}/answers/{q['id']}", sitting, {"value": str(q["id"])}
    yield "exam", "GET", f"/api/exams/{eid}", sitting, None
    yield "exam", "GET", f"/api/exams/{eid}/board?after=0", proctor, None
    yield "exam", "POST", f"/api/exams/{eid}/submit", sitting, {}
    back, _ = yield "leader", "POST", "/api/auth/demo", "", {"role": "leader"}
    leader = _sid(back, "leader: demo login")
    yield "leader", "GET", "/api/analytics", leader, None
    yield "leader", "GET", "/api/insight/evidence", leader, None
    yield "leader", "GET", "/api/radar", leader, None
    back, _ = yield "timetable", "POST", "/api/auth/demo", "", {"role": "office"}
    back, _ = yield "timetable", "POST", "/api/me/role", _sid(back, "timetable: demo login"), {"role": "academic_office"}
    ao, term, vid = _sid(back, "timetable: academic office"), tt["term"], tt["version"]
    b, v = f"/api/timetable/build/{term}", f"/api/timetable/versions/{vid}"
    for path in (b, f"{b}/readiness", f"{b}/units", f"{b}/groups", f"{b}/versions", f"{b}/teachers/{tt['teacher']}/availability",
                 f"{v}/grid?group_id={tt['group']}", f"{v}/grid?teacher_id={tt['teacher']}", f"{v}/grid?room_id={tt['room']}",
                 f"{v}/unplaced", f"{v}/scorecard", f"{v}/placements/{tt['placement']['id']}/options", "/api/timetable/settings"):
        yield "timetable", "GET", path, ao, None
    p = tt["placement"]
    yield "timetable", "POST", f"{v}/placements/{p['id']}/move", ao, {"weekday": p["weekday"], "period": p["period"],
                                                                      "room_id": p["room_id"], "rev": 0}


BULK = 1200


def bulk_exam(data: Path, eid: int, n: int = BULK) -> None:
    """A second exam of the same course, released, that ``n`` other students sat: roster, forms, attempts, answers and
    events. One sitting student leaves every exam table under --min-rows, where a scan would not show (Checkpoint F, TE-F6)."""
    db = sqlite3.connect(data / "campus.db")
    try:
        cid = db.execute("SELECT course_id FROM exams WHERE id=?", (eid,)).fetchone()[0]
        qids = [r[0] for r in db.execute("SELECT id FROM questions WHERE course_id=? ORDER BY id LIMIT 3", (cid,))]
        students = [r[0] for r in db.execute("SELECT id FROM users WHERE role='student' AND status='active' ORDER BY id LIMIT ? OFFSET 1", (n,))]
        if len(students) < n:
            raise SystemExit(f"the dataset has {len(students) + 1} students; the bulk exam needs {n + 1}")
        t = "2026-01-15T09:00:00+00:00"
        bulk = db.execute("INSERT INTO exams(course_id,kind,title,opens_at,closes_at,duration_min,plan,status,secret,created_at,opened_at,closed_at) "
                          "VALUES(?,'main','Keçmiş yük imtahanı',?,?,120,'[]','released','bulk',?,?,?)", (cid, t, t, t, t, t)).lastrowid
        db.executemany("INSERT INTO exam_roster(exam_id,student_id,status,added_at) VALUES(?,?,'eligible',?)", [(bulk, s, t) for s in students])
        db.executemany("INSERT INTO exam_forms(exam_id,student_id,seed,items,created_at) VALUES(?,?,?,?,?)",
                       [(bulk, s, str(s), json.dumps([{"qid": q} for q in qids]), t) for s in students])
        db.executemany("INSERT INTO exam_attempts(exam_id,student_id,started_at,deadline_at,submitted_at,status,score,max_score) "
                       "VALUES(?,?,?,?,?,'submitted',1,3)", [(bulk, s, t, t, t) for s in students])
        attempts = [r[0] for r in db.execute("SELECT id FROM exam_attempts WHERE exam_id=?", (bulk,))]
        db.executemany("INSERT INTO exam_answers(attempt_id,qid,value,saved_at) VALUES(?,?,'1',?)", [(a, q, t) for a in attempts for q in qids])
        db.executemany("INSERT INTO exam_events(exam_id,seq,kind,actor_id,student_id,data,at) VALUES(?,?,'attempt.started',?,?,'{}',?)",
                       [(bulk, i, s, s, t) for i, s in enumerate(students, 1)])
        db.commit()
    finally:
        db.close()


def bulk_timetable(data: Path, n: int = 3000) -> dict:
    """A draft of the current term over ``n`` synthetic units (1 200 teachers, 150 groups, the demo's rooms): placements,
    unplaced meetings, unit needs, availability cells and statuses, group shifts, every builder table above --min-rows
    (Task 48). A group's units take distinct slots, at most 4 a day, odd and even weeks in turn; the first unit is online, so the move
    the scenario sends (to its own slot) passes every rule. Ids only, no real name."""
    db = sqlite3.connect(data / "campus.db")
    try:
        t = "2026-09-01T09:00:00"
        term = db.execute("SELECT id FROM academic_terms WHERE active=1 ORDER BY teaching_start DESC LIMIT 1").fetchone()[0]
        dep = db.execute("INSERT INTO departments(faculty_id,code,name,active,created_at,updated_at) VALUES(1,'QPT','Yük kafedrası',1,?,?)",
                         (t, t)).lastrowid
        db.executemany("INSERT INTO study_groups(name,year,faculty_id,active) VALUES(?,2025,1,1)", [(f"QP-{g}",) for g in range(150)])
        groups = [r[0] for r in db.execute("SELECT id FROM study_groups WHERE name LIKE 'QP-%' ORDER BY id")]
        db.executemany("INSERT INTO users(username,full_name,role,title,color,department_id) VALUES(?,?,'teacher','','#333',?)",
                       [(f"qp_t{i}", f"Yük müəllimi {i}", dep) for i in range(1200)])
        teachers = [r[0] for r in db.execute("SELECT id FROM users WHERE username LIKE 'qp_t%' ORDER BY id")]
        db.executemany("INSERT INTO courses(code,name,teacher_id,credits,color,department_id,term_id,active,created_at,updated_at) "
                       "VALUES(?,?,?,5,'#777',?,?,1,?,?)", [(f"QP-{k}", f"Yük fənni {k}", teachers[k % 300], dep, term, t, t) for k in range(300)])
        courses = [r[0] for r in db.execute("SELECT id FROM courses WHERE code LIKE 'QP-%' ORDER BY id")]
        db.executemany("INSERT INTO teaching_units(course_id,kind,teacher_id,active,created_at,updated_at,hours,students) "
                       "VALUES(?,'seminar',?,1,?,?,15,20)", [(courses[i % 300], teachers[i % 1200], t, t) for i in range(n)])
        units = [r[0] for r in db.execute("SELECT u.id FROM teaching_units u JOIN courses co ON co.id=u.course_id WHERE co.code LIKE 'QP-%' ORDER BY u.id")]
        db.executemany("INSERT INTO teaching_unit_groups(unit_id,group_id) VALUES(?,?)", [(u, groups[i % 150]) for i, u in enumerate(units)])
        rooms = [r[0] for r in db.execute("SELECT id FROM rooms WHERE active=1 ORDER BY id")]
        vid = db.execute("INSERT INTO tt_versions(term_id,status,rev,checked_rev,violations,score,scope,unplaced,created_by,created_at) "
                         "VALUES(?,'draft',0,0,0,'{}','{\"all\":true}',?,1,?)", (term, n // 2, t)).lastrowid
        db.executemany("INSERT INTO tt_placements(version_id,meeting_key,unit_id,part,weekday,period,duration,weeks,room_id,locked,origin) "
                       "VALUES(?,?,?,0,?,?,1,?,?,0,'solver')",
                       [(vid, f"{u}:0", u, 1 + (i // 150) % 6, 1 + (i // 900) % 4, ("odd", "even")[(i // 150) % 2], rooms[i % len(rooms)] if i else None)
                        for i, u in enumerate(units)])
        db.executemany("INSERT INTO tt_unplaced(version_id,meeting_key,unit_id,reasons) VALUES(?,?,?,'[]')", [(vid, f"{u}:1", u) for u in units[: n // 2]])
        db.executemany("INSERT INTO tt_unit_needs(unit_id,duration,mode) VALUES(?,1,?)", [(u, "online" if not i else "in_person")
                                                                                         for i, u in enumerate(units[: n // 2])])
        db.executemany("INSERT INTO tt_availability(term_id,subject_type,subject_id,weekday,period,weeks,level,updated_by,updated_at) "
                       "VALUES(?,'teacher',?,?,?,'all','undesired',1,?)", [(term, x, d, p, t) for x in teachers for d in (5, 6) for p in (5, 6)])
        db.executemany("INSERT INTO tt_availability_status(term_id,teacher_id,confirmed_at) VALUES(?,?,?)", [(term, x, t) for x in teachers])
        db.executemany("INSERT INTO tt_group_terms(term_id,group_id,shift) VALUES(?,?,'morning')", [(term, g) for g in groups])
        db.executemany("INSERT INTO tt_runs(term_id,kind,status,seed,iter_budget,time_budget_s,requested_by,requested_at) "
                       "VALUES(?,'precheck','done',0,0,0,1,?)", [(term, t)] * 1200)
        db.commit()
        p = db.execute("SELECT id, weekday, period, room_id FROM tt_placements WHERE version_id=? ORDER BY id LIMIT 1", (vid,)).fetchone()
        return {"term": term, "version": vid, "group": groups[0], "teacher": teachers[0], "room": rooms[0],
                "placement": {"id": p[0], "weekday": p[1], "period": p[2], "room_id": p[3]}}
    finally:
        db.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--dataset", choices=sorted(loadtest.SIZES), default="university")
    ap.add_argument("--min-rows", type=int, default=1000)
    args = ap.parse_args(argv)
    os.environ.pop("ZEKA_TX_GUARD", None)              # it installs its own trace callback on every connection
    with tempfile.TemporaryDirectory(prefix="zeka-plan-") as tmp:
        data = Path(tmp)
        loadtest.build_dataset(data, args.dataset)       # sets ZEKA_DATA before store is imported
        exam = loadtest.exam_setup(data, 1)
        bulk_exam(data, exam[0])
        tt = bulk_timetable(data)
        from zeka.core import web
        from zeka.legacy import api, store
        seen: list[str] = []
        origin: dict[str, str] = {}                      # statement -> the scenario that first ran it
        timing: list[dict] = []
        connect = store.connect

        def traced():
            c = connect()
            c.set_trace_callback(seen.append)            # parameters arrive already bound into the text
            return c

        store.connect = traced                          # the read routes never search: no BM25 build needed
        srv = web.make_server(0, api.R, ROOT / "frontend", api.before, api.after, lambda _msg: None)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]
        try:
            tokens, news = loadtest.sessions(port, data)
            steps, answer = _routes(tokens[0], news, exam, tt), None
            while True:
                try:
                    name, method, path, cookie, body = steps.send(answer)
                except StopIteration:
                    break
                first, t = len(seen), time.perf_counter()
                status, back, raw = _send(port, method, path, cookie, body)
                timing.append({"scenario": name, "route": f"{method} {re.sub(r'/[0-9]+', '/N', path)}",
                               "ms": round((time.perf_counter() - t) * 1000), "statements": len(seen) - first})
                origin.update({sql: name for sql in seen[first:] if sql not in origin})
                if status != 200:
                    raise SystemExit(f"{name}: {method} {path}: HTTP {status}: {raw[:300].decode('utf-8', 'replace')}")
                answer = back, raw
        finally:
            srv.shutdown()
            srv.server_close()
        db = sqlite3.connect(data / "campus.db")
        try:
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            sizes = {t.lower(): db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}  # nosec B608 - names from sqlite_master
            bad: dict[str, dict[str, list[str]]] = {}
            for sql in dict.fromkeys(seen):
                plan = scans(db, sql, sizes, args.min_rows) if WRITES.match(sql) else []
                if plan:
                    bad.setdefault(origin.get(sql, "setup"), {})[sql] = plan
        finally:
            db.close()
    timing.sort(key=lambda r: -r["ms"])
    print(json.dumps({"dataset": args.dataset, "statements": len(set(seen)), "scenarios": sorted({r["scenario"] for r in timing}),
                      "exam_rows": {t: n for t, n in sorted(sizes.items()) if t.startswith("exam")},
                      "tt_rows": {t: n for t, n in sorted(sizes.items()) if t.startswith("tt_")}, "scans": bad, "slowest": timing[:8]},
                     ensure_ascii=False, indent=1))
    return 1 if any(k != "leader" for k in bad) else 0


if __name__ == "__main__":
    sys.exit(main())
