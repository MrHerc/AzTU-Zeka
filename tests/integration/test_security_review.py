"""Security regression tests for the findings of docs/SECURITY_REVIEW.md.

These are the 43 "sec:" checks that the security review added to the former ``tests/selftest.py``, ported one for
one; the comment above each assertion is the name the check had there. Two of them changed with the port:

* "sec: syllabus save" — the review coerced a non-numeric assessment score to a number and saved the syllabus; the
  save handler now also validates the shape strictly, so that value is refused with 400 and the rest is saved.
* "sec: late quiz answers are not graded" submits the correct answers (the original sent option 0 for every
  question), so a graded late attempt cannot pass unnoticed.
"""
import socket

import pytest

from app import security, store
from app.r_learning import _masked_history

EVIL = "<script>alert(1)</script><img src=x onerror=alert(2)>"
CODE = "zeka-test-code-7"


def raw_http(server, payload: bytes, wait=3.0) -> bytes:
    """Send raw bytes, return everything the server writes until it closes or goes quiet."""
    sk = socket.create_connection(("127.0.0.1", server.port), timeout=wait)
    out = b""
    try:
        sk.sendall(payload)
        while True:
            chunk = sk.recv(65536)
            if not chunk:
                break
            out += chunk
    except TimeoutError:
        pass
    finally:
        sk.close()
    return out


def set_time(table: str, column: str, key: str, value):
    """Move one timestamp into the past, straight in the database."""
    db = store.connect()
    try:
        db.execute(f"UPDATE {table} SET {column}=? WHERE {key}=?", ("2000-01-01T00:00:00", value))
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------- response headers
def test_api_response_headers(student):
    r = student.get("/api/me")
    csp = r.headers.get("Content-Security-Policy", "")
    # sec: CSP frame-ancestors/base-uri/object-src
    assert "frame-ancestors 'self'" in csp and "object-src 'none'" in csp and "base-uri 'none'" in csp
    # sec: X-Frame-Options + nosniff
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN" and r.headers.get("X-Content-Type-Options") == "nosniff"
    # sec: API responses not cached
    assert r.headers.get("Cache-Control") == "no-store"
    # sec: no Python version in Server header
    assert "python" not in r.headers.get("Server", "").lower()


def test_static_files_keep_their_cache_policy(anon):
    r = anon.get("/static/js/core.js")
    # sec: static files keep their cache policy
    assert r.status == 200 and r.headers.get("Cache-Control") == "no-cache"


# ---------------------------------------------------------------- CRLF injection / open redirect in the GET demo login (next=)
@pytest.mark.parametrize("nxt", [
    "/x%0d%0aSet-Cookie:%20pwned=1", "/%09/evil.example", "//evil.example", "/\\evil.example", "https://evil.example",
])
def test_demo_login_next_stays_on_site(app_db, nxt):
    resp = raw_http(app_db, f"GET /demo/login?role=student&next={nxt} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n".encode())
    head = resp.split(b"\r\n\r\n", 1)[0].decode("latin-1")
    loc = next((ln.split(":", 1)[1].strip() for ln in head.split("\r\n") if ln.lower().startswith("location:")), "")
    # sec: demo login next=… stays on site
    assert head.startswith("HTTP/1.1 302") and "pwned" not in head and loc == "/", head[:300]


def test_demo_login_keeps_a_valid_in_app_next(app_db):
    resp = raw_http(app_db, b"GET /demo/login?role=student&next=/%23/student/services HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
    # sec: demo login keeps a valid in-app next
    assert b"Location: /#/student/services" in resp, resp[:300]


# ---------------------------------------------------------------- CSRF
@pytest.mark.parametrize("headers", [
    {"Sec-Fetch-Site": "cross-site"},           # sec: CSRF Sec-Fetch-Site cross-site refused
    {"Sec-Fetch-Site": "same-site"},            # sec: CSRF same-site (sibling subdomain) refused
    {"Origin": "https://evil.example"},         # sec: CSRF foreign Origin refused
    {"Origin": "null"},                         # sec: CSRF Origin null refused
])
def test_cross_site_requests_with_cookies_are_refused(student, headers):
    assert student.post("/api/notifications/read", {}, headers=headers).status == 403


def test_same_origin_requests_are_allowed(app_db, student):
    # sec: same-origin request allowed
    assert student.post("/api/notifications/read", {}, headers={"Sec-Fetch-Site": "same-origin", "Origin": app_db.url}).status == 200
    # sec: same-origin by Origin header allowed
    assert student.post("/api/notifications/read", {}, headers={"Origin": app_db.url}).status == 200


def test_simple_request_content_type_is_refused(student):
    # sec: simple-request content type refused
    assert student.post("/api/notifications/read", {}, headers={"Content-Type": "text/plain; x=application/json"}).status == 415


# ---------------------------------------------------------------- request smuggling / desync guards
def test_chunked_request_bodies_are_refused(app_db):
    resp = raw_http(app_db, b"POST /api/feedback HTTP/1.1\r\nHost: 127.0.0.1\r\nTransfer-Encoding: chunked\r\n"
                            b"Content-Type: application/json\r\n\r\n2\r\n{}\r\n0\r\n\r\n")
    # sec: chunked request bodies refused
    assert resp.startswith(b"HTTP/1.1 501") and resp.count(b"HTTP/1.1 ") == 1, resp[:200]


def test_negative_content_length_is_refused(app_db):
    resp = raw_http(app_db, b"POST /api/feedback HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: -5\r\nContent-Type: application/json\r\n\r\n")
    # sec: negative Content-Length refused
    assert resp.startswith(b"HTTP/1.1 400"), resp[:200]


def test_conflicting_content_length_is_refused(app_db):
    resp = raw_http(app_db, b"POST /api/feedback HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 2\r\nContent-Length: 40\r\n"
                            b"Content-Type: application/json\r\n\r\n{}")
    # sec: conflicting Content-Length refused
    assert resp.startswith(b"HTTP/1.1 400"), resp[:200]


def test_oversized_body_is_refused_before_reading(app_db):
    resp = raw_http(app_db, b"POST /api/feedback HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 99999999\r\nContent-Type: application/json\r\n\r\n")
    # sec: oversized body refused before reading
    assert resp.startswith(b"HTTP/1.1 413"), resp[:200]


def test_unread_body_is_not_parsed_as_a_second_request(app_db):
    smuggled = b"GET /api/contact HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
    resp = raw_http(app_db, b"POST /api/feedback HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: "
                            + str(len(smuggled)).encode() + b"\r\n\r\n" + smuggled)
    # sec: unread body is not parsed as a second request
    assert resp.startswith(b"HTTP/1.1 401") and resp.count(b"HTTP/1.1 ") == 1, resp[:300]


# ---------------------------------------------------------------- malformed input
def test_bad_ids_are_400(student):
    # sec: bad ids -> 400   (not a 500 with a traceback in the log)
    assert student.post("/api/notifications/read", {"ids": ["x"]}).status == 400


# ---------------------------------------------------------------- session lifetime
def test_an_expired_session_is_no_longer_accepted(app_db):
    c = app_db.client()
    token = c.post("/api/auth/demo", {"role": "student"}).json["token"]
    # sec: fresh session works
    assert c.get("/api/me").status == 200
    set_time("sessions", "created_at", "sid", token)
    # sec: expired session rejected
    assert c.get("/api/me").status == 401


# ---------------------------------------------------------------- demo access code (ZEKA_ACCESS_CODE)
def test_demo_access_code_gate(app_db, monkeypatch, rate_limits):
    monkeypatch.setattr(security.CFG, "access_code", CODE)
    gate = app_db.client()
    # sec: bootstrap announces the access code
    assert gate.get("/api/bootstrap").json["app"]["access_required"] is True
    # sec: login without code refused
    assert gate.post("/api/auth/demo", {"role": "admin"}).status == 403
    # sec: login with wrong code refused
    assert gate.post("/api/auth/demo", {"role": "admin", "code": "guess"}).status == 403
    # sec: GET demo login without code refused
    assert app_db.client().get("/demo/login?role=admin").status == 403
    # sec: login with the code works
    assert gate.post("/api/auth/demo", {"role": "student", "code": CODE}).status == 200
    # sec: role switch inside a session needs no code
    assert gate.post("/api/auth/demo", {"role": "teacher"}).status == 200


def test_access_code_guessing_is_throttled(app_db, monkeypatch, rate_limits):
    monkeypatch.setattr(security.CFG, "access_code", CODE)
    brute = app_db.client()
    codes = [brute.post("/api/auth/demo", {"role": "admin", "code": f"x{i}"}).status for i in range(12)]
    # sec: access-code guessing is throttled
    assert codes[:10] == [403] * 10 and codes[-1] == 429, codes
    # sec: throttled client blocked even with the right code
    assert brute.post("/api/auth/demo", {"role": "admin", "code": CODE}).status == 429


# ---------------------------------------------------------------- stored HTML injection in the printable syllabus
def test_syllabus_page_escapes_saved_data(teacher):
    tcid = teacher.get("/api/courses").json[0]["id"]
    syl = teacher.post(f"/api/syllabus/{tcid}/generate", {"weeks": 15}).json
    syl["plan"][0]["week"] = EVIL
    syl["assessment"][0][1] = EVIL
    syl["workload"]["total"] = EVIL
    syl["course"]["credits"] = EVIL
    syl["description"] = EVIL
    # sec: syllabus save   (stricter than in the review: markup in place of a score is refused, not coerced to 0)
    assert teacher.put(f"/api/syllabus/{tcid}", {"data": syl}).status == 400
    syl["assessment"][0][1] = 10
    assert teacher.put(f"/api/syllabus/{tcid}", {"data": syl}).status == 200
    r = teacher.get(f"/syllabus/{tcid}")
    # sec: syllabus page escapes saved data
    assert r.status == 200 and "<script>" not in r.text and "<img src=x" not in r.text and "&lt;script&gt;" in r.text, r.text[:200]
    # sec: syllabus shape validated
    assert teacher.put(f"/api/syllabus/{tcid}", {"data": {"course": "x"}}).status == 400


# ---------------------------------------------------------------- AI Academy
def test_academy_key_is_hidden_after_a_failed_attempt(teacher):
    mod = next(m for t in teacher.get("/api/academy").json["tracks"] for m in t["modules"])
    quiz = teacher.get(f"/api/academy/module/{mod['id']}").json["quiz"]
    r = teacher.post(f"/api/academy/module/{mod['id']}/complete", {"answers": [-1] * len(quiz)})
    # sec: academy key hidden after a failed attempt
    assert r.status == 200 and not r.json["passed"] and all(x is None for x in r.json["correct"]), r.json


# ---------------------------------------------------------------- quiz time limit
def test_late_quiz_answers_are_not_graded(app_db):
    student = app_db.client("student")
    quiz = next(q for q in student.get("/api/quizzes").json if q.get("can_start"))
    start = student.post(f"/api/quizzes/{quiz['id']}/start").json
    set_time("attempts", "started_at", "id", start["attempt_id"])
    db = store.connect()
    try:
        answers = {str(q["id"]): store.J(store.row(db, "SELECT answer FROM questions WHERE id=?", (q["id"],))["answer"]) for q in start["questions"]}
    finally:
        db.close()
    late = student.post(f"/api/attempts/{start['attempt_id']}/submit", {"answers": answers})
    # sec: late quiz answers are not graded   (the time limit is enforced by the server, not only by the browser timer)
    assert late.status == 200 and late.json["score"] == 0 and all(d["given"] == "—" for d in late.json["details"]), late.json


# ---------------------------------------------------------------- privacy
def test_consent_is_recorded_as_choices(app_db):
    student = app_db.client("student")
    student.post("/api/consent", {"ai": True, "external": False, "junk": "x" * 5000})
    prefs = student.get("/api/me").json["prefs"]
    # sec: consent choices stored (no arbitrary payload)
    assert prefs.get("consent") == {"ai": True, "external": False}, prefs


def test_history_is_masked_before_an_external_llm_call():
    hm = _masked_history([{"role": "user", "content": "Mənim nömrəm +994 50 123 45 67"}, {"role": "assistant", "content": "ok"}], True)
    # sec: history masked for the LLM
    assert "+994" not in hm[0]["content"] and hm[1]["content"] == "ok", hm


# ---------------------------------------------------------------- helpers
def test_safe_next():
    # sec: safe_next
    assert security.safe_next("/#/student") == "/#/student" and security.safe_next("//evil") == "/"
    assert security.safe_next("/\tx") == "/" and security.safe_next("/a\r\nb") == "/" and security.safe_next("javascript:alert(1)") == "/"


def test_rate_limiter():
    lim = security.RateLimiter(3, 60)
    # sec: rate limiter
    assert [lim.hit("k") for _ in range(4)] == [True, True, True, False] and lim.hit("other")
