"""Transcripts from final grades only (tasks/todo.md, Task 21): no transcript before the student's history is reconciled,
the average over every final grade, the credits only of the passed ones, and no synthetic rows anywhere."""
from pathlib import Path

from zeka.legacy import store

BACKEND = Path(__file__).resolve().parents[2] / "backend"
ORDER = {"purpose": "Magistraturaya qəbul", "lang": "Azərbaycan dili", "scope": "Bütün semestrlər", "delivery": "Elektron (QR kodlu PDF)"}


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


def test_an_unreconciled_history_gets_no_transcript_until_the_office_checks_it(app_db):
    student, admin = app_db.client("student"), app_db.client("admin")
    sid = student.user["id"]
    keep = q("SELECT admission_year, history_reconciled_at FROM users WHERE id=?", (sid,))[0]
    run("UPDATE users SET history_reconciled_at=NULL, admission_year=2020 WHERE id=?", (sid,))
    try:
        r = student.post("/api/requests", {"type_code": "transcript", "data": ORDER})
        assert r.status == 400 and "Transkript hələ verilmir" in r.json["error"]
        assert app_db.client("teacher").post(f"/api/journal/students/{sid}/reconcile").status == 403
        assert admin.post(f"/api/journal/students/{sid}/reconcile").status == 200
        assert q("SELECT 1 FROM audit WHERE action='history_reconciled' AND detail=?", (f"#{sid}",))
        assert student.post("/api/requests", {"type_code": "transcript", "data": ORDER}).status == 200
    finally:
        run("UPDATE users SET history_reconciled_at=?, admission_year=? WHERE id=?", (keep["history_reconciled_at"], keep["admission_year"], sid))


def test_a_student_admitted_in_zeka_s_first_term_needs_no_reconciliation(app_db):
    student = app_db.client("student")
    sid = student.user["id"]
    keep = q("SELECT admission_year, history_reconciled_at FROM users WHERE id=?", (sid,))[0]
    first = q("SELECT MIN(teaching_start) d FROM academic_terms")[0]["d"]
    run("UPDATE users SET history_reconciled_at=NULL, admission_year=? WHERE id=?", (int(first[:4]), sid))
    try:
        assert student.post("/api/requests", {"type_code": "transcript", "data": ORDER}).status == 200
    finally:
        run("UPDATE users SET history_reconciled_at=?, admission_year=? WHERE id=?", (keep["history_reconciled_at"], keep["admission_year"], sid))


def test_the_average_counts_every_final_grade_and_the_credits_only_the_passed(app_db):
    student = app_db.client("student")
    sid = student.user["id"]
    run("INSERT INTO final_grades(user_id,term_name,term_start,course_name,credits,score,letter,passed,source,published_at) "
        "VALUES(?,'2024/2025 · yaz semestri','2025-02-01','Kəsilən fənn',5,40,'F',0,'legacy','x')", (sid,))
    try:
        g = student.get("/api/grades").json
        rows = q("SELECT score, credits, passed FROM final_grades WHERE user_id=?", (sid,))
        assert g["average"] == round(sum(r["score"] * r["credits"] for r in rows) / sum(r["credits"] for r in rows), 1)
        assert g["credits"] == sum(r["credits"] for r in rows if r["passed"])
        assert g["past"][0]["name"] == "2024/2025 · yaz semestri", "oldest term first"
        doc_rows = [c for t in g["past"] for c in t["courses"]]
        assert any(c["name"] == "Kəsilən fənn" and not c["passed"] for c in doc_rows)
    finally:
        run("DELETE FROM final_grades WHERE user_id=? AND course_name='Kəsilən fənn'", (sid,))


def test_no_synthetic_transcript_is_left():
    assert not [p for p in BACKEND.rglob("*.py") if "transcript_rows" in p.read_text(encoding="utf-8")]
    assert "sintetikdir" not in (BACKEND / "zeka" / "legacy" / "docs.py").read_text(encoding="utf-8")
