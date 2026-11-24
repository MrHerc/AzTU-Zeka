"""Frameworks and the outcome map (tasks/todo.md, Task 24): the NICE file NIST published imports unchanged, idempotently
and per version; Bloom and EQF are built in; one outcome carries items of several frameworks; the picker searches on
the server; a programme's coverage report lists, per work role, the covered and the uncovered statements, as JSON and
CSV, within the caller's scope."""
import csv
import hashlib
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import manage
from zeka.legacy import store
from zeka.modules.syllabus import frameworks

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "content" / "frameworks" / "nice-components-2.2.0.json"
SAMPLE = ROOT / "tests" / "fixtures" / "nice_sample.json"
REAL_COUNTS = {"task": 962, "knowledge": 693, "skill": 556, "work_role": 42, "competency_area": 11, "category": 5, "opm_code": 40, "sort": 47}
ROLE = "OG-WRL-015"


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def run(sql, args=()):
    c = store.connect()
    try:
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def element_counts(doc: dict) -> dict:
    out: dict = {}
    for e in doc["elements"]:
        out[e["element_type"]] = out.get(e["element_type"], 0) + 1
    return out


def fw_id(key, version):
    return q("SELECT id FROM frameworks WHERE key=? AND version=?", (key, version))[0]["id"]


def item_id(key, version, code):
    return q("SELECT i.id FROM framework_items i JOIN frameworks f ON f.id=i.framework_id WHERE f.key=? AND f.version=? AND i.code=?",
             (key, version, code))[0]["id"]


def snapshot():
    return [q(f"SELECT COUNT(*) n, COALESCE(MAX(rowid), 0) m FROM {t}")[0] for t in ("frameworks", "framework_items")] + \
        [q("SELECT COUNT(*) n FROM framework_links")[0], q("SELECT * FROM frameworks ORDER BY id")]  # nosec B608 (constant names)


@pytest.fixture(scope="module")
def sample(app_db):
    assert manage.main(["import-framework", "--file", str(SAMPLE)]) == 0
    return fw_id("nice", "0.0.0-sample")


def make_course(app_db, code="FW-101", n1="Kibertəhlükəsizlik risklərini təhlil edir", department=None):
    """A course of the demo teacher, taught to a group of the demo programme, with a saved syllabus of two outcomes.
    A test that publishes the syllabus or removes an outcome makes its own course (ORD-1): the shared one stays a draft."""
    admin, teacher = app_db.client("admin"), app_db.client("teacher")
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    cid = admin.post("/api/directory/courses", {"code": code, "name": "Çərçivə sınağı", "credits": 5, "term_id": term["id"],
                                                "teacher_id": teacher.user["id"]}).json["id"]
    if department:
        run("UPDATE courses SET department_id=? WHERE id=?", (department, cid))
    unit = admin.post("/api/directory/units", {"course_id": cid, "kind": "lecture", "teacher_id": teacher.user["id"]}).json["id"]
    gid = q("SELECT id FROM study_groups WHERE specialty_id IS NOT NULL ORDER BY id LIMIT 1")[0]["id"]
    assert admin.put(f"/api/directory/units/{unit}/groups", {"group_ids": [gid]}).status == 200
    d = teacher.post(f"/api/syllabi/{cid}/draft").json["data"]
    d["outcomes"] = [{"id": "N1", "text": n1, "bloom": "analyze"},
                     {"id": "N2", "text": "Təhlükəsizlik siyasətinin layihəsini hazırlayır", "bloom": "create"}]
    d["plan"] = [{"week": 1, "topic": "Risklərin təhlili", "outcomes": ["N1", "N2"], "activity": ""}]
    assert teacher.put(f"/api/syllabi/{cid}", {"data": d}).status == 200
    return cid


@pytest.fixture(scope="module")
def course(app_db, sample):
    return make_course(app_db)


def programme():
    return q("SELECT specialty_id FROM study_groups WHERE specialty_id IS NOT NULL ORDER BY id LIMIT 1")[0]["specialty_id"]


def office(app_db):
    reg = app_db.client("office")
    assert reg.post("/api/me/role", {"role": "academic_office"}).status == 200
    return reg


def signed_in(app_db, username, role=None, grant=None):
    """A session of one of the demo's other teachers (the demo login has one teacher; a staff password needs a second
    factor), acting in ``role`` with ``grant``."""
    c = store.connect()
    try:
        logins = store.setting(c, "demo_logins")
        store.set_setting(c, "demo_logins", {**logins, "teacher": username})
        c.commit()
        s = app_db.client("teacher")
    finally:
        store.set_setting(c, "demo_logins", logins)
        c.commit()
        c.close()
    assert s.user["username"] == username
    if role:
        scope_type, scope_id = grant
        assert app_db.client("admin").post(f"/api/admin/users/{s.user['id']}/roles",
                                           {"role": role, "scope_type": scope_type, "scope_id": scope_id}).status == 200
        assert s.post("/api/me/role", {"role": role}).status == 200
    return s


# ---------------------------------------------------------------- the file and the sample
def test_the_sample_is_cut_from_the_file_nist_published():
    real, sample = json.loads(REAL.read_text(encoding="utf-8")), json.loads(SAMPLE.read_text(encoding="utf-8"))
    assert hashlib.sha256(REAL.read_bytes()).hexdigest() == frameworks.KNOWN[("nice", "2.2.0")][0], "the file is byte-identical"
    by_id = {e["element_identifier"]: e for e in real["elements"]}
    assert all(by_id.get(e["element_identifier"]) == e for e in sample["elements"]), "every sample element exists identically"
    rels = {json.dumps(r, sort_keys=True) for r in real["relationships"]}
    assert all(json.dumps(r, sort_keys=True) in rels for r in sample["relationships"])
    assert sample["documents"] == [{**real["documents"][0], "version": "0.0.0-sample"}]
    sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
    import make_nice_sample
    assert make_nice_sample.cut(real) == sample, "the committed sample is what the script cuts"


def test_the_full_file_imports_with_a_row_per_element_and_a_second_import_changes_nothing(app_db, capsys):
    real = json.loads(REAL.read_text(encoding="utf-8"))
    assert element_counts(real) == REAL_COUNTS
    assert manage.main(["import-framework", "--file", str(REAL)]) == 0
    fid = fw_id("nice", "2.2.0")
    stored = {r["kind"]: r["n"] for r in q("SELECT kind, COUNT(*) n FROM framework_items WHERE framework_id=? GROUP BY kind", (fid,))}
    assert stored == REAL_COUNTS
    links = q("SELECT COUNT(*) n FROM framework_links l JOIN framework_items i ON i.id=l.source_id WHERE i.framework_id=?", (fid,))[0]["n"]
    assert links == len(real["relationships"]) == 5950
    out = capsys.readouterr().out
    assert "imported" in out and "task             file    962   database    962" in out
    f = q("SELECT * FROM frameworks WHERE id=?", (fid,))[0]
    assert (f["sha256"], f["size"], f["source_url"]) == (frameworks.KNOWN[("nice", "2.2.0")][0], 2674252, frameworks.KNOWN[("nice", "2.2.0")][1])
    role = q("SELECT parent, title FROM framework_items WHERE framework_id=? AND code='DD-WRL-002'", (fid,))[0]
    assert role == {"parent": "DD", "title": "Enterprise Architecture"}, "a work role's parent is its category"
    assert not q("SELECT 1 FROM framework_items WHERE framework_id=? AND kind<>'work_role' AND parent IS NOT NULL", (fid,)), \
        "only a work role has a parent (MUT-n10)"
    before = snapshot()
    assert manage.main(["import-framework", "--file", str(REAL)]) == 0
    assert "already imported, nothing changed" in capsys.readouterr().out
    assert snapshot() == before


def test_an_edited_copy_of_a_known_version_and_a_changed_file_of_an_imported_version_are_refused(app_db, sample, tmp_path, capsys):
    raw = REAL.read_bytes()
    edited = tmp_path / "edited.json"
    edited.write_bytes(raw.replace(b"Knowledge of encryption algorithms", b"Knowledge of encryption algorithmz", 1))
    before = snapshot()
    assert manage.main(["import-framework", "--file", str(edited)]) == 1
    assert "SHA-256" in capsys.readouterr().err
    doc = json.loads(SAMPLE.read_text(encoding="utf-8"))
    doc["documents"][0]["version"] = "2.2.0"                       # a cut-down copy that says it is 2.2.0
    edited.write_text(json.dumps(doc), encoding="utf-8")
    assert manage.main(["import-framework", "--file", str(edited)]) == 1
    doc = json.loads(SAMPLE.read_text(encoding="utf-8"))
    doc["elements"][-1]["text"] += "."                             # the sample's version, other content
    edited.write_text(json.dumps(doc), encoding="utf-8")
    assert manage.main(["import-framework", "--file", str(edited)]) == 1
    assert "already imported from another file" in capsys.readouterr().err
    assert snapshot() == before


@pytest.mark.parametrize("raw,why", [
    (b"\xff\xfe", "not UTF-8"), (b"[]", "not an object"), (b'{"documents": [], "elements": [], "relationships": []}', "no document"),
    (json.dumps({"documents": [{"doc_identifier": "X", "version": "1", "name": "n"}], "elements": [
        {"element_identifier": "A", "element_type": "task", "title": "", "text": "t", "doc_identifier": "X"}],
        "relationships": [{"source_element_identifier": "A", "dest_element_identifier": "B"}]}).encode(), "a link to a missing element"),
    (json.dumps({"documents": [{"doc_identifier": "X", "version": "1", "name": "n"}], "elements": [
        {"element_identifier": "A", "element_type": "task", "title": "", "text": "t", "doc_identifier": "X"}] * 2,
        "relationships": []}).encode(), "an element twice"),
    (json.dumps({"documents": [{"doc_identifier": "X", "version": "1", "name": "n"}], "elements": [
        {"element_identifier": "A", "element_type": "Task!", "title": "", "text": "t", "doc_identifier": "X"}],
        "relationships": []}).encode(), "a bad type"),
    (json.dumps({"documents": [{"doc_identifier": "X", "version": "1", "name": "n"}, {"doc_identifier": "Y", "version": "1", "name": "n"}],
                 "elements": [], "relationships": []}).encode(), "two documents"),
    (json.dumps({"documents": [{"doc_identifier": "X", "version": "1", "name": "n"}], "elements": [
        {"element_identifier": "A", "element_type": "task", "title": "", "text": "t", "doc_identifier": "Y"}],
        "relationships": []}).encode(), "an element of another document"),
    (json.dumps({"documents": [{"doc_identifier": "X", "version": "1" * 41, "name": "n"}], "elements": [],
                 "relationships": []}).encode(), "a version longer than 40"),
    (b"[" * 200000 + b"]" * 200000, "nested too deep (SEC-FW-4)"),
])
def test_a_file_that_is_not_a_framework_file_is_refused(raw, why):
    with pytest.raises(frameworks.FrameworkError):
        frameworks.parse_cprt(raw)


def test_a_file_over_the_limit_is_refused_before_it_is_read(app_db, tmp_path, monkeypatch, capsys):
    """MUT-parse n06 and SEC-FW-4: the limit holds in the import and in the command, which checks the size before it
    reads the file; a file nested too deep ends as a refusal, not a traceback."""
    monkeypatch.setattr(frameworks, "MAX_FILE", 100)
    with pytest.raises(frameworks.FrameworkError) as refused:
        frameworks.import_file(None, json.dumps({"documents": [], "pad": "x" * 100}).encode())
    assert refused.value.args[0]["en"] == "The file is too large"
    big = tmp_path / "big.json"
    big.write_bytes(b" " * 101)
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("the file was read"))
    assert manage.main(["import-framework", "--file", str(big)]) == 1 and "larger than" in capsys.readouterr().err
    monkeypatch.undo()
    deep = tmp_path / "deep.json"
    deep.write_bytes(b"[" * 200000 + b"]" * 200000)
    assert manage.main(["import-framework", "--file", str(deep)]) == 1 and "not JSON" in capsys.readouterr().err


def test_versions_sort_by_their_numbers():
    """MUT-c08: 10.0.0 is newer than 9.0.0."""
    assert sorted(["10.0.0", "9.0.0", "2.2.0", "0.0.0-sample", "2.10.0"], key=frameworks._vkey) == \
        ["0.0.0-sample", "2.2.0", "2.10.0", "9.0.0", "10.0.0"]


def test_a_version_nist_did_not_publish_imports_unverified_and_is_never_the_default(app_db, sample, course, tmp_path, capsys):
    """SEC-FW-3, BR-F3: an edited copy under a version KNOWN does not hold imports without a source, is marked
    unverified, is listed after the verified versions and is not the report's default."""
    if not q("SELECT 1 FROM frameworks WHERE key='nice' AND version='2.2.0'"):
        assert manage.main(["import-framework", "--file", str(REAL)]) == 0
    doc = json.loads(SAMPLE.read_text(encoding="utf-8"))
    doc["documents"][0]["version"] = "9.9.9"
    doc["elements"][-1]["text"] = "TAMPERED statement"
    f = tmp_path / "tampered.json"
    f.write_text(json.dumps(doc), encoding="utf-8")
    capsys.readouterr()
    assert manage.main(["import-framework", "--file", str(f)]) == 0 and "not verified" in capsys.readouterr().out
    assert q("SELECT source_url FROM frameworks WHERE key='nice' AND version='9.9.9'")[0]["source_url"] is None
    nice = [(x["version"], x["verified"]) for x in app_db.client("teacher").get("/api/frameworks").json if x["key"] == "nice"]
    assert nice == [("2.2.0", True), ("9.9.9", False), ("0.0.0-sample", False)]
    rep = app_db.client("admin").get(f"/api/frameworks/coverage?programme={programme()}").json
    assert rep["framework"]["version"] == "2.2.0" and rep["framework"]["verified"]


# ---------------------------------------------------------------- built-in frameworks and the picker
def test_bloom_and_eqf_are_built_in_with_working_translations(app_db):
    fws = {f["key"]: f for f in app_db.client("teacher", lang="en").get("/api/frameworks").json}
    assert fws["bloom"]["counts"] == {"level": 6} and fws["bloom"]["builtin"]
    assert fws["eqf"]["counts"] == {"knowledge": 8, "level": 8, "responsibility": 8, "skill": 8}
    assert fws["eqf"]["title"] == "European Qualifications Framework (EQF)" and "working translation" in fws["eqf"]["note"]
    ru = app_db.client("teacher", lang="ru").get(f"/api/frameworks/{fws['eqf']['id']}/items?kind=knowledge&size=8").json["items"]
    az = app_db.client("teacher").get(f"/api/frameworks/{fws['eqf']['id']}/items?kind=knowledge&size=8").json["items"]
    assert [x["code"] for x in az] == [f"{n}-K" for n in range(1, 9)] and az[0]["text"] == "Əsas ümumi bilik"
    assert ru[0]["text"] and ru[0]["text"] != az[0]["text"]
    run("UPDATE framework_items SET text='köhnə mətn' WHERE code='1-K'")
    c = store.connect()
    try:
        frameworks.ensure_builtin(c)                                # every start: a changed text is written back, the ids stay
        c.commit()
    finally:
        c.close()
    assert {f["key"]: f["id"] for f in app_db.client("teacher").get("/api/frameworks").json}["eqf"] == fws["eqf"]["id"]
    assert q("SELECT text FROM framework_items WHERE code='1-K'")[0]["text"] == "Əsas ümumi bilik"
    keep = q("SELECT title, source_url, counts FROM frameworks WHERE key='eqf'")[0]
    run("UPDATE frameworks SET title='köhnə', source_url=NULL, counts='{}' WHERE key='eqf'")   # MUT-n11: the row is written back too
    c = store.connect()
    try:
        frameworks.ensure_builtin(c)
        c.commit()
    finally:
        c.close()
    assert q("SELECT title, source_url, counts FROM frameworks WHERE key='eqf'")[0] == keep


def test_a_corrected_builtin_text_replaces_the_old_row_and_the_outcome_maps_keep_their_items(app_db, course):
    """A start after a text correction (content/frameworks/README.md): the stored item is rewritten in place by its code,
    so its id, the outcome maps and a submitted version's frozen tags still point at it and show the new text."""
    t = app_db.client("teacher", lang="en")
    ids = [item_id("eqf", "2017", "7-K"), item_id("bloom", "2001", "understand")]
    assert t.put(f"/api/syllabi/{course}/outcomes/N1/items", {"items": ids}).status == 200
    before = q("SELECT outcome, item_id FROM outcome_items WHERE course_id=? ORDER BY item_id", (course,))
    items = {code: text for code, _, _, _, text in frameworks.BUILTIN[1]["items"]} | \
        {code: text for code, _, _, _, text in frameworks.BUILTIN[0]["items"]}
    run("UPDATE framework_items SET text='köhnə mətn', title='köhnə ad' WHERE id IN (?, ?)", tuple(ids))   # an older release's rows
    c = store.connect()
    try:
        frameworks.ensure_builtin(c)
        c.commit()
    finally:
        c.close()
    got = q("SELECT id, code, title, text FROM framework_items WHERE id IN (?, ?) ORDER BY id", tuple(ids))
    assert [g["id"] for g in got] == sorted(ids) and all(g["text"] == items[g["code"]] for g in got)
    assert q("SELECT outcome, item_id FROM outcome_items WHERE course_id=? ORDER BY item_id", (course,)) == before
    tags = {x["code"]: x for x in t.get(f"/api/syllabi/{course}/frameworks").json["outcomes"]["N1"]}
    assert tags["7-K"]["text"].startswith("Highly specialised knowledge, some of which is at the forefront of knowledge")
    assert tags["understand"]["title"] == "Understand"
    c = store.connect()
    try:
        frozen = frameworks.outcome_items(c, course, frozen=json.dumps({"N1": ids}))["N1"]
    finally:
        c.close()
    assert {x["id"]: x["text"] for x in frozen} == {g["id"]: g["text"] for g in got}
    assert t.put(f"/api/syllabi/{course}/outcomes/N1/items", {"items": []}).status == 200   # the shared course as it was


def test_the_picker_searches_on_the_server_paged_and_scoped_to_a_work_role(app_db, sample):
    t = app_db.client("teacher")
    page = t.get(f"/api/frameworks/{sample}/items?kind=knowledge&size=10").json
    assert len(page["items"]) == 10 and page["more"] and {x["kind"] for x in page["items"]} == {"knowledge"}
    nxt = t.get(f"/api/frameworks/{sample}/items?kind=knowledge&size=10&page=2").json["items"]
    assert not {x["id"] for x in nxt} & {x["id"] for x in page["items"]}
    found = t.get(f"/api/frameworks/{sample}/items?q=artificial%20intelligence&size=100").json["items"]
    assert found and all("artificial intelligence" in (x["text"] + x["title"]).lower() for x in found)
    assert t.get(f"/api/frameworks/{sample}/items?q=%25%25%25").json["items"] == [], "a % is searched for, not a wildcard"
    doc = json.loads(SAMPLE.read_text(encoding="utf-8"))
    linked = {r["dest_element_identifier"] for r in doc["relationships"] if r["source_element_identifier"] == ROLE}
    scoped = t.get(f"/api/frameworks/{sample}/items?role={ROLE}&kind=task&size=100").json["items"]
    assert scoped and {x["code"] for x in scoped} <= linked and all(x["kind"] == "task" for x in scoped)
    assert len(scoped) == sum(1 for e in doc["elements"] if e["element_identifier"] in linked and e["element_type"] == "task")
    assert t.get(f"/api/frameworks/{sample}/items?role=K0018").status == 404, "no such item"
    assert t.get(f"/api/frameworks/{sample}/items?role=OG").status == 404, "a category is not a work role (MUT-p02)"
    bloom = fw_id("bloom", "2001")                                   # six levels: a last page that is full has no next one (MUT-p04)
    assert t.get(f"/api/frameworks/{bloom}/items?size=3").json["more"] is True
    assert t.get(f"/api/frameworks/{bloom}/items?size=3&page=2").json["more"] is False
    assert t.get(f"/api/frameworks/{bloom}/items?size=6").json["more"] is False
    assert t.get("/api/frameworks/999999/items").status == 404
    assert app_db.client("student").get(f"/api/frameworks/{sample}/items").status == 403


# ---------------------------------------------------------------- the outcome map
def statements(sample, kind, n):
    return [x["id"] for x in q("SELECT i.id FROM framework_items i JOIN framework_links l ON l.dest_id=i.id JOIN framework_items r "
                                "ON r.id=l.source_id WHERE r.code=? AND r.framework_id=? AND i.kind=? ORDER BY i.code LIMIT ?",
                                (ROLE, sample, kind, n))]


def test_one_outcome_carries_items_of_several_frameworks_and_a_new_version_keeps_them(app_db, sample, course):
    t = app_db.client("teacher")
    ids = statements(sample, "task", 1) + [item_id("bloom", "2001", "analyze"), item_id("eqf", "2017", "6-K")]
    r = t.put(f"/api/syllabi/{course}/outcomes/N1/items", {"items": ids})
    assert r.status == 200
    tags = r.json["outcomes"]["N1"]
    assert {x["key"] for x in tags} == {"nice", "bloom", "eqf"} and {x["id"] for x in tags} == set(ids)
    who = q("SELECT mapped_by, mapped_at FROM outcome_items WHERE course_id=? AND outcome='N1'", (course,))
    assert len(who) == 3 and {w["mapped_by"] for w in who} == {t.user["id"]} and all(w["mapped_at"] for w in who)
    d = t.get(f"/api/syllabi/{course}").json["latest"]["data"]
    d["description"] = "Yeni versiya"
    assert t.put(f"/api/syllabi/{course}", {"data": d}).status == 200
    assert {x["id"] for x in t.get(f"/api/syllabi/{course}/frameworks").json["outcomes"]["N1"]} == set(ids), "the key is course + outcome"
    assert t.put(f"/api/syllabi/{course}/outcomes/N1/items", {"items": ids[:2]}).status == 200
    assert len(q("SELECT 1 FROM outcome_items WHERE course_id=? AND outcome='N1'", (course,))) == 2, "a removed tag goes"
    assert q("SELECT 1 FROM audit WHERE action='syllabus_outcome_map' LIMIT 1")


def test_only_a_teacher_of_the_course_maps_a_saved_outcome_with_statements(app_db, sample, course):
    t = app_db.client("teacher")
    stranger = signed_in(app_db, "t01")
    ok = statements(sample, "knowledge", 1)
    assert stranger.put(f"/api/syllabi/{course}/outcomes/N2/items", {"items": ok}).status == 404, "another teacher's course"
    assert app_db.client("admin").put(f"/api/syllabi/{course}/outcomes/N2/items", {"items": ok}).status == 403
    assert t.put(f"/api/syllabi/{course}/outcomes/N9/items", {"items": ok}).status == 404, "not an outcome of the saved syllabus"
    assert t.put(f"/api/syllabi/{course}/outcomes/x/items", {"items": ok}).status == 404
    role = q("SELECT id FROM framework_items WHERE framework_id=? AND code=?", (sample, ROLE))[0]["id"]
    assert t.put(f"/api/syllabi/{course}/outcomes/N2/items", {"items": [role]}).status == 400, "a work role is not a statement"
    assert t.put(f"/api/syllabi/{course}/outcomes/N2/items", {"items": [10 ** 9]}).status == 400
    assert t.put(f"/api/syllabi/{course}/outcomes/N2/items", {"items": ok * 2}).status == 400
    many = [r["id"] for r in q("SELECT id FROM framework_items WHERE framework_id=? AND kind='knowledge' ORDER BY id LIMIT 51", (sample,))]
    assert t.put(f"/api/syllabi/{course}/outcomes/N2/items", {"items": many}).status == 400, "51 statements"
    assert t.put(f"/api/syllabi/{course}/outcomes/N2/items", {"items": many[:50]}).status == 200, "50 are allowed"
    assert t.put(f"/api/syllabi/{course}/outcomes/N2/items", {"items": "K0018"}).status == 400
    assert t.put(f"/api/syllabi/{course}/outcomes/N2/items", {"items": ["abc"]}).status == 400
    assert stranger.get(f"/api/syllabi/{course}/frameworks").status == 404
    assert t.get(f"/api/syllabi/{course}/frameworks").json["can_map"] is True
    assert app_db.client("admin").get(f"/api/syllabi/{course}/frameworks").json["can_map"] is False, "a reader only (MUT-m07)"
    assert t.put(f"/api/syllabi/{course}/outcomes/N2/items", {"items": ok}).status == 200


# ---------------------------------------------------------------- the coverage report
def test_the_coverage_report_lists_covered_and_uncovered_statements_per_work_role(app_db, sample, course):
    t, reg, sid = app_db.client("teacher"), office(app_db), programme()
    task = statements(sample, "task", 1)
    assert t.put(f"/api/syllabi/{course}/outcomes/N1/items", {"items": task}).status == 200
    rep = reg.get(f"/api/frameworks/coverage?programme={sid}&framework={sample}&role={ROLE}").json
    assert {r["code"] for r in rep["roles"]} == {"OG-WRL-015", "IO-WRL-003", "DD-WRL-009"}
    row = next(r for r in rep["roles"] if r["code"] == ROLE)
    assert row["kinds"]["task"]["covered"] == 1 and row["covered"] == 1 + row["kinds"]["knowledge"]["covered"]
    detail = rep["role"]["statements"]
    covered = [s for s in detail if s["covered_by"]]
    hit = next(s for s in covered if s["kind"] == "task")
    assert hit["covered_by"] == [{"course_id": course, "course": "FW-101", "name": "Çərçivə sınağı", "outcome": "N1",
                                  "text": "Kibertəhlükəsizlik risklərini təhlil edir"}]
    uncovered = [s for s in detail if not s["covered_by"]]
    assert len(uncovered) == row["total"] - row["covered"] > 0
    r = reg.get(f"/api/frameworks/coverage?programme={sid}&framework={sample}&format=csv")
    assert r.status == 200 and r.headers["Content-Type"].startswith("text/csv") and r.body.startswith(b"\xef\xbb\xbf")
    lines = list(csv.reader(io.StringIO(r.body.decode("utf-8-sig"))))
    assert lines[0][0] == "İş rolu" and len(lines) - 1 == sum(x["total"] for x in rep["roles"])
    mine = [x for x in lines[1:] if x[0] == ROLE and x[4] == hit["code"]]
    assert mine and mine[0][6] == "Bəli" and mine[0][7] == "FW-101 N1: Kibertəhlükəsizlik risklərini təhlil edir"
    assert sum(1 for x in lines[1:] if x[6] == "Xeyr") == sum(x["total"] - x["covered"] for x in rep["roles"])
    en = reg.get(f"/api/frameworks/coverage?programme={sid}&framework={sample}&format=csv&lang=en").body.decode("utf-8-sig")
    assert en.startswith("Work role,")


def test_an_outcome_the_syllabus_no_longer_has_covers_nothing_and_its_code_starts_empty(app_db, sample):
    """ORD-1: its own course, which nothing publishes; BR-F2: a later outcome given a removed outcome's code inherits nothing."""
    t, admin, sid = app_db.client("teacher"), app_db.client("admin"), programme()
    cid = make_course(app_db, "FW-102")
    assert t.put(f"/api/syllabi/{cid}/outcomes/N2/items", {"items": statements(sample, "skill", 1)}).status == 200

    def covered():
        rep = admin.get(f"/api/frameworks/coverage?programme={sid}&framework={sample}&role={ROLE}").json
        return [b["outcome"] for s in rep["role"]["statements"] for b in s["covered_by"] if b["course_id"] == cid]
    assert covered() == ["N2"]
    d = t.get(f"/api/syllabi/{cid}").json["latest"]["data"]
    without = {**d, "outcomes": d["outcomes"][:1], "plan": [{**w, "outcomes": ["N1"]} for w in d["plan"]]}
    assert t.put(f"/api/syllabi/{cid}", {"data": without}).status == 200
    assert covered() == [], "N2 is not in the version the report reads"
    assert "N2" not in t.get(f"/api/syllabi/{cid}/frameworks").json["outcomes"], "a saved version without N2 drops its items"
    other = {**d, "outcomes": [d["outcomes"][0], {"id": "N2", "text": "Ofis sənədlərini formatlaşdırır və çap edir", "bloom": "apply"}]}
    assert t.put(f"/api/syllabi/{cid}", {"data": other}).status == 200
    assert covered() == [] and "N2" not in t.get(f"/api/syllabi/{cid}/frameworks").json["outcomes"], "the new N2 starts empty"


def test_the_editor_never_reuses_a_code_that_still_has_items():
    """BR-F2 in the editor: deleting N3 and adding an outcome before saving must not give the new one N3's items."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    line = next(x for x in (ROOT / "frontend" / "js" / "syllabus.js").read_text(encoding="utf-8").splitlines() if x.startswith("const nextId"))
    out = subprocess.run([node, "-e", line + "\nconsole.log(nextId([{id: 'N1'}, {id: 'N2'}], {N3: [{}]}), nextId([{id: 'N1'}]), "
                          "nextId([], {}))"], capture_output=True, text=True, timeout=30, check=True)
    assert out.stdout.split() == ["N4", "N2", "N1"]


def test_the_coverage_report_answers_within_the_caller_s_scope(app_db, sample, course):
    sid, admin = programme(), app_db.client("admin")
    fac = q("SELECT faculty_id FROM specialties WHERE id=?", (sid,))[0]["faculty_id"]
    other_fac = run("INSERT INTO faculties(code,name,active,created_at,updated_at) VALUES('FWX','Başqa fakültə',1,'2026-01-01','2026-01-01')")
    other = run("INSERT INTO specialties(faculty_id,code,name,created_at,updated_at) VALUES(?,'FW-999','Başqa ixtisas','2026-01-01','2026-01-01')",
                (other_fac,))
    url = f"/api/frameworks/coverage?framework={sample}&programme="
    assert app_db.client("leader").get(url + str(sid)).status == 200 and admin.get(url + str(other)).status == 200
    assert office(app_db).get(url + str(other)).status == 200, "the academic office's grant has no scope"
    head = signed_in(app_db, "t02", "dept_head", ("faculty", fac))
    assert head.get(url + str(sid)).status == 200
    assert head.get(url + str(other)).status == 404 and head.get(url + str(other) + "&format=csv").status == 404
    assert [p["id"] for p in head.get("/api/frameworks/programmes").json] == [sid]
    narrow = signed_in(app_db, "t03", "dept_head", ("course", course))
    assert narrow.get(url + str(sid)).status == 404 and narrow.get("/api/frameworks/programmes").json == []
    assert app_db.client("teacher").get(url + str(sid)).status == 403 and app_db.client("student").get(url + str(sid)).status == 403
    assert admin.get(url + "999999").status == 404 and admin.get(f"/api/frameworks/coverage?programme={sid}&framework=999999").status == 404
    assert admin.get(url + str(sid) + "&role=NOPE").status == 404


# ---------------------------------------------------------------- versions, the printed and the published syllabus
def test_a_newer_version_leaves_the_older_version_and_its_maps_readable(app_db, sample, course):
    t, sid = app_db.client("teacher"), programme()
    task = statements(sample, "task", 1)
    assert t.put(f"/api/syllabi/{course}/outcomes/N1/items", {"items": task}).status == 200
    assert manage.main(["import-framework", "--file", str(REAL)]) == 0
    versions = [f["version"] for f in t.get("/api/frameworks").json if f["key"] == "nice"]
    assert versions.index("2.2.0") < versions.index("0.0.0-sample"), "the newest first, the older one kept"
    assert task[0] in {x["id"] for x in t.get(f"/api/syllabi/{course}/frameworks").json["outcomes"]["N1"]}
    old = app_db.client("admin").get(f"/api/frameworks/coverage?programme={sid}&framework={sample}").json
    assert next(r for r in old["roles"] if r["code"] == ROLE)["kinds"]["task"]["covered"] == 1
    new = app_db.client("admin").get(f"/api/frameworks/coverage?programme={sid}").json
    assert new["framework"]["version"] == "2.2.0" and len(new["roles"]) == 42, "the default is the newest NICE version"


def test_the_printed_and_the_published_syllabus_show_the_tags_it_was_submitted_with(app_db, sample):
    """SEC-FW-1, BR-F1: a change of the outcome map after submission, by the head teacher or by a teacher of one of the
    course's units who cannot edit the syllabus, reaches neither the published page nor the coverage report; it reaches
    the next version once that is submitted, approved and published. MUT-c05: the report reads the published version,
    not a later draft."""
    t, admin, sid = app_db.client("teacher"), app_db.client("admin"), programme()
    cid = make_course(app_db, "FW-103")
    skill, create, remember = statements(sample, "skill", 1), item_id("bloom", "2001", "create"), item_id("bloom", "2001", "remember")
    assert t.put(f"/api/syllabi/{cid}/outcomes/N2/items", {"items": [create, *skill]}).status == 200
    page = t.get(f"/syllabus/{cid}")
    assert page.status == 200 and "Çərçivə bəndləri" in page.text and "BLOOM 2001 · create — Yaratmaq" in page.text
    student = app_db.client("student")
    admin.post(f"/api/directory/courses/{cid}/enrollments", {"user_id": student.user["id"]})
    assert student.get(f"/syllabus/{cid}").status == 404, "nothing published yet"
    head = signed_in(app_db, "t04", "dept_head", ("course", cid))

    def publish():
        vid = t.get(f"/api/syllabi/{cid}").json["latest"]["id"]
        for client, action in ((t, "submit"), (head, "approve"), (office(app_db), "publish")):
            assert client.post(f"/api/syllabi/{cid}/versions/{vid}/{action}", {}).status == 200, action
        return vid

    def covered():
        rep = admin.get(f"/api/frameworks/coverage?programme={sid}&framework={sample}&role={ROLE}").json
        return [b["outcome"] for s in rep["role"]["statements"] for b in s["covered_by"] if b["course_id"] == cid]
    vid = publish()
    assert "BLOOM 2001 · create — Yaratmaq" in student.get(f"/syllabus/{cid}").text and covered() == ["N2"]
    lab = signed_in(app_db, "t05")
    assert admin.post("/api/directory/units", {"course_id": cid, "kind": "lab", "teacher_id": lab.user["id"]}).status == 200
    assert lab.get(f"/api/syllabi/{cid}").json["can_edit"] is False
    assert lab.put(f"/api/syllabi/{cid}/outcomes/N2/items", {"items": [remember]}).status == 200, "a unit teacher tags the working map"
    for page in (student.get(f"/syllabus/{cid}").text, head.get(f"/syllabus/{cid}?v={vid}").text):
        assert "BLOOM 2001 · create — Yaratmaq" in page and "Xatırlamaq" not in page, "the published version keeps its map"
    assert covered() == ["N2"], "the report reads the published version's map"
    d = t.get(f"/api/syllabi/{cid}").json["latest"]["data"]
    without = {**d, "outcomes": d["outcomes"][:1], "plan": [{**w, "outcomes": ["N1"]} for w in d["plan"]]}
    assert t.put(f"/api/syllabi/{cid}", {"data": without}).status == 200
    assert covered() == ["N2"], "a draft without N2 does not change what the published syllabus covers"
    assert t.put(f"/api/syllabi/{cid}", {"data": d}).status == 200
    assert t.put(f"/api/syllabi/{cid}/outcomes/N2/items", {"items": [remember]}).status == 200
    assert "Yaratmaq" in student.get(f"/syllabus/{cid}").text
    publish()
    page = student.get(f"/syllabus/{cid}").text
    assert "BLOOM 2001 · remember — Xatırlamaq" in page and "Yaratmaq" not in page and covered() == []


def test_a_department_head_reads_the_department_s_programmes_and_no_other_department_s_draft(app_db, sample):
    """MUT-c02: a department grant covers that department's programme. SEC-FW-2: the outcome texts of a course the head
    may not read come only from its published version; a draft of another department's course stays out. MUT-c15: a
    course whose unit is inactive is not the programme's."""
    t, admin, sid = app_db.client("teacher"), app_db.client("admin"), programme()
    spec = q("SELECT faculty_id, department_id FROM specialties WHERE id=?", (sid,))[0]
    mine = run("INSERT INTO departments(faculty_id,code,name,created_at,updated_at) VALUES(?,'FW-DA','Kafedra A','2026-01-01','2026-01-01')",
               (spec["faculty_id"],))
    theirs = run("INSERT INTO departments(faculty_id,code,name,created_at,updated_at) VALUES(?,'FW-DB','Kafedra B','2026-01-01','2026-01-01')",
                 (spec["faculty_id"],))
    run("UPDATE specialties SET department_id=? WHERE id=?", (mine, sid))
    try:
        draft = "Qaralama mətni: hələ təqdim olunmayıb"
        cid = make_course(app_db, "FW-104", n1=draft, department=theirs)
        assert t.put(f"/api/syllabi/{cid}/outcomes/N1/items", {"items": statements(sample, "task", 1)}).status == 200
        head = signed_in(app_db, "t06", "dept_head", ("department", mine))
        assert sid in [p["id"] for p in head.get("/api/frameworks/programmes").json], "the department's programme"
        url = f"/api/frameworks/coverage?programme={sid}&framework={sample}&role={ROLE}"
        assert head.get(f"/api/syllabi/{cid}").status == 404
        rep = head.get(url)
        assert rep.status == 200 and draft not in rep.text and draft not in head.get(url + "&format=csv").text
        assert draft in admin.get(url).text, "a reader of the course sees its latest version"
        before = admin.get(url).json["courses"]
        run("UPDATE teaching_units SET active=0 WHERE course_id=?", (cid,))
        rep = admin.get(url)
        assert rep.json["courses"] == before - 1 and draft not in rep.text, "an inactive unit does not make the course the programme's"
    finally:
        run("UPDATE specialties SET department_id=? WHERE id=?", (spec["department_id"], sid))


def test_a_cell_of_the_coverage_csv_never_starts_a_formula(app_db, course, tmp_path):
    """MUT-csv (c10): a framework's codes and texts, and a course's outcome text, come from outside; a cell that a
    spreadsheet would run starts with a quote."""
    doc = {"documents": [{"doc_identifier": "CSV_TEST", "version": "1", "name": "CSV test"}], "elements": [
        {"element_identifier": "=R1", "element_type": "work_role", "title": '=HYPERLINK("http://evil.example")', "text": "-r",
         "doc_identifier": "CSV_TEST"},
        {"element_identifier": "@T1", "element_type": "task", "title": "", "text": "+SUM(1)", "doc_identifier": "CSV_TEST"}],
        "relationships": [{"source_element_identifier": "=R1", "dest_element_identifier": "@T1"}]}
    f = tmp_path / "csv.json"
    f.write_text(json.dumps(doc), encoding="utf-8")
    assert manage.main(["import-framework", "--file", str(f)]) == 0
    fid, t = fw_id("csv_test", "1"), app_db.client("teacher")
    before = [x["id"] for x in t.get(f"/api/syllabi/{course}/frameworks").json["outcomes"].get("N1", [])]
    assert t.put(f"/api/syllabi/{course}/outcomes/N1/items", {"items": [*before, item_id("csv_test", "1", "@T1")]}).status == 200
    body = app_db.client("admin").get(f"/api/frameworks/coverage?programme={programme()}&framework={fid}&format=csv").body.decode("utf-8-sig")
    row = next(x for x in csv.reader(io.StringIO(body)) if x[0] != "İş rolu")
    assert row[:2] == ["'=R1", '\'=HYPERLINK("http://evil.example")'] and row[4:6] == ["'@T1", "'+SUM(1)"] and row[6] == "Bəli"
    assert t.put(f"/api/syllabi/{course}/outcomes/N1/items", {"items": before}).status == 200


# ---------------------------------------------------------------- query plans
def test_the_read_queries_use_an_index_on_the_large_tables(app_db, sample, course):
    """After the full import (2 356 items, 5 950 links) no read of the picker, the map or the report walks a table that
    grows (tools/queryplan.py's check, with every growing table counted as large)."""
    sys.path.insert(0, str(ROOT / "tools"))
    import queryplan
    if not q("SELECT 1 FROM frameworks WHERE key='nice' AND version='2.2.0'"):
        assert manage.main(["import-framework", "--file", str(REAL)]) == 0
    real, sid = fw_id("nice", "2.2.0"), programme()
    user = {**app_db.client("admin").user, "role": "admin", "primary_role": "admin"}
    teacher = {**app_db.client("teacher").user, "role": "teacher", "primary_role": "teacher"}
    seen: list[str] = []
    c = store.connect()
    c.set_trace_callback(seen.append)
    try:
        frameworks.listing(c)
        frameworks.search(c, real, "risk", "knowledge", None, 2, 20)
        frameworks.search(c, real, None, None, "OG-WRL-015", 1, 20)
        frameworks.course_map(c, teacher, course)
        frameworks.programmes(c, user)
        frameworks.coverage(c, user, sid, real, "OG-WRL-015")
        frameworks.coverage_csv(c, user, sid, real, "az")
    finally:
        c.set_trace_callback(None)
    big = dict.fromkeys(("framework_items", "framework_links", "outcome_items", "study_groups", "teaching_unit_groups", "teaching_units",
                         "courses", "syllabus_versions"), 10 ** 6)
    bad = {sql: plan for sql in dict.fromkeys(seen) if (plan := queryplan.scans(c, sql, big, 1000))}
    c.close()
    assert len(seen) > 10 and bad == {}, json.dumps(bad, indent=1)


def test_the_coverage_report_costs_the_same_statements_whatever_the_programme_s_size(app_db, sample, course):
    """2026-11-24 measurement: the report read each course's published version on its own (310 statements for a
    programme of 300 courses); the published versions of the programme's courses are now one read per 500 courses."""
    sid, user = programme(), {**app_db.client("admin").user, "role": "admin", "primary_role": "admin"}
    gid = q("SELECT id FROM study_groups WHERE specialty_id=? ORDER BY id LIMIT 1", (sid,))[0]["id"]
    body = json.dumps({"outcomes": [{"id": "N1", "text": "Yük nəticəsi"}], "plan": [], "assessment": []})

    def statements():
        seen: list[str] = []
        c = store.connect()
        c.set_trace_callback(seen.append)
        try:
            assert frameworks.coverage(c, user, sid, sample, None) is not None
            assert frameworks.coverage_csv(c, user, sid, sample, "az") is not None
        finally:
            c.close()
        return len(seen)

    before = statements()
    added = []
    for k in range(12):
        cid = run("INSERT INTO courses(code,name,credits,color,active,created_at,updated_at) VALUES(?,?,5,'#777',1,'2026-01-01','2026-01-01')",
                  (f"FWN-{k}", f"Ölçü fənni {k}"))
        unit = run("INSERT INTO teaching_units(course_id,kind,active,created_at,updated_at) VALUES(?,'lecture',1,'2026-01-01','2026-01-01')", (cid,))
        run("INSERT INTO teaching_unit_groups(unit_id,group_id) VALUES(?,?)", (unit, gid))
        run("INSERT INTO syllabus_versions(course_id,version,status,data,created_at,tags) VALUES(?,1,'published',?,'2026-01-01','{}')", (cid, body))
        added.append((cid, unit))
    try:
        assert statements() == before
    finally:
        for cid, unit in added:
            run("DELETE FROM syllabus_versions WHERE course_id=?", (cid,))
            run("DELETE FROM teaching_unit_groups WHERE unit_id=?", (unit,))
            run("DELETE FROM teaching_units WHERE id=?", (unit,))
            run("DELETE FROM courses WHERE id=?", (cid,))
