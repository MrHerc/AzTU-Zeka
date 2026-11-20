-- Task 39: the event log. One row per signed-in request that changed something (its handler's module and name), per
-- sign-in and per session's first request of a day ("visit"): who (the user and the role the session acted in), what,
-- when (the university's wall clock, as store.now()), module. Kept 365 days (legacy/periodic.py, retention.purge).
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, user_id INTEGER, role TEXT NOT NULL, action TEXT NOT NULL,
  module TEXT NOT NULL, created_at TEXT NOT NULL);
-- active users per week and role, modules in use, the purge: one range over time, read from the index alone
CREATE INDEX IF NOT EXISTS idx_events_time ON events(created_at, role, user_id, module);
-- the measured indicators (modules/insight): requests closed in a period, assistant answers given in a period
CREATE INDEX IF NOT EXISTS idx_requests_status_updated ON requests(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);
