"""`python tools/i18n.py rename`: rewrites an Azerbaijani key in code, tests, content and the catalogue (Task 20)."""
import ast
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def tree(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("i18n_tool_rename", ROOT / "tools" / "i18n.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    files = {
        "frontend/js/a.js": 'const x = t("Köhnə mətn");\nif (s === "Köhnə status") ok(t("Köhnə status"));\n',
        "backend/zeka/legacy/r_x.py": 'A = S("Köhnə mətn")\nB = ("Uzun köhnə cümlənin birinci hissəsi "\n     "və ikinci hissəsi")\n',
        "tests/test_x.py": 'assert body == "Köhnə mətn"\n',
        "content/seed.json": '{"users": [], "courses": [], "university": {"name": "Köhnə mətn"}}\n',
        "content/academy.json": '{"tracks": []}', "content/tools.json": '{"areas": {}, "tools": []}',
        "content/news.json": '{"kinds": {}, "news": []}', "content/guide.json": "{}",
        "i18n/en/a.json": json.dumps({"Köhnə mətn": "Old text", "Köhnə status": "Old", "Qal": "Stay",
                                      "Uzun köhnə cümlənin birinci hissəsi və ikinci hissəsi": "Long"}, ensure_ascii=False, indent=1) + "\n",
        "i18n/ru/a.json": json.dumps({"Köhnə mətn": "Старый текст", "Köhnə status": "Старый", "Qal": "Оставь",
                                      "Uzun köhnə cümlənin birinci hissəsi və ikinci hissəsi": "Длинный"}, ensure_ascii=False, indent=1) + "\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    monkeypatch.setattr(tool, "CONTENT", tmp_path / "content")
    monkeypatch.setattr(tool, "I18N", tmp_path / "i18n")
    mapping = {
        "Köhnə mətn": {"az": "Yeni mətn", "en": None, "ru": "Новый текст"},
        "Köhnə status": {"az": "Yeni status", "en": None, "ru": None},          # also a compared value: refused
        "Qal": {"az": None, "en": "Stays", "ru": None},
        "Uzun köhnə cümlənin birinci hissəsi və ikinci hissəsi": {"az": "Uzun yeni cümlənin birinci hissəsi və ikinci hissəsi", "en": None, "ru": None},
    }
    (tmp_path / "map.json").write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    return tool, tmp_path


def read(root, rel):
    return (root / rel).read_text(encoding="utf-8")


def test_dry_run_writes_nothing(tree):
    tool, root = tree
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    total = tool.rename(root / "map.json")
    assert total["renamed"] == 2 and total["refused"] == 1
    assert before == {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_apply_rewrites_code_tests_content_and_catalogue_once(tree, capsys):
    tool, root = tree
    tool.rename(root / "map.json", apply=True)
    out = capsys.readouterr().out
    assert "REFUSED 'Köhnə status'" in out and "a.js:2" in out
    js = read(root, "frontend/js/a.js")
    assert 't("Yeni mətn")' in js and '"Köhnə status"' in js and "Köhnə mətn" not in js
    py = read(root, "backend/zeka/legacy/r_x.py")
    assert 'S("Yeni mətn")' in py and py.count("\n") == 3          # the two-piece literal stays two pieces
    assert ast.literal_eval(py.split("B = ", 1)[1]) == "Uzun yeni cümlənin birinci hissəsi və ikinci hissəsi"
    assert read(root, "tests/test_x.py") == 'assert body == "Yeni mətn"\n'
    assert json.loads(read(root, "content/seed.json"))["university"]["name"] == "Yeni mətn"
    en, ru = json.loads(read(root, "i18n/en/a.json")), json.loads(read(root, "i18n/ru/a.json"))
    assert en["Yeni mətn"] == "Old text" and ru["Yeni mətn"] == "Новый текст" and "Köhnə mətn" not in en
    assert list(en)[0] == "Yeni mətn"                                # moved in place
    assert en["Qal"] == "Stays" and en["Köhnə status"] == "Old"
    snapshot = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    again = tool.rename(root / "map.json", apply=True)
    assert again["renamed"] == 0 and again["translations"] == 0
    assert snapshot == {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_only_keeps_the_old_key_for_its_other_uses(tree):
    tool, root = tree
    (root / "frontend/js/b.js").write_text('t("Köhnə mətn");\n', encoding="utf-8")
    m = {"Köhnə mətn": {"az": "Yeni mətn", "en": "New text", "ru": None, "only": ["frontend/js/b.js"]}}
    (root / "only.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    tool.rename(root / "only.json", apply=True)
    assert read(root, "frontend/js/b.js") == 't("Yeni mətn");\n' and 't("Köhnə mətn")' in read(root, "frontend/js/a.js")
    en = json.loads(read(root, "i18n/en/a.json"))
    assert en["Köhnə mətn"] == "Old text" and en["Yeni mətn"] == "New text"


def test_a_key_inside_a_longer_content_string_is_refused(tree):
    tool, root = tree
    (root / "content/news.json").write_text(json.dumps({"kinds": {}, "news": [{"event": {"location": "Köhnə mətn, Bakı"}}]},
                                                      ensure_ascii=False), encoding="utf-8")
    total = tool.rename(root / "map.json", apply=True)
    assert total["refused"] == 2 and 't("Köhnə mətn")' in read(root, "frontend/js/a.js")
