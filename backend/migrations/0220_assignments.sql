-- Task 22, slice 1: assignments of a course and the students' submissions. A graded submission's score goes to the
-- assignment's grade component (the sum of that component's graded assignments, never above its maximum).
CREATE TABLE IF NOT EXISTS assignments(id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
  due_at TEXT NOT NULL, max_score REAL NOT NULL, component TEXT NOT NULL, late_rule TEXT NOT NULL, created_by INTEGER NOT NULL,
  active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_assignments_course ON assignments(course_id, due_at);
CREATE TABLE IF NOT EXISTS submissions(id INTEGER PRIMARY KEY, assignment_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
  text TEXT, file_id INTEGER, submitted_at TEXT NOT NULL, late INTEGER NOT NULL DEFAULT 0, score REAL, feedback TEXT,
  graded_by INTEGER, graded_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS idx_submissions_student ON submissions(assignment_id, student_id);
CREATE INDEX IF NOT EXISTS idx_submissions_file ON submissions(file_id);
