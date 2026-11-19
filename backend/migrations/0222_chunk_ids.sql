-- Checkpoint C (L2): a section id is never given again. Without AUTOINCREMENT a new material (or a new version) could
-- take the ids of deleted sections, and an old tutor answer or question would then cite the new text.
CREATE TABLE chunks_new(id INTEGER PRIMARY KEY AUTOINCREMENT, material_id INT, course_id INT, seq INT, heading TEXT, text TEXT);
INSERT INTO chunks_new(id, material_id, course_id, seq, heading, text) SELECT id, material_id, course_id, seq, heading, text FROM chunks;
DROP TABLE chunks;
ALTER TABLE chunks_new RENAME TO chunks;
CREATE INDEX IF NOT EXISTS idx_chunks_material ON chunks(material_id);
