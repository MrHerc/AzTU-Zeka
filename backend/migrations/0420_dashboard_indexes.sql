-- Task 42: the leadership dashboard (/api/analytics) reads each course's finished quiz attempts; without this index every
-- course scanned the whole attempts table (13 s on the university dataset, tools/queryplan.py, docs/perf/task42.md).
CREATE INDEX IF NOT EXISTS idx_attempts_quiz_finished ON attempts(quiz_id, finished_at);
