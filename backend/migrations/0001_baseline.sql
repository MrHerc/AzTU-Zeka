-- 0001: baseline. The schema of the demo at SCHEMA_VERSION 4 (main + the five merged PRs).
-- Never edit an applied migration: add a new file (tasks/todo.md, Task 4).
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS study_groups(id INTEGER PRIMARY KEY, name TEXT, year INT);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, full_name TEXT, patronymic TEXT, role TEXT, title TEXT,
  group_id INT, color TEXT, consent_at TEXT, synthetic INT DEFAULT 0, student_no TEXT, admission_year INT, funding TEXT, form TEXT,
  dept TEXT, prefs TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS sessions(sid TEXT PRIMARY KEY, user_id INT, created_at TEXT);
CREATE TABLE IF NOT EXISTS courses(id INTEGER PRIMARY KEY, code TEXT, name TEXT, teacher_id INT, credits INT, color TEXT,
  description TEXT, suggestions TEXT, tutor_modes TEXT, tutor_rules TEXT, tutor_locked INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS enrollments(user_id INT, course_id INT, PRIMARY KEY(user_id, course_id));
CREATE TABLE IF NOT EXISTS timetable(id INTEGER PRIMARY KEY, course_id INT, weekday INT, start TEXT, end TEXT, kind TEXT, room TEXT);
CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY, course_id INT, day TEXT, start TEXT, end TEXT, kind TEXT, room TEXT, topic TEXT);
CREATE TABLE IF NOT EXISTS attendance(lesson_id INT, user_id INT, status TEXT, request_id INT, PRIMARY KEY(lesson_id, user_id));
CREATE TABLE IF NOT EXISTS grades(user_id INT, course_id INT, component TEXT, score REAL, max REAL, updated_at TEXT,
  PRIMARY KEY(user_id, course_id, component));
CREATE TABLE IF NOT EXISTS materials(id INTEGER PRIMARY KEY, course_id INT, title TEXT, filename TEXT, text TEXT,
  chunk_count INT, term_count INT, uploaded_by INT, created_at TEXT);
CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY, material_id INT, course_id INT, seq INT, heading TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS campus_kb(id INTEGER PRIMARY KEY, heading TEXT, text TEXT, request TEXT, action_label TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, user_id INT, course_id INT, channel TEXT, role TEXT,
  content TEXT, cites TEXT, meta TEXT, rating INT, created_at TEXT, synthetic INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS teacher_questions(id INTEGER PRIMARY KEY, course_id INT, student_id INT, anonymous INT,
  question TEXT, context TEXT, answer TEXT, status TEXT, created_at TEXT, answered_at TEXT);
CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY, course_id INT, chunk_id INT, qtype TEXT, text TEXT,
  options TEXT, answer TEXT, unit TEXT, explanation TEXT, bloom TEXT, difficulty TEXT, topic TEXT, status TEXT,
  origin TEXT, flags TEXT, created_by INT, created_at TEXT);
CREATE TABLE IF NOT EXISTS quizzes(id INTEGER PRIMARY KEY, course_id INT, title TEXT, kind TEXT, question_ids TEXT,
  time_limit INT, attempts INT, show_explanations INT DEFAULT 1, published INT DEFAULT 1, created_at TEXT);
CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, quiz_id INT, user_id INT, answers TEXT, details TEXT,
  score REAL, max_score REAL, started_at TEXT, finished_at TEXT, synthetic INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS service_categories(key TEXT PRIMARY KEY, seq INT, name TEXT, icon TEXT, color TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS request_types(code TEXT PRIMARY KEY, seq INT, category TEXT, name TEXT, icon TEXT, sla_hours INT,
  document TEXT, document_en TEXT, prefix TEXT, description TEXT, needs TEXT, outcome TEXT, privacy TEXT, fields TEXT,
  attachments TEXT, steps TEXT, answer TEXT, popular INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY, type_code TEXT, student_id INT, data TEXT, status TEXT,
  step INT DEFAULT 0, created_at TEXT, updated_at TEXT, due_at TEXT, document_id INT, answer TEXT);
CREATE TABLE IF NOT EXISTS request_events(id INTEGER PRIMARY KEY, request_id INT, actor_id INT, action TEXT, note TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS request_messages(id INTEGER PRIMARY KEY, request_id INT, author_id INT, text TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY, owner_id INT, request_id INT, filename TEXT, mime TEXT, size INT,
  sha256 TEXT, path TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, kind TEXT, request_id INT, holder_id INT, title TEXT,
  reg_no TEXT UNIQUE, verify_code TEXT UNIQUE, data TEXT, hash TEXT, issued_by INT, issued_at TEXT, status TEXT,
  revoked_reason TEXT, revoked_at TEXT);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, user_id INT, kind TEXT, title TEXT, body TEXT, link TEXT,
  created_at TEXT, read_at TEXT);
CREATE TABLE IF NOT EXISTS news(id INTEGER PRIMARY KEY, kind TEXT, title TEXT, summary TEXT, body TEXT, cover TEXT,
  author_id INT, audience TEXT, pinned INT DEFAULT 0, important INT DEFAULT 0, published_at TEXT, event_start TEXT,
  event_end TEXT, location TEXT, capacity INT, registration INT DEFAULT 0, tags TEXT, status TEXT DEFAULT 'published');
CREATE TABLE IF NOT EXISTS news_rsvp(news_id INT, user_id INT, created_at TEXT, PRIMARY KEY(news_id, user_id));
CREATE TABLE IF NOT EXISTS news_saved(news_id INT, user_id INT, PRIMARY KEY(news_id, user_id));
CREATE TABLE IF NOT EXISTS news_reads(news_id INT, user_id INT, PRIMARY KEY(news_id, user_id));
CREATE TABLE IF NOT EXISTS academy_tracks(key TEXT PRIMARY KEY, seq INT, title TEXT, icon TEXT, color TEXT, level TEXT,
  audience TEXT, summary TEXT, outcomes TEXT);
CREATE TABLE IF NOT EXISTS academy_modules(id INTEGER PRIMARY KEY, track_key TEXT, seq INT, title TEXT, minutes INT,
  paragraphs TEXT, key_points TEXT, phrases TEXT, task TEXT, link TEXT, quiz TEXT);
CREATE TABLE IF NOT EXISTS academy_progress(user_id INT, module_id INT, status TEXT, score REAL, completed_at TEXT,
  PRIMARY KEY(user_id, module_id));
CREATE TABLE IF NOT EXISTS tools(key TEXT PRIMARY KEY, seq INT, name TEXT, areas TEXT, type TEXT, pricing TEXT, platform TEXT,
  url TEXT, summary TEXT, use_cases TEXT, steps TEXT, lesson_idea TEXT);
CREATE TABLE IF NOT EXISTS course_tools(course_id INT, tool_key TEXT, added_by INT, created_at TEXT, PRIMARY KEY(course_id, tool_key));
CREATE TABLE IF NOT EXISTS syllabi(course_id INT PRIMARY KEY, user_id INT, data TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, ts TEXT, user_id INT, action TEXT, entity TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS support_tickets(id INTEGER PRIMARY KEY, user_id INT, category TEXT, priority TEXT, subject TEXT, body TEXT,
  page TEXT, status TEXT, assignee_id INT, rating INT, created_at TEXT, updated_at TEXT, closed_at TEXT, synthetic INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS support_messages(id INTEGER PRIMARY KEY, ticket_id INT, author_id INT, text TEXT, internal INT DEFAULT 0,
  file_id INT, created_at TEXT);
CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY, user_id INT, role TEXT, area TEXT, score INT, nps INT, comment TEXT,
  page TEXT, lang TEXT, created_at TEXT, synthetic INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS interventions(id INTEGER PRIMARY KEY, student_id INT, course_id INT, created_by INT, kind TEXT, status TEXT,
  plan TEXT, risk_before REAL, level_before TEXT, drivers TEXT, note TEXT, created_at TEXT, updated_at TEXT, due_at TEXT, closed_at TEXT,
  synthetic INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS risk_snapshots(week_start TEXT, course_id INT, high INT, watch INT, ok INT, students INT);
CREATE INDEX IF NOT EXISTS idx_iv_student ON interventions(student_id, course_id, status);
CREATE INDEX IF NOT EXISTS idx_ticket_user ON support_tickets(user_id, status);
CREATE INDEX IF NOT EXISTS idx_msg_user ON messages(user_id, channel, course_id);
CREATE INDEX IF NOT EXISTS idx_msg_course ON messages(course_id, channel, role);
CREATE INDEX IF NOT EXISTS idx_att_user ON attendance(user_id);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, read_at);
CREATE INDEX IF NOT EXISTS idx_req_student ON requests(student_id);
