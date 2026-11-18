-- Task 17: a course's prerequisites are its own field (the syllabus of Task 23 edits it), not a table in the code.
ALTER TABLE courses ADD COLUMN prereq TEXT;
