-- Task 37: the integration hub. An API key is kept as its SHA-256 only (the key is shown once), with its scopes and a
-- per-minute limit; every call is audited. A webhook has its URL, its signing secret (kept to sign each delivery) and
-- the events it wants; every delivery is a row: tried, signed, retried with a growing wait, logged.
CREATE TABLE IF NOT EXISTS api_tokens(id INTEGER PRIMARY KEY, name TEXT NOT NULL, prefix TEXT NOT NULL, token_hash TEXT NOT NULL,
  scopes TEXT NOT NULL, per_minute INTEGER NOT NULL DEFAULT 60, created_by INTEGER NOT NULL, created_at TEXT NOT NULL,
  last_used_at TEXT, revoked_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS idx_api_tokens_hash ON api_tokens(token_hash);
CREATE TABLE IF NOT EXISTS webhooks(id INTEGER PRIMARY KEY, url TEXT NOT NULL, secret TEXT NOT NULL, events TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1, created_by INTEGER NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS webhook_deliveries(id INTEGER PRIMARY KEY, webhook_id INTEGER NOT NULL, event TEXT NOT NULL, payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, next_at TEXT NOT NULL, last_status INTEGER, last_error TEXT,
  created_at TEXT NOT NULL, sent_at TEXT);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_due ON webhook_deliveries(status, next_at);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_hook ON webhook_deliveries(webhook_id, id);
