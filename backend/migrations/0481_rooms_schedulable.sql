-- Task 48: rooms the timetable builder may use. schedulable 0: an office or a closed room; dedicated 1: only the units
-- that list the room in tt_unit_needs.room_ids.
ALTER TABLE rooms ADD COLUMN schedulable INTEGER NOT NULL DEFAULT 1;
ALTER TABLE rooms ADD COLUMN dedicated INTEGER NOT NULL DEFAULT 0;
