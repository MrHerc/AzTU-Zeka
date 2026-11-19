"""The course forum (tasks/todo.md, Task 33): who reads, anonymity, the teacher-only AI draft, the FAQ the tutor cites,
reports and moderation, and the old ask-the-teacher path landing in the forum."""
import pytest

from zeka.legacy import store


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


@pytest.fixture(scope="module")
def forum(app_db):
    admin = app_db.client("admin")
    cid = q("SELECT id FROM courses WHERE code='ELM-2105'")[0]["id"]
    gid = q("SELECT group_id FROM users WHERE username='aysel'")[0]["group_id"]
    ids = {}
    for name in ("qa.peer", "qa.out"):
        ids[name] = admin.post("/api/directory/users", {"username": name, "full_name": f"Sınaq {name}", "role": "student", "group_id": gid,
                                                        "student_no": name.upper()}).json["id"]
    assert admin.post(f"/api/directory/courses/{cid}/enrollments", {"user_id": ids["qa.peer"]}).status == 200

    def student(name):
        s = app_db.client()
        assert s.post("/api/auth/demo", {"role": "student", "user": name}).status == 200
        return s
    return {"course": cid, "author": app_db.client("student"), "peer": student("qa.peer"), "outsider": student("qa.out"),
            "teacher": app_db.client("teacher"), "office": app_db.client("office"), "admin": admin}


def new_topic(f, anonymous=False, title="Kirxhof qanununda işarə qaydası"):
    r = f["author"].post(f"/api/courses/{f['course']}/qa", {"title": title, "text": "Dövrədə EHQ-nin işarəsini necə seçirik? Nəticəm mənfi çıxır.",
                                                            "tag": "3-cü həftə", "anonymous": anonymous})
    assert r.status == 200, r.text
    return r.json


def test_only_the_course_s_students_and_teacher_read_its_topics(forum):
    t = new_topic(forum)
    cid = forum["course"]
    for who in ("author", "peer", "teacher"):
        assert forum[who].get(f"/api/courses/{cid}/qa").status == 200, who
        assert forum[who].get(f"/api/qa/topics/{t['id']}").status == 200, who
    assert forum["outsider"].get(f"/api/courses/{cid}/qa").status == 404
    assert forum["outsider"].get(f"/api/qa/topics/{t['id']}").status == 404
    assert forum["outsider"].post(f"/api/qa/topics/{t['id']}/replies", {"text": "Mən də bilmirəm"}).status == 404
    assert forum["outsider"].post("/api/qa/reports", {"topic_id": t["id"], "reason": "spam"}).status == 404
    for who in ("office", "admin"):
        assert forum[who].get(f"/api/courses/{cid}/qa").status == 403, who
        assert forum[who].get(f"/api/qa/topics/{t['id']}").status == 403, who


def test_an_anonymous_author_is_hidden_from_students_and_shown_to_the_teacher_and_moderators(forum):
    t = new_topic(forum, anonymous=True, title="Anonim sual: paralel müqavimətlər")
    peer = forum["peer"].get(f"/api/qa/topics/{t['id']}").json
    assert peer["author"] == "Anonim tələbə" and peer["mine"] is False and "student_id" not in peer
    listed = next(x for x in forum["peer"].get(f"/api/courses/{forum['course']}/qa").json if x["id"] == t["id"])
    assert listed["author"] == "Anonim tələbə"
    real = forum["author"].user["full_name"]
    assert forum["author"].get(f"/api/qa/topics/{t['id']}").json["mine"] is True
    assert forum["teacher"].get(f"/api/qa/topics/{t['id']}").json["author"] == real
    assert forum["peer"].post("/api/qa/reports", {"topic_id": t["id"], "reason": "Mövzu fənnə aid deyil"}).status == 200
    queued = next(x for x in forum["office"].get("/api/qa/reports").json if x["topic_id"] == t["id"])
    assert queued["topic_author"] == real and queued["anonymous"] == 1


def test_the_ai_draft_is_the_teacher_s_until_published_and_a_faq_answer_is_cited_by_the_tutor(forum):
    t = new_topic(forum, title="Kirxhofun ikinci qanunu necə tətbiq olunur")
    teacher, student = forum["teacher"], forum["peer"]
    assert student.post(f"/api/qa/topics/{t['id']}/draft").status == 403
    d = teacher.post(f"/api/qa/topics/{t['id']}/draft").json
    assert d["ai_draft"] and "Kirxhof" in d["ai_draft"]
    assert "ai_draft" not in student.get(f"/api/qa/topics/{t['id']}").json
    assert d["ai_draft"] not in str(student.get(f"/api/courses/{forum['course']}/qa").json)
    assert teacher.get(f"/api/qa/topics/{t['id']}").json["ai_draft"] == d["ai_draft"]
    assert teacher.post(f"/api/qa/topics/{t['id']}/faq", {"on": True}).status == 400, "no accepted answer yet"
    answer = "Qapalı konturda EHQ-lərin cəmi gərginlik düşgülərinin cəmidir; konturu bir istiqamətdə gəzib işarələri ona görə seçin."
    after = teacher.post(f"/api/qa/topics/{t['id']}/replies", {"text": answer}).json
    rid = next(r["id"] for r in after["replies"] if r["text"] == answer)
    assert student.post(f"/api/qa/replies/{rid}/accept").status == 403
    shown = teacher.post(f"/api/qa/replies/{rid}/accept").json
    assert shown["status"] == "answered" and [r["accepted"] for r in shown["replies"] if r["id"] == rid] == [1]
    assert student.get(f"/api/qa/topics/{t['id']}").json["replies"][0]["text"] == answer
    assert teacher.post(f"/api/qa/topics/{t['id']}/faq", {"on": True}).json["faq"] is True
    ask = student.post(f"/api/tutor/{forum['course']}/ask", {"message": "Kirxhofun ikinci qanununda EHQ-lərin işarəsini necə seçirik?",
                                                             "mode": "explain"}).json["answer"]
    assert any(c["material"] == "Fənnin FAQ-ı" for c in ask["cites"]), ask["cites"]
    assert teacher.post(f"/api/qa/topics/{t['id']}/faq", {"on": False}).json["faq"] is False
    assert not q("SELECT 1 FROM chunks WHERE heading=? AND material_id IN (SELECT id FROM materials WHERE filename='qa-faq.md')", (t["title"],))
    assert teacher.post(f"/api/qa/topics/{t['id']}/faq", {"on": "yes"}).status == 400


def test_a_reported_reply_reaches_the_moderators_and_hiding_it_is_audited(forum):
    t = new_topic(forum, title="Laboratoriya işinin hesabatı nə vaxt təhvil verilir")
    bad = forum["peer"].post(f"/api/qa/topics/{t['id']}/replies", {"text": "Cavabları mənə yazın, pulla verirəm"}).json
    rid = bad["replies"][-1]["id"]
    assert forum["author"].post("/api/qa/reports", {"topic_id": t["id"], "reply_id": rid, "reason": "Akademik dürüstlüyə ziddir"}).status == 200
    assert forum["author"].post("/api/qa/reports", {"topic_id": t["id"], "reply_id": rid, "reason": "x"}).status == 400
    other = new_topic(forum, title="Başqa mövzu, başqa cavab")
    assert forum["author"].post("/api/qa/reports", {"topic_id": other["id"], "reply_id": rid, "reason": "uyğun deyil"}).status == 404
    assert forum["peer"].get("/api/qa/reports").status == 403 and forum["teacher"].get("/api/qa/reports").status == 403
    report = next(x for x in forum["office"].get("/api/qa/reports").json if x["reply_id"] == rid)
    assert report["reply_text"].startswith("Cavabları") and report["reply_author"] == "Sınaq qa.peer"
    assert forum["office"].post(f"/api/qa/reports/{report['id']}/resolve", {"action": "delete"}).status == 400
    assert forum["office"].post(f"/api/qa/reports/{report['id']}/resolve", {"action": "hide"}).status == 200
    assert forum["office"].post(f"/api/qa/reports/{report['id']}/resolve", {"action": "hide"}).status == 404, "resolved once"
    assert all(r["id"] != rid for r in forum["peer"].get(f"/api/qa/topics/{t['id']}").json["replies"])
    assert [r["hidden"] for r in forum["teacher"].get(f"/api/qa/topics/{t['id']}").json["replies"] if r["id"] == rid] == [1]
    assert q("SELECT 1 FROM audit WHERE action='qa_moderate' AND detail LIKE ?", (f"#{report['id']} hide%",))
    assert q("SELECT 1 FROM audit WHERE action='qa_report' AND detail LIKE ?", (f"#{t['id']} reply #{rid}",))


def test_bad_input_is_a_400_and_the_old_ask_the_teacher_path_lands_in_the_forum(forum):
    cid = forum["course"]
    assert forum["author"].post(f"/api/courses/{cid}/qa", {"title": "Ab", "text": "Bu sual kifayət qədər uzundur"}).status == 400
    assert forum["author"].post(f"/api/courses/{cid}/qa", {"title": "Normal başlıq", "text": "qısa"}).status == 400
    assert forum["author"].post(f"/api/courses/{cid}/qa", {"title": ["x"], "text": "Bu sual kifayət qədər uzundur"}).status == 400
    t = new_topic(forum, title="Cavab yoxlaması")
    assert forum["peer"].post(f"/api/qa/topics/{t['id']}/replies", {"text": ""}).status == 400
    assert forum["author"].post(f"/api/tutor/{cid}/forward", {"question": "Tutor bu məsələni izah edə bilmədi, kömək edin", "anonymous": True}).status == 200
    topic = next(x for x in forum["teacher"].get(f"/api/courses/{cid}/qa").json if x["title"].startswith("Tutor bu məsələni"))
    assert topic["anonymous"] is True and topic["author"] == "Anonim tələbə", "the tutor promises the teacher will not see the name"
    assert forum["teacher"].post(f"/api/teacher/questions/{topic['id']}/answer", {"answer": "Materialın 2-ci bölməsinə baxın."}).status == 200
    got = forum["author"].get(f"/api/qa/topics/{topic['id']}").json
    assert got["status"] == "answered" and got["replies"][-1]["accepted"] == 1 and got["replies"][-1]["by_teacher"] is True


# ---------------------------------------------------------------- Checkpoint E (area A)
def forward(f, text, **extra):
    assert f["author"].post(f"/api/tutor/{f['course']}/forward", {"question": text, **extra}).status == 200
    return q("SELECT id FROM teacher_questions WHERE question=? ORDER BY id DESC LIMIT 1", (text,))[0]["id"]


def test_a_question_forwarded_from_the_tutor_stays_between_its_author_and_the_teacher(forum):
    """SEC-E1 / SEC-E3: a forward was the teacher's alone before the forum; classmates never read it, and an anonymous
    one hides the name from the teacher too."""
    cid = forum["course"]
    anon = forward(forum, "Şəxsi sual: imtahana qədər bu mövzunu çatdıra bilmirəm", anonymous=True, context="tutor söhbəti")
    named = forward(forum, "Laboratoriya işini xəstəliyə görə buraxdım, nə edim?")      # through the API without a context
    for tid in (anon, named):
        assert all(x["id"] != tid for x in forum["peer"].get(f"/api/courses/{cid}/qa").json)
        assert forum["peer"].get(f"/api/qa/topics/{tid}").status == 404
        assert forum["peer"].post(f"/api/qa/topics/{tid}/replies", {"text": "Mən də"}).status == 404
        assert forum["peer"].post("/api/qa/reports", {"topic_id": tid, "reason": "uyğun deyil"}).status == 404
        mine = forum["author"].get(f"/api/qa/topics/{tid}").json
        assert mine["private"] is True and mine["mine"] is True
    listed = {x["id"]: x for x in forum["teacher"].get(f"/api/courses/{cid}/qa").json}
    assert listed[anon]["author"] == "Anonim tələbə" and listed[anon]["private"] is True
    assert listed[named]["author"] == forum["author"].user["full_name"]
    assert forum["teacher"].get(f"/api/qa/topics/{anon}").json["author"] == "Anonim tələbə"
    assert q("SELECT private FROM teacher_questions WHERE context='AI tutor söhbətindən göndərilib'") == [{"private": 1}] * 3, "seeded forwards"


def test_the_anonymous_author_s_own_reply_does_not_name_them(forum):
    """SEC-E2: the topic said "Anonim tələbə" and the author's reply under it said their name."""
    t = new_topic(forum, anonymous=True, title="Anonim: öz cavabım da anonim qalsın")
    forum["author"].post(f"/api/qa/topics/{t['id']}/replies", {"text": "Özüm tapdım: işarə konturun istiqamətindən asılıdır."})
    forum["peer"].post(f"/api/qa/topics/{t['id']}/replies", {"text": "Mənim adım görünsün."})
    seen = forum["peer"].get(f"/api/qa/topics/{t['id']}").json["replies"]
    assert [(r["author"], r["anonymous"]) for r in seen] == [("Anonim tələbə", True), ("Sınaq qa.peer", False)]
    assert forum["author"].user["full_name"] not in str(forum["peer"].get(f"/api/qa/topics/{t['id']}").json)
    by_teacher = forum["teacher"].get(f"/api/qa/topics/{t['id']}").json["replies"]
    assert by_teacher[0]["author"] == forum["author"].user["full_name"], "a forum topic's teacher sees the author (Task 33)"


def faq_topic(f, title):
    t = new_topic(f, title=title)
    rid = f["teacher"].post(f"/api/qa/topics/{t['id']}/replies", {"text": "Konturu bir istiqamətdə gəzin, EHQ-ni ona görə yazın."}).json["replies"][-1]["id"]
    assert f["teacher"].post(f"/api/qa/replies/{rid}/accept").status == 200
    assert f["teacher"].post(f"/api/qa/topics/{t['id']}/faq", {"on": True}).json["faq"] is True
    return t


def faq_material():
    got = q("SELECT id, title FROM materials WHERE filename='qa-faq.md' AND course_id=(SELECT id FROM courses WHERE code='ELM-2105')")
    return got[0] if got else None


def test_deleting_the_faq_material_takes_its_topics_out_of_the_faq_and_nothing_recreates_it_empty(forum):
    """CR-E6: after the delete the topic still said FAQ and turning FAQ off made a material with no title."""
    t = faq_topic(forum, "FAQ materialı silinəndə nə olur")
    assert forum["teacher"].delete(f"/api/materials/{faq_material()['id']}").status == 200
    assert forum["teacher"].get(f"/api/qa/topics/{t['id']}").json["faq"] is False
    assert forum["teacher"].post(f"/api/qa/topics/{t['id']}/faq", {"on": True}).json["faq"] is True, "it can go back"
    assert faq_material()["title"] == "Fənnin FAQ-ı"
    c = store.connect()                                       # a flag left from before this fix: its section is gone
    try:
        c.execute("UPDATE teacher_questions SET faq_chunk_id=987654321 WHERE id=?", (t["id"],))
        store.delete_material(c, faq_material()["id"])
        c.execute("UPDATE teacher_questions SET faq_chunk_id=987654321 WHERE id=?", (t["id"],))
        c.commit()
    finally:
        c.close()
    assert forum["teacher"].post(f"/api/qa/topics/{t['id']}/faq", {"on": False}).json["faq"] is False
    assert faq_material() is None, "turning FAQ off never creates the material"


def test_the_old_answer_route_moves_the_faq_with_the_new_answer(forum):
    """CR-E7: the accepted reply changed, the FAQ section kept the old answer."""
    t = faq_topic(forum, "Köhnə səhifədən verilən cavab FAQ-a düşür")
    assert forum["teacher"].post(f"/api/teacher/questions/{t['id']}/answer", {"answer": "Yeni cavab: Kirxhofun ikinci qanunu."}).status == 200
    text = q("SELECT text FROM chunks WHERE id=(SELECT faq_chunk_id FROM teacher_questions WHERE id=?)", (t["id"],))[0]["text"]
    assert text.endswith("Yeni cavab: Kirxhofun ikinci qanunu.")
    assert forum["teacher"].post("/api/teacher/questions/99999999/answer", {"answer": "x"}).status == 404


def test_only_a_teacher_s_answer_reaches_the_faq_the_tutor_cites(forum):
    """TM-E5: an accepted student reply became the course FAQ the tutor cites as the course's own."""
    t = new_topic(forum, title="Tələbə cavabı FAQ-a keçməməlidir")
    rid = forum["peer"].post(f"/api/qa/topics/{t['id']}/replies", {"text": "Mənim cavabım: işarəni təsadüfi seçin."}).json["replies"][-1]["id"]
    assert forum["teacher"].post(f"/api/qa/replies/{rid}/accept").status == 200
    r = forum["teacher"].post(f"/api/qa/topics/{t['id']}/faq", {"on": True})
    assert r.status == 400 and "müəllimin" in r.json["error"]
    t2 = faq_topic(forum, "FAQ-dakı cavab tələbə cavabı ilə əvəzlənir")
    peer = forum["peer"].post(f"/api/qa/topics/{t2['id']}/replies", {"text": "Başqa cavab: ehtimal ki, belədir."}).json["replies"][-1]["id"]
    assert forum["teacher"].post(f"/api/qa/replies/{peer}/accept").json["faq"] is False, "the FAQ leaves with the teacher's answer"


def test_a_draft_without_a_source_is_not_saved(forum):
    """SF-E6: the tutor's refusal was saved as the teacher's AI draft."""
    t = new_topic(forum, title="Qwzxv plmkjh trrsdv vbnmxq")
    c = store.connect()
    try:
        c.execute("UPDATE teacher_questions SET question='Qwzxv plmkjh trrsdv vbnmxq zzyqw' WHERE id=?", (t["id"],))
        c.commit()
    finally:
        c.close()
    d = forum["teacher"].post(f"/api/qa/topics/{t['id']}/draft").json
    assert d == {"ai_draft": None, "no_source": True}
    assert q("SELECT ai_draft FROM teacher_questions WHERE id=?", (t["id"],)) == [{"ai_draft": None}]


def test_a_dean_s_office_moderates_only_its_faculty_s_forum(forum):
    """TM-E13: an office of another faculty saw an anonymous author's real name in the queue and could resolve it."""
    t = new_topic(forum, title="Başqa fakültənin dekanlığı görməməlidir")
    assert forum["peer"].post("/api/qa/reports", {"topic_id": t["id"], "reason": "mövzudan kənar"}).status == 200
    pid = next(r["id"] for r in forum["office"].get("/api/qa/reports").json if r["topic_id"] == t["id"])
    office = forum["office"].user["id"]
    mine = q("SELECT scope_id FROM role_grants WHERE user_id=? AND role='office' AND scope_type='faculty'", (office,))[0]["scope_id"]
    c = store.connect()
    try:
        other = c.execute("INSERT INTO faculties(code,name,created_at,updated_at) VALUES('QA-X','Sınaq fakültəsi','2026-01-01','2026-01-01') "
                          "ON CONFLICT(code) DO UPDATE SET name=excluded.name RETURNING id").fetchone()[0]
        c.execute("UPDATE role_grants SET scope_id=? WHERE user_id=? AND role='office' AND scope_type='faculty'", (other, office))
        c.commit()
        assert all(r["topic_id"] != t["id"] for r in forum["office"].get("/api/qa/reports").json)
        assert forum["office"].post(f"/api/qa/reports/{pid}/resolve", {"action": "hide"}).status == 404
        assert any(r["id"] == pid for r in forum["admin"].get("/api/qa/reports").json), "the administrator sees every faculty"
    finally:
        c.execute("UPDATE role_grants SET scope_id=? WHERE user_id=? AND role='office' AND scope_type='faculty'", (mine, office))
        c.commit()
        c.close()
    assert forum["office"].post(f"/api/qa/reports/{pid}/resolve", {"action": "keep"}).status == 200


def test_the_teacher_s_question_badge_reads_by_index(app_db):
    """AR-E4: polled every 30 s, it scanned teacher_questions."""
    plan = " ".join(r["detail"] for r in q("EXPLAIN QUERY PLAN SELECT COUNT(*) n FROM teacher_questions tq JOIN courses co ON co.id=tq.course_id "
                                          "WHERE co.teacher_id=? AND tq.status='open'", (1,)))
    assert "idx_courses_teacher" in plan and "SCAN tq" not in plan, plan


# ---------------------------------------------------------------- Checkpoint E (test review)
def test_a_teacher_of_another_course_reads_nothing_there(forum):
    """T-E1: the demo teacher does not teach the author's other course (neither its teacher nor a teaching unit)."""
    me = forum["teacher"].user["id"]
    other = q("SELECT e.course_id FROM enrollments e JOIN courses co ON co.id=e.course_id WHERE e.user_id=? AND co.teacher_id<>? "
              "AND NOT EXISTS (SELECT 1 FROM teaching_units u WHERE u.course_id=co.id AND u.teacher_id=?) LIMIT 1",
              (forum["author"].user["id"], me, me))[0]["course_id"]
    t = forum["author"].post(f"/api/courses/{other}/qa", {"title": "Başqa fənnin anonim sualı", "text": "Bu sualı yalnız fənnin müəllimi görür.",
                                                          "anonymous": True}).json
    stranger = forum["teacher"]
    assert stranger.get(f"/api/courses/{other}/qa").status == 404
    assert stranger.get(f"/api/qa/topics/{t['id']}").status == 404
    assert stranger.post(f"/api/qa/topics/{t['id']}/draft").status == 404
    assert stranger.post(f"/api/qa/topics/{t['id']}/faq", {"on": True}).status == 404
    rid = forum["author"].post(f"/api/qa/topics/{t['id']}/replies", {"text": "Özüm əlavə edirəm: şərt belədir"}).json["replies"][-1]["id"]
    assert stranger.post(f"/api/qa/replies/{rid}/accept").status == 404


def test_a_hidden_topic_is_gone_for_students_and_kept_for_the_teacher(forum):
    """T-E6: a report on the topic itself (no reply_id), resolved with hide."""
    t = new_topic(forum, title="Mövzu özü şikayət olunur")
    assert forum["peer"].post("/api/qa/reports", {"topic_id": t["id"], "reason": "Fənnə aid deyil"}).status == 200
    rep = next(x for x in forum["office"].get("/api/qa/reports").json if x["topic_id"] == t["id"] and not x["reply_id"])
    assert forum["office"].post(f"/api/qa/reports/{rep['id']}/resolve", {"action": "hide"}).status == 200
    assert forum["peer"].get(f"/api/qa/topics/{t['id']}").status == 404
    assert t["id"] not in [x["id"] for x in forum["peer"].get(f"/api/courses/{forum['course']}/qa").json]
    assert forum["teacher"].get(f"/api/qa/topics/{t['id']}").status == 200
