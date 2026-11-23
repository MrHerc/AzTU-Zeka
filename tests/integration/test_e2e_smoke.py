"""Smoke test in a real browser (tasks/todo.md, Task 42): every role of perms.ROLES × az, en, ru × desktop and mobile opens
its home and every entry of its navigation (tests/e2e/smoke.js, one node run of about a minute). The demo login has
five roles; dept_head and proctor are granted to the demo teacher here, the demo dean's office holds academic_office.
Skipped without node and Playwright, like test_exam_page.py."""
import json
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

import pytest

from zeka.core import perms

SCRIPT = Path(__file__).resolve().parents[1] / "e2e" / "smoke.js"


def _playwright() -> bool:
    node = shutil.which("node")
    return bool(node) and subprocess.run([node, "-e", "require('playwright')"], capture_output=True, timeout=30).returncode == 0


pytestmark = pytest.mark.skipif(not _playwright(), reason="node with Playwright is not installed")


@pytest.fixture(scope="module")
def seen(app_db):
    admin, teacher = app_db.client("admin"), app_db.client("teacher")
    faculty = admin.get("/api/directory/faculties").json["items"][0]["id"]
    for grant in ({"role": "dept_head", "scope_type": "faculty", "scope_id": faculty}, {"role": "proctor"}):
        r = admin.post(f"/api/admin/users/{teacher.user['id']}/roles", grant)
        assert r.status == 200, r.text
    n0 = len(app_db.errors)
    run = subprocess.run([shutil.which("node"), str(SCRIPT), app_db.url], capture_output=True, text=True, timeout=900)
    # TE-F11: a 500 during the node run happens before any test's own server-error guard: report it here, with its cause
    assert not app_db.errors[n0:], "the server logged an exception during the browser run:\n" + "\n".join(app_db.errors[n0:])
    assert run.stdout.strip(), run.stderr
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert "fatal" not in out, out["fatal"]
    return out


def report(failures):
    by = defaultdict(list)
    for f in failures:
        by[(f["kind"], f["path"], f["detail"])].append(f["combo"])
    return "\n".join(f"{k[0]} {k[1]}: {k[2]}\n    in {', '.join(sorted(v))}" for k, v in sorted(by.items()))


def test_every_role_language_and_viewport_was_opened(seen):
    assert seen["combos"] == len(perms.ROLES) * 3 * 2
    assert seen["pages"] >= seen["combos"] * 4, "each combination opens its home and its NAV entries"


def test_no_page_breaks(seen):
    broken = [f for f in seen["failures"] if f["kind"] != "untranslated"]
    assert not broken, report(broken)


def test_nav_labels_are_translated(seen):
    left = [f for f in seen["failures"] if f["kind"] == "untranslated"]
    assert not left, report(left)
