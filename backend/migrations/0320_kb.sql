-- Task 32: the campus knowledge base is edited on screen. An article has a version, a status (published, draft,
-- archived: only a published one is searched), the clause of its source document, a date by which it is reviewed
-- again, and who changed it last; every saved state is a row of campus_kb_versions.
ALTER TABLE campus_kb ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE campus_kb ADD COLUMN status TEXT NOT NULL DEFAULT 'published';
ALTER TABLE campus_kb ADD COLUMN source_ref TEXT;
ALTER TABLE campus_kb ADD COLUMN review_at TEXT;
ALTER TABLE campus_kb ADD COLUMN updated_at TEXT;
ALTER TABLE campus_kb ADD COLUMN updated_by INTEGER;
CREATE TABLE IF NOT EXISTS campus_kb_versions(id INTEGER PRIMARY KEY, kb_id INTEGER NOT NULL, version INTEGER NOT NULL,
  heading TEXT NOT NULL, text TEXT NOT NULL, request TEXT, action_label TEXT, source TEXT, source_ref TEXT, review_at TEXT,
  status TEXT NOT NULL, changed_by INTEGER, changed_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS idx_kb_versions ON campus_kb_versions(kb_id, version);
