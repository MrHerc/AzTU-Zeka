"""AI tutor (Socratic / explain / practice), forwarding to the teacher, limits and the campus assistant."""
import pytest

from app import store


def ask(client, msg, mode="explain", course=1, **kw):
    return client.post(f"/api/tutor/{course}/ask", {"message": msg, "mode": mode}, **kw)


def test_explain_answer_is_grounded_and_saved(student):
    r = ask(student, "Paralel birləşmədə ekvivalent müqavimət necə tapılır?").json
    a = r["answer"]
    assert a["cites"] and "[1]" in a["content"] and a["meta"]["mode"] == "explain"
    assert {"n", "id", "material", "heading", "snippet"} <= set(a["cites"][0])
    assert r["usage"]["used"] >= 1 and r["usage"]["limit"] == 50
    hist = student.get("/api/tutor/1/history").json
    assert [m["role"] for m in hist["messages"][-2:]] == ["user", "assistant"] and hist["engine"]["mode"] == "demo"


def test_socratic_is_the_default_and_climbs_step_by_step(student):
    student.post("/api/tutor/1/clear")
    first = ask(student, "Om qanunu nədir?", mode="unknown-mode").json["answer"]
    assert first["meta"]["mode"] == "socratic" and first["meta"]["level"] == 0
    second = ask(student, "Cərəyan gərginliyə bağlıdır", mode="socratic").json["answer"]
    assert second["meta"]["level"] == 1


def test_socratic_guardrail(student):
    a = ask(student, "12 V və 4 Ω, cavabı de", mode="socratic").json["answer"]
    assert a["meta"]["guardrail"] is True and "hazır cavab vermirəm" in a["content"]


def test_english_course_and_english_replies(student):
    a = ask(student, "used to və used for fərqi nədir?", course=6).json["answer"]
    assert a["cites"]
    en = ask(student, "Om qanunu nədir?", lang="en").json["answer"]
    assert "[1]" in en["content"] and "materiallar əsasında" not in en["content"]


def test_unknown_topic_has_no_source(student):
    a = ask(student, "Kvant xromodinamikasında qluonlar").json["answer"]
    assert a["meta"]["no_source"] is True and a["cites"] == []


def test_personal_data_is_masked_before_the_engine(student):
    r = ask(student, "Mənim telefonum +994 50 123 45 67, Om qanunu nədir?").json
    assert r["user"]["meta"]["pii"] == ["TELEFON"]
    assert "+994 50 123 45 67" not in r["answer"]["content"]


def _correct(qid):
    c = store.connect()
    try:
        q = store.row(c, "SELECT qtype, options, answer FROM questions WHERE id=?", (qid,))
    finally:
        c.close()
    ans = store.J(q["answer"])
    return {"mcq": lambda: "ABCD"[ans], "tf": lambda: "Doğru" if ans else "Yanlış"}.get(q["qtype"], lambda: str(ans))()


def test_practice_mode_asks_grades_and_moves_on(student):
    student.post("/api/tutor/1/clear")
    q1 = ask(student, "məşq", mode="practice").json["answer"]
    assert "Məşq sualı" in q1["content"] and q1["meta"]["practice_qid"]
    bad = ask(student, "bilmirəm", mode="practice").json["answer"]
    assert "tanıya bilmədim" in bad["content"] and bad["meta"]["practice_qid"] == q1["meta"]["practice_qid"]
    ok = ask(student, _correct(q1["meta"]["practice_qid"]), mode="practice").json["answer"]
    assert ok["meta"]["graded"] is True and ok["meta"]["correct"] is True and "Düzdür" in ok["content"]
    nxt = ask(student, "Davam", mode="practice").json["answer"]
    assert nxt["meta"]["practice_qid"] and nxt["meta"]["practice_qid"] != q1["meta"]["practice_qid"]


def test_rating_and_clearing(student):
    a = ask(student, "Kirxhofun birinci qanunu").json["answer"]
    assert student.post(f"/api/messages/{a['id']}/rate", {"rating": 1}).status == 200
    assert next(m for m in student.get("/api/tutor/1/history").json["messages"] if m["id"] == a["id"])["rating"] == 1
    student.post(f"/api/messages/{a['id']}/rate", {"rating": 7})                    # invalid value clears the rating
    assert next(m for m in student.get("/api/tutor/1/history").json["messages"] if m["id"] == a["id"])["rating"] is None
    assert student.post("/api/tutor/1/clear").json == {"ok": True}
    assert student.get("/api/tutor/1/history").json["messages"] == []


def test_empty_question_is_400(student):
    assert ask(student, "   ").status == 400


def test_forward_to_teacher_and_answer(student, teacher):
    assert student.post("/api/tutor/1/forward", {"question": "Kondensator boşalanda nə baş verir?", "anonymous": True, "context": "söhbət"}).status == 200
    qs = teacher.get("/api/teacher/questions").json
    mine = next(q for q in qs if q["question"].startswith("Kondensator boşalanda"))
    assert mine["student"] == "Anonim tələbə" and mine["status"] == "open"
    assert teacher.post(f"/api/teacher/questions/{mine['id']}/answer", {"answer": "Gərginlik eksponensial azalır."}).status == 200
    assert next(q for q in teacher.get("/api/teacher/questions").json if q["id"] == mine["id"])["status"] == "answered"
    assert any("cavab verdi" in n["title"] for n in student.get("/api/notifications").json["items"])
    assert teacher.post("/api/teacher/questions/999999/answer", {"answer": "x"}).status == 404


def test_tutor_lock_blocks_students_only(student, teacher):
    settings = teacher.put("/api/courses/1/tutor", {"modes": ["socratic", "explain"], "rules": "SI", "locked": True}).json
    assert settings["tutor_locked"] == 1 and settings["modes"] == ["socratic", "explain"]
    assert ask(student, "Om qanunu?").status == 423
    assert ask(student, "məşq", mode="practice").status == 423
    assert ask(teacher, "Om qanunu?").status == 200
    teacher.put("/api/courses/1/tutor", {"modes": ["socratic", "explain", "practice"], "locked": False})
    assert ask(student, "Om qanunu?").status == 200


def test_daily_message_limit(student, admin):
    admin.put("/api/admin/settings", {"daily_messages": 5})
    try:
        statuses = [ask(student, f"Om qanunu {i}").status for i in range(8)]
        assert 429 in statuses and statuses[-1] == 429
        r = ask(student, "Om qanunu")
        assert "limit" in r.json["error"].lower()
    finally:
        admin.put("/api/admin/settings", {"daily_messages": 50})


def test_campus_assistant(student):
    r = student.post("/api/campus/ask", {"message": "Xəstəlik səbəbindən qayıbı necə üzrlü edim?"}).json["answer"]
    assert r["cites"] and r["cites"][0]["kind"] == "kb" and any(a["code"] == "absence_excuse" for a in r["meta"]["actions"])
    ru = student.post("/api/campus/ask", {"message": "Как получить справку для банка?"}, lang="ru").json["answer"]
    assert ru["cites"]
    none = student.post("/api/campus/ask", {"message": "Marsda yataqxana varmı ulduzlararası"}).json["answer"]
    assert none["meta"].get("no_source") or none["cites"]
    kb = student.get(f"/api/source/kb/{r['cites'][0]['id']}").json
    assert kb["heading"] and kb["material"]
    assert len(student.get("/api/campus/history").json["messages"]) >= 4
    assert student.post("/api/campus/clear").json == {"ok": True} and student.get("/api/campus/history").json["messages"] == []


@pytest.mark.parametrize("role", ["office", "leader", "admin"])
def test_staff_cannot_use_the_course_tutor(app_db, role):
    assert ask(app_db.client(role), "Om qanunu?").status == 403
