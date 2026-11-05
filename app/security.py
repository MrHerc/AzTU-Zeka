"""Security controls shared by the HTTP layer and the routes (stdlib only).

Configuration comes from environment variables and is finalised by run.py:

* ``ZEKA_ACCESS_CODE``      – shared code required for the password-less demo login (mandatory on a public host).
* ``ZEKA_ALLOW_OPEN_DEMO``  – "1" lets a public host run without an access code (not recommended).
* ``ZEKA_SESSION_HOURS``    – absolute session lifetime in hours (default 12).
* ``ZEKA_PROXY_HOPS``       – number of trusted reverse proxies in front of the app (X-Forwarded-For), default 0.
* ``ZEKA_ACCESS_LOG``       – "1"/"0" forces the per-request access log on or off (default: on for public hosts).
"""
from __future__ import annotations

import hmac
import os
import re
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
    session_hours=_env_int("ZEKA_SESSION_HOURS", 12, 1, 24 * 30),
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
class RateLimiter:
    """Fixed-window counter per key, thread-safe, with a bounded number of tracked keys."""

    def __init__(self, limit: int, window: float, max_keys: int = 20000):
        self.limit, self.window, self.max_keys = limit, window, max_keys
        self._b: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def hit(self, key, cost: int = 1) -> bool:
        """Count one event for key; False when the key is over its limit for the current window."""
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
        t = time.monotonic()
        with self._lock:
            start, n = self._b.get(key, (t, 0))
            return t - start < self.window and n >= self.limit

    def reset(self):
        with self._lock:
            self._b.clear()


LIMITS = {
    "login": RateLimiter(30, 60),           # demo logins per client per minute
    "login_fail": RateLimiter(10, 600),     # wrong access codes per client per 10 minutes
    "ai": RateLimiter(30, 60),              # tutor / assistant / generator calls per user per minute
    "upload": RateLimiter(40, 600),         # uploads per user per 10 minutes
    "preview": RateLimiter(30, 60),         # PDF/DOCX previews per user per minute
    "link": RateLimiter(120, 60),           # one-time document links per user per minute
    "verify": RateLimiter(60, 60),          # public verification lookups per client per minute
}


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
