"""OneRoster round trip (tasks/todo.md, Task 37): the demo registry exported on the screen as OneRoster CSV, imported
with the Task 16 importer (``manage.py import``) into an empty database in the order orgs, terms, users, courses,
classes, enrollments, and exported again (``manage.py export``) gives the same registry: users, orgs, terms, courses,
teaching units with their groups and subgroups, enrolments with ``beginDate``/``endDate``, and the units' teachers.

The empty database is a separate ``ZEKA_DATA`` in prod mode (migrations and the product catalogue, no people), worked on
by subprocesses only. Study groups (and specialties) are not OneRoster kinds here: the test creates the demo's group
names in the empty copy first. The copy's import links keep the first export's sourcedIds, so equal registries are
byte-identical files.

The demo is first given what it lacks: a department and a second term, e-mails, a disabled teacher, two subgroup labs
of one group, a seminar of another group with a student of the first group in it, a unit with no group, and enrolment
dates."""
import csv
import io
import json
import os
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

from zeka.legacy import store
from zeka.modules.integration import export

ROOT = Path(__file__).resolve().parents[2]


def run(sql, args=()):
    c = store.connect()
    try:
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def table(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def unzip(data: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n).decode("utf-8") for n in z.namelist()}


def enrich():
    t = "2026-11-19T10:00:00"
    dep = run("INSERT INTO departments(faculty_id,code,name,created_at,updated_at) VALUES(1,'KM-KAF','Kompüter mühəndisliyi kafedrası',?,?)", (t, t))
    run("UPDATE courses SET department_id=? WHERE id IN (1,2)", (dep,))
    run("UPDATE users SET department_id=? WHERE username='rauf'", (dep,))
    term = run("INSERT INTO academic_terms(code,name,teaching_start,teaching_end,exam_start,exam_end,created_at,updated_at) "
               "VALUES('2027-Y','2026/2027 tədris ili · yaz semestri','2027-02-15','2027-05-31','2027-06-05','2027-06-30',?,?)", (t, t))
    run("UPDATE courses SET term_id=? WHERE id=6", (term,))
    run("UPDATE users SET email=username || '@example.org' WHERE role='student' AND group_id=2")
    run("UPDATE users SET status='disabled' WHERE username='gunel'")
    leyla = q("SELECT id FROM users WHERE username='leyla'")[0]["id"]
    for sub, teacher in ((1, leyla), (2, None)):
        unit = run("INSERT INTO teaching_units(course_id,kind,teacher_id,subgroup,created_at,updated_at) VALUES(1,'lab',?,?,?,?)", (teacher, sub, t, t))
        run("INSERT INTO teaching_unit_groups(unit_id,group_id) VALUES(?,1)", (unit,))
    run("INSERT INTO teaching_units(course_id,kind,created_at,updated_at) VALUES(3,'lab',?,?)", (t, t))          # no group: everyone
    run("UPDATE enrollments SET subgroup=1 + (user_id % 2) WHERE course_id=1 AND user_id IN (SELECT id FROM users WHERE group_id=1)")
    seminar = run("INSERT INTO teaching_units(course_id,kind,created_at,updated_at) VALUES(1,'seminar',?,?)", (t, t))
    run("INSERT INTO teaching_unit_groups(unit_id,group_id) VALUES(?,2)", (seminar,))
    run("UPDATE enrollments SET group_id=2, subgroup=NULL WHERE course_id=1 AND user_id=(SELECT MIN(id) FROM users WHERE role='student' "
        "AND group_id=1)")                                  # a student of group 1 who takes this course with group 2
    run("UPDATE enrollments SET begin_date='2026-09-15', end_date='2026-12-01' WHERE course_id=2 AND user_id IN "
        "(SELECT id FROM users WHERE group_id=3 ORDER BY id LIMIT 3)")
    run("UPDATE enrollments SET begin_date='2026-10-01' WHERE course_id=4 AND user_id IN (SELECT id FROM users WHERE group_id=2 ORDER BY id LIMIT 2)")


def cli(env, *args) -> str:
    r = subprocess.run([sys.executable, str(ROOT / "backend" / "manage.py"), *args], capture_output=True, text=True, encoding="utf-8",
                       env=env, timeout=180)
    assert r.returncode == 0, f"{args}: {r.stdout}\n{r.stderr}"
    return r.stdout + r.stderr


def test_the_export_imported_into_an_empty_copy_gives_the_same_registry(app_db, tmp_path):
    enrich()
    r = app_db.client("admin").get("/api/integration/export/oneroster")
    assert r.status == 200 and r.headers["Content-Type"] == "application/zip"
    first = unzip(r.body)
    assert sorted(first) == sorted(f"{k}.csv" for k in export.FILES)
    files = {k: table(first[f"{k}.csv"]) for k in export.FILES}

    # the first export carries what the round trip must keep
    fac = next(x for x in files["orgs"] if x["type"] == "faculty")
    assert any(x["identifier"] == "KM-KAF" and x["parentSourcedId"] == fac["sourcedId"] for x in files["orgs"])
    assert {x["identifier"] for x in files["terms"]} == {"2026-P", "2027-Y"}
    users = {x["username"]: x for x in files["users"]}
    assert users["rauf"]["department"] == "KM-KAF" and users["gunel"]["enabledUser"] == "false"
    assert users["aysel"]["middleName"] and users["aysel"]["identifier"] and users["aysel"]["group"] == "İT-25-1"
    in_group = {g: q("SELECT COUNT(*) n FROM users WHERE role='student' AND group_id=?", (g,))[0]["n"] for g in (1, 2)}
    assert sum(1 for x in files["users"] if x["email"].endswith("@example.org")) == in_group[2] > 0
    labs = [x for x in files["classes"] if x["groups"] == "İT-25-1"]
    assert sorted(x["subgroup"] for x in labs) == ["1", "2"] and any(x["groups"] == "" for x in files["classes"])
    enrolments = files["enrollments"]
    dated = q("SELECT COUNT(*) n FROM enrollments WHERE begin_date IS NOT NULL OR end_date IS NOT NULL")[0]["n"]
    assert dated == 5 and sum(1 for x in enrolments if (x["beginDate"], x["endDate"]) == ("2026-09-15", "2026-12-01")) >= 3
    assert any(x["beginDate"] == "2026-10-01" and not x["endDate"] for x in enrolments)
    lab_ids = {x["sourcedId"] for x in labs}
    assert sum(1 for x in enrolments if x["classSourcedId"] in lab_ids and x["role"] == "student") == in_group[1] - 1 > 0, \
        "each of group 1 in one subgroup lab, but the one taking the course with group 2"
    assert sum(1 for x in enrolments if x["classSourcedId"] in lab_ids and x["role"] == "teacher") == 1

    # an empty database: prod mode, a data directory of its own, the demo's group names
    copy = tmp_path / "copy"
    env = {k: v for k, v in os.environ.items() if not k.startswith("ZEKA_")} | {"ZEKA_DATA": str(copy), "ZEKA_MODE": "prod"}
    groups = sorted({x["group"] for x in files["users"] if x["group"]} | {g for x in files["classes"] for g in x["groups"].split(";") if g})
    make = (f"import sys, json; sys.path.insert(0, {str(ROOT / 'backend')!r}); from zeka.legacy import store; store.init(); "
            "c = store.connect(); assert not store.rows(c, 'SELECT 1 FROM users'); "
            "c.executemany('INSERT INTO study_groups(name, year) VALUES(?, 2)', [(g,) for g in json.loads(sys.argv[1])]); c.commit()")
    made = subprocess.run([sys.executable, "-c", make, json.dumps(groups)], capture_output=True, text=True, env=env, timeout=180)
    assert made.returncode == 0, made.stderr
    for kind in export.FILES:
        path = tmp_path / f"{kind}.csv"
        path.write_text(first[f"{kind}.csv"], encoding="utf-8", newline="")
        out = cli(env, "import", "--kind", kind, "--source", "zeka-demo", "--file", str(path))
        assert "refused 0" in out and "conflicts 0" in out, out
    cli(env, "export", "--kind", "oneroster", "--out", str(tmp_path / "second.zip"))
    second = unzip((tmp_path / "second.zip").read_bytes())

    for name in first:
        assert second[name] == first[name], name
    db = sqlite3.connect(copy / "campus.db")
    try:
        copied = db.execute("SELECT COUNT(*) FROM enrollments WHERE begin_date IS NOT NULL OR end_date IS NOT NULL").fetchone()[0]
    finally:
        db.close()
    assert copied == dated, "the enrolment dates are in the copy itself"
