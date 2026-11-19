"""Document integrity (tasks/todo.md, Task 45): an issued document is shown from the payload stored at issue, /verify
recomputes its hash, a document without a payload is not verified, and registry numbers come from a sequence."""
import multiprocessing
import os
import re

import pytest

from zeka.legacy import store


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def run(sql, args=()):
    c = store.connect()
    try:
        c.execute(sql, args)
        c.commit()
    finally:
        c.close()


@pytest.fixture(scope="module")
def issued(app_db):
    """A certificate of enrolment issued to the demo student through the office's flow."""
    student, office = app_db.client("student"), app_db.client("office")
    rid = student.post("/api/requests", {"type_code": "enrollment_certificate", "data": {"purpose": "Bank", "lang": "Azərbaycan dili",
                                                                                         "copies": "1", "delivery": "Elektron (QR kodlu PDF)"}}).json["id"]
    office.post(f"/api/requests/{rid}/action", {"action": "approve"})
    doc = office.post(f"/api/requests/{rid}/action", {"action": "issue"}).json["document"]
    return q("SELECT * FROM documents WHERE id=?", (doc["id"],))[0]


def test_a_document_is_shown_as_issued_after_the_holder_changes(app_db, issued):
    office = app_db.client("office")
    sid = issued["holder_id"]
    keep = q("SELECT u.full_name, g.id gid, g.name grp FROM users u JOIN study_groups g ON g.id=u.group_id WHERE u.id=?", (sid,))[0]
    before = office.get(f"/doc/{issued['id']}").text
    run("UPDATE users SET full_name='Başqa Ad Soyad' WHERE id=?", (sid,))
    run("UPDATE study_groups SET name='YENİ-99' WHERE id=?", (keep["gid"],))
    try:
        after = office.get(f"/doc/{issued['id']}").text
        assert keep["full_name"] in after and keep["grp"] in after and "Başqa Ad Soyad" not in after and "YENİ-99" not in after
        assert re.sub(r"\s+", " ", before) == re.sub(r"\s+", " ", after)
        page = app_db.client().get(f"/verify/{issued['verify_code']}").text
        assert "Sənəd etibarlıdır" in page and "SHA-256 ✓" in page
    finally:
        run("UPDATE users SET full_name=? WHERE id=?", (keep["full_name"], sid))
        run("UPDATE study_groups SET name=? WHERE id=?", (keep["grp"], keep["gid"]))


def test_a_transcript_is_shown_as_issued_after_a_published_grade_changes(app_db):
    student, office = app_db.client("student"), app_db.client("office")
    order = {"purpose": "Magistraturaya qəbul", "lang": "Azərbaycan dili", "scope": "Bütün semestrlər", "delivery": "Elektron (QR kodlu PDF)"}
    r = student.post("/api/requests", {"type_code": "transcript", "data": order})
    assert r.status == 200, r.text
    office.post(f"/api/requests/{r.json['id']}/action", {"action": "approve"})
    doc = office.post(f"/api/requests/{r.json['id']}/action", {"action": "issue"}).json["document"]
    row = q("SELECT id, course_name, score, letter, passed FROM final_grades WHERE user_id=? AND score IS NOT NULL ORDER BY id LIMIT 1",
            (student.user["id"],))[0]
    payload = q("SELECT payload FROM documents WHERE id=?", (doc["id"],))[0]["payload"]
    assert row["course_name"] in payload, "the transcript's rows are in the stored payload"
    before = office.get(f"/doc/{doc['id']}").text
    run("UPDATE final_grades SET score=13, letter='F', passed=0 WHERE id=?", (row["id"],))
    try:
        after = office.get(f"/doc/{doc['id']}").text
        assert re.sub(r"\s+", " ", before) == re.sub(r"\s+", " ", after)
        page = app_db.client().get(f"/verify/{doc['verify_code']}").text
        assert "Sənəd etibarlıdır" in page and "SHA-256 ✓" in page
    finally:
        run("UPDATE final_grades SET score=?, letter=?, passed=? WHERE id=?", (row["score"], row["letter"], row["passed"], row["id"]))


@pytest.mark.parametrize("column", ["payload", "hash"])
def test_a_tampered_document_is_reported_changed(app_db, issued, column):
    original = q(f"SELECT {column} FROM documents WHERE id=?", (issued["id"],))[0][column]
    changed = original.replace(issued["reg_no"], issued["reg_no"][:-1] + "9") if column == "payload" else "0" * 64
    run(f"UPDATE documents SET {column}=? WHERE id=?", (changed, issued["id"]))
    try:
        page = app_db.client().get(f"/verify/{issued['verify_code']}").text
        assert "Sənəd dəyişdirilib" in page and "SHA-256 ✓" not in page
    finally:
        run(f"UPDATE documents SET {column}=? WHERE id=?", (original, issued["id"]))


def test_a_document_without_a_payload_is_not_verified_and_not_rebuilt(app_db, issued):
    run("UPDATE documents SET payload=NULL WHERE id=?", (issued["id"],))
    try:
        page = app_db.client().get(f"/verify/{issued['verify_code']}").text
        assert "doğrulanmır" in page and "SHA-256 ✓" not in page
        shown = app_db.client("office").get(f"/doc/{issued['id']}").text
        assert "doğrulanmır" in shown and q("SELECT full_name FROM users WHERE id=?", (issued["holder_id"],))[0]["full_name"] not in shown
    finally:
        run("UPDATE documents SET payload=? WHERE id=?", (issued["payload"], issued["id"]))


def _issue_many(n: int, out):
    c = store.connect()
    try:
        holder = store.row(c, "SELECT id FROM users WHERE role='student' ORDER BY id LIMIT 1")["id"]
        for _ in range(n):
            c.execute("BEGIN IMMEDIATE")
            d = store.issue_document(c, "request", holder, "Arayış", {"type": "free_application"}, None, "PAR")
            c.commit()
            out.put(d["reg_no"])
    finally:
        c.close()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="two processes need fork")
def test_fifty_parallel_issues_from_two_processes_get_fifty_gapless_numbers(app_db):
    ctx = multiprocessing.get_context("fork")
    out = ctx.Queue()
    procs = [ctx.Process(target=_issue_many, args=(25, out)) for _ in range(2)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
    assert all(p.exitcode == 0 for p in procs)
    nos = sorted(int(out.get(timeout=5)[-6:]) for _ in range(50))
    assert nos == list(range(nos[0], nos[0] + 50)), "fifty distinct numbers, no gap"


def test_a_deleted_document_does_not_give_its_number_back(app_db):
    c = store.connect()
    try:
        holder = store.row(c, "SELECT id FROM users WHERE role='student' ORDER BY id LIMIT 1")["id"]
        a = store.issue_document(c, "request", holder, "Arayış", {"type": "free_application"}, None, "DEL")
        c.execute("DELETE FROM documents WHERE id=?", (a["id"],))
        b = store.issue_document(c, "request", holder, "Arayış", {"type": "free_application"}, None, "DEL")
        c.commit()
    finally:
        c.close()
    assert int(b["reg_no"][-6:]) == int(a["reg_no"][-6:]) + 1


def test_the_registry_number_is_not_a_count():
    src = (store.ROOT / "backend" / "zeka" / "legacy" / "store.py").read_text(encoding="utf-8")
    assert not re.search(r"COUNT\(\*\).*reg_no|reg_no.*COUNT\(\*\)", src)
