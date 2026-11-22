-- Task 42 (AR-F11, with Checkpoint F AR-F4): a person's active days are exported and erased by user_id
-- (identity/repo.INVENTORY); the primary key (role, day, user_id) cannot serve that lookup.
CREATE INDEX IF NOT EXISTS idx_active_days_user ON active_days(user_id);
