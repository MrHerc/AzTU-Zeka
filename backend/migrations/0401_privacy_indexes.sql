-- Task 40, Checkpoint F (AR-F4): the person's export (GET /api/me/export) and an approved erasure (identity/repo.erase,
-- inside the decider's write transaction) read every person column of identity/repo.INVENTORY and the VIA links. Without
-- these indexes each of about 20 tables was read whole, on a university's data for seconds under the write lock.
-- tests/integration/test_privacy.py explains every statement of both and fails on a scan.
CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_news_reads_user ON news_reads(user_id);
CREATE INDEX IF NOT EXISTS idx_news_rsvp_user ON news_rsvp(user_id);
CREATE INDEX IF NOT EXISTS idx_news_saved_user ON news_saved(user_id);
CREATE INDEX IF NOT EXISTS idx_outbox_user ON outbox(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_holder ON documents(holder_id);
CREATE INDEX IF NOT EXISTS idx_files_owner ON files(owner_id);
CREATE INDEX IF NOT EXISTS idx_request_events_request ON request_events(request_id);
CREATE INDEX IF NOT EXISTS idx_request_messages_request ON request_messages(request_id);
CREATE INDEX IF NOT EXISTS idx_request_messages_author ON request_messages(author_id);
CREATE INDEX IF NOT EXISTS idx_support_messages_ticket ON support_messages(ticket_id);
CREATE INDEX IF NOT EXISTS idx_support_messages_author ON support_messages(author_id);
CREATE INDEX IF NOT EXISTS idx_exam_attempts_student ON exam_attempts(student_id);
CREATE INDEX IF NOT EXISTS idx_exam_roster_student ON exam_roster(student_id);
CREATE INDEX IF NOT EXISTS idx_submissions_student_id ON submissions(student_id);
CREATE INDEX IF NOT EXISTS idx_grade_changes_user ON grade_changes(user_id);
CREATE INDEX IF NOT EXISTS idx_tq_student ON teacher_questions(student_id);
CREATE INDEX IF NOT EXISTS idx_feedback_user ON feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_doc_keys_user ON doc_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_qa_replies_author ON qa_replies(author_id);
CREATE INDEX IF NOT EXISTS idx_qa_reports_reporter ON qa_reports(reporter_id);
CREATE INDEX IF NOT EXISTS idx_qa_reports_topic ON qa_reports(topic_id);
CREATE INDEX IF NOT EXISTS idx_qa_reports_reply ON qa_reports(reply_id);
CREATE INDEX IF NOT EXISTS idx_club_messages_author ON club_messages(author_id);
CREATE INDEX IF NOT EXISTS idx_club_reports_reporter ON club_reports(reporter_id);
CREATE INDEX IF NOT EXISTS idx_clubs_leader ON clubs(leader_id);
CREATE INDEX IF NOT EXISTS idx_sso_pending_link_user ON sso_pending(link_user_id);
