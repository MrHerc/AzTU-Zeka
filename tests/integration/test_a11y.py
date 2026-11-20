"""axe-core on the ten main pages (tasks/todo.md, Task 42): no WCAG 2.2 AA violation of impact "serious" or "critical",
on a desktop and on a phone (tests/e2e/a11y.js). axe-core is tests/e2e/node_modules/axe-core (npm ci --prefix tests/e2e)
or the axe.min.js named by AXE_CORE; skipped without it, or without node and Playwright."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "e2e" / "a11y.js"
PAGES = ("sign-in", "student-home", "student-schedule", "tutor", "e-services", "teacher-home", "teacher-course",
         "office-requests", "leader-dashboard", "admin-settings")


def _node_has(expr: str) -> bool:
    node = shutil.which("node")
    return bool(node) and subprocess.run([node, "-e", expr], capture_output=True, timeout=30, cwd=SCRIPT.parent).returncode == 0


def _axe() -> bool:
    return os.path.isfile(os.environ.get("AXE_CORE", "")) or _node_has("require.resolve('axe-core')")


pytestmark = [pytest.mark.skipif(not _node_has("require('playwright')"), reason="node with Playwright is not installed"),
              pytest.mark.skipif(not _axe(), reason="axe-core not found: npm ci --prefix tests/e2e, or AXE_CORE=<path of axe.min.js>")]


@pytest.fixture(scope="module")
def seen(app_db):
    course = app_db.client("teacher").get("/api/courses").json[0]["id"]
    run = subprocess.run([shutil.which("node"), str(SCRIPT), app_db.url, str(course)], capture_output=True, text=True, timeout=600)
    assert run.stdout.strip(), run.stderr
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert "fatal" not in out, out["fatal"]
    assert {k.split("/")[0] for k in out} == set(PAGES)
    return out


@pytest.mark.parametrize("page", PAGES)
def test_no_serious_or_critical_violation(seen, page):
    for view in ("desktop", "mobile"):
        got = seen[f"{page}/{view}"]
        assert "error" not in got, got["error"]
        bad = [v for v in got["violations"] if v["impact"] in ("serious", "critical")]
        assert not bad, f"{got['url']} ({view}):\n" + "\n".join(f"{v['impact']} {v['id']} ({v['help']}), {v['count']}×: {v['targets']}" for v in bad)
