-- Task 31: a building's route graph. Nodes are entrances, corridor points, stairs, lifts and the rooms' doors; edges
-- carry a length in metres and whether they are step-free. Imported from CSV (manage.py import-routes), replaced per
-- building in one transaction.
CREATE TABLE IF NOT EXISTS route_nodes(id INTEGER PRIMARY KEY, building_id INTEGER NOT NULL, code TEXT NOT NULL, kind TEXT NOT NULL,
  floor INTEGER NOT NULL, room_id INTEGER, label TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS idx_route_nodes_code ON route_nodes(building_id, code);
CREATE INDEX IF NOT EXISTS idx_route_nodes_room ON route_nodes(room_id);
CREATE TABLE IF NOT EXISTS route_edges(id INTEGER PRIMARY KEY, building_id INTEGER NOT NULL, a INTEGER NOT NULL, b INTEGER NOT NULL,
  length_m REAL NOT NULL, step_free INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_route_edges_building ON route_edges(building_id);
