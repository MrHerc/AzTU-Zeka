-- Checkpoint B (review of Tasks 10-17): the dean's-office scope reads students by group, and the started sign-ins
-- are swept by age; both were full scans of growing tables.
CREATE INDEX IF NOT EXISTS idx_users_group ON users(group_id);
CREATE INDEX IF NOT EXISTS idx_sso_pending_created ON sso_pending(created_at);
