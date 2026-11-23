"""Zəka Radar: explainable early warning, support plans (teacher → student), privacy and roles.

These are the 26 "radar:" checks of the former ``tests/selftest.py``, ported one for one: one test per check, in the
same order, each with the name the check had there. The tests build on each other (one database for the module): the
dashboard is read first, then a plan is sent to the storyline student Murad, who works through it.
"""
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from zeka.legacy import radar, store

AZ_LETTERS = re.compile(r"[əğıöüşçƏĞİÖÜŞÇ]")
COURSE = 1          # ELM-2105, taught by the demo teacher


@pytest.fixture(scope="module")
def story(app_db):
    """Ids of the synthetic storyline students: murad, elnur, nermin, fidan, kamran, lale."""
    return app_db.client().get("/api/demo/storyline").json["students"]


@pytest.fixture(scope="module")
def dashboard(teacher):
    """The teacher's radar before any plan is sent by these tests."""
    r = teacher.get("/api/radar")
    assert r.status == 200, r.text
    return r.json


@pytest.fixture(scope="module")
def profile(teacher, story):
    r = teacher.get(f"/api/radar/student/{story['murad']}?course={COURSE}")
    assert r.status == 200, r.text
    return r.json


@pytest.fixture(scope="module")
def sent(teacher, story):
    """The plan the teacher sends to Murad (created by the first test that asks for it)."""
    return teacher.post(f"/api/radar/student/{story['murad']}/plan", {"course_id": COURSE, "kind": "plan", "note": "Birlikdə bərpa edək."})


@pytest.fixture(scope="module")
def murad(app_db):
    """A client signed in as the storyline student (demo login with ``user``)."""
    c = app_db.client()
    assert c.post("/api/auth/demo", {"role": "student", "user": "murad"}).status == 200
    return c


@pytest.fixture(scope="module")
def own_plan(murad, sent):
    """Murad's plan as he sees it right after it was sent."""
    r = murad.get("/api/student/plans")
    assert r.status == 200 and r.json["items"], r.text
    return r.json["items"][0]


# ---------------------------------------------------------------- dashboard
def test_teacher_sees_own_course(dashboard):
    # radar: teacher sees own course
    assert dashboard["scope"]["selected"] == COURSE and dashboard["counts"]["students"] == 120, dashboard["counts"]


def test_murad_is_ranked_first_with_a_reason(dashboard, story):
    top = dashboard["rows"][0]
    # radar: Murad ranked first, high risk, with a reason
    assert top["id"] == story["murad"] and top["level"] == "high" and top["why"], top


def test_storyline_levels(dashboard, story):
    lv = {r["id"]: r["level"] for r in dashboard["rows"]}
    # radar: storylines (Elnur and Nərmin watch, Lalə ok)
    assert lv.get(story["elnur"]) == "watch" and lv.get(story["nermin"]) == "watch" and lv.get(story["lale"]) == "ok", \
        {k: lv.get(v) for k, v in story.items()}


def test_realistic_cohort(dashboard):
    # radar: realistic cohort (few high, some watch)
    assert 1 <= dashboard["counts"]["high"] <= 6 and 4 <= dashboard["counts"]["watch"] <= 25, dashboard["counts"]


def test_earlier_plans_are_measured_as_improved(dashboard):
    im = dashboard["impact"]
    # radar: earlier plans measured as improved
    assert im["measured"] >= 2 and im["improved"] == im["measured"] and im["avg_delta"] < 0, im


def test_weekly_trend_and_cohort_gaps(dashboard):
    # radar: weekly trend + cohort gaps
    assert len(dashboard["trend"]) >= 2 and dashboard["gaps"] and dashboard["gaps"][0]["chunk_id"], dashboard["trend"]


# ---------------------------------------------------------------- explainable profile
def test_score_is_the_sum_of_its_drivers(profile):
    p = profile["profile"]
    # radar: score is the sum of its drivers
    assert abs(sum(d["points"] for d in p["drivers"]) - p["score"]) < 0.2 and all(d["evidence"] for d in p["drivers"][:3]), p


def test_recommendation_is_a_plan_and_copies_the_deans_office(profile):
    rec = profile["profile"]["recommendation"]
    # radar: recommendation is a plan and copies the dean's office
    assert rec["kind"] == "plan" and rec["cc_office"], rec


def test_profile_history_and_lessons(profile):
    # radar: profile history and lessons
    assert profile["history"][-1]["score"] == profile["profile"]["score"] and profile["lessons"] and profile["cohort"]["rank"] == 1


def test_excused_absences_never_count(teacher, story):
    r = teacher.get(f"/api/radar/student/{story['lale']}?course={COURSE}")
    p = r.json["profile"]
    # radar: excused absences never count
    assert r.status == 200 and p["level"] == "ok" and p["drivers"]
    assert any("üzrlü" in e for d in p["drivers"] for e in d["evidence"])
    assert next(d for d in p["drivers"] if d["key"] == "attendance")["points"] == 0


# ---------------------------------------------------------------- support plan: preview, roles, sending
def test_plan_preview_cites_the_lecture(teacher, story):
    r = teacher.post(f"/api/radar/student/{story['murad']}/plan", {"course_id": COURSE, "preview": True})
    assert r.status == 200, r.text
    plan = r.json["plan"]
    kinds = [x["kind"] for x in plan["steps"]]
    # radar: plan preview cites the lecture
    assert kinds[:2] == ["read", "practice"] and "attend" in kinds and plan["steps"][0]["cites"] and plan["topics"][0] == "Kirxhofun birinci qanunu", plan


def test_preview_does_not_create_a_plan(teacher, story, dashboard):
    assert teacher.post(f"/api/radar/student/{story['murad']}/plan", {"course_id": COURSE, "preview": True}).status == 200
    # radar: preview does not create a plan
    assert teacher.get("/api/radar").json["impact"]["plans"] == dashboard["impact"]["plans"]


def test_leadership_reads_but_cannot_send_plans(leader, story):
    # radar: leadership reads, cannot send plans
    assert leader.get("/api/radar").status == 200
    assert leader.post(f"/api/radar/student/{story['murad']}/plan", {"course_id": COURSE}).status == 403


def test_students_cannot_open_the_radar(student, story):
    # radar: students cannot open the radar
    assert student.get("/api/radar").status == 403 and student.get(f"/api/radar/student/{story['murad']}").status == 403


def test_plan_sent(sent):
    # radar: plan sent
    assert sent.status == 200 and sent.json["intervention"]["status"] == "open" and sent.json["intervention"]["progress"]["total"] >= 4, sent.text


def test_one_open_plan_per_student_and_course(teacher, story, sent):
    # radar: one open plan per student and course
    assert teacher.post(f"/api/radar/student/{story['murad']}/plan", {"course_id": COURSE}).status == 409


def test_deans_office_is_copied_on_attendance(office, sent):
    titles = [n["title"] for n in office.get("/api/notifications").json["items"]]
    # radar: dean's office copied on attendance
    assert any("Radar" in t for t in titles), titles[:4]


# ---------------------------------------------------------------- the student's side
def test_student_sees_the_plan_never_a_risk_score(own_plan, sent):
    # radar: student sees the plan, never a risk score
    assert own_plan["id"] == sent.json["id"] and "risk_before" not in own_plan and "drivers" not in own_plan and own_plan["note"], own_plan


def test_student_badge(murad, sent):
    # radar: student badge
    assert murad.get("/api/badges").json.get("plan") == 1


def test_step_ticks_itself_from_tutor_activity(murad, own_plan):
    topic = own_plan["plan"]["steps"][0]["topic"]
    assert murad.post(f"/api/tutor/{COURSE}/ask", {"message": topic + " mövzusunu izah et", "mode": "explain"}).status == 200
    r = murad.get(f"/api/student/plans/{own_plan['id']}")
    step = r.json["plan"]["steps"][0]
    # radar: step ticks itself from tutor activity
    assert r.status == 200 and step["done"] and step["auto"], step


def test_manual_step_toggle(murad, own_plan):
    r = murad.post(f"/api/student/plans/{own_plan['id']}/steps", {"index": len(own_plan["plan"]["steps"]) - 1, "done": True})
    # radar: manual step toggle
    assert r.status == 200 and r.json["plan"]["steps"][-1]["done"] and r.json["progress"]["done"] == 2, r.text


def test_plans_are_private_to_their_student(student, own_plan):
    # radar: plans are private to their student
    assert student.get(f"/api/student/plans/{own_plan['id']}").status == 404


def test_completed_plan_closes_and_tells_the_teacher(murad, teacher, own_plan):
    for i in range(len(own_plan["plan"]["steps"])):
        murad.post(f"/api/student/plans/{own_plan['id']}/steps", {"index": i, "done": True})
    done = murad.get(f"/api/student/plans/{own_plan['id']}").json
    titles = [n["title"] for n in teacher.get("/api/notifications").json["items"]]
    # radar: completed plan closes and tells the teacher
    assert done["status"] == "completed" and any("tamamladı" in t for t in titles), (done["status"], titles[:4])


# ---------------------------------------------------------------- language, model, leadership
def test_explanations_are_translated(teacher, story):
    r = teacher.get(f"/api/radar/student/{story['murad']}?course={COURSE}", lang="en")
    top = r.json["profile"]["drivers"][0]
    # radar: explanations translated
    assert r.status == 200 and top["label"] in ("Attendance", "Assessment", "Concept gap") and not AZ_LETTERS.search(top["evidence"][0]), top


def test_no_alarm_from_too_little_data(app_db, story):
    c = store.connect()
    try:
        frame = radar.Frame(c, [COURSE])
        early = radar.profile(frame, story["murad"], COURSE, frame.semester_start + timedelta(days=3))
    finally:
        c.close()
    # radar: no alarm from too little data
    assert early["level"] == "ok" and early["confidence"] == "low", early["score"]


def test_leadership_insight(leader):
    r = leader.get("/api/analytics")
    # radar: leadership insight
    assert r.status == 200 and any(i.get("link") == "/radar" for i in r.json["insights"])


# ---------------------------------------------------------------- Task 42 (PERF-F1): the dashboard reads the periodic summary
def _db(fn):
    c = store.connect()
    try:
        out = fn(c)
        c.commit()
        return out
    finally:
        c.close()


def test_the_leadership_dashboard_and_the_staff_badge_read_the_summary_never_the_analysis(leader, office, monkeypatch):
    live = _db(lambda c: (radar.analysis(c).counts(), radar.impact(c, radar.analysis(c))))
    s = _db(radar.summarize)                     # what the job radar.summary writes every 15 minutes
    assert {k: s[k] for k in ("high", "watch", "ok", "students", "measured", "improved")} == {
        **live[0], "measured": live[1]["measured"], "improved": live[1]["improved"]}, "the summary is the live analysis"

    def analysed(*_a, **_k):
        raise AssertionError("the campus-wide analysis ran in a request")
    monkeypatch.setattr(radar, "analysis", analysed)
    at = datetime.fromisoformat(s["at"])
    for lang, fmt in (("az", "%d.%m.%Y %H:%M"), ("en", "%d/%m/%Y %H:%M")):       # the reader's date format (Checkpoint F, L15)
        r = leader.get("/api/analytics", lang=lang)
        assert r.status == 200, r.text
        line = next(i for i in r.json["insights"] if i.get("link") == "/radar")
        assert line["at"] == s["at"] and at.strftime(fmt) in line["text"] and f"{s['high']} " in line["text"], line
    assert leader.get("/api/badges").json["radar"] == s["high"] and office.get("/api/badges").json["radar"] == s["high"]

    _db(lambda c: c.execute("DELETE FROM settings WHERE key='radar_summary'"))     # before the job's first run
    line = next(i for i in leader.get("/api/analytics").json["insights"] if i.get("link") == "/radar")
    assert line["at"] is None and "hesablanmayıb" in line["text"] and "radar" not in leader.get("/api/badges").json
    monkeypatch.undo()
    _db(radar.summarize)


def test_the_dashboard_s_radar_card_is_the_summary_too(leader, monkeypatch):
    """Checkpoint F (F1): the dashboard's Radar card asked GET /api/radar, the live campus-wide analysis (seconds on a
    university's data), and could disagree with the summary line above it. /api/analytics carries the summary."""
    an = _db(radar.analysis)
    s = _db(radar.summarize)
    top = sorted((x for x in an.course_counts() if x["high"] or x["watch"]), key=lambda x: -(x["high"] * 3 + x["watch"]))[:4]
    assert s["courses"] and [x["id"] for x in s["courses"]] == [x["id"] for x in top]
    assert s["avg_delta"] == _db(lambda c: radar.impact(c, an)["avg_delta"])
    assert len(s["trend"]) > 1 and s["trend"][-1] == {"week_start": s["at"][:10], "high": s["high"], "watch": s["watch"]}

    def analysed(*_a, **_k):
        raise AssertionError("the campus-wide analysis ran in a request")
    monkeypatch.setattr(radar, "analysis", analysed)
    assert leader.get("/api/analytics").json["radar"] == s
    src = (Path(__file__).resolve().parents[2] / "frontend" / "js" / "radar.js").read_text(encoding="utf-8")
    card = src[src.index("export function radarLeaderCard"):]
    assert "/api/radar" not in card[:card.index("\n}\n")], "the card asks for the live analysis"
