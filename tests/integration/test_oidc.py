"""Single sign-on through a generic OpenID Connect provider (tasks/todo.md, Task 14).

The provider is a fake written with the standard library (http.server on a loopback port, demo mode): discovery,
/authorize with PKCE and nonce, /token, /userinfo. Knobs change one thing per test: the claims of the person who signs
in, a tampered ID token claim or header, a different userinfo subject, a changed discovery document.
"""
import base64
import hashlib
import json
import re
import threading
import types
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from zeka.core import config
from zeka.legacy import store
from zeka.modules.identity import domain, service, sso

CLIENT_ID = "zeka-test"
GOOD = "müəllimin uzun və yaxşı parolu"


class IdP:
    """The provider's knobs and what it saw."""
    base = ""
    person: dict = {}             # claims of the person who signs in (sub, email, amr, ...)
    header: dict = {}             # the ID token's JOSE header
    tamper: dict = {}             # ID token claims overridden after the honest ones
    userinfo: dict = {}           # userinfo claims overridden
    discovery: dict = {}          # discovery document overrides
    codes: dict = {}              # code -> the /authorize request
    seen: list = []               # token requests


def _b64(d) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        q = dict(urllib.parse.parse_qsl(url.query))
        if url.path == "/.well-known/openid-configuration":
            return self._json({"issuer": IdP.base, "authorization_endpoint": IdP.base + "/authorize",
                               "token_endpoint": IdP.base + "/token", "userinfo_endpoint": IdP.base + "/userinfo",
                               "jwks_uri": IdP.base + "/jwks", **IdP.discovery})
        if url.path == "/authorize":
            code = "code-" + str(len(IdP.seen) + len(IdP.codes) + 1)
            IdP.codes[code] = q
            self.send_response(302)
            self.send_header("Location", q["redirect_uri"] + "?" + urllib.parse.urlencode({"code": code, "state": q["state"]}))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        if url.path == "/userinfo":
            if self.headers.get("Authorization") != "Bearer at-" + IdP.person["sub"]:
                return self._json({"error": "invalid_token"}, 401)
            return self._json({**IdP.person, **IdP.userinfo})
        return self._json({}, 404)

    def do_POST(self):
        form = dict(urllib.parse.parse_qsl(self.rfile.read(int(self.headers["Content-Length"])).decode()))
        IdP.seen.append({"form": form, "auth": self.headers.get("Authorization")})
        asked = IdP.codes.pop(form.get("code"), None)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(form.get("code_verifier", "").encode()).digest()).decode().rstrip("=")
        if not asked or asked["redirect_uri"] != form.get("redirect_uri") or asked["code_challenge_method"] != "S256" \
                or asked["code_challenge"] != challenge or form.get("grant_type") != "authorization_code":
            return self._json({"error": "invalid_grant"}, 400)
        claims = {"iss": IdP.base, "aud": CLIENT_ID, "exp": 4_000_000_000, "iat": 1_700_000_000, "nonce": asked["nonce"],
                  **{k: v for k, v in IdP.person.items() if k in ("sub", "amr", "acr")}, **IdP.tamper}
        token = _b64(IdP.header or {"alg": "RS256", "typ": "JWT"}) + "." + _b64(claims) + ".c2ln"
        return self._json({"access_token": "at-" + IdP.person["sub"], "token_type": "Bearer", "id_token": token})


@pytest.fixture(scope="module")
def idp():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    IdP.base = f"http://127.0.0.1:{srv.server_address[1]}"
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield IdP
    srv.shutdown()
    srv.server_close()


def db():
    return store.connect()


def set_sso(**fields):
    c = db()
    try:
        store.set_setting(c, "sso", {"enabled": True, "issuer": IdP.base, "client_id": CLIENT_ID, "label": "AzTU hesabı",
                                     "student_claim": "student_number", "mfa_amr": ["mfa"], **fields})
        c.commit()
    finally:
        c.close()
    sso._CACHE.clear()
    sso._FAILED.clear()


@pytest.fixture(autouse=True)
def setup(app_db, idp, monkeypatch):
    monkeypatch.setattr(domain, "N", 2 ** 4)
    IdP.person, IdP.header, IdP.tamper, IdP.userinfo, IdP.discovery, IdP.codes, IdP.seen = {}, {}, {}, {}, {}, {}, []
    set_sso()
    c = db()
    try:
        for table in ("sso_identities", "sso_pending", "login_blocks", "recovery_codes"):
            c.execute(f"DELETE FROM {table}")
        c.execute("UPDATE users SET email=NULL, student_no=NULL, status='active', password_hash=NULL, must_change=0, "
                  "totp_secret=NULL, totp_last=NULL, totp_enabled_at=NULL")
        c.commit()
    finally:
        c.close()


def person(role, **fields):
    """The demo account of a role, with the given columns set; returns its row."""
    c = db()
    try:
        name = store.setting(c, "demo_logins")[role]
        for k, v in fields.items():
            c.execute(f"UPDATE users SET {k}=? WHERE username=?", (v, name))
        c.commit()
        return store.row(c, "SELECT * FROM users WHERE username=?", (name,))
    finally:
        c.close()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def browser(app_db, role=None):
    """An API client that does not follow redirects, so every hop of the flow is visible."""
    b = app_db.client()
    b.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()), urllib.request.ProxyHandler({}),
                                           _NoRedirect)
    if role:
        b.login(role)
    return b


def hop(b, url):
    """(status, Location) of one request."""
    try:
        with b.opener.open(url, timeout=30) as r:
            return r.status, r.headers.get("Location")
    except urllib.error.HTTPError as e:
        e.close()
        return e.code, e.headers.get("Location")


def to_provider(app_db, b, where=None):
    """Start (or take the provider address ``where``) and sign in at the provider; returns the callback address."""
    if where is None:
        status, where = hop(b, app_db.url + "/api/auth/sso/start")
        assert status == 302, status
    assert where.startswith(IdP.base + "/authorize?"), where
    status, back = hop(b, where)
    assert status == 302, status
    return back


def sso_sign_in(app_db, b=None, **claims):
    """The whole flow for a person with these claims; returns (browser, final Location)."""
    IdP.person = {"sub": "sub-1", **claims}
    b = b or browser(app_db)
    status, where = hop(b, to_provider(app_db, b))
    assert status == 302, status
    return b, where


def bindings():
    c = db()
    try:
        return store.rows(c, "SELECT user_id, iss, sub, linked_by FROM sso_identities ORDER BY id")
    finally:
        c.close()


def signed_in(b):
    return b.get("/api/bootstrap").json["user"]


def test_the_full_flow_signs_a_student_in_by_the_student_number_claim(app_db):
    aysel = person("student", student_no="S-90001")
    b, where = sso_sign_in(app_db, student_number="S-90001")
    assert where == "/"
    me = signed_in(b)
    assert me["id"] == aysel["id"] and me["scope"] == "full"
    assert bindings() == [{"user_id": aysel["id"], "iss": IdP.base, "sub": "sub-1", "linked_by": "student_no"}]
    assert IdP.seen[0]["form"]["client_id"] == CLIENT_ID and IdP.seen[0]["auth"] is None     # a public client: PKCE alone
    assert app_db.client().get("/api/bootstrap").json["app"]["sso"] == {"enabled": True, "label": "AzTU hesabı"}
    b2, where = sso_sign_in(app_db)                    # the second time only (iss, sub) is needed
    assert where == "/" and signed_in(b2)["id"] == aysel["id"] and len(bindings()) == 1


def test_a_client_secret_is_sent_with_basic_authentication(app_db, monkeypatch):
    monkeypatch.setenv(sso.SECRET_ENV, "s3cr:et/+")
    person("student", student_no="S-90001")
    assert sso_sign_in(app_db, student_number="S-90001")[1] == "/"
    pair = base64.b64decode(IdP.seen[0]["auth"].split()[1]).decode()
    assert [urllib.parse.unquote_plus(x) for x in pair.split(":")] == [CLIENT_ID, "s3cr:et/+"]
    assert "client_id" not in IdP.seen[0]["form"]


def test_a_tampered_state_or_a_callback_from_another_browser_is_refused(app_db):
    person("student", student_no="S-90001")
    IdP.person = {"sub": "sub-1", "student_number": "S-90001"}
    b = browser(app_db)
    back = to_provider(app_db, b)
    assert hop(b, re.sub(r"state=[^&]+", "state=forged", back))[1] == "/#/login?sso=expired"
    other = browser(app_db)                            # the callback link opened in another browser: no binding cookie
    assert hop(other, back)[1] == "/#/login?sso=expired"
    assert hop(b, back)[1] == "/#/login?sso=expired", "the other browser's try spent the state"
    assert not bindings() and signed_in(b) is None and signed_in(other) is None


def test_a_state_is_good_once(app_db):
    person("student", student_no="S-90001")
    IdP.person = {"sub": "sub-1", "student_number": "S-90001"}
    b = browser(app_db)
    back = to_provider(app_db, b)
    assert hop(b, back)[1] == "/"
    assert hop(b, back)[1] == "/#/login?sso=expired"


@pytest.mark.parametrize("tamper", [{"nonce": "other"}, {"iss": "https://evil.example"}, {"aud": "other-client"},
                                    {"aud": [CLIENT_ID, "other-client"]}, {"azp": "other-client"}, {"exp": 1_000_000_000},
                                    {"iat": 4_000_000_000}, {"sub": ""}])
def test_a_wrong_id_token_is_refused(app_db, tamper):
    person("student", student_no="S-90001")
    IdP.tamper = tamper
    b, where = sso_sign_in(app_db, student_number="S-90001")
    assert where == "/#/login?sso=failed"
    assert signed_in(b) is None and not bindings()


def test_an_unsigned_id_token_is_refused(app_db):
    person("student", student_no="S-90001")
    IdP.header = {"alg": "none"}
    assert sso_sign_in(app_db, student_number="S-90001")[1] == "/#/login?sso=failed"


def test_a_userinfo_subject_other_than_the_id_token_s_is_refused(app_db):
    person("student", student_no="S-90001")
    IdP.userinfo = {"sub": "someone-else"}
    b, where = sso_sign_in(app_db, student_number="S-90001")
    assert where == "/#/login?sso=failed" and signed_in(b) is None


def test_the_refusal_reason_is_audited(app_db):
    IdP.tamper = {"aud": "other-client"}
    sso_sign_in(app_db)
    c = db()
    try:
        assert store.row(c, "SELECT detail FROM audit WHERE action='sso_refused' ORDER BY id DESC LIMIT 1")["detail"] == "aud"
    finally:
        c.close()


def test_an_unknown_person_gets_account_not_found_and_no_account_is_made(app_db):
    c = db()
    before = store.row(c, "SELECT COUNT(*) n FROM users")["n"]
    c.close()
    b, where = sso_sign_in(app_db, student_number="S-00000", email="nobody@aztu.edu.az", email_verified=True)
    assert where == "/#/login?sso=not_found" and signed_in(b) is None
    c = db()
    assert store.row(c, "SELECT COUNT(*) n FROM users")["n"] == before
    c.close()
    assert not bindings()


def test_an_unverified_e_mail_links_nothing(app_db):
    person("student", email="aysel@aztu.edu.az")
    for verified in ({"email_verified": False}, {"email_verified": "true"}, {}):
        assert sso_sign_in(app_db, email="aysel@aztu.edu.az", **verified)[1] == "/#/login?sso=not_found", verified
    assert not bindings()


def test_a_verified_e_mail_links_a_student(app_db):
    aysel = person("student", email="aysel@aztu.edu.az")
    b, where = sso_sign_in(app_db, email="Aysel@AzTU.edu.az", email_verified=True)
    assert where == "/" and signed_in(b)["id"] == aysel["id"] and bindings()[0]["linked_by"] == "email"


def test_a_staff_account_is_never_linked_by_e_mail_or_student_number(app_db):
    person("teacher", email="muellim@aztu.edu.az", student_no="S-90002")
    _, where = sso_sign_in(app_db, email="muellim@aztu.edu.az", email_verified=True, student_number="S-90002")
    assert where == "/#/login?sso=not_found" and not bindings()


def test_a_student_with_a_staff_grant_is_not_linked_automatically(app_db):
    aysel = person("student", email="aysel@aztu.edu.az")
    c = db()
    c.execute("INSERT INTO role_grants(user_id,role,granted_at) VALUES(?,?,?)", (aysel["id"], "proctor", store.iso(store.now())))
    c.commit()
    c.close()
    try:
        assert sso_sign_in(app_db, email="aysel@aztu.edu.az", email_verified=True)[1] == "/#/login?sso=not_found"
    finally:
        c = db()
        c.execute("DELETE FROM role_grants WHERE user_id=? AND role='proctor'", (aysel["id"],))
        c.commit()
        c.close()


def test_a_changed_e_mail_at_the_provider_does_not_move_the_sign_in(app_db):
    aysel = person("student", email="aysel@aztu.edu.az")
    assert sso_sign_in(app_db, email="aysel@aztu.edu.az", email_verified=True)[1] == "/"
    c = db()
    other = store.row(c, "SELECT id FROM users WHERE role='student' AND id<>? ORDER BY id LIMIT 1", (aysel["id"],))["id"]
    c.execute("UPDATE users SET email='kamran@aztu.edu.az' WHERE id=?", (other,))
    c.commit()
    c.close()
    b, where = sso_sign_in(app_db, email="kamran@aztu.edu.az", email_verified=True)      # same sub, the other's address
    assert where == "/" and signed_in(b)["id"] == aysel["id"] and len(bindings()) == 1


def test_a_disabled_account_cannot_sign_in_through_the_provider(app_db):
    person("student", student_no="S-90001")
    assert sso_sign_in(app_db, student_number="S-90001")[1] == "/"
    person("student", status="disabled")
    assert sso_sign_in(app_db, student_number="S-90001")[1] == "/#/login?sso=not_found"


def test_the_person_cancelling_at_the_provider_comes_back_to_the_sign_in_page(app_db):
    b = browser(app_db)
    _, where = hop(b, app_db.url + "/api/auth/sso/start")
    state = urllib.parse.parse_qs(urllib.parse.urlsplit(where).query)["state"][0]
    back = app_db.url + "/api/auth/sso/callback?" + urllib.parse.urlencode({"error": "access_denied", "state": state})
    assert hop(b, back)[1] == "/#/login?sso=cancelled"


def test_the_authorization_request_carries_pkce_state_and_nonce(app_db):
    b = browser(app_db)
    _, where = hop(b, app_db.url + "/api/auth/sso/start")
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(where).query)
    assert q["response_type"] == ["code"] and q["code_challenge_method"] == ["S256"] and q["client_id"] == [CLIENT_ID]
    assert q["redirect_uri"] == [app_db.url + "/api/auth/sso/callback"] and "openid" in q["scope"][0].split()
    assert all(len(q[k][0]) >= 40 for k in ("state", "nonce", "code_challenge"))


# ---------------------------------------------------------------- staff: linking and the second factor
def admin_links(app_db, u, sub="sub-1"):
    r = app_db.client("admin").post(f"/api/admin/users/{u['id']}/sso", {"sub": sub})
    assert r.status == 200, r.text


def test_without_the_provider_s_mfa_a_staff_member_still_needs_the_local_second_factor(app_db):
    admin_links(app_db, person("teacher"))
    b, where = sso_sign_in(app_db, amr=["pwd"])
    assert where == "/" and signed_in(b)["scope"] == "mfa_enroll"
    assert b.get("/api/courses").status == 403, "nothing but the enrolment is open"
    b, _ = sso_sign_in(app_db)                         # no amr at all
    assert signed_in(b)["scope"] == "mfa_enroll"
    b, _ = sso_sign_in(app_db, amr=["pwd", "mfa"])     # the tenant trusts "mfa" from this provider
    assert signed_in(b)["scope"] == "full"


def test_a_staff_member_with_totp_must_enter_the_code_after_the_provider(app_db):
    admin_links(app_db, person("teacher", totp_secret=domain.new_totp_secret(), totp_enabled_at=store.iso(store.now())))
    b, _ = sso_sign_in(app_db, amr=["pwd"])
    assert signed_in(b)["scope"] == "mfa"


def test_an_mfa_claim_counts_only_when_the_tenant_trusts_it(app_db):
    set_sso(mfa_amr=[])
    admin_links(app_db, person("teacher"))
    b, _ = sso_sign_in(app_db, amr=["mfa"])
    assert signed_in(b)["scope"] == "mfa_enroll"
    set_sso(mfa_amr=[], mfa_acr=["urn:aztu:mfa"])
    b, _ = sso_sign_in(app_db, acr="urn:aztu:mfa")
    assert signed_in(b)["scope"] == "full"


def test_the_administrator_links_and_unlinks_and_a_taken_subject_is_refused(app_db):
    teacher, office = person("teacher"), person("office")
    admin = app_db.client("admin")
    admin_links(app_db, teacher)
    assert admin.post(f"/api/admin/users/{office['id']}/sso", {"sub": "sub-1"}).status == 409
    assert admin.post(f"/api/admin/users/{teacher['id']}/sso", {"sub": "sub-2"}).status == 409, "one per issuer"
    assert admin.post(f"/api/admin/users/{teacher['id']}/sso", {"sub": ""}).status == 400
    iid = admin.get(f"/api/admin/users/{teacher['id']}/sso").json[0]["id"]
    assert admin.delete(f"/api/admin/users/{teacher['id']}/sso/{iid}").status == 200
    assert admin.delete(f"/api/admin/users/{teacher['id']}/sso/{iid}").status == 404
    assert not bindings()
    assert app_db.client("teacher").post(f"/api/admin/users/{teacher['id']}/sso", {"sub": "x"}).status == 403


def test_a_staff_member_links_only_from_a_password_and_totp_session(app_db, monkeypatch):
    assert browser(app_db, "teacher").post("/api/auth/sso/link").status == 403     # a session without the second factor
    now = 1_900_000_005.0
    monkeypatch.setattr(service, "time", types.SimpleNamespace(time=lambda: now))
    teacher = person("teacher", password_hash=domain.hash_password(GOOD))
    b = browser(app_db)
    assert b.post("/api/auth/login", {"login": teacher["username"], "password": GOOD}).json["user"]["scope"] == "mfa_enroll"
    assert b.post("/api/auth/sso/link").status == 403, "not before the second factor"
    secret = b.post("/api/auth/mfa/enroll").json["secret"]
    assert b.post("/api/auth/mfa/confirm", {"code": domain.hotp(domain.totp_key(secret), int(now) // 30)}).status == 200
    IdP.person = {"sub": "sub-t"}
    back = to_provider(app_db, b, b.post("/api/auth/sso/link").json["url"])
    assert hop(b, back)[1] == "/#/profile?sso=linked"
    assert bindings() == [{"user_id": teacher["id"], "iss": IdP.base, "sub": "sub-t", "linked_by": "owner"}]
    assert [x["iss"] for x in b.get("/api/me/sso").json] == [IdP.base]


def test_a_student_links_from_their_own_session_and_a_taken_identity_is_refused(app_db):
    student = browser(app_db, "student")
    IdP.person = {"sub": "sub-s"}
    back = to_provider(app_db, student, student.post("/api/auth/sso/link").json["url"])
    assert hop(student, back)[1] == "/#/profile?sso=linked"
    admin = app_db.client("admin")
    assert admin.post(f"/api/admin/users/{person('teacher')['id']}/sso", {"sub": "sub-s"}).status == 409
    other = browser(app_db, "student")                 # the same account again: one binding per issuer
    back = to_provider(app_db, other, other.post("/api/auth/sso/link").json["url"])
    assert hop(other, back)[1] == "/#/profile?sso=taken"


def test_a_link_finished_after_signing_out_is_refused(app_db):
    student = browser(app_db, "student")
    IdP.person = {"sub": "sub-s"}
    back = to_provider(app_db, student, student.post("/api/auth/sso/link").json["url"])
    student.post("/api/auth/logout")
    assert hop(student, back)[1] == "/#/profile?sso=expired"
    assert not bindings()


# ---------------------------------------------------------------- transport rules
def test_prod_refuses_an_http_issuer(app_db, monkeypatch):
    monkeypatch.setattr(config, "MODE", "prod")
    assert app_db.client().get("/api/bootstrap").json["app"]["sso"]["enabled"] is False
    assert hop(browser(app_db), app_db.url + "/api/auth/sso/start") == (302, "/#/login?sso=off")


def test_prod_refuses_a_discovery_document_with_an_endpoint_that_is_not_https(app_db, monkeypatch):
    monkeypatch.setattr(config, "MODE", "prod")
    set_sso(issuer="https://idp.example")
    doc = {"issuer": "https://idp.example", "authorization_endpoint": "https://idp.example/authorize",
           "token_endpoint": "https://idp.example/token", "userinfo_endpoint": "http://idp.example/userinfo"}
    monkeypatch.setattr(sso, "_call", lambda url, *a, **k: dict(doc))
    b = browser(app_db)
    assert hop(b, app_db.url + "/api/auth/sso/start") == (302, "/#/login?sso=failed")
    doc["userinfo_endpoint"] = "https://idp.example/userinfo"
    assert hop(b, app_db.url + "/api/auth/sso/start") == (302, "/#/login?sso=failed"), "a failed discovery is kept 30 s"
    sso._FAILED.clear()
    status, where = hop(b, app_db.url + "/api/auth/sso/start")
    assert status == 302 and where.startswith("https://idp.example/authorize?")


def test_a_discovery_document_of_another_issuer_is_refused(app_db):
    IdP.discovery = {"issuer": "https://elsewhere.example"}
    assert hop(browser(app_db), app_db.url + "/api/auth/sso/start") == (302, "/#/login?sso=failed")


def test_sso_is_off_until_it_is_configured(app_db):
    c = db()
    c.execute("DELETE FROM settings WHERE key='sso'")
    c.commit()
    c.close()
    assert app_db.client().get("/api/bootstrap").json["app"]["sso"] == {"enabled": False, "label": None}
    assert hop(browser(app_db), app_db.url + "/api/auth/sso/start") == (302, "/#/login?sso=off")
    assert browser(app_db, "student").post("/api/auth/sso/link").status == 404
