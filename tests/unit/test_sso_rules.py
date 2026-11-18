"""Rules of single sign-on (tasks/todo.md, Task 14): ID token checks, PKCE, which addresses may be called."""
import base64
import hashlib
import json

import pytest

from zeka.core import config
from zeka.modules.identity import domain, sso

GOOD = {"iss": "https://idp.example", "aud": "zeka", "exp": 2000, "iat": 1000, "nonce": "n-1", "sub": "s-1"}


def check(**changes):
    return domain.claims_problem({**GOOD, **changes}, issuer="https://idp.example", client_id="zeka", nonce="n-1", now=1500)


def test_an_honest_token_passes_and_each_broken_claim_is_named():
    assert check() is None
    assert check(aud=["zeka"]) is None
    assert check(exp=1500 - domain.SSO_LEEWAY + 1) is None, "a minute of clock difference is allowed"
    cases = {"iss": {"iss": "https://idp.example/"}, "aud": {"aud": ["zeka", "x"]}, "exp": {"exp": 1440},
             "iat": {"iat": 1561}, "nonce": {"nonce": "n-2"}, "sub": {"sub": 7}}
    for reason, change in cases.items():
        assert check(**change) == reason, change
    assert check(exp=True) == "exp" and check(nonce="ä") == "nonce" and check(azp="other") == "aud"


def _enc(d) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")


def test_only_a_signed_compact_jwt_gives_claims():
    assert domain.jwt_claims(f"{_enc({'alg': 'RS256'})}.{_enc(GOOD)}.sig") == GOOD
    for bad in (f"{_enc({'alg': 'none'})}.{_enc(GOOD)}.", f"{_enc({})}.{_enc(GOOD)}.s", f"{_enc({'alg': 'RS256'})}.{_enc([1])}.s",
                "a.b", "a.b.c.d.e", None, "!.!.!"):
        assert domain.jwt_claims(bad) is None, bad


def test_pkce_challenge_is_the_s256_of_the_verifier():
    verifier, challenge = domain.pkce_pair()
    assert 43 <= len(verifier) <= 128
    assert challenge == base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


def test_an_e_mail_counts_only_when_verified_with_json_true():
    assert domain.verified_email({"email": "A@B.az", "email_verified": True}) == "a@b.az"
    for v in (False, "true", 1, None):
        assert domain.verified_email({"email": "a@b.az", "email_verified": v}) is None


def test_trusted_mfa_comes_from_amr_or_acr():
    assert domain.idp_mfa({"amr": ["pwd", "mfa"]}, ["mfa"], [])
    assert not domain.idp_mfa({"amr": ["pwd"]}, ["mfa"], [])
    assert not domain.idp_mfa({"amr": "mfa"}, ["mfa"], []), "amr is a list"
    assert domain.idp_mfa({"acr": "gold"}, [], ["gold"]) and not domain.idp_mfa({"acr": "gold"}, [], [])
    assert not domain.idp_mfa({"amr": ["m"], "acr": "g"}, "mfa", "gold"), "a setting written as a string trusts nothing"
    assert domain.student_number({"n": 7}, ["n"]) is None and domain.student_number({"n": 7}, "n") == "7"


@pytest.mark.parametrize("mode, url, ok", [
    ("prod", "https://idp.example/x", True), ("prod", "http://127.0.0.1:9/x", False), ("demo", "http://127.0.0.1:9/x", True),
    ("demo", "http://idp.example/x", False), ("demo", "ftp://idp.example", False), ("demo", "https://idp.example/#f", False),
    ("demo", "https:///x", False), ("demo", None, False)])
def test_which_addresses_may_be_called(monkeypatch, mode, url, ok):
    monkeypatch.setattr(config, "MODE", mode)
    assert (sso.url_problem(url) is None) is ok
