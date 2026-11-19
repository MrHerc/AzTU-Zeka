-- Task 26: the exam core. A question's purpose (practice or exam) is chosen when it is first approved and never
-- changes; an exam question reaches a student only inside that student's own attempt. An exam's roster is drawn once,
-- when it opens. A student's form (questions and option order) is made from a seed and never changes. Times are
-- aware UTC (clock.now). exam_events is append-only; Task 30 computes its hash chain (seq, prev_hash, hash).
ALTER TABLE questions ADD COLUMN purpose TEXT NOT NULL DEFAULT 'practice';
CREATE TABLE IF NOT EXISTS exams(id INTEGER PRIMARY KEY AUTOINCREMENT, course_id INTEGER NOT NULL, kind TEXT NOT NULL DEFAULT 'main',
  title TEXT NOT NULL, opens_at TEXT NOT NULL, closes_at TEXT NOT NULL, duration_min INTEGER NOT NULL, plan TEXT NOT NULL,
  protection TEXT NOT NULL DEFAULT 'open', allowed_cidrs TEXT, status TEXT NOT NULL DEFAULT 'draft', attempt_no INTEGER NOT NULL DEFAULT 1,
  secret TEXT NOT NULL, created_by INTEGER, created_at TEXT NOT NULL, opened_at TEXT, closed_at TEXT);
CREATE INDEX IF NOT EXISTS idx_exams_course ON exams(course_id);
CREATE TABLE IF NOT EXISTS exam_roster(exam_id INTEGER NOT NULL, student_id INTEGER NOT NULL, status TEXT NOT NULL, reason TEXT,
  added_by INTEGER, added_at TEXT NOT NULL, PRIMARY KEY(exam_id, student_id));
CREATE TABLE IF NOT EXISTS exam_forms(exam_id INTEGER NOT NULL, student_id INTEGER NOT NULL, seed TEXT NOT NULL, items TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY(exam_id, student_id));
CREATE TABLE IF NOT EXISTS exam_attempts(id INTEGER PRIMARY KEY AUTOINCREMENT, exam_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
  started_at TEXT NOT NULL, deadline_at TEXT NOT NULL, submitted_at TEXT, auto INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'in_progress',
  score REAL, max_score REAL, UNIQUE(exam_id, student_id));
CREATE INDEX IF NOT EXISTS idx_exam_attempts_due ON exam_attempts(status, deadline_at);
CREATE TABLE IF NOT EXISTS exam_answers(attempt_id INTEGER NOT NULL, qid INTEGER NOT NULL, value TEXT, saved_at TEXT NOT NULL,
  PRIMARY KEY(attempt_id, qid));
CREATE TABLE IF NOT EXISTS exam_events(id INTEGER PRIMARY KEY AUTOINCREMENT, exam_id INTEGER NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL,
  actor_id INTEGER, student_id INTEGER, data TEXT, at TEXT NOT NULL, prev_hash TEXT, hash TEXT, UNIQUE(exam_id, seq));
