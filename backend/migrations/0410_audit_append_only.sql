-- Task 41 (SP 800-53 AU-9, threat model R3): the audit log is append-only. No row is ever changed; a row is deleted only
-- when it is older than the shortest audit retention period (365 days, identity/privacy.RETENTION), which is what the
-- retention job does (legacy/periodic.py). Like exam_events (0301) this stops the application and an ordinary SQL session;
-- someone holding the database file can drop the triggers, which the backups and the second host expose.
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_early_delete BEFORE DELETE ON audit
WHEN old.ts IS NULL OR old.ts >= strftime('%Y-%m-%dT%H:%M:%S', 'now', '-364 days')
BEGIN SELECT RAISE(ABORT, 'audit rows are kept at least a year'); END;
