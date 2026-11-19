"""The campus knowledge base on screen and the handoff to a person (tasks/todo.md, Task 32): who edits, versions, a
saved article used on the next question, drafts out of search, every answer with a source or a handoff, and the
evaluation set."""
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from zeka.legacy import store

ROOT = Path(__file__).resolve().parents[2]
ARTICLE = {"heading": "Kampusda velosiped dayanacağı", "text": "Velosiped dayanacağı Əsas korpusun həyətində, şərq girişinin yanındadır. "
           "Dayanacaq pulsuzdur və gecə-gündüz açıqdır.", "source": "Kampus qaydaları (demo)", "source_ref": "4.2",
           "review_at": "2027-06-01", "status": "published"}


def one(sql, args=()):
    c = store.connect()
    try:
        return store.row(c, sql, args)
    finally:
        c.close()


def test_only_the_academic_office_and_the_administrator_manage_articles(app_db):
    for role in ("student", "teacher", "office", "leader"):
        assert app_db.client(role).get("/api/kb").status == 403, role
    assert app_db.client(role="student").post("/api/kb", ARTICLE).status == 403
    rows = app_db.client("admin").get("/api/kb").json
    assert len(rows) >= 17 and {"heading", "status", "version", "review_at", "overdue"} <= set(rows[0])


def test_a_new_article_is_checked_saved_with_a_version_and_answered_on_the_next_question(app_db):
    admin = app_db.client("admin")
    assert admin.post("/api/kb", {**ARTICLE, "heading": "Ab"}).status == 400
    assert admin.post("/api/kb", {**ARTICLE, "text": "qısa"}).status == 400
    assert admin.post("/api/kb", {**ARTICLE, "source": ""}).status == 400
    assert admin.post("/api/kb", {**ARTICLE, "request": "no_such_service"}).status == 400
    assert admin.post("/api/kb", {**ARTICLE, "review_at": "next year"}).status == 400
    assert admin.post("/api/kb", {**ARTICLE, "status": "secret"}).status == 400
    assert admin.post("/api/kb", {**ARTICLE, "heading": ["list"]}).status == 400
    a = admin.post("/api/kb", ARTICLE).json
    assert a["version"] == 1 and a["status"] == "published" and a["updated_by"] == admin.user["id"]
    s = app_db.client("student")
    ans = s.post("/api/campus/ask", {"message": "Velosiped dayanacağı haradadır?"}).json["answer"]
    assert ans["cites"] and ans["cites"][0]["heading"] == ARTICLE["heading"]
    changed = admin.put(f"/api/kb/{a['id']}", {**ARTICLE, "text": ARTICLE["text"] + " Dayanacaqda 40 yer var."}).json
    assert changed["version"] == 2
    ans = s.post("/api/campus/ask", {"message": "Velosiped dayanacağında neçə yer var?"}).json["answer"]
    assert "40 yer" in ans["content"], "the edited text is used on the next question"
    got = admin.get(f"/api/kb/{a['id']}").json
    assert [v["version"] for v in got["versions"]] == [2, 1]
    assert one("SELECT 1 FROM audit WHERE action='kb_save' AND detail LIKE ?", (f"#{a['id']} v2%",))


def test_a_draft_or_an_archived_article_is_not_searched_and_a_seeded_one_keeps_its_first_state(app_db):
    admin, s = app_db.client("admin"), app_db.client("student")
    dorm = next(x for x in admin.get("/api/kb").json if x["heading"] == "Yataqxana")
    full = admin.get(f"/api/kb/{dorm['id']}").json["article"]
    body = {k: full[k] for k in ("heading", "text", "request", "action_label", "source", "source_ref", "review_at")}
    assert admin.put(f"/api/kb/{dorm['id']}", {**body, "status": "draft"}).status == 200
    ans = s.post("/api/campus/ask", {"message": "Yataqxanada yer necə əldə edə bilərəm?"}).json["answer"]
    assert not any(c["heading"] == "Yataqxana" for c in ans["cites"]), "a draft is not searched"
    versions = admin.get(f"/api/kb/{dorm['id']}").json["versions"]
    assert [(v["version"], v["status"]) for v in versions] == [(2, "draft"), (1, "published")], "the seeded state is kept as v1"
    assert admin.put(f"/api/kb/{dorm['id']}", {**body, "status": "published"}).status == 200
    ans = s.post("/api/campus/ask", {"message": "Yataqxanada yer necə əldə edə bilərəm?"}).json["answer"]
    assert ans["cites"][0]["heading"] == "Yataqxana"
    assert admin.put("/api/kb/999999", body).status == 404


def test_an_answer_without_a_source_hands_over_to_the_support_desk_with_the_conversation(app_db):
    s = app_db.client("student")
    s.post("/api/campus/clear")
    s.post("/api/campus/ask", {"message": "Salam"})
    ans = s.post("/api/campus/ask", {"message": "Universitetin hovuzu neçədə açılır?"}).json["answer"]
    assert not ans["cites"] and not ans["meta"].get("source")
    assert ans["meta"]["actions"][0] == {"type": "handoff", "label": "Dəstək xidmətinə ötür"}
    tid = s.post("/api/campus/handoff", {"message_id": ans["id"]}).json["ticket_id"]
    t = one("SELECT * FROM support_tickets WHERE id=?", (tid,))
    assert t["user_id"] == s.user["id"] and "hovuzu" in t["subject"] and "Köməkçi:" in t["body"] and "Salam" in t["body"]
    assert s.post("/api/campus/handoff", {"message_id": ans["id"]}).json["ticket_id"] == tid, "once per answer"
    other = app_db.client("teacher")
    assert other.post("/api/campus/handoff", {"message_id": ans["id"]}).status == 404, "only one's own answer"
    assert s.post("/api/campus/handoff", {"message_id": ans["id"] - 1}).status == 404, "a question is not an answer"
    assert s.post("/api/campus/handoff", {"message_id": "x"}).status == 400


def test_the_evaluation_set_scores_at_least_45_of_50_and_every_answer_has_a_source_or_a_handoff():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "eval_assistant.py"), str(ROOT / "tests" / "eval" / "assistant_az.jsonl")],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    right = int(r.stdout.strip().splitlines()[-1].split()[1].split("/")[0])
    assert right >= 45 and "without a source or a handoff: 0" in r.stdout, r.stdout


def test_campus_answer_hands_over_when_the_composer_gives_neither_source_nor_handoff(app_db, monkeypatch):
    """T-E19: the guard in assistant.service.campus_answer (Task 32), reached with a bare composer answer."""
    from zeka.legacy import tutor
    from zeka.modules.assistant import service
    monkeypatch.setattr(tutor, "compose_campus", lambda q, hits, lang: {"text": "Bilmirəm.", "cites": [], "actions": [], "meta": {}})
    c = store.connect()
    try:
        out = service.campus_answer(c, {"id": 1, "role": "student"}, "Yataqxanada növbə necə paylanır", "az")
    finally:
        c.close()
    assert [a["type"] for a in out["actions"]] == ["handoff"]


# ---------------------------------------------------------------- Checkpoint E (area F)
def test_a_draft_article_is_not_readable_as_a_source(app_db):
    """SEC-E4: /api/source/kb/{id} served a draft or archived article to any signed-in user."""
    admin = app_db.client("admin")
    draft = admin.post("/api/kb", {**ARTICLE, "heading": "Qaralama: yeni yataqxana qaydası", "status": "draft"}).json
    live = admin.post("/api/kb", {**ARTICLE, "heading": "Dərc olunmuş: kitabxana saatları"}).json
    s = app_db.client("student")
    assert s.get(f"/api/source/kb/{draft['id']}").status == 404
    assert s.get(f"/api/source/kb/{live['id']}").status == 200


def test_the_review_date_is_exactly_year_month_day(app_db):
    """PY-E3: Python 3.11+ reads 20261118 and 2026-W47-3, which were stored raw and never flagged as overdue."""
    admin = app_db.client("admin")
    for bad in ("20261118", "2026-W47-3", "2026-11-18T00:00", "２０２６-11-18"):
        assert admin.post("/api/kb", {**ARTICLE, "heading": f"Tarix {bad}", "review_at": bad}).status == 400, bad


def test_a_handoff_carries_only_the_same_day_s_conversation(app_db):
    """TM-E16: a phone number asked about days ago went into the ticket with the new question."""
    s = app_db.client("student")
    s.post("/api/campus/clear")
    old = (store.now() - timedelta(days=3)).isoformat(timespec="seconds")
    c = store.connect()
    try:
        c.execute("INSERT INTO messages(user_id,channel,role,content,created_at) VALUES(?,?,?,?,?)",
                  (s.user["id"], "campus", "user", "Mənim nömrəm +994501234567, FİN 5ABC123", old))
        c.commit()
    finally:
        c.close()
    ans = s.post("/api/campus/ask", {"message": "Universitetin hovuzu neçədə açılır?"}).json["answer"]
    tid = s.post("/api/campus/handoff", {"message_id": ans["id"]}).json["ticket_id"]
    body = one("SELECT body FROM support_tickets WHERE id=?", (tid,))["body"]
    assert "hovuzu" in body and "+994501234567" not in body and "5ABC123" not in body
