"""The real HTTP server: keep-alive, HEAD, request-size limits, static files, error pages, connection cleanup."""
import json
import re
import socket

import pytest

from app import common, web


def raw_exchange(server, payload: bytes, timeout=3.0) -> bytes:
    """Send raw bytes on one connection and read until the server closes it or goes quiet."""
    s = socket.create_connection(("127.0.0.1", server.port), timeout=timeout)
    s.sendall(payload)
    data = b""
    try:
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
    except TimeoutError:
        pass
    finally:
        s.close()
    return data


def statuses(data: bytes) -> list[int]:
    return [int(x) for x in re.findall(rb"HTTP/1\.[01] (\d{3})", data)]


def post(path: str, body: bytes, extra: str = "") -> bytes:
    return (f"POST {path} HTTP/1.1\r\nHost: t\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n{extra}\r\n").encode() + body


GET_CONTACT = b"GET /api/contact HTTP/1.1\r\nHost: t\r\nConnection: close\r\n\r\n"


# ---------------------------------------------------------------- keep-alive
@pytest.mark.parametrize("path, first_status", [
    ("/api/tutor/1/ask", 401),        # rejected by auth before the handler reads the body
    ("/api/does-not-exist", 404),     # rejected by the router
    ("/api/bootstrap", 405),          # wrong method
])
def test_unread_request_body_does_not_corrupt_the_next_request(app_db, path, first_status):
    body = json.dumps({"message": "Om qanunu nədir?"}).encode()
    data = raw_exchange(app_db, post(path, body) + GET_CONTACT)
    # regression: the body stayed in the socket and the next request failed with "400 Bad request syntax"
    assert statuses(data) == [first_status, 200]
    assert b"info@aztu.edu.az" in data


def test_wrong_content_type_body_is_also_discarded(app_db):
    payload = (b"POST /api/auth/demo HTTP/1.1\r\nHost: t\r\nContent-Type: text/plain\r\nContent-Length: 5\r\n\r\nhello" + GET_CONTACT)
    assert statuses(raw_exchange(app_db, payload)) == [415, 200]


def test_two_valid_requests_share_a_connection(app_db):
    data = raw_exchange(app_db, post("/api/auth/demo", json.dumps({"role": "student"}).encode()) + GET_CONTACT)
    assert statuses(data) == [200, 200]


# ---------------------------------------------------------------- Content-Length
@pytest.mark.parametrize("value", ["abc", "-1", "1.5"])
def test_invalid_content_length_is_400_and_closes_the_connection(app_db, value):
    payload = (f"POST /api/auth/demo HTTP/1.1\r\nHost: t\r\nContent-Type: application/json\r\nContent-Length: {value}\r\n\r\n").encode()
    data = raw_exchange(app_db, payload, timeout=5)
    # regression: "abc" answered 500 and "-1" blocked the server thread in rfile.read(-1)
    assert statuses(data) == [400]
    assert b"Connection: close" in data


def test_oversized_body_is_413_without_reading_it(app_db, monkeypatch):
    token = app_db.client().post("/api/auth/demo", {"role": "student"}).json["token"]
    monkeypatch.setattr(web, "MAX_BODY", 1000)
    payload = (f"POST /api/files HTTP/1.1\r\nHost: t\r\nX-Session: {token}\r\nContent-Type: application/json\r\n"
               "Content-Length: 5000000\r\n\r\n").encode()
    data = raw_exchange(app_db, payload)
    assert statuses(data) == [413] and b"Connection: close" in data


def test_rejected_request_with_a_body_too_large_to_drain_closes_the_connection(app_db):
    payload = (f"POST /api/files HTTP/1.1\r\nHost: t\r\nContent-Type: application/json\r\nContent-Length: {web.DRAIN_LIMIT + 1}\r\n\r\n").encode()
    data = raw_exchange(app_db, payload)
    assert statuses(data) == [401] and b"Connection: close" in data


# ---------------------------------------------------------------- HEAD
@pytest.mark.parametrize("path, ctype", [("/", "text/html"), ("/api/achievements", "application/json"), ("/static/css/app.css", "text/css")])
def test_head_returns_headers_without_body(app_db, path, ctype):
    data = raw_exchange(app_db, f"HEAD {path} HTTP/1.1\r\nHost: t\r\nConnection: close\r\n\r\n".encode())
    head, _, body = data.partition(b"\r\n\r\n")
    # regression: HEAD answered "501 Unsupported method" although _send() was written to support it
    assert statuses(head) == [200]
    assert ctype.encode() in head and int(re.search(rb"Content-Length: (\d+)", head).group(1)) > 0
    assert body == b""


def test_unsupported_method_is_501(app_db):
    assert statuses(raw_exchange(app_db, b"PATCH /api/me HTTP/1.1\r\nHost: t\r\nConnection: close\r\n\r\n")) == [501]


# ---------------------------------------------------------------- static files
def test_index_and_static_assets(anon):
    r = anon.get("/")
    assert r.status == 200 and r.headers["Content-Type"] == "text/html; charset=utf-8" and r.headers["Cache-Control"] == "no-cache"
    js = anon.get("/static/js/main.js")
    assert js.status == 200 and js.headers["Content-Type"] == "text/javascript; charset=utf-8"
    font = anon.get("/static/fonts/inter-latin.woff2")
    assert font.headers["Content-Type"] == "font/woff2" and font.headers["Cache-Control"] == "public, max-age=86400"
    fav = anon.get("/favicon.ico")
    assert fav.status == 200 and fav.headers["Content-Type"].startswith("image/svg+xml")


@pytest.mark.parametrize("path", [
    "/static/../app/web.py", "/static/%2e%2e/app/web.py", "/static/..%2fapp%2fweb.py", "/static//etc/passwd",
    "/static/", "/static/js", "/static/nope.js",
])
def test_static_never_serves_outside_the_static_folder(anon, path):
    r = anon.get(path)
    assert r.status == 404 and b"def make_server" not in r.body and b"root:" not in r.body


def test_security_headers_on_every_response(anon):
    for path in ("/", "/api/bootstrap", "/api/nope", "/verify/XXXX-XXXX"):
        h = anon.get(path).headers
        assert h["X-Content-Type-Options"] == "nosniff" and "default-src 'self'" in h["Content-Security-Policy"]
        assert h["Referrer-Policy"] == "same-origin"


# ---------------------------------------------------------------- errors
def test_api_errors_are_json_and_translated(anon):
    for lang, text in (("az", "Daxil olmamısınız"), ("en", "You are not signed in")):
        r = anon.get("/api/courses", lang=lang)
        assert r.status == 401 and r.json == {"error": text}
    r = anon.get("/api/courses?lang=ru")
    assert r.status == 401 and re.search("[а-я]", r.json["error"])


def test_non_api_errors_are_escaped_html(anon):
    r = anon.get("/no/such/<script>")
    assert r.status == 404 and r.headers["Content-Type"].startswith("text/html")
    assert "<script>" not in r.text


def test_malformed_json_bodies(student):
    assert student.request("POST", "/api/tutor/1/ask", raw=b"{oops", headers={"Content-Type": "application/json"}).status == 400
    assert student.request("POST", "/api/tutor/1/ask", raw=b"[1]", headers={"Content-Type": "application/json"}).status == 400
    nan = student.request("POST", "/api/feedback", raw=b'{"score": 5, "nps": NaN}', headers={"Content-Type": "application/json"})
    assert nan.status == 400 and nan.json["error"] == "Yanlış JSON"


# ---------------------------------------------------------------- DB connections
def test_every_request_closes_its_database_connection(app_db, monkeypatch):
    opened, closed = [], []
    real = common.store.connect

    class Tracked:
        def __init__(self, conn):
            self._c = conn
            opened.append(self)

        def __getattr__(self, name):
            return getattr(self._c, name)

        def close(self):
            closed.append(self)
            return self._c.close()

    monkeypatch.setattr(common.store, "connect", lambda: Tracked(real()))
    anon, student = app_db.client(), app_db.client("student")
    anon.get("/api/courses")              # 401 raised in before()
    student.get("/api/analytics")         # 403 raised in before()
    student.get("/api/courses/999")       # 404 raised in the handler
    student.get("/api/courses")           # 200
    # regression: connections opened by before() were never closed when it raised 401/403
    assert opened and len(closed) == len(opened)
