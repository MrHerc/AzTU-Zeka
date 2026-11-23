-- Task 24: frameworks (NICE Components, Bloom, EQF) as one model: a framework version, its items with a parent, the links
-- between items, and which item a course's learning outcome carries. A version is never changed after its import: a
-- newer one is another row, and the older one with its items and maps stays readable. `counts` holds the items per
-- kind (JSON), so listing the frameworks never walks the items.
CREATE TABLE IF NOT EXISTS frameworks(id INTEGER PRIMARY KEY, key TEXT NOT NULL, version TEXT NOT NULL,
  title TEXT NOT NULL, source_url TEXT, sha256 TEXT, size INTEGER, counts TEXT NOT NULL DEFAULT '{}', links INTEGER NOT NULL DEFAULT 0,
  builtin INTEGER NOT NULL DEFAULT 0, imported_at TEXT NOT NULL, UNIQUE(key, version));
-- kind: the source's element type (NICE: work_role, task, knowledge, skill, competency_area, category, opm_code, sort;
-- Bloom: level; EQF: level, knowledge, skill, responsibility). parent: the code of the item this one belongs to.
CREATE TABLE IF NOT EXISTS framework_items(id INTEGER PRIMARY KEY, framework_id INTEGER NOT NULL, code TEXT NOT NULL,
  kind TEXT NOT NULL, parent TEXT, title TEXT NOT NULL DEFAULT '', text TEXT NOT NULL DEFAULT '', UNIQUE(framework_id, code));
CREATE INDEX IF NOT EXISTS idx_framework_items_kind ON framework_items(framework_id, kind, code);
-- A relationship of the source (NICE: "projection"): a work role to its tasks, knowledge and skills, a category to its
-- work roles, a competency area to its knowledge and skills.
CREATE TABLE IF NOT EXISTS framework_links(source_id INTEGER NOT NULL, dest_id INTEGER NOT NULL, PRIMARY KEY(source_id, dest_id)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_framework_links_dest ON framework_links(dest_id);
-- The outcome map. A syllabus outcome lives in the version JSON; its key here is the course and the outcome's code
-- (N1 …), which a new version of the syllabus keeps. Who mapped it and when stay with the row.
CREATE TABLE IF NOT EXISTS outcome_items(id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL, outcome TEXT NOT NULL,
  item_id INTEGER NOT NULL, mapped_by INTEGER, mapped_at TEXT NOT NULL, UNIQUE(course_id, outcome, item_id));
CREATE INDEX IF NOT EXISTS idx_outcome_items_item ON outcome_items(item_id);
-- A programme (specialty) reaches its courses through its groups' teaching units (coverage report).
CREATE INDEX IF NOT EXISTS idx_study_groups_specialty ON study_groups(specialty_id);
