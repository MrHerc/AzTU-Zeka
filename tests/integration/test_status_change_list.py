"""The "Tələbə-məzun" change list (tasks/todo.md, Task 37): every status order entered after the given moment, with the
days left to the 10-day deadline counted from the order date (an assumption to check against Decree No. 225, SPEC Open
Questions 17); the operator's "entered" mark writes ``reported_at`` once, and the next list shows it.

Orders are entered on the screen at known moments (``clock.now`` patched; the server runs in this process), minutes
apart: a staff session ends after an idle hour."""
from datetime import timedelta, timezone

import pytest

from zeka.core import clock
from zeka.legacy import store

BASE = clock.now().replace(microsecond=0)
BEFORE, AFTER, LATER = BASE + timedelta(minutes=2), BASE + timedelta(minutes=10), BASE + timedelta(minutes=30)
SINCE = (BASE + timedelta(minutes=5)).astimezone(clock.ZONE).isoformat()          # e.g. 2026-11-19T10:05:00+04:00
TODAY = store.now().date()


def wall(t) -> str:
    return t.astimezone(clock.ZONE).replace(tzinfo=None).isoformat()


def day(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


@pytest.fixture(scope="module")
def registrar(app_db):
    """The dean's office user acting as the academic office (a granted role), who enters orders and reports them."""
    office_id = app_db.client("office").user["id"]
    app_db.client("admin").post(f"/api/admin/users/{office_id}/roles", {"role": "academic_office"})
    r = app_db.client("office")
    assert r.post("/api/me/role", {"role": "academic_office"}).status == 200
    return r


@pytest.fixture(scope="module")
def orders(app_db, registrar):
    """A: entered before SINCE. B (an order of 3 days ago) and C (of 12 days ago) after it."""
    students = [x["id"] for x in q("SELECT id FROM users WHERE role='student' ORDER BY id LIMIT 3")]
    admin = app_db.client("admin")                     # T-E3: D is a student of another faculty
    fb = admin.post("/api/directory/faculties", {"code": "TMB", "name": "TM B fakültəsi"}).json["id"]
    gb = admin.post("/api/directory/groups", {"name": "TMB-25-1", "year": 2025, "faculty_id": fb}).json["id"]
    students.append(admin.post("/api/directory/users", {"username": "tm.d", "full_name": "Sınaq tm.d", "role": "student", "group_id": gb,
                                                        "student_no": "TM-D"}).json["id"])
    real = clock.now
    out = {}
    try:
        for name, at, sid, kind, order_date, effective in (("A", BEFORE, students[0], "admission", day(-1), day(-1)),
                                                            ("B", AFTER, students[1], "reinstatement", day(-3), day(2)),   # T-E4
                                                            ("C", AFTER, students[2], "admission", day(-12), day(-12)),
                                                            ("D", AFTER, students[3], "admission", day(-1), day(-1))):
            clock.now = lambda at=at: at
            r = registrar.post(f"/api/directory/students/{sid}/status", {"kind": kind, "order_no": f"TM-{name}", "order_date": order_date,
                                                                         "effective_date": effective})
            assert r.status == 200, r.text
            out[name] = q("SELECT id FROM student_status_events WHERE order_no=?", (f"TM-{name}",))[0]["id"]
    finally:
        clock.now = real
    return out


@pytest.fixture
def at_noon_after(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: AFTER)


def listed(client, since=SINCE):
    r = client.get(f"/api/integration/status-changes?since={since}")
    assert r.status == 200, r.text
    return {x["id"]: x for x in r.json["items"]}


def test_every_order_entered_after_the_moment_is_listed_with_the_days_left(registrar, orders, at_noon_after):
    items = listed(registrar)                          # the '+' of the offset arrives as a space; it still reads as +04:00
    assert set(items) == {orders["B"], orders["C"], orders["D"]}, "A was entered before the moment"
    b, c = items[orders["B"]], items[orders["C"]]
    assert (b["kind"], b["order_no"], b["order_date"], b["deadline"], b["days_left"]) == ("reinstatement", "TM-B", day(-3), day(7), 7)
    assert (c["deadline"], c["days_left"]) == (day(-2), -2), "overdue: negative"
    assert b["reported_at"] is None and c["reported_at"] is None and b["student_no"]
    utc = (BASE + timedelta(minutes=1)).astimezone(timezone.utc).isoformat().replace("+00:00", "%2B00:00")
    assert set(listed(registrar, utc)) == {orders["A"], orders["B"], orders["C"], orders["D"]}, "the same moments in another zone"
    assert listed(registrar, (AFTER + timedelta(seconds=1)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")) == {}
    assert registrar.get("/api/integration/status-changes?since=yesterday").status == 400


def test_marking_writes_reported_at_once_and_the_next_list_shows_it(registrar, orders, monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: AFTER)
    r = registrar.post(f"/api/integration/status-changes/{orders['B']}/reported")
    assert r.status == 200 and r.json["reported_at"] == wall(AFTER)
    assert q("SELECT reported_at FROM student_status_events WHERE id=?", (orders["B"],))[0]["reported_at"] == wall(AFTER)
    items = listed(registrar)
    assert items[orders["B"]]["reported_at"] == wall(AFTER) and items[orders["C"]]["reported_at"] is None
    monkeypatch.setattr(clock, "now", lambda: LATER)
    again = registrar.post(f"/api/integration/status-changes/{orders['B']}/reported")
    assert again.status == 200 and again.json["reported_at"] == wall(AFTER), "the first mark stays"
    assert q("SELECT COUNT(*) n FROM audit WHERE action='status_reported' AND detail=?", (f"#{orders['B']}",))[0]["n"] == 1
    assert registrar.post("/api/integration/status-changes/999999/reported").status == 404


def test_who_may_list_and_mark(app_db, orders, at_noon_after):
    for role in ("admin", "leader", "office"):
        assert app_db.client(role).get(f"/api/integration/status-changes?since={SINCE}").status == 200, role
    for role in ("teacher", "student"):
        assert app_db.client(role).get(f"/api/integration/status-changes?since={SINCE}").status == 403, role
    assert orders["D"] not in listed(app_db.client("office")) and orders["B"] in listed(app_db.client("office")), "T-E3: own faculty only"
    assert orders["D"] in listed(app_db.client("admin"))
    for role in ("admin", "leader", "office", "teacher", "student"):
        assert app_db.client(role).post(f"/api/integration/status-changes/{orders['C']}/reported").status == 403, role
    assert app_db.client().get("/api/integration/status-changes").status == 401
    assert q("SELECT reported_at FROM student_status_events WHERE id=?", (orders["C"],))[0]["reported_at"] is None
