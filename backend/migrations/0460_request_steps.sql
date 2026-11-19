-- Task 46: e-service honesty. Each step of a request type is done by one role (step_roles: a JSON list, one role id per
-- step); the last step runs the type's effect (`none` or an effect registered in code, legacy/r_services.EFFECTS); a type
-- is offered only after the administrator opened it (enabled: 0 by default, so prod offers nothing until then).
ALTER TABLE request_types ADD COLUMN step_roles TEXT;
ALTER TABLE request_types ADD COLUMN effect TEXT NOT NULL DEFAULT 'none';
ALTER TABLE request_types ADD COLUMN enabled INTEGER NOT NULL DEFAULT 0;
-- the role an act was done in: a person may hold several (Task 13)
ALTER TABLE request_events ADD COLUMN role TEXT;
-- who is told about a step: the accounts whose primary role is that step's role (it has no grant row)
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
-- the queue of an academic office or a department head: the requests of the types it has a step in
CREATE INDEX IF NOT EXISTS idx_requests_type_status ON requests(type_code, status);
