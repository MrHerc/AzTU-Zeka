"""The university's structure and terms (tasks/todo.md, Task 15, slice 1): create, change, deactivate; never delete."""
import pytest

from zeka.legacy import store


def audits(action):
    c = store.connect()
    try:
        return [r["detail"] for r in store.rows(c, "SELECT detail FROM audit WHERE action=?", (action,))]
    finally:
        c.close()


def test_the_demo_structure_links_groups_to_a_faculty(admin):
    faculties = admin.get("/api/directory/faculties").json
    assert faculties["total"] >= 1 and faculties["items"][0]["code"] == "İTT"
    groups = admin.get("/api/directory/groups").json["items"]
    assert groups and all(g["faculty_id"] == faculties["items"][0]["id"] for g in groups)


def test_a_faculty_is_created_changed_deactivated_and_never_deleted(admin):
    r = admin.post("/api/directory/faculties", {"code": "ENR", "name": "Energetika fakültəsi"})
    assert r.status == 200 and r.json["active"] == 1
    fid = r.json["id"]
    assert admin.put(f"/api/directory/faculties/{fid}", {"name": "Energetika və avtomatika fakültəsi"}).json["name"].startswith("Energetika və")
    assert admin.post(f"/api/directory/faculties/{fid}/deactivate").json["active"] == 0
    assert admin.post(f"/api/directory/faculties/{fid}/activate").json["active"] == 1
    assert admin.delete(f"/api/directory/faculties/{fid}").status == 405
    assert any(d.startswith(f"{fid} ·") for d in audits("directory_create"))
    assert any("Energetika və avtomatika" in d for d in audits("directory_update"))
    assert str(fid) in audits("directory_deactivate")


def test_references_must_exist(admin):
    assert admin.post("/api/directory/departments", {"faculty_id": 999999, "code": "XX-1", "name": "Heç yerdə"}).status == 400
    fid = admin.post("/api/directory/faculties", {"code": "MEX", "name": "Mexanika fakültəsi"}).json["id"]
    dep = admin.post("/api/directory/departments", {"faculty_id": fid, "code": "MEX-1", "name": "Tətbiqi mexanika"})
    assert dep.status == 200 and dep.json["faculty_id"] == fid


@pytest.mark.parametrize("body", [
    {"code": "a", "name": "Qısa kod"},
    {"code": "OK", "name": "x"},
    {"code": "OK2", "name": 5},
    {"code": "boşluqlu kod", "name": "Boşluq kodda olmaz"},
])
def test_fields_are_validated_with_a_translated_reason(admin, body):
    r = admin.post("/api/directory/faculties", body, lang="en")
    assert r.status == 400 and r.json["error"] and "sahə" not in r.json["error"]


def test_a_term_whose_teaching_does_not_end_before_the_exams_is_refused(admin):
    good = {"code": "2026-PAYIZ", "name": "2026/2027 payız", "teaching_start": "2026-09-15", "teaching_end": "2026-12-27",
            "exam_start": "2027-01-04", "exam_end": "2027-01-31"}
    r = admin.post("/api/directory/terms", {**good, "exam_start": "2026-12-20"}, lang="en")
    assert r.status == 400 and "exam" in r.json["error"].lower()
    assert admin.post("/api/directory/terms", {**good, "teaching_end": "2026-09-01"}).status == 400
    tid = admin.post("/api/directory/terms", good).json["id"]
    assert admin.put(f"/api/directory/terms/{tid}", {"teaching_end": "2027-01-10"}).status == 400     # checked on the merged record
    assert admin.post("/api/directory/terms", {**good, "code": "Bad date", "teaching_start": "15.09.2026"}).status == 400


def test_a_code_is_unique(admin):
    assert admin.post("/api/directory/faculties", {"code": "TKS", "name": "Telekommunikasiya"}).status == 200
    assert admin.post("/api/directory/faculties", {"code": "TKS", "name": "Başqa"}).status == 409
    other = admin.post("/api/directory/faculties", {"code": "TKS2", "name": "Başqa"}).json["id"]
    assert admin.put(f"/api/directory/faculties/{other}", {"code": "TKS"}).status == 409


def test_lists_are_paged_on_the_server_and_searched_there(admin):
    fid = admin.post("/api/directory/faculties", {"code": "PAGE", "name": "Səhifələmə fakültəsi"}).json["id"]
    for i in range(55):
        assert admin.post("/api/directory/departments", {"faculty_id": fid, "code": f"PG-{i:02d}", "name": f"Kafedra {i:02d}"}).status == 200
    first = admin.get("/api/directory/departments?q=PG-").json
    assert first["total"] >= 55 and len(first["items"]) == 50 and first["pages"] >= 2 and first["page_size"] == 50
    second = admin.get("/api/directory/departments?q=PG-&page=2").json
    assert len(second["items"]) == first["total"] - 50
    assert [d["code"] for d in admin.get("/api/directory/departments?q=PG-07").json["items"]] == ["PG-07"]
    assert admin.get("/api/directory/departments?q=%25").json["total"] == 0       # LIKE wildcards are plain text


def test_only_admin_and_academic_affairs_change_the_structure(app_db):
    for role in ("teacher", "office", "leader"):
        c = app_db.client(role)
        assert c.get("/api/directory/faculties").status == 200, role
        assert c.post("/api/directory/faculties", {"code": f"R-{role}", "name": "Rol yoxlaması"}).status == 403, role
    assert app_db.client("student").get("/api/directory/faculties").status == 403
    assert app_db.client("admin").get("/api/directory/planets").status == 404
