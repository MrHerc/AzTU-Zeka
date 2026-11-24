"""The syllabus items of the audit of 2026-11-23 in a real browser (tests/e2e/syllabus_registry.js): a new exam's
defaults from the published syllabus, a draft copied from the course's earlier offering, a prerequisite picked from the
registry and kept after a save, the term overview's state filter and CSV link, and the queue's second page. Skipped
without node and Playwright, like test_syllabus_pages.py."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from zeka.legacy import store

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tests" / "e2e" / "syllabus_registry.js"
T = "2026-11-01T09:00:00"


def _playwright() -> bool:
    node = shutil.which("node")
    return bool(node) and subprocess.run([node, "-e", "require('playwright')"], capture_output=True, timeout=30,
                                         cwd=SCRIPT.parent).returncode == 0


pytestmark = pytest.mark.skipif(not _playwright(), reason="node with Playwright is not installed")

DATA = {"description": "", "outcomes": [{"id": "N1", "text": "Dövrəni təhlil edir və hesablayır", "bloom": "analyze"}],
        "plan": [{"week": 1, "topic": "Giriş mövzusu", "outcomes": ["N1"], "activity": ""}],
        "assessment": [{"name": "Davamiyyət", "kind": "attendance", "weight": 10, "outcomes": []},
                       {"name": "Layihə işi", "kind": "component", "weight": 40, "outcomes": ["N1"]},
                       {"name": "Yekun imtahan", "kind": "exam", "weight": 50, "outcomes": ["N1"]}],
        "rules": {"attendance_limit": 20, "ai_policy": "limited", "late_policy": "", "ai_note": ""},
        "prerequisites": [], "literature": [], "workload": {"lecture": 30, "seminar": 30, "lab": 0, "independent": 60}}


@pytest.fixture(scope="module")
def seen(app_db):
    c = store.connect()
    try:
        co = store.row(c, "SELECT * FROM courses WHERE code='ELM-2105'")
        other = store.row(c, "SELECT id FROM users WHERE username='elcin'")["id"]
        blob = json.dumps(DATA, ensure_ascii=False)
        add = "INSERT INTO syllabus_versions(course_id,version,status,data,created_at,tags) VALUES(?,?,?,?,?,'{}')"
        c.execute(add, (co["id"], 1, "published", blob, T))
        old = c.execute("INSERT INTO academic_terms(code,name,teaching_start,teaching_end,exam_start,exam_end,active,created_at,updated_at) "
                        "VALUES('2024-P','2024 payız','2024-09-15','2024-12-28','2025-01-05','2025-01-30',0,?,?)", (T, T)).lastrowid
        new = "INSERT INTO courses(code,name,teacher_id,credits,color,department_id,term_id,active,created_at,updated_at) VALUES(?,?,?,5,'#777',?,?,1,?,?)"
        src = c.execute(new, ("ELM-2105", co["name"], other, co["department_id"], old, T, T)).lastrowid
        c.execute(add, (src, 1, "published", blob, T))
        for k in range(55):                              # more than a page of the academic office's queue
            cid = c.execute(new, (f"QQ-{k:02d}", f"Növbə sınağı {k}", other, co["department_id"], co["term_id"], T, T)).lastrowid
            c.execute(add, (cid, 1, "approved", blob, T))
        c.commit()
        cid = co["id"]
    finally:
        c.close()
    r = subprocess.run([shutil.which("node"), str(SCRIPT), app_db.url, str(cid)], capture_output=True, text=True, timeout=300)
    assert r.stdout.strip(), r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert "fatal" not in out, out["fatal"]
    return out


def got(seen, key):
    assert "error" not in seen[key], seen[key]["error"]
    assert not seen[key].get("errors"), seen[key]["errors"]
    return seen[key]


def test_a_new_exam_starts_from_the_published_syllabus(seen):
    s = got(seen, "exam")
    assert "Dərc olunmuş sillabusa görə: «Yekun imtahan», çəkisi 50 bal." in s["note"] and "N1" in s["note"], s
    assert s["title"] == "Yekun imtahan", s


def test_a_draft_is_copied_from_the_course_s_earlier_offering_and_names_its_source(seen):
    s = got(seen, "copy")
    assert "ELM-2105" in s["offered"] and "2024 payız" in s["offered"], s
    assert s["toast"] == "Sillabus köçürüldü: versiya 2", s
    assert s["source"].startswith("Köçürülüb: ELM-2105 · ") and "2024 payız, versiya 1" in s["source"], s


def test_a_prerequisite_is_picked_from_the_registry_and_kept_by_its_name(seen):
    s = got(seen, "prereq")
    assert any(x.startswith("RİY-1101") for x in s["offered"]), s
    assert any(x.startswith("RİY-1101 · Ali riyaziyyat I") for x in s["chips"]), s
    assert s["saved"] == "Versiya 3 saxlanıldı" and any(x.startswith("RİY-1101 · Ali riyaziyyat I") for x in s["after"]), s
    assert s["narrow"] <= 0, s


def test_the_overview_filters_by_state_and_offers_a_csv(seen):
    s = got(seen, "overview")
    assert s["counts"]["approved"] >= 55 and s["counts"]["none"] > 0 and s["counts"]["draft"] >= 1, s
    assert "format=csv" in s["csv"], s
    assert s["states"] == ["Sillabus yoxdur"] and s["rows"] == s["counts"]["none"], s
    assert s["narrow"] <= 0, s


def test_the_queue_has_a_second_page(seen):
    s = got(seen, "queue")
    assert len(s["first"]) == 50 and s["second"] and not set(s["first"]) & set(s["second"]), s
    assert s["pager"].startswith("Səhifə 1 / 2"), s
