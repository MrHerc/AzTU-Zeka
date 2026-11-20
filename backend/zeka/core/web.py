"""Tiny dependency-free HTTP layer (stdlib http.server)."""
from __future__ import annotations

import html
import json
import math
import os
import mimetypes
import re
import socket
import sys
import threading
import time
import traceback
import urllib.parse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import clock, config, perms
from .i18n import E, L, localize, norm_lang, tr
from .security import CFG, RateLimiter, client_ip, cross_site, header_ok

# A 10 MB upload is ~13.4 MB as base64 inside JSON; nothing larger is ever needed.
MAX_BODY = 16 * 1024 * 1024
MAX_INT = 2 ** 63 - 1            # SQLite INTEGER range
UNSAFE = ("POST", "PUT", "DELETE")
_TRACE_LIMIT = RateLimiter(30, 60)      # full tracebacks written to the error log per minute (log-flood guard)
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("font/woff2", ".woff2")


class HTTPError(Exception):
    """An error answered to the client; ``message`` is an Azerbaijani catalog key or an i18n dict (``E(...)``)."""

    def __init__(self, status: int, message: str | dict):
        super().__init__(message)
        self.status, self.message = status, message


def _reject_constant(name):
    raise ValueError(f"non-standard JSON constant {name}")


def _bad_value(key):
    raise HTTPError(400, E("Yanlış dəyər: {field}", field=key))


def to_int(v, key: str, default=None, lo=None, hi=None):
    """Parse a client-supplied integer (JSON number or digit string); None/"" give ``default``; anything else is a 400."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return default
    if isinstance(v, bool):
        _bad_value(key)
    if isinstance(v, float):
        if not math.isfinite(v) or not v.is_integer():
            _bad_value(key)
        v = int(v)
    elif isinstance(v, str):
        t = v.strip()
        if not re.fullmatch(r"[+-]?\d{1,19}", t):
            _bad_value(key)
        v = int(t)
    elif not isinstance(v, int):
        _bad_value(key)
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    if not -MAX_INT <= v <= MAX_INT:
        _bad_value(key)
    return v


class Body(dict):
    """A parsed JSON request object with typed accessors.

    A value of the wrong JSON type is the client's mistake and is answered with 400 — it must never surface as a
    500 from deep inside a handler (``int("abc")``, ``[].strip()``, an unhashable list used as a SQL parameter…).
    """

    def text(self, key: str, limit: int | None = None, default: str = "") -> str:
        v = self.get(key)
        if v is None:
            return default
        if isinstance(v, bool) or not isinstance(v, (str, int, float)):
            _bad_value(key)
        out = str(v).strip()
        return out[:limit] if limit is not None else out

    def integer(self, key: str, default=None, lo=None, hi=None):
        return to_int(self.get(key), key, default, lo, hi)

    def number(self, key: str, default=None, lo=None, hi=None):
        v = self.get(key)
        if v is None or (isinstance(v, str) and not v.strip()):
            return default
        if isinstance(v, bool) or not isinstance(v, (str, int, float)):
            _bad_value(key)
        try:
            f = float(str(v).strip().replace(",", ".")) if isinstance(v, str) else float(v)
        except ValueError:
            _bad_value(key)
        if not math.isfinite(f):
            _bad_value(key)
        if lo is not None:
            f = max(lo, f)
        if hi is not None:
            f = min(hi, f)
        return f

    def array(self, key: str) -> list:
        v = self.get(key)
        if v is None:
            return []
        if not isinstance(v, list):
            _bad_value(key)
        return v

    def ids(self, key: str, limit: int = 100) -> list[int]:
        return [to_int(x, key, lo=None) for x in self.array(key)[:limit] if x not in (None, "")]

    def obj(self, key: str) -> dict:
        v = self.get(key)
        if v is None:
            return {}
        if not isinstance(v, dict):
            _bad_value(key)
        return v


class Request:
    def __init__(self, handler, method, path, query, params=None):
        self.handler, self.method, self.path, self.query = handler, method, path, query
        self.params = params or {}
        self.headers = handler.headers
        self.cookies = {}
        raw = self.headers.get("Cookie")
        if raw:
            ck = SimpleCookie()
            ck.load(raw)
            self.cookies = {k: v.value for k, v in ck.items()}
        self._json: Body | None = None
        self.user = None
        self.db = None
        self.lang = norm_lang(self.headers.get("X-Lang")) or norm_lang(query.get("lang")) or "az"
        self.raw_i18n = False
        self.ip = client_ip(handler)
        self.length = 0             # validated Content-Length (set by the dispatcher)
        self.body_read = False
        self.raw: bytes | None = None   # the body, read by the dispatcher before a handler slot is taken
        self.audit_kind = None          # the route's audit_read kind (Task 13); the handler names whose data it read:
        self.read_owner = None          # the person the data belongs to
        self.read_object = None         # the id of what was read
        self.route_scope = None         # Task 27: the route's scope ("exam" or None)
        self.endpoint = None            # Task 39: the route's handler; its module and name go to the event log

    def content_length(self) -> int:
        raw = (self.headers.get("Content-Length") or "").strip()
        if not raw:
            return 0
        if not raw.isascii() or not raw.isdigit():     # also rejects negative values: read(-1) would block until EOF
            raise HTTPError(400, "Yanlış Content-Length")
        if len(raw) > 9 or int(raw) > MAX_BODY:          # 5 000 digits would overflow int() into a logged ValueError
            raise HTTPError(413, "Sorğu çox böyükdür (maks. 16 MB)")
        return int(raw)

    def json(self) -> Body:
        if self._json is None:
            if self.raw is None:
                length = self.content_length()
                self.raw = self.handler.rfile.read(length) if length else b""
            self.body_read = True
            body = self.raw or b"{}"
            try:
                data = json.loads(body.decode("utf-8") or "{}", parse_constant=_reject_constant)
            except ValueError:
                raise HTTPError(400, "Yanlış JSON") from None
            if not isinstance(data, dict):
                raise HTTPError(400, "JSON obyekt olmalıdır")
            self._json = Body(data)
        return self._json

    def qint(self, key: str, default=None, lo=None, hi=None):
        """Integer from the query string (400 when it is not a number)."""
        return to_int(self.query.get(key), key, default, lo, hi)


class Response:
    def __init__(self, body=b"", status=200, ctype="application/json; charset=utf-8", headers=None):
        self.body = body if isinstance(body, bytes) else str(body).encode("utf-8")
        self.status, self.ctype = status, ctype
        self.headers = headers or []


def json_resp(data, status=200, headers=None):
    return Response(json.dumps(data, ensure_ascii=False, default=str), status, headers=headers)


def html_resp(text, status=200, headers=None):
    return Response(text, status, "text/html; charset=utf-8", headers)


def redirect(location, headers=None):
    return Response(b"", 302, "text/plain", [("Location", location)] + (headers or []))


# Handler gate (tasks/todo.md, Task 6). Measured on the demo: an unbounded number of handler threads contending for
# the GIL and SQLite gave 47 req/s at 20 clients and errors at 300; two at a time gave 226 req/s and none.
HANDLERS = max(1, int(os.environ.get("ZEKA_HANDLERS", "2")))
SLOW_HANDLERS = max(1, int(os.environ.get("ZEKA_SLOW", "4")))   # routes that wait on the network (slow=True) never take a GATE slot
QUEUE_WAIT = float(os.environ.get("ZEKA_QUEUE_WAIT", "10"))      # seconds a request may wait for a slot before a 503
GATE = threading.BoundedSemaphore(HANDLERS)
SLOW = threading.BoundedSemaphore(SLOW_HANDLERS)


_INFLIGHT = [0]                 # requests between parsing and the last byte of their response
_IDLE = threading.Condition()
_STOPPING = [False]


def drain(timeout: float = QUEUE_WAIT) -> bool:
    """Graceful stop after the listening socket is closed: every answer from now on closes its keep-alive connection, and
    this returns once every started request has been answered (its response written), or after ``timeout``."""
    _STOPPING[0] = True
    with _IDLE:
        return _IDLE.wait_for(lambda: _INFLIGHT[0] == 0, timeout=timeout)


MAX_ID = 2 ** 63 - 1                     # the largest SQLite integer


def an_id(v) -> int | None:
    """``v`` when it is a row id a JSON body may carry (a positive integer SQLite can hold), else None."""
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 < v <= MAX_ID else None


class Router:
    def __init__(self):
        self.routes = []

    def add(self, method, pattern, fn, roles=None, auth=True):
        # the literal parts are escaped: the "." of /api/v1/oneroster.zip or /.well-known/security.txt is a dot (Task 41)
        parts = re.split(r"(\{\w+(?::int)?\})", pattern)
        regex = "^" + "".join((f"(?P<{x[1:-1].split(':')[0]}>{'[0-9]+' if x.endswith(':int}') else '[^/]+'})" if i % 2 else re.escape(x))
                              for i, x in enumerate(parts)) + "$"
        self.routes.append((method, re.compile(regex), fn, roles, auth))

    def __call__(self, method, pattern, roles=None, auth=True, demo=False, slow=False, perm=None, audit_read=None, scope=None):
        if perm and roles:
            raise ValueError(f"{method} {pattern}: give roles= or perm=, not both")

        def deco(fn):
            fn.demo_only = demo        # demo-only routes do not exist in prod mode (404, not 403)
            fn.slow = slow             # waits on an outside service: runs under SLOW, not GATE
            fn.perm = perm             # Task 13: a permission from core/perms.py, checked as the roles that hold it
            fn.audit_read = audit_read  # Task 13: reading another person's data of this kind is written to the audit log
            fn.scope = scope           # Task 27: "exam" routes answer only a session scoped to that exam, and only they do
            self.add(method, pattern, fn, perms.roles_for(perm) if perm else roles, auth)
            return fn
        return deco

    def match(self, method, path):
        allowed = False
        for m, rx, fn, roles, auth in self.routes:
            mt = rx.match(path)
            if not mt or (config.prod() and getattr(fn, "demo_only", False)):
                continue
            allowed = True
            if m == method:
                # The path is already percent-decoded by the handler; decoding again would turn "%2541" into "A".
                # Only ASCII digits are converted ("²".isdigit() is True, but int("²") raises).
                raw = mt.groupdict()
                if any(v.isascii() and v.isdigit() and (len(v) > 19 or int(v) > MAX_ID) for v in raw.values()):
                    raise HTTPError(404, "Tapılmadı")          # SQLite would overflow (int() too, past 4300 digits)
                params = {k: int(v) if v.isascii() and v.isdigit() else v for k, v in raw.items()}
                return fn, params, roles, auth
        raise HTTPError(405 if allowed else 404, "Tapılmadı" if not allowed else "Metod dəstəklənmir")


SECURITY_HEADERS = [
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "same-origin"),
    ("X-Frame-Options", "SAMEORIGIN"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"),
    ("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
                                "form-action 'self'; frame-ancestors 'self'"),
]
HSTS = ("Strict-Transport-Security", "max-age=31536000")


def _body_length(req: Request) -> int:
    """Validated request body length. Chunked bodies and ambiguous lengths are refused (request smuggling)."""
    if req.headers.get("Transfer-Encoding"):
        raise HTTPError(501, "Transfer-Encoding dəstəklənmir")
    if len({v.strip() for v in req.headers.get_all("Content-Length") or []}) > 1:
        raise HTTPError(400, "Yanlış Content-Length")
    return req.content_length()


def make_server(port: int, router: Router, static_dir: Path, before, after, log=print, host: str = "127.0.0.1", reuse_port: bool = False):
    static_dir = static_dir.resolve()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "Zeka"
        sys_version = ""            # do not advertise the Python version
        timeout = 30                # idle/slow clients cannot hold a worker thread forever
        disable_nagle_algorithm = True   # headers and body are two writes: with Nagle the body waits ~40 ms for a delayed ACK

        def version_string(self):
            return self.server_version

        def log_message(self, fmt, *args):
            pass

        def _dispatch(self, method):
            with _IDLE:
                _INFLIGHT[0] += 1
            try:
                self._answer(method)
            finally:
                with _IDLE:
                    _INFLIGHT[0] -= 1
                    _IDLE.notify_all()

        def _answer(self, method):
            started = time.monotonic()
            parts = urllib.parse.urlsplit(self.path)
            path = urllib.parse.unquote(parts.path)
            shown = "/ical/…" if path.startswith("/ical/") else path      # a calendar feed's path is its secret: never logged
            query = dict(urllib.parse.parse_qsl(parts.query))
            req = Request(self, method, path, query)
            try:
                req.length = _body_length(req)
                if method == "GET" and (path == "/" or path.startswith("/static/") or path == "/favicon.ico"):
                    resp = self._static("index.html" if path == "/" else path[len("/static/"):] if path != "/favicon.ico" else "img/favicon.svg")
                else:
                    if method in UNSAFE:
                        if cross_site(self.headers):
                            raise HTTPError(403, "Sorğu başqa saytdan göndərilib və rədd edildi")
                        media = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                        if req.length and media != "application/json":
                            raise HTTPError(415, "Content-Type application/json olmalıdır")
                    fn, params, roles, auth = router.match(method, path)
                    req.params = params
                    # a slow upload waits here on its own thread, never inside a handler slot; a request that cannot pass
                    # auth (no credential at all) is still answered without its body being read, then its connection closed
                    if req.length and (not auth or self.headers.get("Cookie")):
                        req.raw = self.rfile.read(req.length)
                        req.body_read = True
                    sem = SLOW if getattr(fn, "slow", False) else GATE
                    if not sem.acquire(timeout=QUEUE_WAIT):
                        raise HTTPError(503, "Server məşğuldur, bir neçə saniyədən sonra yenidən cəhd edin")
                    try:
                        try:
                            req.audit_kind = getattr(fn, "audit_read", None)
                            req.route_scope = getattr(fn, "scope", None)
                            req.endpoint = fn
                            before(req, roles, auth)      # inside the try: a 401/403 must still close the DB connection
                            resp = fn(req)
                            after(req, ok=True)
                        except BaseException:
                            after(req, ok=False)
                            raise
                        if isinstance(resp, (dict, list)):
                            resp = json_resp(resp if req.raw_i18n else localize(resp, req.lang))
                    finally:
                        sem.release()
            except HTTPError as e:
                resp = self._error(path, e.status, e.message, req.lang)
                if e.status == 503:
                    resp.headers.append(("Retry-After", "5"))
            except (ValueError, TypeError, OverflowError) as ex:      # malformed input a handler did not validate (an id > 2**63 too)
                if _TRACE_LIMIT.hit("trace"):
                    log(f"400 {method} {shown}: {type(ex).__name__}: {str(ex)[:200]}")
                resp = self._error(path, 400, "Sorğu məlumatı düzgün deyil", req.lang)
            except Exception:
                if _TRACE_LIMIT.hit("trace"):
                    log("".join(traceback.format_exception(*sys.exc_info())))
                resp = json_resp({"error": tr("Daxili server xətası", req.lang)}, 500)
            # An unread request body would be parsed as the next request on this keep-alive connection.
            close = bool(req.length and not req.body_read) or resp.status in (400, 413, 501) and not req.body_read
            self._send(resp, close or _STOPPING[0])
            if CFG.access_log:      # one JSON object per line, written at once: a path cannot forge or split an entry
                sys.stdout.write(json.dumps({"time": clock.now().isoformat(timespec="milliseconds"), "ip": req.ip,
                                             "method": method, "path": shown,
                                             "status": resp.status,
                                             "ms": round((time.monotonic() - started) * 1000), "worker": os.getpid()},
                                            ensure_ascii=False) + "\n")
                sys.stdout.flush()

        def _error(self, path, status, message, lang):
            msg = L(message, lang) if isinstance(message, dict) else tr(message, lang)
            if path.startswith("/api/"):
                return json_resp({"error": msg}, status)
            return html_resp(f"<h1>{status}</h1><p>{html.escape(str(msg))}</p>", status)

        def _static(self, rel):
            target = (static_dir / rel).resolve()
            if static_dir not in target.parents and target != static_dir or not target.is_file():
                raise HTTPError(404, "Fayl tapılmadı")
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript") or ctype.endswith("svg+xml"):
                ctype += "; charset=utf-8"
            cache = "public, max-age=86400" if target.suffix in (".woff2", ".png") else "no-cache"
            return Response(target.read_bytes(), 200, ctype, [("Cache-Control", cache)])

        def _send(self, resp, close=False):
            if not all(header_ok(k, v) for k, v in resp.headers):   # header injection (CR/LF) never reaches the wire
                resp = json_resp({"error": "Bad response header"}, 500)
            extra = [HSTS] if CFG.https else []
            if not any(k.lower() == "cache-control" for k, _ in resp.headers):
                extra.append(("Cache-Control", "no-store"))        # API data and documents are personal
            if close:
                self.close_connection = True
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.ctype)
            self.send_header("Content-Length", str(len(resp.body)))
            for k, v in SECURITY_HEADERS + extra + resp.headers:
                self.send_header(k, v)
            if self.close_connection:
                self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(resp.body)

        def do_GET(self):
            self._dispatch("GET")

        def do_HEAD(self):              # same headers as GET; _send() leaves out the body (health checks, uptime monitors)
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PUT(self):
            self._dispatch("PUT")

        def do_DELETE(self):
            self._dispatch("DELETE")

    class Server(ThreadingHTTPServer):
        # socketserver's default listen backlog is 5: at 300 simultaneous clients the kernel dropped connection attempts
        # and clients hung in SYN retries for up to a minute (measured: 94 connection errors, p99 61 s).
        request_queue_size = 1024

        def server_bind(self):
            if reuse_port:              # several worker processes share the port; the kernel spreads connections
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            super().server_bind()

    srv = Server((host, port), Handler)
    srv.daemon_threads = True
    return srv
