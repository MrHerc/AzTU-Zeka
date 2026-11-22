"""Checkpoint B (review of Tasks 10-17): one regression test per confirmed finding, each failing on the code before
its fix. The ids (A1 ... E7, T*) are those of docs/review/checkpoint-b-2026-11-18.md."""
import base64
import csv
import io
import json
import time
import urllib.parse
import zipfile

import pytest

from tests.fixtures.make_fixtures import xlsx
from zeka.core import security, tenant
from zeka.legacy import common, store
from zeka.modules.directory import domain as directory_rules
from zeka.modules.identity import domain as identity
from zeka.modules.identity import sso
from zeka.modules.integration import domain as integration
from zeka.modules.integration import forma3, importer, tables

GOOD = "dəniz kənarında gəzinti 2026"
WRONG = "yanlış parol budur!"
HEADER = ["sourcedId", "username", "givenName", "familyName", "role", "identifier", "group", "email"]


def db():
    return store.connect()


def q(sql, args=()):
    c = db()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def run(sql, args=()):
    c = db()
    try:
        c.execute(sql, args)
        c.commit()
    finally:
        c.close()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def csv_bytes(header, rows) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    w.writerows(rows)
    return out.getvalue().encode()


def imp(admin, kind, filename, data, source="sis"):
    return admin.post("/api/admin/import", {"kind": kind, "source": source, "filename": filename, "content_b64": b64(data),
                                            "dry_run": False, "prefer_source": False})


def uid(username):
    return q("SELECT id FROM users WHERE username=?", (username,))[0]["id"]


def demo_login(role):
    c = db()
    try:
        return store.setting(c, "demo_logins")[role]
    finally:
        c.close()


def faculty_id(admin):
    return admin.get("/api/directory/faculties?q=" + urllib.parse.quote("İTT")).json["items"][0]["id"]


def codes_for(admin) -> dict:
    out = admin.post("/api/admin/activation-codes", {"faculty_id": faculty_id(admin)}).json["csv"]
    return {r["student_no"]: r["code"] for r in csv.DictReader(io.StringIO(out))}


def activate(client, no, code, ip="10.9.0.1"):
    return client.post("/api/auth/activate", {"student_no": no, "code": code, "password": GOOD}, headers={"X-Forwarded-For": ip})


def login(client, name, password=GOOD, ip="10.3.0.1"):
    return client.post("/api/auth/login", {"login": name, "password": password}, headers={"X-Forwarded-For": ip})


def set_password(username):
    run("UPDATE users SET password_hash=? WHERE username=?", (identity.hash_password(GOOD), username))


def with_totp(username):
    run("UPDATE users SET totp_secret=?, totp_enabled_at=? WHERE username=?", (identity.new_totp_secret(), store.iso(store.now()), username))


def without_password(username):
    run("UPDATE users SET totp_secret=NULL, totp_enabled_at=NULL, password_hash=NULL, must_change=0, failed_count=0, "
        "locked_until=NULL WHERE username=?", (username,))


@pytest.fixture(autouse=True)
def setup(app_db, monkeypatch):
    monkeypatch.setattr(identity, "N", 2 ** 4)
    monkeypatch.setattr(security.CFG, "proxy_hops", 1)
    run("DELETE FROM login_blocks")


@pytest.fixture(scope="module")
def faculty_b(app_db):
    """A second faculty with one student moved into it: the demo dean's office (faculty İTT) must not reach her."""
    admin = app_db.client("admin")
    fb = admin.post("/api/directory/faculties", {"code": "FBX", "name": "B fakültəsi"}).json["id"]
    gb = admin.post("/api/directory/groups", {"name": "FBX-1", "year": 2025, "faculty_id": fb}).json["id"]
    sid = q("SELECT id FROM users WHERE role='student' AND username<>? ORDER BY id DESC LIMIT 1", (demo_login("student"),))[0]["id"]
    run("UPDATE users SET group_id=? WHERE id=?", (gb, sid))
    return {"faculty": fb, "group": gb, "student": sid}


# ---------------------------------------------------------------- activation codes and imports (A)
def test_a1_a_code_opens_only_an_account_that_has_no_way_in_yet(app_db):
    admin = app_db.client("admin")
    rows = [[f"x{i}", f"kod.{i}", "Ad", "Soyad", "student", f"K-{i}", "İT-25-1", ""] for i in range(3)]
    assert imp(admin, "users", "k.csv", csv_bytes(HEADER, rows)).json["inserted"] == 3
    with_totp("kod.1")
    run("INSERT INTO sso_identities(user_id,iss,sub,linked_by,linked_at) VALUES(?,?,?,?,?)",
        (uid("kod.2"), "https://idp.example", "s-2", "admin", store.iso(store.now())))
    got = codes_for(admin)
    assert "K-0" in got and "K-1" not in got and "K-2" not in got, "a second factor or a provider link: no code"
    assert admin.post(f"/api/admin/users/{uid('kod.0')}/temp-password").status == 200       # another way in, later
    assert activate(app_db.client(), "K-0", got["K-0"]).status == 401, "the printed code no longer opens the account"


def test_a2_an_import_that_changes_a_role_ends_the_sessions(app_db):
    admin = app_db.client("admin")
    assert imp(admin, "users", "r.csv", csv_bytes(HEADER, [["r1", "rol.one", "Ad", "Soyad", "student", "R-1", "İT-25-1", ""]])).status == 200
    set_password("rol.one")
    student = app_db.client()
    assert login(student, "rol.one").status == 200
    rep = imp(admin, "users", "r.csv", csv_bytes(HEADER, [["r1", "rol.one", "Ad", "Soyad", "teacher", "", "", ""]])).json
    assert rep["updated"] == 1, rep
    assert student.get("/api/bootstrap").json["user"] is None, "a teacher starts from a new sign-in (and its second factor)"


def test_a3_exported_csv_cells_cannot_run_as_formulas(app_db):
    assert integration.csv_cell("=HYPERLINK(1)") == "'=HYPERLINK(1)" and integration.csv_cell("+1") == "'+1"
    assert integration.csv_cell("Aysel") == "Aysel" and integration.csv_cell(None) == ""
    admin = app_db.client("admin")
    assert imp(admin, "users", "f.csv", csv_bytes(HEADER, [["f1", "form.ul", "=HYPERLINK(1)", "Ad", "student", "F-1", "İT-25-1", ""]])).status == 200
    out = admin.post("/api/admin/activation-codes", {"faculty_id": faculty_id(admin)}).json["csv"]
    assert "'=HYPERLINK(1) Ad" in out


def test_a4_a_code_of_an_account_disabled_since_does_not_work(app_db):
    admin = app_db.client("admin")
    assert imp(admin, "users", "d.csv", csv_bytes(HEADER, [["d1", "dis.one", "Ad", "Soyad", "student", "D-1", "İT-25-1", ""]])).status == 200
    code = codes_for(admin)["D-1"]
    assert admin.post(f"/api/directory/users/{uid('dis.one')}/deactivate").status == 200
    assert activate(app_db.client(), "D-1", code).status == 401


def test_a6_a_first_import_does_not_overwrite_a_value_zeka_already_holds(app_db):
    admin = app_db.client("admin")
    assert admin.post("/api/directory/users", {"username": "yerli.ad", "full_name": "Yerli Ad", "role": "student",
                                               "student_no": "Y-1"}).status == 200
    rep = imp(admin, "users", "y.csv", csv_bytes(HEADER, [["y1", "yerli.ad", "Başqa", "Ad", "student", "Y-1", "", "y@aztu.edu.az"]])).json
    assert len(rep["conflicts"]) == 1, rep
    assert q("SELECT full_name FROM users WHERE username='yerli.ad'")[0]["full_name"] == "Yerli Ad"


# ---------------------------------------------------------------- import robustness (B)
def test_b1_a_lecture_and_a_lab_of_one_course_are_one_enrolment(app_db):
    admin = app_db.client("admin")

    def ok(r):
        return r.status == 200 and not r.json["errors"]

    assert ok(imp(admin, "courses", "c.csv", csv_bytes(["sourcedId", "title", "courseCode"], [["kb1", "Elektronika", "EL-B1"]]), "b1"))
    assert ok(imp(admin, "classes", "cl.csv", csv_bytes(["sourcedId", "courseSourcedId", "kind", "subgroup", "groups"],
                                                        [["L1", "kb1", "lecture", "", "İT-25-1"], ["P1", "kb1", "lab", "2", "İT-25-1"]]), "b1"))
    assert ok(imp(admin, "users", "u.csv", csv_bytes(HEADER, [["s1", "enr.one", "Ad", "Soyad", "student", "E-1", "İT-25-1", ""]]), "b1"))
    both = csv_bytes(["sourcedId", "classSourcedId", "userSourcedId", "role"], [["e1", "L1", "s1", "student"], ["e2", "P1", "s1", "student"]])
    r = imp(admin, "enrollments", "e.csv", both, "b1")
    assert ok(r) and not r.json["conflicts"], r.text
    course = q("SELECT id FROM courses WHERE code='EL-B1'")[0]["id"]
    assert len(q("SELECT 1 FROM enrollments WHERE user_id=? AND course_id=?", (uid("enr.one"), course))) == 1
    assert q("SELECT COUNT(*) n FROM import_links WHERE kind='enrollments' AND source_system='b1'")[0]["n"] == 2
    again = imp(admin, "enrollments", "e.csv", both, "b1").json
    assert again["inserted"] == again["updated"] == 0 and not again["conflicts"], again


def _xlsx(sheet_xml: str) -> bytes:
    good = zipfile.ZipFile(io.BytesIO(xlsx([("S", [["a"]], [])])))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name in good.namelist():
            z.writestr(name, sheet_xml if name == "xl/worksheets/sheet1.xml" else good.read(name))
    return out.getvalue()


def test_b2_a_tiny_xlsx_cannot_expand_into_millions_of_cells():
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    bomb = _xlsx(f'<worksheet xmlns="{main}"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>a</t></is></c></row>'
                 '<row r="199999"><c r="GR199999" t="inlineStr"><is><t>b</t></is></c></row></sheetData></worksheet>')
    started = time.monotonic()
    with pytest.raises(tables.TableError):
        tables.xlsx_sheets(bomb)
    assert time.monotonic() - started < 2 and len(bomb) < 4000


def test_b3_a_damaged_xlsx_is_refused_not_a_500(app_db):
    with pytest.raises(tables.TableError):
        tables.xlsx_sheets(_xlsx("<a>"))
    assert imp(app_db.client("admin"), "users", "x.xlsx", _xlsx("<a>")).status == 400


def _form(rows, merges):
    return [tables.Sheet("S", rows, merges)]


FORM = [["1,0 ştat - dosent, Quliyev Elçin Rauf oğlu"], ["", "", "", "", "payız semestri", ""],
        ["Sıra sayı", "Qruplar", "Fənlər", "Tələbələrin sayı", "Mühazirə", "Məşğələ"], ["1", "2", "3", "4", "5", "6"],
        ["1", "651a", "Alqoritmlər", "inf", "1e30", "nan"], ["2", "", "Fizika", "20", "30", ""]]


def test_b4_b5_forma3_reports_every_cell_and_row_it_cannot_use():
    form = forma3.read(_form(FORM, [(1, 4, 1, 5)]))
    found = {(c.cell, c.code) for c in form.conflicts if c.blocking}
    assert {("#0!D5", "students_text"), ("#0!E5", "hours_text"), ("#0!F5", "hours_text"), ("#0!B6", "group_missing")} <= found, found
    assert not form.unclassified and all(p.blocked for p in form.posts), "inf, 1e30 and nan are never hours; nothing is applied"


def test_b5_a_header_that_does_not_close_its_semesters_refuses_the_post():
    """Task 47 (H3): a semester is the columns up to a «Cəmi» column, so a header without one is refused, not guessed."""
    form = forma3.read(_form(FORM, [(1, 4, 1, 5)]))
    assert ("#0!C3", "header_incomplete", True) in {(c.cell, c.code, c.blocking) for c in form.conflicts}


def test_b6_reported_rows_are_the_rows_of_the_file(app_db):
    data = csv_bytes(HEADER, []) + b"\n\nz1,X Y,Ad,Soyad,student,Z-1,,\n"
    rep = imp(app_db.client("admin"), "users", "b.csv", data).json
    assert [e["row"] for e in rep["errors"]] == [4], rep


def test_b8_a_change_made_while_the_file_is_checked_is_not_overwritten(app_db, monkeypatch):
    admin = app_db.client("admin")
    rows = [["w1", "race.one", "Ad", "Soyad", "student", "W-1", "İT-25-1", ""]]
    assert imp(admin, "users", "w.csv", csv_bytes(HEADER, rows)).json["inserted"] == 1
    plain = importer._classify

    def classify_then_edit(*a, **k):
        out = plain(*a, **k)
        run("UPDATE users SET full_name='Dəyişdirilib Burada' WHERE username='race.one'")   # another admin, meanwhile
        return out

    monkeypatch.setattr(importer, "_classify", classify_then_edit)
    rows[0][3] = "Yeni"
    rep = imp(admin, "users", "w.csv", csv_bytes(HEADER, rows)).json
    assert rep["updated"] == 0 and len(rep["conflicts"]) == 1, rep
    assert q("SELECT full_name FROM users WHERE username='race.one'")[0]["full_name"] == "Dəyişdirilib Burada"


def test_b10_latin_capitals_match_their_azerbaijani_spelling():
    v, problem = integration.draft("classes", {"sourcedId": "c1", "courseSourcedId": "k", "kind": "SEMINAR"})
    assert problem is None and v["kind"] == "seminar", (v, problem)
    assert forma3.norm("FƏNNIN ADI") == forma3.norm("FƏNNİN ADI") == forma3.norm("fənnin adı")


# ---------------------------------------------------------------- the dean's-office scope (C)
def _docs_of(sid, n=1):
    c = db()
    try:
        ids = [store.issue_document(c, "request", sid, "Arayış", {"type": "enrollment_certificate"}, None, "TA")["id"] for _ in range(n)]
        c.commit()
        return ids
    finally:
        c.close()


def test_c1_another_faculty_s_document_cannot_be_revoked(app_db, faculty_b):
    doc = _docs_of(faculty_b["student"])[0]
    assert app_db.client("office").post(f"/api/documents/{doc}/revoke", {"reason": "sınaq"}).status == 404
    assert q("SELECT revoked_at FROM documents WHERE id=?", (doc,))[0]["revoked_at"] is None


def test_c2_only_the_student_and_the_registry_offices_read_a_request(app_db):
    # a type whose steps are all the dean's office's: since Task 46 a role a step is assigned to reads that type's requests
    rid = q("SELECT id FROM requests WHERE type_code='dormitory' ORDER BY id LIMIT 1")[0]["id"]
    admin, teacher = app_db.client("admin"), app_db.client("teacher")
    assert teacher.get(f"/api/requests/{rid}").status == 404
    for role in ("academic_office", "dept_head", "proctor"):
        gid = admin.post(f"/api/admin/users/{teacher.user['id']}/roles", {"role": role}).json["id"]
        try:
            acting = app_db.client("teacher")
            assert acting.post("/api/me/role", {"role": role}).status == 200, role
            assert acting.get(f"/api/requests/{rid}").status == 404, role
            assert acting.post(f"/api/requests/{rid}/messages", {"text": "salam"}).status == 404, role
        finally:
            admin.delete(f"/api/admin/users/{teacher.user['id']}/roles/{gid}")


def test_c3_c4_lists_and_counts_are_scoped_before_their_limit(app_db, faculty_b):
    office = app_db.client("office")
    own_before = len(office.get("/api/documents").json)
    _docs_of(faculty_b["student"], 205)
    assert len(office.get("/api/documents").json) == own_before > 0, "the other faculty's newer documents push nothing out"
    t = store.iso(store.now())
    run("INSERT INTO requests(type_code,student_id,data,status,step,created_at,updated_at,due_at) VALUES(?,?,?,?,?,?,?,?)",
        ("free_application", faculty_b["student"], "{}", "submitted", 0, t, t, t))
    listed = [r for r in office.get("/api/requests?status=all").json if r["status"] == "submitted"]
    assert office.get("/api/badges").json["office"] == len(listed)


def test_c6_only_the_student_s_own_dean_s_office_is_told_and_counted(app_db, faculty_b):
    office = app_db.client("office")
    c = db()
    try:
        assert office.user["id"] not in common.office_for(c, faculty_b["student"])
        assert office.user["id"] in common.office_for(c, uid(demo_login("student")))
    finally:
        c.close()
    t = store.iso(store.now())
    run("INSERT INTO requests(type_code,student_id,data,status,step,created_at,updated_at,due_at) VALUES(?,?,?,?,?,?,?,?)",
        ("free_application", faculty_b["student"], "{}", "submitted", 0, t, t, t))
    listed = [r for r in office.get("/api/requests?status=all").json if r["status"] == "submitted"]
    assert office.get("/api/office/summary").json["new"] == len(listed)


def test_c5_the_scope_check_reads_one_row_not_the_users_table(app_db):
    office = app_db.client("office").user
    c = db()
    try:
        u = store.row(c, "SELECT * FROM users WHERE id=?", (office["id"],))
        u["role"] = "office"
        sqls: list = []
        c.set_trace_callback(sqls.append)
        common.serves(c, u, 1)
        c.set_trace_callback(None)
        plans = []
        for s in sqls:
            plans += [r[3] for r in c.execute("EXPLAIN QUERY PLAN " + s, (1,) * s.count("?"))]
        assert sqls and not [p for p in plans if p.startswith("SCAN")], plans
    finally:
        c.close()


def test_c7_a_message_on_another_person_s_request_is_an_audited_read(app_db):
    r = q("SELECT id, student_id FROM requests WHERE student_id=? ORDER BY id LIMIT 1", (uid(demo_login("student")),))[0]
    before = len(q("SELECT 1 FROM audit WHERE action='read_request'"))
    assert app_db.client("office").post(f"/api/requests/{r['id']}/messages", {"text": "Sənədi gətirin"}).status == 200
    assert len(q("SELECT 1 FROM audit WHERE action='read_request'")) == before + 1


def test_c8_a_one_time_key_of_an_account_disabled_since_opens_nothing(app_db):
    student = app_db.client("student")
    doc = q("SELECT id FROM documents WHERE holder_id=? ORDER BY id LIMIT 1", (student.user["id"],))[0]["id"]
    url = student.post(f"/api/documents/{doc}/link").json["url"]
    run("UPDATE users SET status='disabled' WHERE id=?", (student.user["id"],))
    try:
        assert app_db.client().get(urllib.parse.urlsplit(url).path + "?" + urllib.parse.urlsplit(url).query).status != 200
    finally:
        run("UPDATE users SET status='active' WHERE id=?", (student.user["id"],))


def test_c9_a_half_finished_sign_in_does_not_lock_the_public_pages(app_db):
    name = demo_login("teacher")
    set_password(name)
    with_totp(name)
    try:
        pending = app_db.client()
        assert login(pending, name).json["user"]["scope"] == "mfa"
        code = q("SELECT verify_code FROM documents ORDER BY id LIMIT 1")[0]["verify_code"]
        assert pending.get(f"/verify/{code}").status == 200
        assert pending.get("/api/courses").status == 403, "the protected routes still wait for the second factor"
    finally:
        without_password(name)


# ---------------------------------------------------------------- sign-in, sessions, SSO (D)
def test_d1_one_address_cannot_spray_passwords_over_many_accounts(app_db, rate_limits):
    for i in range(100):
        assert login(app_db.client(), f"yox.{i}", WRONG, ip="10.44.0.1").status == 401
    assert login(app_db.client(), "yox.yeni", WRONG, ip="10.44.0.1").status == 429
    assert login(app_db.client(), "yox.yeni", WRONG, ip="10.45.0.1").status == 401


def test_d2_sso_starts_are_rate_limited_per_address(app_db, rate_limits):
    for _ in range(30):
        app_db.client().get("/api/auth/sso/start", headers={"X-Forwarded-For": "10.46.0.1"})
    assert rate_limits["sso"].blocked(identity.client_key("10.46.0.1"))
    assert not rate_limits["sso"].blocked(identity.client_key("10.46.0.2"))


def test_d4_a_name_that_does_not_exist_locks_like_one_that_does(app_db):
    for i in range(100):
        assert login(app_db.client(), "hec.kim.yox", WRONG, ip=f"10.47.{i // 10}.{i % 10 + 1}").status == 401
    assert login(app_db.client(), "hec.kim.yox", WRONG, ip="10.48.0.1").status == 429


def test_d5_d9_claims_that_are_not_numbers_or_not_the_token_s_own_are_refused(monkeypatch):
    good = {"iss": "https://i", "aud": "z", "exp": 2000, "iat": 1000, "nonce": "n", "sub": "s"}
    assert identity.claims_problem({**good, "exp": float("nan")}, issuer="https://i", client_id="z", nonce="n", now=1500) == "exp"
    token = ".".join(base64.urlsafe_b64encode(json.dumps(x).encode()).decode().rstrip("=") for x in
                     ({"alg": "RS256"}, {**good, "email": "victim@aztu.edu.az", "email_verified": False})) + ".sig"
    answers = {"https://i/token": {"id_token": token, "access_token": "a"}, "https://i/userinfo": {"sub": "s", "email_verified": True}}
    monkeypatch.setattr(sso, "_call", lambda url, *a, **k: answers[url])
    monkeypatch.setattr(sso.time, "time", lambda: 1500)
    claims = sso.exchange({"issuer": "https://i", "client_id": "z"}, {"token_endpoint": "https://i/token",
                          "userinfo_endpoint": "https://i/userinfo"}, "c", "v", "n", "https://zeka/cb")
    assert identity.verified_email(claims) is None, "a verification without its address does not verify the token's address"


@pytest.mark.parametrize("userinfo, check", [
    ({"sub": "s", "amr": ["mfa"], "acr": "gold"}, lambda c: not identity.idp_mfa(c, ["mfa"], ["gold"])),   # only the token's own
    ({"sub": "s", "email": "other@aztu.edu.az"}, lambda c: identity.verified_email(c) is None),          # an address, no proof
])
def test_d9_userinfo_cannot_add_a_second_factor_or_an_unverified_address(monkeypatch, userinfo, check):
    good = {"iss": "https://i", "aud": "z", "exp": 2000, "iat": 1000, "nonce": "n", "sub": "s"}
    token = ".".join(base64.urlsafe_b64encode(json.dumps(x).encode()).decode().rstrip("=") for x in ({"alg": "RS256"}, good)) + ".sig"
    answers = {"https://i/token": {"id_token": token, "access_token": "a"}, "https://i/userinfo": userinfo}
    monkeypatch.setattr(sso, "_call", lambda url, *a, **k: answers[url])
    monkeypatch.setattr(sso.time, "time", lambda: 1500)
    claims = sso.exchange({"issuer": "https://i", "client_id": "z"}, {"token_endpoint": "https://i/token",
                          "userinfo_endpoint": "https://i/userinfo"}, "c", "v", "n", "https://zeka/cb")
    assert check(claims), claims


def test_d7_an_id_beyond_sqlite_integers_is_not_found(app_db):
    student = app_db.client("student")
    assert student.get("/api/courses/" + "9" * 25).status == 404
    assert student.get("/api/courses/" + "9" * 5000).status == 404, "int() itself refuses 4300+ digits"


def test_d8_only_calendar_dates_are_dates():
    assert directory_rules.date_problem("d", "2026-W01-1") is not None
    assert directory_rules.date_problem("d", "2026-11-18") is None
    assert tenant.problem("calendar", {**tenant.DEFAULTS["calendar"], "holidays": ["2026-W01-1"]}) is not None


# ---------------------------------------------------------------- tenant settings (E) and test gaps (T5)
def test_e1_without_a_term_the_limit_is_unknown_not_zero(app_db):
    saved = q("SELECT id, teaching_start, teaching_end FROM academic_terms")
    run("UPDATE academic_terms SET teaching_start='2999-01-01', teaching_end='2999-02-01'")   # none has begun
    try:
        rows = app_db.client("student").get("/api/attendance").json["courses"]
        assert rows and all(x["limit"] is None for x in rows), rows
    finally:
        for t in saved:
            run("UPDATE academic_terms SET teaching_start=?, teaching_end=? WHERE id=?", (t["teaching_start"], t["teaching_end"], t["id"]))


def test_e2_an_older_database_gets_the_university_s_own_rules(app_db):
    run("DELETE FROM settings WHERE key='tenant'")
    store.init()
    c = db()
    try:
        assert tenant.load(c)["registry"]["prefix"] == "AzTU"
    finally:
        c.close()


def put(admin, section, value):
    return admin.put(f"/api/admin/settings/{section}", {"value": value})


def test_e3_e7_t5_every_settings_check_refuses_and_never_crashes(app_db):
    admin = app_db.client("admin")
    cur = admin.get("/api/admin/settings").json
    att, grading = cur["attendance"], cur["grading"]
    sessions = {"staff": {"idle_minutes": 60, "absolute_hours": 24}, "student": {"idle_minutes": 480, "absolute_hours": 720}}
    bad = [("sessions", {**sessions, "staff": {"idle_minutes": 60, "absolute_hours": True}}),
           ("sessions", {**sessions, "staff": {"idle_minutes": 1440, "absolute_hours": 1}}),
           ("activation", {"days": 0}), ("activation", {"days": 91}), ("activation", {"days": True}),
           ("calendar", {**cur["calendar"], "lesson_times": [["09:00", "10:30"], ["10:00", "11:20"]]}),
           ("attendance", {**att, "points_rule": [[10, 8], [0, 10]]}),
           ("attendance", {**att, "x": 1}), ("attendance", {**att, "limit_percent": 10 ** 400}),
           ("grading", {**grading, "pass_mark": 0}),
           ("grading", {**grading, "scale": [["A", 150], ["B", 81], ["C", 71], ["D", 61], ["E", 51]]}),
           ("grading", {**grading, "components": [{**grading["components"][0], "extra": 1}, *grading["components"][1:]]})]
    for section, value in bad:
        r = put(admin, section, value)
        assert r.status == 400, (section, value, r.status, r.text[:200])
    assert put(admin, "sessions", {**sessions, "extra": {"idle_minutes": 1, "absolute_hours": 1}}).status == 200
    c = db()
    try:
        assert set(store.setting(c, "session_limits")) <= {"staff", "student"}
    finally:
        c.close()


def test_t5_the_points_rule_is_capped_and_exact():
    rule = [[0, 10], [10, 8], [25, 5]]
    assert tenant.attendance_points(30, 30, 10, rule) == 10
    assert tenant.attendance_points(27, 30, 10, rule) == 8
    assert tenant.attendance_points(30, 30, 10, [[0, 50]]) == 10, "never more than the component's maximum"


def test_t5_the_excused_flag_changes_the_counted_absences(app_db):
    sid = uid(demo_login("student"))
    lesson = q("SELECT lesson_id FROM attendance WHERE user_id=? AND status='present' LIMIT 1", (sid,))[0]["lesson_id"]
    run("UPDATE attendance SET status='excused' WHERE lesson_id=? AND user_id=?", (lesson, sid))
    admin, student = app_db.client("admin"), app_db.client("student")
    att = admin.get("/api/admin/settings").json["attendance"]
    try:
        for counted in (True, False):
            assert put(admin, "attendance", {**att, "excused_counts_toward_limit": counted}).status == 200
            rows = student.get("/api/attendance").json["courses"]
            assert any(x["excused"] for x in rows)
            assert all(x["counted"] == x["absent"] + (x["excused"] if counted else 0) for x in rows), rows
    finally:
        put(admin, "attendance", att)
        run("UPDATE attendance SET status='present' WHERE lesson_id=? AND user_id=?", (lesson, sid))


# ---------------------------------------------------------------- identity test gaps (T2, T4)
def test_t2_a_pending_second_factor_reaches_nothing_but_its_own_step(app_db):
    name = demo_login("teacher")
    set_password(name)
    with_totp(name)
    try:
        pending = app_db.client()
        assert login(pending, name).json["user"]["scope"] == "mfa"
        for method, path, body in (("POST", "/api/auth/password", {"current": GOOD, "new": GOOD + "x"}),
                                   ("POST", "/api/auth/mfa/disable", {"code": "000000"}), ("POST", "/api/me/role", {"role": "teacher"}),
                                   ("GET", "/api/me/sessions", None)):
            assert pending.request(method, path, body).status == 403, path
    finally:
        without_password(name)


@pytest.mark.parametrize("role", ["teacher", "dept_head", "office", "academic_office", "proctor", "leader", "admin"])
def test_t2_a_student_takes_no_staff_role_without_a_second_factor(app_db, role):
    admin, student = app_db.client("admin"), app_db.client("student")
    gid = admin.post(f"/api/admin/users/{student.user['id']}/roles", {"role": role}).json["id"]
    try:
        assert app_db.client("student").post("/api/me/role", {"role": role}).status == 403
    finally:
        admin.delete(f"/api/admin/users/{student.user['id']}/roles/{gid}")


def test_t4_sign_in_costs_one_hash_and_a_success_clears_the_count(app_db, monkeypatch):
    calls = []
    plain = identity.verify
    monkeypatch.setattr(identity, "verify", lambda *a: calls.append(1) or plain(*a))
    name = demo_login("student")
    set_password(name)
    try:
        for who in ("hec.kim", name):
            calls.clear()
            assert login(app_db.client(), who, WRONG).status == 401
            assert len(calls) == 1, who
        for i in range(5):
            login(app_db.client(), name, WRONG, ip=f"10.50.0.{i + 1}")
        assert q("SELECT failed_count FROM users WHERE username=?", (name,))[0]["failed_count"] >= 5
        signed = app_db.client()
        assert login(signed, name, ip="10.51.0.1").status == 200
        assert q("SELECT failed_count FROM users WHERE username=?", (name,))[0]["failed_count"] == 0
        assert app_db.client("admin").post(f"/api/admin/users/{uid(name)}/temp-password").status == 200
        assert signed.get("/api/bootstrap").json["user"] is None, "a temporary password ends the sessions"
    finally:
        without_password(name)


def test_t6_a_blocked_attempt_costs_no_hash(app_db, monkeypatch):
    name = demo_login("student")
    set_password(name)
    calls = []
    plain = identity.verify
    monkeypatch.setattr(identity, "verify", lambda *a: calls.append(1) or plain(*a))
    try:
        for _ in range(10):
            login(app_db.client(), name, WRONG, ip="10.53.0.1")
        calls.clear()
        assert login(app_db.client(), name, WRONG, ip="10.53.0.1").status == 429
        assert calls == [], "the block is checked before scrypt"
    finally:
        without_password(name)
