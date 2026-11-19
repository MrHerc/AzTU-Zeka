-- Task 34: a teacher's weekly office hours (a weekday, a time range cut into slots, a room or an online link) and the
-- students' bookings of single slots. A slot is booked at most once: the partial unique index makes the second of two
-- simultaneous bookings fail in the database, whatever the workers do.
CREATE TABLE IF NOT EXISTS office_hours(id INTEGER PRIMARY KEY, teacher_id INTEGER NOT NULL, weekday INTEGER NOT NULL, start TEXT NOT NULL,
  end TEXT NOT NULL, slot_min INTEGER NOT NULL, place TEXT, online_url TEXT, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_office_hours_teacher ON office_hours(teacher_id, active);
CREATE TABLE IF NOT EXISTS office_bookings(id INTEGER PRIMARY KEY, hours_id INTEGER NOT NULL, teacher_id INTEGER NOT NULL,
  student_id INTEGER NOT NULL, day TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, topic TEXT, status TEXT NOT NULL DEFAULT 'booked',
  created_at TEXT NOT NULL, cancelled_at TEXT, cancelled_by INTEGER);
CREATE UNIQUE INDEX IF NOT EXISTS idx_office_bookings_slot ON office_bookings(teacher_id, day, start) WHERE status='booked';
CREATE INDEX IF NOT EXISTS idx_office_bookings_student ON office_bookings(student_id, day);
CREATE INDEX IF NOT EXISTS idx_office_bookings_day ON office_bookings(status, day, start);
