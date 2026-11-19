-- Task 29: the proctor panel. A proctor is assigned to an exam (any staff member; the course's teachers and the academic
-- office reach the board without it). A paused attempt keeps its deadline frozen from paused_at; resuming moves the
-- deadline by the pause. The board reads the exam sessions by scope and a student's events by (exam, student).
CREATE TABLE IF NOT EXISTS exam_proctors(exam_id INTEGER NOT NULL, user_id INTEGER NOT NULL, added_by INTEGER, added_at TEXT NOT NULL,
  PRIMARY KEY(exam_id, user_id));
CREATE INDEX IF NOT EXISTS idx_exam_proctors_user ON exam_proctors(user_id);
ALTER TABLE exam_attempts ADD COLUMN paused_at TEXT;
CREATE INDEX IF NOT EXISTS idx_sessions_scope ON sessions(scope);
CREATE INDEX IF NOT EXISTS idx_exam_events_student ON exam_events(exam_id, student_id, kind);
CREATE INDEX IF NOT EXISTS idx_exams_status ON exams(status);
