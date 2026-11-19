"""Safe Exam Browser's Config Key and request hashes (tasks/todo.md, Task 28).

The serialization rules were checked against two real SEB files with known keys (SEB 2.1.4 macOS and 2.2.3 Windows,
from Moodle's quizaccess_seb tests; not copied here because of their licence): set SEB_TEST_VECTORS to a folder with
those files and a ``keys.json`` ({file name: key}) to run that check. The owner's reference file goes to
tests/fixtures/reference.seb with the key the SEB Config Tool shows in tests/fixtures/reference.seb.key."""
import gzip
import hashlib
import json
import os
from pathlib import Path

import pytest

from zeka.modules.exam import seb

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_an_empty_configuration_has_the_published_key():
    assert seb.config_key({}) == "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"   # sha256("[]")
    assert seb.config_key(seb.read(b"")) == seb.config_key({})


def test_the_serialization_rules():
    cfg = {"originatorVersion": "SEB_Win_3.10.3", "allowWLAN": True, "allowWlan": False, "empty": {}, "Alpha": 1, "a_b": 2, "a1": 3,
           "URLFilterRules": [{"regex": True, "expression": "aztu\\.edu\\.az/.*", "action": 1}], "examKeySalt": b"\x01\x02", "zeta": "Zəka/ə"}
    text = ('{"a_b":2,"a1":3,"allowWlan":false,"allowWLAN":true,"Alpha":1,"examKeySalt":"AQI=",'
            '"URLFilterRules":[{"action":1,"expression":"aztu\\.edu\\.az/.*","regex":true}],"zeta":"Zəka/ə"}')
    assert seb.config_key(cfg) == hashlib.sha256(text.encode()).hexdigest()
    assert seb.config_key({**cfg, "originatorVersion": "SEB_Mac_3.7"}) == seb.config_key(cfg)   # the version does not count


def test_reading_plain_and_wrapped_files_and_refusing_encrypted_ones():
    cfg = seb.config(7, "https://zeka.test", "quit1234")
    raw = seb.to_file(cfg)
    key = seb.config_key(cfg)
    assert seb.config_key(seb.read(raw)) == key
    assert seb.config_key(seb.read(gzip.compress(b"plnd" + gzip.compress(raw)))) == key
    assert seb.config_key(seb.read(gzip.compress(b"plnd" + raw))) == key
    for prefix in (b"pswd", b"pwcc", b"pkhs"):
        with pytest.raises(seb.SebFileError, match="şifrələnib"):
            seb.read(gzip.compress(prefix + b"\x00" * 32))
    with pytest.raises(seb.SebFileError):
        seb.read(b"<?xml This is no property list")


def test_the_generated_configuration_locks_the_exam_down():
    cfg = seb.config(7, "https://zeka.test", "quit1234")
    assert cfg["startURL"] == "https://zeka.test/" and cfg["sendBrowserExamKey"] is True and cfg["browserWindowWebView"] == 3
    assert cfg["allowVirtualMachine"] is False and cfg["enablePrintScreen"] is False and cfg["clipboardPolicy"] == 2
    assert cfg["hashedQuitPassword"] == hashlib.sha256(b"quit1234").hexdigest()
    assert cfg["URLFilterRules"] == [{"action": 1, "active": True, "expression": "zeka.test/*", "regex": False}]
    assert seb.launch_link("https://zeka.test", 7, "tok") == "sebs://zeka.test/exam/7/config.seb?k=tok"
    assert seb.launch_link("http://10.0.0.5:5070", 7, "tok") == "seb://10.0.0.5:5070/exam/7/config.seb?k=tok"


def test_the_header_hash_is_over_the_public_address_and_the_raw_target():
    key, nonce = "k" * 64, "N1"
    target = f"/api/exams/7/seb-verify?n={nonce}&dir=a%2Fb"                    # %2F stays as sent, two parameters
    good = hashlib.sha256(f"https://zeka.test{target}{key}".encode()).hexdigest()
    assert seb.header_ok("https://zeka.test", target, good, key, nonce)
    assert seb.header_ok("https://zeka.test", target, good.upper(), key, nonce)
    local = hashlib.sha256(f"http://127.0.0.1:5070{target}{key}".encode()).hexdigest()
    assert not seb.header_ok("https://zeka.test", target, local, key, nonce)   # computed on the listening address
    decoded = hashlib.sha256(f"https://zeka.test/api/exams/7/seb-verify?n={nonce}&dir=a/b{key}".encode()).hexdigest()
    assert not seb.header_ok("https://zeka.test", target, decoded, key, nonce)
    assert not seb.header_ok("https://zeka.test", target, good, key, "N2")     # another session's value
    assert not seb.header_ok("https://zeka.test", target.replace(f"n={nonce}&", ""), good, key, nonce)


def test_the_js_api_hash_is_over_the_page_url_on_the_public_address():
    key, nonce = "k" * 64, "N1"
    page = f"https://zeka.test/static/exam.html?exam=7&n={nonce}"
    good = seb.request_hash(page, key)
    assert seb.page_ok("https://zeka.test", page, good, key, nonce)
    assert seb.page_ok("https://zeka.test", page + "#top", good, key, nonce)   # the fragment does not count
    other = f"https://evil.test/static/exam.html?exam=7&n={nonce}"
    assert not seb.page_ok("https://zeka.test", other, seb.request_hash(other, key), key, nonce)
    assert not seb.page_ok("https://zeka.test", page, good, key, "N2")
    assert not seb.page_ok("https://zeka.test", page, None, key, nonce)


@pytest.mark.skipif(not os.environ.get("SEB_TEST_VECTORS"), reason="set SEB_TEST_VECTORS to a folder of real .seb files and keys.json")
def test_real_seb_files_give_their_known_keys():
    folder = Path(os.environ["SEB_TEST_VECTORS"])
    keys = json.loads((folder / "keys.json").read_text())
    assert keys
    for name, key in keys.items():
        assert seb.config_key(seb.read((folder / name).read_bytes())) == key, name


@pytest.mark.skipif(not (FIXTURES / "reference.seb").exists(), reason="the owner's reference .seb file is not in tests/fixtures yet")
def test_the_owners_reference_file_gives_the_key_the_seb_config_tool_shows():
    want = (FIXTURES / "reference.seb.key").read_text().strip().lower()
    assert seb.config_key(seb.read((FIXTURES / "reference.seb").read_bytes())) == want
