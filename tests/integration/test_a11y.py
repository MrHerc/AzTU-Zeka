"""axe-core on the ten main pages (tasks/todo.md, Task 42): no WCAG 2.2 AA violation of impact "serious" or "critical",
on a desktop and on a phone (tests/e2e/a11y.js). The screens added since Checkpoint F (the login page with every role
card, the syllabus editor with the framework picker open, the reviewer's window, the print view, the framework coverage
report, the timetable hours report and the builder's pages) have no WCAG 2.2 AA violation at all, at 1280 and 390 px, in
the light and the dark theme; the user menu and the picker work by keyboard. axe-core is tests/e2e/node_modules/axe-core
(npm ci --prefix tests/e2e) or the axe.min.js named by AXE_CORE; skipped without it, or without node and Playwright."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import manage
from zeka.legacy import store

SCRIPT = Path(__file__).resolve().parents[1] / "e2e" / "a11y.js"
SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "nice_sample.json"
PAGES = ("sign-in", "student-home", "student-schedule", "tutor", "e-services", "teacher-home", "teacher-course",
         "office-requests", "leader-dashboard", "admin-settings")
SCREENS = ("login", "syllabus-picker", "syllabus-review", "syllabus-print", "framework-coverage", "hours-report",
           "timetable-builder", "timetable-version", "dept-timetable", "teacher-availability", "faculty-timetable")
VIEWS = ("1280/light", "1280/dark", "390/light", "390/dark")
# Rules not held against the screens since Checkpoint F, each with its reason. Empty: every rule of the tags applies.
EXCLUDED: dict[str, str] = {}


def _node_has(expr: str) -> bool:
    node = shutil.which("node")
    return bool(node) and subprocess.run([node, "-e", expr], capture_output=True, timeout=30, cwd=SCRIPT.parent).returncode == 0


def _axe() -> bool:
    return os.path.isfile(os.environ.get("AXE_CORE", "")) or _node_has("require.resolve('axe-core')")


pytestmark = [pytest.mark.skipif(not _node_has("require('playwright')"), reason="node with Playwright is not installed"),
              pytest.mark.skipif(not _axe(), reason="axe-core not found: npm ci --prefix tests/e2e, or AXE_CORE=<path of axe.min.js>")]


def _syllabus(teacher, code: str, submit: bool) -> tuple[int, int]:
    """A syllabus of the demo teacher's course with two outcomes, a week and a book, N1 tagged with Bloom and NICE (what
    the picker and the reviewer show); submitted to the department head when ``submit``. Returns (course, version)."""
    c = store.connect()
    try:
        cid = store.row(c, "SELECT id FROM courses WHERE code=?", (code,))["id"]
    finally:
        c.close()
    d = teacher.post(f"/api/syllabi/{cid}/draft", {}).json["data"]
    d["outcomes"] = [{"id": "N1", "text": "Kirxhof qanunlarını tətbiq edərək cərəyan və gərginlikləri hesablayır", "bloom": "apply"},
                     {"id": "N2", "text": "RC dövrəsinin keçid prosesini izah edir", "bloom": "understand"}]
    d["plan"] = [{"week": 1, "topic": "Om qanunu və sabit cərəyan dövrələri", "outcomes": ["N1"], "activity": "Mühazirə və məsələ həlli"}]
    d["literature"] = [{"title": "Elektrik dövrələrinin nəzəriyyəsi, dərslik", "kind": "main"}]
    for a in d["assessment"]:
        a["outcomes"] = []
    assert teacher.put(f"/api/syllabi/{cid}", {"data": d}).status == 200
    fws = teacher.get("/api/frameworks").json
    bloom = next(f for f in fws if f["key"] == "bloom")
    nice = next(f for f in fws if f["key"] == "nice")
    apply_ = next(i for i in teacher.get(f"/api/frameworks/{bloom['id']}/items?size=10").json["items"] if i["code"] == "apply")
    task = teacher.get(f"/api/frameworks/{nice['id']}/items?kind=task&size=1").json["items"][0]
    assert teacher.put(f"/api/syllabi/{cid}/outcomes/N1/items", {"items": [apply_["id"], task["id"]]}).status == 200
    vid = teacher.get(f"/api/syllabi/{cid}").json["latest"]["id"]
    if submit:
        assert teacher.post(f"/api/syllabi/{cid}/versions/{vid}/submit", {}).status == 200
    return cid, vid


def _draft(office) -> int:
    """A builder draft of the demo term over a synthetic department (the demo's own units have hand-written rows and stay
    out of the builder): a course's lecture, seminars and lab, placed once a week, so the hours report and the version
    page have lines; written straight into the tables a solve run fills, as the job runner is not part of this check."""
    c = store.connect()
    try:
        now = store.iso(store.now())
        dep = c.execute("INSERT INTO departments(faculty_id,code,name,active,created_at,updated_at) VALUES(1,'A11','Sınaq kafedrası',1,?,?)",
                        (now, now)).lastrowid
        groups = [c.execute("INSERT INTO study_groups(name,year,faculty_id,active) VALUES(?,2025,1,1)", (f"A11-{i}",)).lastrowid for i in (1, 2)]
        teacher = c.execute("INSERT INTO users(username,full_name,role,title,color,department_id,consent_at) VALUES('a11.t','Müəllim A11',"
                            "'teacher','','#333',?,?)", (dep, now)).lastrowid
        co = c.execute("INSERT INTO courses(code,name,teacher_id,credits,color,department_id,term_id,active,created_at,updated_at) "
                       "VALUES('A11-1','Sınaq fənni',?,5,'#777',?,1,1,?,?)", (teacher, dep, now, now)).lastrowid
        for kind, gs, hours in (("lecture", groups, 30), ("seminar", groups[:1], 15), ("seminar", groups[1:], 15), ("lab", groups[:1], 15)):
            u = c.execute("INSERT INTO teaching_units(course_id,kind,teacher_id,active,created_at,updated_at,hours,students) "
                          "VALUES(?,?,?,1,?,?,?,20)", (co, kind, teacher, now, now, hours)).lastrowid
            c.executemany("INSERT INTO teaching_unit_groups(unit_id,group_id) VALUES(?,?)", [(u, g) for g in gs])
        units = store.rows(c, "SELECT id FROM teaching_units WHERE course_id=? ORDER BY id", (co,))
        vid = c.execute("INSERT INTO tt_versions(term_id,status,name,rev,checked_rev,violations,scope,created_by,created_at) "
                        "VALUES(1,'draft','Sınaq',0,NULL,NULL,'{\"all\":true}',?,?)", (office.user["id"], now)).lastrowid
        c.executemany("INSERT INTO tt_placements(version_id,meeting_key,unit_id,part,weekday,period,duration,weeks,origin) "
                      "VALUES(?,?,?,0,?,?,1,'all','solver')",
                      [(vid, f"{u['id']}:0", u["id"], 1 + k % 5, 1 + k // 5) for k, u in enumerate(units)])
        c.commit()
    finally:
        c.close()
    assert units
    r = office.get(f"/api/timetable/versions/{vid}/hours")
    assert r.status == 200 and r.json["items"], r.text
    return vid


@pytest.fixture(scope="module")
def seen(app_db):
    course = app_db.client("teacher").get("/api/courses").json[0]["id"]
    teacher = app_db.client("teacher")                     # the demo teacher heads the faculty's departments for dept-timetable
    faculty = app_db.client("admin").get("/api/directory/faculties").json["items"][0]["id"]
    assert app_db.client("admin").post(f"/api/admin/users/{teacher.user['id']}/roles",
                                       {"role": "dept_head", "scope_type": "faculty", "scope_id": faculty}).status == 200
    assert manage.main(["import-framework", "--file", str(SAMPLE)]) == 0
    syl, version = _syllabus(teacher, "ELM-2105", submit=True)        # the reviewer's version
    editor, _ = _syllabus(teacher, "ELM-2105", submit=False)          # the teacher's next draft, open in the editor
    office = app_db.client("office")
    assert office.post("/api/me/role", {"role": "academic_office"}).status == 200
    more = {"editor": editor, "course": syl, "version": version, "draft": _draft(office)}
    run = subprocess.run([shutil.which("node"), str(SCRIPT), app_db.url, str(course), json.dumps(more)],
                         capture_output=True, text=True, timeout=1200)
    assert run.stdout.strip(), run.stderr
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert "fatal" not in out, out["fatal"]
    assert {k.split("/")[0] for k in out} == set(PAGES) | set(SCREENS) | {"keys"}
    return out


def _lines(got: dict, bad: list) -> str:
    return f"{got['url']}:\n" + "\n".join(f"{v['impact']} {v['id']} ({v['help']}), {v['count']}×: {v['targets']}" for v in bad)


@pytest.mark.parametrize("page", PAGES)
def test_no_serious_or_critical_violation(seen, page):
    for view in ("desktop", "mobile"):
        got = seen[f"{page}/{view}"]
        assert "error" not in got, got["error"]
        bad = [v for v in got["violations"] if v["impact"] in ("serious", "critical")]
        assert not bad, f"({view}) " + _lines(got, bad)


@pytest.mark.parametrize("screen", SCREENS)
def test_a_screen_since_checkpoint_f_has_no_violation_in_either_theme_or_width(seen, screen):
    said = []
    for view in VIEWS:
        got = seen[f"{screen}/{view}"]
        assert "error" not in got, got["error"]
        bad = [v for v in got["violations"] if v["id"] not in EXCLUDED]
        if bad:
            said.append(f"({view}) " + _lines(got, bad))
    assert not said, "\n".join(said)


@pytest.mark.parametrize("view", ("1280/light", "1280/dark"))
def test_the_user_menu_works_by_keyboard(seen, view):
    # Enter opens it with the focus on its first item, Tab moves within it and shows where, Escape closes it and gives the
    # focus back to the profile button (it was lost to the page's body)
    got = seen[f"keys/{view}"]
    assert "error" not in got, got["error"]
    m = got["menu"]
    assert m["first"]["inside"] and m["first"]["ring"] and m["next"]["inside"] and m["next"]["ring"], m
    assert m["closed"] and m["back"] == "BUTTON#user-btn", m


@pytest.mark.parametrize("view", ("1280/light", "1280/dark"))
def test_the_framework_picker_works_by_keyboard(seen, view):
    # Enter on «Bəndlər» opens it, the focus stays inside and shows on each step, Escape closes it and returns to the button
    got = seen[f"keys/{view}"]
    assert "error" not in got, got["error"]
    p = got["picker"]
    assert all(s["inside"] and s["ring"] for s in p["steps"]), p
    assert p["closed"] and p["back"] == "N1", p
