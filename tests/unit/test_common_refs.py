"""common.py helpers, refs.py (verified external references) and support.py vocabularies."""
import json
from datetime import timedelta

import pytest

from app import common, refs, support
from app.store import iso, now


def test_session_cookie(monkeypatch):
    monkeypatch.setitem(common.BASE_URL, "value", "http://127.0.0.1:5070")
    name, value = common.session_cookie("abc")
    assert name == "Set-Cookie" and value == "zeka_sid=abc; HttpOnly; SameSite=Lax; Path=/"
    monkeypatch.setitem(common.BASE_URL, "value", "https://zeka.example.az")
    assert common.session_cookie(expire=True)[1] == "zeka_sid=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0; Secure"


def test_make_key_prunes_expired_keys():
    stale = common.make_key("doc", 1, 1)
    common._DOC_KEYS[stale]["exp"] = now() - timedelta(seconds=1)
    fresh = common.make_key("doc", 2, 1)
    assert stale not in common._DOC_KEYS and fresh in common._DOC_KEYS
    assert common._DOC_KEYS[fresh]["exp"] > now() + timedelta(minutes=4)


def test_week_index():
    assert common.week_index(iso(now())) == 0
    assert common.week_index(iso(now() - timedelta(days=8))) == 1
    assert common.week_index(iso(now() - timedelta(days=50))) == 7


def test_pub_user_hides_internal_fields():
    u = {"id": 1, "username": "aysel", "full_name": "A", "role": "student", "title": "t", "color": "#fff", "consent_at": None,
         "prefs": '{"lang": "en"}', "student_no": "secret", "patronymic": "x"}
    out = common.pub_user(u)
    assert out == {"id": 1, "username": "aysel", "full_name": "A", "role": "student", "title": "t", "color": "#fff", "consent_at": None, "prefs": {"lang": "en"}}
    assert common.pub_user(None) is None and common.pub_user({**u, "prefs": None})["prefs"] == {}


# ---------------------------------------------------------------- refs
@pytest.fixture
def refs_file(tmp_path, monkeypatch):
    monkeypatch.setattr(refs, "CONTENT", tmp_path)
    monkeypatch.setitem(refs._cache, "mtime", None)
    path = tmp_path / "references.json"

    def write(data):
        path.write_text(json.dumps(data), encoding="utf-8")
        refs._cache["mtime"] = None
    return write


def test_refs_only_serve_https_links_with_a_title(refs_file):
    refs_file({"checked": "2026-10-01", "courses": {"X": [
        {"work": "Good", "url": "https://openstax.org/x", "kind": "book"},
        {"work": "Plain http", "url": "http://example.com"},
        {"work": "Script", "url": "javascript:alert(1)"},
        {"url": "https://no-title.example"},
        {"work": "Odd kind", "url": "https://ok.example", "kind": "video", "lang": "az"},
    ]}})
    out = refs.for_course("X")
    assert [r["work"] for r in out] == ["Good", "Odd kind"]
    assert out[1]["kind"] == "docs" and out[1]["lang"] == "az" and out[0]["lang"] == "en" and out[0]["part"] == ""
    assert refs.checked() == "2026-10-01" and refs.for_course("missing") == []


def test_refs_material_and_module_lookups(refs_file):
    refs_file({"materials": {"a.md": [{"work": "W", "url": "https://w"}]}, "academy": {"ai/2": [{"work": "M", "url": "https://m"}]}})
    assert refs.for_material("a.md")[0]["work"] == "W" and refs.for_module("ai", 2)[0]["work"] == "M" and refs.for_module("ai", 3) == []


def test_refs_survive_a_broken_or_missing_file(refs_file, tmp_path):
    (tmp_path / "references.json").write_text("{broken", encoding="utf-8")
    assert refs.for_course("X") == [] and refs.checked() == ""
    (tmp_path / "references.json").unlink()
    assert refs._data() == {}


def test_real_references_file_is_clean():
    data = json.loads((refs.CONTENT / "references.json").read_text(encoding="utf-8"))
    raw = [r for group in ("courses", "materials", "academy") for items in data[group].values() for r in items]
    assert raw and all(r["url"].startswith("https://") and r.get("work") and r.get("kind") in refs.KINDS for r in raw)


# ---------------------------------------------------------------- support vocabularies
def test_support_vocabularies_are_consistent():
    assert set(support.SLA_HOURS) == support.CODES["priority"]
    assert set(support.OPEN) <= support.CODES["status"]
    assert len(support.SCORE_LABELS) == 5 and "overall" in support.CODES["area"]
    assert all(len(set(k for k, *_ in vocab)) == len(vocab) for vocab in (support.CATEGORIES, support.PRIORITIES, support.STATUSES, support.AREAS))
