"""No full scan of a large table on the read routes (tasks/todo.md, Task 7).

tools/queryplan.py builds the university dataset (10 000 students, 100 000 attempts, 100 000 chunks) in its own process,
sends the read scenario of tools/loadtest.py as a student and explains every statement the handlers ran.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.slow


def test_the_read_routes_never_scan_a_table_with_more_than_1000_rows():
    env = {k: v for k, v in os.environ.items() if not k.startswith("ZEKA_")}
    run = subprocess.run([sys.executable, str(ROOT / "tools" / "queryplan.py"), "--dataset", "university"],
                         env={**env, "PYTHONIOENCODING": "utf-8"}, capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert run.returncode in (0, 1), run.stderr[-2000:]
    report = json.loads(run.stdout)
    assert report["statements"] > 50, report          # the routes really ran
    assert report["scans"] == {}, json.dumps(report["scans"], ensure_ascii=False, indent=1)
