"""web.py — router, typed JSON body accessors, request parsing, response helpers (no sockets)."""
import io
import json

import pytest

from app import web
from app.web import Body, HTTPError, Request, Router, to_int


# ---------------------------------------------------------------- router
@pytest.fixture
def router():
    r = Router()

    @r("GET", "/api/items")
    def items(req):
        return "items"

    @r("GET", "/api/items/{id:int}", roles=("admin",))
    def item(req):
        return "item"

    @r("POST", "/api/items/{id:int}/tags/{tag}", auth=False)
    def tag(req):
        return "tag"

    return r


def test_match_returns_handler_params_roles_and_auth(router):
    fn, params, roles, auth = router.match("GET", "/api/items/42")
    assert fn.__name__ == "item" and params == {"id": 42} and roles == ("admin",) and auth is True
    fn, params, roles, auth = router.match("POST", "/api/items/7/tags/qırmızı")
    assert params == {"id": 7, "tag": "qırmızı"} and roles is None and auth is False


def test_match_unknown_path_is_404_and_wrong_method_is_405(router):
    with pytest.raises(HTTPError) as e:
        router.match("GET", "/api/nothing")
    assert e.value.status == 404
    with pytest.raises(HTTPError) as e:
        router.match("DELETE", "/api/items/1")
    assert e.value.status == 405


def test_int_params_accept_only_ascii_digits(router):
    with pytest.raises(HTTPError) as e:
        router.match("GET", "/api/items/abc")
    assert e.value.status == 404
    # "²".isdigit() is True; it used to reach int("²") and crash with a 500
    fn, params, _, _ = router.match("POST", "/api/items/1/tags/²")
    assert params["tag"] == "²"


def test_params_are_not_percent_decoded_twice(router):
    # the handler already decoded the path once ("%2541" -> "%41"); a second decode turned it into "A"
    _, params, _, _ = router.match("POST", "/api/items/1/tags/%41")
    assert params["tag"] == "%41"


def test_numeric_untyped_params_become_int(router):
    _, params, _, _ = router.match("POST", "/api/items/1/tags/2024")
    assert params["tag"] == 2024


def test_registration_order_defines_priority():
    r = Router()
    r.add("GET", "/a/{x}", lambda req: 1)
    r.add("GET", "/a/fixed", lambda req: 2)
    assert r.match("GET", "/a/fixed")[0](None) == 1


# ---------------------------------------------------------------- to_int / Body
@pytest.mark.parametrize("v, expected", [(5, 5), ("12", 12), (" 7 ", 7), ("-3", -3), (4.0, 4), (None, "d"), ("", "d"), ("  ", "d")])
def test_to_int_valid(v, expected):
    assert to_int(v, "k", default="d") == expected


@pytest.mark.parametrize("v", ["abc", "1.5", "1e3", 1.5, True, False, [], {}, [1], float("inf"), float("nan"), "9" * 25, 10 ** 30])
def test_to_int_invalid_is_400(v):
    with pytest.raises(HTTPError) as e:
        to_int(v, "count")
    assert e.value.status == 400
    assert e.value.message["en"] == "Invalid value: count"


def test_to_int_clamps():
    assert to_int(500, "k", lo=1, hi=15) == 15 and to_int(-5, "k", lo=1, hi=15) == 1
    assert to_int(10 ** 30, "k", hi=100) == 100          # clamped before the 64-bit range check


def test_body_text():
    b = Body({"s": "  salam  ", "n": 5, "f": 1.5, "none": None, "lst": ["x"], "d": {}, "t": True})
    assert b.text("s") == "salam" and b.text("s", 3) == "sal"
    assert b.text("n") == "5" and b.text("f") == "1.5"
    assert b.text("missing") == "" and b.text("none", default="x") == "x"
    for key in ("lst", "d", "t"):
        with pytest.raises(HTTPError):
            b.text(key)


def test_body_number():
    b = Body({"a": "2,5", "b": 3, "c": "x", "d": True, "e": [1]})
    assert b.number("a") == 2.5 and b.number("b") == 3.0
    assert b.number("a", lo=3) == 3 and b.number("b", hi=1) == 1
    assert b.number("missing", 2) == 2
    for key in ("c", "d", "e"):
        with pytest.raises(HTTPError):
            b.number(key)


def test_body_array_ids_obj():
    b = Body({"l": [1, "2", None, ""], "s": "x", "o": {"k": 1}, "bad": ["1", "x"]})
    assert b.array("l") == [1, "2", None, ""] and b.array("missing") == []
    assert b.ids("l") == [1, 2]
    assert b.ids("l", limit=1) == [1]
    assert b.obj("o") == {"k": 1} and b.obj("missing") == {}
    for call in (lambda: b.array("s"), lambda: b.obj("s"), lambda: b.ids("bad"), lambda: b.obj("l")):
        with pytest.raises(HTTPError):
            call()


def test_body_is_still_a_dict():
    b = Body({"a": 1})
    assert isinstance(b, dict) and b.get("a") == 1 and b["a"] == 1


# ---------------------------------------------------------------- Request
class FakeHandler:
    def __init__(self, body=b"", headers=None):
        self.headers = {"Content-Length": str(len(body))} if body else {}
        self.headers.update(headers or {})
        self.rfile = io.BytesIO(body)


def make_req(body=b"", headers=None, query=None, path="/api/x"):
    return Request(FakeHandler(body, headers), "POST", path, query or {})


def test_request_json_parses_object_into_body():
    r = make_req(json.dumps({"a": "ə"}).encode())
    data = r.json()
    assert isinstance(data, Body) and data == {"a": "ə"} and r.body_read is True
    assert r.json() is data                                  # parsed once


def test_request_json_empty_body_is_empty_object():
    assert make_req().json() == {}


@pytest.mark.parametrize("raw, status", [
    (b"{not json", 400), (b"[1, 2]", 400), (b'"text"', 400), (b'{"nps": NaN}', 400), (b'{"x": Infinity}', 400),
    (b"\xff\xfe", 400),
])
def test_request_json_rejects_invalid_or_non_object(raw, status):
    with pytest.raises(HTTPError) as e:
        make_req(raw).json()
    assert e.value.status == status


def test_request_json_body_too_large(monkeypatch):
    monkeypatch.setattr(web, "MAX_BODY", 10)
    with pytest.raises(HTTPError) as e:
        make_req(b'{"a": "0123456789"}').json()
    assert e.value.status == 413


@pytest.mark.parametrize("value", ["abc", "-1", "1.5", "١٢"])
def test_request_content_length_must_be_a_non_negative_integer(value):
    # "-1" used to reach rfile.read(-1), which blocks until the client closes the connection
    with pytest.raises(HTTPError) as e:
        make_req(headers={"Content-Length": value}).content_length()
    assert e.value.status == 400


def test_request_language_from_header_then_query_then_default():
    assert make_req(headers={"X-Lang": "EN-gb"}).lang == "en"
    assert make_req(query={"lang": "ru"}).lang == "ru"
    assert make_req(headers={"X-Lang": "de"}).lang == "az"
    assert make_req().lang == "az"


def test_request_cookies_and_qint():
    r = make_req(headers={"Cookie": "zeka_sid=abc; other=1"}, query={"n": "4", "bad": "x"})
    assert r.cookies == {"zeka_sid": "abc", "other": "1"}
    assert r.qint("n") == 4 and r.qint("missing", 9) == 9
    with pytest.raises(HTTPError):
        r.qint("bad")


# ---------------------------------------------------------------- responses
def test_response_helpers():
    r = web.json_resp({"a": "ə", "d": __import__("datetime").date(2026, 1, 2)}, 201, [("X-A", "1")])
    assert r.status == 201 and r.ctype.startswith("application/json") and r.headers == [("X-A", "1")]
    assert json.loads(r.body) == {"a": "ə", "d": "2026-01-02"} and "ə".encode() in r.body
    h = web.html_resp("<p>ok</p>", 404)
    assert h.status == 404 and h.ctype.startswith("text/html") and h.body == b"<p>ok</p>"
    rd = web.redirect("/x", [("Set-Cookie", "a=b")])
    assert rd.status == 302 and rd.headers == [("Location", "/x"), ("Set-Cookie", "a=b")]


def test_security_headers_include_csp_and_nosniff():
    names = dict(web.SECURITY_HEADERS)
    assert names["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in names["Content-Security-Policy"] and "script-src 'self'" in names["Content-Security-Policy"]
