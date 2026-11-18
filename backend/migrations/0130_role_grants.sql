-- Task 13: more than one role per person. users.role stays the primary role (always held); role_grants adds others,
-- each with an optional scope (scope_type faculty | department | course, scope_id the row it names).
-- sessions.role: the role a session acts in (NULL = the primary role); switching it gives the session a new id.
CREATE TABLE IF NOT EXISTS role_grants(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, role TEXT NOT NULL,
  scope_type TEXT, scope_id INTEGER, granted_by INTEGER, granted_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS idx_role_grants_unique ON role_grants(user_id, role, IFNULL(scope_type, ''), IFNULL(scope_id, 0));
CREATE INDEX IF NOT EXISTS idx_role_grants_scope ON role_grants(role, scope_type, scope_id);
ALTER TABLE sessions ADD COLUMN role TEXT;
