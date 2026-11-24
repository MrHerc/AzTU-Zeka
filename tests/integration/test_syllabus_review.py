"""The syllabus approval as the demo shows it (the acceptance walk and the audit of 2026-11-23): the demo's department
head and academic office sign in from the login page, the demo courses carry Forma №3 hours, the approver sees the
version's frozen tags and warnings, a resubmission is compared with the returned version, one odd literature title does
not break the queue, and a ticked permission without a reason says so. Each test builds the versions it needs with the
helpers below (audit SYL-T8: three tests failed alone or in reverse order), all on ELM-2105."""
import pytest

from zeka.legacy import store


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


@pytest.fixture(scope="module")
def walk(app_db):
    teacher, head, office = app_db.client("teacher"), app_db.client("dept_head"), app_db.client("academic_office")
    cid = q("SELECT id FROM courses WHERE code='ELM-2105'")[0]["id"]
    return {"teacher": teacher, "head": head, "office": office, "course": cid}


def save(w, change=None):
    t, cid = w["teacher"], w["course"]
    st = t.get(f"/api/syllabi/{cid}").json
    d = st["latest"]["data"] if st["latest"] else t.post(f"/api/syllabi/{cid}/draft").json["data"]
    d["outcomes"] = [{"id": "N1", "text": "Dövrəni təhlil edir və hesablayır", "bloom": "analyze"},
                     {"id": "N2", "text": "Keçid proseslərini izah edir", "bloom": "understand"}]
    d["plan"] = [{"week": 1, "topic": "Giriş mövzusu", "outcomes": ["N1"], "activity": "Mühazirə və məsələ həlli"}]
    for a in d["assessment"]:                          # the draft's exam assesses the draft's own outcomes (F7)
        a["outcomes"] = []
    if change:
        change(d)
    r = t.put(f"/api/syllabi/{cid}", {"data": d})
    assert r.status == 200, r.text
    return r.json["latest"]["id"]


def step(client, w, vid, action, **body):
    return client.post(f"/api/syllabi/{w['course']}/versions/{vid}/{action}", body)


def submitted(w, change=None):
    vid = save(w, change)
    assert step(w["teacher"], w, vid, "submit").status == 200
    return vid


def returned(w, note, change=None):
    vid = submitted(w, change)
    assert step(w["head"], w, vid, "return", note=note).status == 200
    return vid


def approved(w, change=None):
    vid = submitted(w, change)
    assert step(w["head"], w, vid, "approve").status == 200
    return vid


def published(w):
    vid = approved(w)
    assert step(w["office"], w, vid, "publish", override=True, note="Qiymət sxemi dəyişmir").status == 200
    return vid


def queued(w, vid):
    return next(x for x in w["head"].get("/api/syllabi/queue").json["items"] if x["id"] == vid)


def lab(hours):
    return lambda d: d["workload"].update(lab=hours)


def test_the_demo_department_head_and_academic_office_sign_in_and_reach_the_queue(app_db, walk):
    # walk D1: no demo role could reach the department head's or the academic office's step
    assert walk["head"].user["role"] == "dept_head" and walk["office"].user["role"] == "academic_office"
    for who in ("head", "office"):
        assert walk[who].get("/api/syllabi/queue").status == 200
    dep = q("SELECT department_id FROM courses WHERE code='ELM-2105'")[0]["department_id"]
    assert dep and q("SELECT scope_type, scope_id FROM role_grants WHERE user_id=? AND role='dept_head'",
                     (walk["head"].user["id"],)) == [{"scope_type": "department", "scope_id": dep}]


def test_the_demo_courses_have_forma3_hours_so_a_draft_is_prefilled_and_a_change_is_a_difference(walk):
    # walk gap: the seed's teaching units had no hours, so neither the prefill nor the head's Forma №3 diff showed
    t, cid = walk["teacher"], walk["course"]
    st = t.get(f"/api/syllabi/{cid}").json
    assert st["imported"] == {"lecture": 30.0, "seminar": 30.0, "lab": 30.0}
    d = t.post(f"/api/syllabi/{cid}/draft").json["data"]
    assert {k: d["workload"][k] for k in ("lecture", "seminar", "lab")} == st["imported"]
    vid = save(walk, lambda d: d["workload"].update(lab=24))
    assert step(t, walk, vid, "submit").status == 200
    mine = next(x for x in walk["head"].get("/api/syllabi/queue").json["items"] if x["id"] == vid)
    assert mine["forma3"] == [{"kind": "lab", "imported": 30.0, "syllabus": 24.0}]
    assert step(walk["head"], walk, vid, "return", note="Laboratoriya saatlarını Forma №3-ə uyğunlaşdırın").status == 200


def test_a_resubmission_is_compared_with_the_returned_version(walk):
    # walk D5: the queue said «ilk dərc» and listed no change, though the head had returned the earlier version
    back = returned(walk, "Laboratoriya saatlarını Forma №3-ə uyğunlaşdırın", lab(24))
    vid = submitted(walk, lab(30))
    mine = queued(walk, vid)
    assert mine["returned_id"] == back and mine["returned_note"] == "Laboratoriya saatlarını Forma №3-ə uyğunlaşdırın"
    diff = walk["head"].get(f"/api/syllabi/{walk['course']}/diff?a={back}&b={vid}").json
    assert mine["changes_returned"] == len(diff) == 1 and diff[0]["section"] == "workload"
    assert step(walk["head"], walk, vid, "return", note="Yenə baxın").status == 200


def test_after_two_returns_a_resubmission_answers_the_later_one(walk):
    # audit SYL-T2 (mutant M22, ORDER BY version ASC): with one return in the walk the order was never seen
    returned(walk, "Birinci qeyd: laboratoriya", lab(24))
    second = returned(walk, "İkinci qeyd: məşğələ", lab(26))
    mine = queued(walk, submitted(walk, lab(30)))
    assert (mine["returned_id"], mine["returned_note"]) == (second, "İkinci qeyd: məşğələ")


def test_a_return_answered_by_an_approval_or_a_publication_is_not_compared_again(walk):
    # F3: v5, submitted after v4's publication, was compared with v3, returned before it, and showed v3's old note
    returned(walk, "Ədəbiyyatı tamamlayın", lab(24))
    approved(walk, lab(30))
    after_approval = queued(walk, submitted(walk, lab(28)))
    published(walk)
    after_publication = queued(walk, submitted(walk, lab(26)))
    for mine in (after_approval, after_publication):
        assert (mine["returned_id"], mine["returned_version"], mine["returned_note"], mine["changes_returned"]) == (None, None, None, None), mine
    assert after_publication["changes"] == 1


def test_the_reviewer_reads_the_frozen_tags_and_the_warnings(walk):
    # walk D4: the reviewer's window had no framework tags; plus the Bloom and alignment warnings (no block)
    t, cid = walk["teacher"], walk["course"]
    vid = save(walk)
    bloom = t.get("/api/frameworks").json
    fid = next(f["id"] for f in bloom if f["key"] == "bloom")
    items = t.get(f"/api/frameworks/{fid}/items?size=10").json["items"]
    assert [x["code"] for x in items] == ["remember", "understand", "apply", "analyze", "evaluate", "create"], "D6: by level"
    evaluate = next(x["id"] for x in items if x["code"] == "evaluate")
    assert t.put(f"/api/syllabi/{cid}/outcomes/N1/items", {"items": [evaluate]}).status == 200
    st = t.get(f"/api/syllabi/{cid}").json
    assert st["checks"] == {"untaught": ["N2"], "unassessed": ["N1", "N2"], "bloom": [{"outcome": "N1", "level": "analyze", "tags": ["evaluate"]}]}
    assert step(t, walk, vid, "submit").status == 200
    assert t.put(f"/api/syllabi/{cid}/outcomes/N1/items", {"items": []}).status == 200       # a later map change is not the version's
    v = walk["head"].get(f"/api/syllabi/{cid}/versions/{vid}", lang="en").json
    assert [x["code"] for x in v["tags"]["N1"]] == ["evaluate"] and v["tags"]["N1"][0]["title"] == "Evaluate"
    assert v["checks"]["bloom"] == [{"outcome": "N1", "level": "analyze", "tags": ["evaluate"]}]
    r = step(walk["head"], walk, vid, "approve")
    assert r.status == 200, "a warning never blocks"


def test_a_ticked_permission_without_a_reason_says_what_is_missing(walk):
    # walk D7: the same long message came back whether the box was ticked or not
    vid = approved(walk)
    r = step(walk["office"], walk, vid, "publish", override=True, note=" ")
    assert r.status == 409 and r.json["error"] == "Xüsusi icazənin səbəbini şərhdə yazın"
    assert "xüsusi icazəsi" in step(walk["office"], walk, vid, "publish").json["error"]
    # audit SYL-T6: only a ticked box (true, not a truthy "yes") asks for the reason alone (M23); three letters are a reason (M24)
    assert "xüsusi icazəsi" in step(walk["office"], walk, vid, "publish", override="yes").json["error"]
    assert step(walk["office"], walk, vid, "publish", override=True, note="abc").status == 200


def test_a_literature_title_of_superscript_digits_does_not_break_the_queue(walk):
    # audit SYL-D1: int('²³⁴') raised in the diff and the head's whole queue answered 400; the diff runs against a publication
    published(walk)
    vid = submitted(walk, lambda d: d.update(literature=[{"title": "²³⁴", "kind": "main"}]))
    r = walk["head"].get("/api/syllabi/queue")
    assert r.status == 200 and any(x["id"] == vid and x["changes"] is not None for x in r.json["items"]), r.text
    dup = walk["teacher"].put(f"/api/syllabi/{walk['course']}", {"data": {**walk["teacher"].get(f"/api/syllabi/{walk['course']}").json["latest"]["data"],
                                                                         "literature": [{"title": "Kitab", "kind": "main"}, {"title": "Kitab", "kind": "extra"}]}})
    assert dup.status == 400 and dup.json["error"] == "Ədəbiyyat siyahısında eyni adlı iki mənbə ola bilməz", "audit SYL-D2"


def test_a_units_hours_count_its_weekly_slots(walk):
    # audit SYL-T5 (mutant M20): ELM-2105 has one slot of each kind; İNG-1105 has two «Məşğələ» slots: 2 × 15 × 2
    assert q("SELECT u.hours FROM teaching_units u JOIN courses c ON c.id=u.course_id WHERE c.code='İNG-1105'") == [{"hours": 60}]


def test_every_seeded_teacher_belongs_to_the_department_of_its_dept(walk):
    # F10: the 18 synthetic teachers were inserted after the departments were bound, so their department_id stayed empty
    assert q("SELECT username FROM users WHERE dept IS NOT NULL AND department_id IS NULL") == []
    assert q("SELECT COUNT(*) n FROM users u JOIN departments d ON d.id=u.department_id WHERE u.dept='Elektronika' AND u.synthetic=1")[0]["n"] == 3


def test_the_demo_department_head_sees_its_programme_in_the_coverage_report(walk):
    # F6: the demo specialty had no department, so the department head's coverage page said «Sizə aid ixtisas yoxdur»
    assert [p["code"] for p in walk["head"].get("/api/frameworks/programmes").json] == ["KM-050616"]


def test_the_printed_and_published_syllabus_shows_what_each_component_assesses(app_db, walk):
    # F8: the reviewer approved «Sərbəst iş → N1, N2», but /syllabus/{id} listed only a component's name, kind and weight
    def assess(d):
        for a in d["assessment"]:
            a["outcomes"] = ["N1", "N2"] if a["kind"] == "exam" else ["N2"] if a["kind"] == "component" else []
    vid = approved(walk, assess)
    assert step(walk["office"], walk, vid, "publish", override=True, note="Qiymət sxemi dəyişmir").status == 200
    cid = walk["course"]
    for page in (app_db.client("student").get(f"/syllabus/{cid}").text, walk["head"].get(f"/syllabus/{cid}?v={vid}").text):
        table = page.split("<h3>Qiymətləndirmə</h3>", 1)[1].split("</table>", 1)[0]
        assert "<th>Nəticələr</th>" in table and "<td>N1, N2</td>" in table and "<td>N2</td>" in table, table
