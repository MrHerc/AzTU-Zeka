-- Task 47: a teaching unit read from Forma №3 keeps how it is paid, whether it is vacant load, and where it stands in
-- the department's file, so the dean's office can find the cell it came from.
--   pay        staff | hourly (a "saat hesabı" block or section); NULL for a unit not read from the form
--   vacancy    1: unassigned load of a vacancy (teacher_id is NULL on purpose, not a missing teacher)
--   post_ref   the staff line or section label of the post: "#0!A21"
--   anchor     the top-left hour cell of the class: "#12!G30"
ALTER TABLE teaching_units ADD COLUMN pay TEXT;
ALTER TABLE teaching_units ADD COLUMN vacancy INTEGER NOT NULL DEFAULT 0;
ALTER TABLE teaching_units ADD COLUMN post_ref TEXT;
ALTER TABLE teaching_units ADD COLUMN anchor TEXT;
