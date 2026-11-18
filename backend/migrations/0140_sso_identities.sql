-- Task 14: single sign-on through a generic OpenID Connect provider.
-- An account is bound to the provider's (iss, sub) pair; later sign-ins find the account only through this row, so a
-- changed e-mail at the provider never moves a sign-in to another local account. One binding per account and issuer.
CREATE TABLE IF NOT EXISTS sso_identities(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, iss TEXT NOT NULL,
  sub TEXT NOT NULL, email TEXT, linked_by TEXT NOT NULL, linked_at TEXT NOT NULL, last_login TEXT,
  UNIQUE(iss, sub), UNIQUE(user_id, iss));
-- A started sign-in: state, nonce and the PKCE verifier, taken once with DELETE ... RETURNING by the callback (any
-- worker). browser_hash binds it to the browser that started it; link_user_id is set when an account owner links.
-- The first link finds a student by the provider's student-number claim.
CREATE INDEX IF NOT EXISTS idx_users_student_no ON users(student_no) WHERE student_no IS NOT NULL;
CREATE TABLE IF NOT EXISTS sso_pending(state TEXT PRIMARY KEY, browser_hash TEXT NOT NULL, nonce TEXT NOT NULL,
  verifier TEXT NOT NULL, link_user_id INTEGER, created_at REAL NOT NULL);
