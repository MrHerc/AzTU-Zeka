"""Password hashing and policy (tasks/todo.md, Task 10): backend/zeka/modules/identity/domain.py."""
import pytest

from zeka.modules.identity import domain, service


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(domain, "N", 2 ** 4)        # same code path, a fraction of the cost


def problem(pw, mfa=False, context=()):
    return domain.policy_problem(pw, mfa=mfa, context=list(context), blocklist=service.blocklist())


def test_a_hash_verifies_only_its_password_and_carries_its_parameters():
    h = domain.hash_password("uzun və yadda qalan cümlə 2026")
    assert h.startswith("scrypt$16$8$1$") and domain.verify("uzun və yadda qalan cümlə 2026", h)
    assert not domain.verify("uzun və yadda qalan cümlə 2027", h)
    assert domain.hash_password("eyni parol eyni parol") != domain.hash_password("eyni parol eyni parol")   # salted


def test_the_password_is_nfkc_normalised_before_hashing():
    assert domain.verify("ﬁle cabinet password", domain.hash_password("file cabinet password"))


@pytest.mark.parametrize("stored", [None, "", "plain", "scrypt$abc$8$1$AA==$AA==", "bcrypt$16$8$1$AA==$AA==",
                                    "scrypt$4194304$8$1$AA==$AA==", "scrypt$16$8$1$!!$AA=="])
def test_a_missing_or_broken_hash_never_matches(stored):
    assert domain.verify("anything at all here", stored) is False


def test_a_parameter_change_asks_for_a_rehash(monkeypatch):
    h = domain.hash_password("köhnə parametrlərlə parol")
    assert not domain.needs_rehash(h)
    monkeypatch.setattr(domain, "N", 2 ** 5)
    assert domain.needs_rehash(h) and domain.needs_rehash("broken")


def test_length_follows_nist_with_and_without_a_second_factor():
    assert "15" in problem("qısa-parol-14x")["en"]                     # 14 characters alone
    assert problem("on beş simvollu!") is None                         # 15 characters
    assert problem("8simvol!", mfa=True) is None and problem("7simvol", mfa=True)
    assert problem("söz " * 16) is None                                 # 64 characters are allowed
    assert "128" in problem("a1" * 65)["en"]


@pytest.mark.parametrize("pw", ["passwordpassword", "Password Password", "1234567890123456", "aaaaaaaaaaaaaaaaaa",
                                "ababababababababab", "qwertyuiopasdfghjk", "zyxwvutsrqponmlkj", "Azərbaycan123"])
def test_common_repeated_and_sequential_passwords_are_refused(pw):
    assert problem(pw, mfa=True) is not None, pw


def test_a_password_that_is_mostly_the_users_name_is_refused():
    assert problem("aysel.mammadova2026", context=["aysel.mammadova"]) is not None
    assert problem("aysel bu gün dənizə getdi", context=["aysel"]) is None   # a name inside a real phrase is fine


def test_every_reason_is_translated():
    reason = problem("qısa")
    assert set(reason) == {"az", "en", "ru"} and reason["en"] != reason["az"] and reason["ru"] != reason["az"]


def test_ipv6_clients_are_counted_per_64_network():
    assert domain.client_key("2001:db8:1:2:aaaa::1") == domain.client_key("2001:db8:1:2:bbbb::9") == "2001:db8:1:2::/64"
    assert domain.client_key("2001:db8:1:3::1") != domain.client_key("2001:db8:1:2::1")
    assert domain.client_key("::ffff:10.0.0.7") == "10.0.0.7" and domain.client_key("10.0.0.7") == "10.0.0.7"


def test_a_temporary_password_is_long_and_unambiguous():
    pw = domain.temporary_password()
    assert len(pw) == 23 and problem(pw) is None and not set(pw) & set("01lo")
