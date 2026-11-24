"""The timetable builder's deferred page parts in a real browser (tasks/todo.md, Task 48; tests/e2e/tt_more.js): the room
editor's «open for the timetable» and «reserved» boxes, the Forma №3 preview's department per post, and the published
version's daily check with its repair button. Synthetic data only (tests/fixtures/forma3_blocks.xlsx). Skipped without
node and Playwright, like test_tt_pages.py."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from zeka.legacy import store

SCRIPT = Path(__file__).resolve().parents[1] / "e2e" / "tt_more.js"
FIX = Path(__file__).resolve().parents[1] / "fixtures" / "forma3_blocks.xlsx"
TODAY = "2026-11-19"                                # the suite's date (tests/conftest.py)


def _playwright() -> bool:
    node = shutil.which("node")
    return bool(node) and subprocess.run([node, "-e", "require('playwright')"], capture_output=True, timeout=30).returncode == 0


pytestmark = pytest.mark.skipif(not _playwright(), reason="node with Playwright is not installed")


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def world(app_db) -> dict:
    office = app_db.client("office")
    assert office.post("/api/me/role", {"role": "academic_office"}).status == 200
    value = office.get("/api/timetable/settings").json["timetable"]
    value["shifts"].pop("evening", None)                              # the demo has six pairs: no evening shift
    assert office.put("/api/timetable/settings", {"value": value}).status == 200
    c = store.connect()
    try:
        now = store.iso(store.now())
        fid = c.execute("SELECT id FROM faculties ORDER BY id LIMIT 1").fetchone()[0]
        deps = [c.execute("INSERT INTO departments(faculty_id,code,name,active,created_at,updated_at) VALUES(?,?,?,1,?,?)",
                          (fid, f"TTM{k}", f"Sınaq kafedrası {k}", now, now)).lastrowid for k in (1, 2)]
        for g in ("6524a1", "6524a2", "6524a3"):
            c.execute("INSERT INTO study_groups(name,year,faculty_id,active) VALUES(?,2025,?,1)", (g, fid))
        for name, patronymic, username in (("Elçin Quliyev", "Rauf oğlu", "e.quliyev"), ("Leyla Həsənova", "Akif qızı", "l.hesenova")):
            c.execute("INSERT INTO users(username,full_name,patronymic,role,title,color,department_id,synthetic,consent_at) "
                      "VALUES(?,?,?,'teacher','','#333',?,1,?)", (username, name, patronymic, deps[0], now))
        courses = {d: c.execute("INSERT INTO courses(code,name,credits,color,department_id,term_id,active,created_at,updated_at) "
                                "VALUES(?,'Alqoritmlər',5,'#777',?,1,1,?,?)", (f"ALQ-TTM{k}", d, now, now)).lastrowid
                   for k, d in enumerate(deps)}
        unit = c.execute("SELECT u.id FROM teaching_units u JOIN courses co ON co.id=u.course_id WHERE co.term_id=1 AND u.active=1 "
                         "AND co.active=1 ORDER BY u.id LIMIT 1").fetchone()[0]
        problem = {"code": "teacher_unavailable", "keys": [f"{unit}:0"], "slot": [2, 3], "weeks": "all"}
        health = {"at": now, "count": 1, "problems": [problem], "seen": [f"teacher_unavailable|{unit}:0|2,3"]}
        c.execute("INSERT INTO tt_versions(term_id,status,scope,rev,created_by,created_at,published_at,effective_from,health) "
                  "VALUES(1,'published','{\"all\": true}',0,?,?,?,?,?)", (office.user["id"], now, now, TODAY, json.dumps(health)))
        c.commit()
    finally:
        c.close()
    return {"deps": deps, "courses": courses}


@pytest.fixture(scope="module")
def seen(app_db):
    w = world(app_db)
    r = subprocess.run([shutil.which("node"), str(SCRIPT), app_db.url, TODAY, str(FIX)], capture_output=True, text=True, timeout=300)
    assert r.stdout.strip(), r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert "fatal" not in out, out["fatal"]
    out["world"] = w
    return out


def got(seen, key):
    assert "error" not in seen[key], seen[key]["error"]
    assert not seen[key].get("errors"), seen[key]["errors"]
    return seen[key]


def test_the_room_editor_opens_a_new_room_and_closes_or_reserves_one(seen):
    s = got(seen, "rooms")
    assert s["fresh"]["schedulable"] == "1" and s["fresh"]["dedicated"] == "0", "a new room is open to the timetable and shared"
    assert "Cədvəl qurucusu" in s["fresh"]["label"] and s["saved"] == "Saxlanıldı"
    assert q("SELECT schedulable, dedicated FROM rooms WHERE code=?", (s["code"],)) == [{"schedulable": 0, "dedicated": 1}]


def test_the_forma3_preview_lets_the_office_choose_the_department_of_a_post(seen):
    s = got(seen, "import")
    w = seen["world"]
    assert s["hint"] and s["resetRun"], "a new choice needs a new check before the import"
    assert int(s["pick"]["value"]) == w["deps"][0], "the file's department until the office chooses"
    assert s["done"] == "İdxal olundu"
    mine = q("SELECT DISTINCT u.course_id FROM teaching_units u JOIN import_links l ON l.row_id=u.id AND l.kind='teaching_load' "
             "WHERE l.source_system='f3-pick' AND u.post_ref=? AND u.course_id IN (?,?)", (s["pick"]["post"], *w["courses"].values()))
    assert [x["course_id"] for x in mine] == [w["courses"][s["other"]]], mine
    assert q("SELECT 1 FROM audit WHERE action='import_department' AND detail LIKE ?", (f"%{s['pick']['post']} → {s['other']}%",))


def test_the_builder_shows_the_daily_check_and_starts_a_repair(seen):
    s = got(seen, "health")
    assert s["count"] == 1 and "Müəllim bu vaxtı məşğul kimi qeyd edib" in s["text"], s["text"]
    assert s["queued"] == "Hesablama növbəyə qoyuldu" and "Bərpa layihəsi" in s["card"], s
    assert q("SELECT kind, json_extract(scope, '$.repair') repair FROM tt_runs ORDER BY id DESC LIMIT 1") == [{"kind": "repair", "repair": 1}]
