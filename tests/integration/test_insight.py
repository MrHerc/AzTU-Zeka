"""Measured indicators and the accreditation evidence (tasks/todo.md, Task 39).

- No dashboard tile is fed by a constant: every tile of /api/analytics is a tile of the insight module, each tile runs a
  query, reads 0 or nothing on a database without the rows it counts, and the exact value on rows written for it.
- Every tile carries its definition and its period.
- The evidence page exports (CSV).
Also: the event log (a change and a sign-in leave an event, a read does not) and its retention.
"""
import csv
import io
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from zeka.core import clock, events
from zeka.legacy import periodic, store
from zeka.modules.insight import service

CODES = ["3.5.1", "3.5.3", "5.4.2", "5.4.3", "5.4.4", "5.4.5", "5.4.6", "5.4.7", "5.4.8"]
COUNTED = ("events", "lessons", "attendance", "requests", "messages", "exams", "academy_progress")   # what the tiles read


@pytest.fixture
def copy(app_db, tmp_path):
    """A copy of the module's database: the rows written or deleted here stay out of the server's."""
    src = store.connect()
    dst = sqlite3.connect(tmp_path / "insight.db")
    src.backup(dst)
    src.close()
    dst.row_factory = sqlite3.Row
    yield dst
    dst.close()


def _events(where="1=1", args=()):
    c = store.connect()
    try:
        return store.rows(c, f"SELECT * FROM events WHERE {where} ORDER BY id", args)  # nosec B608
    finally:
        c.close()


# ---------------------------------------------------------------- criterion 1 and 2: tiles
def test_every_dashboard_tile_is_an_insight_tile_with_its_definition_and_period(leader):
    a = leader.get("/api/analytics").json
    assert [k["key"] for k in a["kpis"]] == [s["key"] for s in service.TILES], "a tile outside the insight module"
    for k in a["kpis"]:
        assert isinstance(k["definition"], str) and len(k["definition"]) > 30 and k["definition"] != k["label"], k
        assert k["unit"] in ("pct", "hours", "count") and len(k["series"]) == service.WEEKS, k
        assert k["value"] is None or isinstance(k["value"], (int, float)), k
        to = datetime.fromisoformat(k["range"]["to"])
        assert k["range"]["from"] is None or datetime.fromisoformat(k["range"]["from"]) < to, k
    assert [k["key"] for k in a["kpis"] if k["range"]["from"] is None] == ["academy"], "only the running total has no start"
    assert "cost_per_student" not in a["ai"]
    en = {k["key"]: k for k in leader.get("/api/analytics", lang="en").json["kpis"]}
    assert all(en[k["key"]]["definition"] != k["definition"] for k in a["kpis"]), "every definition is translated"


def test_every_tile_runs_a_query_and_reads_nothing_without_its_rows(copy):
    t = store.now()
    for spec in service.TILES:
        ran: list[str] = []
        copy.set_trace_callback(ran.append)
        service.tile(copy, spec, t)
        copy.set_trace_callback(None)
        assert any(s.lstrip().upper().startswith("SELECT") for s in ran), f"{spec['key']}: no query behind the tile"
    for table in COUNTED:
        copy.execute(f"DELETE FROM {table}")  # nosec B608
    for k in service.tiles(copy):
        assert k["value"] in (None, 0) and all(v in (None, 0) for v in k["series"]), f"{k['key']} shows {k['value']} without rows"


def test_every_tile_counts_the_rows_written_for_it(copy):
    for table in COUNTED:
        copy.execute(f"DELETE FROM {table}")  # nosec B608
    t, u = store.now(), clock.now()
    at = lambda d, h=0: store.iso(t - timedelta(days=d) + timedelta(hours=h))  # noqa: E731
    q = lambda sql, args=(): [r[0] for r in copy.execute(sql, args)]  # noqa: E731
    students, teachers = q("SELECT id FROM users WHERE role='student' AND status='active'"), q("SELECT id FROM users WHERE role='teacher' AND status='active'")
    course = q("SELECT id FROM courses LIMIT 1")[0]
    # 2 students and 1 teacher active this week; a student active 10 days ago only counts in an earlier week
    for uid, role, d in ((students[0], "student", 1), (students[0], "student", 2), (students[1], "student", 3), (teachers[0], "teacher", 1),
                         (students[2], "student", 10)):
        copy.execute("INSERT INTO events(user_id,role,action,module,created_at) VALUES(?,?,?,?,?)", (uid, role, "x", "core", at(d)))
    # 4 lessons held 2 days ago, 3 of them with attendance; a cancelled one and tomorrow's do not count
    day = (t - timedelta(days=2)).date().isoformat()
    lids = [copy.execute("INSERT INTO lessons(course_id,day,start,\"end\",status) VALUES(?,?,?,?,?)", (course, d, "09:00", "10:20", s)).lastrowid
            for d, s in ((day, "scheduled"),) * 4 + ((day, "cancelled"), ((t + timedelta(days=1)).date().isoformat(), "scheduled"))]
    for lid in lids[:3]:
        copy.execute("INSERT INTO attendance(lesson_id,user_id,status) VALUES(?,?,?)", (lid, students[0], "present"))
    # requests closed: 10 h within its 24 h, 30 h past its 24 h; an open one does not count
    for created, hours, status in ((3, 10, "ready"), (5, 30, "rejected"), (1, 0, "submitted")):
        copy.execute("INSERT INTO requests(type_code,student_id,data,status,created_at,updated_at,due_at) VALUES('ref',?,'{}',?,?,?,?)",
                     (students[0], status, at(created), at(created, hours), at(created, 24)))
    # 4 answers of the tutor and the assistant, 3 citing a source; a student's question does not count
    for channel, role, cites in (("tutor", "assistant", "[1]"), ("tutor", "assistant", "[2,3]"), ("campus", "assistant", "[4]"),
                                 ("campus", "assistant", "[]"), ("tutor", "user", "[]")):
        copy.execute("INSERT INTO messages(user_id,course_id,channel,role,content,cites,created_at) VALUES(?,?,?,?,?,?,?)",
                     (students[0], course, channel, role, "x", cites, at(1)))
    # 2 exams opened yesterday; a draft has not opened
    for opened in ((u - timedelta(days=1)).isoformat(timespec="seconds"),) * 2 + (None,):
        copy.execute("INSERT INTO exams(course_id,title,opens_at,closes_at,duration_min,plan,secret,created_at,opened_at) "
                     "VALUES(?,?,?,?,?,?,?,?,?)", (course, "x", "2026-01-01", "2026-01-02", 60, "{}", "s", "2026-01-01", opened))
    # one teacher with 3 completed academy modules, another with 2
    mods = q("SELECT id FROM academy_modules ORDER BY id LIMIT 3")
    for uid, n in ((teachers[0], 3), (teachers[1], 2)):
        for mid in mods[:n]:
            copy.execute("INSERT INTO academy_progress(user_id,module_id,status,score,completed_at) VALUES(?,?,?,?,?)", (uid, mid, "completed", 100, at(4)))
    got = {k["key"]: k for k in service.tiles(copy)}
    pct = lambda n, d: round(100 * n / d, 1)  # noqa: E731
    assert {k: v["value"] for k, v in got.items()} == {
        "wau_student": pct(2, len(students)), "wau_teacher": pct(1, len(teachers)), "journal": 75.0, "request_hours": 20.0,
        "request_sla": 50.0, "cited": 75.0, "exams": 2, "academy": pct(1, len(teachers))}
    assert got["wau_student"]["series"][-2] == pct(1, len(students)), "the student of 10 days ago is in the week before"
    assert got["request_hours"]["ok"] is True and got["cited"]["ok"] is False      # target 24 h (lower is better); 95 %
    # Checkpoint F (CR-F1): lessons up to the journal's cut-over date cannot be marked in Zəka and leave the fill share
    for _ in range(4):
        copy.execute("INSERT INTO lessons(course_id,day,start,\"end\",status) VALUES(?,?,?,?,?)",
                     (course, (t - timedelta(days=9)).date().isoformat(), "09:00", "10:20", "scheduled"))
    assert {k["key"]: k["value"] for k in service.tiles(copy)}["journal"] == pct(3, 8), "unmarked lessons count until a cut-over"
    copy.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('tenant',?)",
                 (json.dumps({"journal": {"cutover_date": (t - timedelta(days=5)).date().isoformat()}}),))
    assert {k["key"]: k["value"] for k in service.tiles(copy)}["journal"] == 75.0


def test_a_28_day_tile_counts_20_days_back_and_not_30(copy):
    """Checkpoint F (TE-F10): the period each definition names (28 days, 7 for the weekly active users) is the period counted."""
    for table in COUNTED:
        copy.execute(f"DELETE FROM {table}")  # nosec B608
    t, u = store.now(), clock.now()
    student = copy.execute("SELECT id FROM users WHERE role='student' AND status='active' LIMIT 1").fetchone()[0]
    course = copy.execute("SELECT id FROM courses LIMIT 1").fetchone()[0]
    for days, marked, hours in ((20, True, 10), (30, False, 40)):          # inside the 28 days, outside them
        day = (t - timedelta(days=days)).date().isoformat()
        lid = copy.execute("INSERT INTO lessons(course_id,day,start,\"end\",status) VALUES(?,?,'09:00','10:20','scheduled')", (course, day)).lastrowid
        if marked:
            copy.execute("INSERT INTO attendance(lesson_id,user_id,status) VALUES(?,?,'present')", (lid, student))
        closed = t - timedelta(days=days)
        copy.execute("INSERT INTO requests(type_code,student_id,data,status,created_at,updated_at) VALUES('ref',?,'{}','ready',?,?)",
                     (student, store.iso(closed - timedelta(hours=hours)), store.iso(closed)))
        copy.execute("INSERT INTO exams(course_id,title,opens_at,closes_at,duration_min,plan,secret,created_at,opened_at) "
                     "VALUES(?,'x','2026-01-01','2026-01-02',60,'{}','s','2026-01-01',?)",
                     (course, (u - timedelta(days=days)).isoformat(timespec="seconds")))
    got = {k["key"]: k for k in service.tiles(copy)}
    assert (got["journal"]["value"], got["request_hours"]["value"], got["exams"]["value"]) == (100.0, 10.0, 1)
    span = {k: datetime.fromisoformat(v["range"]["to"]) - datetime.fromisoformat(v["range"]["from"]) for k, v in got.items() if v["range"]["from"]}
    assert span == {"wau_student": timedelta(days=7), "wau_teacher": timedelta(days=7), "journal": timedelta(days=28),
                    "request_hours": timedelta(days=28), "request_sla": timedelta(days=28), "cited": timedelta(days=28), "exams": timedelta(days=28)}


# ---------------------------------------------------------------- the event log
def test_a_sign_in_and_a_change_leave_an_event_and_a_read_does_not(app_db):
    s = app_db.client("student")
    uid = s.user["id"]
    assert [(e["role"], e["action"], e["module"]) for e in _events("user_id=?", (uid,))][-1:] == [("student", "login", "identity")]
    n = len(_events())
    assert s.get("/api/student/home").status == 200 and s.get("/api/courses").status == 200
    assert len(_events()) == n, "a read is not an event"
    assert s.put("/api/me/prefs", {"theme": "dark"}).status == 200
    last = _events()[-1]
    assert (last["user_id"], last["role"], last["action"], last["module"]) == (uid, "student", "me_prefs", "core")
    assert s.request("PUT", "/api/me/prefs", raw=b"{", headers={"Content-Type": "application/json"}).status == 400
    assert len(_events()) == n + 1, "a refused request changed nothing: no event"
    assert events.module_of("zeka.modules.exam.routes") == "exam" and events.module_of("zeka.legacy.r_services") == "services"


def test_a_session_s_first_request_of_a_day_is_a_visit(app_db, monkeypatch):
    s = app_db.client("student")
    uid = s.user["id"]
    c = store.connect()
    c.execute("UPDATE sessions SET last_seen='2026-11-19T23:50:00' WHERE id=(SELECT MAX(id) FROM sessions WHERE user_id=?)", (uid,))
    c.commit()
    c.close()
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 19, 20, 30, tzinfo=timezone.utc))     # 00:30 in Baku, the next day
    assert s.get("/api/student/home").status == 200
    assert [(e["action"], e["created_at"]) for e in _events("user_id=?", (uid,))][-1] == ("visit", "2026-11-20T00:30:00")


def test_the_retention_purge_drops_events_older_than_a_year(copy):
    t = store.now()
    for d in (366, 364):
        copy.execute("INSERT INTO events(user_id,role,action,module,created_at) VALUES(1,'student','x','core',?)", (store.iso(t - timedelta(days=d)),))
    before = copy.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert "events 1" in periodic.retention_purge(copy)
    assert copy.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before - 1
    assert copy.execute("SELECT COUNT(*) FROM events WHERE created_at<?", (store.iso(t - timedelta(days=365)),)).fetchone()[0] == 0


# ---------------------------------------------------------------- criterion 3: the evidence page
def test_the_evidence_page_counts_live_and_exports(leader, admin, student):
    ev = leader.get("/api/insight/evidence").json
    assert [i["code"] for i in ev["indicators"]] == CODES
    for i in ev["indicators"]:
        assert i["title"] and i["measures"] and all(isinstance(m["value"], int) and m["label"] for m in i["measures"]), i
    hrefs = lambda e: {lk["href"] for i in e["indicators"] for lk in i["links"]}  # noqa: E731
    assert "/admin/integration" not in hrefs(ev) and "/admin/integration" in hrefs(admin.get("/api/insight/evidence").json), \
        "a link is offered only to the roles that can open it"
    value = lambda e, key: next(m["value"] for i in e["indicators"] for m in i["measures"] if m["key"] == key)  # noqa: E731
    assert student.put("/api/me/prefs", {"theme": "light"}).status == 200
    assert value(leader.get("/api/insight/evidence").json, "student_events") == value(ev, "student_events") + 1, "the count is live"

    r = leader.get("/api/insight/evidence?format=csv&lang=en")
    assert r.status == 200 and r.headers["Content-Type"].startswith("text/csv")
    assert r.headers["Content-Disposition"].startswith("attachment;")
    table = list(csv.reader(io.StringIO(r.text)))
    assert table[0] == ["Indicator", "Name", "Measure", "Count", "Start", "End"]
    ev = leader.get("/api/insight/evidence", lang="en").json
    assert table[1:] == [[i["code"], i["title"], m["label"], str(m["value"]), m["range"]["from"] or "", m["range"]["to"]]
                         for i in ev["indicators"] for m in i["measures"]]
    assert student.get("/api/insight/evidence").status == 403
    assert student.get("/api/insight/evidence?format=csv").status == 403
    json.dumps(ev)          # the page's data is plain JSON


def test_an_event_that_cannot_be_written_never_fails_the_request(app_db, monkeypatch):
    """Checkpoint F (SF-F3): the event is bookkeeping; a locked database at that moment keeps the request's own write."""
    s = app_db.client("student")

    def locked(*_a, **_k):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(events, "record", locked)
    assert s.put("/api/me/prefs", {"theme": "dark"}).status == 200
    assert s.get("/api/me").json["prefs"]["theme"] == "dark"
