-- Task 40: privacy. A consent is a row per purpose and choice: the version of the text the person saw (the first 12 hex
-- digits of its SHA-256, backend/zeka/modules/identity/privacy.py), granted or withdrawn, when and how (method: 'portal'
-- is the portal's checkbox; a written or e-signed consent entered later gets its own method). The newest row of a purpose
-- is the person's current choice; older rows stay as the proof (Personal Data Law, Art. 8: the burden of proof is on the
-- operator). consent_texts keeps the exact text of every version that was ever consented to.
CREATE TABLE IF NOT EXISTS consents(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, purpose TEXT NOT NULL,
  version TEXT NOT NULL, granted INTEGER NOT NULL, method TEXT NOT NULL, lang TEXT, at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_consents_user ON consents(user_id, purpose, id);
CREATE TABLE IF NOT EXISTS consent_texts(version TEXT PRIMARY KEY, purpose TEXT NOT NULL, text TEXT NOT NULL, first_at TEXT NOT NULL);
-- A person's request to delete their data: a staff role decides (privacy.decide); an approved one deletes or anonymises
-- the rows by the data inventory (docs/privacy/data-inventory.md) and keeps the counts in result.
CREATE TABLE IF NOT EXISTS privacy_requests(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
  kind TEXT NOT NULL DEFAULT 'erase', reason TEXT, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL,
  decided_by INTEGER, decided_at TEXT, note TEXT, result TEXT);
CREATE INDEX IF NOT EXISTS idx_privacy_requests_status ON privacy_requests(status, id);
CREATE INDEX IF NOT EXISTS idx_privacy_requests_user ON privacy_requests(user_id, id);
-- The consents given before Task 40 had no text version: they are kept as version '0', which matches no current text,
-- so the external AI waits for a new consent to the versioned text.
INSERT INTO consents(user_id, purpose, version, granted, method, lang, at)
  SELECT id, 'ai', '0', 1, 'portal', NULL, consent_at FROM users WHERE consent_at IS NOT NULL;
INSERT INTO consents(user_id, purpose, version, granted, method, lang, at)
  SELECT id, 'external_ai', '0', 1, 'portal', NULL, consent_at FROM users
  WHERE consent_at IS NOT NULL AND (CASE WHEN json_valid(prefs) THEN json_extract(prefs, '$.consent.external') END) = 1;
-- The retention job deletes by time; the export and the erasure read the audit log by person.
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit(ts);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at);
