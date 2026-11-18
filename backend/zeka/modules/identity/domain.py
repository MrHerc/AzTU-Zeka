"""Passwords and sign-in throttling (tasks/todo.md, Task 10). Rules only: no database, no files, no clock.

Hash: scrypt with fixed parameters stored in the hash string ``scrypt$n$r$p$salt$hash`` (base64), so a parameter change
is applied to each account at its next successful sign-in. Policy: NIST SP 800-63B-4 — at least 15 characters for a
password used alone, 8 with a second factor, at least 64 allowed, no composition rules and no periodic change, a
blocklist of common and context-specific values. The password is NFKC-normalised before hashing.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import secrets
import unicodedata

from ...core.i18n import E

N, R, P = 2 ** 15, 8, 1        # 32 MiB and about 110 ms per hash on the reference machine
DKLEN = 32
MIN_ALONE, MIN_MFA, MAX_LEN = 15, 8, 128
WINDOW = 15 * 60               # failures are counted per (account, client) in this window ...
CLIENT_LIMIT = 10              # ... and block that client for that account after this many
ACCOUNT_LIMIT = 100            # consecutive failures from anywhere lock the account
BLOCK = 15 * 60                # seconds a block or a lock lasts
SEQUENCES = ("abcdefghijklmnopqrstuvwxyz", "0123456789", "qwertyuiopasdfghjklzxcvbnm", "qazwsxedcrfvtgbyhnujmikolp")


def normalize(password: str) -> str:
    return unicodedata.normalize("NFKC", password)


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    # maxmem must be given: the stdlib default (32 MiB) refuses n=2^15, r=8, which needs 128 * r * n bytes
    return hashlib.scrypt(normalize(password).encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=DKLEN,
                          maxmem=129 * r * n + (1 << 20))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, N, R, P)
    return f"scrypt${N}${R}${P}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def _parse(stored: str):
    try:
        kind, n, r, p, salt, digest = stored.split("$")
        if kind != "scrypt" or not (1 < int(n) <= 2 ** 20 and 0 < int(r) <= 32 and 0 < int(p) <= 16):
            return None
        return int(n), int(r), int(p), base64.b64decode(salt, validate=True), base64.b64decode(digest, validate=True)
    except (ValueError, AttributeError):
        return None


def verify(password: str, stored: str | None) -> bool:
    """Constant-time comparison; a missing or broken hash never matches."""
    parsed = _parse(stored or "")
    if not parsed:
        return False
    n, r, p, salt, digest = parsed
    return hmac.compare_digest(_scrypt(password, salt, n, r, p), digest)


def needs_rehash(stored: str) -> bool:
    parsed = _parse(stored)
    return not parsed or parsed[:3] != (N, R, P)


def policy_problem(password: str, *, mfa: bool, context: list[str], blocklist: frozenset[str]) -> dict | None:
    """None when the password may be used, else the reason in every language (an HTTPError message)."""
    pw = normalize(password)
    least = MIN_MFA if mfa else MIN_ALONE
    if len(pw) < least:
        return E("Parol ən azı {n} simvol olmalıdır", n=least)
    if len(pw) > MAX_LEN:
        return E("Parol {n} simvoldan uzun ola bilməz", n=MAX_LEN)
    squeezed = "".join(pw.lower().split())
    if pw.lower() in blocklist or squeezed in blocklist:
        return E("Bu parol çox geniş yayılıb; başqasını seçin")
    if len(set(squeezed)) <= 2:
        return E("Parol eyni simvolların təkrarından ibarətdir")
    for seq in SEQUENCES:
        if any(squeezed in s * 3 for s in (seq, seq[::-1])):
            return E("Parol klaviatura və ya əlifba ardıcıllığıdır")
    for word in context:
        w = "".join((word or "").lower().split())
        if len(w) >= 4 and w in squeezed and len(squeezed) - len(w) < 8:
            return E("Parol əsasən adınızı, istifadəçi adınızı və ya universitetin adını təkrarlayır")
    return None


def client_key(ip: str) -> str:
    """The client a failure is counted against: the address, or its /64 network for IPv6."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip[:64]
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr)


def temporary_password() -> str:
    """One-time password an administrator hands over: 4 groups of 5 letters and digits (no 0/o/1/l), 23 characters."""
    alphabet = "abcdefghijkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(4))


# ---------------------------------------------------------------- sessions (Task 11)
STUDENT_ROLES = ("student",)
SESSION_LIMITS = {                       # (idle, absolute) in seconds; a tenant setting overrides them (Task 17)
    "staff": (60 * 60, 24 * 60 * 60),
    "student": (8 * 60 * 60, 30 * 24 * 60 * 60),
}
SEEN_EVERY = 60                          # last_seen is written at most this often per session
MAX_IDLE = 24 * 60 * 60                  # the longest idle time any setting allows: older sessions are deleted


def session_hash(sid: str) -> str:
    """What the database keeps instead of the session id."""
    return hashlib.sha256(sid.encode("utf-8")).hexdigest()


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def session_limits(role: str, overrides: dict | None = None) -> tuple[int, int]:
    kind = "student" if role in STUDENT_ROLES else "staff"
    idle, absolute = SESSION_LIMITS[kind]
    o = (overrides or {}).get(kind) or {}
    if isinstance(o.get("idle_minutes"), int) and 5 <= o["idle_minutes"] <= 24 * 60:
        idle = o["idle_minutes"] * 60
    if isinstance(o.get("absolute_hours"), int) and 1 <= o["absolute_hours"] <= 90 * 24:
        absolute = o["absolute_hours"] * 3600
    return idle, absolute


def session_expired(role: str, created_at, last_seen, now, overrides: dict | None = None) -> bool:
    idle, absolute = session_limits(role, overrides)
    return (now - last_seen).total_seconds() > idle or (now - created_at).total_seconds() > absolute
