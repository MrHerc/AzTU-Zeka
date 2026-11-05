"""Shared fixtures for the Zəka test suite.

Every test runs against a throw-away copy of the demo database: ``store.DATA`` / ``store.UPLOADS`` /
``store.DB_PATH`` are redirected to a temporary directory *before* any application module can cache the
real paths, so the repository's ``data/`` folder is never read or modified. The optional LLM is disabled by
pointing ``engine.ROOT`` (where ``config.json`` is looked up) at the same empty directory and clearing the
``AZTU_LLM_*`` environment variables, so no test can ever reach a network provider.

An in-process HTTP server (``app.web.make_server`` on port 0) serves the API for integration tests.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from http.cookiejar import CookieJar
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="zeka-tests-"))

from app import engine, store  # noqa: E402  (import after sys.path / before redirecting paths)

store.DATA = TMP / "data"
store.UPLOADS = store.DATA / "uploads"
store.DB_PATH = store.DATA / "campus.db"
engine.ROOT = TMP  # no config.json here -> the demo engine is always used
for _k in ("AZTU_LLM_PROVIDER", "AZTU_LLM_BASE_URL", "AZTU_LLM_API_KEY", "AZTU_LLM_MODEL"):
    os.environ.pop(_k, None)

ROLES = ("student", "teacher", "office", "leader", "admin")


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(TMP, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def _isolated_paths():
    """Guard: the suite must never touch the repository's own data directory."""
    assert str(store.DB_PATH).startswith(str(TMP)), store.DB_PATH
    assert str(engine.ROOT) == str(TMP) and not (TMP / "config.json").exists()
    yield


def fresh_db():
    """(Re)create the demo database from scratch and rebuild the in-memory indexes."""
    store.init(reset=True)


@pytest.fixture
def db():
    """A freshly seeded database and an open connection (function scope: safe to mutate)."""
    fresh_db()
    c = store.connect()
    try:
        yield c
    finally:
        c.close()


@pytest.fixture(scope="module")
def seeded():
    """A seeded database shared by the read-only tests of one module; returns a connection factory."""
    fresh_db()
    conns = []

    def connect():
        c = store.connect()
        conns.append(c)
        return c

    yield connect
    for c in conns:
        c.close()


# ---------------------------------------------------------------- HTTP server & client
@dataclass
class Response:
    status: int
    body: bytes
    headers: dict

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")

    @property
    def json(self):
        ct = self.headers.get("Content-Type", "")
        assert ct.startswith("application/json"), f"not JSON ({ct}): {self.text[:200]}"
        return json.loads(self.body.decode("utf-8"))


class ApiClient:
    """Minimal cookie-aware JSON client (urllib, proxies disabled) for the in-process server."""

    def __init__(self, base: str, lang: str | None = None):
        self.base, self.lang = base, lang
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()), urllib.request.ProxyHandler({}))
        self.user = None

    def request(self, method: str, path: str, body=None, lang: str | None = None, headers: dict | None = None,
                raw: bytes | None = None) -> Response:
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
        hdr = {}
        if data is not None and raw is None:
            hdr["Content-Type"] = "application/json"
        if lang or self.lang:
            hdr["X-Lang"] = lang or self.lang
        hdr.update(headers or {})
        rq = urllib.request.Request(self.base + path, data=data, method=method, headers=hdr)
        try:
            with self.opener.open(rq, timeout=30) as r:
                return Response(r.status, r.read(), dict(r.headers))
        except urllib.error.HTTPError as e:
            return Response(e.code, e.read(), dict(e.headers))

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body if body is not None else {}, **kw)

    def put(self, path, body=None, **kw):
        return self.request("PUT", path, body if body is not None else {}, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    def login(self, role: str):
        r = self.post("/api/auth/demo", {"role": role})
        assert r.status == 200, r.text
        self.user = r.json["user"]
        return self.user


@dataclass
class Server:
    url: str
    port: int
    errors: list = field(default_factory=list)  # server-side tracebacks (500s) logged during the run

    def client(self, role: str | None = None, lang: str | None = None) -> ApiClient:
        c = ApiClient(self.url, lang)
        if role:
            c.login(role)
        return c


@pytest.fixture(scope="session")
def server():
    from app import api
    from app.web import make_server

    fresh_db()
    srv_errors: list = []
    srv = make_server(0, api.R, ROOT / "static", api.before, api.after, log=srv_errors.append)
    port = srv.server_address[1]
    api.BASE_URL["value"] = f"http://127.0.0.1:{port}"
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield Server(f"http://127.0.0.1:{port}", port, srv_errors)
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture(scope="module")
def app_db(server):
    """Fresh demo data for one integration test module (module scope: the flows build on each other)."""
    fresh_db()
    server.errors.clear()
    yield server


def _role_fixture(role):
    @pytest.fixture(scope="module", name=role)
    def fx(app_db):
        return app_db.client(role)

    fx.__doc__ = f"Logged-in {role} client (module scope)."
    return fx


student = _role_fixture("student")
teacher = _role_fixture("teacher")
office = _role_fixture("office")
leader = _role_fixture("leader")
admin = _role_fixture("admin")


@pytest.fixture
def anon(app_db):
    """A client without a session."""
    return app_db.client()


# ---------------------------------------------------------------- helpers
def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


@pytest.fixture
def pdf_bytes():
    return store.demo_pdf(["DEMO HEKIM ARAYISI", "Ambulator mualice"])
