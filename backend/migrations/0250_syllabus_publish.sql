-- Task 25: the approval chain of a syllabus version and what its publication configures. Each step of the chain is a
-- row (who, when, the comment); a published syllabus writes the course's grading scheme (its components and exam, in
-- the university's format), its attendance limit (courses.attendance_limit, Task 20) and its tutor modes.
CREATE TABLE IF NOT EXISTS syllabus_steps(id INTEGER PRIMARY KEY AUTOINCREMENT, version_id INTEGER NOT NULL, action TEXT NOT NULL,
  user_id INTEGER NOT NULL, note TEXT, at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_syllabus_steps_version ON syllabus_steps(version_id);
CREATE INDEX IF NOT EXISTS idx_syllabus_versions_status ON syllabus_versions(status);
ALTER TABLE courses ADD COLUMN grading TEXT;
