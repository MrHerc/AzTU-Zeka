"""API keys (tasks/todo.md, Task 37): a key reaches only the routes of its scopes, only by its Bearer header (a cookie
session reaches no key route, a key reaches no cookie route); it is kept as a hash, limited per minute, revocable, and
every call and refusal is audited."""
import http.client
import json
from urllib.parse import urlsplit

from zeka.legacy import store


def q(sql, args=()):
    c = store.connect()
    try:
        return store.rows(c, sql, args)
    finally:
        c.close()


def call(app_db, path: str, token: str | None = None, cookie_client=None):
    """A request with only the Bearer header (no cookie), or through a signed-in client when given."""
    if cookie_client is not None:
        return cookie_client.get(path).status
    u = urlsplit(app_db.url)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=30)
    try:
        conn.request("GET", path, headers={"Authorization": f"Bearer {token}"} if token else {})
        r = conn.getresponse()
        r.read()
        return r.status
    finally:
        conn.close()


def key(app_db, scopes, per_minute=60, name="Sınaq açarı"):
    r = app_db.client("admin").post("/api/integration/keys", {"name": name, "scopes": scopes, "per_minute": per_minute})
    assert r.status == 200, r.text
    return r.json


def test_only_the_administrator_manages_keys_and_a_key_is_shown_once_and_kept_as_a_hash(app_db):
    for role in ("office", "leader", "teacher", "student"):
        assert app_db.client(role).post("/api/integration/keys", {"name": "X açar", "scopes": ["grades.read"]}).status == 403, role
    admin = app_db.client("admin")
    assert admin.post("/api/integration/keys", {"name": "X açar", "scopes": ["everything"]}).status == 400
    assert admin.post("/api/integration/keys", {"name": "X açar", "scopes": []}).status == 400
    k = key(app_db, ["grades.read"])
    assert k["token"].startswith("zk_") and "token" not in json.dumps(admin.get("/api/integration/keys").json)
    assert not q("SELECT 1 FROM api_tokens WHERE token_hash=? OR prefix=?", (k["token"], k["token"]))
    assert q("SELECT 1 FROM audit WHERE action='api_key_create' AND detail LIKE ?", (f"#{k['id']} %",))


def test_a_key_reaches_only_its_scopes_and_only_by_its_header(app_db):
    k = key(app_db, ["grades.read"])
    assert call(app_db, "/api/v1/grades", k["token"]) == 200
    for path in ("/api/v1/attendance", "/api/v1/oneroster.zip", "/api/v1/status-changes"):
        assert call(app_db, path, k["token"]) == 403, path
    assert call(app_db, "/api/v1/grades") == 401
    assert call(app_db, "/api/v1/grades", "zk_" + "x" * 43) == 401
    assert call(app_db, "/api/v1/grades", cookie_client=app_db.client("admin")) == 401, "a cookie session reaches no key route"
    assert call(app_db, "/api/integration/keys", k["token"]) == 401, "a key reaches no cookie route"
    assert call(app_db, "/api/me", k["token"]) == 401
    assert q("SELECT 1 FROM audit WHERE action='api_call' AND detail=?", (f"#{k['id']} /api/v1/grades",))
    assert q("SELECT 1 FROM audit WHERE action='api_call_refused' AND detail LIKE ?", (f"#{k['id']} /api/v1/attendance%",))


def test_a_key_has_its_own_limit_and_a_revoked_key_is_refused(app_db):
    k = key(app_db, ["attendance.read"], per_minute=2, name="Limitli açar")
    assert [call(app_db, "/api/v1/attendance", k["token"]) for _ in range(3)] == [200, 200, 429]
    other = key(app_db, ["attendance.read"], name="Başqa açar")
    assert call(app_db, "/api/v1/attendance", other["token"]) == 200, "the limit is the key's own"
    assert app_db.client("admin").post(f"/api/integration/keys/{other['id']}/revoke").status == 200
    assert call(app_db, "/api/v1/attendance", other["token"]) == 401
    assert app_db.client("admin").post(f"/api/integration/keys/{other['id']}/revoke").status == 404, "once"
