-- Task 15, slice 2: courses are managed and deactivated (a course row of a term is its offering), teaching units,
-- enrolments with a group, subgroup and dates, and the students' status orders.
ALTER TABLE courses ADD COLUMN active INTEGER NOT NULL DEFAULT 1;
ALTER TABLE courses ADD COLUMN created_at TEXT;
ALTER TABLE courses ADD COLUMN updated_at TEXT;
CREATE INDEX IF NOT EXISTS idx_courses_term ON courses(term_id);

-- A lecture, seminar or laboratory of a course, with its teacher and optional subgroup, for one or more groups.
CREATE TABLE IF NOT EXISTS teaching_units(id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL, kind TEXT NOT NULL,
  teacher_id INTEGER, subgroup INTEGER, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_teaching_units_course ON teaching_units(course_id);
CREATE TABLE IF NOT EXISTS teaching_unit_groups(unit_id INTEGER NOT NULL, group_id INTEGER NOT NULL, PRIMARY KEY(unit_id, group_id));

-- group_id NULL: the student's own group. begin_date / end_date (OneRoster beginDate / endDate): the enrolment counts for
-- lessons on days d with begin_date <= d < end_date; an ended enrolment keeps its attendance and grades.
ALTER TABLE enrollments ADD COLUMN group_id INTEGER;
ALTER TABLE enrollments ADD COLUMN subgroup INTEGER;
ALTER TABLE enrollments ADD COLUMN begin_date TEXT;
ALTER TABLE enrollments ADD COLUMN end_date TEXT;

-- Status orders: rows are only added; a correction is a new event whose note gives the reason. reported_at is set when
-- the event is sent to an outside register (later tasks), the only column that may change.
CREATE TABLE IF NOT EXISTS student_status_events(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, kind TEXT NOT NULL,
  order_no TEXT NOT NULL, order_date TEXT NOT NULL, effective_date TEXT NOT NULL, from_group_id INTEGER, to_group_id INTEGER,
  note TEXT, entered_by INTEGER NOT NULL, created_at TEXT NOT NULL, reported_at TEXT);
CREATE INDEX IF NOT EXISTS idx_status_events_student ON student_status_events(student_id, effective_date);
CREATE TRIGGER IF NOT EXISTS status_events_no_delete BEFORE DELETE ON student_status_events
BEGIN SELECT RAISE(ABORT, 'student_status_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS status_events_no_update BEFORE UPDATE OF id, student_id, kind, order_no, order_date,
  effective_date, from_group_id, to_group_id, note, entered_by, created_at ON student_status_events
BEGIN SELECT RAISE(ABORT, 'student_status_events is append-only'); END;
