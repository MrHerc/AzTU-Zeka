"""Bulk import (tasks/todo.md, Task 16): Forma №3 in both layouts, OneRoster CSV kinds, all or nothing, conflicts with
rows changed in Zəka, the write lock, the screen's row limit, and one-time activation codes.

Fixtures are synthetic (tests/fixtures/make_fixtures.py); the owner's real files never enter the repository.
"""
import base64
import csv
import io
import time
import urllib.parse
from pathlib import Path

import pytest

from zeka.core import security
from zeka.legacy import store
from zeka.modules.identity import domain as identity
from zeka.modules.integration import importer

FIX = Path(__file__).resolve().parents[1] / "fixtures"
GOOD = "dəniz kənarında gəzinti 2026"


def db():
    return store.connect()


def q(sql, args=()):
    c = db()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def imp(admin, kind, filename, data, dry_run=False, prefer=False, source="sis"):
    return admin.post("/api/admin/import", {"kind": kind, "source": source, "filename": filename, "content_b64": b64(data),
                                            "dry_run": dry_run, "prefer_source": prefer})


def csv_bytes(header, rows) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    w.writerows(rows)
    return out.getvalue().encode()


@pytest.fixture(autouse=True)
def fast_hash(monkeypatch):
    monkeypatch.setattr(identity, "N", 2 ** 4)


# ---------------------------------------------------------------- Forma №3
@pytest.fixture(scope="module")
def load_world(app_db):
    """The teachers, courses and groups the synthetic Forma №3 names."""
    admin = app_db.client("admin")
    fid = admin.get("/api/directory/faculties").json["items"][0]["id"]
    groups = {g: admin.post("/api/directory/groups", {"name": g, "year": 2025, "faculty_id": fid}).json["id"]
              for g in ("651a", "652a", "653a")}
    c = db()
    try:
        teachers = {}
        for name, patronymic, username in (("Elçin Quliyev", "Rauf oğlu", "e.quliyev"), ("Leyla Həsənova", "Akif qızı", "l.hesenova")):
            teachers[username] = c.execute("INSERT INTO users(username,full_name,patronymic,role,synthetic) VALUES(?,?,?,'teacher',1)",
                                           (username, name, patronymic)).lastrowid
        c.commit()
    finally:
        c.close()
    courses = {n: admin.post("/api/directory/courses", {"code": code, "name": n, "credits": 5}).json["id"]
               for code, n in (("ALQ-F3", "Alqoritmlər"), ("VB-F3", "Verilənlər bazaları"), ("FIZ-F3", "Fizika"))}
    return {"groups": groups, "teachers": teachers, "courses": courses}


def units(course_id):
    out = []
    for u in q("SELECT * FROM teaching_units WHERE course_id=? ORDER BY id", (course_id,)):
        u["groups"] = sorted(r["group_id"] for r in q("SELECT group_id FROM teaching_unit_groups WHERE unit_id=?", (u["id"],)))
        out.append(u)
    return out


@pytest.mark.parametrize("fixture, source", [("forma3_blocks.xlsx", "f3-a"), ("forma3_sheets.xlsx", "f3-b")])
def test_forma3_gives_the_expected_teaching_units(app_db, load_world, fixture, source):
    admin = app_db.client("admin")
    users_before = q("SELECT COUNT(*) n FROM users")[0]["n"]
    r = imp(admin, "teaching-load", fixture, (FIX / fixture).read_bytes(), source=source)
    assert r.status == 200, r.text
    rep = r.json
    g, t, co = load_world["groups"], load_world["teachers"], load_world["courses"]
    alq = [u for u in units(co["Alqoritmlər"]) if u["id"] in {lk["row_id"] for lk in q(
        "SELECT row_id FROM import_links WHERE source_system=?", (source,))}]
    lecture = [u for u in alq if u["kind"] == "lecture"]
    assert len(lecture) == 1 and lecture[0]["groups"] == sorted(g.values()), "one lecture stream for every group"
    assert lecture[0]["hours"] == 30 and lecture[0]["teacher_id"] == t["e.quliyev"]
    seminars = {u["groups"][0]: u["teacher_id"] for u in alq if u["kind"] == "seminar"}
    assert set(seminars) == {g["651a"], g["652a"]}
    second = t["l.hesenova"] if source == "f3-b" else t["e.quliyev"]      # layout B names another teacher for 652a
    assert seminars[g["652a"]] == second
    labs = sorted(u["subgroup"] for u in alq if u["kind"] == "lab")
    assert labs == [1, 2] and all(u["groups"] == [g["653a"]] for u in alq if u["kind"] == "lab")
    assert {(u["kind"]) for u in units(co["Verilənlər bazaları"])} >= {"lecture", "seminar"}
    assert any(u["kind"] == "lab" and u["teacher_id"] == t["l.hesenova"] for u in units(co["Fizika"]))
    assert all(u["hours"] != 99 for u in alq), "the SAAT HESABI / saat hesabı rows are not units"
    assert rep["inserted"] == 8 and rep["error_count"] == 0
    if source == "f3-b":
        assert [x["row"] for x in rep["conflicts"]] == ["Naməlum N.N.!9"], "an unknown teacher is reported, not created"
    assert q("SELECT COUNT(*) n FROM users")[0]["n"] == users_before
    again = imp(admin, "teaching-load", fixture, (FIX / fixture).read_bytes(), source=source).json
    assert again["inserted"] == again["updated"] == 0 and again["unchanged"] == 8


# ---------------------------------------------------------------- users, all or nothing, conflicts
def test_ten_thousand_users_import_fast_and_a_second_run_changes_nothing(app_db):
    data = (FIX / "users_10k.csv").read_bytes()
    c = db()
    try:
        started = time.monotonic()
        rep = importer.run(c, "users", "test", "users_10k.csv", data)
        took = time.monotonic() - started
        assert rep["error_count"] == 0 and rep["inserted"] == 10_000, rep["errors"][:3]
        assert took < 60 and rep["lock_ms"] <= 1000, (took, rep["lock_ms"])
        again = importer.run(c, "users", "test", "users_10k.csv", data)
        assert (again["inserted"], again["updated"], again["unchanged"]) == (0, 0, 10_000)
    finally:
        c.close()
    assert q("SELECT COUNT(*) n FROM import_links WHERE kind='users' AND source_system='test'")[0]["n"] == 10_000


HEADER = ["sourcedId", "username", "givenName", "familyName", "role", "identifier", "group", "email"]


def test_a_file_with_three_bad_rows_writes_nothing_and_names_them(app_db):
    admin = app_db.client("admin")
    rows = [["b1", "bad.one", "Ad", "Soyad", "student", "B-1", "İT-25-1", ""],
            ["b2", "x", "Ad", "Soyad", "student", "B-2", "İT-25-1", ""],             # user name too short
            ["b3", "bad.three", "Ad", "Soyad", "rector", "B-3", "", ""],             # unknown role
            ["b4", "bad.four", "Ad", "Soyad", "student", "B-4", "Yoxdur-1", ""],     # unknown group
            ["b5", "bad.five", "Ad", "Soyad", "student", "B-5", "İT-25-1", ""]]
    before = q("SELECT COUNT(*) n FROM users")[0]["n"]
    rep = imp(admin, "users", "bad.csv", csv_bytes(HEADER, rows)).json
    assert [e["row"] for e in rep["errors"]] == [3, 4, 5] and all(e["reason"] for e in rep["errors"])
    assert rep["written"] is False and q("SELECT COUNT(*) n FROM users")[0]["n"] == before
    missing = imp(admin, "users", "x.csv", csv_bytes(["sourcedId", "username"], [["a", "b"]])).json
    assert missing["errors"][0]["row"] == 1 and "givenName" in missing["errors"][0]["reason"]


def test_a_row_changed_in_zeka_is_not_overwritten_until_prefer_source(app_db):
    admin = app_db.client("admin")
    rows = [["c1", "conf.one", "Nərmin", "Qasımova", "student", "C-1", "İT-25-1", ""],
            ["c2", "conf.two", "Rauf", "Səfərli", "student", "C-2", "İT-25-1", ""]]
    assert imp(admin, "users", "c.csv", csv_bytes(HEADER, rows)).json["inserted"] == 2
    uid = q("SELECT id FROM users WHERE username='conf.one'")[0]["id"]
    assert admin.put(f"/api/directory/users/{uid}", {"full_name": "Nərmin Qasımova-Əliyeva"}).status == 200
    rows[0][3], rows[1][3] = "Qasımlı", "Səfərov"          # the source changes both rows
    rep = imp(admin, "users", "c.csv", csv_bytes(HEADER, rows)).json
    assert rep["updated"] == 1 and [x["row"] for x in rep["conflicts"]] == [2] and rep["conflicts"][0]["fields"] == ["full_name"]
    assert q("SELECT full_name FROM users WHERE id=?", (uid,))[0]["full_name"] == "Nərmin Qasımova-Əliyeva"
    assert q("SELECT full_name FROM users WHERE username='conf.two'")[0]["full_name"] == "Rauf Səfərov", "the other row is written"
    rep = imp(admin, "users", "c.csv", csv_bytes(HEADER, rows), prefer=True).json
    assert rep["updated"] == 1 and rep["overwritten"] == 1 and not rep["conflicts"]
    assert q("SELECT full_name FROM users WHERE id=?", (uid,))[0]["full_name"] == "Nərmin Qasımlı"
    assert any(f"#{uid}" in r["detail"] for r in q("SELECT detail FROM audit WHERE action='import_overwrite'"))


def test_staff_accounts_are_never_changed_by_an_import(app_db):
    admin = app_db.client("admin")
    rows = [["s1", admin.user["username"], "Ad", "Soyad", "teacher", "", "", ""]]
    rep = imp(admin, "users", "s.csv", csv_bytes(HEADER, rows)).json
    assert rep["error_count"] == 1 and q("SELECT role FROM users WHERE id=?", (admin.user["id"],))[0]["role"] == "admin"


def test_the_screen_takes_at_most_20000_rows_and_only_the_administrator(app_db):
    admin = app_db.client("admin")
    big = csv_bytes(HEADER, [[f"z{i}", f"zz{i:05d}", "A", "B", "student", f"Z-{i}", "", ""] for i in range(20_001)])
    assert imp(admin, "users", "big.csv", big).status == 400
    assert imp(app_db.client("office"), "users", "a.csv", csv_bytes(HEADER, [])).status == 403
    assert imp(admin, "users", "a.pdf", b"%PDF").status == 400
    assert imp(admin, "users", "a.csv", csv_bytes(HEADER, []), source="").status == 400
    dry = imp(admin, "users", "d.csv", csv_bytes(HEADER, [["d1", "dry.one", "A", "B", "student", "D-1", "", ""]]), dry_run=True).json
    assert dry["inserted"] == 1 and dry["written"] is False and not q("SELECT 1 FROM users WHERE username='dry.one'")


# ---------------------------------------------------------------- OneRoster kinds end to end
def test_oneroster_files_build_the_structure_units_and_enrolments(app_db):
    admin = app_db.client("admin")
    ok = lambda r: (r.status == 200 and r.json["error_count"] == 0, r.text)   # noqa: E731
    r = imp(admin, "orgs", "orgs.csv", csv_bytes(["sourcedId", "name", "type", "identifier", "parentSourcedId"],
                                                 [["o-d", "Kompüter mühəndisliyi kafedrası", "department", "KM-K", "o-f"],
                                                  ["o-f", "İnformasiya texnologiyaları fakültəsi", "faculty", "ITF", ""]]))
    assert ok(r)[0], ok(r)[1]
    dep = q("SELECT * FROM departments WHERE code='KM-K'")[0]
    assert dep["faculty_id"] == q("SELECT id FROM faculties WHERE code='ITF'")[0]["id"], "the parent of the same file"
    r = imp(admin, "terms", "terms.csv", csv_bytes(["sourcedId", "title", "identifier", "startDate", "endDate", "examStartDate", "examEndDate"],
                                                   [["t1", "2027 payız", "2027P", "15.09.2027", "2027-12-28", "2028-01-05", "2028-01-30"]]))
    assert ok(r)[0], ok(r)[1]
    users = csv_bytes(HEADER, [["r-t", "or.teacher", "Ülvi", "Məmmədli", "teacher", "", "", ""],
                               ["r-s", "or.student", "Səbinə", "Rzayeva", "student", "R-1", "İT-25-1", ""]])
    assert ok(imp(admin, "users", "u.csv", users))[0]
    r = imp(admin, "courses", "c.csv", csv_bytes(["sourcedId", "title", "courseCode", "orgSourcedId", "termSourcedId", "credits"],
                                                 [["k1", "Şəbəkələr", "ŞB-1", "o-d", "t1", "5"]]))
    assert ok(r)[0], ok(r)[1]
    r = imp(admin, "classes", "cl.csv", csv_bytes(["sourcedId", "courseSourcedId", "kind", "subgroup", "groups"],
                                                  [["cl1", "k1", "laboratoriya", "2", "İT-25-1"]]))
    assert ok(r)[0], ok(r)[1]
    r = imp(admin, "enrollments", "e.csv", csv_bytes(["sourcedId", "classSourcedId", "userSourcedId", "role", "beginDate", "endDate"],
                                                     [["e1", "cl1", "r-t", "teacher", "", ""],
                                                      ["e2", "cl1", "r-s", "student", "2027-09-15", "2027-12-28"]]))
    assert ok(r)[0], ok(r)[1]
    course = q("SELECT * FROM courses WHERE code='ŞB-1'")[0]
    assert course["term_id"] and course["department_id"] == dep["id"] and course["credits"] == 5
    unit = q("SELECT * FROM teaching_units WHERE course_id=?", (course["id"],))[0]
    teacher = q("SELECT id FROM users WHERE username='or.teacher'")[0]["id"]
    student = q("SELECT id, group_id FROM users WHERE username='or.student'")[0]
    assert unit["kind"] == "lab" and unit["subgroup"] == 2 and unit["teacher_id"] == teacher
    e = q("SELECT * FROM enrollments WHERE user_id=? AND course_id=?", (student["id"], course["id"]))[0]
    assert (e["group_id"], e["subgroup"], e["begin_date"], e["end_date"]) == (student["group_id"], 2, "2027-09-15", "2027-12-28")
    r = imp(admin, "timetable", "tt.csv", csv_bytes(["sourcedId", "courseSourcedId", "weekday", "start", "end", "kind", "room"],
                                                    [["tt1", "k1", "2", "09:00", "10:20", "lab", "316"]]))
    assert ok(r)[0], ok(r)[1]
    assert q("SELECT kind, room FROM timetable WHERE course_id=?", (course["id"],)) == [{"kind": "Laboratoriya", "room": "316"}]
    bad = imp(admin, "enrollments", "e2.csv", csv_bytes(["sourcedId", "classSourcedId", "userSourcedId", "role"],
                                                        [["e3", "cl1", "r-s", "teacher"], ["e4", "nope", "r-s", "student"]])).json
    assert [e["row"] for e in bad["errors"]] == [2, 3]


# ---------------------------------------------------------------- activation codes
@pytest.fixture(scope="module")
def codes(app_db):
    admin = app_db.client("admin")
    rows = [[f"a{i}", f"akt.{i}", "Fidan", "Nəsibova", "student", f"A-{i}", "İT-25-1", ""] for i in range(3)]
    assert imp(admin, "users", "a.csv", csv_bytes(HEADER, rows)).json["inserted"] == 3
    fid = admin.get("/api/directory/faculties?q=" + urllib.parse.quote("İTT")).json["items"][0]["id"]
    out = admin.post("/api/admin/activation-codes", {"faculty_id": fid}).json
    mine = {r["student_no"]: r["code"] for r in csv.DictReader(io.StringIO(out["csv"])) if r["student_no"].startswith("A-")}
    assert len(mine) == 3
    return mine


def activate(client, no, code, ip="10.9.0.1", password=GOOD):
    return client.post("/api/auth/activate", {"student_no": no, "code": code, "password": password}, headers={"X-Forwarded-For": ip})


@pytest.fixture
def proxy(monkeypatch):
    monkeypatch.setattr(security.CFG, "proxy_hops", 1)
    c = db()
    c.execute("DELETE FROM login_blocks")
    c.commit()
    c.close()


def test_only_the_hash_of_a_code_is_stored(codes):
    raw = [x for row in q("SELECT * FROM activation_codes") for x in row.values()]
    assert not any(isinstance(v, str) and (code in v or code.replace("-", "") in v) for code in codes.values() for v in raw)


def test_a_code_works_once_for_its_own_student_number(app_db, codes, proxy):
    a0, a1 = codes["A-0"], codes["A-1"]
    assert activate(app_db.client(), "A-1", a0).status == 401, "another student's number"
    assert activate(app_db.client(), "A-0", a0, password="qısa").status == 400, "a weak password spends nothing"
    me = app_db.client()
    r = activate(me, "A-0", a0)
    assert r.status == 200 and r.json["user"]["role"] == "student" and me.get("/api/bootstrap").json["user"]["username"] == "akt.0"
    assert activate(app_db.client(), "A-0", a0).status == 401, "spent"
    assert app_db.client().post("/api/auth/login", {"login": "akt.0", "password": GOOD}).status == 200
    assert a1


def test_an_expired_code_is_refused(app_db, codes, proxy):
    c = db()
    c.execute("UPDATE activation_codes SET expires_at='2000-01-01T00:00:00' WHERE user_id=(SELECT id FROM users WHERE username='akt.2') "
              "AND used_at IS NULL AND revoked_at IS NULL")
    c.commit()
    c.close()
    assert activate(app_db.client(), "A-2", codes["A-2"]).status == 401


def test_ten_wrong_codes_from_one_address_block_it_and_another_address_still_works(app_db, codes, proxy):
    for i in range(10):
        assert activate(app_db.client(), "A-1", f"ZZZZ-ZZZZ-ZZ{i % 10}{i % 7}"[:14], ip="10.9.9.9").status == 401
    assert activate(app_db.client(), "A-1", codes["A-1"], ip="10.9.9.9").status == 429
    assert activate(app_db.client(), "A-1", codes["A-1"], ip="10.8.8.8").status == 200, "a wrong attempt does not spend the code"


def test_a_new_batch_revokes_the_old_codes(app_db, codes, proxy):
    admin = app_db.client("admin")
    assert imp(admin, "users", "n.csv", csv_bytes(HEADER, [["an", "akt.yeni", "Nərmin", "Əliyeva", "student", "A-N", "İT-25-1", ""]])).status == 200
    fid = admin.get("/api/directory/faculties?q=" + urllib.parse.quote("İTT")).json["items"][0]["id"]

    def batch():
        return {r["student_no"]: r["code"] for r in csv.DictReader(io.StringIO(admin.post("/api/admin/activation-codes", {"faculty_id": fid}).json["csv"]))}

    old, new = batch()["A-N"], batch()
    assert "A-0" not in new, "an activated account gets no new code"
    rows = q("SELECT revoked_at FROM activation_codes WHERE user_id=(SELECT id FROM users WHERE username='akt.yeni') ORDER BY id")
    assert len(rows) == 2 and rows[0]["revoked_at"] and rows[1]["revoked_at"] is None
    assert activate(app_db.client(), "A-N", old, ip="10.7.7.7").status == 401
    assert activate(app_db.client(), "A-N", new["A-N"], ip="10.7.7.7").status == 200


def test_the_screen_import_refuses_the_migration_history_kinds(admin):
    """Checkpoint F (SEC-F1): status orders, legacy marks and final grades come in through manage.py import with --by;
    the administrator's screen would bypass the registry office's permission (students.status)."""
    before = q("SELECT COUNT(*) n FROM student_status_events")[0]["n"]
    for kind in ("status-events", "results", "attendance"):
        r = imp(admin, kind, "x.csv", b"userSourcedId,kind,orderNo,orderDate,effectiveDate\nOLD-1,expulsion,X-1,2026-11-18,2026-11-19\n")
        assert r.status == 400 and "manage.py" in r.json["error"], (kind, r.status, r.json)
    assert q("SELECT COUNT(*) n FROM student_status_events")[0]["n"] == before
