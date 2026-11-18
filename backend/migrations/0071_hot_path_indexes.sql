-- Task 7 (dilim 2): indexes for the hot read paths. tools/queryplan.py lists every full scan of a table with more than
-- 1 000 rows on the read routes of the university dataset; tests/load/test_query_plans.py keeps that list empty.
CREATE INDEX IF NOT EXISTS idx_attempts_user_quiz ON attempts(user_id, quiz_id);
CREATE INDEX IF NOT EXISTS idx_timetable_course ON timetable(course_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_course ON enrollments(course_id);
CREATE INDEX IF NOT EXISTS idx_quizzes_course ON quizzes(course_id);
CREATE INDEX IF NOT EXISTS idx_materials_course ON materials(course_id);
CREATE INDEX IF NOT EXISTS idx_lessons_course ON lessons(course_id);
