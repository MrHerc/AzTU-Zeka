-- Task 22, slice 2: a material keeps its original file; a new version replaces it for students and the tutor, the old
-- version's file and text stay for the teacher.
ALTER TABLE materials ADD COLUMN file_id INTEGER;
ALTER TABLE materials ADD COLUMN replaces_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_materials_replaces ON materials(replaces_id);
CREATE INDEX IF NOT EXISTS idx_materials_file ON materials(file_id);
