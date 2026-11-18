-- Task 12: a second factor (TOTP, RFC 6238) for staff, optional for students.
-- totp_secret is stored in plain text: the standard library has no symmetric cipher. This is an accepted risk recorded
-- in the threat model (Task 41); with an approved dependency it would be encrypted with a key from the environment.
-- totp_last: the last accepted 30-second step, so a code is accepted at most once. totp_enabled_at: NULL while enrolling.
ALTER TABLE users ADD COLUMN totp_secret TEXT;
ALTER TABLE users ADD COLUMN totp_last INTEGER;
ALTER TABLE users ADD COLUMN totp_enabled_at TEXT;
-- Ten one-time recovery codes per account, stored as SHA-256 (each code carries about 50 random bits).
CREATE TABLE IF NOT EXISTS recovery_codes(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, code_hash TEXT NOT NULL,
  used_at TEXT);
CREATE INDEX IF NOT EXISTS idx_recovery_codes_user ON recovery_codes(user_id);
-- Wrong second-factor codes in a pending sign-in; at 5 the pending session ends and the password step starts again.
ALTER TABLE sessions ADD COLUMN mfa_failures INTEGER NOT NULL DEFAULT 0;
