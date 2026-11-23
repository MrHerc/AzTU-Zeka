-- Task 24, Checkpoint F (SEC-FW-1, BR-F1): a submitted version keeps the framework items its outcomes carried when it
-- was submitted, as {outcome: [item id …]}. The printed page and the coverage report read a version's own map, so a
-- later change of the outcome map reaches only the next version, through submission, approval and publication. A
-- version submitted before this file takes the map as it stands now; a draft has none (NULL) and reads the live map.
ALTER TABLE syllabus_versions ADD COLUMN tags TEXT;
UPDATE syllabus_versions SET tags = COALESCE((SELECT json_group_object(outcome, json(ids)) FROM (
  SELECT outcome, json_group_array(item_id) ids FROM (SELECT outcome, item_id FROM outcome_items
  WHERE outcome_items.course_id = syllabus_versions.course_id ORDER BY outcome, item_id) GROUP BY outcome)), '{}')
WHERE status <> 'draft';
