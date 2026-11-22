"""The semester timetable builder through HTTP and the job runner (tasks/todo.md, Task 48, slice 2).

A synthetic department of the demo's current term (6 groups, 20 units of 4 courses, 5 teachers plus the demo teacher,
3 students a group; ids only, no real name) goes through the cycle: settings and readiness, the term's deadlines, unit
needs, group shifts, availability (one grid above the cap, decided by the academic office), a solve run in the job
runner, the draft's grid, options and moves (a clash and a stale edit lose), a check run, the publish gate, and a
publication to timetable rows, lessons from the effective date and one notification per person; then a second
publication that is interrupted after every batch and still writes everything exactly once."""
from datetime import date, datetime, timedelta, timezone

import pytest

from zeka.core import jobs
from zeka.legacy import periodic, store             # periodic registers timetable.work
from zeka.modules.timetable import builder, domain

TERM = 1
EFF, EFF2 = "2026-11-23", "2026-11-30"


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
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


def test_a_grid_above_the_cap_waits_for_a_decision(app_db, office_ao, world):
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
            n = q("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND link='/student/schedule' AND title LIKE ?", (s, f"%{EFF}%"))
            assert n[0]["n"] == 1, (g, s)
    for t in world["teachers"]:
        assert q("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND title LIKE ?", (t, f"%{EFF}%"))[0]["n"] == 1
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
    told = q("SELECT user_id, COUNT(*) n FROM notifications WHERE title LIKE ? GROUP BY user_id", (f"%{EFF2}%",))
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


def test_a_faculty_scoped_office_reaches_no_draft_or_run_of_another_faculty(app_db, office_ao, world):
    """TT-SEC-3: an academic office of another faculty edits, reads and cancels nothing of this one."""
    c = store.connect()
    now = store.iso(store.now())
    f2 = c.execute("INSERT INTO faculties(code,name,active,created_at,updated_at) VALUES('F2X','İkinci fakültə',1,?,?)", (now, now)).lastrowid
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
