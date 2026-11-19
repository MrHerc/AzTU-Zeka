-- Checkpoint C (P3): a course's grade table reads its grades by course; the primary key starts with the student.
CREATE INDEX IF NOT EXISTS idx_grades_course ON grades(course_id, user_id);
-- and the academic debts (P5) are the final grades that did not pass
CREATE INDEX IF NOT EXISTS idx_finals_failed ON final_grades(user_id) WHERE passed=0;
