-- Task 38: every file a migration wave loaded. The reconciliation reads these files again (their SHA-256 must not have
-- changed) and compares each row with what Zəka holds now; source_sha256 is the old system's export file it came from.
CREATE TABLE IF NOT EXISTS migration_files(id INTEGER PRIMARY KEY, wave INTEGER NOT NULL, source TEXT NOT NULL, kind TEXT NOT NULL,
  filename TEXT NOT NULL, sha256 TEXT NOT NULL, source_file TEXT, source_sha256 TEXT, rows INTEGER NOT NULL, as_of TEXT,
  exported_at TEXT, imported_at TEXT NOT NULL, imported_by INTEGER);
CREATE INDEX IF NOT EXISTS idx_migration_files_wave ON migration_files(wave, source, id);
