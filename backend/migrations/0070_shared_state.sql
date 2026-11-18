-- 0070 (Task 7): state that several worker processes must share.
-- One-time document links: taken with DELETE ... RETURNING, so two processes cannot both accept the same key.
CREATE TABLE IF NOT EXISTS doc_keys(key TEXT PRIMARY KEY, kind TEXT NOT NULL, obj_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL, expires_at TEXT NOT NULL);
-- Rate-limit events (sliding window per limiter and key); written in their own short transaction.
CREATE TABLE IF NOT EXISTS rate_hits(name TEXT NOT NULL, key TEXT NOT NULL, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_rate_hits ON rate_hits(name, key, ts);
-- Search index changes: every process applies the rows after the last seq it has seen.
CREATE TABLE IF NOT EXISTS index_changes(seq INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
  doc_id INTEGER NOT NULL, op TEXT NOT NULL CHECK (op IN ('upsert', 'delete')));
