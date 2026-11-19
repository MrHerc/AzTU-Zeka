-- Task 35: clubs and their channels. A club is proposed by a student or a teacher (its leader) and approved by a dean's
-- office; people ask to join and the leader lets them in; a member accepts the code of conduct before the first post.
-- Channels are a chat (members write) or announcements (the leader writes). Messages are kept for the retention period
-- (the periodic purge), reported to the moderators, hidden; a member can be muted until a time or removed.
CREATE TABLE IF NOT EXISTS clubs(id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, leader_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', decided_by INTEGER, decided_at TEXT, note TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_clubs_status ON clubs(status, name);
CREATE TABLE IF NOT EXISTS club_members(club_id INTEGER NOT NULL, user_id INTEGER NOT NULL, role TEXT NOT NULL DEFAULT 'member',
  status TEXT NOT NULL DEFAULT 'requested', muted_until TEXT, conduct_at TEXT, created_at TEXT NOT NULL, PRIMARY KEY(club_id, user_id));
CREATE INDEX IF NOT EXISTS idx_club_members_user ON club_members(user_id, status);
CREATE TABLE IF NOT EXISTS club_channels(id INTEGER PRIMARY KEY, club_id INTEGER NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
  created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_club_channels_club ON club_channels(club_id);
CREATE TABLE IF NOT EXISTS club_messages(id INTEGER PRIMARY KEY, channel_id INTEGER NOT NULL, author_id INTEGER NOT NULL, text TEXT NOT NULL,
  hidden INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_club_messages_channel ON club_messages(channel_id, id);
CREATE INDEX IF NOT EXISTS idx_club_messages_created ON club_messages(created_at);
CREATE TABLE IF NOT EXISTS club_reports(id INTEGER PRIMARY KEY, message_id INTEGER NOT NULL, reporter_id INTEGER NOT NULL, reason TEXT NOT NULL,
  created_at TEXT NOT NULL, resolved_at TEXT, resolved_by INTEGER, outcome TEXT);
CREATE INDEX IF NOT EXISTS idx_club_reports_open ON club_reports(resolved_at, id);
CREATE INDEX IF NOT EXISTS idx_club_reports_message ON club_reports(message_id);
