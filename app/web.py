"""Tiny dependency-free HTTP layer (stdlib http.server)."""
from __future__ import annotations

import html
import json
import mimetypes
import re
import sys
import traceback
import urllib.parse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .i18n import L, localize, norm_lang, tr

MAX_BODY = 30 * 1024 * 1024
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

    def json(self) -> dict:
        if self._json is None:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise HTTPError(413, "Fayl çox böyükdür (maks. 30 MB)")
            body = self.handler.rfile.read(length) if length else b"{}"
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
    ("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                "script-src 'self'; connect-src 'self'"),
]


def make_server(port: int, router: Router, static_dir: Path, before, after, log=print, host: str = "127.0.0.1"):
    static_dir = static_dir.resolve()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "ZekaDemo/0.3"

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
                        if int(self.headers.get("Content-Length") or 0) and "application/json" not in ctype:
                            raise HTTPError(415, "Content-Type application/json olmalıdır")
                    fn, params, roles, auth = router.match(method, path)
                    req.params = params
                    before(req, roles, auth)
                    try:
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
            self._send(resp)

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
