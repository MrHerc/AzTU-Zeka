"""Checkpoint E, area D (docs/review/checkpoint-e-2026-11-19.md): exports and API keys. A row of the pull's second comes
back, a since outside 1900–2999 is a 400, an HTTP export has a row cap and runs in the slow slots, a revoked key in use is
audited, a source id shared by two rows names neither in any export, a OneRoster export says how many enrolments it
left out, and ``manage.py export --out`` checks its file first and keeps it private."""
import csv
import io
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from zeka.legacy import store
from zeka.modules.integration import domain, export, tokens

from .test_api_tokens import call, key, q

ROOT = Path(__file__).resolve().parents[2]


def test_a_row_written_in_the_pull_s_own_second_comes_back():
    """CR-E3: ``since`` is the second of the last pull; ``>`` lost a row written later in that second."""
    c = store.connect()
    try:
        g = store.row(c, "SELECT updated_at FROM grades WHERE updated_at IS NOT NULL ORDER BY updated_at DESC LIMIT 1")
        got = list(csv.DictReader(io.StringIO(export.grades_csv(c, datetime.fromisoformat(g["updated_at"])))))
    finally:
        c.close()
    assert g["updated_at"] in [r["updatedAt"] for r in got]


def test_a_since_outside_1900_to_2999_is_refused(app_db):
    """PY-E2: 0001-01-01T00:00+04:00 parsed and overflowed later, inside the export."""
    for bad in ("0001-01-01T00:00:00+04:00", "9999-12-31T23:59:59-04:00", "1899-12-31"):
        with pytest.raises(ValueError):
            domain.moment(bad)
    assert domain.moment("2026-12-01T00:00:00+04:00").year == 2026
    assert app_db.client("admin").get("/api/integration/export/grades?since=0001-01-01T00:00:00%2B04:00").status == 400


def test_an_http_export_has_a_row_cap_and_runs_in_the_slow_slots(app_db, monkeypatch):
    """AR-E1: a full export of 1.2 M marks took 13.7 s and 1.7 GB inside a regular handler slot."""
    monkeypatch.setattr(export, "HTTP_CAP", 1)
    r = app_db.client("admin").get("/api/integration/export/grades")
    assert r.status == 400 and "manage.py export" in r.json["error"]
    k = key(app_db, ["grades.read"], name="Böyük eksport")
    assert call(app_db, "/api/v1/grades", k["token"]) == 400
    out = subprocess.run([sys.executable, str(ROOT / "backend" / "manage.py"), "export", "--kind", "grades"], capture_output=True,
                         env={**os.environ, "ZEKA_DATA": str(store.DATA)}, timeout=120)
    assert out.returncode == 0 and out.stdout.count(b"\n") > 2, "the command line has no cap"
    matrix = json.loads((ROOT / "tests" / "security" / "matrix.json").read_text(encoding="utf-8"))
    for route in ("GET /api/integration/export/{kind}", "GET /api/v1/grades", "GET /api/v1/attendance", "GET /api/v1/oneroster.zip"):
        assert matrix[route]["slow"] is True, route


def test_a_revoked_key_in_use_is_audited_and_an_unknown_one_is_not(app_db):
    """SF-E11: a 401 left no trace, even for a revoked key that some system still sends."""
    k = key(app_db, ["grades.read"], name="Köhnə inteqrasiya")
    assert app_db.client("admin").post(f"/api/integration/keys/{k['id']}/revoke").status == 200
    assert call(app_db, "/api/v1/grades", k["token"]) == 401
    assert q("SELECT 1 FROM audit WHERE action='api_call_revoked' AND detail=?", (f"#{k['id']} /api/v1/grades",))
    before = q("SELECT COUNT(*) n FROM audit")[0]["n"]
    assert call(app_db, "/api/v1/grades", "zk_not-a-key") == 401
    assert q("SELECT COUNT(*) n FROM audit")[0]["n"] == before, "anonymous 401s do not fill the audit log"


def test_one_limiter_per_limit_value(app_db):
    """AR-E9: a RateLimiter was built on every call."""
    tokens._LIMITERS.clear()
    k = key(app_db, ["grades.read"], per_minute=37, name="Limit açarı")
    assert call(app_db, "/api/v1/grades", k["token"]) == 200
    first = tokens._LIMITERS[37]
    assert call(app_db, "/api/v1/grades", k["token"]) == 200
    assert list(tokens._LIMITERS) == [37] and tokens._LIMITERS[37] is first


def test_a_source_id_shared_by_two_rows_names_neither_in_any_export():
    """The refuter's side finding: the check ran per export, so a person got different ids in different files; and an
    export with no rows read the whole link table (AR-E13)."""
    assert export._sids(None, "users", set()) == {}
    c = store.connect()
    try:
        a, b = [r["id"] for r in store.rows(c, "SELECT id FROM users WHERE role='student' ORDER BY id LIMIT 2")]
        kind = export.LINKS["users"][0]
        for system, uid in (("sis-a", a), ("sis-b", b)):
            c.execute("INSERT INTO import_links(kind,source_system,source_id,row_id,source_hash,imported_at) VALUES(?,?,?,?,?,?)",
                      (kind, system, "SHARED-1", uid, "x", "2026-01-01T00:00:00"))
        assert export._sids(c, "users", [a]) == {a: f"zeka:users:{a}"}
        assert export._sids(c, "users", [a, b]) == {a: f"zeka:users:{a}", b: f"zeka:users:{b}"}
    finally:
        c.rollback()
        c.close()


def test_a_oneroster_export_says_how_many_enrolments_it_left_out():
    """SF-E5: an enrolment in a course with no class the student attends is not listed; the audit said nothing."""
    c = store.connect()
    try:
        sid = store.row(c, "SELECT id FROM users WHERE role='student' ORDER BY id LIMIT 1")["id"]
        cid = c.execute("INSERT INTO courses(code,name,credits) VALUES('NOUNIT-1','Bölməsiz fənn',3)").lastrowid
        c.execute("INSERT INTO enrollments(user_id,course_id) VALUES(?,?)", (sid, cid))
        export.run(c, "oneroster")
        detail = store.row(c, "SELECT detail FROM audit WHERE action='export' AND entity='oneroster' ORDER BY id DESC LIMIT 1")["detail"]
    finally:
        c.rollback()
        c.close()
    assert detail.startswith("enrolments left out ") and int(detail.split()[-1]) >= 1


def test_export_out_checks_its_file_first_and_keeps_it_private(tmp_path):
    """SF-E14 / TM-E15: a bad path failed after the audit row was committed, and the file was 0644."""
    cmd = [sys.executable, str(ROOT / "backend" / "manage.py"), "export", "--kind", "registry", "--out"]
    env = {**os.environ, "ZEKA_DATA": str(store.DATA)}
    before = q("SELECT COUNT(*) n FROM audit WHERE action='export'")[0]["n"]
    bad = subprocess.run([*cmd, str(tmp_path / "no" / "such" / "dir.csv")], capture_output=True, text=True, env=env, timeout=120)
    assert bad.returncode == 2 and "Traceback" not in bad.stderr
    assert q("SELECT COUNT(*) n FROM audit WHERE action='export'")[0]["n"] == before, "nothing exported, nothing audited"
    out = tmp_path / "registry.csv"
    out.write_text("old")
    os.chmod(out, 0o644)
    ok = subprocess.run([*cmd, str(out)], capture_output=True, text=True, env=env, timeout=120)
    assert ok.returncode == 0 and out.read_text(encoding="utf-8").startswith("student_no,")
    if os.name == "posix":
        assert out.stat().st_mode & 0o777 == 0o600
