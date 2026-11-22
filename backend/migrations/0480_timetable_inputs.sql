-- Task 48: the inputs of one term's timetable that the forms do not hold. No foreign keys; rows are deactivated or
-- replaced, never deleted. Person columns are in identity/repo.INVENTORY and docs/privacy/data-inventory.md.

-- one term's preparation: deadlines (NULL: the default offset from teaching_start) and the per-term confirmations
CREATE TABLE IF NOT EXISTS tt_terms(term_id INTEGER PRIMARY KEY,
  needs_due TEXT, groups_due TEXT, availability_due TEXT, review_due TEXT, publish_target TEXT,
  confirmed TEXT NOT NULL DEFAULT '[]',     -- JSON list: "practice", "reserved_weeks", "fixed_slots", "online"
  note TEXT, updated_by INTEGER, updated_at TEXT);

-- a department head's "our load is final", with the units and hours as they were then (it informs, it never blocks)
CREATE TABLE IF NOT EXISTS tt_dept_status(term_id INTEGER NOT NULL, department_id INTEGER NOT NULL,
  status TEXT NOT NULL,                     -- confirmed | reopened
  units INTEGER NOT NULL, hours REAL NOT NULL, set_by INTEGER NOT NULL, at TEXT NOT NULL,
  PRIMARY KEY(term_id, department_id));

-- what a unit needs from a room and a week; NULL falls back to the defaults
CREATE TABLE IF NOT EXISTS tt_unit_needs(unit_id INTEGER PRIMARY KEY,
  room_kinds TEXT,                          -- JSON list of room kinds; NULL: by the unit's kind
  room_ids TEXT,                            -- JSON list: only these rooms; NULL: any room that fits
  need INTEGER, need_reason TEXT,           -- seats override (a reason is required); NULL: students, registry, default_need
  duration INTEGER NOT NULL DEFAULT 1,      -- pairs per meeting
  mode TEXT NOT NULL DEFAULT 'in_person',   -- in_person | online (no room, no travel)
  pattern TEXT,                             -- JSON list of week sets overriding the weekly-pattern rule
  lecture_unit_id INTEGER,                  -- a confirmed lecture link; NULL: derived when unambiguous
  split TEXT,                               -- lab split decision: NULL undecided | 'whole' | 'split'
  updated_by INTEGER, updated_at TEXT);

CREATE TABLE IF NOT EXISTS tt_group_terms(term_id INTEGER NOT NULL, group_id INTEGER NOT NULL, shift TEXT,
  home_building_id INTEGER, updated_by INTEGER, updated_at TEXT, PRIMARY KEY(term_id, group_id));

-- one cell of a teacher's or a room's week: unavailable (hard), undesired and preferred (soft)
CREATE TABLE IF NOT EXISTS tt_availability(id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL,
  subject_type TEXT NOT NULL, subject_id INTEGER NOT NULL,       -- teacher | room
  weekday INTEGER NOT NULL, period INTEGER NOT NULL, weeks TEXT NOT NULL DEFAULT 'all',
  level TEXT NOT NULL, note TEXT, updated_by INTEGER NOT NULL, updated_at TEXT NOT NULL);
-- subject first: the same index serves a term's grid and the person's export and erasure (Task 40)
CREATE UNIQUE INDEX IF NOT EXISTS idx_tt_avail_cell ON tt_availability(subject_type, subject_id, term_id, weekday, period);

-- a teacher's "my grid is complete" (a confirmed empty grid: no restrictions), and a grid above the cap that waits for
-- the head (the solver never reads it); over_cap_cells: by how many cells an approved grid exceeded the cap
CREATE TABLE IF NOT EXISTS tt_availability_status(term_id INTEGER NOT NULL, teacher_id INTEGER NOT NULL,
  confirmed_at TEXT, confirmed_by INTEGER,
  pending TEXT, pending_at TEXT,
  reopened_until TEXT, over_cap_cells INTEGER, decided_by INTEGER, decided_at TEXT,
  PRIMARY KEY(term_id, teacher_id));
CREATE INDEX IF NOT EXISTS idx_tt_avail_pending ON tt_availability_status(term_id) WHERE pending IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tt_avail_status_teacher ON tt_availability_status(teacher_id);

-- whole weeks a group, a room or a teacher is away: practice, military training, closure, leave
CREATE TABLE IF NOT EXISTS tt_blocks(id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL,
  subject_type TEXT NOT NULL, subject_id INTEGER NOT NULL,       -- group | room | teacher
  weeks TEXT NOT NULL, kind TEXT NOT NULL,                       -- practice | military | closure | leave | other
  note TEXT, active INTEGER NOT NULL DEFAULT 1, updated_by INTEGER NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_tt_blocks_subject ON tt_blocks(subject_type, subject_id, term_id);
