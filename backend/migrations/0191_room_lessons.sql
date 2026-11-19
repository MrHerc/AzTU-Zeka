-- Checkpoint C (R1): the page behind a room's QR code shows the room's lessons (not its weekly rows), so a cancelled,
-- moved or deactivated lesson and other terms' rows are not shown on the door.
CREATE INDEX IF NOT EXISTS idx_lessons_room_day ON lessons(room_id, day);
