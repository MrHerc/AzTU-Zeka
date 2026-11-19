"""The original file of a lecture material (tasks/todo.md, Task 22, slice 2): kept as uploaded, downloaded by the
course's students and teacher, replaced by a new version that students and the tutor see alone."""
import base64
import hashlib
import io
import zipfile

import pytest

from zeka.legacy import engine, store


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def docx(paras) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paras)
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                                        f"<w:body>{body}</w:body></w:document>")
    return b.getvalue()


V1 = docx(["# Tranzistorlar", "Bipolyar tranzistor — üç qatlı yarımkeçirici cihazdır və gücləndirici kimi işləyir.",
           "Emitter, baza və kollektor tranzistorun üç çıxışıdır və hər birinin rolu fərqlidir."])
V2 = docx(["# Tranzistorlar (yenilənmiş)", "Sahə tranzistoru — gərginliklə idarə olunan yarımkeçirici cihazdır və az güc sərf edir.",
           "Mənbə, axın və qapı sahə tranzistorunun üç çıxışıdır və idarəetmə qapıdan aparılır."])


@pytest.fixture(scope="module")
def course(app_db):
    teacher, student = app_db.client("teacher"), app_db.client("student")
    return q("SELECT c.id FROM courses c JOIN enrollments e ON e.course_id=c.id WHERE c.teacher_id=? AND e.user_id=? ORDER BY c.id LIMIT 1",
             (teacher.user["id"], student.user["id"]))[0]["id"]


def upload(teacher, course, data, name="tranzistor.docx", **kw):
    return teacher.post(f"/api/courses/{course}/materials", {"filename": name, "content_b64": base64.b64encode(data).decode(), **kw})


@pytest.fixture(scope="module")
def first(app_db, course):
    r = upload(app_db.client("teacher"), course, V1)
    assert r.status == 200, r.text
    return r.json["id"]


def test_an_enrolled_student_downloads_the_file_as_uploaded(app_db, course, first):
    got = app_db.client("student").get(f"/api/materials/{first}/file")
    assert got.status == 200 and hashlib.sha256(got.body).hexdigest() == hashlib.sha256(V1).hexdigest()
    assert "attachment" in got.headers["Content-Disposition"] and got.headers["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml")


def test_a_student_of_another_course_gets_404(app_db):
    teacher, student = app_db.client("teacher"), app_db.client("student")
    admin = app_db.client("admin")
    other = admin.post("/api/directory/courses", {"code": "MF-NO", "name": "Başqa fənn", "credits": 3, "teacher_id": teacher.user["id"]}).json["id"]
    mid = upload(teacher, other, V1).json["id"]
    assert student.get(f"/api/materials/{mid}/file").status == 404
    assert student.get(f"/api/materials/{mid}").status == 404


def test_a_demo_material_keeps_its_markdown_original(app_db, course):
    m = q("SELECT id, file_id FROM materials WHERE course_id=? AND file_id IS NOT NULL ORDER BY id LIMIT 1", (course,))[0]
    got = app_db.client("student").get(f"/api/materials/{m['id']}/file")
    assert got.status == 200 and got.headers["Content-Type"].startswith("text/markdown") and got.body.startswith(b"#")


def test_files_that_are_not_materials_are_refused(app_db, course):
    teacher = app_db.client("teacher")
    assert upload(teacher, course, b"MZ\x90\x00" + b"x" * 200, name="virus.exe").status == 400
    assert upload(teacher, course, docx(["# A", "Bir abzas mətn burada uzun olsun ki, çıxarılsın və yoxlansın."]), name="a.pdf").status == 400


def test_a_new_version_replaces_the_old_one_for_students_and_the_tutor(app_db, course, first):
    teacher, student = app_db.client("teacher"), app_db.client("student")
    old_chunks = [r["id"] for r in q("SELECT id FROM chunks WHERE material_id=?", (first,))]
    assert old_chunks
    r = upload(teacher, course, V2, name="tranzistor-v2.docx", replaces=first)
    assert r.status == 200
    new = r.json["id"]
    assert upload(teacher, course, V2, replaces=first).status == 404, "a version replaces the current one only"
    listed = [m["id"] for m in student.get(f"/api/courses/{course}").json["materials_list"]]
    assert new in listed and first not in listed
    teacher_view = {m["id"]: m for m in teacher.get(f"/api/courses/{course}").json["materials_list"]}
    assert teacher_view[first]["replaced"] and teacher_view[new]["replaces_id"] == first
    assert student.get(f"/api/materials/{first}/file").status == 404
    old = teacher.get(f"/api/materials/{first}/file")
    assert old.status == 200 and old.body == V1, "the teacher keeps the earlier version's file"
    assert q("SELECT LENGTH(text) n FROM materials WHERE id=?", (first,))[0]["n"] > 0, "its text stays"
    assert q("SELECT id FROM chunks WHERE material_id=?", (first,)) == []
    hits = {h["id"] for h in engine.INDEX["chunks"].search("tranzistor emitter baza kollektor sahə qapı", k=50)}
    new_chunks = {r["id"] for r in q("SELECT id FROM chunks WHERE material_id=?", (new,))}
    assert hits & new_chunks and not hits & set(old_chunks), "the tutor's index has the current version only"
