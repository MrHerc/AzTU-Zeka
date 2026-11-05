"""Integrity of the demo content in content/: every reference resolves, every quiz answer is gradable, links are https."""
import json
import re
from pathlib import Path

import pytest

from app import engine, store

CONTENT = Path(__file__).resolve().parents[2] / "content"
FIELD_TYPES = {"text", "textarea", "radio", "select", "number", "date", "daterange", "course", "courses", "absences"}


def load(name):
    return json.loads((CONTENT / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def seed():
    return load("seed.json")


@pytest.mark.parametrize("name", sorted(p.name for p in CONTENT.glob("*.json")))
def test_json_files_parse(name):
    assert isinstance(load(name), dict)


def test_users_and_demo_logins(seed):
    names = [u["username"] for u in seed["users"]]
    assert len(names) == len(set(names))
    roles = {u["username"]: u["role"] for u in seed["users"]}
    assert {role: roles[user] for role, user in seed["demo_logins"].items()} == {r: r for r in seed["demo_logins"]}
    groups = {g["name"] for g in seed["groups"]}
    assert all(u.get("group") in groups for u in seed["users"] if u["role"] == "student")


def test_courses(seed):
    users = {u["username"]: u for u in seed["users"]}
    tools = {t["key"] for t in load("tools.json")["tools"]}
    for co in seed["courses"]:
        assert users[co["teacher"]]["role"] == "teacher"
        for fname, title in co["materials"]:
            text = (CONTENT / "materials" / fname).read_text(encoding="utf-8")
            assert engine.chunk_markdown(text) and title
        for wd, start, end, kind, room in co["schedule"]:
            assert 1 <= wd <= 5 and re.fullmatch(r"\d\d:\d\d", start) and re.fullmatch(r"\d\d:\d\d", end) and start < end and kind and room
        assert set(co["tools"]) <= tools


def test_every_material_file_is_used(seed):
    used = {f for co in seed["courses"] for f, _ in co["materials"]}
    assert used == {p.name for p in (CONTENT / "materials").glob("*.md")}


def test_question_bank_answers_are_gradable(seed):
    codes = {co["code"]: co for co in seed["courses"]}
    for q in seed["question_bank"]:
        assert q["course"] in codes and 0 <= q["material"] < len(codes[q["course"]]["materials"])
        if q["qtype"] == "mcq":
            assert isinstance(q["answer"], int) and 0 <= q["answer"] < len(q["options"]) and len(q["options"]) >= 3
        elif q["qtype"] == "tf":
            assert isinstance(q["answer"], bool)
        else:
            assert isinstance(q["answer"], (int, float)) and not isinstance(q["answer"], bool)
        assert engine.grade(q, q["answer"])[0] is True, q["text"]


def test_quizzes_reference_questions_of_their_own_course(seed):
    bank = seed["question_bank"]
    titles = {qz["title"] for qz in seed["quizzes"]}
    for qz in seed["quizzes"]:
        assert qz["questions"] and all(bank[i]["course"] == qz["course"] for i in qz["questions"])
        assert qz["kind"] in ("practice", "graded") and qz["time_limit"] > 0 and qz["attempts"] > 0
    for title, pattern in seed["demo_attempts"]:
        qz = next(q for q in seed["quizzes"] if q["title"] == title)
        assert title in titles and len(pattern) == len(qz["questions"])


def test_request_types(seed):
    cats = {c["key"] for c in seed["service_categories"]}
    codes = [rt["code"] for rt in seed["request_types"]]
    assert len(codes) == len(set(codes)) == 13
    for rt in seed["request_types"]:
        assert rt["category"] in cats and rt["sla_hours"] > 0 and rt["steps"] and rt["prefix"]
        names = [f["name"] for f in rt["fields"]]
        assert len(names) == len(set(names)), rt["code"]
        for f in rt["fields"]:
            assert f["type"] in FIELD_TYPES and f["label"], (rt["code"], f)
            if f["type"] in ("radio", "select"):
                assert f["options"] and len(set(f["options"])) == len(f["options"])
            for k, v in (f.get("show_if") or {}).items():
                ref = next(x for x in rt["fields"] if x["name"] == k)
                assert v in ref["options"]
        att = rt.get("attachments")
        if att:
            assert att["label"] and att.get("accept", "doc") in ("doc", "image") and att.get("max", 3) >= 1


def test_campus_kb_actions_point_to_real_services(seed):
    codes = {rt["code"] for rt in seed["request_types"]}
    entries = store._parse_kb((CONTENT / "campus_kb.md").read_text(encoding="utf-8"))
    assert len(entries) >= 10
    for heading, text, req, _label, source in entries:
        assert heading and len(text) > 40 and source
        assert req is None or req in codes, (heading, req)


def test_academy(seed):
    ac = load("academy.json")
    keys = [t["key"] for t in ac["tracks"]]
    assert len(keys) == len(set(keys)) == 7
    for t in ac["tracks"]:
        assert t["modules"] and t["outcomes"]
        for m in t["modules"]:
            assert m["minutes"] > 0 and m["paragraphs"] and m["task"]
            for item in m["quiz"]:
                assert 0 <= item["a"] < len(item["o"]) and item["q"]
    assert {s["track"] for s in ac["self_assessment"]} <= set(keys)


def test_news_events():
    news = load("news.json")
    for n in news["news"]:
        assert n["kind"] in news["kinds"] and n["audience"] in ("all", "students", "teachers") and n["title"] and n["summary"]
        ev = n.get("event")
        if ev:
            assert re.fullmatch(r"\d\d:\d\d", ev["time"]) and ev["duration_h"] > 0 and ev["location"]
            assert ev["capacity"] is None or ev["capacity"] >= 0          # 0 = unlimited
            assert not ev["registration"] or ev["capacity"]               # registration needs a seat limit


def test_guide_and_tools():
    guide = load("guide.json")
    roles = {"student", "teacher", "office", "leader", "admin"}
    ids = [a["id"] for a in guide["articles"]]
    assert len(ids) == len(set(ids)) and all(set(a["roles"]) <= roles and a["steps"] for a in guide["articles"])
    assert all(set(f["roles"]) <= roles for f in guide["faq"])
    tools = load("tools.json")
    keys = [t["key"] for t in tools["tools"]]
    assert len(keys) == len(set(keys))
    for t in tools["tools"]:
        assert (t["url"] == "" and t["key"] == "zeka") or t["url"].startswith("https://")     # the platform itself has no external link
        assert set(t["areas"]) <= set(tools["areas"])
    assert all(set(v) <= set(tools["areas"]) for v in tools["dept_areas"].values())


def test_achievements_and_contacts_are_sourced_https():
    ach = load("achievements.json")
    cats = {c["key"] for c in ach["categories"]}
    ids = [i["id"] for i in ach["items"]]
    assert len(ids) == len(set(ids))
    for item in ach["items"]:
        assert item["category"] in cats and item["sources"]
        assert all(src["url"].startswith("https://") for src in item["sources"])
        assert item["date"] == "" or item["date"] is None or re.fullmatch(r"\d{4}-\d\d-\d\d", item["date"])
    ct = load("contacts.json")
    assert all(x["url"].startswith("https://") for x in ct["social"] + ct["systems"])


def test_references_point_to_existing_courses_materials_and_modules(seed):
    r = load("references.json")
    assert set(r["courses"]) <= {co["code"] for co in seed["courses"]}
    assert set(r["materials"]) <= {p.name for p in (CONTENT / "materials").glob("*.md")}
    tracks = {t["key"]: len(t["modules"]) for t in load("academy.json")["tracks"]}
    for key in r["academy"]:
        track, seq = key.split("/")
        assert track in tracks and 1 <= int(seq) <= tracks[track]
