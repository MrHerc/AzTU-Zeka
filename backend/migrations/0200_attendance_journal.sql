-- Task 20: the attendance journal. A row says who wrote it and when; `source` is 'zeka' or 'legacy' (a lesson-level row
-- imported for a lesson before the cut-over date, Task 38), with the import's `as_of`.
ALTER TABLE attendance ADD COLUMN source TEXT NOT NULL DEFAULT 'zeka';
ALTER TABLE attendance ADD COLUMN as_of TEXT;
ALTER TABLE attendance ADD COLUMN marked_by INTEGER;
ALTER TABLE attendance ADD COLUMN marked_at TEXT;
-- An opening balance: the hours held, missed without and with an excuse up to `as_of`, per student, course and term,
-- for a term that started before Zəka. It is not a lesson record: it changes only by importing the same source row again
-- or by a department head's correction with a reason.
CREATE TABLE IF NOT EXISTS attendance_opening(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, course_id INTEGER NOT NULL,
  term_id INTEGER NOT NULL, held_hours INTEGER NOT NULL, unexcused_hours INTEGER NOT NULL, excused_hours INTEGER NOT NULL,
  as_of TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS idx_opening_student ON attendance_opening(student_id, course_id, term_id);
CREATE INDEX IF NOT EXISTS idx_opening_course ON attendance_opening(course_id, term_id);
-- the limit of a published syllabus (percent; Task 25 writes it); empty: the university's limit applies
ALTER TABLE courses ADD COLUMN attendance_limit REAL;
