-- Task 48: solver runs, timetable versions (drafts and published), their placements, review and notes; and the link of a
-- timetable row to the meeting it publishes. JSON in TEXT, run blobs zlib(JSON) with ids only (no names, no notes).
CREATE TABLE IF NOT EXISTS tt_runs(id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL,
  kind TEXT NOT NULL,                       -- precheck | solve | repair | check | adopt | publish
  scope TEXT NOT NULL DEFAULT '{"all":true}',   -- or {"departments":[...]}; repair adds {"dirty":[unit ids]}
  base_version_id INTEGER, version_id INTEGER, effective_from TEXT,
  params TEXT,                              -- JSON: publish {accept_unplaced, override_reason}; solve {name}
  status TEXT NOT NULL DEFAULT 'queued',    -- queued | running | done | failed | cancelled
  cancel INTEGER NOT NULL DEFAULT 0, seed INTEGER NOT NULL, iter_budget INTEGER NOT NULL, time_budget_s INTEGER NOT NULL,
  iterations INTEGER NOT NULL DEFAULT 0, cpu_ms INTEGER NOT NULL DEFAULT 0, stopped TEXT,
  progress TEXT,                            -- JSON: phase or step, cursor, placed, unplaced, score, eta_s, tx_ms_max
  input BLOB, input_sha256 TEXT, inputs_fp TEXT,
  state BLOB,                               -- the solver state between chunks; NULL when done
  report BLOB,                              -- pre-check lines and coverage per group (precheck, solve, repair)
  error TEXT, fails INTEGER NOT NULL DEFAULT 0,
  requested_by INTEGER NOT NULL, requested_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, heartbeat_at TEXT);
CREATE INDEX IF NOT EXISTS idx_tt_runs_status ON tt_runs(status, id);
CREATE INDEX IF NOT EXISTS idx_tt_runs_term ON tt_runs(term_id, kind, id);
-- one active run per term, in every worker
CREATE UNIQUE INDEX IF NOT EXISTS idx_tt_runs_active ON tt_runs(term_id) WHERE status IN ('queued','running');

CREATE TABLE IF NOT EXISTS tt_versions(id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL, run_id INTEGER, parent_id INTEGER,
  status TEXT NOT NULL,                     -- draft | review | published | superseded | discarded
  name TEXT, rev INTEGER NOT NULL DEFAULT 0,   -- +1 on every edit (optimistic lock)
  checked_rev INTEGER, violations INTEGER,     -- the last full check; publishing needs checked_rev = rev and violations = 0
  score TEXT,                               -- JSON scorecard at checked_rev, with the diff against parent_id
  inputs_fp TEXT, scope TEXT NOT NULL, effective_from TEXT,
  unplaced INTEGER NOT NULL DEFAULT 0, excluded INTEGER NOT NULL DEFAULT 0,
  review_due TEXT, note TEXT, created_by INTEGER NOT NULL, created_at TEXT NOT NULL,
  published_by INTEGER, published_at TEXT, publish_note TEXT);
CREATE INDEX IF NOT EXISTS idx_tt_versions_term ON tt_versions(term_id, status);

CREATE TABLE IF NOT EXISTS tt_placements(id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL, meeting_key TEXT NOT NULL,
  unit_id INTEGER NOT NULL, part INTEGER NOT NULL, weekday INTEGER NOT NULL, period INTEGER NOT NULL, duration INTEGER NOT NULL,
  weeks TEXT NOT NULL, room_id INTEGER, locked INTEGER NOT NULL DEFAULT 0,
  origin TEXT NOT NULL,                     -- solver | manual | adopted | kept
  changed_by INTEGER, changed_at TEXT, timetable_id INTEGER);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tt_place_key ON tt_placements(version_id, meeting_key);
CREATE INDEX IF NOT EXISTS idx_tt_place_unit ON tt_placements(version_id, unit_id);
CREATE INDEX IF NOT EXISTS idx_tt_place_slot ON tt_placements(version_id, weekday, period);

CREATE TABLE IF NOT EXISTS tt_unplaced(version_id INTEGER NOT NULL, meeting_key TEXT NOT NULL, unit_id INTEGER NOT NULL,
  reasons TEXT NOT NULL,                    -- JSON: reasons, suggested moves, input relaxations
  PRIMARY KEY(version_id, meeting_key));

CREATE TABLE IF NOT EXISTS tt_reviews(version_id INTEGER NOT NULL, scope_type TEXT NOT NULL, scope_id INTEGER NOT NULL,  -- department | faculty
  status TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | changes
  comment TEXT, decided_by INTEGER, decided_at TEXT, reset_at TEXT, PRIMARY KEY(version_id, scope_type, scope_id));

CREATE TABLE IF NOT EXISTS tt_notes(id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL, meeting_key TEXT,
  scope_type TEXT NOT NULL, scope_id INTEGER NOT NULL, author_id INTEGER NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL,
  carried_from INTEGER, resolved_by INTEGER, resolved_at TEXT, resolution TEXT);
CREATE INDEX IF NOT EXISTS idx_tt_notes_version ON tt_notes(version_id, resolved_at);
CREATE INDEX IF NOT EXISTS idx_tt_notes_author ON tt_notes(author_id);      -- the person's export (Task 40)

-- a published row keeps its meeting: the next publish updates it in place instead of replacing it
ALTER TABLE timetable ADD COLUMN meeting_key TEXT;
ALTER TABLE timetable ADD COLUMN period INTEGER;
ALTER TABLE timetable ADD COLUMN version_id INTEGER;
CREATE UNIQUE INDEX IF NOT EXISTS idx_timetable_meeting ON timetable(meeting_key) WHERE active=1 AND meeting_key IS NOT NULL;
