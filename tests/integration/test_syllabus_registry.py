"""The syllabus items the audit of 2026-11-23 found missing that need no owner decision: publication sets a new exam's
defaults (plan A12, Task 25), prerequisites are registry courses kept by code, a draft starts from another course's
published syllabus, the term overview for the academic office, the dean's office and leadership (with a CSV), and the
approval queue pages without a query per row (AR-11)."""
import json

import pytest

from zeka.legacy import common, store


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


T = "2026-11-01T09:00:00"


def course(code, name, term, teacher, dep):
    return run("INSERT INTO courses(code,name,teacher_id,credits,color,department_id,term_id,active,created_at,updated_at) "
               "VALUES(?,?,?,5,'#777',?,?,1,?,?)", (code, name, teacher, dep, term, T, T))


def data(**kw):
    """A syllabus that passes the demo university's rules (the exam weighs 50)."""
    d = {"description": "", "outcomes": [{"id": "N1", "text": "Dövrəni təhlil edir və hesablayır", "bloom": "analyze"}],
         "plan": [{"week": 1, "topic": "Giriş mövzusu", "outcomes": ["N1"], "activity": ""}],
         "assessment": [{"name": "Davamiyyət", "kind": "attendance", "weight": 10, "outcomes": []},
                        {"name": "Layihə işi", "kind": "component", "weight": 40, "outcomes": ["N1"]},
                        {"name": "Yekun imtahan", "kind": "exam", "weight": 50, "outcomes": ["N1"]}],
         "rules": {"attendance_limit": 20, "ai_policy": "limited", "late_policy": "", "ai_note": ""},
         "prerequisites": [], "literature": [{"title": "Elektrotexnika", "kind": "main"}],
         "workload": {"lecture": 30, "seminar": 30, "lab": 0, "independent": 60}}
    return d | kw


def version(cid, status, d=None, version=1, tags=None):
    return run("INSERT INTO syllabus_versions(course_id,version,status,data,author_id,created_at,tags) VALUES(?,?,?,?,NULL,?,?)",
               (cid, version, status, json.dumps(d or data(), ensure_ascii=False), T, json.dumps(tags) if tags is not None else None))


@pytest.fixture(scope="module")
def world(app_db):
    admin, teacher = app_db.client("admin"), app_db.client("teacher")
    term = q("SELECT * FROM academic_terms WHERE active=1")[0]
    dep = q("SELECT d.id, d.faculty_id FROM departments d JOIN study_groups g ON g.faculty_id=d.faculty_id "
            "JOIN users u ON u.group_id=g.id WHERE u.id=? LIMIT 1", (app_db.client("student").user["id"],))[0]
    cid = course("SR-101", "Reyestr sınağı", term["id"], teacher.user["id"], dep["id"])
    admin.post(f"/api/admin/users/{teacher.user['id']}/roles", {"role": "dept_head", "scope_type": "department", "scope_id": dep["id"]})
    head = app_db.client("teacher")
    assert head.post("/api/me/role", {"role": "dept_head"}).status == 200
    registrar = app_db.client("office")
    assert registrar.post("/api/me/role", {"role": "academic_office"}).status == 200
    return {"course": cid, "term": term, "dep": dep, "admin": admin, "teacher": teacher, "head": head, "registrar": registrar,
            "office": app_db.client("office"), "leader": app_db.client("leader"), "student": app_db.client("student")}


def publish(w, cid, d):
    t = w["teacher"]
    st = t.put(f"/api/syllabi/{cid}", {"data": d})
    assert st.status == 200, st.text
    vid = st.json["latest"]["id"]
    for client, action in ((t, "submit"), (w["head"], "approve"), (w["registrar"], "publish")):
        r = client.post(f"/api/syllabi/{cid}/versions/{vid}/{action}", {})
        assert r.status == 200, (action, r.text)
    return vid


# ---------------------------------------------------------------- 1. a new exam's defaults (plan A12, Task 25)
def other_teacher(world):
    return q("SELECT id FROM users WHERE role='teacher' AND id<>? ORDER BY id LIMIT 1", (world["teacher"].user["id"],))[0]["id"]


def exam_course(world, code):
    """A course of the demo teacher of its own with exam questions (ORD-1: no test shares a course another publishes)."""
    cid = course(code, f"İmtahan sınağı {code}", world["term"]["id"], world["teacher"].user["id"], world["dep"]["id"])
    for i in range(8):
        run("INSERT INTO questions(course_id,qtype,text,options,answer,unit,explanation,difficulty,topic,status,purpose,created_at) "
            "VALUES(?,'numeric',?,'[]',?,'','izah','Asan','Om','approved','exam','x')", (cid, f"Sual {i}", str(i)))
    return cid


EXAM = {"start": "00:01", "end": "23:59", "duration_min": 60, "plan": [{"difficulty": "Asan", "count": 3}]}


def test_publication_fills_a_new_exam_s_defaults_and_an_exam_already_set_keeps_its_plan(world):
    t, cid = world["teacher"], exam_course(world, "SR-102")
    body = {**EXAM, "day": store.now().date().isoformat()}
    assert t.get(f"/api/courses/{cid}/exam-defaults").json == {"defaults": None}, "no published syllabus, no defaults"
    assert t.post(f"/api/courses/{cid}/exams", body).status == 400, "no title and nothing to take it from"
    old = t.post(f"/api/courses/{cid}/exams", {**body, "title": "Aralıq imtahan"})
    assert old.status == 200, old.text
    publish(world, cid, data())
    d = t.get(f"/api/courses/{cid}/exam-defaults").json["defaults"]
    assert d["title"] == "Yekun imtahan" and d["weight"] == 50 and [o["id"] for o in d["outcomes"]] == ["N1"], d
    new = t.post(f"/api/courses/{cid}/exams", body)
    assert new.status == 200 and new.json["title"] == "Yekun imtahan", new.text
    kept = t.get(f"/api/exams/{old.json['id']}/manage").json["exam"]
    assert kept["title"] == "Aralıq imtahan" and kept["plan"] == [{"difficulty": "Asan", "topic": None, "count": 3}], kept
    own = t.post(f"/api/courses/{cid}/exams", {**body, "title": "Öz adım"})
    assert own.status == 200 and own.json["title"] == "Öz adım", "MUT-S15: a title the teacher writes is not the syllabus's"
    assert world["student"].get(f"/api/courses/{cid}/exam-defaults").status == 403


def test_exam_defaults_are_read_only_by_the_course_s_staff(world):
    """MUT-S16: a teacher reads the exam defaults of a course they manage only: another teacher's published course is 404."""
    cid = course("SR-103", "Başqasının imtahanı", world["term"]["id"], other_teacher(world), world["dep"]["id"])
    version(cid, "published")
    r = world["teacher"].get(f"/api/courses/{cid}/exam-defaults")
    assert r.status == 404, r.text


def test_an_exam_takes_a_two_letter_exam_component_s_name_as_its_title(world):
    """F4: the syllabus allows a component name of 2 letters; an exam without a title takes it and is not refused."""
    t, cid = world["teacher"], exam_course(world, "SR-104")
    d = data()
    d["assessment"][2]["name"] = "Ək"
    publish(world, cid, d)
    assert t.get(f"/api/courses/{cid}/exam-defaults").json["defaults"]["title"] == "Ək"
    r = t.post(f"/api/courses/{cid}/exams", {**EXAM, "day": store.now().date().isoformat(), "title": ""})
    assert r.status == 200 and r.json["title"] == "Ək", r.text
    short = t.post(f"/api/courses/{cid}/exams", {**EXAM, "day": store.now().date().isoformat(), "title": "Ə"})
    assert short.status == 400 and short.json["error"] == "İmtahanın adı 2–200 simvol olmalıdır", short.text


# ---------------------------------------------------------------- 2. prerequisites from the registry
def test_prerequisites_are_registry_courses_kept_by_code_and_an_old_text_stays_readable(world):
    t, cid = world["teacher"], world["course"]
    riy = q("SELECT code, name FROM courses WHERE code='RİY-1101'")[0]
    run("UPDATE courses SET prereq=? WHERE id=?", (f"{riy['name']}, Məktəb fizikası", cid))
    draft = t.post(f"/api/syllabi/{cid}/draft").json["data"]
    assert draft["prerequisites"] == [{"code": riy["code"], "name": riy["name"]}, "Məktəb fizikası"], "the course field, matched by name"
    for bad, why in (([{"code": "YOX-0000"}], "Prerekvizit fənn reyestrdə tapılmadı: YOX-0000"),
                     ([{"code": "SR-101"}], "Fənn özünün prerekviziti ola bilməz"), ([{"code": ""}], "Prerekvizit fənnin kodu düzgün deyil")):
        r = t.put(f"/api/syllabi/{cid}", {"data": data(prerequisites=bad)})
        assert r.status == 400 and r.json["error"] == why, r.text
    world["admin"].post(f"/api/directory/courses/{cid}/enrollments", {"user_id": world["student"].user["id"]})
    publish(world, cid, data(prerequisites=[{"code": riy["code"], "name": "Başqa ad"}, "Məktəb fizikası"]))
    stored = json.loads(q("SELECT data FROM syllabus_versions WHERE course_id=? ORDER BY version DESC LIMIT 1", (cid,))[0]["data"])
    assert stored["prerequisites"] == [{"code": riy["code"]}, "Məktəb fizikası"], "by code only: the name is the registry's"
    st = t.get(f"/api/syllabi/{cid}").json
    assert st["latest"]["data"]["prerequisites"][0] == {"code": riy["code"], "name": riy["name"]}
    shown = f"{riy['code']} · {riy['name']}, Məktəb fizikası"
    assert shown in t.get(f"/syllabus/{cid}").text, "the print view"
    assert shown in world["student"].get(f"/syllabus/{cid}").text, "the student's view of the published syllabus"


# ---------------------------------------------------------------- 3. a copy of another course's published syllabus
def test_a_draft_copies_an_earlier_offering_or_a_course_the_teacher_teaches(world):
    t, dep = world["teacher"], world["dep"]["id"]
    me = t.user["id"]
    other = q("SELECT id FROM users WHERE role='teacher' AND id<>? ORDER BY id LIMIT 1", (me,))[0]["id"]
    old_term = run("INSERT INTO academic_terms(code,name,teaching_start,teaching_end,exam_start,exam_end,active,created_at,updated_at) "
                   "VALUES('2024-P','2024 payız','2024-09-15','2024-12-28','2025-01-05','2025-01-30',0,?,?)", (T, T))
    later = run("INSERT INTO academic_terms(code,name,teaching_start,teaching_end,exam_start,exam_end,active,created_at,updated_at) "
                "VALUES('2030-P','2030 payız','2030-09-15','2030-12-28','2031-01-05','2031-01-30',0,?,?)", (T, T))
    bloom = q("SELECT i.id FROM framework_items i JOIN frameworks f ON f.id=i.framework_id WHERE f.key='bloom' ORDER BY i.id LIMIT 1")[0]["id"]
    src = course("CP-201", "Köçürmə sınağı", old_term, other, dep)
    version(src, "published", data(outcomes=[{"id": "N1", "text": "Köhnə dövrün nəticəsi: hesablayır", "bloom": "apply"}],
                                   rules={"attendance_limit": 20, "ai_policy": "forbidden", "late_policy": "Gecikmə yoxdur", "ai_note": ""}),
            tags={"N1": [bloom]})
    mine = course("CP-301", "Öz fənnim", world["term"]["id"], me, dep)
    version(mine, "published", tags={})
    version(course("CP-201", "Köçürmə sınağı (gələcək)", later, other, dep), "published", tags={})
    version(course("CP-999", "Başqasının fənni", world["term"]["id"], other, dep), "published", tags={})
    cid = course("CP-201", "Köçürmə sınağı", world["term"]["id"], me, dep)
    for kind, hours in (("lecture", 45), ("lab", 15)):
        run("INSERT INTO teaching_units(course_id,kind,teacher_id,active,created_at,updated_at,hours,students) VALUES(?,?,?,1,?,?,?,20)",
            (cid, kind, me, T, T, hours))
    found = {x["course_id"] for x in t.get(f"/api/syllabi/{cid}/sources").json}
    refused = [x["course_id"] for x in q("SELECT id course_id FROM courses WHERE code IN ('CP-201','CP-999') AND id NOT IN (?,?)", (src, cid))]
    assert {src, mine} <= found and len(refused) == 2 and not found & set(refused), (found, refused)
    for x in refused:
        r = t.post(f"/api/syllabi/{cid}/copy", {"from": x})
        assert r.status == 400, (x, r.text)
    r = t.post(f"/api/syllabi/{cid}/copy", {"from": src})
    assert r.status == 200, r.text
    latest = r.json["latest"]
    assert latest["status"] == "draft" and latest["source"] == {"course_id": src, "code": "CP-201", "name": "Köçürmə sınağı",
                                                                 "term": "2024 payız", "version": 1}, latest
    assert r.json["versions"][0]["source"]["code"] == "CP-201", "the note of the source in the version list"
    d = latest["data"]
    assert d["outcomes"][0]["text"] == "Köhnə dövrün nəticəsi: hesablayır" and d["rules"]["late_policy"] == "Gecikmə yoxdur"
    assert d["workload"] == {"lecture": 45.0, "seminar": 0.0, "lab": 15.0, "independent": 60.0}, "hours from this course's Forma №3"
    assert q("SELECT outcome, item_id FROM outcome_items WHERE course_id=?", (cid,)) == [{"outcome": "N1", "item_id": bloom}], "tags copied"
    assert q("SELECT 1 FROM audit WHERE action='syllabus_copied' AND detail LIKE 'CP-201%'")
    assert world["registrar"].post(f"/api/syllabi/{cid}/copy", {"from": src}).status == 403
    assert t.get(f"/api/syllabi/{src}/sources").status == 404, "only the course's author copies into it"


def old_term(code, start="2023-09-15"):
    y = int(start[:4])
    return run("INSERT INTO academic_terms(code,name,teaching_start,teaching_end,exam_start,exam_end,active,created_at,updated_at) "
               "VALUES(?,?,?,?,?,?,0,?,?)", (code, code, start, f"{y}-12-28", f"{y + 1}-01-05", f"{y + 1}-01-30", T, T))


def test_a_copy_source_is_readable_to_the_author_and_brings_no_tags_the_source_did_not_publish(world):
    """SEC-8D5-1: the earlier offering a draft may be copied from is readable to the course's author (the read and the
    copy now agree); a published version without its own tags brings no tag of the source's unpublished working map; a
    course without a term has no earlier offering; another teacher's course of another code stays unreadable."""
    t, dep, me, other = world["teacher"], world["dep"]["id"], world["teacher"].user["id"], other_teacher(world)
    old = old_term("2023-SC")
    src = course("SC-501", "Mənbə sınağı", old, other, dep)
    version(src, "published", data(description="Əvvəlki semestrin sillabusu"))          # no tags: a version from before Task 24
    bloom = q("SELECT i.id FROM framework_items i JOIN frameworks f ON f.id=i.framework_id WHERE f.key='bloom' ORDER BY i.id LIMIT 1")[0]["id"]
    run("INSERT INTO outcome_items(course_id,outcome,item_id,mapped_by,mapped_at) VALUES(?,?,?,?,?)", (src, "N1", bloom, other, T))
    cid = course("SC-501", "Mənbə sınağı", world["term"]["id"], me, dep)
    shown = t.get(f"/api/courses/{src}/syllabus")
    assert shown.status == 200 and shown.json["published"]["data"]["description"] == "Əvvəlki semestrin sillabusu", shown.text
    r = t.post(f"/api/syllabi/{cid}/copy", {"from": src})
    assert r.status == 200 and r.json["latest"]["data"]["description"] == "Əvvəlki semestrin sillabusu", r.text
    assert q("SELECT outcome FROM outcome_items WHERE course_id=?", (cid,)) == [], "the source's unpublished tags"
    loose = course("SC-501", "Mənbə sınağı", None, me, dep)
    assert src not in {x["course_id"] for x in t.get(f"/api/syllabi/{loose}/sources").json}, "no term, no earlier offering"
    stranger = course("SC-502", "Başqasının fənni", old, other, dep)
    version(stranger, "published")
    assert t.get(f"/api/courses/{stranger}/syllabus").json["published"] is None


def test_the_sources_of_a_copy_are_earlier_offerings_and_never_the_course_itself(world):
    """MUT-S10, S12: another offering of the same course in the same term is not an earlier one; the course's own
    publication is not a source."""
    t, dep = world["teacher"], world["dep"]["id"]
    same = course("SC-1010", "Paralel", world["term"]["id"], other_teacher(world), dep)
    version(same, "published")
    cid = course("SC-1010", "Paralel", world["term"]["id"], t.user["id"], dep)
    version(cid, "published")
    found = {x["course_id"] for x in t.get(f"/api/syllabi/{cid}/sources").json}
    assert same not in found and cid not in found, found


def test_a_copy_lowers_the_attendance_limit_and_drops_the_course_itself_from_its_prerequisites(world):
    """MUT-S07, S09: a source's attendance limit above the university's comes down to it; a source that names this course
    as its prerequisite does not make the course its own prerequisite."""
    t, dep = world["teacher"], world["dep"]["id"]
    src = course("SC-707", "Hədd", old_term("2023-S7"), other_teacher(world), dep)
    version(src, "published", data(rules={"attendance_limit": 30, "ai_policy": "limited", "late_policy": "", "ai_note": ""}))
    cid = course("SC-707", "Hədd", world["term"]["id"], t.user["id"], dep)
    r = t.post(f"/api/syllabi/{cid}/copy", {"from": src})
    assert r.status == 200 and r.json["latest"]["data"]["rules"]["attendance_limit"] == 25, r.text
    a = course("SC-909A", "Mənim fənnim A", world["term"]["id"], t.user["id"], dep)
    version(a, "published", data(prerequisites=[{"code": "SC-909B"}]))
    b = course("SC-909B", "Mənim fənnim B", world["term"]["id"], t.user["id"], dep)
    r = t.post(f"/api/syllabi/{b}/copy", {"from": a})
    assert r.status == 200 and r.json["latest"]["data"]["prerequisites"] == [], r.text


def test_a_unit_teacher_reads_a_course_but_may_not_copy_into_it(world):
    """MUT-S14: the teacher of one of its units reads the course; the syllabus is its head's, so a copy answers 403."""
    t = world["teacher"]
    cid = course("SC-1414", "Başqasının", world["term"]["id"], other_teacher(world), world["dep"]["id"])
    run("INSERT INTO teaching_units(course_id,kind,teacher_id,active,created_at,updated_at,hours,students) VALUES(?,'lab',?,1,?,?,15,20)",
        (cid, t.user["id"], T, T))
    src = course("SC-1415", "Mənim mənbəm", world["term"]["id"], t.user["id"], world["dep"]["id"])
    version(src, "published")
    r = t.post(f"/api/syllabi/{cid}/copy", {"from": src})
    assert r.status == 403, r.text


def test_prerequisites_are_kept_once_and_the_course_s_own_name_stays_text(world):
    """MUT-S01, S05: a prerequisite named twice is kept once; the course's prerequisite field naming the course itself
    stays text, never a registry reference to itself."""
    t = world["teacher"]
    cid = course("SC-0101", "Özünə istinad fənni", world["term"]["id"], t.user["id"], world["dep"]["id"])
    run("UPDATE courses SET prereq=? WHERE id=?", ("Özünə istinad fənni", cid))
    assert t.post(f"/api/syllabi/{cid}/draft").json["data"]["prerequisites"] == ["Özünə istinad fənni"]
    riy = q("SELECT code FROM courses WHERE code='RİY-1101'")[0]["code"]
    r = t.put(f"/api/syllabi/{cid}", {"data": data(prerequisites=[{"code": riy}, {"code": riy}, "Mətn", "Mətn"])})
    assert r.status == 200 and len(r.json["latest"]["data"]["prerequisites"]) == 2, r.text


# ---------------------------------------------------------------- 4. the overview of a term
@pytest.fixture(scope="module")
def overview(world):
    term, dep = world["term"]["id"], world["dep"]["id"]
    me = world["teacher"].user["id"]
    for code, status in (("OV-1", None), ("OV-2", "draft"), ("OV-3", "submitted"), ("OV-4", "approved"), ("OV-5", "published"), ("OV-6", "returned")):
        cid = course(code, f"İcmal {code}", term, me, dep)
        if status:
            version(cid, status)
    course("OV-7", "=HYPERLINK(\"x\")", term, me, dep)
    fac = run("INSERT INTO faculties(code,name,active,created_at,updated_at) VALUES('OVF','Başqa fakültə',1,?,?)", (T, T))
    far = run("INSERT INTO departments(faculty_id,code,name,active,created_at,updated_at) VALUES(?,'OVD','Uzaq kafedra',1,?,?)", (fac, T, T))
    course("OV-X", "Başqa fakültənin fənni", term, me, far)
    return {"term": term, "far": far}


def codes(r):
    return sorted(x["code"] for x in r.json["items"])


def test_the_overview_counts_a_term_s_courses_by_the_state_of_their_syllabus(world, overview):
    reg = world["registrar"]
    r = reg.get(f"/api/syllabi/overview?term={overview['term']}&q=OV-")
    assert r.status == 200 and r.json["counts"] == {"none": 3, "draft": 2, "submitted": 1, "approved": 1, "published": 1}, r.json["counts"]
    assert codes(reg.get(f"/api/syllabi/overview?term={overview['term']}&q=ov-&state=none")) == ["OV-1", "OV-7", "OV-X"]
    assert codes(reg.get(f"/api/syllabi/overview?term={overview['term']}&q=OV-&department={overview['far']}")) == ["OV-X"]
    six = next(x for x in r.json["items"] if x["code"] == "OV-6")
    assert six["state"] == "draft" and six["status"] == "returned", "a returned version is back with its author"
    assert reg.get("/api/syllabi/overview?term=999999").status == 404


def test_the_dean_s_office_sees_its_faculty_and_leadership_every_course_read_only(world, overview):
    office = world["office"].get(f"/api/syllabi/overview?term={overview['term']}&q=OV-")
    assert office.status == 200 and "OV-X" not in codes(office) and "OV-1" in codes(office), codes(office)
    assert "OV-X" in codes(world["leader"].get(f"/api/syllabi/overview?term={overview['term']}&q=OV-"))
    for who in ("teacher", "head", "student"):
        assert world[who].get("/api/syllabi/overview").status == 403, who


def test_the_overview_csv_has_a_bom_and_no_cell_a_spreadsheet_would_run(world, overview):
    r = world["registrar"].get(f"/api/syllabi/overview?term={overview['term']}&q=OV-&format=csv")
    assert r.status == 200 and r.headers["Content-Type"].startswith("text/csv"), r.status
    text = r.body.decode("utf-8")
    assert text.startswith("﻿Kafedra,Fənnin kodu,Fənn,"), text[:80]
    assert "'=HYPERLINK" in text and "\n=HYPERLINK" not in text and ",=HYPERLINK" not in text, text
    assert "OV-X" in text and "Sillabus yoxdur" in text


def test_the_overview_counts_ignore_the_state_filter_and_a_faculty_lists_only_its_departments(world, overview):
    """MUT-S19, S22: the counts follow the department and the search, not the state filter; the dean's office's list of
    departments is its faculty's."""
    reg = world["registrar"]
    a = reg.get(f"/api/syllabi/overview?term={overview['term']}&q=OV-").json["counts"]
    assert reg.get(f"/api/syllabi/overview?term={overview['term']}&q=OV-&state=none").json["counts"] == a
    deps = world["office"].get(f"/api/syllabi/overview?term={overview['term']}").json["departments"]
    assert deps and overview["far"] not in [d["id"] for d in deps], deps


def _queue(client) -> list[dict]:
    first = client.get("/api/syllabi/queue").json
    return [i for p in range(1, first["pages"] + 1) for i in client.get(f"/api/syllabi/queue?page={p}").json["items"]]


def test_a_department_head_s_queue_holds_only_the_courses_the_grant_covers(world, overview):
    """MUT-S23: a version submitted in another faculty's department is not in the head's queue."""
    mine = version(course("SC-2323A", "Öz təqdim", world["term"]["id"], world["teacher"].user["id"], world["dep"]["id"]), "submitted")
    far = version(course("SC-2323B", "Uzaq təqdim", world["term"]["id"], world["teacher"].user["id"], overview["far"]), "submitted")
    ids = {i["id"] for i in _queue(world["head"])}
    assert mine in ids and far not in ids, ids


def test_the_queue_compares_with_the_latest_publication(world):
    """MUT-S26: an older publication keeps its status; the queue compares with the latest one."""
    cid = course("SC-2626", "İki dərc", world["term"]["id"], world["teacher"].user["id"], world["dep"]["id"])
    version(cid, "published", data(description="bir"), version=1)
    v2 = version(cid, "published", data(description="iki"), version=2)
    v3 = version(cid, "approved", data(description="iki"), version=3)
    x = next(i for i in _queue(world["registrar"]) if i["id"] == v3)
    assert x["published_id"] == v2 and x["changes"] == 0, x


# ---------------------------------------------------------------- 5. the approval queue pages, a constant number of queries (AR-11)
def test_the_queue_pages_and_reads_the_same_queries_for_a_page_of_50_as_for_a_short_one(world, monkeypatch):
    reg, term, dep = world["registrar"], world["term"]["id"], world["dep"]["id"]
    me = world["teacher"].user["id"]
    for k in range(60):
        cid = course(f"QQ-{k}", f"Növbə {k}", term, me, dep)
        version(cid, "published", version=1)
        version(cid, "returned", version=2)
        version(cid, "approved", data(description=f"Dəyişiklik {k}"), version=3)
    first = reg.get("/api/syllabi/queue")
    assert first.status == 200 and len(first.json["items"]) == 50 and first.json["pages"] >= 2, first.json["total"]
    x = next(i for i in first.json["items"] if i["code"] == "QQ-0")
    assert x["changes"] == 1 and x["returned_version"] == 2 and x["changes_returned"] == 1 and x["actions"] == ["publish", "return"], x
    last = reg.get(f"/api/syllabi/queue?page={first.json['pages']}").json
    assert 0 < len(last["items"]) < 50 and not {i["id"] for i in last["items"]} & {i["id"] for i in first.json["items"]}

    ran: list[str] = []
    connect = store.connect

    def traced():
        c = connect()
        c.set_trace_callback(ran.append)
        return c
    monkeypatch.setattr(store, "connect", traced)
    monkeypatch.setattr(common, "_TX_GUARD", False)              # its own trace callback would replace this one
    counts = []
    for page in (1, last["page"], 1):
        ran.clear()
        assert reg.get(f"/api/syllabi/queue?page={page}").status == 200
        counts.append(len([s for s in ran if "syllabus_versions" in s or "teaching_units" in s or "courses" in s]))
    assert counts[0] and counts[0] == counts[1] == counts[2], f"a query per row (AR-11): {counts}"
