-- Task 21: the grade journal. A score is a draft until the teacher publishes it (rows written before this migration
-- were already shown, so they are published); an imported score is 'legacy' with the import's date and reason.
ALTER TABLE grades ADD COLUMN status TEXT NOT NULL DEFAULT 'published';
ALTER TABLE grades ADD COLUMN source TEXT NOT NULL DEFAULT 'zeka';
ALTER TABLE grades ADD COLUMN as_of TEXT;
ALTER TABLE grades ADD COLUMN entered_by INTEGER;
ALTER TABLE grades ADD COLUMN reason TEXT;
-- the exam component's score names its exam and attempt (Task 30 writes them)
ALTER TABLE grades ADD COLUMN exam_id INTEGER;
ALTER TABLE grades ADD COLUMN attempt_no INTEGER;
-- every change of a published score: who, old and new value, why
CREATE TABLE IF NOT EXISTS grade_changes(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, course_id INTEGER NOT NULL,
  component TEXT NOT NULL, old_score REAL, new_score REAL, changed_by INTEGER, reason TEXT NOT NULL, changed_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_grade_changes_course ON grade_changes(course_id, changed_at);
-- A final grade: one per student, course and term, with the names and credits it was given under, so a transcript is
-- built from these rows only. A row of a term before Zəka (imported history) has no course_id.
CREATE TABLE IF NOT EXISTS final_grades(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, course_id INTEGER, term_id INTEGER,
  term_name TEXT NOT NULL, term_name_en TEXT, term_start TEXT, course_code TEXT, course_name TEXT NOT NULL, course_name_en TEXT,
  credits INTEGER NOT NULL, score REAL NOT NULL, letter TEXT NOT NULL, passed INTEGER NOT NULL, source TEXT NOT NULL DEFAULT 'zeka',
  published_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS idx_final_course ON final_grades(user_id, course_id) WHERE course_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_final_user ON final_grades(user_id, term_start);
CREATE INDEX IF NOT EXISTS idx_final_failed ON final_grades(passed, course_id);
-- when the dean's office checked the student's history before Zəka; until then no transcript is issued
ALTER TABLE users ADD COLUMN history_reconciled_at TEXT;
