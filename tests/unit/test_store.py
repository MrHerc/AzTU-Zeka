"""store.py — time helpers, files, documents, materials, seeding and schema versioning."""
import hashlib
import sqlite3
from datetime import date, datetime

import pytest

from app import engine, pdftext, store

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
DOCX = b"PK\x03\x04" + b"\x00" * 32


# ---------------------------------------------------------------- time helpers
def test_now_and_iso_have_second_precision():
    t = store.now()
    assert t.microsecond == 0
    assert store.iso(datetime(2026, 1, 2, 3, 4, 5, 999)) == "2026-01-02T03:04:05"


@pytest.mark.parametrize("hour, expected_hour", [(1, 10), (8, 17), (9, 9), (17, 17), (18, 9), (23, 14)])
def test_office_hours_folds_the_hour_into_9_to_17(hour, expected_hour):
    out = store.office_hours(datetime(2026, 3, 4, hour, 35))
    assert out.hour == expected_hour and out.minute == 35 and out.date() == date(2026, 3, 4)


def test_office_hours_moves_back_a_day_if_it_would_be_in_the_future():
    out = store.office_hours(datetime(2026, 3, 4, 2, 0), not_after=datetime(2026, 3, 4, 8, 0))
    assert out == datetime(2026, 3, 3, 11, 0)


@pytest.mark.parametrize("dt, expected", [
    (datetime(2026, 3, 4, 7, 15), datetime(2026, 3, 4, 9, 15)),
    (datetime(2026, 3, 4, 12, 0), datetime(2026, 3, 4, 12, 0)),
    (datetime(2026, 3, 4, 19, 30), datetime(2026, 3, 5, 9, 30)),
])
def test_next_office_time(dt, expected):
    assert store.next_office_time(dt) == expected
    assert store.next_office_time(dt) >= dt


@pytest.mark.parametrize("today, expected", [
    (date(2026, 11, 5), date(2026, 9, 15)),
    (date(2026, 9, 20), date(2026, 8, 30)),       # less than two weeks in: pretend three weeks have passed
    (date(2026, 1, 10), date(2025, 9, 15)),
    (date(2026, 4, 1), date(2026, 2, 15)),
])
def test_semester_start(today, expected):
    assert store.semester_start(today) == expected


@pytest.mark.parametrize("score, letter", [(100, "A"), (91, "A"), (90.9, "B"), (81, "B"), (71, "C"), (61, "D"), (51, "E"), (50.9, "F"), (0, "F")])
def test_letter_grades(score, letter):
    assert store.letter(score) == letter


def test_json_helper():
    assert store.J('{"a": 1}') == {"a": 1}
    assert store.J(None, []) == [] and store.J("", {}) == {} and store.J("{bad", "d") == "d"


# ---------------------------------------------------------------- files
@pytest.mark.parametrize("data, kind", [(b"%PDF-1.4", "pdf"), (PNG, "png"), (JPG, "jpg"), (DOCX, "docx"), (b"GIF89a", None), (b"", None)])
def test_sniff(data, kind):
    assert store.sniff(data) == kind


def test_save_file_stores_content_addressed_blob(db):
    pdf = store.demo_pdf(["X"])
    f = store.save_file(db, 1, "həkim arayışı.pdf", pdf)
    assert f["mime"] == "application/pdf" and f["size"] == len(pdf) and f["sha256"] == hashlib.sha256(pdf).hexdigest()
    assert f["filename"] == "həkim arayışı.pdf" and f["request_id"] is None
    assert (store.UPLOADS / f["path"]).read_bytes() == pdf
    g = store.save_file(db, 2, "copy.pdf", pdf)
    assert g["id"] != f["id"] and g["path"] == f["path"]         # same bytes, one blob


@pytest.mark.parametrize("name, data, accept, message", [
    ("x.pdf", b"", "doc", "boşdur"),
    ("x.pdf", b"not a pdf", "doc", "Yalnız PDF"),
    ("x.png", store.demo_pdf(["X"]), "doc", "Yalnız PDF"),        # extension must match the content
    ("x.pdf", store.demo_pdf(["X"]), "image", "yalnız şəkil"),
    ("x.exe", PNG, "doc", "Yalnız PDF"),
])
def test_save_file_rejects(db, name, data, accept, message):
    with pytest.raises(ValueError, match=message):
        store.save_file(db, 1, name, data, accept)


def test_save_file_size_limit(db, monkeypatch):
    monkeypatch.setattr(store, "MAX_FILE", 100)
    with pytest.raises(ValueError, match="10 MB"):
        store.save_file(db, 1, "big.png", PNG + b"\x00" * 200)


def test_save_file_sanitises_the_name(db):
    f = store.save_file(db, 1, "../../etc/pass<wd>?.png", PNG)
    assert f["filename"] == "pass_wd__.png"
    assert store.save_file(db, 1, "noext", PNG)["mime"] == "image/png"     # no extension: content decides
    assert store.save_file(db, 1, "photo.JPEG", JPG)["mime"] == "image/jpeg"


def test_demo_pdf_is_a_readable_pdf():
    pdf = store.demo_pdf(["HEKIM ARAYISI (DEMO)", "a (b) \\ c"])
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    xref = int(pdf.rsplit(b"startxref\n", 1)[1].split(b"\n")[0])
    assert pdf[xref:xref + 4] == b"xref"
    assert pdftext.extract_pages(pdf) == ["HEKIM ARAYISI (DEMO)\na (b) \\ c"]


# ---------------------------------------------------------------- materials & indexes
MD = "# Test\n\n## Əsas anlayışlar\n- **Transformator** — dəyişən cərəyanın gərginliyini çevirən qurğudur.\n\n## Generator işi\nGenerator mexaniki enerjini elektrik enerjisinə çevirir.\n"


def test_add_material_indexes_chunks_and_delete_removes_them(db):
    info = store.add_material(db, 1, "Yeni material", "new.md", MD, 2)
    assert info["chunks"] == 2 and info["terms"] == 1 and info["headings"] == ["Əsas anlayışlar", "Generator işi"]
    hits = engine.INDEX["chunks"].search("generator mexaniki enerji", k=1)
    assert hits and hits[0]["material_id"] == info["id"]
    store.delete_material(db, info["id"])
    assert store.row(db, "SELECT COUNT(*) n FROM chunks WHERE material_id=?", (info["id"],))["n"] == 0
    assert not any(h["material_id"] == info["id"] for h in engine.INDEX["chunks"].search("generator mexaniki enerji", k=20))


def test_add_material_without_text_fails(db):
    with pytest.raises(ValueError):
        store.add_material(db, 1, "Boş", "empty.md", "# Başlıq\n\n   \n", 2)


def test_build_indexes_matches_the_database(db):
    n_chunks = store.row(db, "SELECT COUNT(*) n FROM chunks")["n"]
    store.build_indexes(db)
    assert len(engine.INDEX["chunks"].docs) == n_chunks
    assert len(engine.INDEX["campus"].docs) == store.row(db, "SELECT COUNT(*) n FROM campus_kb")["n"]
    assert len(engine.INDEX["questions"].docs) == store.row(db, "SELECT COUNT(*) n FROM questions")["n"]


# ---------------------------------------------------------------- documents
def test_issue_document_numbers_and_codes(db):
    d1 = store.issue_document(db, "request", 1, "Arayış", {"a": 1}, 8, "TST", issued_at=datetime(2031, 5, 1, 10, 0))
    d2 = store.issue_document(db, "request", 1, "Arayış", {"a": 2}, 8, "TST", issued_at=datetime(2031, 5, 2, 10, 0))
    assert d1["reg_no"] == "AzTU-TST-2031-000001" and d2["reg_no"] == "AzTU-TST-2031-000002"
    for d in (d1, d2):
        assert d["status"] == "valid" and len(d["hash"]) == 64
        code = d["verify_code"]
        assert len(code) == 9 and code[4] == "-" and set(code.replace("-", "")) <= set(store._CODE_ALPHA)
        assert not set(code) & set("01IO")                  # unambiguous alphabet
    assert d1["verify_code"] != d2["verify_code"] and d1["hash"] != d2["hash"]


def test_transcript_rows_are_deterministic(db):
    a, b = store.transcript_rows(db, 5), store.transcript_rows(db, 5)
    assert a == b and len(a) == 2
    for sem in a:
        for r in sem["courses"]:
            assert 64 <= r["score"] <= 98 and r["letter"] == store.letter(r["score"]) and r["credits"] > 0
    assert all(r["score"] >= 78 for s in store.transcript_rows(db, 1) for r in s["courses"])   # the demo student


def test_parse_kb():
    md = "# KB\n\n## Sual bir?\n<!-- request: transcript | label: Sifariş et | source: Bələdçi, 2.2 -->\nCavab mətni.\n\n## Sual iki\nYalnız mətn.\n"
    assert store._parse_kb(md) == [
        ("Sual bir?", "Cavab mətni.", "transcript", "Sifariş et", "Bələdçi, 2.2"),
        ("Sual iki", "Yalnız mətn.", None, None, "Tələbə bələdçisi (demo)"),
    ]


def test_notify_accepts_one_id_or_many_and_i18n_titles(db):
    store.notify(db, 1, "x", {"az": "A", "en": "E", "ru": "R"}, "b")
    store.notify(db, [2, 3], "x", "Başlıq")
    n = store.rows(db, "SELECT * FROM notifications WHERE kind='x' ORDER BY id")
    assert [r["user_id"] for r in n] == [1, 2, 3]
    assert store.J(n[0]["title"]) == {"az": "A", "en": "E", "ru": "R"} and n[1]["title"] == "Başlıq"
    assert all(r["read_at"] is None for r in n)


# ---------------------------------------------------------------- seed invariants
def test_seed_creates_the_demo_world(db):
    q = lambda sql: store.row(db, sql)["n"]  # noqa: E731
    assert q("SELECT COUNT(*) n FROM users WHERE role='student'") == 120
    assert q("SELECT COUNT(*) n FROM courses") == 6 and q("SELECT COUNT(*) n FROM request_types") == 13
    assert q("SELECT COUNT(*) n FROM quizzes") == 10 and q("SELECT COUNT(*) n FROM lessons") > 20
    assert q("SELECT COUNT(*) n FROM attendance WHERE user_id=1 AND status='absent'") == 6   # the "ill on Monday and Tuesday" story
    assert q("SELECT COUNT(*) n FROM documents WHERE status='revoked'") == 1
    assert q("SELECT COUNT(*) n FROM feedback") == 140
    users = {r["username"] for r in store.rows(db, "SELECT username FROM users")}
    assert set(store.setting(db, "demo_logins").values()) <= users


def test_seed_is_reproducible(db):
    names = [r["full_name"] for r in store.rows(db, "SELECT full_name FROM users ORDER BY id")]
    store.reseed()
    assert [r["full_name"] for r in store.rows(db, "SELECT full_name FROM users ORDER BY id")] == names


def test_seeded_office_activity_is_within_office_hours(db):
    for r in store.rows(db, "SELECT created_at FROM requests"):
        assert 9 <= datetime.fromisoformat(r["created_at"]).hour < 18


def test_seed_never_dates_activity_in_the_future(db):
    # a synthetic tutor reply is stamped 4 s after its question; anything later than a minute would be a real shift
    t = store.iso(store.now() + __import__("datetime").timedelta(minutes=1))
    for table, col in (("requests", "created_at"), ("documents", "issued_at"), ("notifications", "created_at"), ("news", "published_at"),
                       ("support_tickets", "created_at"), ("feedback", "created_at"), ("messages", "created_at")):
        assert store.row(db, f"SELECT MAX({col}) m FROM {table}")["m"] <= t, table


# ---------------------------------------------------------------- schema version
def test_init_keeps_an_up_to_date_database(db):
    db.execute("INSERT INTO audit(ts,user_id,action) VALUES('x', 1, 'marker')")
    db.commit()
    store.init()
    assert store.row(db, "SELECT COUNT(*) n FROM audit WHERE action='marker'")["n"] == 1


def test_init_rebuilds_an_outdated_schema(db):
    db.execute("INSERT INTO audit(ts,user_id,action) VALUES('x', 1, 'marker')")
    db.execute("PRAGMA user_version=1")
    db.commit()
    db.close()
    store.init()
    c = store.connect()
    try:
        assert store.row(c, "SELECT COUNT(*) n FROM audit WHERE action='marker'")["n"] == 0
        assert c.execute("PRAGMA user_version").fetchone()[0] == store.SCHEMA_VERSION
    finally:
        c.close()


def test_init_replaces_a_corrupt_database_file():
    store.init(reset=True)
    store.DB_PATH.write_bytes(b"this is not a sqlite database" * 100)
    for p in (store.DB_PATH.with_suffix(".db-wal"), store.DB_PATH.with_suffix(".db-shm")):
        p.unlink(missing_ok=True)
    store.init()
    c = sqlite3.connect(store.DB_PATH)
    try:
        assert c.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 100
    finally:
        c.close()
