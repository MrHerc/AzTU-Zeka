-- Task 23 (the measurement of 2026-11-24): the syllabus editor looks a prerequisite up by the start of a course's code or
-- name (/api/syllabi/{id}/prerequisites) through index ranges; the code has its index since 0231, the name gets one here.
CREATE INDEX IF NOT EXISTS idx_courses_name ON courses(name);
