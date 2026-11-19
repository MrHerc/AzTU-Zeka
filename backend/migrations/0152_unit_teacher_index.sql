-- Checkpoint C (P6): a teacher's courses include those of the teaching units the teacher holds.
CREATE INDEX IF NOT EXISTS idx_teaching_units_teacher ON teaching_units(teacher_id, course_id);
