"""Security controls shared by the HTTP layer and the routes (stdlib only).

Configuration comes from environment variables and is finalised by run.py:

* ``ZEKA_ACCESS_CODE``      – shared code required for the password-less demo login (mandatory on a public host).
* ``ZEKA_ALLOW_OPEN_DEMO``  – "1" lets a public host run without an access code (not recommended).
* ``ZEKA_PROXY_HOPS``       – number of trusted reverse proxies in front of the app (X-Forwarded-For), default 0.
* ``ZEKA_ACCESS_LOG``       – "1"/"0" forces the per-request access log on or off (default: on for public hosts).
"""
from __future__ import annotations

import hmac
import os
import re
import sqlite3
import threading
import time
import urllib.parse
from collections import OrderedDict
from types import SimpleNamespace

LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(int(os.environ.get(name, default)), hi))
    except ValueError:
        return default


CFG = SimpleNamespace(
    access_code=os.environ.get("ZEKA_ACCESS_CODE", "").strip(),
    proxy_hops=_env_int("ZEKA_PROXY_HOPS", 0, 0, 5),
    https=False,             # set by run.py when the public URL is HTTPS (HSTS, Secure cookie)
    allowed_hosts=set(),     # extra host[:port] values accepted in the Origin header (the public URL)
    access_log=False,
)


def access_code_ok(given) -> bool:
    """Constant-time comparison with the configured demo access code; always true when none is configured."""
    code = CFG.access_code
    if not code:
        return True
    return hmac.compare_digest(str(given or "").strip().encode("utf-8"), code.encode("utf-8"))


# ---------------------------------------------------------------- rate limiting
_SHARED_DB: list = []   # [path] once the database is attached: named limiters then count across worker processes


def attach_database(path) -> None:
    """Share the named limiters (LIMITS) through the rate_hits table of this SQLite file (migration 0070)."""
    _SHARED_DB[:] = [str(path)]


class RateLimiter:
    """Events per key in a window. In memory (fixed window, per process) until attach_database(); then the named
    limiters keep a sliding window in the database, so N worker processes share one limit."""

    def __init__(self, limit: int, window: float, max_keys: int = 20000, name: str | None = None):
        self.limit, self.window, self.max_keys, self.name = limit, window, max_keys, name
        self._b: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self._swept = 0.0           # last sweep of this limiter's expired rows (per process)

    def _db(self, key, cost: int, count: bool) -> bool:
        # Own connection and transaction, committed at once: the request's transaction never holds this lock.
        c = sqlite3.connect(_SHARED_DB[0], timeout=5)
        try:
            c.execute("BEGIN IMMEDIATE")
            t = time.time()
            if t - self._swept > 60:        # keys that never come back would otherwise stay in rate_hits for ever
                c.execute("DELETE FROM rate_hits WHERE name=? AND ts<?", (self.name, t - self.window))
                self._swept = t
            c.execute("DELETE FROM rate_hits WHERE name=? AND key=? AND ts<?", (self.name, str(key), t - self.window))
            n = c.execute("SELECT COUNT(*) FROM rate_hits WHERE name=? AND key=?", (self.name, str(key))).fetchone()[0]
            ok = n + cost <= self.limit if count else n >= self.limit
            if count and ok:
                c.executemany("INSERT INTO rate_hits(name,key,ts) VALUES(?,?,?)", [(self.name, str(key), t)] * cost)
            c.execute("COMMIT")
            return ok
        finally:
            c.close()

    def hit(self, key, cost: int = 1) -> bool:
        """Count one event for key; False when the key is over its limit for the current window."""
        if self.name and _SHARED_DB:
            return self._db(key, cost, True)
        t = time.monotonic()
        with self._lock:
            start, n = self._b.get(key, (t, 0))
            if t - start >= self.window:
                start, n = t, 0
            n += cost
            self._b[key] = (start, n)
            self._b.move_to_end(key)
            while len(self._b) > self.max_keys:
                self._b.popitem(last=False)
            return n <= self.limit

    def blocked(self, key) -> bool:
        """True when key has already used up its limit (does not count an event)."""
        if self.name and _SHARED_DB:
            return self._db(key, 0, False)
        t = time.monotonic()
        with self._lock:
            start, n = self._b.get(key, (t, 0))
            return t - start < self.window and n >= self.limit

    def reset(self):
        with self._lock:
            self._b.clear()
        if self.name and _SHARED_DB:
            c = sqlite3.connect(_SHARED_DB[0], timeout=5)
            try:
                c.execute("DELETE FROM rate_hits WHERE name=?", (self.name,))
                c.commit()
            finally:
                c.close()


LIMITS = {
    "login": RateLimiter(30, 60),           # demo logins per client per minute
    "login_fail": RateLimiter(10, 600),     # wrong access codes per client per 10 minutes
    "ai": RateLimiter(30, 60),              # tutor / assistant / generator calls per user per minute
    "upload": RateLimiter(40, 600),         # uploads per user per 10 minutes
    "preview": RateLimiter(30, 60),         # PDF/DOCX previews per user per minute
    "link": RateLimiter(120, 60),           # one-time document links per user per minute
    "verify": RateLimiter(60, 60),          # public verification lookups per client per minute
    # Checkpoint B: failed password sign-ins per client (IPv6: /64) per 15 minutes, whatever the account; generous,
    # because a campus puts many students behind one address. Stops one client spraying passwords or tying up scrypt.
    "password_fail": RateLimiter(100, 900),
    "sso": RateLimiter(30, 60),             # single sign-on starts per client per minute
    "room": RateLimiter(60, 60),            # public room pages (QR codes on the doors, Task 18) per client per minute
    "club_post": RateLimiter(20, 60),       # club channel messages per user per minute (Task 35)
    "ical": RateLimiter(30, 60),            # fetches of one calendar feed (Task 19) per minute
    "ical_client": RateLimiter(600, 60),    # calendar feed fetches per client per minute (calendar services share addresses)
}
for _name, _lim in LIMITS.items():
    _lim.name = _name


# ---------------------------------------------------------------- request helpers
def client_ip(handler) -> str:
    """The client address; behind N trusted proxies, the N-th address from the right of X-Forwarded-For."""
    peer = handler.client_address[0] if handler.client_address else ""
    hops = CFG.proxy_hops
    if hops:
        xff = [p.strip() for p in (handler.headers.get("X-Forwarded-For") or "").split(",") if p.strip()]
        if len(xff) >= hops:
            return xff[-hops][:64]
    return peer


def cross_site(headers) -> bool:
    """True when a browser marked the request as coming from another site (CSRF defence for unsafe methods).

    Uses Fetch Metadata (Sec-Fetch-Site) where the browser sends it and the Origin header otherwise.
    Requests without either header come from non-browser clients and are not affected.
    """
    site = (headers.get("Sec-Fetch-Site") or "").strip().lower()
    if site:
        return site not in ("same-origin", "none")
    origin = headers.get("Origin")
    if origin is None:
        return False
    if origin.strip().lower() == "null":
        return True
    netloc = urllib.parse.urlsplit(origin.strip()).netloc.lower()
    allowed = {(headers.get("Host") or "").strip().lower()} | CFG.allowed_hosts
    return not netloc or netloc not in allowed


_SAFE_PATH = re.compile(r"/(?![/\\])[A-Za-z0-9/#?&=._~%:+,-]*")


def safe_next(target, default: str = "/") -> str:
    """A same-site relative redirect target, or default. Rejects scheme-relative URLs, backslashes, whitespace and controls."""
    t = str(target or "")
    return t if len(t) <= 512 and _SAFE_PATH.fullmatch(t) else default


_BAD_HEADER = re.compile(r"[\r\n\x00]")


def header_ok(name: str, value: str) -> bool:
    return not (_BAD_HEADER.search(str(name)) or _BAD_HEADER.search(str(value)))
