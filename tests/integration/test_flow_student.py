"""Student portal: bootstrap, profile, home, courses, schedule, attendance, grades, notifications, search, guide."""
import urllib.parse

import pytest


def test_bootstrap_anonymous_and_signed_in(anon, student):
    b = anon.get("/api/bootstrap").json
    assert b["user"] is None and b["home"] is None and b["unread"] == 0
    assert b["app"]["version"] == "0.3" and b["app"]["langs"] == ["az", "en", "ru"] and b["app"]["engine"]["mode"] == "demo"
    assert b["app"]["contact"]["email"] == "info@aztu.edu.az"
    s = student.get("/api/bootstrap").json
    assert s["user"]["username"] == "aysel" and s["home"] == "/student" and s["unread"] >= 3


def test_profile(student):
    me = student.get("/api/me").json
    assert me["full_name"] == "Aysel Məmmədova" and me["group"] == "İT-25-1" and me["year"] == 2
    assert me["university"]["short"] == "AzTU" and me["specialty"]["years"] == 4


def test_preferences_are_validated_and_saved(student):
    r = student.put("/api/me/prefs", {"theme": "dark", "lang": "ru", "sidebar": "collapsed", "tours": ["a", "b", "a"]}).json
    assert r["prefs"] == {"theme": "dark", "lang": "ru", "sidebar": "collapsed", "tours": ["a", "b"]}
    r = student.put("/api/me/prefs", {"theme": "neon", "lang": "de", "sidebar": "wide"}).json
    assert r["prefs"]["theme"] == "dark" and r["prefs"]["lang"] == "ru"
    assert student.get("/api/me").json["prefs"]["lang"] == "ru"


def test_consent(student):
    r = student.post("/api/consent", {"ai": True})
    assert r.status == 200 and r.json["consent_at"]
    assert student.get("/api/me").json["consent_at"]


def test_student_home(student):
    h = student.get("/api/student/home").json
    assert len(h["courses"]) == 6 and h["unexcused"] == 6
    assert h["stats"]["quizzes_done"] == 3 and h["stats"]["avg_score"] is not None
    assert {"topic", "course_id", "n"} <= set(h["weak_topics"][0])
    assert all(q["can_start"] for q in h["quizzes"]) and len(h["news"]) == 4


def test_courses(student):
    cs = student.get("/api/courses").json
    assert [c["code"] for c in cs] == ["ELM-2105", "KOMP-1102", "RİY-1101", "FİZ-1103", "QRF-1104", "İNG-1105"]
    elm = cs[0]
    assert elm["teacher"] == "Rauf Əliyev" and elm["materials"] == 4 and elm["students"] == 120
    assert 0 <= elm["progress"] <= 100 and elm["attendance"]["planned"] == 45 and elm["attendance"]["limit"] == 11
    assert elm["next"]["weekday"] and elm["modes"] == ["socratic", "explain", "practice"]


def test_course_detail_and_material_viewer(student):
    cd = student.get("/api/courses/1").json
    assert len(cd["materials_list"]) == 4 and cd["tools"] and len(cd["schedule"]) == 3 and cd["quizzes"]
    assert cd["references"] and cd["references_checked"] and "insights" not in cd          # insights are for teachers
    m = student.get(f"/api/materials/{cd['materials_list'][0]['id']}").json
    assert m["chunks"] and m["glossary"] and m["references"] and m["text"].startswith("#")
    chunk = student.get(f"/api/source/chunk/{m['chunks'][0]['id']}").json
    assert chunk["course"] == "Elektrik dövrələrinin nəzəriyyəsi" and chunk["material"] == m["title"]
    assert student.get("/api/materials/99999").status == 404 and student.get("/api/source/chunk/99999").status == 404


def test_schedule(student):
    s = student.get("/api/schedule").json
    assert len(s["days"]) == 5 and sum(len(d["items"]) for d in s["days"]) == 15
    assert all(it["teacher"] and it["course"] for d in s["days"] for it in d["items"])
    assert sum(d["today"] for d in s["days"]) <= 1


def test_attendance_and_absences(student):
    a = student.get("/api/attendance").json
    assert len(a["courses"]) == 6 and a["semester_start"]
    absent = [r for r in a["records"] if r["status"] == "absent"]
    assert len(absent) == 6 and all(r["pending_request"] is None for r in absent)
    days = sorted({r["day"] for r in absent})
    assert len(days) == 2
    ab = student.get(f"/api/me/absences?from={days[0]}&to={days[-1]}").json
    assert len(ab) == 6 and student.get(f"/api/me/absences?from={days[-1]}&to={days[-1]}").json.__len__() < 6


def test_grades(student):
    g = student.get("/api/grades").json
    assert len(g["courses"]) == 6 and len(g["past"]) == 2 and g["credits"] > 0 and 78 <= g["average"] <= 98
    comp = {i["name"]: i for i in g["courses"][0]["items"]}
    assert comp["Kollokvium 1"]["score"] is None and comp["Sərbəst iş 1"]["score"] is not None
    assert 0 < comp["Davamiyyət"]["score"] <= 10
    assert g["courses"][0]["semester"] == pytest.approx(sum(i["score"] or 0 for i in g["courses"][0]["items"]), abs=0.11)


def test_notifications_and_badges(student):
    n = student.get("/api/notifications").json
    assert n["unread"] >= 3 and len(n["items"]) >= 4
    first = next(x for x in n["items"] if not x["read_at"])
    assert student.post("/api/notifications/read", {"ids": [first["id"]]}).json["unread"] == n["unread"] - 1
    b = student.get("/api/badges").json
    assert b["absences"] == 6 and b["requests"] >= 1 and {"notifications", "news", "support"} <= set(b)
    assert student.post("/api/notifications/read", {"all": True}).json["unread"] == 0
    assert student.get("/api/badges").json["notifications"] == 0


@pytest.mark.parametrize("q, group", [("arayış", "E-xidmətlər"), ("hakaton", "Xəbərlər"), ("GreenMetric", "AzTU-nun nailiyyətləri"),
                                      ("Fizika", "Fənlər"), ("paralel birləşmə", "Fənn materialları"), ("bələdçi", None)])
def test_search(student, q, group):
    r = student.get("/api/search?q=" + urllib.parse.quote(q)).json["results"]
    if group:
        assert any(x["group"] == group for x in r), [x["group"] for x in r]
    assert len(r) <= 24


def test_search_ignores_short_queries(student):
    assert student.get("/api/search?q=a").json == {"results": []} and student.get("/api/search").json == {"results": []}


def test_guide_is_role_specific(student, teacher):
    s, t = student.get("/api/guide").json, teacher.get("/api/guide").json
    assert len(s["articles"]) >= 8 and s["faq"] and s["shortcuts"]
    assert {a["id"] for a in s["articles"]} != {a["id"] for a in t["articles"]}


def test_public_achievements_and_contacts(anon):
    ach = anon.get("/api/achievements", lang="en").json
    assert len(ach["items"]) == 18 and len(ach["categories"]) == 6 and sum(c["n"] for c in ach["categories"]) == 18
    dated = [i["date"] for i in ach["items"] if i["date"]]
    assert dated == sorted(dated, reverse=True)
    ct = anon.get("/api/contact").json
    assert ct["phone"] == "+994 12 539 13 48" and len(ct["social"]) == 4
