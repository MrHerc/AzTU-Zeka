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
    assert topic["anonymous"] is True and topic["author"] == forum["author"].user["full_name"]
    assert forum["teacher"].post(f"/api/teacher/questions/{topic['id']}/answer", {"answer": "Materialın 2-ci bölməsinə baxın."}).status == 200
    got = forum["author"].get(f"/api/qa/topics/{topic['id']}").json
    assert got["status"] == "answered" and got["replies"][-1]["accepted"] == 1 and got["replies"][-1]["by_teacher"] is True
