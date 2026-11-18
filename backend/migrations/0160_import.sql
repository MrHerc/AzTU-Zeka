-- Task 16: bulk import. A row that came from an outside system is linked to it only here; imported tables get no
-- source columns. source_hash is the hash of the imported fields as written: a row whose fields hash differently now was
-- changed in Zəka after the import, and a later import does not overwrite it (a conflict) unless --prefer source.
CREATE TABLE IF NOT EXISTS import_links(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, source_system TEXT NOT NULL,
  source_id TEXT NOT NULL, row_id INTEGER NOT NULL, source_hash TEXT NOT NULL, imported_at TEXT NOT NULL,
  UNIQUE(kind, source_system, source_id));
CREATE INDEX IF NOT EXISTS idx_import_links_row ON import_links(kind, row_id);

-- One-time activation codes for students: 60 random bits, only the SHA-256 is kept, accepted only together with the
-- student number they were issued for. A new batch for a faculty revokes the unused codes of the old one.
CREATE TABLE IF NOT EXISTS activation_codes(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, code_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL, expires_at TEXT NOT NULL, used_at TEXT, revoked_at TEXT);
CREATE INDEX IF NOT EXISTS idx_activation_codes_user ON activation_codes(user_id);

-- Forma №3 (docs/forms/forma-3.md): contact hours and students of a teaching unit; fractional hours stay as they are.
ALTER TABLE teaching_units ADD COLUMN hours REAL;
ALTER TABLE teaching_units ADD COLUMN students INTEGER;
