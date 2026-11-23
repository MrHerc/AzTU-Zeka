"""The syllabus approval in a real browser (tests/e2e/syllabus.js): the demo's department head and academic office from the
login page, the coverage report's "Bax", the editor's fields at 1280 and 390 px with the warnings, the picker, and the
reviewer's window through return, resubmission, approval and publication (the acceptance walk and audit of 2026-11-23).
A NICE sample is imported for the coverage report. Skipped without node and Playwright, like test_tt_pages.py."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import manage
from zeka.legacy import store

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tests" / "e2e" / "syllabus.js"
SAMPLE = ROOT / "tests" / "fixtures" / "nice_sample.json"


def _playwright() -> bool:
    node = shutil.which("node")
    return bool(node) and subprocess.run([node, "-e", "require('playwright')"], capture_output=True, timeout=30,
                                         cwd=SCRIPT.parent).returncode == 0


pytestmark = pytest.mark.skipif(not _playwright(), reason="node with Playwright is not installed")


@pytest.fixture(scope="module")
def seen(app_db):
    assert manage.main(["import-framework", "--file", str(SAMPLE)]) == 0
    c = store.connect()
    try:
        cid = store.row(c, "SELECT id FROM courses WHERE code='ELM-2105'")["id"]
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


def test_the_login_page_offers_the_department_head_and_the_academic_office(seen):
    # walk D1: no demo role reached the department head's or the academic office's step
    s = got(seen, "login")
    assert {"dept_head", "academic_office"} <= set(s["cards"]) and s["role"] == "dept_head", s


def test_a_coverage_rows_button_opens_its_card_and_signs_nobody_in(seen):
    # walk D2: the login page's [data-role] handler stayed on #root and posted the work role's code to /api/auth/demo
    s = got(seen, "coverage")
    assert s["demoPosts"] == 0 and not s["toasts"], s
    assert s["card"], s


def test_the_editors_outcome_and_week_fields_are_readable_and_warn(seen):
    # walk D3: the outcome field was 100 px at 1280 and 48 at 390, a week's topic 51 px; plus the warnings (no block)
    s = got(seen, "editor")
    for width, low in (("1280", 500), ("390", 250)):
        for field in ("outcome", "topic", "activity"):
            assert s["seen"][width][field]["tag"] == "TEXTAREA" and s["seen"][width][field]["width"] >= low, (width, field, s["seen"])
        assert s["seen"][width]["pageScroll"] <= 0, s["seen"]
    assert "N2" in s["first"] and "Bloom bəndi isə «Qiymətləndirmə»" in s["first"] and "qiymətləndirilməyən nəticələr: N1, N2" in s["first"]
    assert "qiymətləndirilməyən nəticələr: N1" in s["after"] and "N1, N2" not in s["after"].split("qiymətləndirilməyən")[1]
    assert s["assessBoxes"] > 0


def test_the_picker_resets_its_search_and_lists_bloom_by_level(seen):
    # walk D6
    s = got(seen, "picker")
    assert s["q"] == "" and s["codes"] == ["remember", "understand", "apply", "analyze", "evaluate", "create"], s


def test_the_reviewer_reads_everything_approved_and_the_toast_names_the_step(seen):
    # walk D4 and D7
    s = got(seen, "review")
    for part in ("BLOOM", "evaluate", "Elektrik dövrələrinin nəzəriyyəsi, dərslik", "Mühazirə, sonra kiçik qruplarda məsələ həlli",
                 "Prerekvizitlər", "Gecikmiş işlər", "Fənnin təsviri", "Çap görünüşü", "Bloom bəndi isə"):
        assert part in s["text"], part
    assert s["print"].startswith("/syllabus/") and "v=" in s["print"]
    assert s["returned"] == "Sillabus geri qaytarıldı"


def test_a_resubmission_shows_its_difference_from_the_returned_version(seen):
    # walk D5: the queue said «ilk dərc» and listed nothing
    s = got(seen, "resubmit")
    assert "Geri qaytarılmış versiyadan fərq: 1" in s["row"], s["row"]
    assert "Geri qaytarılmış versiyadan fərq (versiya" in s["text"] and "Ədəbiyyatı tamamlayın" in s["text"]
    assert s["approved"] == "Sillabus təsdiqləndi"


def test_a_ticked_permission_without_a_reason_says_so_and_publication_is_named(seen):
    # walk D7
    s = got(seen, "publish")
    assert "xüsusi icazəsi" in s["blocked"] and s["noReason"] == "Xüsusi icazənin səbəbini şərhdə yazın" and s["done"] == "Sillabus dərc olundu", s
