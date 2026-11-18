-- Task 15, slice 1: the university's structure and its terms. Rows are deactivated, never deleted (history stays).
CREATE TABLE IF NOT EXISTS faculties(id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS departments(id INTEGER PRIMARY KEY, faculty_id INTEGER NOT NULL, code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_departments_faculty ON departments(faculty_id);
CREATE TABLE IF NOT EXISTS specialties(id INTEGER PRIMARY KEY, faculty_id INTEGER NOT NULL, department_id INTEGER,
  code TEXT NOT NULL UNIQUE, name TEXT NOT NULL, degree TEXT NOT NULL DEFAULT 'bachelor',
  active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_specialties_faculty ON specialties(faculty_id);
-- A term keeps its teaching period and its exam session apart: teaching_end < exam_start.
CREATE TABLE IF NOT EXISTS academic_terms(id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  teaching_start TEXT NOT NULL, teaching_end TEXT NOT NULL, exam_start TEXT NOT NULL, exam_end TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
-- Existing rows are linked to the structure (NULL until set; the demo seed links them).
ALTER TABLE study_groups ADD COLUMN faculty_id INTEGER;
ALTER TABLE study_groups ADD COLUMN specialty_id INTEGER;
ALTER TABLE study_groups ADD COLUMN active INTEGER NOT NULL DEFAULT 1;
CREATE INDEX IF NOT EXISTS idx_study_groups_faculty ON study_groups(faculty_id);
ALTER TABLE courses ADD COLUMN department_id INTEGER;
ALTER TABLE courses ADD COLUMN term_id INTEGER;
ALTER TABLE users ADD COLUMN department_id INTEGER;
