-- Checkpoint D (TM-21, TM-19): the exam's log is append-only in the database too, so a mistaken UPDATE or DELETE fails
-- at once instead of breaking the chain silently (someone with the database file can still drop the triggers: the
-- e-mailed root is the real guard). The roster keeps the group a student was in when it was drawn, so a later move to
-- another group neither unlocks a closed statement nor moves the student out of it.
CREATE TRIGGER IF NOT EXISTS exam_events_no_update BEFORE UPDATE ON exam_events
BEGIN SELECT RAISE(ABORT, 'exam_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS exam_events_no_delete BEFORE DELETE ON exam_events
BEGIN SELECT RAISE(ABORT, 'exam_events is append-only'); END;
ALTER TABLE exam_roster ADD COLUMN group_id INTEGER;
