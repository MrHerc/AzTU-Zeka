-- Checkpoint E (SEC-E1, SEC-E3): a question a student forwards from the tutor was the teacher's alone before Task 33
-- and stays so: only its author and the course's teachers read it, and an anonymous one hides the name from the teacher
-- too, as the tutor promises. A row posted in the forum has an audited qa_topic ("<code> #<id>"); every other row is a
-- forward, so it becomes private (fail closed).
ALTER TABLE teacher_questions ADD COLUMN private INTEGER NOT NULL DEFAULT 0;
UPDATE teacher_questions SET private = 1
  WHERE id NOT IN (SELECT CAST(substr(detail, instr(detail, '#') + 1) AS INTEGER) FROM audit WHERE action = 'qa_topic');
-- AR-E4: the teacher's question badge (polled every 30 s) and list find the teacher's courses by an index.
CREATE INDEX IF NOT EXISTS idx_courses_teacher ON courses(teacher_id);
