"""Tiny dependency-free HTTP layer (stdlib http.server)."""
from __future__ import annotations

import html
import json
import math
import mimetypes
import re
import sys
import traceback
import urllib.parse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .i18n import E, L, localize, norm_lang, tr

MAX_BODY = 30 * 1024 * 1024
DRAIN_LIMIT = 1024 * 1024        # an unread request body up to this size is discarded so the keep-alive connection stays usable
MAX_INT = 2 ** 63 - 1            # SQLite INTEGER range
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
        self.body_read = False
        self.user = None
        self.db = None
        self.lang = norm_lang(self.headers.get("X-Lang")) or norm_lang(query.get("lang")) or "az"
        self.raw_i18n = False

    def content_length(self) -> int:
        raw = (self.headers.get("Content-Length") or "").strip()
        if not raw:
            return 0
        if not raw.isascii() or not raw.isdigit():     # also rejects negative values: read(-1) would block until EOF
            raise HTTPError(400, "Yanlış Content-Length başlığı")
        return int(raw)

    def json(self) -> Body:
        if self._json is None:
            length = self.content_length()
            if length > MAX_BODY:
                raise HTTPError(413, "Fayl çox böyükdür (maks. 30 MB)")
            body = self.handler.rfile.read(length) if length else b"{}"
            self.body_read = True
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


class Router:
    def __init__(self):
        self.routes = []

    def add(self, method, pattern, fn, roles=None, auth=True):
        regex = "^" + re.sub(r"\{(\w+)(:int)?\}", lambda m: f"(?P<{m.group(1)}>{'[0-9]+' if m.group(2) else '[^/]+'})", pattern) + "$"
        self.routes.append((method, re.compile(regex), fn, roles, auth))

    def __call__(self, method, pattern, roles=None, auth=True):
        def deco(fn):
            self.add(method, pattern, fn, roles, auth)
            return fn
        return deco

    def match(self, method, path):
        allowed = False
        for m, rx, fn, roles, auth in self.routes:
            mt = rx.match(path)
            if not mt:
                continue
            allowed = True
            if m == method:
                # The path is already percent-decoded by the handler; decoding again would turn "%2541" into "A".
                # Only ASCII digits are converted ("²".isdigit() is True, but int("²") raises).
                params = {k: int(v) if v.isascii() and v.isdigit() else v for k, v in mt.groupdict().items()}
                return fn, params, roles, auth
        raise HTTPError(405 if allowed else 404, "Tapılmadı" if not allowed else "Metod dəstəklənmir")


SECURITY_HEADERS = [
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "same-origin"),
    ("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                "script-src 'self'; connect-src 'self'"),
]


def make_server(port: int, router: Router, static_dir: Path, before, after, log=print, host: str = "127.0.0.1"):
    static_dir = static_dir.resolve()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "ZekaDemo/0.3"
        timeout = 120            # seconds; an idle or stalled connection must not hold a server thread forever

        def log_message(self, fmt, *args):
            pass

        def _dispatch(self, method):
            parts = urllib.parse.urlsplit(self.path)
            path = urllib.parse.unquote(parts.path)
            query = dict(urllib.parse.parse_qsl(parts.query))
            req = Request(self, method, path, query)
            try:
                if method == "GET" and (path == "/" or path.startswith("/static/") or path == "/favicon.ico"):
                    resp = self._static("index.html" if path == "/" else path[len("/static/"):] if path != "/favicon.ico" else "img/favicon.svg")
                else:
                    if method in ("POST", "PUT", "DELETE") and path.startswith("/api/"):
                        ctype = self.headers.get("Content-Type", "")
                        if req.content_length() and "application/json" not in ctype:
                            raise HTTPError(415, "Content-Type application/json olmalıdır")
                    fn, params, roles, auth = router.match(method, path)
                    req.params = params
                    try:
                        before(req, roles, auth)      # inside the try: a 401/403 must still close the DB connection
                        resp = fn(req)
                        after(req, ok=True)
                    except Exception:
                        after(req, ok=False)
                        raise
                    if isinstance(resp, (dict, list)):
                        resp = json_resp(resp if req.raw_i18n else localize(resp, req.lang))
            except HTTPError as e:
                msg = L(e.message, req.lang) if isinstance(e.message, dict) else tr(e.message, req.lang)
                if path.startswith("/api/"):
                    resp = json_resp({"error": msg}, e.status)
                else:
                    resp = html_resp(f"<h1>{e.status}</h1><p>{html.escape(str(msg))}</p>", e.status)
            except Exception:
                log("".join(traceback.format_exception(*sys.exc_info())))
                resp = json_resp({"error": tr("Daxili server xətası", req.lang)}, 500)
            self._discard_body(req)
            self._send(resp)

        def _discard_body(self, req):
            """Keep-alive: a body the handler never read (401, 404, 415 …) would be parsed as the next request line."""
            if req.body_read:
                return
            try:
                n = req.content_length()
            except HTTPError:
                n = -1
            if 0 < n <= DRAIN_LIMIT:
                self.rfile.read(n)
            elif n:
                self.close_connection = True

        def _static(self, rel):
            target = (static_dir / rel).resolve()
            if static_dir not in target.parents and target != static_dir or not target.is_file():
                raise HTTPError(404, "Fayl tapılmadı")
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript") or ctype.endswith("svg+xml"):
                ctype += "; charset=utf-8"
            cache = "public, max-age=86400" if target.suffix in (".woff2", ".png") else "no-cache"
            return Response(target.read_bytes(), 200, ctype, [("Cache-Control", cache)])

        def _send(self, resp):
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.ctype)
            self.send_header("Content-Length", str(len(resp.body)))
            for k, v in SECURITY_HEADERS + resp.headers:
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

    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    return srv
