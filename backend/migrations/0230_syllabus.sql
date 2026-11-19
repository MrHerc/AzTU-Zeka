-- Task 23: the structured syllabus. Each save is a new version (validated JSON, modules/syllabus/domain.py); a version
-- is never changed afterwards. `status` follows the approval chain of Task 25: draft, submitted, approved, published,
-- returned. The old one-row-per-course `syllabi` table stays readable: a course with no version starts from it.
CREATE TABLE IF NOT EXISTS syllabus_versions(id INTEGER PRIMARY KEY AUTOINCREMENT, course_id INTEGER NOT NULL, version INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft', data TEXT NOT NULL, author_id INTEGER, created_at TEXT NOT NULL,
  note TEXT, decided_by INTEGER, decided_at TEXT, UNIQUE(course_id, version));
CREATE INDEX IF NOT EXISTS idx_syllabus_status ON syllabus_versions(course_id, status);
