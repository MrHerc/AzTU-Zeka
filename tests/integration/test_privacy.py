"""Privacy (tasks/todo.md, Task 40): every column of the schema that holds a person's id is in the data inventory and its
document; the export holds every row of the person's own and no one else's, without secrets, exam forms or unreleased
scores (the exam part is in tests/security/test_exam_item_leak.py); an approved deletion request deletes or keeps each
column as the inventory says, anonymises the account and is audited, and only the academic office decides; the external
AI is called only with a consent to the current text; the retention job follows the university settings; the notice
and the consent texts are in three languages."""
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
    have = counts(uid)                          # before the export audits itself
    r = client.get("/api/me/export")
    assert r.status == 200 and "attachment" in r.headers.get("Content-Disposition", "")
    out = r.json
    tables = out["tables"]
    for (t, col), (cond, _) in repo.INVENTORY.items():
        if cond is None:
            continue
        got = sum(1 for x in tables[t] if x.get(col) == uid)
        if (t, col) in FILTERED:                # published grades, released exams, a person's own documents
            assert got <= have[t, col], (t, col)
        else:
            assert got == have[t, col], (t, col, got, have[t, col])
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
    assert q("SELECT text FROM consent_texts WHERE version=?", (v2,))[0]["text"].endswith("yeni təchizatçı.")
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
    assert _ask(t).status == 200 and calls == []
    assert t.post("/api/consent", {"external": True}).status == 200
    assert _ask(t).status == 200 and len(calls) == 1


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
    s.post("/api/consent", {"ai": True, "external": True})
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
