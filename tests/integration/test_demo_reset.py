"""The demo reset clears every table, append-only ones included, and leaves their guards in place (Checkpoint F, F1)."""
import sqlite3

from zeka.legacy import store

GUARDS = {"audit_no_early_delete", "audit_no_update", "exam_events_no_delete", "exam_events_no_update",
          "status_events_no_delete", "status_events_no_update"}


def _triggers():
    c = sqlite3.connect(store.DB_PATH)
    try:
        return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    finally:
        c.close()


def test_a_reset_with_a_status_order_succeeds_and_keeps_every_guard(app_db, admin, student):
    c = sqlite3.connect(store.DB_PATH)
    sid = c.execute("SELECT id FROM users WHERE role='student' LIMIT 1").fetchone()[0]
    c.execute("INSERT INTO student_status_events(student_id, kind, order_no, order_date, effective_date, entered_by, created_at)"
              " VALUES (?, 'leave', 'T-1', '2026-11-01', '2026-11-01', 1, '2026-11-01 10:00:00')", (sid,))
    c.commit()
    c.close()
    assert GUARDS <= _triggers()
    r = admin.post("/api/admin/reset")
    assert r.status == 200, r.text
    assert GUARDS <= _triggers()
    c = sqlite3.connect(store.DB_PATH)
    assert c.execute("SELECT COUNT(*) FROM student_status_events").fetchone()[0] == 0
    c.close()
    assert app_db.client("student").post("/api/feedback", {"score": 4}).status == 200     # the database is not left locked


def test_a_failed_reset_rolls_back_and_releases_the_lock(app_db, monkeypatch):
    def boom(c):
        raise RuntimeError("seed failed")
    monkeypatch.setattr(store, "seed", boom)
    try:
        store.reseed()
    except RuntimeError:
        pass
    assert GUARDS <= _triggers()
    c = sqlite3.connect(store.DB_PATH, timeout=1)
    assert c.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0        # nothing was deleted
    c.execute("UPDATE settings SET value=value WHERE key='university'")    # and nothing holds the write lock
    c.commit()
    c.close()
