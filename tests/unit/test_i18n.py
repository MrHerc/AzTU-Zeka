"""i18n.py — catalog lookup, plurals, formatting, localisation of API responses."""
import json

import pytest

from app import i18n
from app.i18n import L, S, T3, canon, is_i18n, join3, localize, norm_lang, num3, tr, tr3


@pytest.mark.parametrize("v, out", [("az", "az"), ("EN", "en"), ("ru-RU", "ru"), (" en ", "en"), ("de", None), ("", None), (None, None), (5, None)])
def test_norm_lang(v, out):
    assert norm_lang(v) == out


@pytest.mark.parametrize("n, key", [(1, "one"), (21, "one"), (2, "few"), (4, "few"), (22, "few"), (5, "many"), (11, "many"), (12, "many"),
                                    (14, "many"), (0, "many"), (111, "many"), (-3, "few"), ("x", "many")])
def test_russian_plural_rules(n, key):
    assert i18n._plural("ru", n, {"one": "one", "few": "few", "many": "many"}) == key


def test_english_plural_and_fallbacks():
    f = {"one": "a question", "other": "questions"}
    assert i18n._plural("en", 1, f) == "a question" and i18n._plural("en", 2, f) == "questions" and i18n._plural("en", 0, f) == "questions"
    assert i18n._plural("ru", 3, {"other": "x"}) == "x"


def test_tr_uses_the_catalog_and_falls_back_to_the_source():
    assert tr("Daxil olmamısınız", "en") == "You are not signed in"
    assert tr("Bu mətn kataloqda yoxdur", "en") == "Bu mətn kataloqda yoxdur"
    assert tr("Daxil olmamısınız", "az") == "Daxil olmamısınız"
    assert tr("", "en") == "" and tr(None, "en") is None and tr(5, "en") == 5


def test_s_formats_and_translates_params():
    assert S("{course} · {n} sual", "en", course="X", n=1) == "X · 1 question"
    assert S("{course} · {n} sual", "en", course="X", n=3) == "X · 3 questions"
    assert S("{course} · {n} sual", "ru", course="X", n=3) == "X · 3 вопроса"
    assert S("{course} · {n} sual", "az", course="X", n=3) == "X · 3 sual"
    # i18n dict parameters resolve to the target language
    assert S("Mənbə: {ref}", "en", ref={"az": "a", "en": "e", "ru": "r"}).endswith("e")
    assert S("Salam {x}", "az") == "Salam {x}"                 # missing parameter: left as written, no crash


def test_t3_and_tr3_and_j3():
    d = T3("Daxil olmamısınız")
    assert is_i18n(d) and d["en"] == "You are not signed in" and d["az"] == "Daxil olmamısınız" and d["ru"]
    assert tr3("Daxil olmamısınız") == d and tr3("") == "" and tr3(None) is None
    assert json.loads(i18n.J3("Daxil olmamısınız")) == d and i18n.J3("") == ""


def test_is_i18n_and_L():
    d = {"az": "A", "en": "E", "ru": ""}
    assert is_i18n(d) and not is_i18n({"az": "A", "en": "E"}) and not is_i18n("x")
    assert L(d, "en") == "E" and L(d, "ru") == "A"            # empty translation falls back to Azerbaijani
    assert L(json.dumps(d), "en") == "E" and L('{"az" broken', "en") == '{"az" broken' and L("plain", "en") == "plain"


def test_localize_walks_nested_structures():
    obj = {"title": {"az": "A", "en": "E", "ru": "R"}, "items": [{"name": "Yeni"}, '{"az": "x", "en": "y", "ru": "z"}'], "n": 5, "none": None}
    assert localize(obj, "en") == {"title": "E", "items": [{"name": "New"}, "y"], "n": 5, "none": None}


def test_localize_never_translates_user_content_or_codes():
    obj = {"content": "Yeni", "question": "Yeni", "heading": "Giriş", "username": "Yeni", "status": "open", "role": "student", "label": "Giriş"}
    out = localize(obj, "en")
    assert out["content"] == out["question"] == out["username"] == "Yeni"
    assert out["heading"] == "Giriş" and out["label"] != "Giriş"
    assert out["status"] == "open" and out["role"] == "student"


def test_localize_composite_strings():
    assert localize("İT korpusu, 214", "en") == "IT building, 214"
    assert localize("Sertifikat: Təhsildə süni intellekt", "en") == "Certificate: Artificial intelligence in education"
    assert localize("Naməlum hissə, 214", "en") == "Naməlum hissə, 214"           # every textual part must be known
    assert localize("Yeni", "az") == "Yeni"


def test_canon_maps_translated_option_labels_back():
    opts = ["Azərbaycan dili", "İngilis dili"]
    assert canon("İngilis dili", opts) == "İngilis dili"
    assert canon(tr("İngilis dili", "en"), opts) == "İngilis dili"
    assert canon(tr("İngilis dili", "ru"), opts) == "İngilis dili"
    assert canon("Klingon", opts) == "Klingon"


def test_num3_and_join3():
    assert num3(3.14159, 2) == {"az": "3,14", "en": "3.14", "ru": "3,14"}
    assert num3(5.0) == {"az": "5", "en": "5", "ru": "5"} and num3(7.6, 0) == {"az": "8", "en": "8", "ru": "8"}
    assert join3([{"az": "a", "en": "b", "ru": "c"}, "x"]) == {"az": "a, x", "en": "b, x", "ru": "c, x"}


def test_load_tolerates_a_broken_catalog(tmp_path, monkeypatch):
    (tmp_path / "locales").mkdir()
    (tmp_path / "locales" / "en.json").write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(i18n, "ROOT", tmp_path)
    saved = dict(i18n._CAT)
    try:
        i18n.load()
        assert i18n._CAT["en"] == {} and i18n._CAT["ru"] == {}
    finally:
        i18n._CAT.update(saved)
