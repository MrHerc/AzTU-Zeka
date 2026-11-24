-- Task 48: the daily re-check of a published version against the term as it is now (job timetable.health): JSON
-- {at, count, problems: [{code, keys, slot, weeks}], seen: [signatures]}; seen holds the problems the timetable
-- office was told about, so each new problem is told once. Meeting keys and codes only, no person.
ALTER TABLE tt_versions ADD COLUMN health TEXT;
