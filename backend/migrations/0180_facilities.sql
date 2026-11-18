-- Task 18: buildings, rooms and the room a timetable row is in.
-- A room code is unique across the university (it is the room's URL, /r/<code>, printed as a QR code); `number` is what
-- the door says, so two buildings can both have a room 101. The floor is a number of the room, not a table of its own.
CREATE TABLE IF NOT EXISTS buildings(id INTEGER PRIMARY KEY, code TEXT NOT NULL, name TEXT NOT NULL, address TEXT,
  active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS idx_buildings_code ON buildings(code);
CREATE TABLE IF NOT EXISTS rooms(id INTEGER PRIMARY KEY, building_id INTEGER NOT NULL, code TEXT NOT NULL, number TEXT NOT NULL,
  name TEXT, floor INTEGER, kind TEXT NOT NULL, capacity INTEGER, accessible INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rooms_code ON rooms(code);
CREATE INDEX IF NOT EXISTS idx_rooms_building ON rooms(building_id);
-- `room` keeps the text the timetable was entered with; `room_id` is set when that text names a room
ALTER TABLE timetable ADD COLUMN room_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_timetable_room ON timetable(room_id, weekday, start);
