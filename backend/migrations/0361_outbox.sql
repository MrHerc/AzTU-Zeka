-- Task 36, slice 2: outgoing e-mail. A message is queued with its template, parameters and the recipient's language and
-- rendered when it is sent; a failed attempt waits longer each time (next_at) and is never lost; after the last attempt
-- the row stays as failed with the reason.
CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, address TEXT NOT NULL, kind TEXT NOT NULL,
  template TEXT NOT NULL, params TEXT NOT NULL, lang TEXT NOT NULL DEFAULT 'az', status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0, next_at TEXT NOT NULL, last_error TEXT, created_at TEXT NOT NULL, sent_at TEXT);
CREATE INDEX IF NOT EXISTS idx_outbox_due ON outbox(status, next_at);
