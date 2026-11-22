-- Task 42 (AR-F11): who was active on which day, in which role (the one the session acted in). core/events.py writes a
-- row next to every event, at most one per person, role and day. The active-user tiles counted distinct people over
-- every event row of 8 weeks (about 0.6 s a query at millions of events); they count these rows. Purged with the events
-- (365 days, legacy/periodic.py); erased with the person (identity/repo.INVENTORY).
CREATE TABLE IF NOT EXISTS active_days(day TEXT NOT NULL, role TEXT NOT NULL, user_id INTEGER NOT NULL,
  PRIMARY KEY(role, day, user_id)) WITHOUT ROWID;
-- active users per role over a period, the purge
CREATE INDEX IF NOT EXISTS idx_active_days_day ON active_days(day, role);
INSERT OR IGNORE INTO active_days(day, role, user_id) SELECT substr(created_at, 1, 10), role, user_id FROM events WHERE user_id IS NOT NULL;
