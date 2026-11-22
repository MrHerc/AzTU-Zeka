-- Task 48: the outcome of each writing Forma №3 import (today it is shown once and lost, so held-back units are
-- invisible). File cells and codes only, never a name or a cell's text.
CREATE TABLE IF NOT EXISTS forma3_imports(id INTEGER PRIMARY KEY, term_id INTEGER, department_id INTEGER NOT NULL,
  filename TEXT NOT NULL, sha256 TEXT NOT NULL, units_written INTEGER NOT NULL, hours_written REAL NOT NULL,
  held_back TEXT NOT NULL,                  -- JSON [{anchor, code, blocking, message_key}]: units not written, with the cell
  posts_blocked TEXT NOT NULL,              -- JSON [{ref, code}]
  vacancies INTEGER NOT NULL, vacancy_hours REAL NOT NULL, hidden_sheets INTEGER NOT NULL,
  imported_by INTEGER, imported_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_forma3_imports_term ON forma3_imports(term_id, department_id, id);
