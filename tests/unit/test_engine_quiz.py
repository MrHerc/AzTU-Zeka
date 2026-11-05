"""engine.py — answer grading, display and rule-based quiz generation."""
import random
import re

import pytest

from app import engine

MCQ = {"qtype": "mcq", "answer": 1, "options": ["Alfa", "Beta", "Qamma", "Delta"]}
TF = {"qtype": "tf", "answer": True, "options": []}
NUM = {"qtype": "numeric", "answer": 2.5, "unit": "Ω", "options": []}


# ---------------------------------------------------------------- grade
@pytest.mark.parametrize("given, ok, shown", [
    (1, True, "B"), (0, False, "A"), ("B", True, "B"), ("b)", True, "B"), ("Cavab: D", False, "D"), ("beta", True, "B"), ("BETA", True, "B"),
])
def test_grade_mcq_accepts_index_letter_or_option_text(given, ok, shown):
    assert engine.grade(MCQ, given) == (ok, shown)


def test_grade_mcq_unparseable_or_out_of_range():
    assert engine.grade(MCQ, 7) == (None, "7")
    assert engine.grade(MCQ, "bilmirəm") == (None, "bilmirəm")


@pytest.mark.parametrize("given, v", [
    (True, True), (False, False), ("Doğru", True), ("doğrudur", True), ("düz", True), ("bəli", True), ("true", True), ("hə", True),
    ("Yanlış", False), ("səhv", False), ("xeyr", False), ("false", False), ("deyil", False),
    # negation flips the word it follows (regression: "doğru deyil" used to be graded as "true")
    ("doğru deyil", False), ("düz deyil", False), ("not true", False), ("yanlış deyil", True), ("xeyr, doğru deyil", False),
])
def test_grade_tf_parses_az_and_en_words(given, v):
    assert engine.grade(TF, given) == (v == TF["answer"], "Doğru" if v else "Yanlış")


def test_grade_tf_unparseable():
    assert engine.grade(TF, "bəlkə") == (None, "bəlkə")


@pytest.mark.parametrize("given, ok, shown", [
    (2.5, True, "2.5"), ("2,5", True, "2.5"), ("cavab 2.52 Ω", True, "2.52"), (2.6, False, "2.6"), ("-1", False, "-1"),
])
def test_grade_numeric_two_percent_tolerance_and_comma_decimal(given, ok, shown):
    assert engine.grade(NUM, given) == (ok, shown)


def test_grade_numeric_small_answers_use_absolute_tolerance():
    q = {"qtype": "numeric", "answer": 0, "options": []}
    assert engine.grade(q, 0.01)[0] is True and engine.grade(q, 0.02)[0] is False
    assert engine.grade(NUM, "abc") == (None, "abc")


def test_parse_number():
    assert engine.parse_number("cavab: -3,5 A") == -3.5
    assert engine.parse_number("12") == 12.0
    assert engine.parse_number("yoxdur") is None


def test_answer_display():
    assert engine.answer_display(MCQ) == "B) Beta"
    assert engine.answer_display(TF) == "Doğru"
    assert engine.answer_display({**TF, "answer": False}) == "Yanlış"
    assert engine.answer_display(NUM) == "2.5 Ω"
    assert engine.answer_display({"qtype": "numeric", "answer": "4", "unit": ""}) == "4"


# ---------------------------------------------------------------- helpers
def test_first_sentence_and_fmt():
    assert engine._first_sentence("Birinci cümlə. İkinci cümlə.") == "Birinci cümlə"
    long = "söz " * 60
    s = engine._first_sentence(long, 50)
    assert s.endswith("…") and len(s) <= 50
    assert engine._fmt(2.5) == "2,5" and engine._fmt(3.0) == "3"


def test_numeric_templates_are_self_consistent():
    rng = random.Random(7)
    templates = engine._numeric_templates(rng)
    assert len(templates) == 19
    for trigger, build in templates:
        assert trigger == engine.fold(trigger)                 # triggers are matched against folded text
        text, ans, unit, expl, topic = build()
        assert isinstance(text, str) and text and isinstance(topic, str) and topic
        assert isinstance(ans, (int, float)) and isinstance(expl, str) and expl
        q = {"qtype": "numeric", "answer": ans, "options": [], "unit": unit}
        assert engine.grade(q, ans)[0] is True, (trigger, text, ans)
        assert engine.grade(q, str(ans).replace(".", ","))[0] is True


# ---------------------------------------------------------------- generation
GLOSS_MD = """## Əsas anlayışlar
- **Cərəyan şiddəti** — vahid zamanda keçirici kəsiyindən keçən yükün miqdarıdır.
- **Gərginlik** — iki nöqtə arasında potensiallar fərqidir, voltla ölçülür.
- **Müqavimət** — keçiricinin cərəyana göstərdiyi əks təsirdir, omla ölçülür.
- **Elektrik gücü** — vahid zamanda görülən işdir, vattla ölçülür.
- **Zaman sabiti** — RC dövrəsində kondensatorun dolma sürətini göstərən kəmiyyətdir.

## Om qanunu
Om qanunu cərəyanla gərginliyi bağlayır.
"""


def _chunks():
    return [{"id": i + 1, "heading": h, "text": t} for i, (h, t) in enumerate(engine.chunk_markdown(GLOSS_MD))]


def test_generate_questions_is_deterministic_and_well_formed():
    gl = engine.glossary(GLOSS_MD)
    a = engine.generate_questions(_chunks(), gl, 8, ("mcq", "tf", "numeric"), seed=3)
    b = engine.generate_questions(_chunks(), gl, 8, ("mcq", "tf", "numeric"), seed=3)
    assert a == b and 6 <= len(a) <= 8
    assert {q["qtype"] for q in a} == {"mcq", "tf", "numeric"}
    texts = [engine.fold(q["text"])[:80] for q in a]
    assert len(set(texts)) == len(texts)                           # no duplicates
    for q in a:
        assert q["chunk_id"] in (1, 2) and q["topic"] and q["explanation"] and q["bloom"] and q["difficulty"]
        if q["qtype"] == "mcq":
            assert len(q["options"]) == 4 and 0 <= q["answer"] < 4
            assert engine.grade(q, q["answer"])[0] is True
        elif q["qtype"] == "tf":
            assert isinstance(q["answer"], bool) and q["options"] == []
        else:
            assert q["unit"] in ("A", "Vt", "s") and engine.grade(q, q["answer"])[0] is True


def test_generate_questions_respects_requested_types_and_count():
    gl = engine.glossary(GLOSS_MD)
    only_tf = engine.generate_questions(_chunks(), gl, 3, ("tf",), seed=1)
    assert only_tf and all(q["qtype"] == "tf" for q in only_tf) and len(only_tf) <= 3
    assert len(engine.generate_questions(_chunks(), gl, 2, seed=1)) == 2


def test_generate_questions_numeric_needs_a_trigger_in_the_material():
    chunks = [{"id": 9, "heading": "Giriş", "text": "Bu material heç bir düstur mövzusuna toxunmur."}]
    assert engine.generate_questions(chunks, [], 5, ("numeric",), seed=1) == []
    chunks = [{"id": 9, "heading": "Om qanunu", "text": "Om qanunu: I = U / R."}]
    gen = engine.generate_questions(chunks, [], 5, ("numeric",), seed=1)
    assert gen and all(q["topic"] == "Om qanunu" and q["unit"] == "A" for q in gen)


def test_generate_questions_mcq_needs_at_least_four_terms():
    md = "## T\n- **A termini** — birinci anlayışın tərifi budur.\n- **B termini** — ikinci anlayışın tərifi budur.\n"
    chunks = [{"id": 1, "heading": "T", "text": md}]
    gen = engine.generate_questions(chunks, engine.glossary(md), 6, ("mcq", "tf"), seed=1)
    assert gen and all(q["qtype"] == "tf" for q in gen)


def test_generate_questions_uses_course_glossary_for_distractors():
    md = "## T\n- **Yalnız termin** — bu bölmədə tək anlayış var, distraktorlar fənn lüğətindən gəlir.\n"
    chunks = [{"id": 1, "heading": "T", "text": md}]
    course_gl = engine.glossary(GLOSS_MD)
    gen = engine.generate_questions(chunks, course_gl, 4, ("mcq",), seed=2)
    assert gen
    for q in gen:
        assert q["qtype"] == "mcq"
        assert re.search(r"Yalnız termin|hansı anlayışa aiddir", q["text"])


def test_grade_mcq_rejects_negative_index():
    # regression: -1 passed the "< len(options)" check and was graded (and shown) as option D
    assert engine.grade(MCQ, -1) == (None, "-1")
    assert engine.grade({**MCQ, "answer": 3}, -1)[0] is None
