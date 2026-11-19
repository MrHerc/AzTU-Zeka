"""Rooms, routes and the next lesson in the campus assistant (tasks/todo.md, Task 31), on the demo's synthetic graphs
(content/routes): every room of the pilot buildings is a node, any two rooms have a way or a named reason, a step-free
way never uses stairs, and "where is my next lesson" matches the person's own calendar feed."""
import csv
import itertools
import os
import subprocess
import sys
import time
from pathlib import Path

from zeka.core import clock
from zeka.legacy import store
from zeka.modules.facilities import domain, repo, service

ROOT = Path(__file__).resolve().parents[2]


def db():
    return store.connect()


def test_every_room_of_the_pilot_buildings_is_a_node_and_any_two_have_a_way_or_a_reason(app_db):
    c = db()
    try:
        rooms = store.rows(c, "SELECT r.code, r.building_id FROM rooms r JOIN buildings b ON b.id=r.building_id WHERE b.code IN ('EK','IT')")
        doors = {n["room_id"] for b in {r["building_id"] for r in rooms} for n in repo.graph(c, b)[0].values() if n["kind"] == "door"}
        assert len(rooms) == 12 and len(doors) == 12
        for a, b in itertools.permutations([r["code"] for r in rooms], 2):
            for step_free in (False, True):
                r = service.route(c, b, a, step_free)
                assert r["missing"] in (None, "no_path") and (r["steps"] or r["missing"]), (a, b, step_free, r)
                if r["missing"] is None:
                    assert r["steps"][-1][1]["label"] == b and r["length_m"] > 0
        assert service.route(c, "IT-214", None, True)["missing"] == "no_path", "no lift in the İT korpusu"
    finally:
        c.close()


def test_a_step_free_way_never_passes_stairs_between_any_two_doors(app_db):
    c = db()
    try:
        for b in store.rows(c, "SELECT id FROM buildings"):
            nodes, edges = repo.graph(c, b["id"])
            doors = [k for k, n in nodes.items() if n["kind"] in ("door", "entrance")]
            for x, y in itertools.permutations(doors, 2):
                found = domain.shortest(nodes, edges, [x], y, step_free=True)
                if found:
                    assert not any(nodes[n]["kind"] == "stairs" for n in found[0])
    finally:
        c.close()


def test_the_assistant_answers_where_a_room_is_with_the_way(app_db):
    s = app_db.client("student")
    a = s.post("/api/campus/ask", {"message": "EK-305 otağı haradadır?"}).json["answer"]
    assert a["meta"]["source"] == "rooms" and "EK-305" in a["content"] and "Pilləkənlə qalxın, mərtəbə: 3" in a["content"]
    assert a["meta"]["actions"] == [{"type": "link", "label": "Otağın səhifəsi", "href": "/r/EK-305"}]
    lift = s.post("/api/campus/ask", {"message": "Əlil arabası ilə 512 otağına necə gedim?"}).json["answer"]
    assert "Liftlə qalxın, mərtəbə: 5" in lift["content"] and "Pilləkən" not in lift["content"]
    by_name = s.post("/api/campus/ask", {"message": "Fizika laboratoriyası harda yerləşir?"}).json["answer"]
    assert "EK-121" in by_name["content"]
    en = s.post("/api/campus/ask", {"message": "Where is room IT-214?"}, lang="en").json["answer"]
    assert "IT-214" in en["content"] and en["meta"]["source"] == "rooms"
    rule = s.post("/api/campus/ask", {"message": "Xəstəlik səbəbindən qayıbı necə üzrlü edim?"}).json["answer"]
    assert rule["meta"].get("source") != "rooms", "a question about a rule still goes to the knowledge base"


def _next_in_feed(app_db, client) -> tuple[str, str]:
    """(SUMMARY, DTSTART) of the first lesson in the person's own calendar feed that has not ended yet."""
    url = client.post("/api/me/calendar").json["url"]
    text = app_db.client().get("/" + url.split("/", 3)[3]).text
    now = clock.now().astimezone(clock.ZONE).strftime("%Y%m%dT%H%M%S")
    events = []
    for block in text.split("BEGIN:VEVENT")[1:]:
        fields = {}
        for line in block.splitlines():
            if ":" in line:
                name, value = line.split(":", 1)
                fields[name.split(";")[0]] = value
        if fields.get("STATUS") == "CONFIRMED" and fields["DTEND"] > now:
            events.append((fields["DTSTART"], fields["SUMMARY"]))
    start, summary = min(events)
    return summary.replace("\\,", ","), start


def test_where_is_my_next_lesson_matches_the_calendar_and_answers_within_two_seconds(app_db):
    for role in ("student", "teacher"):
        client = app_db.client(role)
        summary, start = _next_in_feed(app_db, client)
        t0 = time.monotonic()
        a = client.post("/api/campus/ask", {"message": "Növbəti dərsim hardadır?"}).json["answer"]
        assert time.monotonic() - t0 < 2.0
        course = summary.split(" · ")[0]
        assert a["meta"]["source"] == "timetable" and f"**{course}**" in a["content"], (role, summary, a["content"])
        assert f"{start[9:11]}:{start[11:13]}–" in a["content"], (role, start, a["content"])


def test_the_room_page_shows_the_way_from_its_door_and_the_step_free_choice(app_db):
    anon = app_db.client()
    page = anon.get("/r/EK-118?to=EK-512").text
    assert "Başlanğıc: EK-118" in page and "Pilləkənlə qalxın, mərtəbə: 5" in page and "Çatdınız: EK-512" in page
    lift = anon.get("/r/EK-118?to=ek-512&sf=1").text
    assert "Liftlə qalxın, mərtəbə: 5" in lift and "Pilləkənlə qalxın" not in lift
    assert "Bu otaqlar arasında marşrut yoxdur" in anon.get("/r/IT-101?to=IT-214&sf=1").text
    assert "Otaq tapılmadı" in anon.get("/r/EK-118?to=ZZ-999").text
    assert "&lt;script&gt;" in anon.get("/r/EK-118?to=%3Cscript%3E").text


def test_import_routes_is_all_or_nothing_and_reports_coverage(app_db, tmp_path):
    nodes = tmp_path / "n.csv"
    edges = tmp_path / "e.csv"
    nodes.write_text("code,kind,floor,room,label\nE1,entrance,1,,Giriş\nD1,door,1,IT-101,\n", encoding="utf-8")
    edges.write_text("from,to,length_m,step_free\nE1,D1,7,1\nE1,NOPE,3,1\n", encoding="utf-8")
    cmd = [sys.executable, str(ROOT / "backend" / "manage.py"), "import-routes", "--building", "IT", "--nodes", str(nodes), "--edges", str(edges)]
    env = {**os.environ, "ZEKA_DATA": str(store.DATA)}
    bad = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
    assert bad.returncode == 1 and "edges.csv:3: both ends must be different nodes" in bad.stderr and "nothing imported" in bad.stderr
    c = db()
    try:
        assert len(repo.graph(c, repo.building_by_code(c, "IT")["id"])[0]) == 7, "the old graph is kept"
    finally:
        c.close()
    edges.write_text("from,to,length_m,step_free\nE1,D1,7,1\n", encoding="utf-8")
    ok = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
    assert ok.returncode == 0 and "IT: 2 nodes, 1 edges" in ok.stdout and "rooms without a door node: IT-214" in ok.stdout
    c = db()
    try:
        assert service.route(c, "IT-214")["missing"] == "no_node" and service.route(c, "IT-101")["length_m"] == 7
        demo = [list(csv.DictReader((ROOT / "content" / "routes" / f).read_text(encoding="utf-8").splitlines()))
                for f in ("IT.nodes.csv", "IT.edges.csv")]
        r = service.import_graph(c, "IT", *demo)
        c.commit()
        assert r["ok"] and r["coverage"]["no_step_free_route"] == []
    finally:
        c.close()


# ---------------------------------------------------------------- Checkpoint E (area F)
def test_a_longer_room_code_is_not_taken_for_a_shorter_one(monkeypatch):
    """PY-E8: with EK-12 and EK-121, "EK-121 haradadır?" answered with both, so EK-121 could never be picked."""
    from zeka.modules.assistant import service as assistant
    rooms = [{"id": 1, "code": "EK-12", "number": "12", "name": None}, {"id": 2, "code": "EK-121", "number": "121", "name": None}]
    monkeypatch.setattr(service, "rooms_for_search", lambda c: rooms)
    assert [r["code"] for r in assistant.find_rooms(None, "EK-121 haradadır?")] == ["EK-121"]
    assert [r["code"] for r in assistant.find_rooms(None, "EK-12 haradadır?")] == ["EK-12"]
    assert [r["code"] for r in assistant.find_rooms(None, "EK-12 və EK-121 harda yerləşir?")] == ["EK-12", "EK-121"]


def test_a_teacher_acting_in_another_role_still_finds_their_next_lesson(app_db):
    """SF-E10: any role but student read None, so "no lessons" was claimed without a lookup."""
    from zeka.modules.assistant import service as assistant
    teacher = app_db.client("teacher").user
    c = db()
    try:
        as_teacher = assistant.next_lesson(c, {"id": teacher["id"], "role": "teacher"})
        as_office = assistant.next_lesson(c, {"id": teacher["id"], "role": "office"})
    finally:
        c.close()
    assert as_teacher and as_office == as_teacher


def test_a_room_link_takes_any_room_code_and_a_link_without_one_is_not_drawn():
    """SF-E15: İT-214, ƏK-101 and EK.101 failed chat.js's pattern and fell through to a request button with no service."""
    import re
    import shutil
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("node is not installed")
    src = (ROOT / "frontend" / "js" / "chat.js").read_text(encoding="utf-8")
    pattern = re.search(r'\? \((/\^.+?\$/u)\.test\(a\.href', src).group(1)
    probe = f"const re = {pattern}; console.log(JSON.stringify(['/r/İT-214', '/r/ƏK-101', '/r/EK.101', '/office-hours', '/r/', '/x', '/r/a b'].map((h) => re.test(h))))"
    got = subprocess.run([node, "-e", probe], capture_output=True, text=True, timeout=30).stdout.strip()
    assert got == "[true,true,true,true,false,false,false]", got
    assert ': a.code ? html`<button class="btn btn-primary btn-sm" data-request=' in src, "no request button without a service"


def test_import_routes_keeps_a_label_with_a_line_separator(app_db, tmp_path):
    """PY-E11: splitlines() split a U+2028 inside a label and refused the file with misleading errors."""
    nodes, edges = tmp_path / "n.csv", tmp_path / "e.csv"
    demo = (ROOT / "content" / "routes" / "IT.nodes.csv").read_text(encoding="utf-8").replace("İT korpusunun girişi", "İT korpusunun\u2028girişi", 1)
    assert "\u2028" in demo
    nodes.write_text(demo, encoding="utf-8")
    edges.write_text((ROOT / "content" / "routes" / "IT.edges.csv").read_text(encoding="utf-8"), encoding="utf-8")
    cmd = [sys.executable, str(ROOT / "backend" / "manage.py"), "import-routes", "--building", "IT", "--nodes", str(nodes), "--edges", str(edges)]
    r = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "ZEKA_DATA": str(store.DATA)}, timeout=60)
    assert r.returncode == 0, r.stderr
