-- Task 19: timetable rows of teaching units, the lessons made from them, and per-user calendar feeds.
-- A row repeats weekly in the teaching period of its course's term: every week, or odd or even weeks (week 1 is the
-- week of the term's first teaching day). Kind and teacher come from the unit; `academic_hours` is copied to its lessons.
ALTER TABLE timetable ADD COLUMN unit_id INTEGER;
ALTER TABLE timetable ADD COLUMN academic_hours INTEGER;
ALTER TABLE timetable ADD COLUMN weeks TEXT NOT NULL DEFAULT 'all';
ALTER TABLE timetable ADD COLUMN active INTEGER NOT NULL DEFAULT 1;
ALTER TABLE timetable ADD COLUMN updated_at TEXT;
CREATE INDEX IF NOT EXISTS idx_timetable_unit ON timetable(unit_id);
CREATE INDEX IF NOT EXISTS idx_timetable_weekday ON timetable(weekday, start);
-- A lesson keeps the slot it was made for (slot_day, slot_start): making the lessons again finds it there even after it
-- was moved to another day or time, so a unit has at most one lesson per slot.
ALTER TABLE lessons ADD COLUMN unit_id INTEGER;
ALTER TABLE lessons ADD COLUMN teacher_id INTEGER;
ALTER TABLE lessons ADD COLUMN academic_hours INTEGER;
ALTER TABLE lessons ADD COLUMN timetable_id INTEGER;
ALTER TABLE lessons ADD COLUMN room_id INTEGER;
ALTER TABLE lessons ADD COLUMN slot_day TEXT;
ALTER TABLE lessons ADD COLUMN slot_start TEXT;
ALTER TABLE lessons ADD COLUMN status TEXT NOT NULL DEFAULT 'scheduled';
ALTER TABLE lessons ADD COLUMN note TEXT;
ALTER TABLE lessons ADD COLUMN updated_at TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_lessons_slot ON lessons(unit_id, slot_day, slot_start) WHERE unit_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_lessons_day ON lessons(day, start);
CREATE INDEX IF NOT EXISTS idx_lessons_teacher_day ON lessons(teacher_id, day);
CREATE INDEX IF NOT EXISTS idx_lessons_timetable ON lessons(timetable_id, day);
CREATE INDEX IF NOT EXISTS idx_unit_groups_group ON teaching_unit_groups(group_id);    -- a group's timetable and lessons
-- A calendar feed is a secret URL: only its SHA-256 is kept; a new one replaces the old, deleting it revokes the feed.
CREATE TABLE IF NOT EXISTS ical_feeds(user_id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ical_feeds_token ON ical_feeds(token_hash);
