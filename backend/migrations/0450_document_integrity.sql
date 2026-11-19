-- Task 45: an issued document keeps everything it is shown with, and its registry number comes from a sequence.
-- `payload` is the canonical JSON gathered at issue (holder, issuer, university, the data, the transcript rows) and
-- `hash` is its SHA-256; a document issued before this migration has none and is not verified.
ALTER TABLE documents ADD COLUMN payload TEXT;
CREATE TABLE IF NOT EXISTS doc_sequences(prefix TEXT NOT NULL, year INTEGER NOT NULL, last_no INTEGER NOT NULL, PRIMARY KEY(prefix, year));
-- reg_no is <register>-<prefix>-<year>-<six digits>: each sequence starts after the largest number already given
INSERT OR IGNORE INTO doc_sequences(prefix, year, last_no)
  SELECT substr(reg_no, 1, length(reg_no) - 12), CAST(substr(reg_no, length(reg_no) - 10, 4) AS INTEGER), MAX(CAST(substr(reg_no, -6) AS INTEGER))
  FROM documents WHERE reg_no GLOB '*-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]'
  GROUP BY substr(reg_no, 1, length(reg_no) - 12), substr(reg_no, length(reg_no) - 10, 4);
