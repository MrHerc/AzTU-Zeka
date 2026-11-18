-- Task 10: accounts and passwords. password_hash is "scrypt$n$r$p$salt$hash" (backend/zeka/modules/identity/domain.py).
-- status: active | disabled. must_change: the next session may only change the password (a temporary password).
-- failed_count / locked_until: consecutive failed sign-ins of the account and the end of its lock (ISO, university time).
ALTER TABLE users ADD COLUMN email TEXT;
ALTER TABLE users ADD COLUMN password_hash TEXT;
ALTER TABLE users ADD COLUMN must_change INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE users ADD COLUMN failed_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN locked_until TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL;

-- Failed sign-ins per (account as typed, client address or IPv6 /64): counted in a window, then blocked until `until`
-- (epoch seconds). The account is the typed login, so unknown accounts are throttled exactly like real ones.
CREATE TABLE IF NOT EXISTS login_blocks(account TEXT NOT NULL, client TEXT NOT NULL, failures INTEGER NOT NULL,
  first REAL NOT NULL, until REAL, PRIMARY KEY(account, client));
