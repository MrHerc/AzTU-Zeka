"""Privacy (tasks/todo.md, Task 40): every column of the schema that holds a person's id is in the data inventory and its
document; the export holds every row of the person's own and no one else's, without secrets, exam forms or unreleased
scores (the exam part is in tests/security/test_exam_item_leak.py); an approved deletion request deletes or keeps each
column as the inventory says, anonymises the account and is audited, and only the academic office decides; the AI tutor
and the campus assistant answer only with the person's consent to the current text, and a withdrawal deletes the chats;
the external AI is called only with a consent to the current text and the service the notice names; the retention job
follows the university settings; the notice and the consent texts are in three languages."""
import json
import re
from datetime import timedelta
from pathlib import Path

import pytest

from zeka.core import clock
from zeka.legacy import engine, periodic, r_learning, store, tutor
from zeka.modules.identity import privacy, repo

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "privacy" / "data-inventory.md"
# a column whose name says it holds a person's id; read from the live schema, not from the inventory under test
PERSON = re.compile(r"(^|_)(user|student|owner|holder|author|teacher|reporter|actor|assignee|leader)_id$|_by$")
SECRET = re.compile(r"password|secret|nonce|verifier|_hash$|^totp_")
# the export rows that are filtered on purpose (drafts, unreleased exams, exam documents); every other one is exported whole
FILTERED = {("grades", "user_id"), ("documents", "holder_id"), ("exam_events", "student_id")}
# what the law keeps (academic and legal records, proofs) and what an erasure must remove, independent of the inventory
KEPT = {"attendance", "attendance_opening", "grades", "grade_changes", "final_grades", "enrollments", "exam_attempts", "exam_roster",
        "exam_events", "exam_forms", "documents", "submissions", "student_status_events", "requests", "consents", "privacy_requests", "audit"}
GONE = {"messages", "notifications", "sessions", "feedback", "ical_feeds", "recovery_codes", "support_tickets", "news_saved"}


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def run(sql, args=()):
    c = store.connect()
    try:
        c.execute(sql, args)
        c.commit()
    finally:
        c.close()


def person_columns() -> set:
    out = {("users", "id")}
    for t in q("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        out |= {(t["name"], col["name"]) for col in q(f'PRAGMA table_info("{t["name"]}")') if PERSON.search(col["name"])}  # nosec B608
    return out


def counts(uid: int) -> dict:
    return {(t, col): q(f'SELECT COUNT(*) n FROM "{t}" WHERE "{col}"=?', (uid,))[0]["n"] for t, col in repo.INVENTORY}  # nosec B608


def exact(uid: int) -> dict:
    """Checkpoint F (TE-F2): the rows the export must hold of the filtered and the VIA tables, filtered here in Python from
    the whole tables, not with the inventory's SQL."""
    released = {e["id"] for e in q("SELECT id, status FROM exams") if e["status"] == "released"}
    reqs = {r["id"] for r in q("SELECT id, student_id FROM requests") if r["student_id"] == uid}
    tickets = {r["id"] for r in q("SELECT id, user_id FROM support_tickets") if r["user_id"] == uid}
    attempts = {a["id"] for a in q("SELECT id, exam_id, student_id FROM exam_attempts") if a["student_id"] == uid and a["exam_id"] in released}
    return {
        "grades": sum(g["user_id"] == uid and g["status"] == "published" for g in q("SELECT user_id, status FROM grades")),
        "documents": sum(d["holder_id"] == uid and d["kind"] not in ("exam_protocol", "exam_statement")
                         for d in q("SELECT holder_id, kind FROM documents")),
        "exam_events": sum(e["student_id"] == uid and e["exam_id"] in released for e in q("SELECT student_id, exam_id FROM exam_events")),
        "exam_answers": sum(a["attempt_id"] in attempts for a in q("SELECT attempt_id FROM exam_answers")),
        "request_events": sum(e["request_id"] in reqs for e in q("SELECT request_id FROM request_events")),
        "request_messages": sum(m["request_id"] in reqs or m["author_id"] == uid for m in q("SELECT request_id, author_id FROM request_messages")),
        "support_messages": sum(m["author_id"] == uid or (not m["internal"] and m["ticket_id"] in tickets)
                                for m in q("SELECT ticket_id, author_id, internal FROM support_messages")),
    }


def login_as(app_db, username):
    s = app_db.client()
    assert s.post("/api/auth/demo", {"role": "student", "user": username}).status == 200
    return s


# ---------------------------------------------------------------- the inventory
def test_every_column_holding_a_person_is_in_the_inventory_and_its_document(app_db):
    found = person_columns()
    assert found - set(repo.INVENTORY) == set(), "add the column to identity/repo.INVENTORY and docs/privacy/data-inventory.md"
    assert set(repo.INVENTORY) - found == set(), "the inventory names a column the schema does not have"
    assert {a for _, a in repo.INVENTORY.values()} <= {"delete", "keep", "anonymise"}
    doc = DOC.read_text(encoding="utf-8")
    assert [f"{t}.{col}" for t, col in repo.INVENTORY if f"`{t}.{col}`" not in doc] == []
    for t in (*repo.VIA, "exam_forms", "exam_answers"):
        assert f"`{t}" in doc, t


# ---------------------------------------------------------------- the export
@pytest.mark.parametrize("role", ["student", "teacher"])
def test_the_export_holds_every_own_row_and_nothing_else(app_db, role):
    client = app_db.client(role)
    uid = client.user["id"]
    if role == "student":       # rows in tables the demo leaves empty for her
        client.post("/api/consent", {"ai": True, "external": False})
        run("INSERT INTO feedback(user_id,role,area,score,comment,created_at) VALUES(?,?,?,?,?,?)", (uid, "student", "tutor", 5, "əla", store.iso(store.now())))
        run("INSERT INTO grades(user_id,course_id,component,score,max,updated_at,status) VALUES(?,1,'Gizli qaralama',3,10,?,'draft')",
            (uid, store.iso(store.now())))
    have, want = counts(uid), exact(uid)        # before the export audits itself
    if role == "student":                       # rows the mutations of the filtered and VIA conditions would lose
        assert want["grades"] and want["documents"] and want["request_events"], want
    r = client.get("/api/me/export")
    assert r.status == 200 and "attachment" in r.headers.get("Content-Disposition", "")
    out = r.json
    tables = out["tables"]
    for (t, col), (cond, _) in repo.INVENTORY.items():
        if cond is None or (t, col) in FILTERED:
            continue
        got = sum(1 for x in tables[t] if x.get(col) == uid)
        assert got == have[t, col], (t, col, got, have[t, col])
    assert {t: len(tables[t]) for t in want} == want     # published grades, released exams, own documents, the VIA rows: exactly
    own = {t: [col for (tt, col), (cond, _) in repo.INVENTORY.items() if tt == t and cond] for t in tables}
    for t, rows_ in tables.items():
        for x in rows_:
            assert not [k for k in x if SECRET.search(k)], (t, x)
            if t not in repo.VIA:
                assert any(x.get(col) == uid for col in own[t]), (t, x)      # never someone else's row
    mine = {"requests": {x["id"] for x in tables["requests"]}, "tickets": {x["id"] for x in tables["support_tickets"]},
            "attempts": {x["id"] for x in tables["exam_attempts"]}}
    assert all(x["request_id"] in mine["requests"] for x in tables["request_events"])
    assert all(x["request_id"] in mine["requests"] or x["author_id"] == uid for x in tables["request_messages"])
    assert all(x["attempt_id"] in mine["attempts"] for x in tables["exam_answers"])
    assert all(not x["internal"] and (x["ticket_id"] in mine["tickets"] or x["author_id"] == uid) for x in tables["support_messages"])
    assert "exam_forms" not in tables and "exam_forms.student_id" in out["not_exported"]
    assert sum(1 for v in tables.values() if v) >= (10 if role == "student" else 5)
    assert tables["users"][0]["id"] == uid and "password_hash" not in tables["users"][0]
    assert not [g for g in tables["grades"] if g["status"] != "published"], "a draft score is not released"
    assert not [d for d in tables["documents"] if d["kind"] in ("exam_protocol", "exam_statement")]
    assert q("SELECT 1 FROM audit WHERE user_id=? AND action='privacy_export'", (uid,))


def test_the_export_needs_a_session(anon):
    assert anon.get("/api/me/export").status == 401


# ---------------------------------------------------------------- consent and the external AI
def _ask(client):
    return client.post("/api/tutor/1/ask", {"message": "Paralel birləşmədə ekvivalent müqavimət necə tapılır?", "mode": "explain"})


def test_the_external_ai_is_called_only_with_a_consent_to_the_current_text(app_db, monkeypatch):
    name = q("SELECT u.username FROM users u JOIN enrollments e ON e.user_id=u.id WHERE e.course_id=1 AND u.synthetic=1 "
             "ORDER BY u.id LIMIT 1 OFFSET 3")[0]["username"]
    s = login_as(app_db, name)
    calls = []
    real = r_learning.search_chunks
    monkeypatch.setattr(engine, "llm_config", lambda: {"enabled": True, "provider": "openai", "model": "fake", "api_key": "x", "base_url": "https://x"})
    monkeypatch.setattr(r_learning, "search_chunks", lambda cid, text: [{**h, "score": 5.0} for h in real(cid, text)])
    monkeypatch.setattr(tutor, "llm_tutor", lambda mode, text, hits, *a: calls.append(text) or
                        {"text": "Xarici cavab [1]", "cites": [hits[0]["id"]], "meta": {"mode": mode}})
    assert s.post("/api/consent", {"ai": True, "external": False}).status == 200
    r = _ask(s)
    assert r.status == 200 and calls == [] and r.json["answer"]["meta"].get("note"), "no consent: the offline engine"
    v1 = privacy.version("external_ai")
    assert s.post("/api/consent", {"external": True, "versions": {"external_ai": v1}}).status == 200
    assert _ask(s).status == 200 and len(calls) == 1
    # a new text is a new version: the consent to the old one no longer lets a question out
    monkeypatch.setitem(privacy.PURPOSES, "external_ai", privacy.PURPOSES["external_ai"] + " Xidmət: yeni təchizatçı.")
    v2 = privacy.version("external_ai")
    assert v2 != v1
    r = _ask(s)
    assert r.status == 200 and len(calls) == 1 and r.json["answer"]["meta"].get("note")
    ext = next(p for p in s.get("/api/privacy").json["purposes"] if p["id"] == "external_ai")
    assert ext["version"] == v2 and ext["consent"]["granted"] and not ext["consent"]["current"]
    assert s.post("/api/consent", {"external": True, "versions": {"external_ai": v1}}).status == 409      # the page showed the old text
    assert s.post("/api/consent", {"external": True, "versions": {"external_ai": v2}}).status == 200
    assert _ask(s).status == 200 and len(calls) == 2
    assert q("SELECT text FROM consent_texts WHERE version=?", (v2,))[0]["text"].endswith("yeni təchizatçı.\n— · —")   # no service named
    assert s.post("/api/consent", {"external": False}).status == 200            # withdrawn
    assert _ask(s).status == 200 and len(calls) == 2
    history = q("SELECT version, granted, method FROM consents c JOIN users u ON u.id=c.user_id WHERE u.username=? "
                "AND purpose='external_ai' ORDER BY c.id", (name,))
    assert [(h["version"], h["granted"], h["method"]) for h in history] == [(v1, 0, "portal"), (v1, 1, "portal"), (v2, 1, "portal"), (v2, 0, "portal")]


def test_a_teacher_also_needs_the_consent(app_db, monkeypatch):
    calls = []
    real = r_learning.search_chunks
    monkeypatch.setattr(engine, "llm_config", lambda: {"enabled": True, "provider": "openai", "model": "fake", "api_key": "x", "base_url": "https://x"})
    monkeypatch.setattr(r_learning, "search_chunks", lambda cid, text: [{**h, "score": 5.0} for h in real(cid, text)])
    monkeypatch.setattr(tutor, "llm_tutor", lambda mode, text, hits, *a: calls.append(text) or {"text": "ok [1]", "cites": [hits[0]["id"]], "meta": {"mode": mode}})
    t = app_db.client("teacher")
    run("DELETE FROM consents WHERE user_id=?", (t.user["id"],))
    assert _ask(t).status == 403 and calls == []                                  # the AI study aids need their own consent
    assert t.post("/api/consent", {"ai": True}).status == 200
    assert _ask(t).status == 200 and calls == []
    # Checkpoint F (SF-F9): a consent to the external AI names the version of the text the page showed
    assert t.post("/api/consent", {"external": True}).status == 409 and _ask(t).status == 200 and calls == []
    assert t.post("/api/consent", {"external": True, "versions": {"external_ai": privacy.version("external_ai")}}).status == 200
    assert _ask(t).status == 200 and len(calls) == 1


def test_nothing_leaves_for_the_external_ai_unmasked_even_with_masking_off(app_db, monkeypatch):
    """Checkpoint F (SA-F5): the consent text promises masked questions; the masking toggle only changes the offline engine."""
    calls = []
    real = r_learning.search_chunks
    monkeypatch.setattr(engine, "llm_config", lambda: {"enabled": True, "provider": "openai", "model": "fake", "api_key": "x", "base_url": "https://x"})
    monkeypatch.setattr(r_learning, "search_chunks", lambda cid, text: [{**h, "score": 5.0} for h in real(cid, text)])
    monkeypatch.setattr(tutor, "llm_tutor", lambda mode, text, hits, hist, *a: calls.append((text, hist)) or
                        {"text": "ok [1]", "cites": [hits[0]["id"]], "meta": {"mode": mode}})
    limits = json.loads(q("SELECT value FROM settings WHERE key='limits'")[0]["value"])
    run("UPDATE settings SET value=? WHERE key='limits'", (json.dumps({**limits, "pii_masking": False}),))
    try:
        t = app_db.client("teacher")
        assert t.post("/api/consent", {"ai": True, "external": True, "versions": {"external_ai": privacy.version("external_ai")}}).status == 200
        ask = "Paralel birləşmədə ekvivalent müqavimət necə tapılır? Nömrəm +994 50 123 45 67, poçtum ali@example.az"
        for _ in range(2):                                 # the second call carries the first question in its history
            assert t.post("/api/tutor/1/ask", {"message": ask, "mode": "explain"}).status == 200
    finally:
        run("UPDATE settings SET value=? WHERE key='limits'", (json.dumps(limits),))
    sent = json.dumps(calls, ensure_ascii=False)
    assert len(calls) == 2 and "123 45 67" not in sent and "ali@example.az" not in sent, sent


def _chats(uid):
    return q("SELECT COUNT(*) n FROM messages WHERE user_id=?", (uid,))[0]["n"]


def _allowed(uid, purpose="external_ai"):
    c = store.connect()
    try:
        return privacy.allowed(c, uid, purpose)
    finally:
        c.close()


@pytest.mark.parametrize("role", ["student", "teacher"])
def test_the_ai_helpers_answer_only_with_the_current_consent_and_a_withdrawal_closes_them(app_db, role):
    """The owner's decision of 2026-11-21: the AI tutor and the campus assistant are optional study aids. Without the
    person's consent to the current text both refuse, store nothing and leave the rest of the portal as it was; the
    profile withdraws the consent, and the withdrawal deletes the chats it covered."""
    client = app_db.client(role)
    uid = client.user["id"]
    campus = {"message": "Arayışı necə ala bilərəm?"}
    run("DELETE FROM consents WHERE user_id=?", (uid,))
    have = _chats(uid)
    for path, body in (("/api/tutor/1/ask", {"message": "Om qanunu nədir?", "mode": "explain"}), ("/api/campus/ask", campus)):
        r = client.post(path, body)
        assert r.status == 403 and "razılı" in r.json["error"], (path, r.text)
        assert client.post(path, body, lang="en").json["error"] != r.json["error"]            # translated
    assert _chats(uid) == have, "a refused question is not stored"
    assert client.get("/api/me").status == 200 and client.get("/api/courses").status == 200   # the portal does not depend on it
    assert client.post("/api/consent", {"ai": True}).status == 200
    assert _ask(client).status == 200 and client.post("/api/campus/ask", campus).status == 200 and _chats(uid) == have + 4
    ai = next(p for p in client.get("/api/privacy").json["purposes"] if p["id"] == "ai")
    assert ai["consent"]["granted"] and ai["consent"]["current"] and "required" not in ai
    assert client.post("/api/consent", {"ai": False, "versions": {"ai": privacy.version("ai")}}).status == 200
    assert _chats(uid) == 0, "the withdrawal deletes the chats the consent covered"
    assert _ask(client).status == 403 and client.post("/api/campus/ask", campus).status == 403 and _chats(uid) == 0
    assert q("SELECT granted FROM consents WHERE user_id=? AND purpose='ai' ORDER BY id DESC LIMIT 1", (uid,))[0]["granted"] == 0
    assert client.post("/api/consent", {"ai": True}).status == 200 and _ask(client).status == 200     # given again


def test_a_new_ai_text_asks_again(app_db, monkeypatch):
    s = app_db.client("student")
    assert s.post("/api/consent", {"ai": True}).status == 200 and _ask(s).status == 200
    monkeypatch.setitem(privacy.PURPOSES, "ai", privacy.PURPOSES["ai"] + " Yeni mətn.")
    assert _ask(s).status == 403
    assert s.post("/api/consent", {"ai": True, "versions": {"ai": privacy.version("ai")}}).status == 200 and _ask(s).status == 200
    monkeypatch.undo()
    assert not _allowed(s.user["id"], "ai") and s.post("/api/consent", {"ai": True}).status == 200


def test_the_notice_names_the_external_service_and_a_new_service_asks_again(app_db, monkeypatch):
    """The owner's decision of 2026-11-21 (data-inventory.md, Qərarlar): the consent text says the notice names the
    service and its country; the notice takes them from the LLM settings, and another service is a new version."""
    assert "məxfilik bildirişində" in privacy.PURPOSES["external_ai"]
    anon = app_db.client()
    assert anon.get("/api/privacy").json["external_ai"] == {"enabled": False, "vendor": None, "country": None}
    cfg = {"enabled": True, "provider": "openai", "model": "fake", "api_key": "sirr-açar", "base_url": "https://x",
           "vendor": "Nümunə AI MMC", "country": "Almaniya"}
    monkeypatch.setattr(engine, "llm_config", lambda: cfg)
    r = anon.get("/api/privacy")
    assert r.json["external_ai"] == {"enabled": True, "vendor": "Nümunə AI MMC", "country": "Almaniya"} and "sirr-açar" not in r.text
    s = app_db.client("teacher")
    v1 = privacy.version("external_ai")
    assert s.post("/api/consent", {"ai": True, "external": True, "versions": {"external_ai": v1}}).status == 200
    assert _allowed(s.user["id"])
    assert q("SELECT text FROM consent_texts WHERE version=?", (v1,))[0]["text"].endswith("Nümunə AI MMC · Almaniya")
    monkeypatch.setitem(cfg, "country", "ABŞ")
    assert privacy.version("external_ai") != v1 and not _allowed(s.user["id"])
    assert s.post("/api/consent", {"external": True, "versions": {"external_ai": v1}}).status == 409


def test_the_radar_risk_score_is_in_the_student_s_own_export(app_db):
    """The owner's decision of 2026-11-21: the support plan's risk score, level and drivers are the student's own data
    and are exported; the teacher's unsent AI draft is still not."""
    sid = q("SELECT student_id FROM interventions WHERE risk_before IS NOT NULL ORDER BY id LIMIT 1")[0]["student_id"]
    s = login_as(app_db, q("SELECT username FROM users WHERE id=?", (sid,))[0]["username"])
    t = store.iso(store.now())
    run("INSERT INTO teacher_questions(course_id,student_id,anonymous,title,question,status,created_at,updated_at,private,ai_draft) "
        "VALUES(1,?,0,'s','sual','open',?,?,1,'Müəllimin radar qaralaması')", (sid, t, t))
    out = s.get("/api/me/export").json
    plans = out["tables"]["interventions"]
    assert plans and all(p["student_id"] == sid for p in plans)
    assert all({"risk_before", "level_before", "drivers"} <= set(p) for p in plans)
    assert any(p["risk_before"] is not None and p["level_before"] and json.loads(p["drivers"]) for p in plans)
    assert all("ai_draft" not in x for x in out["tables"]["teacher_questions"])
    assert "Müəllimin radar qaralaması" not in json.dumps(out, ensure_ascii=False)
    for doc in (DOC, ROOT / "docs" / "API.md"):
        assert "interventions.risk_before" in doc.read_text(encoding="utf-8"), doc


# ---------------------------------------------------------------- deletion
def _fill(uid):
    """Rows in the tables a deletion empties, besides what the demo seed gave the person."""
    t = store.iso(store.now())
    run("INSERT INTO feedback(user_id,role,area,score,comment,created_at) VALUES(?,?,?,?,?,?)", (uid, "student", "tutor", 4, "yaxşı", t))
    run("INSERT INTO messages(user_id,course_id,channel,role,content,created_at) VALUES(?,1,'tutor','user','Mənim sualım',?)", (uid, t))
    run("INSERT INTO notifications(user_id,kind,title,created_at) VALUES(?,'request','x',?)", (uid, t))
    run("INSERT INTO news_saved(news_id,user_id) VALUES(1,?)", (uid,))
    run("INSERT INTO support_tickets(user_id,category,priority,subject,body,status,created_at,updated_at) VALUES(?,'other','normal','s','b','open',?,?)",
        (uid, t, t))
    tid = q("SELECT MAX(id) id FROM support_tickets")[0]["id"]
    run("INSERT INTO support_messages(ticket_id,author_id,text,internal,created_at) VALUES(?,?,?,0,?)", (tid, uid, "salam", t))
    run("INSERT INTO teacher_questions(course_id,student_id,anonymous,title,question,status,created_at,updated_at,private) "
        "VALUES(1,?,0,'s','sual','open',?,?,1)", (uid, t, t))
    topic = q("SELECT MAX(id) id FROM teacher_questions")[0]["id"]
    run("INSERT INTO qa_replies(topic_id,author_id,text,created_at) VALUES(?,?,?,?)", (topic, 2, "müəllimin cavabı", t))
    run("INSERT INTO ical_feeds(user_id,token_hash,created_at) VALUES(?,?,?)", (uid, f"h{uid}", t))
    run("INSERT INTO recovery_codes(user_id,code_hash) VALUES(?,?)", (uid, f"r{uid}"))
    return tid, topic


def test_an_approved_deletion_follows_the_inventory_and_is_audited(app_db, registrar, office):
    victim = q("SELECT id, username, full_name, student_no FROM users WHERE synthetic=1 AND role='student' ORDER BY id LIMIT 1 OFFSET 11")[0]
    uid = victim["id"]
    s = login_as(app_db, victim["username"])
    assert s.post("/api/consent", {"ai": True, "external": True, "versions": {"external_ai": privacy.version("external_ai")}}).status == 200
    ticket, topic = _fill(uid)
    exam_events = q("SELECT COUNT(*) n FROM exam_events")[0]["n"]
    r = s.post("/api/me/erase", {"reason": "Universiteti bitirdim"})
    assert r.status == 200, r.text
    rid = r.json["id"]
    assert s.post("/api/me/erase", {}).status == 409                                     # one pending request at a time
    assert q("SELECT 1 FROM notifications WHERE user_id=? AND link='/staff/privacy'", (registrar.user["id"],))
    for who in (s, office, app_db.client("admin"), app_db.client("teacher")):            # only the academic office decides
        assert who.get("/api/privacy/requests").status == 403
        assert who.post(f"/api/privacy/requests/{rid}/decide", {"approve": True}).status == 403
    assert rid in [x["id"] for x in registrar.get("/api/privacy/requests?status=pending").json["items"]]
    assert registrar.post(f"/api/privacy/requests/{rid}/decide", {"approve": "yes"}).status == 400
    before = counts(uid)
    assert sum(n for k, n in before.items() if repo.INVENTORY[k][1] == "delete") >= 10
    assert sum(n for k, n in before.items() if repo.INVENTORY[k][1] == "keep") >= 10
    r = registrar.post(f"/api/privacy/requests/{rid}/decide", {"approve": True, "note": "Qanunla saxlanan qeydlər qalır"})
    assert r.status == 200 and r.json["status"] == "done", r.text
    after = counts(uid)
    for k, (_, action) in repo.INVENTORY.items():
        if action == "delete":
            assert after[k] == 0, k
        else:
            assert after[k] == before[k], k                  # academic and legal records stay, linked to the anonymised account
    assert {t for t, _ in repo.INVENTORY if t in KEPT} == KEPT and all(repo.INVENTORY[k][1] == "keep" for k in repo.INVENTORY if k[0] in KEPT)
    assert all(repo.INVENTORY[k][1] == "delete" for k in repo.INVENTORY if k[0] in GONE and k[1] in ("user_id", "student_id"))
    assert sum(before[k] for k in before if k[0] in KEPT) >= 10 and sum(before[k] for k in before if k[0] in GONE) >= 6
    u = q("SELECT * FROM users WHERE id=?", (uid,))[0]
    assert (u["full_name"], u["username"], u["status"], u["email"], u["password_hash"], u["consent_at"]) == \
           (f"#{uid}", f"erased-{uid}", "erased", None, None, None)
    assert u["student_no"] == victim["student_no"]
    assert q("SELECT COUNT(*) n FROM support_messages WHERE ticket_id=?", (ticket,))[0]["n"] == 0
    assert q("SELECT COUNT(*) n FROM qa_replies WHERE topic_id=?", (topic,))[0]["n"] == 0       # the replies of their own topic
    assert q("SELECT COUNT(*) n FROM exam_events")[0]["n"] == exam_events                       # the exam log is append-only
    entry = q("SELECT * FROM audit WHERE action='privacy_erased' AND user_id=?", (registrar.user["id"],))[-1]
    assert f"#{uid}" in entry["detail"] and "messages.user_id" in entry["detail"]
    assert json.loads(q("SELECT result FROM privacy_requests WHERE id=?", (rid,))[0]["result"])["messages.user_id"] >= 1
    assert s.get("/api/me").status == 401                                                # the sessions are gone
    assert registrar.post(f"/api/privacy/requests/{rid}/decide", {"approve": False}).status == 409
    assert app_db.client().post("/api/auth/demo", {"role": "student", "user": victim["username"]}).status == 404
    # Checkpoint F (SA-F6): the deciders' notice and its e-mail copy never named the person, so nothing of them outlives this
    like = f"%{victim['full_name']}%"
    assert q("SELECT COUNT(*) n FROM notifications WHERE title LIKE ? OR body LIKE ?", (like, like))[0]["n"] == 0
    assert q("SELECT COUNT(*) n FROM outbox WHERE params LIKE ?", (like,))[0]["n"] == 0


def test_a_refused_deletion_tells_the_person_and_nobody_decides_their_own(app_db, registrar):
    victim = q("SELECT id, username FROM users WHERE synthetic=1 AND role='student' ORDER BY id LIMIT 1 OFFSET 12")[0]
    s = login_as(app_db, victim["username"])
    rid = s.post("/api/me/erase", {"reason": ""}).json["id"]
    r = registrar.post(f"/api/privacy/requests/{rid}/decide", {"approve": False, "note": "Aktiv tələbədir"})
    assert r.status == 200 and r.json["status"] == "rejected"
    assert q("SELECT 1 FROM notifications WHERE user_id=? AND link='/profile'", (victim["id"],))
    assert q("SELECT full_name FROM users WHERE id=?", (victim["id"],))[0]["full_name"] != f"#{victim['id']}"
    reqs = s.get("/api/privacy").json["requests"]
    assert reqs[0]["status"] == "rejected" and reqs[0]["note"] == "Aktiv tələbədir"
    own = registrar.post("/api/me/erase", {}).json["id"]
    assert registrar.post(f"/api/privacy/requests/{own}/decide", {"approve": True}).status == 403
    run("UPDATE privacy_requests SET status='rejected' WHERE id=?", (own,))
    demo = app_db.client("student")
    did = demo.post("/api/me/erase", {}).json["id"]
    assert registrar.post(f"/api/privacy/requests/{did}/decide", {"approve": True}).status == 409    # the demo's sign-in account stays
    run("UPDATE privacy_requests SET status='rejected' WHERE id=?", (did,))
    assert registrar.post("/api/privacy/requests/999999/decide", {"approve": True}).status == 404


# ---------------------------------------------------------------- retention
def test_the_retention_job_follows_the_university_settings(app_db, admin):
    value = {"chats_days": 30, "community_days": 10, "notifications_days": 30, "logs_days": 7, "audit_days": 365}
    for bad in ({**value, "chats_days": 5}, {**value, "audit_days": "365"}, {k: v for k, v in value.items() if k != "logs_days"},
                {**value, "extra": 1}, {**value, "community_days": True}):
        assert admin.put("/api/admin/settings/retention", {"value": bad}).status == 400, bad
    r = admin.put("/api/admin/settings/retention", {"value": value})
    assert r.status == 200 and r.json["retention"] == value
    assert app_db.client().get("/api/privacy").json["retention"] == value
    t, aware = store.now(), clock.now()
    old, fresh = lambda d: store.iso(t - timedelta(days=d + 1)), store.iso(t - timedelta(days=1))
    for at in (old(30), fresh):
        run("INSERT INTO messages(user_id,course_id,channel,role,content,created_at) VALUES(1,1,'tutor','user','r',?)", (at,))
        run("INSERT INTO notifications(user_id,kind,title,created_at) VALUES(1,'request','retention',?)", (at,))
    for at in (old(10), fresh):
        run("INSERT INTO club_messages(channel_id,author_id,text,created_at) VALUES(1,1,'retention',?)", (at,))
    for at in (old(365), fresh):
        run("INSERT INTO audit(ts,user_id,action,entity,detail) VALUES(?,1,'retention_probe','x','')", (at,))
    for at in ((aware - timedelta(days=8)).isoformat(timespec="seconds"), (aware - timedelta(days=1)).isoformat(timespec="seconds")):
        run("INSERT INTO job_runs(name,started_at,status) VALUES('retention.probe',?,'ok')", (at,))
    c = store.connect()
    try:
        periodic.retention_purge(c)
        c.commit()
    finally:
        c.close()
    assert [x["created_at"] for x in q("SELECT created_at FROM messages WHERE content='r'")] == [fresh]
    assert [x["created_at"] for x in q("SELECT created_at FROM notifications WHERE title='retention'")] == [fresh]
    assert [x["created_at"] for x in q("SELECT created_at FROM club_messages WHERE text='retention'")] == [fresh]
    assert [x["ts"] for x in q("SELECT ts FROM audit WHERE action='retention_probe'")] == [fresh]
    assert len(q("SELECT 1 FROM job_runs WHERE name='retention.probe'")) == 1
    defaults = {k: d for k, (_, d, _, _) in privacy.RETENTION.items()}
    assert admin.put("/api/admin/settings/retention", {"value": defaults}).status == 200


# ---------------------------------------------------------------- the notice, three languages, bad input
def test_the_notice_and_the_consent_texts_are_in_three_languages(app_db):
    anon = app_db.client()
    texts = {lang: {p["id"]: p["text"] for p in anon.get("/api/privacy", lang=lang).json["purposes"]} for lang in ("az", "en", "ru")}
    assert texts["az"] == privacy.PURPOSES
    for p in privacy.PURPOSES:
        assert len({texts[lang][p] for lang in texts}) == 3, p
    keys = re.findall(r'\bt\("((?:[^"\\]|\\.)+)"', (ROOT / "frontend" / "js" / "privacy.js").read_text(encoding="utf-8"))
    for lang in ("en", "ru"):
        cat = json.loads((ROOT / "frontend" / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        assert [k for k in keys if k not in cat] == [], lang
    assert len(keys) > 30


@pytest.mark.parametrize("path, body", [
    ("/api/consent", {"ai": "yes"}), ("/api/consent", {"external": 1}), ("/api/consent", {"versions": "x"}),
    ("/api/consent", {"ai": True, "versions": {"ai": 5}}), ("/api/me/erase", {"reason": ["x"]}),
])
def test_malformed_input_is_a_400(app_db, path, body):
    r = app_db.client("teacher").post(path, body)
    assert r.status == 400, r.text


def test_malformed_decisions_are_400(registrar):
    assert registrar.get("/api/privacy/requests?status=bogus").status == 400
    assert registrar.post("/api/privacy/requests/1/decide", {"approve": True, "note": {"x": 1}}).status == 400
    assert registrar.post("/api/privacy/requests/1/decide", {}).status == 400


# ---------------------------------------------------------------- Checkpoint F
def test_the_last_active_administrator_is_not_erased(app_db, registrar):
    """SEC-F4: the tenant would lose its administration; in prod no demo login protects the account."""
    admin = app_db.client("admin")
    logins = q("SELECT value FROM settings WHERE key='demo_logins'")[0]["value"]
    run("UPDATE settings SET value=? WHERE key='demo_logins'", (json.dumps({k: v for k, v in json.loads(logins).items() if k != "admin"}),))
    try:
        assert q("SELECT COUNT(*) n FROM users WHERE role='admin' AND status='active'")[0]["n"] == 1
        rid = admin.post("/api/me/erase", {"reason": ""}).json["id"]
        r = registrar.post(f"/api/privacy/requests/{rid}/decide", {"approve": True})
        assert r.status == 409, r.text
        assert q("SELECT status FROM users WHERE id=?", (admin.user["id"],))[0]["status"] == "active"
        assert q("SELECT status FROM privacy_requests WHERE id=?", (rid,))[0]["status"] == "pending"
        run("UPDATE privacy_requests SET status='rejected' WHERE id=?", (rid,))
    finally:
        run("UPDATE settings SET value=? WHERE key='demo_logins'", (logins,))


def test_an_administrator_grants_no_role_to_themselves(app_db):
    """SA-F8: the inventory says the administrator does not decide erasures; a self-grant of academic_office would."""
    admin = app_db.client("admin")
    r = admin.post(f"/api/admin/users/{admin.user['id']}/roles", {"role": "academic_office"})
    assert r.status == 403
    assert not q("SELECT 1 FROM role_grants WHERE user_id=? AND role='academic_office'", (admin.user["id"],))


def test_the_teacher_s_unsent_ai_draft_is_not_in_the_student_s_export(app_db):
    """SA-F7: the AI draft is the teacher's work product; the student never sees it in the forum either."""
    s = app_db.client("student")
    t = store.iso(store.now())
    run("INSERT INTO teacher_questions(course_id,student_id,anonymous,title,question,status,created_at,updated_at,private,ai_draft) "
        "VALUES(1,?,0,'s','sual','open',?,?,1,'Müəllimin qaralaması')", (s.user["id"], t, t))
    out = s.get("/api/me/export").json
    rows_ = out["tables"]["teacher_questions"]
    assert rows_ and all("ai_draft" not in r for r in rows_) and "Müəllimin qaralaması" not in json.dumps(out, ensure_ascii=False)


def test_an_old_pending_request_stays_in_the_queue_behind_newer_decided_ones(app_db, registrar):
    """PY-F2: the decider's scope and the limit applied in that order; pending first."""
    victim = q("SELECT id FROM users WHERE synthetic=1 AND role='student' ORDER BY id LIMIT 1 OFFSET 13")[0]["id"]
    t = store.iso(store.now())
    run("INSERT INTO privacy_requests(user_id,kind,reason,status,created_at) VALUES(?,'erase','',?,?)", (victim, "pending", t))
    pending = q("SELECT MAX(id) id FROM privacy_requests")[0]["id"]
    for _ in range(201):
        run("INSERT INTO privacy_requests(user_id,kind,reason,status,created_at) VALUES(?,'erase','',?,?)", (victim, "rejected", t))
    try:
        assert pending in [x["id"] for x in registrar.get("/api/privacy/requests").json["items"]]
    finally:
        run("DELETE FROM privacy_requests WHERE user_id=?", (victim,))


def test_the_chat_purge_keeps_the_period_the_notice_shows(app_db):
    """SF-F8: a stored value outside the allowed range shows (and now enforces) the default, 180 days."""
    limits = json.loads(q("SELECT value FROM settings WHERE key='limits'")[0]["value"])
    run("UPDATE settings SET value=? WHERE key='limits'", (json.dumps({**limits, "retention_days": 5}),))
    at = store.iso(store.now() - timedelta(days=10))
    run("INSERT INTO messages(user_id,course_id,channel,role,content,created_at) VALUES(1,1,'tutor','user','sf-f8',?)", (at,))
    try:
        assert app_db.client().get("/api/privacy").json["retention"]["chats_days"] == 180
        c = store.connect()
        try:
            periodic.retention_purge(c)
            c.commit()
        finally:
            c.close()
        assert q("SELECT COUNT(*) n FROM messages WHERE content='sf-f8'")[0]["n"] == 1
    finally:
        run("DELETE FROM messages WHERE content='sf-f8'")
        run("UPDATE settings SET value=? WHERE key='limits'", (json.dumps(limits),))


def test_a_users_import_never_brings_an_erased_account_back(app_db):
    """SEC-F2: the erased row keeps its import link and student number; a re-import, preferred source or not, is a conflict."""
    import base64
    admin = app_db.client("admin")
    head = "sourcedId,username,givenName,familyName,role,identifier,group,email\n"
    data = (head + "secf2,sec.ftwo,Nərgiz,Əhmədova,student,SECF-2,İT-25-1,secf2@example.az\n").encode()

    def imp(prefer):
        return admin.post("/api/admin/import", {"kind": "users", "source": "sis", "filename": "u.csv", "dry_run": False,
                                                "prefer_source": prefer, "content_b64": base64.b64encode(data).decode()}).json
    assert imp(False)["inserted"] == 1
    uid = q("SELECT id FROM users WHERE username='sec.ftwo'")[0]["id"]
    c = store.connect()
    try:
        repo.erase(c, uid)
        c.commit()
    finally:
        c.close()
    for prefer in (False, True):
        rep = imp(prefer)
        assert rep.get("overwritten", 0) == 0 and len(rep["conflicts"]) == 1, rep
    u = q("SELECT username, full_name, status, email FROM users WHERE id=?", (uid,))[0]
    assert (u["username"], u["full_name"], u["status"], u["email"]) == (f"erased-{uid}", f"#{uid}", "erased", None)


def test_the_export_and_the_erasure_read_no_whole_table(app_db):
    """AR-F4: every statement of the export and of the erasure (which runs inside the decider's write transaction) finds
    the person's rows through an index; on a university's tables a scan per inventory table held the lock for seconds."""
    uid = q("SELECT id FROM users WHERE synthetic=1 AND role='student' ORDER BY id LIMIT 1 OFFSET 14")[0]["id"]
    c = store.connect()
    ran: list[str] = []
    try:
        c.set_trace_callback(ran.append)
        privacy.export(c, repo.user(c, uid))
        repo.erase(c, uid)
        c.set_trace_callback(None)
        explained = [s for s in ran if s.lstrip().upper().startswith(("SELECT", "DELETE", "UPDATE"))]
        scans = {s: d for s in explained for *_, d in c.execute("EXPLAIN QUERY PLAN " + s)
                 if d.startswith("SCAN ") and not d.startswith("SCAN CONSTANT")}
    finally:
        c.rollback()
        c.close()
    assert len(explained) > 60, "the export and the erasure really ran"
    assert scans == {}, json.dumps(scans, ensure_ascii=False, indent=1)


def test_the_sixth_export_in_an_hour_is_refused(app_db, rate_limits):
    """AR-F4: each export reads every table of the inventory; five an hour are enough for a person."""
    s = app_db.client("teacher")
    assert [s.get("/api/me/export").status for _ in range(5)] == [200] * 5
    r = s.get("/api/me/export", lang="en")
    assert r.status == 429, r.status
    assert r.json["error"] == "You can download your data at most five times an hour. Please try again later."
    assert app_db.client("student").get("/api/me/export").status == 200, "the limit is per person"


def test_the_retention_purge_deletes_in_batches(app_db, monkeypatch):
    """AR-F5: after a period is shortened the purge may meet millions of rows; it deletes and commits them a batch at a
    time instead of holding the single write lock for all of them at once."""
    monkeypatch.setattr(store, "PURGE_BATCH", 1000, raising=False)
    t = store.now()
    old, young = store.iso(t - timedelta(days=400)), store.iso(t - timedelta(days=1))
    c = store.connect()
    try:
        c.executemany("INSERT INTO notifications(user_id,kind,title,created_at) VALUES(1,'request','af5',?)", [(old,)] * 2500 + [(young,)] * 3)
        c.commit()
        ran: list[str] = []
        c.set_trace_callback(ran.append)
        periodic.retention_purge(c)
        c.set_trace_callback(None)
        c.commit()
    finally:
        c.close()
    at = [i for i, s in enumerate(ran) if re.match(r'\s*DELETE FROM "?notifications"?\s', s)]
    assert len(at) >= 3, at
    assert all("COMMIT" in ran[i + 1:j] for i, j in zip(at, at[1:], strict=False)), "each batch is its own transaction"
    assert [x["created_at"] for x in q("SELECT created_at FROM notifications WHERE title='af5'")] == [young] * 3


def test_a_failed_settings_request_keeps_the_settings_and_the_chats(app_db, monkeypatch):
    """R1: PUT /api/admin/settings purges expired chats inside its own transaction; a failure after the purge (here the
    audit) rolls back the settings change and the deleted messages together, so no change is left without its audit."""
    from zeka.legacy import r_admin

    def boom(*_a, **_k):
        raise RuntimeError("audit failed")

    before = json.loads(q("SELECT value FROM settings WHERE key='limits'")[0]["value"])
    run("INSERT INTO messages(user_id,course_id,channel,role,content,created_at) VALUES(1,1,'tutor','user','r1',?)",
        (store.iso(store.now() - timedelta(days=4000)),))
    monkeypatch.setattr(r_admin, "audit", boom)
    try:
        assert app_db.client("admin").put("/api/admin/settings", {"daily_messages": before.get("daily_messages", 50) + 7}).status == 500
        app_db.errors.clear()
        assert json.loads(q("SELECT value FROM settings WHERE key='limits'")[0]["value"]) == before
        assert q("SELECT COUNT(*) n FROM messages WHERE content='r1'")[0]["n"] == 1
    finally:
        run("DELETE FROM messages WHERE content='r1'")
