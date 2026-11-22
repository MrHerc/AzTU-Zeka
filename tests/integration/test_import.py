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

from tests.fixtures.make_fixtures import xlsx
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


# ---------------------------------------------------------------- Forma №3 (Task 47, docs/forms/forma-3.md)
@pytest.fixture(scope="module")
def load_world(app_db):
    """The registry the synthetic forms meet: most of their teachers, courses and groups, and on purpose not all of them."""
    admin = app_db.client("admin")
    fid = admin.get("/api/directory/faculties").json["items"][0]["id"]
    groups = {}
    for g in ("6524a1", "6524a2", "6524a3", "6523a1", "6523a2", "6525e", "6525r", "6524r", "6526e1", "6526e2", "6526e3", "6525a", "M656a",
              "6325r"):
        r = admin.post("/api/directory/groups", {"name": g, "year": 2025, "faculty_id": fid})
        assert r.status == 200, r.text
        groups[g] = r.json["id"]
    c = db()
    try:
        teachers = {}
        for name, patronymic, username in (("Elçin Quliyev", "Rauf oğlu", "e.quliyev"), ("Leyla Həsənova", "Akif qızı", "l.hesenova"),
                                           ("Nigar Əliyeva", "Samir qızı", "n.eliyeva")):
            teachers[username] = c.execute("INSERT INTO users(username,full_name,patronymic,role,synthetic) VALUES(?,?,?,'teacher',1)",
                                           (username, name, patronymic)).lastrowid
        c.commit()
    finally:
        c.close()
    courses = {}
    for i, n in enumerate(("Alqoritmlər", "Verilənlər bazaları", "Fizika", "Texniki xarici dil (rus dili)", "İFS: Siqnalların emalı",
                           "Elektronika", "Riyazi analiz-1", "Riyazi analiz-2", "Xətti cəbr", "Fizika-1", "Diskret riyaziyyat",
                           "Ədədi üsullar", "Ehtimal nəzəriyyəsi")):
        r = admin.post("/api/directory/courses", {"code": f"F3-{i}", "name": n, "credits": 5})
        assert r.status == 200, r.text
        courses[n] = r.json["id"]
    return {"groups": groups, "teachers": teachers, "courses": courses}


def units(source):
    out = {}
    for u in q("SELECT u.* FROM teaching_units u JOIN import_links l ON l.row_id=u.id AND l.kind='teaching_load' "
               "WHERE l.source_system=? ORDER BY u.id", (source,)):
        u["groups"] = sorted(r["group_id"] for r in q("SELECT group_id FROM teaching_unit_groups WHERE unit_id=?", (u["id"],)))
        out[u["anchor"]] = u
    return out


def load(admin, fixture, source, dry_run=False):
    r = imp(admin, "teaching-load", fixture, (FIX / fixture).read_bytes(), source=source, dry_run=dry_run)
    assert r.status == 200, r.text
    return r.json


def test_forma3_preview_shows_the_readers_report_and_writes_nothing(app_db, load_world):
    """The preview: per post ok / blocked / hidden with its controls, the conflicts by cell, the notes and load totals."""
    rep = load(app_db.client("admin"), "forma3_blocks.xlsx", "f3-a", dry_run=True)
    f = rep["forma3"]
    assert rep["written"] is False and not units("f3-a")
    assert (f["layout"], f["year"], f["unclassified"]) == ("A", "2026/2027", 0)
    assert {p["ref"]: p["status"] for p in f["posts"]} == {"#0!A7": "ok", "#0!A22": "ok", "#0!A48": "ok", "#0!A61": "blocked",
                                                           "#0!A72": "ok", "#1!A4": "blocked"}
    assert all(p["controls"] == {"T1": True, "T2": True, "T3": True} for p in f["posts"])
    assert (f["units"]["count"], f["units"]["ready"], f["units"]["hourly"], f["units"]["vacancy"]) == (19, 17, 4, 3)
    assert f["excluded"] == {"posts": ["#1!A4"], "units": 2, "hours": 45, "load_lines": 3, "load_hours": 9.3}, "A11: outside the totals"
    blocking = {(c["cell"], c["code"]) for c in f["conflicts"] if c["blocking"]}
    assert blocking == {("#0!C66", "subject_missing"), ("#1!A4", "year_conflict"), ("#1!A4", "not_in_summary")}
    assert all(isinstance(c["message"], str) and c["message"] for c in f["conflicts"]), "messages arrive in the reader's language"
    assert f["note_count"] and f["load"]["exam"]["lines"] and f["load_hours"] > 0
    assert [s["class"] for s in f["sheets"] if not s["imported"]] == ["empty", "summary", "list"]
    listed = {x["row"]: x["reason"] for x in rep["conflicts"]}
    assert rep["inserted"] == 9 and listed["#0!U54"].startswith("Fənn tapılmadı"), "a subject the registry lacks is listed"
    assert len(listed) == 8 and listed["#0!F26"].startswith("Müəllim tapılmadı"), \
        "two people of the registry share this name and «Akifovna» cannot tell them apart: listed, never guessed"
    there = imp(app_db.client("admin", lang="en"), "teaching-load", "a.xlsx", (FIX / "forma3_blocks.xlsx").read_bytes(), source="f3-a", dry_run=True).json["forma3"]
    assert next(c["message"] for c in there["conflicts"] if c["code"] == "year_conflict").startswith("The academic year")


def test_forma3_layout_a_applies_only_the_posts_that_passed(app_db, load_world):
    admin = app_db.client("admin")
    users_before = q("SELECT COUNT(*) n FROM users")[0]["n"]
    rep = load(admin, "forma3_blocks.xlsx", "f3-a")
    g, t, co = load_world["groups"], load_world["teachers"], load_world["courses"]
    got = units("f3-a")
    assert rep["written"] and rep["inserted"] == len(got) == 9
    assert not [a for a in got if a.startswith("#1!") or a in ("#0!F65", "#0!G65")], "X21: a blocked post applies nothing"
    lecture = got["#0!E11"]                                         # J1: one lecture for the three groups its merge covers
    assert (lecture["kind"], lecture["hours"], lecture["teacher_id"], lecture["students"]) == ("lecture", 30, t["e.quliyev"], 75)
    assert lecture["groups"] == sorted(g[x] for x in ("6524a1", "6524a2", "6524a3"))
    assert got["#0!F11"]["groups"] == sorted((g["6524a1"], g["6524a2"])) and got["#0!F13"]["groups"] == [g["6524a3"]], "J2"
    assert got["#0!S14"]["course_id"] == co["Verilənlər bazaları"]
    assert all(u["subgroup"] is None for u in got.values()), "G7: a group's suffix is never a subgroup"
    vacant = got["#0!S53"]                                          # P3: unassigned load, not a missing teacher
    assert (vacant["teacher_id"], vacant["vacancy"], vacant["pay"], vacant["post_ref"]) == (None, 1, "staff", "#0!A48")
    assert (got["#0!F76"]["pay"], got["#0!F76"]["teacher_id"], got["#0!F76"]["vacancy"]) == ("hourly", t["n.eliyeva"], 0), "P2"
    assert q("SELECT COUNT(*) n FROM users")[0]["n"] == users_before, "the form never creates a person"
    again = load(admin, "forma3_blocks.xlsx", "f3-a")
    assert (again["inserted"], again["updated"], again["unchanged"]) == (0, 0, 9)


def test_forma3_layout_b_hidden_hourly_vacancy_and_repeated_classes(app_db, load_world):
    admin = app_db.client("admin")
    rep = load(admin, "forma3_sheets.xlsx", "f3-b")
    g, t = load_world["groups"], load_world["teachers"]
    got = units("f3-b")
    assert rep["inserted"] == len(got) == 19
    assert sorted(x["row"] for x in rep["conflicts"]) == ["#2!AA11", "#2!AA12", "#7!H11"], "unknown teachers are listed, never created"
    assert not [a for a in got if a.startswith(("#6!", "#5!Z", "#5!AA"))], "G4: the hidden sheet; R5/R2: the blocked section"
    assert {p["ref"]: p["status"] for p in rep["forma3"]["posts"]}["#6!B10"] == "hidden"
    assert got["#0!F11"]["groups"] == sorted(g[x] for x in ("6526e1", "6526e2", "6526e3")), "J1"
    assert [got[a]["groups"] for a in ("#1!H11", "#1!H12", "#1!H13")] == [[g["6526e1"]], [g["6526e2"]], [g["6526e3"]]], \
        "G7: «6526e 1» is the group 6526e1, and its lab is its own class"
    assert all(u["subgroup"] is None for u in got.values())
    assert got["#0!F11"]["teacher_id"] == t["e.quliyev"] and got["#1!H12"]["teacher_id"] == t["l.hesenova"], "X9: the owner teaches"
    assert got["#0!Z14"]["course_id"] == load_world["courses"]["Riyazi analiz-2"], "G6: «- 2» and «-2» are one subject"
    assert (got["#1!F15"]["hours"], got["#1!F16"]["hours"]) == (30, 15) and got["#1!F15"]["id"] != got["#1!F16"]["id"], \
        "R4: the same class written twice is two classes, never one with the hours added"
    assert (got["#0!G24"]["pay"], got["#0!G24"]["post_ref"], got["#0!F20"]["pay"]) == ("hourly", "#0!B23", "staff")
    assert [(got[a]["teacher_id"], got[a]["vacancy"], got[a]["pay"]) for a in ("#3!Z11", "#4!F11")] == [(None, 1, "staff"), (None, 1, "hourly")]
    assert got["#5!G15"]["teacher_id"] == t["n.eliyeva"], "the hourly section of a sheet whose first section is blocked still applies"
    again = load(admin, "forma3_sheets.xlsx", "f3-b")
    assert (again["inserted"], again["updated"], again["unchanged"]) == (0, 0, 19)


def test_forma3_refuses_a_file_that_is_no_form_with_a_translated_400(app_db):
    admin = app_db.client("admin")
    for name, data in (("x.xlsx", b"PK\x03\x04 not a workbook"), ("x.xlsx", (FIX / "users_10k.csv").read_bytes()[:4000]),
                       ("x.csv", b"a,b\n1,2\n")):
        r = imp(admin, "teaching-load", name, data, source="f3-x", dry_run=True)
        assert r.status == 400 and r.json["error"], (name, r.status, r.text)
    c = db()
    try:
        with pytest.raises(importer.tables.TableError, match="tapılmadı"):
            importer.run(c, "teaching-load", "f3-x", "list.xlsx", xlsx([("Siyahı", [["Ad", "Saat"], ["Nümunə", "30"]], [])]))
    finally:
        c.close()


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
