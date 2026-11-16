"""Support desk, feedback, leadership analytics, administration, system status and translated responses."""
import re
import urllib.parse

import pytest

AZ_LETTERS = re.compile(r"[əğıöüşçƏĞİÖÜŞÇ]")


# ---------------------------------------------------------------- support desk
@pytest.fixture(scope="module")
def ticket(student):
    r = student.post("/api/support/tickets", {"category": "technical", "priority": "high", "subject": "Səhifə açılmır",
                                              "body": "Testlər səhifəsi boş açılır.", "page": "/student/quizzes"})
    assert r.status == 200, r.text
    return r.json


def test_support_meta(student, office):
    m = student.get("/api/support/meta").json
    assert len(m["categories"]) == 8 and len(m["priorities"]) == 4 and m["desk"] is False and len(m["score_labels"]) == 5
    assert office.get("/api/support/meta").json["desk"] is True


def test_ticket_creation_rules(student, ticket):
    assert ticket["status"] == "open" and ticket["can_reply"] and ticket["mine"] and ticket["due_at"]
    assert student.post("/api/support/tickets", {"subject": "x", "body": "long enough body"}).status == 400
    assert student.post("/api/support/tickets", {"subject": "Mövzu", "body": "qısa"}).status == 400
    odd = student.post("/api/support/tickets", {"category": "spaceship", "priority": "now", "subject": "Mövzu var", "body": "Təsvir mətni burada"}).json
    assert odd["category"] == "other" and odd["priority"] == "normal"


def test_ticket_lifecycle(student, office, ticket):
    tid = ticket["id"]
    assert any(t["id"] == tid for t in office.get("/api/support/tickets?scope=all&status=open").json)
    assert not any(t["id"] != tid and not t["mine"] for t in student.get("/api/support/tickets?scope=all").json)   # students only see their own
    r = office.post(f"/api/support/tickets/{tid}/messages", {"text": "Brauzeri yeniləyin.", "status": "waiting"}).json
    assert r["status"] == "waiting" and r["assignee"] and r["first_response_at"]
    office.post(f"/api/support/tickets/{tid}/messages", {"text": "Daxili: keş problemi", "internal": True})
    mine = student.get(f"/api/support/tickets/{tid}").json
    assert [m["internal"] for m in mine["thread"]] == [0] and len(office.get(f"/api/support/tickets/{tid}").json["thread"]) == 2
    assert student.get("/api/badges").json["support"] >= 1
    assert student.post(f"/api/support/tickets/{tid}/messages", {"text": "İndi işləyir."}).json["status"] == "in_progress"
    assert student.post(f"/api/support/tickets/{tid}/rate", {"rating": 5}).status == 409            # not resolved yet
    assert student.post(f"/api/support/tickets/{tid}/status", {"status": "closed"}).status == 403
    assert office.post(f"/api/support/tickets/{tid}/status", {"status": "sideways"}).status == 400
    res = office.post(f"/api/support/tickets/{tid}/status", {"status": "resolved", "priority": "low", "assign": "me"}).json
    assert res["status"] == "resolved" and res["priority"] == "low" and res["closed_at"]
    assert student.post(f"/api/support/tickets/{tid}/rate", {"rating": 9}).status == 400
    rated = student.post(f"/api/support/tickets/{tid}/rate", {"rating": 5}).json
    assert rated["rating"] == 5 and rated["can_rate"] is False and rated["can_reopen"] is True
    re_ = student.post(f"/api/support/tickets/{tid}/reopen").json
    assert re_["status"] == "open" and re_["rating"] is None
    office.post(f"/api/support/tickets/{tid}/status", {"status": "closed"})
    assert student.post(f"/api/support/tickets/{tid}/messages", {"text": "x"}).status == 409


def test_tickets_of_other_users_are_hidden(app_db, office):
    other = next(t for t in office.get("/api/support/tickets?scope=all").json if t["user"] != "Aysel Məmmədova")
    assert app_db.client("student").get(f"/api/support/tickets/{other['id']}").status == 404


def test_desk_queue_filters(office):
    allt = office.get("/api/support/tickets?scope=all").json
    assert all(t["category"] == "ai" for t in office.get("/api/support/tickets?scope=all&category=ai").json)
    assert all(t["status"] in ("resolved", "closed") for t in office.get("/api/support/tickets?scope=all&status=done").json)
    assert office.get(f"/api/support/tickets?scope=all&q={allt[0]['id']}").json[0]["id"] == allt[0]["id"]
    order = [t["status"] for t in allt]
    rank = {"open": 0, "in_progress": 1, "waiting": 2}
    assert [rank.get(s, 3) for s in order] == sorted(rank.get(s, 3) for s in order)


def test_thread_author_personas_are_translated(student):
    t = student.get("/api/support/tickets/1", lang="en").json
    assert "IT administrator" in {m["author"] for m in t["thread"]}


def test_support_summary(office, leader, student):
    s = leader.get("/api/support/summary").json
    assert s["total"] >= 18 and s["csat"] and len(s["by_category"]) == 8 and s["avg_first_response_h"] is not None
    assert student.get("/api/support/summary").status == 403


# ---------------------------------------------------------------- feedback
def test_feedback(student, leader):
    assert student.post("/api/feedback", {"score": 5, "area": "tutor", "comment": "Əla", "nps": 10}).json == {"ok": True}
    assert student.post("/api/feedback", {"score": 4, "area": "nowhere", "nps": 42}).status == 200
    assert student.post("/api/feedback", {"score": 9}).status == 400 and student.post("/api/feedback", {}).status == 400
    s = leader.get("/api/feedback/summary").json
    assert s["count"] >= 142 and s["nps"] is not None and len(s["weekly"]) == 8 and len(s["distribution"]) == 5
    assert sum(s["distribution"]) == s["count"] and s["recent"][0]["comment"] == "Əla"
    avgs = [a["avg"] for a in s["by_area"]]
    assert avgs == sorted(avgs, reverse=True)


# ---------------------------------------------------------------- leadership & admin
def test_analytics(leader):
    an = leader.get("/api/analytics").json
    assert len(an["kpis"]) == 8 and len(an["courses"]) == 6 and an["requests_by_type"] and len(an["labels"]) == 8
    assert an["totals"]["students"] == 120 and an["totals"]["teachers"] == 24 and an["insights"]
    assert 0 < an["attendance"]["rate"] <= 100 and 0 <= an["ai"]["cited_rate"] <= 100
    assert an["labels"][:3] == ["1-ci h.", "2-ci h.", "3-cü h."]
    assert leader.get("/api/analytics", lang="en").json["labels"][2] == "Wk 3"


def test_admin_status_never_reveals_absolute_paths(admin):
    st = admin.get("/api/admin/status").json
    assert st["engine"]["mode"] == "demo" and st["llm"]["configured"] is False
    assert st["db_path"] == "data/campus.db" and st["uploads"] == "data/uploads" and st["counts"]["users"] > 100


def test_admin_settings_are_clamped(admin):
    lim = admin.put("/api/admin/settings", {"daily_messages": 10000, "retention_days": 1, "pii_masking": 0}).json
    assert lim["daily_messages"] == 500 and lim["retention_days"] == 30 and lim["pii_masking"] is False
    lim = admin.put("/api/admin/settings", {"daily_messages": 50, "retention_days": 180, "pii_masking": True}).json
    assert lim == {**lim, "daily_messages": 50, "retention_days": 180, "pii_masking": True}


def test_llm_test_without_configuration(admin):
    r = admin.post("/api/admin/test-llm").json
    assert r["ok"] is False and "config.json" in r["message"]


def test_audit_log(admin, leader, student):
    log = admin.get("/api/admin/audit").json
    assert log and {"action", "ts", "full_name"} <= set(log[0]) and any(e["action"] == "login" for e in log)
    assert leader.get("/api/admin/audit").status == 200 and student.get("/api/admin/audit").status == 403


def test_system_status(student):
    s = student.get("/api/system/status").json
    assert len(s["components"]) == 6 and s["overall"] == "degraded"                       # the demo engine runs offline
    assert {c["key"]: c["status"] for c in s["components"]}["db"] == "operational"


# ---------------------------------------------------------------- languages
def test_errors_and_catalogue_are_translated(student):
    en = student.get("/api/news/999999", lang="en").json["error"]
    ru = student.get("/api/news/999999", lang="ru").json["error"]
    assert not AZ_LETTERS.search(en) and re.search("[а-я]", ru)
    az = student.get("/api/services").json
    en_svc = student.get("/api/services", lang="en").json
    assert en_svc["categories"][0]["name"] != az["categories"][0]["name"]
    assert [t["code"] for t in en_svc["types"]] == [t["code"] for t in az["types"]]       # codes are never translated


def test_codes_stay_untranslated(admin):
    assert admin.get("/api/bootstrap", lang="ru").json["user"]["role"] == "admin"


def test_course_headings_and_reference_titles_are_not_translated(student):
    r = student.get("/api/search?q=" + urllib.parse.quote("giriş"), lang="en").json["results"]
    titles = [x["title"] for x in r if x.get("icon") == "file"]
    assert "Giriş" in titles and "Log in" not in titles
    az, en = student.get("/api/courses/1").json, student.get("/api/courses/1", lang="en").json
    assert az["references"][0]["work"] == en["references"][0]["work"] == "University Physics Volume 2"


def test_tool_price_tone_survives_translation(teacher):
    tl = teacher.get("/api/tools", lang="en").json["tools"]
    assert any(x["price_tone"] == "free" and x["pricing"].startswith("Free") for x in tl)
    keys = {x["key"] for x in tl}
    assert "classroom50" in keys and "github_classroom" not in keys


def test_notifications_and_achievements_are_localised(app_db):
    t = app_db.client("teacher", lang="en")
    assert all(not AZ_LETTERS.search(n["title"]) for n in t.get("/api/notifications").json["items"][:5])
    ach = app_db.client().get("/api/achievements", lang="en").json
    assert not AZ_LETTERS.search(ach["items"][0]["title"])
    qs = next(x for x in ach["items"] if x["id"] == "qs-2026")
    assert qs["date"] == "2025-06-19" and len(qs["sources"]) == 2


# ---------------------------------------------------------------- reset (last: ends every session)
def test_admin_reset_reseeds_and_ends_sessions(app_db, admin, student):
    student.post("/api/feedback", {"score": 3})
    r = admin.post("/api/admin/reset")
    assert r.status == 200 and "Max-Age=0" in r.headers["Set-Cookie"]
    assert student.get("/api/me").status == 401
    fresh = app_db.client("leader").get("/api/feedback/summary").json
    assert fresh["count"] == 140
