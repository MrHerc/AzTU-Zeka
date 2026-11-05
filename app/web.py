"""Tiny dependency-free HTTP layer (stdlib http.server)."""
from __future__ import annotations

import html
import json
import mimetypes
import re
import sys
import time
import traceback
import urllib.parse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .i18n import L, localize, norm_lang, tr
from .security import CFG, RateLimiter, client_ip, cross_site, header_ok

# A 10 MB upload is ~13.4 MB as base64 inside JSON; nothing larger is ever needed.
MAX_BODY = 16 * 1024 * 1024
UNSAFE = ("POST", "PUT", "DELETE")
_TRACE_LIMIT = RateLimiter(30, 60)      # full tracebacks written to the error log per minute (log-flood guard)
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("font/woff2", ".woff2")


class HTTPError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


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
        self._json = None
        self.user = None
        self.db = None
        self.lang = norm_lang(self.headers.get("X-Lang")) or norm_lang(query.get("lang")) or "az"
        self.raw_i18n = False
        self.ip = client_ip(handler)
        self.length = 0             # validated Content-Length (set by the dispatcher)
        self.body_read = False

    def json(self) -> dict:
        if self._json is None:
            length = self.length
            body = self.handler.rfile.read(length) if length else b"{}"
            self.body_read = True
            try:
                self._json = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                raise HTTPError(400, "Yanlış JSON")
            if not isinstance(self._json, dict):
                raise HTTPError(400, "JSON obyekt olmalıdır")
        return self._json


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
                params = {k: int(v) if v.isdigit() else urllib.parse.unquote(v) for k, v in mt.groupdict().items()}
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


def _body_length(headers) -> int:
    """Validated request body length. Chunked bodies and ambiguous lengths are refused (request smuggling)."""
    if headers.get("Transfer-Encoding"):
        raise HTTPError(501, "Transfer-Encoding dəstəklənmir")
    values = headers.get_all("Content-Length") or []
    if not values:
        return 0
    if len({v.strip() for v in values}) != 1 or not values[0].strip().isdigit():
        raise HTTPError(400, "Yanlış Content-Length")
    length = int(values[0].strip())
    if length > MAX_BODY:
        raise HTTPError(413, "Sorğu çox böyükdür (maks. 16 MB)")
    return length


def make_server(port: int, router: Router, static_dir: Path, before, after, log=print, host: str = "127.0.0.1"):
    static_dir = static_dir.resolve()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "Zeka"
        sys_version = ""            # do not advertise the Python version
        timeout = 30                # idle/slow clients cannot hold a worker thread forever

        def version_string(self):
            return self.server_version

        def log_message(self, fmt, *args):
            pass

        def _dispatch(self, method):
            started = time.monotonic()
            parts = urllib.parse.urlsplit(self.path)
            path = urllib.parse.unquote(parts.path)
            query = dict(urllib.parse.parse_qsl(parts.query))
            req = Request(self, method, path, query)
            try:
                req.length = _body_length(self.headers)
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
                    try:
                        before(req, roles, auth)
                        resp = fn(req)
                        after(req, ok=True)
                    except BaseException:
                        after(req, ok=False)
                        raise
                    if isinstance(resp, (dict, list)):
                        resp = json_resp(resp if req.raw_i18n else localize(resp, req.lang))
            except HTTPError as e:
                resp = self._error(path, e.status, e.message, req.lang)
            except (ValueError, TypeError) as ex:      # malformed input that a handler did not validate explicitly
                if _TRACE_LIMIT.hit("trace"):
                    log(f"400 {method} {path}: {type(ex).__name__}: {str(ex)[:200]}")
                resp = self._error(path, 400, "Sorğu məlumatı düzgün deyil", req.lang)
            except Exception:
                if _TRACE_LIMIT.hit("trace"):
                    log("".join(traceback.format_exception(*sys.exc_info())))
                resp = json_resp({"error": tr("Daxili server xətası", req.lang)}, 500)
            # An unread request body would be parsed as the next request on this keep-alive connection.
            close = bool(req.length and not req.body_read) or resp.status in (400, 413, 501) and not req.body_read
            self._send(resp, close)
            if CFG.access_log:
                print(f'{req.ip} "{method} {path}" {resp.status} {round((time.monotonic() - started) * 1000)}ms', flush=True)

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
                extra.append(("Connection", "close"))
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.ctype)
            self.send_header("Content-Length", str(len(resp.body)))
            for k, v in SECURITY_HEADERS + extra + resp.headers:
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(resp.body)

        def do_GET(self):
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
