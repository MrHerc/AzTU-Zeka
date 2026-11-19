-- Checkpoint E (AR-E5): a person's bookings as student OR teacher (the calendar feed, the bookings page) read through
-- an index on each side; the teacher side had none, so every feed scanned office_bookings.
CREATE INDEX IF NOT EXISTS idx_office_bookings_teacher ON office_bookings(teacher_id, day);
