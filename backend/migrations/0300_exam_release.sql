-- Task 30: the closing protocol (a QR document, its root in the document and in the e-mail) is linked from the exam;
-- after the teacher releases the results, the dean's office closes each group's statement (a QR document), and from
-- then on only the office changes an exam score in the journal. The chain columns came with 0260.
ALTER TABLE exams ADD COLUMN protocol_id INTEGER;
CREATE TABLE IF NOT EXISTS exam_statements(exam_id INTEGER NOT NULL, group_id INTEGER NOT NULL, document_id INTEGER NOT NULL,
  closed_by INTEGER NOT NULL, closed_at TEXT NOT NULL, PRIMARY KEY(exam_id, group_id));
CREATE INDEX IF NOT EXISTS idx_grades_exam ON grades(exam_id) WHERE exam_id IS NOT NULL;
