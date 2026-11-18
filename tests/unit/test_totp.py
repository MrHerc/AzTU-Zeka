"""TOTP and recovery codes (tasks/todo.md, Task 12): backend/zeka/modules/identity/domain.py."""
import base64

import pytest

from zeka.modules.identity import domain

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()      # RFC 6238 appendix B, SHA-1


@pytest.mark.parametrize("t, code", [(59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"),
                                     (1234567890, "89005924"), (2000000000, "69279037"), (20000000000, "65353130")])
def test_rfc_6238_test_vectors(t, code):
    assert domain.hotp(domain.totp_key(RFC_SECRET), t // 30, 8) == code


def code_at(t):
    return domain.hotp(domain.totp_key(RFC_SECRET), int(t) // 30)


def test_one_step_either_side_is_accepted_and_no_further():
    t = 1_700_000_015
    assert domain.totp_match(RFC_SECRET, code_at(t), t, None) == t // 30
    assert domain.totp_match(RFC_SECRET, code_at(t - 30), t, None) == t // 30 - 1
    assert domain.totp_match(RFC_SECRET, code_at(t + 30), t, None) == t // 30 + 1
    assert domain.totp_match(RFC_SECRET, code_at(t - 60), t, None) is None
    assert domain.totp_match(RFC_SECRET, code_at(t + 60), t, None) is None


def test_a_used_step_and_older_ones_are_refused():
    t = 1_700_000_015
    assert domain.totp_match(RFC_SECRET, code_at(t), t, last_step=t // 30) is None
    assert domain.totp_match(RFC_SECRET, code_at(t - 30), t, last_step=t // 30 - 1) is None
    assert domain.totp_match(RFC_SECRET, code_at(t + 30), t, last_step=t // 30) == t // 30 + 1


@pytest.mark.parametrize("code", ["", "12345", "1234567", "abcdef", "12 34 5x"])
def test_malformed_codes_never_match(code):
    assert domain.totp_match(RFC_SECRET, code, 1_700_000_015, None) is None


def test_spaces_inside_a_code_are_ignored():
    t = 1_700_000_015
    c = code_at(t)
    assert domain.totp_match(RFC_SECRET, f"{c[:3]} {c[3:]}", t, None) == t // 30


def test_a_new_secret_is_160_bits_and_its_uri_is_what_authenticator_apps_read():
    secret = domain.new_totp_secret()
    assert len(domain.totp_key(secret)) == 20
    uri = domain.otpauth_uri(secret, "rəşad.admin")
    assert uri.startswith("otpauth://totp/AzTU%20Z%C9%99ka:r%C9%99%C5%9Fad.admin?secret=" + secret)
    assert "&algorithm=SHA1&digits=6&period=30" in uri


def test_recovery_codes_are_ten_distinct_and_their_hash_ignores_case_and_dashes():
    codes = domain.recovery_codes()
    assert len(codes) == len(set(codes)) == 10 and all(domain.is_recovery_code(c) for c in codes)
    c = codes[0]
    assert domain.recovery_hash(c) == domain.recovery_hash(c.upper().replace("-", " "))
    assert not domain.is_recovery_code("123456")
