"""A migration wave (tasks/todo.md, Task 38): an old system's exports (tests/fixtures, written by make_fixtures.py) mapped
by content/mappings/sample-sis.json, loaded through Task 16's import and reconciled.

The registry of the wave (6 students of group ETL-1, courses ETL-C1 and ETL-C2 with one class each, their enrolments) is
loaded first from canonical files, as wave 0's earlier files would be; the term T-2026 is linked directly. The cut-over
date is 2026-11-10; the lesson records are of 2–6 November."""
import csv
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from zeka.legacy import store
from zeka.modules.exam import service as exam_service
from zeka.modules.integration import importer, tables
from zeka.modules.journal import service as journal
from zeka.modules.migration import domain, service as migration

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures"
MAPPING = ROOT / "content" / "mappings" / "sample-sis.json"
SOURCE, AS_OF, EXPORTED = "sample-sis", "2026-11-10", "2026-11-10T18:00:00+04:00"
sys.path.insert(0, str(ROOT / "tools" / "etl"))
# by path under its own name: backend/run.py is also a module called "run" (tests/integration/test_run.py imports it)
_spec = importlib.util.spec_from_file_location("zeka_etl_run", ROOT / "tools" / "etl" / "run.py")
etl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(etl)

NAMES = ["Aysu", "Nərmin", "Kamran", "Fidan", "Orxan", "Lalə"]


def q(statement, args=()):
    c = store.connect()
    try:
        return store.rows(c, statement, args)
    finally:
        c.close()


def sql(statement, args=()):
    c = store.connect()
    try:
        cur = c.execute(statement, args)
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def uid(sid):
    return q("SELECT row_id FROM import_links WHERE kind='users' AND source_system=? AND source_id=?", (SOURCE, sid))[0]["row_id"]


def course(code):
    return q("SELECT id FROM courses WHERE code=?", (code,))[0]["id"]


def reconcile(wave, folder):
    c = store.connect()
    try:
        return migration.reconcile(c, wave, SOURCE, folder)
    finally:
        c.close()


def load(wave, kind, name, text, folder):
    (folder / name).write_text(text, encoding="utf-8")
    c = store.connect()
    try:
        return migration.load(c, wave, SOURCE, kind, name, text.encode(), exported_at=EXPORTED)
    finally:
        c.close()


@pytest.fixture(scope="module")
def world(app_db, registrar, tmp_path_factory):
    admin = app_db.client("admin")
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    assert term["teaching_start"] <= "2026-11-02" <= term["teaching_end"], "the fixtures' lessons are in the demo term"
    fid = admin.get("/api/directory/faculties").json["items"][0]["id"]
    assert admin.post("/api/directory/groups", {"name": "ETL-1", "year": 2025, "faculty_id": fid}).status == 200
    sql("INSERT INTO import_links(kind,source_system,source_id,row_id,source_hash,imported_at) VALUES('terms',?,'T-2026',?,'-',?)",
        (SOURCE, term["id"], store.iso(store.now())))
    folder = tmp_path_factory.mktemp("wave0")
    registry = {
        "users": "sourcedId,username,givenName,familyName,role,identifier,group\n"
                 + "".join(f"ETL-S{i},etl.s{i},{n},Etlova,student,ETL-100{i},ETL-1\n" for i, n in enumerate(NAMES, 1)),
        "courses": "sourcedId,title,courseCode,termSourcedId,credits\nETL-C1,ETL sınağı bir,ETL-101,T-2026,5\n"
                   "ETL-C2,ETL sınağı iki,ETL-102,T-2026,4\n",
        "classes": "sourcedId,courseSourcedId,kind,subgroup,groups\nETL-K1,ETL-C1,lecture,,ETL-1\nETL-K2,ETL-C2,lecture,,ETL-1\n",
        # the old system ended ETL-S6's enrolments with the leave from 12 November, as its export says
        "enrollments": "sourcedId,classSourcedId,userSourcedId,role,endDate\n"
                       + "".join(f"E{k}-S{i},ETL-K{k},ETL-S{i},student,{'2026-11-12' if i == 6 else ''}\n" for k in (1, 2) for i in range(1, 7)),
    }
    for kind, text in registry.items():
        r = load(0, kind, f"{kind}.csv", text, folder)
        assert r["written"] and not r["error_count"], (kind, r["errors"])
    # the dean's office entered this order in Zəka before the old system's orders were loaded
    r = registrar.post(f"/api/directory/students/{uid('ETL-S5')}/status", {"kind": "admission", "order_no": "ETL-25/Q",
                                                                           "order_date": "2025-08-25", "effective_date": "2025-09-01"})
    assert r.status == 200, r.text
    rules = admin.get("/api/admin/settings").json["journal"]
    assert admin.put("/api/admin/settings/journal", {"value": {**rules, "cutover_date": AS_OF}}).status == 200
    yield {"folder": folder}
    admin.put("/api/admin/settings/journal", {"value": rules})


def admin_id():
    return q("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1")[0]["id"]


def wave0(folder, dry_run=False):
    return etl.run(MAPPING, FIX, 0, AS_OF, EXPORTED, folder, dry_run, False, admin_id())


# ---------------------------------------------------------------- the rules of a mapping (no I/O)
def test_names_group_codes_dates_values_and_scales_are_transformed():
    assert domain.az_name("MƏMMƏDOVA  aysel") == "Məmmədova Aysel" and domain.az_name("ilkin İSMAYILOV") == "İlkin İsmayılov"
    assert domain.group_code("651 a") == "651A" and domain.group_code("İT–25 1") == "İT-251"
    assert domain.transform("date", "02.11.2026", None) == "2026-11-02"
    assert domain.transform("scale:100:10", "74", None) == "7.4"
    assert domain.transform("values", "Q", {"q": "absent"}) == "absent"
    for name, value in (("date", "2026/11/02"), ("values", "x"), ("scale:100:10", "yox")):
        with pytest.raises(ValueError):
            domain.transform(name, value, {"q": "absent"})


def test_lesson_records_without_their_class_or_start_are_summed_into_opening_balances():
    spec = {"file": "x.csv", "kind": "attendance", "columns": {"Fənn": "courseSourcedId", "Tələbə": "userSourcedId", "Qeyd": "status",
                                                               "Saat": "hours"}, "constants": {"termSourcedId": "T-2026"}}
    rows = [(2, ["ETL-C2", "S1", "absent", "2"]), (3, ["ETL-C2", "S1", "excused", "3"]), (4, ["ETL-C2", "S1", "present", ""]),
            (5, ["ETL-C2", "S2", "absent", "2"]), (6, ["ETL-C2", "S2", "nə?", "2"])]
    kind, _, out, rep = domain.apply(spec, ["Fənn", "Tələbə", "Qeyd", "Saat"], rows)
    assert kind == "attendance-opening" and rep["aggregated"] and [r["row"] for r in rep["refused"]] == [6]
    got = {x["userSourcedId"]: (x["heldHours"], x["unexcusedHours"], x["excusedHours"]) for x in out}
    assert got == {"S1": ("7", "2", "3"), "S2": ("2", "2", "0")}, "a lesson without its hours is one pair (2)"


def test_a_column_neither_mapped_nor_left_out_is_unexplained():
    spec = {"file": "x.csv", "kind": "grades", "columns": {"Fənn": "courseSourcedId", "Tələbə": "userSourcedId", "Komponent": "component",
                                                           "Bal": "score", "Yox": "max"}, "ignore": {"Qeyd": "free text"}}
    _, _, _, rep = domain.apply(spec, ["Fənn", "Tələbə", "Komponent", "Bal", "Qeyd", "Müəllim"], [])
    assert rep["unexplained"] == ["Müəllim"] and rep["missing"] == ["Yox"] and not domain.explained(rep)
    assert domain.check_spec({"kind": "grades", "columns": {"A": "nope"}}) == ["unknown column 'nope'"]
    assert domain.chunks(list(range(7)), 3) == [[0, 1, 2], [3, 4, 5], [6]]


# ---------------------------------------------------------------- a wave
def test_a_dry_run_maps_every_column_and_accounts_for_every_row(world, capsys, tmp_path):
    assert wave0(tmp_path / "dry", dry_run=True) == 0
    out = capsys.readouterr().out
    assert "left out Müəllim (the lesson's teacher comes with the classes import)" in out and "NOT EXPLAINED" not in out
    assert out.count("· dry run") == 4 and not q("SELECT 1 FROM migration_files WHERE kind='attendance'"), "nothing written"
    m = json.loads(MAPPING.read_text(encoding="utf-8"))
    del m["files"][0]["ignore"]
    loose = tmp_path / "loose.json"
    loose.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    assert etl.run(loose, FIX, 0, AS_OF, EXPORTED, tmp_path / "loose", True, False) == 1
    assert "NOT EXPLAINED: columns not in the mapping ['Müəllim']" in capsys.readouterr().out


def test_the_wave_loads_and_every_entity_reconciles(world, capsys):
    assert wave0(world["folder"]) == 0, capsys.readouterr()
    r = reconcile(0, world["folder"])
    assert r["ok"], (r["differences"], r["hours"], r["entities"])
    assert {k: (v["source"], v["linked"]) for k, v in r["entities"].items()} == {
        "users": (6, 6), "courses": (2, 2), "classes": (2, 2), "enrollments": (12, 12), "attendance": (30, 30),
        "attendance-opening": (6, 6), "grades": (6, 6), "status-events": (2, 2)}
    assert r["exported_at"] == [EXPORTED] and all(f["sha256"] == f["sha256_now"] for f in r["files"])
    lessons = next(f for f in r["files"] if f["kind"] == "attendance")
    assert lessons["source_file"] == "attendance_lessons.csv"
    assert lessons["source_sha256"] == hashlib.sha256((FIX / "attendance_lessons.csv").read_bytes()).hexdigest()
    assert all(f["checksums"]["source"] == f["checksums"]["zeka"] for f in r["files"])
    assert r["hour_pairs"] == 12 and r["hours"] == [] and len(r["sample"]) == 50


def test_the_absence_hours_and_scores_per_student_and_course_are_the_source_s(world):
    c1, c2 = course("ETL-101"), course("ETL-102")
    c = store.connect()
    try:
        lessons, opening = journal.imported_hours(c, c1), journal.imported_hours(c, c2)
    finally:
        c.close()
    assert lessons[uid("ETL-S3")] == (4, 2), "qqüii: two absences and one excuse of 2 hours"
    assert lessons[uid("ETL-S2")] == (0, 0) and lessons[uid("ETL-S4")] == (2, 0), "late is not missed"
    rows = list(csv.DictReader(io.StringIO((FIX / "attendance_opening.csv").read_text(encoding="utf-8"))))
    assert {uid(x["Tələbə"]): (int(x["Üzrsüz"]), int(x["Üzrlü"])) for x in rows} == opening
    scores = {r["user_id"]: r["score"] for r in q("SELECT user_id, score FROM grades WHERE course_id=? AND component='Kollokvium 1'", (c1,))}
    assert scores[uid("ETL-S1")] == 5.0 and scores[uid("ETL-S6")] == 9.0, "the 100-point scale on a component of 10"
    assert q("SELECT DISTINCT a.source, a.as_of FROM attendance a JOIN lessons l ON l.id=a.lesson_id WHERE l.course_id=?", (c1,)) == \
        [{"source": "legacy", "as_of": AS_OF}]


def test_a_row_created_in_zeka_is_not_a_difference_and_a_changed_one_is(world):
    c1 = course("ETL-101")
    unit = q("SELECT id FROM teaching_units WHERE course_id=?", (c1,))[0]["id"]
    later = sql("INSERT INTO lessons(course_id,day,start,end,kind,unit_id,academic_hours,slot_day,slot_start) "
                "VALUES(?,'2026-11-16','09:00','10:30','Mühazirə',?,2,'2026-11-16','09:00')", (c1, unit))
    sql("INSERT INTO attendance(lesson_id,user_id,status,source) VALUES(?,?,'absent','zeka')", (later, uid("ETL-S1")))
    lesson = q("SELECT a.rowid k FROM attendance a JOIN lessons l ON l.id=a.lesson_id WHERE l.course_id=? AND l.day='2026-11-03' "
               "AND a.user_id=?", (c1, uid("ETL-S2")))[0]["k"]
    try:
        assert reconcile(0, world["folder"])["ok"], "Zəka's own records are not compared"
        sql("UPDATE attendance SET status='absent' WHERE rowid=?", (lesson,))
        r = reconcile(0, world["folder"])
        assert not r["ok"]
        assert [(d["source_id"], d["action"], d["fields"]) for d in r["differences"]] == [
            ("ETL-K1|ETL-S2|2026-11-03|09:00", "conflict", ["status"])], "changed in Zəka since the import"
        assert r["hours"] == [{"student_id": uid("ETL-S2"), "course_id": c1, "source": [0, 0], "zeka": [2, 0]}]
    finally:
        sql("UPDATE attendance SET status='present' WHERE rowid=?", (lesson,))
        sql("DELETE FROM attendance WHERE lesson_id=?", (later,))
        sql("DELETE FROM lessons WHERE id=?", (later,))


def test_one_form_per_student_and_course(world):
    """An opening balance for a pair with lesson records, or a lesson record up to the opening's date: refused."""
    c = store.connect()
    try:
        opening = importer.run(c, "attendance-opening", SOURCE, "o.csv", b"termSourcedId,courseSourcedId,userSourcedId,heldHours,"
                               b"unexcusedHours,excusedHours\nT-2026,ETL-C1,ETL-S1,10,2,0\n", as_of=AS_OF)
        lesson = importer.run(c, "attendance", SOURCE, "l.csv", b"classSourcedId,userSourcedId,date,start,status\n"
                              b"ETL-K2,ETL-S1,2026-11-03,09:00,absent\n", as_of=AS_OF)
    finally:
        c.close()
    assert "dərs səviyyəli qeydlər idxal olunub" in opening["errors"][0]["reason"]["az"]
    assert "açılış qalığı var" in lesson["errors"][0]["reason"]["az"]


def test_a_status_order_is_written_once_and_ends_the_lesson_lists(world, app_db):
    s5, s6 = uid("ETL-S5"), uid("ETL-S6")
    leave = q("SELECT kind, order_no, effective_date, entered_by FROM student_status_events WHERE student_id=?", (s6,))
    assert [(x["kind"], x["order_no"], x["effective_date"], x["entered_by"]) for x in leave] == [
        ("academic_leave", "ETL-77/AM", "2026-11-12", admin_id())], "entered by the importing account"
    assert len(q("SELECT 1 FROM student_status_events WHERE student_id=? AND order_no='ETL-25/Q'", (s5,))) == 1, "linked, not doubled"
    assert q("SELECT 1 FROM import_links WHERE kind='status_events' AND source_system=? AND source_id LIKE 'ETL-S5|%'", (SOURCE,))
    c1 = course("ETL-101")
    unit = q("SELECT id FROM teaching_units WHERE course_id=?", (c1,))[0]["id"]
    after = sql("INSERT INTO lessons(course_id,day,start,end,kind,unit_id,academic_hours,slot_day,slot_start) "
                "VALUES(?,'2026-11-17','09:00','10:30','Mühazirə',?,2,'2026-11-17','09:00')", (c1, unit))
    try:
        listed = {s["id"] for s in app_db.client("admin").get(f"/api/journal/lessons/{after}").json["students"]}
        assert s6 not in listed and s5 in listed, "on leave from 12 November: off the later lesson's list"
    finally:
        sql("DELETE FROM lessons WHERE id=?", (after,))


def test_running_the_wave_again_changes_nothing(world, capsys):
    def counts():
        return tuple(q(x)[0]["n"] for x in ("SELECT COUNT(*) n FROM attendance WHERE source='legacy'", "SELECT COUNT(*) n FROM lessons",
                                            "SELECT COUNT(*) n FROM student_status_events", "SELECT COUNT(*) n FROM grades",
                                            "SELECT COUNT(*) n FROM attendance_opening"))
    before = counts()
    assert wave0(world["folder"]) == 0
    out = capsys.readouterr().out
    assert counts() == before and out.count("new 0 · changed 0") == 4
    assert reconcile(0, world["folder"])["ok"]


def test_no_writing_import_while_an_exam_is_going_on(world, monkeypatch):
    monkeypatch.setattr(exam_service, "open_count", lambda c: 1)
    data = b"courseSourcedId,userSourcedId,component,score\nETL-C1,ETL-S1,Kollokvium 2,6\n"
    c = store.connect()
    try:
        with pytest.raises(tables.TableError, match="İmtahan gedir"):
            importer.run(c, "grades", SOURCE, "g.csv", data, as_of=AS_OF)
        assert importer.run(c, "grades", SOURCE, "g.csv", data, as_of=AS_OF, dry_run=True)["inserted"] == 1, "a dry run may"
        assert importer.run(c, "grades", SOURCE, "g.csv", data, as_of=AS_OF, force=True)["written"]
    finally:
        c.close()
    assert q("SELECT detail FROM audit WHERE action='import_forced' ORDER BY id DESC LIMIT 1")[0]["detail"] == f"{SOURCE} · g.csv · exams open: 1"


def test_a_load_over_the_file_limit_goes_in_files_each_one_atomic(world, monkeypatch, tmp_path):
    monkeypatch.setattr(importer, "MAX_FILE_ROWS", 7)
    m = json.loads(MAPPING.read_text(encoding="utf-8"))
    m["files"] = [f for f in m["files"] if f["kind"] == "attendance"]
    one = tmp_path / "lessons.json"
    one.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    assert etl.run(one, FIX, 9, AS_OF, EXPORTED, tmp_path / "w9", False, False) == 0
    names = [f["filename"] for f in q("SELECT filename FROM migration_files WHERE wave=9 ORDER BY id")]
    assert names == [f"attendance_lessons.attendance.{i:03d}.csv" for i in range(1, 6)], "30 rows in files of 7"
    assert reconcile(9, tmp_path / "w9")["ok"]
    c = store.connect()
    try:
        with pytest.raises(tables.TableError, match="200 000"):
            importer.run(c, "attendance", SOURCE, "big.csv", (tmp_path / "w9" / names[0]).read_bytes()
                         + b"ETL-K1,ETL-S1,2026-11-02,09:00,present\n", as_of=AS_OF)
    finally:
        c.close()


def test_a_history_that_reconciles_makes_the_transcript_issuable(world, tmp_path):
    s1 = uid("ETL-S1")
    text = ("userSourcedId,courseCode,courseTitle,termTitle,termStart,credits,score\n"
            "ETL-S1,OLD-1,Ali riyaziyyat,2024/2025 payız,2024-09-15,5,84\nETL-S1,OLD-2,Fizika,2024/2025 payız,2024-09-15,4,49\n")
    assert load(1, "results", "results.csv", text, tmp_path)["written"]
    c = store.connect()
    try:
        assert not journal.transcript_ready(c, s1)
    finally:
        c.close()
    r = reconcile(1, tmp_path)
    assert r["ok"] and r["history_reconciled"] == 1
    finals = q("SELECT course_code, score, letter, passed, source FROM final_grades WHERE user_id=? ORDER BY course_code", (s1,))
    assert finals == [{"course_code": "OLD-1", "score": 84.0, "letter": "B", "passed": 1, "source": "legacy"},
                      {"course_code": "OLD-2", "score": 49.0, "letter": "F", "passed": 0, "source": "legacy"}]
    c = store.connect()
    try:
        assert journal.transcript_ready(c, s1)
    finally:
        c.close()


def test_the_command_line(world, tmp_path):
    env = {**os.environ, "ZEKA_DATA": str(store.DATA)}
    manage = [sys.executable, str(ROOT / "backend" / "manage.py")]
    f = tmp_path / "g.csv"
    f.write_text("courseSourcedId,userSourcedId,component,score\nETL-C1,ETL-S2,Kollokvium 2,7\n", encoding="utf-8")
    no_date = subprocess.run([*manage, "import", "--kind", "grades", "--source", SOURCE, "--file", str(f), "--dry-run"],
                             capture_output=True, text=True, env=env, timeout=120)
    assert no_date.returncode == 2 and "--as-of is required" in no_date.stderr
    ok = subprocess.run([*manage, "reconcile", "--wave", "0", "--source", SOURCE, "--dir", str(world["folder"])],
                        capture_output=True, text=True, env=env, timeout=300)
    assert ok.returncode == 0 and "RECONCILED" in ok.stdout and "attendance: source 30 · linked 30" in ok.stdout, ok.stdout + ok.stderr


def test_a_source_row_whose_link_is_gone_is_counted_as_not_linked(world):
    """The entity count compares the file's rows with the rows linked to them, not with the file again."""
    link = q("SELECT * FROM import_links WHERE kind='users' AND source_system=? AND source_id='ETL-S2'", (SOURCE,))[0]
    sql("DELETE FROM import_links WHERE id=?", (link["id"],))
    try:
        r = reconcile(0, world["folder"])
        assert r["entities"]["users"] == {"source": 6, "linked": 5} and not r["ok"]
    finally:
        sql("INSERT INTO import_links(id,kind,source_system,source_id,row_id,source_hash,imported_at) VALUES(?,?,?,?,?,?,?)",
            tuple(link[k] for k in ("id", "kind", "source_system", "source_id", "row_id", "source_hash", "imported_at")))


def test_status_orders_are_not_imported_without_the_account_that_enters_them(world):
    spec = json.loads(MAPPING.read_text(encoding="utf-8"))["files"][3]
    header, rows = etl.adapters.read(FIX / "status_events.csv")
    kind, head, canon, _ = domain.apply(spec, header, rows)
    c = store.connect()
    try:
        with pytest.raises(tables.TableError, match="--by"):
            importer.run(c, kind, SOURCE, "orders.csv", etl.adapters.to_csv(head, canon))
    finally:
        c.close()
