-- Task 11: the database keeps only the SHA-256 of a session id, so a copy of it holds no usable session.
-- Sessions of the old form (plain ids) end here: everyone signs in once more after this migration.
-- scope: full | password_change | mfa_enroll | mfa (what the session may reach; Tasks 10 and 12).
-- last_seen: idle timeout; created_at: absolute timeout; both per role (backend/zeka/modules/identity/domain.py).
DROP TABLE IF EXISTS sessions;
CREATE TABLE sessions(id INTEGER PRIMARY KEY, id_hash TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL,
  created_at TEXT NOT NULL, last_seen TEXT NOT NULL, scope TEXT NOT NULL DEFAULT 'full', mfa_at TEXT,
  ip TEXT, agent TEXT);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_seen ON sessions(last_seen);
