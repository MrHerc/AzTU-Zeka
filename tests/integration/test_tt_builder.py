"""The semester timetable builder through HTTP and the job runner (tasks/todo.md, Task 48, slice 2).

A synthetic department of the demo's current term (6 groups, 20 units of 4 courses, 5 teachers plus the demo teacher,
3 students a group; ids only, no real name) goes through the cycle: settings and readiness, the term's deadlines, unit
needs, group shifts, availability (one grid above the cap, decided by the academic office), a solve run in the job
runner, the draft's grid, options and moves (a clash and a stale edit lose), a check run, the publish gate, and a
publication to timetable rows, lessons from the effective date and one notification per person; then a second
publication that is interrupted after every batch and still writes everything exactly once."""
import copy
import csv
import inspect
import io
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from zeka.core import i18n, jobs, tenant
from zeka.legacy import periodic, store             # periodic registers timetable.work
from zeka.modules.timetable import builder, domain
from zeka.modules.timetable import service as rows_service

TERM = 1
ROOT = Path(__file__).resolve().parents[2]
EFF, EFF2 = "2026-11-23", "2026-11-30"


def _dotted(day: str) -> str:
    """A date as a notice writes it in Azerbaijani: dd.mm.yyyy."""
    return ".".join(reversed(day.split("-")))


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def _write(sql, args=()):
    c = store.connect()
    try:
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def run_jobs(limit=40):
    """Cycles of the job runner, 31 s apart (timetable.work runs every 30 s), until no run of the builder is active."""
    c = store.connect()
    try:
        t = datetime(2027, 1, 1, tzinfo=timezone.utc) + timedelta(days=q("SELECT COUNT(*) n FROM job_runs")[0]["n"])
        for i in range(limit):
            if not q("SELECT 1 FROM tt_runs WHERE status IN ('queued','running')"):
                return i
            jobs.run_due(c, "tt-test", now=t + timedelta(seconds=31 * i), names=["timetable.work"])
        raise AssertionError(q("SELECT id, kind, status, error, progress FROM tt_runs WHERE status IN ('queued','running')"))
    finally:
        c.close()


@pytest.fixture(scope="module")
def world(app_db):
    """The synthetic department, written straight into the tables the Forma №3 import fills (Task 47 owns the reader)."""
    c = store.connect()
    try:
        now = store.iso(store.now())
        dep = c.execute("INSERT INTO departments(faculty_id,code,name,active,created_at,updated_at) VALUES(1,'TTB','Sınaq kafedrası',1,?,?)",
                        (now, now)).lastrowid
        groups = [c.execute("INSERT INTO study_groups(name,year,faculty_id,active) VALUES(?,2025,1,1)", (f"TB-{i}",)).lastrowid for i in range(1, 7)]
        teachers = [c.execute("INSERT INTO users(username,full_name,role,title,color,department_id,consent_at) VALUES(?,?,'teacher','','#333',?,?)",
                              (f"tb.t{i}", f"Müəllim TB-{i}", dep, now)).lastrowid for i in range(1, 6)]
        demo_teacher = store.row(c, "SELECT id FROM users WHERE username='rauf'")["id"]
        c.execute("UPDATE users SET department_id=? WHERE id=?", (dep, demo_teacher))
        students = {g: [c.execute("INSERT INTO users(username,full_name,role,title,group_id,color,synthetic,consent_at) "
                                  "VALUES(?,?,'student','',?,'#555',1,?)", (f"tb.s{g}.{k}", f"Tələbə {g}-{k}", g, now)).lastrowid
                        for k in range(3)] for g in groups}
        units = []

        def unit(course, kind, teacher, gs, hours, size, subgroup=None):
            uid = c.execute("INSERT INTO teaching_units(course_id,kind,teacher_id,subgroup,active,created_at,updated_at,hours,students) "
                            "VALUES(?,?,?,?,1,?,?,?,?)", (course, kind, teacher, subgroup, now, now, hours, size)).lastrowid
            c.executemany("INSERT INTO teaching_unit_groups(unit_id,group_id) VALUES(?,?)", [(uid, g) for g in gs])
            units.append(uid)
            return uid

        courses = []
        for k in range(4):
            co = c.execute("INSERT INTO courses(code,name,teacher_id,credits,color,department_id,term_id,active,created_at,updated_at) "
                           "VALUES(?,?,?,5,'#777',?,?,1,?,?)", (f"TB-{k}", f"Sınaq fənni {k}", teachers[k], dep, TERM, now, now)).lastrowid
            courses.append(co)
            stream = groups[:3] if k % 2 == 0 else groups[3:]
            unit(co, "lecture", teachers[k], stream, 30, 60)
            for i, g in enumerate(stream):
                unit(co, "seminar", demo_teacher if i % 2 == 0 else teachers[4], [g], 15, 20)
            unit(co, "lab", teachers[4], [stream[0]], 15, 18)
        lonely = unit(courses[0], "seminar", teachers[1], [], 15, 20)                     # no groups: excluded, and said so
        vacancy = unit(courses[1], "seminar", None, [groups[4]], 15, 20)                   # a vacancy: placed without a teacher
        c.commit()
    finally:
        c.close()
    return {"dep": dep, "groups": groups, "teachers": teachers, "rauf": demo_teacher, "students": students, "units": units,
            "lonely": lonely, "vacancy": vacancy, "courses": courses}


@pytest.fixture(scope="module")
def office_ao(app_db):
    """The demo's dean's office acting as the academic office (its seeded grant without a scope)."""
    c = app_db.client("office")
    assert c.post("/api/me/role", {"role": "academic_office"}).status == 200
    return c


@pytest.fixture(scope="module")
def head(app_db, world):
    """The demo teacher, also head of the synthetic department (a grant scoped to it)."""
    admin = app_db.client("admin")
    assert admin.post(f"/api/admin/users/{world['rauf']}/roles", {"role": "dept_head", "scope_type": "department",
                                                                  "scope_id": world["dep"]}).status == 200
    h = app_db.client("teacher")
    assert h.post("/api/me/role", {"role": "dept_head"}).status == 200
    return h


B = f"/api/timetable/build/{TERM}"


def test_readiness_blocks_a_run_until_the_shifts_fit_the_bell_times(office_ao, world):
    r = office_ao.get(f"{B}/readiness")
    assert r.status == 200 and r.json["run_blocked"], r.text
    line = next(x for x in r.json["lines"] if x["code"] == "lesson_times")
    assert line["samples"] == [7, 8] and line["title"]                     # the evening shift names pairs the demo has not
    refused = office_ao.post(f"{B}/runs", {"kind": "solve"})
    assert refused.status == 409 and refused.json["lines"][0]["code"] == "lesson_times"
    value = office_ao.get("/api/timetable/settings").json["timetable"]
    assert office_ao.put("/api/timetable/settings", {"value": {**value, "weights": [1]}}).status == 400
    value["shifts"] = {"morning": [1, 2, 3, 4], "afternoon": [4, 5, 6]}
    assert office_ao.put("/api/timetable/settings", {"value": value}).status == 200
    after = office_ao.get(f"{B}/readiness").json
    assert not after["run_blocked"] and after["publish_blocked"]           # nothing confirmed yet: publishing stays shut
    units = next(x for x in after["lines"] if x["code"] == "unit_groups")
    assert world["lonely"] in units["samples"]
    assert world["vacancy"] in next(x for x in after["lines"] if x["code"] == "vacancies")["samples"]


def test_the_plan_opens_the_deadlines_and_a_head_sets_a_units_needs(office_ao, head, world, app_db):
    plan = office_ao.put(f"{B}/plan", {"needs_due": "2026-12-01", "availability_due": "2026-12-01", "confirmed": ["practice"]})
    assert plan.status == 200 and plan.json["dues"]["availability"] == "2026-12-01"
    assert office_ao.put(f"{B}/plan", {"needs_due": "01.12.2026"}).status == 400
    assert office_ao.put(f"{B}/plan", {"confirmed": ["everything"]}).status == 400
    lab = world["units"][4]
    bad = head.put(f"/api/timetable/units/{lab}/needs", {"pattern": ["1-4"]})
    assert bad.status == 400 and "8" in bad.json["error"] and "15" in bad.json["error"]
    assert head.put(f"/api/timetable/units/{lab}/needs", {"need": 18}).status == 400        # a reason is required
    ok = head.put(f"/api/timetable/units/{lab}/needs", {"need": 18, "need_reason": "Laboratoriyada 18 yer var", "room_kinds": ["lab"]})
    assert ok.status == 200 and ok.json["needs"]["room_kinds"] == ["lab"]
    demo_unit = q("SELECT u.id FROM teaching_units u JOIN courses co ON co.id=u.course_id WHERE co.department_id IS NOT ? LIMIT 1",
                  (world["dep"],))[0]["id"]
    assert head.put(f"/api/timetable/units/{demo_unit}/needs", {"duration": 1}).status == 404     # outside the head's scope
    listed = head.get(f"{B}/units?department_id={world['dep']}")
    assert listed.status == 200 and listed.json["total"] == 22
    assert app_db.client("teacher").put(f"/api/timetable/units/{lab}/needs", {}).status == 403


def test_the_deans_office_sets_shifts_and_a_head_may_not(app_db, head, world):
    office = app_db.client("office")
    items = [{"group_id": g, "shift": "morning" if i < 3 else "afternoon", "home_building_id": None} for i, g in enumerate(world["groups"])]
    assert office.put(f"{B}/groups", {"items": items}).status == 200
    assert office.put(f"{B}/groups", {"items": [{"group_id": world["groups"][0], "shift": "night"}]}).status == 400
    assert head.put(f"{B}/groups", {"items": items[:1]}).status == 403
    seen = {g["id"]: g["shift"] for g in head.get(f"{B}/groups").json}
    assert seen[world["groups"][0]] == "morning" and seen[world["groups"][5]] == "afternoon"


def test_a_grid_above_the_cap_waits_for_a_decision(app_db, office_ao, head, world):
    teacher = app_db.client("teacher")
    me = world["rauf"]
    path = f"{B}/teachers/{me}/availability"
    assert teacher.get(f"{B}/teachers/{world['teachers'][0]}/availability").status == 404    # another teacher's grid
    one = teacher.put(path, {"cells": [{"weekday": 6, "period": 6, "level": "unavailable"}]})
    assert one.status == 200 and one.json["status"] == "saved"
    many = [{"weekday": 6, "period": p, "level": "unavailable"} for p in range(1, 7)] + \
           [{"weekday": 5, "period": p, "level": "unavailable"} for p in range(1, 7)]      # 12 of 36 cells: above 30 %
    pending = teacher.put(path, {"cells": many})
    assert pending.status == 200 and pending.json["status"] == "pending" and pending.json["feedback"]["over_cap"] == 2
    assert len(teacher.get(path).json["cells"]) == 1                     # the solver never reads a pending grid
    board = {x["id"]: x for x in office_ao.get(f"{B}/teachers?department_id={world['dep']}").json["items"]}
    assert board[me]["pending"] and board[me]["cells"] == 1 and board[me]["full_name"] and set(world["teachers"]) <= set(board)
    assert teacher.get(f"{B}/teachers").status == 403                                         # the board is for the builders
    assert teacher.post(f"{path}/decide", {"approve": True}).status == 403                   # route: teachers do not decide
    mine = head.post(f"{path}/decide", {"approve": True})                                    # TE-F2: a head never approves their own
    assert mine.status == 403 and "Öz məşğulluq" in mine.json["error"], mine.text
    assert q("SELECT pending FROM tt_availability_status WHERE teacher_id=?", (me,))[0]["pending"]
    assert office_ao.post(f"{path}/decide", {"approve": "yes"}).status == 400
    ok = office_ao.post(f"{path}/decide", {"approve": True})
    assert ok.status == 200 and ok.json["over_cap_cells"] == 2
    assert len(teacher.get(path).json["cells"]) == 12
    after = {x["id"]: x for x in office_ao.get(f"{B}/teachers").json["items"]}[me]
    assert not after["pending"] and after["cells"] == 12 and after["over_cap_cells"] == 2
    assert teacher.post(f"{path}/confirm", {}).status == 200
    assert q("SELECT 1 FROM notifications WHERE user_id=? AND link='/teacher/availability'", (me,))


def test_after_the_deadline_a_teacher_writes_only_once_reopened(app_db, office_ao, world):
    teacher, me = app_db.client("teacher"), world["rauf"]
    path = f"{B}/teachers/{me}/availability"
    assert office_ao.put(f"{B}/plan", {"needs_due": "2026-12-01", "availability_due": "2026-11-01", "confirmed": ["practice"]}).status == 200
    assert teacher.post(f"{path}/confirm", {}).status == 409
    assert office_ao.post(f"{path}/reopen", {"until": "2026-10-01"}).status == 400                      # before today
    assert office_ao.post(f"{path}/reopen", {"until": "2026-11-30"}).status == 200
    assert teacher.post(f"{path}/confirm", {}).status == 200
    assert q("SELECT reopened_until FROM tt_availability_status WHERE teacher_id=?", (me,))[0]["reopened_until"] == "2026-11-30"


def test_a_head_of_another_department_sees_nothing_of_this_one(app_db, world):
    admin = app_db.client("admin")
    other = admin.post("/api/directory/departments", {"faculty_id": 1, "code": "TTX", "name": "Başqa sınaq kafedrası"}).json["id"]
    leader_id = app_db.client("leader").user["id"]
    assert admin.post(f"/api/admin/users/{leader_id}/roles", {"role": "dept_head", "scope_type": "department", "scope_id": other}).status == 200
    stranger = app_db.client("leader")
    assert stranger.post("/api/me/role", {"role": "dept_head"}).status == 200
    assert stranger.put(f"/api/timetable/units/{world['units'][0]}/needs", {"duration": 1}).status == 404
    assert stranger.get(f"{B}/teachers/{world['teachers'][0]}/availability").status == 404
    assert stranger.get(f"{B}/readiness?department_id={world['dep']}").status == 404
    assert stranger.get(f"{B}/units").json["total"] == 0
    assert stranger.get(f"{B}/teachers").json["items"] == []
    assert stranger.get(f"{B}/teachers?department_id={world['dep']}").status == 404
    assert not stranger.get(B).json["can_publish"] and not stranger.get(B).json["manages"]
    assert stranger.post(f"{B}/teachers/{world['rauf']}/availability/decide", {"approve": False}).status == 404


def test_a_deans_office_grant_counts_only_at_faculty_scope(app_db, world):
    """TE-F3: a department- or course-scoped grant to the dean's office widens nothing."""
    c = store.connect()
    now = store.iso(store.now())
    f3 = c.execute("INSERT INTO faculties(code,name,active,created_at,updated_at) VALUES('F3X','Üçüncü fakültə',1,?,?)", (now, now)).lastrowid
    d3 = c.execute("INSERT INTO departments(faculty_id,code,name,active,created_at,updated_at) VALUES(?,'D3X','Üçüncü kafedra',1,?,?)",
                   (f3, now, now)).lastrowid
    c.commit()
    c.close()
    office = app_db.client("office")
    admin = app_db.client("admin")
    for scope_type, scope_id in (("department", d3), ("course", world["courses"][0])):
        assert admin.post(f"/api/admin/users/{office.user['id']}/roles", {"role": "office", "scope_type": scope_type, "scope_id": scope_id}).status == 200
    office = app_db.client("office")
    assert office.get(f"{B}/readiness?department_id={d3}").status == 404
    assert office.get(f"{B}/units?department_id={d3}").status == 404
    c = store.connect()
    try:
        s = builder.scope_of(c, {"id": office.user["id"], "role": "office"})
        assert not s["all"] and not s["departments"] and not s["courses"]
    finally:
        c.close()


def test_a_head_without_a_grant_covers_their_own_department(world):
    """TE-F7: a person whose primary role is dept_head, with a department and no grant, builds for that department only."""
    c = store.connect()
    try:
        uid = c.execute("INSERT INTO users(username,full_name,role,title,color,department_id,consent_at) VALUES('tb.head','Müdir TB','dept_head','',"
                        "'#333',?,?)", (world["dep"], store.iso(store.now()))).lastrowid
        other = c.execute("INSERT INTO departments(faculty_id,code,name,active,created_at,updated_at) VALUES(1,'TTH','Başqa kafedra',1,?,?)",
                          (store.iso(store.now()), store.iso(store.now()))).lastrowid
        c.commit()
        me = {"id": uid, "role": "dept_head"}
        assert builder.scope_of(c, me)["departments"] == {world["dep"]}
        assert builder.units(c, me, TERM, world["dep"], 0)["total"] == len(world["units"])
        assert builder.unit_for(c, me, world["units"][0])["id"] == world["units"][0]
        with pytest.raises(builder.HTTPError) as e:
            builder.units(c, me, TERM, other, 0)
        assert e.value.status == 404
    finally:
        c.close()


def test_a_run_can_be_cancelled_and_an_open_exam_shortens_the_chunks(office_ao, monkeypatch):
    started = office_ao.post(f"{B}/runs", {"kind": "precheck"})
    assert started.status == 200
    assert office_ao.post(f"/api/timetable/runs/{started.json['id']}/cancel", {}).status == 200
    run_jobs()
    assert office_ao.get(f"/api/timetable/runs/{started.json['id']}").json["status"] == "cancelled"
    assert office_ao.post(f"/api/timetable/runs/{started.json['id']}/cancel", {}).status == 409
    sol = {"atomic_exam_max_s": 10}
    assert builder._waits(True, {"progress": '{"meetings": 20000}'}, sol)          # 20 s estimated: it waits for the exam
    assert not builder._waits(True, {"progress": '{"meetings": 900}'}, sol)
    assert not builder._waits(False, {"progress": '{"meetings": 20000}'}, sol)


def test_a_solve_run_works_in_the_job_runner_and_leaves_a_draft(office_ao, head, world):
    lessons_before = q("SELECT COUNT(*) n FROM lessons")[0]["n"]
    started = office_ao.post(f"{B}/runs", {"kind": "solve", "budget": 3000, "seed": 7, "name": "Sınaq"})
    assert started.status == 200, started.text
    assert office_ao.post(f"{B}/runs", {"kind": "precheck"}).status == 409                  # one active run per term
    assert head.post(f"{B}/runs", {"kind": "solve"}).status == 403
    assert run_jobs() >= 2                                                                # a snapshot cycle, then the solve
    run = office_ao.get(f"/api/timetable/runs/{started.json['id']}").json
    assert run["status"] == "done" and run["version_id"], run
    p = run["progress"]
    assert p["placed"] + p["unplaced"] == p["meetings"] and p["hard"] == 0
    assert world["lonely"] in [x["unit_id"] for x in run["report"]["excluded"]]
    assert run["report"]["kept_manual"]                                    # demo units with hand-written rows stay as they are
    v = q("SELECT * FROM tt_versions WHERE id=?", (run["version_id"],))[0]
    assert v["status"] == "draft" and v["violations"] == 0 and v["checked_rev"] == v["rev"] == 0
    assert q("SELECT COUNT(*) n FROM lessons")[0]["n"] == lessons_before    # a draft makes no lesson
    unavailable = {(5, p_) for p_ in range(1, 7)} | {(6, p_) for p_ in range(1, 7)}
    mine = office_ao.get(f"/api/timetable/versions/{v['id']}/grid?teacher_id={world['rauf']}").json["items"]
    assert mine and not {(x["weekday"], x["period"]) for x in mine} & unavailable
    world["vid"] = v["id"]


def test_drafts_are_seen_only_by_the_builders(office_ao, head, app_db, world):
    vid = world["vid"]
    assert office_ao.get(f"/api/timetable/versions/{vid}/grid").status == 400                  # one filter is required
    grid = office_ao.get(f"/api/timetable/versions/{vid}/grid?group_id={world['groups'][0]}")
    assert grid.status == 200 and grid.json["items"] and all(x["start"] for x in grid.json["items"])
    assert head.get(f"/api/timetable/versions/{vid}/grid?group_id={world['groups'][0]}").status == 404
    assert vid not in [v["id"] for v in head.get(f"{B}/versions").json]
    assert app_db.client("student").get(f"/api/timetable/versions/{vid}/scorecard").status == 403
    assert office_ao.get(f"/api/timetable/versions/{vid}/scorecard").json["score"]["hard"] == 0
    assert isinstance(office_ao.get(f"/api/timetable/versions/{vid}/unplaced").json, list)


def _seminar(world, vid):
    return q("SELECT p.* FROM tt_placements p JOIN teaching_units u ON u.id=p.unit_id WHERE p.version_id=? AND u.kind='seminar' "
             "AND u.teacher_id=? ORDER BY p.id LIMIT 1", (vid, world["teachers"][4]))[0]


def test_options_and_moves_check_every_rule_live(office_ao, world):
    vid = world["vid"]
    p = _seminar(world, vid)
    opts = office_ao.get(f"/api/timetable/versions/{vid}/placements/{p['id']}/options")
    assert opts.status == 200, opts.text
    rev = opts.json["rev"]
    free = [o for o in opts.json["options"] if not o["reasons"] and not o["current"]]
    blocked = [o for o in opts.json["options"] if o["reasons"]]
    assert free and blocked and all(r["title"] for o in blocked for r in o["reasons"])
    lecture = q("SELECT p.* FROM tt_placements p JOIN teaching_unit_groups g ON g.unit_id=p.unit_id JOIN teaching_units u ON u.id=p.unit_id "
                "WHERE p.version_id=? AND u.kind='lecture' AND g.group_id=(SELECT group_id FROM teaching_unit_groups WHERE unit_id=?)",
                (vid, p["unit_id"]))[0]
    path = f"/api/timetable/versions/{vid}/placements/{p['id']}/move"
    clash = office_ao.post(path, {"weekday": lecture["weekday"], "period": lecture["period"], "room_id": p["room_id"], "rev": rev})
    assert clash.status == 409 and "group_clash" in {x["code"] for x in clash.json["reasons"]}, clash.text
    assert office_ao.post(path, {"weekday": "x", "period": 1, "rev": rev}).status == 400
    to = free[0]
    assert office_ao.post(path, {"weekday": to["weekday"], "period": to["period"], "room_id": to["room_id"], "rev": rev + 5}).status == 409
    moved = office_ao.post(path, {"weekday": to["weekday"], "period": to["period"], "room_id": to["room_id"], "rev": rev})
    assert moved.status == 200 and moved.json["rev"] == rev + 1 and moved.json["placement"]["origin"] == "manual"
    again = office_ao.post(path, {"weekday": p["weekday"], "period": p["period"], "room_id": p["room_id"], "rev": rev})
    assert again.status == 409                                             # a stale edit always loses
    locked = office_ao.post(f"/api/timetable/versions/{vid}/lock", {"ids": [p["id"]], "locked": True, "rev": rev + 1})
    assert locked.status == 200 and locked.json["changed"] == 1
    world["rev"] = rev + 2


def test_publishing_needs_a_check_the_confirmations_and_the_right_numbers(office_ao, app_db, world):
    vid = world["vid"]
    v = q("SELECT * FROM tt_versions WHERE id=?", (vid,))[0]
    body = {"effective_from": EFF, "accept_unplaced": v["unplaced"], "override_reason": "Rəy mərhələsi səhifələrlə gələcək"}
    assert app_db.client("admin").post(f"/api/timetable/versions/{vid}/publish", body).status == 403   # admin never publishes
    assert office_ao.get(B).json["can_publish"] and not app_db.client("admin").get(B).json["can_publish"]     # the page's button
    gate = office_ao.post(f"/api/timetable/versions/{vid}/publish", {**body, "accept_unplaced": v["unplaced"] + 1, "override_reason": ""})
    assert gate.status == 409
    assert {"unchecked", "unconfirmed", "readiness", "unplaced_count", "review"} <= {x["code"] for x in gate.json["gate"]}
    early = office_ao.post(f"/api/timetable/versions/{vid}/publish", {**body, "effective_from": "2026-11-20"})
    assert "effective_from" in {x["code"] for x in early.json["gate"]}
    check = office_ao.post(f"{B}/runs", {"kind": "check", "version_id": vid})
    assert check.status == 200
    p = _seminar(world, vid)
    busy = office_ao.post(f"/api/timetable/versions/{vid}/placements/{p['id']}/move",
                          {"weekday": p["weekday"], "period": p["period"], "room_id": p["room_id"], "rev": world["rev"]})
    assert busy.status == 409                                              # no move while the version is being checked
    run_jobs()
    v = q("SELECT * FROM tt_versions WHERE id=?", (vid,))[0]
    assert v["checked_rev"] == v["rev"] == world["rev"] and v["violations"] == 0
    value = office_ao.get("/api/timetable/settings").json["timetable"]
    value["confirmed"] = ["term_dates", "lesson_times", "pattern"]
    assert office_ao.put("/api/timetable/settings", {"value": value}).status == 200
    scoped = app_db.client("admin")                                        # an academic office with one faculty only may not publish
    assert scoped.post(f"/api/admin/users/{world['rauf']}/roles", {"role": "academic_office", "scope_type": "faculty", "scope_id": 1}).status == 200
    faculty_ao = app_db.client("teacher")
    assert faculty_ao.post("/api/me/role", {"role": "academic_office"}).status == 200
    assert faculty_ao.post(f"/api/timetable/versions/{vid}/publish", body).status == 403
    queued = office_ao.post(f"/api/timetable/versions/{vid}/publish", body)
    assert queued.status == 200 and queued.json["kind"] == "publish", queued.text
    manual = office_ao.post("/api/timetable", {"unit_id": world["units"][0], "weekday": 6, "start": "15:05", "end": "16:25", "room": "X",
                                               "weeks": "all", "academic_hours": 2})
    assert manual.status == 409                                            # hand-written rows wait while the term is published


def _lesson_days(row, term):
    return [d.isoformat() for d in domain.lesson_dates(row, term, [], date.fromisoformat(EFF))]


def test_a_publication_writes_rows_lessons_and_one_notice_per_person(world):
    vid = world["vid"]
    run_jobs()
    run = q("SELECT * FROM tt_runs WHERE kind='publish' ORDER BY id DESC LIMIT 1")[0]
    assert run["status"] == "done", run
    v = q("SELECT * FROM tt_versions WHERE id=?", (vid,))[0]
    assert v["status"] == "published" and v["effective_from"] == EFF
    pls = q("SELECT * FROM tt_placements WHERE version_id=?", (vid,))
    rows_ = q("SELECT * FROM timetable WHERE version_id=? AND active=1", (vid,))
    assert len(rows_) == len(pls) and all(p["timetable_id"] for p in pls)
    term = q("SELECT * FROM academic_terms WHERE id=?", (TERM,))[0]
    for r in rows_:
        days = [x["day"] for x in q("SELECT day FROM lessons WHERE timetable_id=? ORDER BY day", (r["id"],))]
        assert days == _lesson_days(r, term), r                            # every lesson from the effective date, none before
    for g, ids in world["students"].items():
        for s in ids:
            n = q("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND link='/student/schedule' AND title LIKE ?", (s, f"%{_dotted(EFF)}%"))
            assert n[0]["n"] == 1, (g, s)
    for t in world["teachers"]:
        assert q("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND title LIKE ?", (t, f"%{_dotted(EFF)}%"))[0]["n"] == 1
    assert q("SELECT 1 FROM audit WHERE action='timetable_publish' AND detail LIKE ?", (f"{vid} ·%",))
    assert q("SELECT tx_ms FROM (SELECT json_extract(progress, '$.tx_ms_max') tx_ms FROM tt_runs WHERE id=?)", (run["id"],))[0]["tx_ms"] < 200


def test_a_second_publication_interrupted_after_every_batch_is_exactly_once(office_ao, world, monkeypatch):
    first = world["vid"]
    started = office_ao.post(f"{B}/runs", {"kind": "solve", "budget": 500, "seed": 3})
    assert started.status == 200
    run_jobs()
    vid = q("SELECT version_id FROM tt_runs WHERE id=?", (started.json["id"],))[0]["version_id"]
    assert q("SELECT parent_id FROM tt_versions WHERE id=?", (vid,))[0]["parent_id"] == first
    p = _seminar(world, vid)
    opts = office_ao.get(f"/api/timetable/versions/{vid}/placements/{p['id']}/options").json
    to = next(o for o in opts["options"] if not o["reasons"] and not o["current"])
    assert office_ao.post(f"/api/timetable/versions/{vid}/placements/{p['id']}/move",
                          {"weekday": to["weekday"], "period": to["period"], "room_id": to["room_id"], "rev": opts["rev"]}).status == 200
    assert office_ao.post(f"{B}/runs", {"kind": "check", "version_id": vid}).status == 200
    run_jobs()
    row = q("SELECT * FROM timetable WHERE meeting_key=? AND active=1", (p["meeting_key"],))[0]
    later = q("SELECT id FROM lessons WHERE timetable_id=? AND day>=? ORDER BY day LIMIT 1", (row["id"], EFF2))[0]["id"]
    student = world["students"][world["groups"][0]][0]
    c = store.connect()
    c.execute("INSERT INTO attendance(lesson_id,user_id,status) VALUES(?,?,'present')", (later, student))  # recorded: never touched
    c.commit()
    c.close()
    before = q("SELECT id, timetable_id, day, start FROM lessons WHERE day<? ORDER BY id", (EFF2,))
    v = q("SELECT * FROM tt_versions WHERE id=?", (vid,))[0]
    queued = office_ao.post(f"/api/timetable/versions/{vid}/publish", {"effective_from": EFF2, "accept_unplaced": v["unplaced"],
                                                                        "override_reason": "İkinci dərc, sınaq üçün"})
    assert queued.status == 200, queued.text
    monkeypatch.setattr(builder, "ROWS_BATCH", 3)
    monkeypatch.setattr(builder, "DROP_BATCH", 1)
    monkeypatch.setattr(builder, "LESSON_BATCH", 1)
    monkeypatch.setattr(builder, "NOTIFY_BATCH", 2)
    crashed: set[str] = set()
    real_save = builder._p_save

    def crash_once(c, r, state, **progress):                            # a crash after every step's effect, before it commits
        key = f"{progress.get('step')}:{progress.get('cursor')}"
        if key not in crashed:
            crashed.add(key)
            raise RuntimeError("killed")
        return real_save(c, r, state, **progress)

    monkeypatch.setattr(builder, "_p_save", crash_once)
    c = store.connect()
    try:
        for _ in range(400):
            r = q("SELECT * FROM tt_runs WHERE id=?", (queued.json["id"],))[0]
            if r["status"] != "running" and r["status"] != "queued":
                break
            try:
                builder.publish_step(c, store.row(c, "SELECT * FROM tt_runs WHERE id=?", (r["id"],)), 0)
            except RuntimeError:
                c.rollback()
    finally:
        c.close()
    r = q("SELECT * FROM tt_runs WHERE id=?", (queued.json["id"],))[0]
    assert r["status"] == "done" and len(crashed) > 5, r
    assert q("SELECT id, timetable_id, day, start FROM lessons WHERE day<? ORDER BY id", (EFF2,)) == before   # the past is frozen
    assert q("SELECT 1 FROM lessons WHERE id=?", (later,))                 # the recorded lesson stays
    moved = q("SELECT * FROM timetable WHERE meeting_key=? AND active=1", (p["meeting_key"],))
    assert len(moved) == 1 and (moved[0]["weekday"], moved[0]["period"]) == (to["weekday"], to["period"])
    term = q("SELECT * FROM academic_terms WHERE id=?", (TERM,))[0]
    days = [d.isoformat() for d in domain.lesson_dates(moved[0], term, [], date.fromisoformat(EFF2))]
    made = [x["day"] for x in q("SELECT day FROM lessons WHERE timetable_id=? AND day>=? AND start=?", (row["id"], EFF2, moved[0]["start"]))]
    assert sorted(made) == days
    rows_ = q("SELECT COUNT(*) n FROM timetable WHERE active=1 AND meeting_key IS NOT NULL")[0]["n"]
    assert rows_ == q("SELECT COUNT(*) n FROM tt_placements WHERE version_id=?", (vid,))[0]["n"]
    told = q("SELECT user_id, COUNT(*) n FROM notifications WHERE title LIKE ? GROUP BY user_id", (f"%{_dotted(EFF2)}%",))
    assert told and all(x["n"] == 1 for x in told)
    assert q("SELECT status FROM tt_versions WHERE id=?", (first,))[0]["status"] == "superseded"
    world["moved"] = (row["id"], moved[0]["weekday"], moved[0]["start"])


def test_the_daily_lessons_job_never_makes_a_lesson_before_the_effective_date(world):
    rid, weekday, start = world["moved"]
    c = store.connect()
    try:
        periodic.lessons_generate(c)
        c.commit()
    finally:
        c.close()
    early = [x for x in q("SELECT slot_day, slot_start FROM lessons WHERE timetable_id=? AND slot_day<?", (rid, EFF2))
             if date.fromisoformat(x["slot_day"]).isoweekday() == weekday and x["slot_start"] == start]
    assert early == []                                                     # the new time only from the second effective date
    assert q("SELECT COUNT(*) n FROM lessons l JOIN timetable t ON t.id=l.timetable_id WHERE t.version_id=? AND l.day<?",
             (world["vid"], EFF))[0]["n"] == 0


# ---------------------------------------------------------------- review of slices 1-3 (tasks/todo.md, Task 48)
def _manual_row(office_ao, unit):
    """A hand-written row for ``unit`` on a free afternoon (POST /api/timetable checks every clash)."""
    for wd in (6, 5, 4, 3):
        for st, en in (("15:05", "16:25"), ("16:35", "17:55"), ("18:05", "19:25")):
            r = office_ao.post("/api/timetable", {"unit_id": unit, "weekday": wd, "start": st, "end": en, "room": "X", "weeks": "all",
                                                  "academic_hours": 2})
            if r.status == 200:
                return r.json
    raise AssertionError("no free afternoon for a hand-written row")


def _solve(office_ao, seed):
    s = office_ao.post(f"{B}/runs", {"kind": "solve", "budget": 300, "seed": seed})
    assert s.status == 200, s.text
    run_jobs()
    run = office_ao.get(f"/api/timetable/runs/{s.json['id']}").json
    assert run["status"] == "done", run
    return run


def _publish(office_ao, vid, eff):
    v = q("SELECT * FROM tt_versions WHERE id=?", (vid,))[0]
    r = office_ao.post(f"/api/timetable/versions/{vid}/publish", {"effective_from": eff, "accept_unplaced": v["unplaced"],
                                                                   "override_reason": "Sınaq üçün dərc edilir"})
    assert r.status == 200, r.text
    return r.json["id"]


def test_a_unit_with_a_hand_written_row_keeps_its_builder_rows_through_a_publication(office_ao, world):
    """TT-SEC-2: the run keeps the unit out and treats its rows as obstacles, so the publication must not drop them."""
    u, eff = world["units"][0], "2026-12-07"
    builder_rows = q("SELECT id FROM timetable WHERE unit_id=? AND active=1 AND meeting_key IS NOT NULL", (u,))
    assert builder_rows
    _manual_row(office_ao, u)
    run = _solve(office_ao, 17)
    assert u in run["report"]["kept_manual"]
    rid = _publish(office_ao, run["version_id"], eff)
    run_jobs()
    assert q("SELECT status FROM tt_runs WHERE id=?", (rid,))[0]["status"] == "done"
    ids = tuple(x["id"] for x in builder_rows)
    assert q(f"SELECT COUNT(*) n FROM timetable WHERE active=1 AND id IN ({','.join('?' * len(ids))})", ids)[0]["n"] == len(ids)
    assert q(f"SELECT COUNT(*) n FROM lessons WHERE day>=? AND timetable_id IN ({','.join('?' * len(ids))})", (eff, *ids))[0]["n"] > 0


def test_a_publication_failing_after_its_check_retries_and_keeps_the_term_locked(office_ao, world, monkeypatch):
    """TT-SEC-1: three errors in a row after the rows step used to leave the version published and its lessons stale."""
    import sqlite3

    from zeka.modules.timetable import repo as ttrepo
    vid, eff = _solve(office_ao, 19)["version_id"], "2026-12-14"
    p = q("SELECT p.* FROM tt_placements p JOIN timetable t ON t.meeting_key=p.meeting_key AND t.active=1 WHERE p.version_id=? "
          "ORDER BY p.id LIMIT 1", (vid,))[0]
    opts = office_ao.get(f"/api/timetable/versions/{vid}/placements/{p['id']}/options").json
    to = next(o for o in opts["options"] if not o["reasons"] and not o["current"])
    assert office_ao.post(f"/api/timetable/versions/{vid}/placements/{p['id']}/move",
                          {"weekday": to["weekday"], "period": to["period"], "room_id": to["room_id"], "rev": opts["rev"]}).status == 200
    assert office_ao.post(f"{B}/runs", {"kind": "check", "version_id": vid}).status == 200
    run_jobs()
    row = q("SELECT * FROM timetable WHERE meeting_key=? AND active=1", (p["meeting_key"],))[0]
    rid = _publish(office_ao, vid, eff)

    def boom(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(ttrepo, "drop_lessons_from", boom)
    c = store.connect()
    try:
        for _ in range(6):
            builder.work(c)
    finally:
        c.close()
    r = office_ao.get(f"/api/timetable/runs/{rid}").json
    assert r["status"] == "running" and r["progress"]["step"] == "drop", r
    assert r["error"] and "OperationalError" not in r["error"] and "OperationalError" in r["progress"]["detail"]
    assert q("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND title LIKE '%yarımçıq%'", (office_ao.user["id"],))[0]["n"] == 1
    assert office_ao.put(f"/api/timetable/{row['id']}", {"room": "Y"}).status == 409          # the term stays locked
    monkeypatch.undo()
    run_jobs()
    done = q("SELECT status, error FROM tt_runs WHERE id=?", (rid,))[0]
    assert (done["status"], done["error"]) == ("done", None)
    moved = q("SELECT * FROM timetable WHERE id=?", (row["id"],))[0]
    stale = q("SELECT COUNT(*) n FROM lessons WHERE timetable_id=? AND day>=? AND start<>?", (row["id"], eff, moved["start"]))[0]["n"]
    assert (moved["weekday"], moved["period"]) == (to["weekday"], to["period"]) and stale == 0


def test_a_version_built_on_an_older_publication_is_not_published(office_ao, world):
    """TE-F1: the gate's stale_parent rule, at the request and again in the publication's own check."""
    a, b = _solve(office_ao, 23)["version_id"], _solve(office_ao, 29)["version_id"]       # both on the current publication
    rid = _publish(office_ao, a, "2026-12-21")
    run_jobs()
    assert q("SELECT status FROM tt_runs WHERE id=?", (rid,))[0]["status"] == "done"
    v = q("SELECT * FROM tt_versions WHERE id=?", (b,))[0]
    r = office_ao.post(f"/api/timetable/versions/{b}/publish", {"effective_from": "2026-12-28", "accept_unplaced": v["unplaced"],
                                                                "override_reason": "Sınaq üçün dərc edilir"})
    assert r.status == 409 and [x["code"] for x in r.json["gate"]] == ["stale_parent"], r.text
    fresh = _solve(office_ao, 31)["version_id"]
    rid = _publish(office_ao, fresh, "2026-12-28")
    c = store.connect()                              # its base replaced after the request: as if another publication came first
    c.execute("UPDATE tt_versions SET parent_id=? WHERE id=?", (v["parent_id"], fresh))
    c.commit()
    c.close()
    run_jobs()
    r = office_ao.get(f"/api/timetable/runs/{rid}").json
    assert r["status"] == "failed" and "stale_parent" in [x["code"] for x in r["progress"]["problems"]], r
    assert q("SELECT status FROM tt_versions WHERE id=?", (a,))[0]["status"] == "published"


def test_a_faculty_scoped_office_reaches_no_draft_or_run_of_another_faculty(app_db, office_ao, world):
    """TT-SEC-3: an academic office of another faculty edits, reads and cancels nothing of this one."""
    c = store.connect()
    now = store.iso(store.now())
    f2 = c.execute("INSERT INTO faculties(code,name,active,created_at,updated_at) VALUES('F2X','İkinci fakültə',1,?,?)", (now, now)).lastrowid
    d2 = c.execute("INSERT INTO departments(faculty_id,code,name,active,created_at,updated_at) VALUES(?,'D2X','İkinci kafedra',1,?,?)",
                   (f2, now, now)).lastrowid
    c.commit()
    c.close()
    admin, uid = app_db.client("admin"), app_db.client("leader").user["id"]
    assert admin.post(f"/api/admin/users/{uid}/roles", {"role": "academic_office", "scope_type": "faculty", "scope_id": f2}).status == 200
    ao2 = app_db.client("leader")
    assert ao2.post("/api/me/role", {"role": "academic_office"}).status == 200
    s = office_ao.post(f"{B}/runs", {"kind": "solve", "budget": 300, "seed": 13})
    assert s.status == 200 and ao2.get(f"/api/timetable/runs/{s.json['id']}").status == 404
    run_jobs()
    vid = q("SELECT version_id FROM tt_runs WHERE id=?", (s.json["id"],))[0]["version_id"]
    p = q("SELECT * FROM tt_placements WHERE version_id=? AND room_id IS NOT NULL ORDER BY id LIMIT 1", (vid,))[0]
    rev = q("SELECT rev FROM tt_versions WHERE id=?", (vid,))[0]["rev"]
    base = f"/api/timetable/versions/{vid}"
    assert ao2.get(f"{base}/placements/{p['id']}/options").status == 404
    assert ao2.post(f"{base}/placements/{p['id']}/move", {"weekday": 1, "period": 1, "room_id": p["room_id"], "rev": rev}).status == 404
    assert ao2.post(f"{base}/lock", {"ids": [p["id"]], "locked": True, "rev": rev}).status == 404
    assert ao2.get(f"{base}/grid?room_id={p['room_id']}").json["items"] == []
    assert ao2.get(f"{base}/unplaced").json == []
    assert q("SELECT rev FROM tt_versions WHERE id=?", (vid,))[0]["rev"] == rev
    # SEC-TT-2: a check of that draft with the office's own department is refused before a run takes the term's slot
    assert ao2.post(f"{B}/runs", {"kind": "check", "version_id": vid, "departments": [d2]}).status == 404
    assert ao2.post(f"{B}/runs", {"kind": "precheck", "departments": [d2], "base_version_id": vid}).status == 404
    assert not q("SELECT 1 FROM tt_runs WHERE requested_by=?", (ao2.user["id"],))
    # SEC-TT-1: the university's timetable rules and the term's plan are not a faculty's to change
    before = office_ao.get("/api/timetable/settings").json["timetable"]
    plan = q("SELECT * FROM tt_terms WHERE term_id=?", (TERM,))
    assert ao2.put("/api/timetable/settings", {"value": {**before, "notice_days": 0, "review_required": False}}).status == 403
    assert ao2.put(f"{B}/plan", {"publish_target": "2026-12-01", "confirmed": []}).status == 403
    assert office_ao.get("/api/timetable/settings").json["timetable"] == before
    assert q("SELECT * FROM tt_terms WHERE term_id=?", (TERM,)) == plan
    s2 = office_ao.post(f"{B}/runs", {"kind": "precheck"})
    assert ao2.post(f"/api/timetable/runs/{s2.json['id']}/cancel", {}).status == 404
    run_jobs()
    assert q("SELECT status FROM tt_runs WHERE id=?", (s2.json["id"],))[0]["status"] == "done"
    world["draft"] = vid


def test_malformed_shifts_and_periods_answer_their_own_400(office_ao, world):
    """TT-SEC-4: a list or an object where a shift or a building id goes, and a negative period, ended in the catch-all."""
    g = world["groups"][0]
    for item in ({"group_id": g, "shift": ["morning"]}, {"group_id": g, "shift": {"a": 1}}, {"group_id": g, "home_building_id": [1]},
                 {"group_id": g, "home_building_id": {"x": 1}}):
        r = office_ao.put(f"{B}/groups", {"items": [item]})
        assert r.status == 400 and "növbəsi" in r.json["error"], (item, r.text)
    vid = world["draft"]
    p = q("SELECT * FROM tt_placements WHERE version_id=? ORDER BY id LIMIT 1", (vid,))[0]
    rev = q("SELECT rev FROM tt_versions WHERE id=?", (vid,))[0]["rev"]
    for wd, period in ((1, -3), (1, 0), (1, 99), (0, 1), (8, 1)):
        r = office_ao.post(f"/api/timetable/versions/{vid}/placements/{p['id']}/move", {"weekday": wd, "period": period, "rev": rev})
        assert r.status == 400 and "Yeni vaxtı" in r.json["error"], (wd, period, r.text)


def test_a_refused_publication_names_the_lesson_and_the_rule_and_the_grid_marks_it(office_ao, world):
    """UX1: a failed publication said 'check: 1 violations'; UX2: a precheck run showed none of its findings."""
    vid = world["draft"]
    p = q("SELECT p.* FROM tt_placements p WHERE p.version_id=? AND p.room_id IS NOT NULL ORDER BY p.id LIMIT 1", (vid,))[0]
    needs = f"/api/timetable/units/{p['unit_id']}/needs"
    assert office_ao.put(needs, {"need": 500, "need_reason": "Sınaq üçün böyük axın"}).status == 200
    rid = _publish(office_ao, vid, "2026-12-21")
    run_jobs()
    r = office_ao.get(f"/api/timetable/runs/{rid}").json
    assert r["status"] == "failed" and r["error"].startswith("Dərc dayandırıldı"), r
    bad = next(x for x in r["progress"]["problems"] if x["code"] == "capacity")
    course = q("SELECT co.name FROM teaching_units u JOIN courses co ON co.id=u.course_id WHERE u.id=?", (p["unit_id"],))[0]["name"]
    assert bad["title"] and bad["courses"] == [course] and bad["slot"] == [p["weekday"], p["period"]]
    v = q("SELECT violations, checked_rev, rev FROM tt_versions WHERE id=?", (vid,))[0]
    assert v["violations"] >= 1 and v["checked_rev"] == v["rev"]                   # the list shows it at once
    g = q("SELECT group_id FROM teaching_unit_groups WHERE unit_id=? LIMIT 1", (p["unit_id"],))[0]["group_id"]
    items = office_ao.get(f"/api/timetable/versions/{vid}/grid?group_id={g}").json["items"]
    marked = next(x for x in items if x["id"] == p["id"])
    assert [x["code"] for x in marked["problems"]] == ["capacity"] and marked["problems"][0]["title"]
    pre = office_ao.post(f"{B}/runs", {"kind": "precheck"})
    run_jobs()
    pr = office_ao.get(f"/api/timetable/runs/{pre.json['id']}").json
    assert pr["progress"]["phase"] == "done"
    line = next(x for x in pr["report"]["precheck"] if x["code"] == "no_room_capacity" and x["key"].startswith(f"{p['unit_id']}:"))
    assert "500" in line["title"] and line["courses"] == [course], line
    assert office_ao.put(needs, {"need": None}).status == 200


def test_a_scoped_office_reads_only_its_own_units_of_a_draft(app_db, office_ao, world):
    """SEC-TT-3: a faculty-scoped office read every problem of a university-wide draft, and every draft of named departments."""
    vid = world["draft"]
    assert office_ao.get(f"/api/timetable/versions/{vid}/scorecard").json["score"]["problems"]
    ao2 = app_db.client("leader")                                       # the academic office of the faculty with no unit here
    assert ao2.post("/api/me/role", {"role": "academic_office"}).status == 200
    assert ao2.get(f"/api/timetable/versions/{vid}/scorecard").json["score"]["problems"] == []
    c = store.connect()
    try:
        other = c.execute("INSERT INTO tt_versions(term_id,status,scope,rev,created_by,created_at) SELECT term_id,'draft',?,0,created_by,"
                          "created_at FROM tt_versions WHERE id=?", (json.dumps({"departments": [world["dep"]]}), vid)).lastrowid
        c.commit()
    finally:
        c.close()
    assert ao2.get(f"/api/timetable/versions/{other}/scorecard").status == 404
    assert other not in [v["id"] for v in ao2.get(f"{B}/versions").json]
    assert other in [v["id"] for v in office_ao.get(f"{B}/versions").json]


def test_a_run_and_the_readiness_say_which_units_hand_written_rows_keep_out(office_ao, world):
    """UX3: the office read 'every lesson placed' while units with hand-written rows were never scheduled; UX11: the
    samples were bare ids; UX4: the editor's week left those rows out."""
    u = world["units"][0]
    lines = office_ao.get(f"{B}/readiness").json["lines"]
    manual = next(x for x in lines if x["code"] == "manual_rows")
    assert u in manual["samples"] and manual["title"] and manual["level"] == "warn"
    assert manual["labels"][manual["samples"].index(u)].startswith("Sınaq fənni 0")
    vac = next(x for x in lines if x["code"] == "vacancies")
    assert vac["labels"][vac["samples"].index(world["vacancy"])].startswith("Sınaq fənni 1")
    shifts = next(x for x in lines if x["code"] == "group_shifts")
    assert all(not str(x).startswith("#") for x in shifts["labels"])
    v = q("SELECT run_id, score FROM tt_versions WHERE id=?", (world["draft"],))[0]
    run = office_ao.get(f"/api/timetable/runs/{v['run_id']}").json
    assert run["progress"]["kept_manual"] == len(run["report"]["kept_manual"]) > 0
    assert office_ao.get(f"/api/timetable/versions/{world['draft']}/scorecard").json["score"]["kept_manual"] == run["progress"]["kept_manual"]
    g = q("SELECT group_id FROM teaching_unit_groups WHERE unit_id=? LIMIT 1", (u,))[0]["group_id"]
    grid = office_ao.get(f"/api/timetable/versions/{world['draft']}/grid?group_id={g}").json
    mine = [x for x in grid["fixed"] if x["course"] == "Sınaq fənni 0"]
    assert mine and all(x["start"] and x["period"] for x in mine), grid["fixed"]
    assert not {x["id"] for x in grid["fixed"]} & {x["timetable_id"] for x in q("SELECT timetable_id FROM tt_placements WHERE version_id=? "
                                                                                  "AND timetable_id IS NOT NULL", (world["draft"],))}


def test_the_teachers_board_tells_apart_two_people_of_one_name(office_ao, world):
    """UX12: the editor's teacher list showed two people of one name with nothing between them."""
    items = office_ao.get(f"{B}/teachers").json["items"]
    mine = next(x for x in items if x["id"] == world["teachers"][0])
    assert mine["department"] == "Sınaq kafedrası" and "patronymic" in mine


def test_the_weekly_schedule_shows_a_publication_only_from_its_effective_date(app_db, world):
    """UX9: the teacher's week showed the first publication's rows (effective 23.11) in the week of 16.11."""
    week = app_db.client("teacher").get("/api/schedule").json
    shown = {x["id"] for d in week["days"] for x in d["items"]}
    published = {x["id"] for x in q("SELECT id FROM timetable WHERE version_id IS NOT NULL")}
    assert shown and not shown & published, shown & published
    assert week["week_start"] == "2026-11-16"


# ---------------------------------------------------------------- the hours report and the timetable export (Task 48, deferred parts)
@pytest.fixture
def chain(app_db, office_ao, head, world):
    """ORD-2: the hours and export tests read the draft and the publication the tests above leave. Run alone (``-k``),
    the tests above run here first, in file order. shortcut: assumes none of them ran in this session already; a
    selection of some of them with these runs them twice, so select all or none of them."""
    if "draft" in world:
        return world
    mp = pytest.MonkeyPatch()
    given = {"app_db": app_db, "office_ao": office_ao, "head": head, "world": world, "monkeypatch": mp}
    first = test_the_hours_report_counts_the_weeks_each_placement_holds.__code__.co_firstlineno
    steps = sorted((f for n, f in globals().items() if n.startswith("test_") and f.__code__.co_firstlineno < first),
                   key=lambda f: f.__code__.co_firstlineno)
    try:
        for f in steps:
            f(*(given[a] for a in inspect.signature(f).parameters))
            mp.undo()
    finally:
        mp.undo()
    return world


def _published_version():
    return q("SELECT id FROM tt_versions WHERE term_id=? AND status='published' ORDER BY id DESC LIMIT 1", (TERM,))[0]["id"]


def _tenant_with(monkeypatch, holidays=(), **timetable):
    """The university settings as the builder reads them, with extra holidays or other timetable settings."""
    real = tenant.load

    def load(c):
        d = copy.deepcopy(real(c))
        d["calendar"]["holidays"] = [*d["calendar"]["holidays"], *holidays]
        d["timetable"].update(timetable)
        return d
    monkeypatch.setattr(tenant, "load", load)


def test_the_hours_report_counts_the_weeks_each_placement_holds(office_ao, world, chain, monkeypatch):
    """The hours page: per unit the Forma №3 hours and the hours the placements yield in the term, counted here week by
    week over the term's teaching days without holidays; a new holiday takes its pair off and says why."""
    vid, url = world["draft"], f"/api/timetable/versions/{world['draft']}/hours?department_id={world['dep']}"
    term = q("SELECT * FROM academic_terms WHERE id=?", (TERM,))[0]
    c = store.connect()
    try:
        st = tenant.load(c)
    finally:
        c.close()
    hol, ph, tol = set(st["calendar"]["holidays"]), st["timetable"]["pair_hours"], st["timetable"]["hours_tolerance"]
    first, last, n = date.fromisoformat(term["teaching_start"]), date.fromisoformat(term["teaching_end"]), domain.term_weeks(term)
    monday = first - timedelta(days=first.isoweekday() - 1)
    pls = q("SELECT p.* FROM tt_placements p JOIN teaching_units u ON u.id=p.unit_id JOIN courses co ON co.id=u.course_id "
            "WHERE p.version_id=? AND co.department_id=? ORDER BY p.id", (vid, world["dep"]))

    def days(p):
        mask = domain.week_mask(p["weeks"], n)
        return [d for d in (monday + timedelta(days=7 * w + p["weekday"] - 1) for w in range(n) if mask >> w & 1) if first <= d <= last]

    def held(off):
        out: dict = {}
        for p in pls:
            out[p["unit_id"]] = out.get(p["unit_id"], 0) + ph * p["duration"] * sum(d.isoformat() not in off for d in days(p))
        return out

    r = office_ao.get(url)
    assert r.status == 200, r.text
    got = {x["unit_id"]: x for x in r.json["items"]}
    assert pls and {u: got[u]["planned_h"] for u in held(hol)} == held(hol)
    assert all(x["delta"] == round(x["planned_h"] - x["form_h"], 2) and x["flagged"] == (abs(x["delta"]) > tol) for x in got.values())
    assert [m["code"] for m in got[world["lonely"]]["reasons"]] == ["no_groups"] and got[world["lonely"]]["reasons"][0]["title"]
    assert r.json["totals"] == {"form_h": sum(x["form_h"] for x in got.values()), "planned_h": sum(x["planned_h"] for x in got.values()),
                                "delta": round(sum(x["planned_h"] - x["form_h"] for x in got.values()), 2)}
    assert r.json["flagged"] == sum(x["flagged"] for x in got.values()) and r.json["total"] == len(got)
    p = next(p for p in pls if any(d.isoformat() not in hol for d in days(p)))
    day = next(d.isoformat() for d in days(p) if d.isoformat() not in hol)
    _tenant_with(monkeypatch, holidays=[day])
    after = {x["unit_id"]: x for x in office_ao.get(url).json["items"]}
    assert after[p["unit_id"]]["planned_h"] == got[p["unit_id"]]["planned_h"] - ph * p["duration"] == held(hol | {day})[p["unit_id"]]
    assert "holidays" in [m["code"] for m in after[p["unit_id"]]["reasons"]]


def test_the_hours_report_filters_totals_and_downloads_as_csv(office_ao, world, chain, monkeypatch):
    """Outside the tolerance only, totals of what is listed, and the CSV (a BOM, the headings in the reader's language)."""
    _tenant_with(monkeypatch, hours_tolerance=0)
    base = f"/api/timetable/versions/{world['draft']}/hours"
    every = office_ao.get(base).json
    out = office_ao.get(f"{base}?outside=1").json
    assert every["flagged"] and out["total"] == every["flagged"] < every["total"]
    assert all(x["flagged"] for x in out["items"])
    assert out["totals"]["form_h"] == sum(x["form_h"] for x in out["items"])
    got = office_ao.get(f"{base}?outside=1&format=csv", lang="en")
    assert got.status == 200 and got.headers["Content-Type"].startswith("text/csv")
    assert got.body.startswith("\ufeff".encode())
    lines = list(csv.reader(io.StringIO(got.text.lstrip("\ufeff"))))
    assert lines[0][:2] == ["Department", "Course"] and len(lines) == out["total"] + 1
    assert {x[8] for x in lines[1:]} == {"No"}                                     # within the tolerance: no, on every line


def test_the_hours_report_keeps_to_the_callers_scope(app_db, office_ao, head, world, chain):
    """As the builder: a draft only to the builders, an id out of scope 404, a scoped office reads only its own units."""
    draft, pub = world["draft"], _published_version()
    assert app_db.client("student").get(f"/api/timetable/versions/{pub}/hours").status == 403
    assert head.get(f"/api/timetable/versions/{draft}/hours").status == 404
    mine = head.get(f"/api/timetable/versions/{pub}/hours").json
    deps = {r["id"]: r["department_id"] for r in q("SELECT u.id, co.department_id FROM teaching_units u JOIN courses co ON co.id=u.course_id")}
    assert mine["items"] and {deps[x["unit_id"]] for x in mine["items"]} == {world["dep"]}
    ao2 = app_db.client("leader")                                          # the academic office of a faculty with no unit here
    assert ao2.post("/api/me/role", {"role": "academic_office"}).status == 200
    none = ao2.get(f"/api/timetable/versions/{draft}/hours").json
    assert none["items"] == [] and none["total"] == 0 and none["totals"]["form_h"] == 0
    assert ao2.get(f"/api/timetable/versions/{draft}/hours?department_id={world['dep']}").status == 404
    assert ao2.get(f"/api/timetable/versions/{draft}/hours?format=csv").text.lstrip("\ufeff").count("\n") == 1     # the headings only
    c = store.connect()
    try:
        named = c.execute("INSERT INTO tt_versions(term_id,status,scope,rev,created_by,created_at) SELECT term_id,'draft',?,0,created_by,"
                          "created_at FROM tt_versions WHERE id=?", (json.dumps({"departments": [world["dep"]]}), draft)).lastrowid
        c.commit()
    finally:
        c.close()
    assert ao2.get(f"/api/timetable/versions/{named}/hours").status == 404
    assert office_ao.get(f"/api/timetable/versions/{named}/hours").status == 200


def test_the_timetable_export_writes_a_version_or_the_terms_rows(office_ao, world, chain):
    """manage.py export --kind timetable: a version's placements (--version) or the term's rows in force (--term), one line
    per group, weeks in the canonical text, the effective date of the publishing version."""
    pub = _published_version()
    eff = q("SELECT effective_from FROM tt_versions WHERE id=?", (pub,))[0]["effective_from"]
    env = {**os.environ, "ZEKA_DATA": str(store.DATA)}
    man = [sys.executable, str(ROOT / "backend" / "manage.py"), "export", "--kind", "timetable"]
    r = subprocess.run([*man, "--version", str(pub)], capture_output=True, env=env, timeout=120)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    got = list(csv.DictReader(io.StringIO(r.stdout.decode("utf-8"))))
    assert got and list(got[0]) == list(rows_service.EXPORT_COLUMNS)
    pls = q("SELECT p.*, g.name grp FROM tt_placements p JOIN teaching_unit_groups ug ON ug.unit_id=p.unit_id "
            "JOIN study_groups g ON g.id=ug.group_id WHERE p.version_id=?", (pub,))
    n = domain.term_weeks(q("SELECT * FROM academic_terms WHERE id=?", (TERM,))[0])
    assert sorted((x["group"], int(x["day"]), int(x["pair"]), x["weeks"]) for x in got) == \
        sorted((p["grp"], p["weekday"], p["period"], domain.week_text(domain.week_mask(p["weeks"], n), n)) for p in pls)
    assert {x["effective_from"] for x in got} == {eff} and all(x["course"] and x["kind"] and x["start"] and x["room"] for x in got)
    rows_ = subprocess.run([*man, "--term", str(TERM)], capture_output=True, env=env, timeout=120)
    assert rows_.returncode == 0, rows_.stderr.decode("utf-8", "replace")
    term_lines = list(csv.DictReader(io.StringIO(rows_.stdout.decode("utf-8"))))
    # every row the version published is in force (with rows earlier publications keep, TT-SEC-2), each with its date
    built = [x for x in term_lines if x["effective_from"]]
    key = ("group", "day", "pair", "weeks", "course", "room")
    assert not Counter(tuple(x[k] for k in key) for x in got) - Counter(tuple(x[k] for k in key) for x in built)
    dates = q("SELECT DISTINCT v.effective_from d FROM timetable t JOIN tt_versions v ON v.id=t.version_id JOIN courses co ON co.id=t.course_id "
              "WHERE t.active=1 AND co.term_id=?", (TERM,))
    assert {x["effective_from"] for x in built} == {x["d"] for x in dates}     # a row unchanged by a publication keeps its own date
    assert any(not x["effective_from"] for x in term_lines)                          # the term's hand-written rows, without one
    assert all(x["pair"] and (x["weeks"] in ("all", "odd", "even") or x["weeks"][0].isdigit()) for x in term_lines)
    bad = subprocess.run([*man, "--version", "999999"], capture_output=True, env=env, timeout=120)
    assert bad.returncode == 2 and b"tap" in bad.stderr
    assert office_ao.get(f"/api/integration/export/timetable?version={pub}").status == 403          # integration.manage only


def test_the_scorecard_counts_the_hours_as_the_hours_report_does(office_ao, world, chain):
    """BR-T1: the versions' comparison and the hours page give one number for one version: a unit the run leaves out
    (no groups) counts in both, with nothing planned. A published version's report counts its lessons instead (OK-1),
    so there only the units and their Forma №3 hours agree."""
    for vid in (world["draft"], _published_version()):
        card = office_ao.get(f"/api/timetable/versions/{vid}/scorecard").json["score"]["hours"]
        rep = office_ao.get(f"/api/timetable/versions/{vid}/hours").json
        if vid == world["draft"]:
            assert card == {"flagged": rep["flagged"], "form_h": rep["totals"]["form_h"], "planned_h": rep["totals"]["planned_h"]}, vid
        assert card["form_h"] == rep["totals"]["form_h"] and world["lonely"] in {x["unit_id"] for x in rep["items"]}


def test_the_hours_report_pages_keep_their_totals_and_the_department_list(office_ao, world, chain, monkeypatch):
    """MUT-hours-page (h04 h05 h06): ``offset`` pages the lines by HOURS_PAGE, the totals and the count stay those of
    every line; MUT-h03: a department filter keeps every department in the list; MUT-h09-h10: the tolerance is the
    university's and a reason has its title in the reader's language."""
    _tenant_with(monkeypatch, hours_tolerance=7)
    monkeypatch.setattr(builder, "HOURS_PAGE", 3)
    base = f"/api/timetable/versions/{world['draft']}/hours"
    first, second = office_ao.get(f"{base}?offset=0").json, office_ao.get(f"{base}?offset=3").json
    lines = list(csv.reader(io.StringIO(office_ao.get(f"{base}?format=csv").text.lstrip("\ufeff"))))[1:]
    assert first["total"] == second["total"] == len(lines) > 6 and (first["offset"], second["offset"]) == (0, 3)
    assert len(first["items"]) == len(second["items"]) == 3
    pages = [x["unit_id"] for p in range(0, first["total"], 3) for x in office_ao.get(f"{base}?offset={p}").json["items"]]
    assert len(pages) == len(set(pages)) == first["total"], "every line once, a page at a time"
    assert first["totals"] == second["totals"] == {"form_h": sum(float(x[5]) for x in lines), "planned_h": sum(float(x[6]) for x in lines),
                                                   "delta": round(sum(float(x[6]) - float(x[5]) for x in lines), 2)}
    assert first["tolerance"] == 7
    other = _write("INSERT INTO departments(faculty_id,code,name,active,created_at,updated_at) VALUES(1,'TTC','İkinci sınaq kafedrası',1,"
                   "'2026-01-01','2026-01-01')")
    _write("UPDATE courses SET department_id=? WHERE id=?", (other, world["courses"][1]))
    try:
        every = office_ao.get(base).json["departments"]
        assert len(every) == 2 and office_ao.get(f"{base}?department_id={world['dep']}").json["departments"] == every
    finally:
        _write("UPDATE courses SET department_id=? WHERE id=?", (world["dep"], world["courses"][1]))
        _write("DELETE FROM departments WHERE id=?", (other,))
    lonely = next(x for p in range(0, first["total"], 3) for x in office_ao.get(f"{base}?offset={p}").json["items"]
                  if x["unit_id"] == world["lonely"])
    en = next(x for p in range(0, first["total"], 3) for x in office_ao.get(f"{base}?offset={p}", lang="en").json["items"]
              if x["unit_id"] == world["lonely"])
    assert lonely["reasons"][0]["code"] == "no_groups" and lonely["reasons"][0]["title"] == i18n.S(builder.HOURS_REASONS["no_groups"], "az")
    assert en["reasons"][0]["title"] == i18n.S(builder.HOURS_REASONS["no_groups"], "en") != lonely["reasons"][0]["title"]


def test_a_cell_of_the_hours_csv_never_starts_a_formula(office_ao, world, chain):
    """MUT-csv (h08): a course name or a department name typed by a person is a cell that starts with a quote."""
    course = world["courses"][0]
    old = q("SELECT name FROM courses WHERE id=?", (course,))[0]["name"]
    dep = q("SELECT name FROM departments WHERE id=?", (world["dep"],))[0]["name"]
    _write("UPDATE courses SET name='=HYPERLINK(\"http://evil.example\")' WHERE id=?", (course,))
    _write("UPDATE departments SET name='@SUM(1)' WHERE id=?", (world["dep"],))
    try:
        text = office_ao.get(f"/api/timetable/versions/{world['draft']}/hours?format=csv&department_id={world['dep']}").text
        lines = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))[1:]
        assert lines and {x[0] for x in lines} == {"'@SUM(1)"}
        assert any(x[1].startswith("'=HYPERLINK") for x in lines) and not any(x[1].startswith("=") for x in lines)
    finally:
        _write("UPDATE courses SET name=? WHERE id=?", (old, course))
        _write("UPDATE departments SET name=? WHERE id=?", (dep, world["dep"]))


def test_the_http_export_takes_the_version_and_its_own_term_and_writes_canonical_weeks(app_db, world, chain):
    """MUT-x06: ``?version=`` and ``?term=`` reach the export over HTTP; MUT-x10: a version's weeks are read with its own
    term's week count; MUT-x02: stored weeks come out in the canonical text; MUT-x08: the audit names the version."""
    admin, pub = app_db.client("admin"), _published_version()
    term = q("SELECT * FROM academic_terms WHERE id=?", (TERM,))[0]
    n = domain.term_weeks(term)
    end = (date.fromisoformat(term["teaching_start"]) + timedelta(days=7 * (n - 3) - 1)).isoformat()   # three weeks shorter
    other = _write("INSERT INTO academic_terms(code,name,teaching_start,teaching_end,exam_start,exam_end,active,created_at,updated_at) "
                   "VALUES('TTX','Qısa semestr',?,?,?,?,0,'2026-01-01','2026-01-01')",
                   (term["teaching_start"], end, term["exam_start"], term["exam_end"]))
    n2 = domain.term_weeks(q("SELECT * FROM academic_terms WHERE id=?", (other,))[0])
    assert 3 < n2 < n
    copy_ = _write("INSERT INTO tt_versions(term_id,status,scope,rev,created_by,created_at,effective_from) SELECT ?,'superseded',scope,0,"
                   "created_by,created_at,effective_from FROM tt_versions WHERE id=?", (other, pub))
    two = q("SELECT * FROM tt_placements WHERE version_id=? ORDER BY id LIMIT 2", (pub,))
    for p, weeks in zip(two, (f"1-{n2}", "1,2,3"), strict=True):
        _write("INSERT INTO tt_placements(version_id,meeting_key,unit_id,part,weekday,period,duration,weeks,room_id,locked,origin) "
               "VALUES(?,?,?,?,?,?,?,?,?,0,'manual')", (copy_, p["meeting_key"], p["unit_id"], p["part"], p["weekday"], p["period"],
                                                     p["duration"], weeks, p["room_id"]))
    r = admin.get(f"/api/integration/export/timetable?version={copy_}")
    assert r.status == 200, r.text
    got = list(csv.DictReader(io.StringIO(r.text.lstrip("\ufeff"))))
    groups = {p["unit_id"]: max(1, q("SELECT COUNT(*) n FROM teaching_unit_groups WHERE unit_id=?", (p["unit_id"],))[0]["n"]) for p in two}
    want = sorted((p["weekday"], p["period"], w) for p, w in zip(two, ("all", "1-3"), strict=True) for _ in range(groups[p["unit_id"]]))
    assert got and sorted((int(x["day"]), int(x["pair"]), x["weeks"]) for x in got) == want
    detail = q("SELECT detail FROM audit WHERE action='export' AND entity='timetable' ORDER BY id DESC LIMIT 1")[0]["detail"]
    assert f"version {copy_}" in detail
    by_term = admin.get(f"/api/integration/export/timetable?term={other}")
    assert by_term.status == 200 and list(csv.DictReader(io.StringIO(by_term.text.lstrip("\ufeff")))) == [], "the short term has no rows"
    assert f"term {other}" in q("SELECT detail FROM audit WHERE action='export' AND entity='timetable' ORDER BY id DESC LIMIT 1")[0]["detail"]


# ---------------------------------------------------------------- Checkpoint F addendum's open item and the deferred builder items
def test_the_hours_report_of_a_published_version_counts_its_lessons(office_ao, world, chain):
    """OK-1: a published version's hours are what its lessons give in the term; a cancelled lesson takes its hours off and
    is named as the reason (the report read the placements only, so «cancelled» never appeared)."""
    pub = _published_version()
    term = q("SELECT * FROM academic_terms WHERE id=?", (TERM,))[0]
    url = f"/api/timetable/versions/{pub}/hours?department_id={world['dep']}"

    def held(u):
        return sum(x["academic_hours"] or 0 for x in q("SELECT academic_hours FROM lessons WHERE unit_id=? AND status<>'cancelled' "
                                                     "AND day BETWEEN ? AND ?", (u, term["teaching_start"], term["teaching_end"])))
    before = {x["unit_id"]: x for x in office_ao.get(url).json["items"]}
    one = q("SELECT l.id, l.unit_id, l.academic_hours, l.status FROM lessons l JOIN tt_placements p ON p.unit_id=l.unit_id "
            "WHERE p.version_id=? AND l.status<>'cancelled' AND l.academic_hours>0 ORDER BY l.id LIMIT 1", (pub,))[0]
    assert before[one["unit_id"]]["planned_h"] == held(one["unit_id"]) > 0
    _write("UPDATE lessons SET status='cancelled' WHERE id=?", (one["id"],))
    try:
        after = {x["unit_id"]: x for x in office_ao.get(url).json["items"]}[one["unit_id"]]
        assert after["planned_h"] == before[one["unit_id"]]["planned_h"] - one["academic_hours"] == held(one["unit_id"])
        assert "cancelled" in [r["code"] for r in after["reasons"]] and all(r["title"] for r in after["reasons"])
    finally:
        _write("UPDATE lessons SET status=? WHERE id=?", (one["status"], one["id"]))

