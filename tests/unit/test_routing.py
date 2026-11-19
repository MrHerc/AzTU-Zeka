"""The route graph (tasks/todo.md, Task 31): the CSV checks, the shortest way, the step-free rule and the steps."""
import csv
import itertools
import random
from pathlib import Path

from zeka.modules.facilities import domain

ROUTES = Path(__file__).resolve().parents[2] / "content" / "routes"
EK_ROOMS = {f"EK-{n}": i for i, n in enumerate(("118", "121", "220", "224", "301", "305", "316", "402", "405", "512"), start=1)}


def load(name: str):
    return list(csv.DictReader((ROUTES / name).read_text(encoding="utf-8").splitlines()))


def keyed(nodes, edges):
    return {n["code"]: n for n in nodes}, edges


def test_the_demo_graph_passes_the_checks():
    nodes, edges, problems = domain.graph_input(load("EK.nodes.csv"), load("EK.edges.csv"), EK_ROOMS)
    assert problems == [] and len(nodes) == 37 and {n["room_id"] for n in nodes if n["kind"] == "door"} == set(EK_ROOMS.values())


def test_each_problem_names_its_file_and_line_and_nothing_is_half_taken():
    nodes = [{"code": "E", "kind": "entrance", "floor": "1"}, {"code": "E", "kind": "door", "floor": "1", "room": "EK-118"},
             {"code": "X", "kind": "hall", "floor": "one"}, {"code": "D", "kind": "door", "floor": "1", "room": "ZZ-1"},
             {"code": "C", "kind": "corridor", "floor": "1", "room": "EK-118"},
             {"code": "S1", "kind": "stairs", "floor": "1"}, {"code": "S2", "kind": "stairs", "floor": "2"},
             {"code": "K", "kind": "corridor", "floor": "2"}]
    edges = [{"from": "E", "to": "Q", "length_m": "5", "step_free": "1"}, {"from": "E", "to": "C", "length_m": "-3", "step_free": "maybe"},
             {"from": "S1", "to": "S2", "length_m": "12", "step_free": "1"}, {"from": "C", "to": "K", "length_m": "4", "step_free": "1"}]
    _, _, problems = domain.graph_input(nodes, edges, EK_ROOMS)
    assert problems == ["nodes.csv:3: the code is empty or repeated",
                        "nodes.csv:4: kind must be one of entrance, corridor, stairs, lift, door",
                        "nodes.csv:4: floor must be a whole number",
                        "nodes.csv:5: a door names a room of this building (got ZZ-1)",
                        "nodes.csv:6: only a door names a room",
                        "edges.csv:2: both ends must be different nodes of nodes.csv",
                        "edges.csv:3: length_m must be a number of metres above 0",
                        "edges.csv:3: step_free must be 1 or 0",
                        "edges.csv:4: stairs are never step-free",
                        "edges.csv:5: a floor change joins two stairs or two lifts"]


def test_the_shortest_way_and_the_step_free_way_by_the_lift():
    nodes, edges = keyed(*domain.graph_input(load("EK.nodes.csv"), load("EK.edges.csv"), EK_ROOMS)[:2])
    path, metres = domain.shortest(nodes, edges, ["E1", "E2"], "D512")
    assert path[0] == "E1" and "S5" in path and "L5" not in path and metres == 76
    path, metres = domain.shortest(nodes, edges, ["E1", "E2"], "D512", step_free=True)
    assert path[0] == "E1" and "L5" in path and not any(nodes[n]["kind"] == "stairs" for n in path) and metres == 110


def test_a_step_free_way_never_uses_stairs_on_random_graphs():
    rng = random.Random(7)
    for _ in range(200):
        floors = rng.randint(1, 4)
        nodes = {f"S{f}": {"kind": "stairs", "floor": f} for f in range(1, floors + 1)}
        nodes |= {f"C{f}{i}": {"kind": "corridor", "floor": f} for f in range(1, floors + 1) for i in range(3)}
        if rng.random() < 0.5:
            nodes |= {f"L{f}": {"kind": "lift", "floor": f} for f in range(1, floors + 1)}
        edges = []
        for a, b in itertools.combinations(nodes, 2):
            na, nb = nodes[a], nodes[b]
            if na["floor"] == nb["floor"] and rng.random() < 0.5:
                edges.append({"a": a, "b": b, "length_m": rng.randint(1, 40), "step_free": int(rng.random() < 0.8)})
            elif abs(na["floor"] - nb["floor"]) == 1 and na["kind"] == nb["kind"] and na["kind"] in ("stairs", "lift"):
                edges.append({"a": a, "b": b, "length_m": rng.randint(5, 25), "step_free": int(na["kind"] == "lift")})
        start, goal = rng.choice(list(nodes)), rng.choice(list(nodes))
        found = domain.shortest(nodes, edges, [start], goal, step_free=True)
        if found and start != goal:
            path = found[0]
            assert not any(nodes[n]["kind"] == "stairs" for n in path), path
            steps = {frozenset((e["a"], e["b"])) for e in edges if not e["step_free"]}
            assert not any(frozenset(p) in steps for p in zip(path, path[1:], strict=False)), path


def test_the_steps_sum_up_a_floor_and_a_run_of_stairs():
    nodes, edges = keyed(*domain.graph_input(load("EK.nodes.csv"), load("EK.edges.csv"), EK_ROOMS)[:2])
    path, _ = domain.shortest(nodes, edges, ["E1"], "D512")
    out = [t.format(**p) for t, p in domain.steps(path, nodes, edges)]
    assert out == ["Başlanğıc: Əsas giriş", "15 m gedin → Mərkəzi pilləkən", "Pilləkənlə qalxın, mərtəbə: 5", "13 m gedin → EK-512",
                   "Çatdınız: EK-512"]


def test_coverage_names_rooms_without_a_node_and_doors_without_a_way():
    it_rooms = {101: {"code": "IT-101", "accessible": 1}, 214: {"code": "IT-214", "accessible": 1}, 300: {"code": "IT-300", "accessible": 0}}
    nodes, edges, problems = domain.graph_input(load("IT.nodes.csv"), load("IT.edges.csv"), {"IT-101": 101, "IT-214": 214, "IT-300": 300})
    assert problems == []
    cov = domain.coverage(*keyed(nodes, edges), it_rooms)
    assert cov == {"rooms_without_node": ["IT-300"], "unreachable": [], "no_step_free_route": ["IT-214"]}
