-- Task 33: a student's question to the teacher is a topic of the course's forum. A topic has a title, a week or topic
-- tag, replies (one of them the teacher's accepted answer), a draft the AI writes from the course's materials for the
-- teacher only, a link to the FAQ chunk the tutor cites once the teacher moves it to the course's FAQ, and reports that
-- reach the moderators. The single answer kept before becomes the topic's accepted reply by the course's teacher.
ALTER TABLE teacher_questions ADD COLUMN title TEXT;
ALTER TABLE teacher_questions ADD COLUMN tag TEXT;
ALTER TABLE teacher_questions ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0;
ALTER TABLE teacher_questions ADD COLUMN faq_chunk_id INTEGER;
ALTER TABLE teacher_questions ADD COLUMN ai_draft TEXT;
ALTER TABLE teacher_questions ADD COLUMN updated_at TEXT;
CREATE INDEX IF NOT EXISTS idx_tq_course ON teacher_questions(course_id, id);
CREATE TABLE IF NOT EXISTS qa_replies(id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL, author_id INTEGER NOT NULL, text TEXT NOT NULL,
  accepted INTEGER NOT NULL DEFAULT 0, hidden INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_qa_replies_topic ON qa_replies(topic_id, id);
CREATE TABLE IF NOT EXISTS qa_reports(id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL, reply_id INTEGER, reporter_id INTEGER NOT NULL,
  reason TEXT NOT NULL, created_at TEXT NOT NULL, resolved_at TEXT, resolved_by INTEGER, outcome TEXT);
CREATE INDEX IF NOT EXISTS idx_qa_reports_open ON qa_reports(resolved_at, id);
UPDATE teacher_questions SET title = substr(question, 1, 80) WHERE title IS NULL;
INSERT INTO qa_replies(topic_id, author_id, text, accepted, created_at)
  SELECT tq.id, co.teacher_id, tq.answer, 1, COALESCE(tq.answered_at, tq.created_at) FROM teacher_questions tq
  JOIN courses co ON co.id=tq.course_id WHERE tq.answer IS NOT NULL AND tq.answer<>'' AND co.teacher_id IS NOT NULL;
