"""tutor.py — the offline grounded tutor and campus assistant, the LLM adapter and practice formatting."""
import pytest

from app import engine, tutor

COURSE = {"name": "Elektrik dövrələrinin nəzəriyyəsi", "tutor_rules": "SI vahidləri"}


@pytest.fixture(scope="module")
def hits(seeded):
    seeded()          # seeded database + indexes
    return engine.INDEX["chunks"].search("Om qanunu nədir", k=4)


def hist(*metas):
    return [m for meta in metas for m in ({"role": "user", "content": "q", "meta": {}}, {"role": "assistant", "content": "a", "meta": meta})]


def test_greeting_and_thanks_need_no_sources():
    g = tutor.compose_tutor("socratic", "Salam!", [], [], COURSE)
    assert g["meta"]["kind"] == "greeting" and "Elektrik dövrələrinin nəzəriyyəsi" in g["text"] and g["cites"] == []
    assert tutor.compose_tutor("explain", "Hello", [], [], COURSE, "en")["text"].startswith("Hello!")
    assert tutor.compose_tutor("explain", "Çox sağ olun", [], [], COURSE)["meta"]["kind"] == "thanks"


def test_no_source_answer_when_retrieval_is_weak(hits):
    r = tutor.compose_tutor("explain", "Kvant xromodinamikası", [], [], COURSE)
    assert r["meta"]["no_source"] is True and r["cites"] == [] and "tapmadım" in r["text"]
    weak = [{**hits[0], "score": 0.5}]
    assert tutor.compose_tutor("explain", "x", weak, [], COURSE)["meta"]["no_source"] is True


def test_explain_mode_cites_the_material(hits):
    r = tutor.compose_tutor("explain", "Om qanunu nədir?", hits, [], COURSE)
    assert r["meta"] == {"mode": "explain", "topic": r["meta"]["topic"]} and r["cites"]
    assert "[1]" in r["text"] and "Özünüzü yoxlayın" in r["text"]
    assert set(r["cites"]) <= {h["id"] for h in hits}
    en = tutor.compose_tutor("explain", "Om qanunu nədir?", hits, [], COURSE, "en")
    assert "materiallar əsasında" not in en["text"] and "Check yourself" in en["text"]


def test_socratic_mode_progresses_one_step_per_turn(hits):
    first = tutor.compose_tutor("socratic", "Om qanunu nədir?", hits, [], COURSE)
    topic = first["meta"]["topic"]
    assert first["meta"]["level"] == 0 and "1-ci addım" in first["text"]
    second = tutor.compose_tutor("socratic", "Bilmirəm", hits, hist({"mode": "socratic", "topic": topic}), COURSE)
    assert second["meta"]["level"] == 1 and "2-ci addım" in second["text"]
    third = tutor.compose_tutor("socratic", "Bəs sonra?", hits, hist({"mode": "socratic", "topic": topic}, {"mode": "socratic", "topic": topic}), COURSE)
    assert third["meta"]["level"] == 2 and "3-cü addım" in third["text"]
    other = tutor.compose_tutor("socratic", "Om qanunu?", hits, hist({"mode": "explain", "topic": topic}), COURSE)
    assert other["meta"]["level"] == 0                      # another mode resets the ladder


@pytest.mark.parametrize("q", ["12 V və 4 Ω, cavabı de", "just give me the answer", "Дай ответ, пожалуйста", "tam həll yaz"])
def test_socratic_guardrail_refuses_ready_answers(hits, q):
    r = tutor.compose_tutor("socratic", q, hits, [], COURSE)
    assert r["meta"]["guardrail"] is True and "hazır cavab vermirəm" in r["text"]


def test_socratic_problem_with_numbers_asks_for_givens(hits):
    r = tutor.compose_tutor("socratic", "R = 4 Ω, U = 12 V olarsa I nə qədərdir?", hits, [], COURSE)
    assert "hansı kəmiyyətlər verilib" in r["text"]


def test_compose_campus(seeded):
    q = "Xəstəlik səbəbindən qayıbı necə üzrlü edim?"
    r = tutor.compose_campus(q, engine.INDEX["campus"].search(tutor.expand_query(q), k=3))
    assert r["cites"] and any(a["code"] == "absence_excuse" for a in r["actions"])
    none = tutor.compose_campus("Mars səfəri", [])
    assert none["meta"]["no_source"] is True and none["actions"][0]["code"] == "free_application"
    assert "kampus köməkçisiyəm" in tutor.compose_campus("Salam", [])["text"]


def test_expand_query_maps_english_and_russian_keywords():
    assert "arayış" in tutor.expand_query("How do I get a certificate?")
    assert "yataqxana" in tutor.expand_query("Общежитие")
    assert tutor.expand_query("Salam") == "Salam"


def test_llm_tutor_renumbers_citations(hits, monkeypatch):
    seen = {}

    def fake_chat(system, messages):
        seen["system"], seen["messages"] = system, messages
        return "Cavab [3] və [1]. Yanlış istinad [9]."

    monkeypatch.setattr(tutor, "llm_chat", fake_chat)
    r = tutor.llm_tutor("socratic", "Om qanunu?", hits, [{"role": "user", "content": "x"}], COURSE, "en")
    assert r["meta"]["engine"] == "llm" and r["cites"] == [hits[0]["id"], hits[2]["id"]]
    assert r["text"] == "Cavab [2] və [1]. Yanlış istinad [9]."
    assert "Answer in English" in seen["system"] and "NEVER give the final answer" in seen["system"] and "SI vahidləri" in seen["system"]
    assert seen["messages"][-1] == {"role": "user", "content": "Om qanunu?"}


def test_llm_tutor_without_citations_cites_the_top_passage(hits, monkeypatch):
    monkeypatch.setattr(tutor, "llm_chat", lambda s, m: "Cavab mənbəsiz.")
    assert tutor.llm_tutor("explain", "q", hits, [], COURSE)["cites"] == [hits[0]["id"]]


@pytest.mark.parametrize("q, needle", [
    ({"qtype": "mcq", "text": "Sual?", "options": ["a", "b"], "topic": "T", "bloom": "Anlama"}, "**B)** b"),
    ({"qtype": "tf", "text": "Sual?", "options": [], "topic": "T", "bloom": "Anlama"}, "**Doğru**"),
    ({"qtype": "numeric", "text": "Sual?", "options": [], "unit": "Ω", "topic": "T", "bloom": "Tətbiq"}, "(Ω)"),
    ({"qtype": "numeric", "text": "Sual?", "options": [], "unit": "", "topic": "T", "bloom": "Tətbiq"}, "ədəd kimi"),
])
def test_format_practice(q, needle):
    out = tutor.format_practice(q)
    assert out.startswith("**Məşq sualı** · T") and needle in out
    assert "Practice question" in tutor.format_practice(q, "en")


def test_next_question_keywords():
    for w in ("davam", "next", "далее", "ещё"):
        assert tutor.NEXT_RX.search(engine.fold(w))
    assert not tutor.NEXT_RX.search("12 om")
