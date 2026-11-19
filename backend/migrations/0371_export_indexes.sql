-- Task 37, exports: `--since` reads only what was written or changed after a moment (attendance by marked_at, grades by
-- updated_at, both the university's naive wall clock), and the "Tələbə-məzun" change list reads the status orders
-- entered after a moment (created_at). Without these each would read its whole table.
CREATE INDEX IF NOT EXISTS idx_attendance_marked_at ON attendance(marked_at);
CREATE INDEX IF NOT EXISTS idx_grades_updated_at ON grades(updated_at);
CREATE INDEX IF NOT EXISTS idx_status_events_created ON student_status_events(created_at);
