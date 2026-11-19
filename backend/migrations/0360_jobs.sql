-- Task 36, slice 1: periodic jobs. job_runs: one row per run of a job (running, ok, error and why); the next run of a
-- job is computed from its last successful one. job_lease: the one runner at a time. reminders_sent: a reminder of a
-- threshold (an SLA about to pass, passed, a due date tomorrow) is sent once per object.
CREATE TABLE IF NOT EXISTS job_runs(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, started_at TEXT NOT NULL,
  finished_at TEXT, status TEXT NOT NULL, detail TEXT, ms INTEGER, holder TEXT);
CREATE INDEX IF NOT EXISTS idx_job_runs_name ON job_runs(name, status, started_at);
CREATE TABLE IF NOT EXISTS job_lease(name TEXT PRIMARY KEY, holder TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reminders_sent(kind TEXT NOT NULL, obj_id INTEGER NOT NULL, threshold TEXT NOT NULL, sent_at TEXT NOT NULL,
  PRIMARY KEY(kind, obj_id, threshold));
