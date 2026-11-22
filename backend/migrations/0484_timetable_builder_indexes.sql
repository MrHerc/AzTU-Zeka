-- Task 48, slice 2: a room's placements in a version (the room grid and the editor's free rooms) without reading the
-- whole version.
CREATE INDEX IF NOT EXISTS idx_tt_place_room ON tt_placements(version_id, room_id);
