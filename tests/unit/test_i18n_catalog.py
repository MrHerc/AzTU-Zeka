"""The translation catalogue (tools/i18n.py): complete, consistent and in sync with the built locale files."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("i18n_tool", ROOT / "tools" / "i18n.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def sources(tool):
    return tool.gather()


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_every_source_string_is_translated(tool, sources, lang):
    tr = tool.load_tr(lang)
    missing = {name: [k for k in d if k not in tr] for name, d in zip(("ui", "server", "content"), sources, strict=True)}
    assert not any(missing.values()), {k: v[:5] for k, v in missing.items() if v}


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_translations_keep_placeholders_and_markup(tool, lang):
    problems = [(k[:60], p) for k, v in tool.load_tr(lang).items() for p in tool._check(k, v, lang)]
    assert not problems, problems[:10]


def test_built_locale_files_are_in_sync(tool, tmp_path, monkeypatch):
    """`python tools/i18n.py build` must not change the committed locale files."""
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    tool.build()
    for sub in ("static/locales", "app/locales"):
        for lang in ("en", "ru"):
            built = json.loads((tmp_path / sub / f"{lang}.json").read_text(encoding="utf-8"))
            committed = json.loads((ROOT / sub / f"{lang}.json").read_text(encoding="utf-8"))
            assert built == committed, f"{sub}/{lang}.json is stale — run: python tools/i18n.py build"
