"""Browser regression tests for the Checkpoint E fixes of the club page (frontend/js/community.js; area B of
docs/review/checkpoint-e-2026-11-19.md). One node run (tests/e2e/clubs.js, Playwright, fake clock, page.route())
sees every scenario; each test below asserts one finding. Skipped without node and Playwright, like test_exam_page.py."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from .test_community import build_club

SCRIPT = Path(__file__).resolve().parents[1] / "e2e" / "clubs.js"


def _playwright() -> bool:
    node = shutil.which("node")
    return bool(node) and subprocess.run([node, "-e", "require('playwright')"], capture_output=True, timeout=30).returncode == 0


pytestmark = pytest.mark.skipif(not _playwright(), reason="node with Playwright is not installed")


@pytest.fixture(scope="module")
def seen(app_db):
    w = build_club(app_db, "kbui")
    assert w["lead"].post(f"/api/channels/{w['announce']}/messages", {"text": "Elan: cümə günü toplantı"}).status == 200
    run = subprocess.run([shutil.which("node"), str(SCRIPT), app_db.url, str(w["club"]), str(w["chat"]), str(w["announce"]),
                          w["member"].user["username"], w["lead"].user["username"]], capture_output=True, text=True, timeout=240)
    assert run.stdout.strip(), run.stderr
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert "fatal" not in out, out["fatal"]
    return out


def got(seen, key):
    assert "error" not in seen[key], seen[key]
    return seen[key]


def test_a_late_reply_of_another_channel_is_not_shown(seen):
    shown = got(seen, "SF-E8-channel")["shown"]
    assert "Xoş gəldiniz!" not in shown and "Elan: cümə günü toplantı" in shown, shown


def test_a_send_during_a_poll_leaves_one_polling_loop(seen):
    assert got(seen, "SF-E8-loops")["gets"] <= 4, "3 s polling over 9 s: three or four GETs, not two loops"


def test_a_hidden_message_leaves_the_member_s_page(seen):
    s = got(seen, "SF-E8-hidden")
    assert s["shown_before"] and not s["shown_after"]


def test_a_hidden_tab_does_not_poll(seen):
    s = got(seen, "SF-E8-hidden-tab")
    assert s["hidden"] == 0 and s["visible"] >= 1


def test_failing_polls_are_shown_and_cleared(seen):
    s = got(seen, "SF-E7")
    assert s["during"].strip() and not s["afterwards"].strip()


def test_a_failing_pending_list_is_an_error_not_an_empty_card(seen):
    s = got(seen, "SF-E9")
    assert s["error_shown"] and not s["empty_shown"]
