-- Task 23 (the audit of 2026-11-23): a prerequisite is a course of the registry, kept by its code, and a draft can start
-- from another course's published syllabus. A course's code is looked up (a prerequisite's name, the earlier offerings
-- of the same course); a version copied from another syllabus keeps its source as JSON: {course_id, code, name, term,
-- version}.
CREATE INDEX IF NOT EXISTS idx_courses_code ON courses(code);
ALTER TABLE syllabus_versions ADD COLUMN source TEXT;
