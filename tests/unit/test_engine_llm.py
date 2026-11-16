"""engine.py — optional LLM provider configuration and HTTP client (network is stubbed)."""
import io
import json

import pytest

from app import engine


@pytest.fixture
def cfg_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "ROOT", tmp_path)
    for k in ("AZTU_LLM_PROVIDER", "AZTU_LLM_BASE_URL", "AZTU_LLM_API_KEY", "AZTU_LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path


def test_llm_disabled_without_config(cfg_dir):
    c = engine.llm_config()
    assert c["enabled"] is False
    assert engine.engine_info()["mode"] == "demo"
    with pytest.raises(RuntimeError):
        engine.llm_chat("sys", [{"role": "user", "content": "hi"}])


def test_llm_config_from_file_and_env_override(cfg_dir, monkeypatch):
    (cfg_dir / "config.json").write_text(json.dumps({"llm": {"provider": "openai", "api_key": "k", "model": "gpt-4o-mini", "timeout": 5}}), encoding="utf-8")
    c = engine.llm_config()
    assert c["enabled"] is True and c["model"] == "gpt-4o-mini" and c["timeout"] == 5
    assert engine.engine_info() == {"mode": "llm", "label": "openai · gpt-4o-mini"}
    monkeypatch.setenv("AZTU_LLM_MODEL", "other-model")
    monkeypatch.setenv("AZTU_LLM_API_KEY", "")           # empty values do not override
    c = engine.llm_config()
    assert c["model"] == "other-model" and c["api_key"] == "k"


def test_llm_config_tolerates_broken_file(cfg_dir):
    (cfg_dir / "config.json").write_text("{not json", encoding="utf-8")
    assert engine.llm_config()["enabled"] is False


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.mark.parametrize("provider, url_part, header, reply", [
    ("openai", "/chat/completions", ("Authorization", "Bearer secret"), {"choices": [{"message": {"content": "OK [1]"}}]}),
    ("azure", "/openai/deployments/dep/chat/completions?api-version=2024-10-21", ("api-key", "secret"), {"choices": [{"message": {"content": "OK [1]"}}]}),
    ("anthropic", "/v1/messages", ("x-api-key", "secret"), {"content": [{"type": "text", "text": "OK "}, {"type": "text", "text": "[1]"}]}),
])
def test_llm_chat_builds_provider_specific_requests(cfg_dir, monkeypatch, provider, url_part, header, reply):
    base = {"openai": "https://llm.example/v1", "azure": "https://res.openai.azure.com", "anthropic": "https://api.anthropic.com"}[provider]
    model = "dep" if provider == "azure" else "m1"
    (cfg_dir / "config.json").write_text(json.dumps({"llm": {"provider": provider, "base_url": base, "api_key": "secret", "model": model}}), encoding="utf-8")
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"], seen["headers"], seen["body"], seen["timeout"] = req.full_url, dict(req.header_items()), json.loads(req.data), timeout
        return _Resp(json.dumps(reply).encode())

    monkeypatch.setattr(engine.urllib.request, "urlopen", fake_urlopen)
    out = engine.llm_chat("SYSTEM", [{"role": "user", "content": "Salam"}], max_tokens=33)
    assert out == "OK [1]"
    assert seen["url"].endswith(url_part) and seen["timeout"] == 40.0
    assert {k.lower(): v for k, v in seen["headers"].items()}[header[0].lower()] == header[1]
    body = seen["body"]
    assert body["max_tokens"] == 33
    if provider == "anthropic":
        assert body["system"] == "SYSTEM" and body["messages"] == [{"role": "user", "content": "Salam"}]
    else:
        assert body["messages"][0] == {"role": "system", "content": "SYSTEM"} and body["messages"][-1]["content"] == "Salam"
