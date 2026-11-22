"""The timetable builder's pages in a real browser (tasks/todo.md, Task 48, slice 3; tests/e2e/timetable.js).

A synthetic department of the demo's current term comes from the synthetic Forma №3 (tests/fixtures/forma3_blocks.xlsx,
imported by the administrator through the API); the demo teacher teaches one of its units. The demo dean's office acts
as department head of it (a grant), as dean's office of the demo faculty (seeded) and as the unscoped academic office
(seeded); the demo teacher also gets an academic-office grant scoped to the faculty, which must not publish. The job
runner is worked here while the browser waits for runs. Skipped without node and Playwright, like test_exam_page.py."""
import base64
import json
import re
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from zeka.core import jobs
from zeka.legacy import periodic, store             # noqa: F401  periodic registers timetable.work

SCRIPT = Path(__file__).resolve().parents[1] / "e2e" / "timetable.js"
FIX = Path(__file__).resolve().parents[1] / "fixtures"
TODAY = "2026-11-19"                                # the suite's date (tests/conftest.py)


def _playwright() -> bool:
    node = shutil.which("node")
    return bool(node) and subprocess.run([node, "-e", "require('playwright')"], capture_output=True, timeout=30).returncode == 0


pytestmark = pytest.mark.skipif(not _playwright(), reason="node with Playwright is not installed")


def world(app_db) -> dict:
    admin, nigar = app_db.client("admin"), app_db.client("office").user["id"]       # the demo's dean's office
    c = store.connect()
    try:
        now = store.iso(store.now())
        fid = c.execute("SELECT id FROM faculties ORDER BY id LIMIT 1").fetchone()[0]
        dep = c.execute("INSERT INTO departments(faculty_id,code,name,active,created_at,updated_at) VALUES(?,'TTP','Sınaq kafedrası',1,?,?)",
                        (fid, now, now)).lastrowid
        groups = [c.execute("INSERT INTO study_groups(name,year,faculty_id,active) VALUES(?,2025,?,1)", (g, fid)).lastrowid
                  for g in ("6524a1", "6524a2", "6524a3")]
        for name, patronymic, username in (("Elçin Quliyev", "Rauf oğlu", "e.quliyev"), ("Leyla Həsənova", "Akif qızı", "l.hesenova")):
            c.execute("INSERT INTO users(username,full_name,patronymic,role,title,color,department_id,synthetic,consent_at) "
                      "VALUES(?,?,?,'teacher','','#333',?,1,?)", (username, name, patronymic, dep, now))
        for g in groups:
            for k in range(3):
                c.execute("INSERT INTO users(username,full_name,role,title,group_id,color,synthetic,consent_at) VALUES(?,?,'student','',?,'#555',1,?)",
                          (f"ttp.s{g}.{k}", f"Tələbə {g}-{k}", g, now))
        for code, name in (("ALQ-F3", "Alqoritmlər"), ("VB-F3", "Verilənlər bazaları"), ("FIZ-F3", "Fizika")):
            c.execute("INSERT INTO courses(code,name,credits,color,department_id,term_id,active,created_at,updated_at) VALUES(?,?,5,'#777',?,1,1,?,?)",
                      (code, name, dep, now, now))
        c.commit()
    finally:
        c.close()
    data = (FIX / "forma3_blocks.xlsx").read_bytes()
    r = admin.post("/api/admin/import", {"kind": "teaching-load", "source": "f3-a", "filename": "forma3_blocks.xlsx",
                                         "content_b64": base64.b64encode(data).decode(), "dry_run": False, "prefer_source": False})
    # the first block's five units; the others name groups, a subject or a person (two Leyla Həsənova) this registry lacks
    assert r.status == 200 and r.json["inserted"] == 5, r.text
    c = store.connect()
    try:
        rauf = store.row(c, "SELECT id FROM users WHERE username='rauf'")["id"]
        seminar = store.row(c, "SELECT u.id FROM teaching_units u JOIN courses co ON co.id=u.course_id WHERE co.code='VB-F3' "
                               "AND u.kind='seminar'")["id"]
        c.execute("UPDATE teaching_units SET teacher_id=? WHERE id=?", (rauf, seminar))     # the demo teacher teaches in the department
        c.execute("UPDATE users SET department_id=? WHERE id=?", (dep, rauf))
        c.commit()
    finally:
        c.close()
    for uid, grant in ((nigar, {"role": "dept_head", "scope_type": "department", "scope_id": dep}),
                       (rauf, {"role": "academic_office", "scope_type": "faculty", "scope_id": fid})):
        assert admin.post(f"/api/admin/users/{uid}/roles", grant).status == 200
    return {"dep": dep, "groups": groups, "rauf": rauf}


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


@pytest.fixture(scope="module")
def seen(app_db):
    w = world(app_db)
    node = subprocess.Popen([shutil.which("node"), str(SCRIPT), app_db.url, TODAY], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    c = store.connect()
    try:
        t, end = datetime(2027, 1, 1, tzinfo=timezone.utc), time.monotonic() + 600
        while node.poll() is None and time.monotonic() < end:        # the job runner, while the browser waits for runs
            if q("SELECT 1 FROM tt_runs WHERE status IN ('queued','running')"):
                t += timedelta(seconds=31)
                jobs.run_due(c, "tt-pages", now=t, names=["timetable.work"])
            time.sleep(0.3)
    finally:
        c.close()
    stdout, stderr = node.communicate(timeout=60)
    assert stdout.strip(), stderr
    out = json.loads(stdout.strip().splitlines()[-1])
    assert "fatal" not in out, out["fatal"]
    out["world"] = w
    return out


def got(seen, key):
    assert "error" not in seen[key], seen[key]["error"]
    assert not seen[key].get("errors"), seen[key]["errors"]
    return seen[key]


def test_the_academic_office_confirms_the_settings_and_the_run_is_no_longer_blocked(seen):
    s = got(seen, "plan")
    assert "hesablama" in s["blocked"] and "Hazırdır" in s["after"], s
    assert set(s["fixes"]) <= {"/admin/directory", "/admin/settings", "/office/timetable", "/dept/timetable", "/admin/timetable"}, s["fixes"]
    assert "həftə, gözlənilən" in s["termLine"] and "Hazırdır" in s["termLine"], s["termLine"]          # confirmed: no warning left
    assert s["fixedSlots"] == 1 and s["weeksExpected"] == 1


def test_every_readiness_fix_link_is_a_page_of_the_app():
    root = Path(__file__).resolve().parents[2]
    js = "".join(p.read_text(encoding="utf-8") for p in (root / "frontend" / "js").glob("*.js"))
    pages = set(re.findall(r'route\("([^"]+)"', js)) | set(re.findall(r'const ROOT = "([^"]+)"', js))
    fixes = set(re.findall(r'fix="(/[^"]+)"', (root / "backend/zeka/modules/timetable/domain.py").read_text(encoding="utf-8")))
    assert fixes and fixes <= pages, fixes - pages


def test_a_teacher_confirms_a_grid_and_one_above_the_cap_waits_for_the_head(seen):
    s = got(seen, "teacher")
    assert "Təsdiqlənib" in s["confirmed"]
    assert s["button"].strip() == "Kafedra müdirinə göndər" and "aşılıb" in s["meter"]
    assert "kafedra müdirinə" in s["sent"]
    assert "tək həftələr" in s["weeksCell"] and "odd" not in s["weeksCell"], s["weeksCell"]


def test_the_head_approves_the_pending_grid_and_saves_a_units_needs(seen):
    s = got(seen, "head")
    assert s["shown"] == 13 and s["decided"] == "Təsdiqləndi"
    assert "26 yer" in s["row"] and re.search(r"6524a[123]", s["row"]), s["row"]          # the unit's group is in its row
    assert "tək həftələr" in s["modalText"] and "Doktorantura seminarı" in s["modalText"]
    rauf = seen["world"]["rauf"]
    assert q("SELECT COUNT(*) n FROM tt_availability WHERE subject_id=? AND level='unavailable'", (rauf,))[0]["n"] == 13


def test_the_deans_office_sets_the_groups_shifts(seen):
    s = got(seen, "dean")
    assert s["groups"] >= 3 and s["saved"] == "Saxlanıldı" and "Qrupun növbəsi" in " ".join(s["heads"])
    assert {r["shift"] for r in q(f"SELECT shift FROM tt_group_terms WHERE group_id IN ({','.join(map(str, seen['world']['groups']))})")} == {"morning"}


def test_a_run_a_keyboard_move_with_reasons_in_text_and_a_check(seen):
    s = got(seen, "build")
    assert s["solved"] == "done" and s["checked"] == "done"
    assert s["draftMark"] == "LAYİHƏ" and s["title"].startswith("Layihə #")
    assert s["printFor"] == f"Qrup: {s['pickName']}" and not s["hintPrinted"], s        # the printed sheet says whose it is
    assert len(s["teachers"]) == len(set(s["teachers"])), s["teachers"]                # two people of one name told apart
    assert s["fixedRows"] > 0
    assert s["reason"], "a blocked slot says why in text"
    assert "mümkündür" in s["status"] and s["moved"] == "Dərs köçürüldü" and s["stale"] == "Yoxlanılmayıb"
    vid = int(s["url"].rsplit("/", 1)[1])
    wd, period = map(int, s["target"].split(":"))
    assert q("SELECT COUNT(*) n FROM tt_placements WHERE version_id=? AND weekday=? AND period=? AND origin='manual'", (vid, wd, period))[0]["n"] == 1


def test_publish_controls_are_absent_for_the_administrator_and_a_faculty_scoped_academic_office(seen):
    s = got(seen, "no-publish")
    assert s["admin"]["publish"] == 0 and s["admin"]["check"] == 1 and not s["admin"]["errors"]
    assert s["academic_office"]["publish"] == 0 and not s["academic_office"]["errors"]


def test_the_draft_is_published_after_a_wrong_unplaced_number_is_refused(seen):
    s = got(seen, "publish")
    assert "sayı" in s["refused"] and s["queued"] == "Dərc növbəyə qoyuldu" and s["published"] == "done"
    assert s["printed"] == 0, "a published version prints without the draft mark"
    assert s["title"].startswith("Versiya #") and s["hint"] == 0, s                       # nothing to drag on a published one
    vid = int(seen["build"]["url"].rsplit("/", 1)[1])
    assert q("SELECT status FROM tt_versions WHERE id=?", (vid,))[0]["status"] == "published"
    assert q("SELECT COUNT(*) n FROM timetable WHERE version_id=? AND active=1", (vid,))[0]["n"] > 0
