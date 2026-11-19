-- Task 28: Safe Exam Browser. Each exam session gets a one-time value that is part of the URL SEB hashes (so a hash
-- caught in one session is refused in another), and is marked once its Config Key hash checks out. The config itself
-- is built from the exam and the public address every time, so it is not stored.
ALTER TABLE sessions ADD COLUMN seb_nonce TEXT;
ALTER TABLE sessions ADD COLUMN seb_ok INTEGER NOT NULL DEFAULT 0;
